"""
Drift must not pay for a repository that has not changed.

Drift asks GitHub what is in every branch a project delivers to, on every
check. That cost is why a pattern-mode project could burn a meaningful share of
an hourly rate limit just by having its page opened a few times.

GitHub answers a conditional request (``If-None-Match``) for unchanged content
with a 304, and **304s do not count against the rate limit** (verified against
the live API). So the fix is not to check less, it is to make an unchanged
answer free.

The assertions here are about *call counts and cache state*, because "it still
reports drift correctly" was never the problem — the cost was.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Repo, WorkflowTreeCache  # noqa: E402
from workflows import (  # noqa: E402
    NotModified, DriftCheckUnavailable, _fetch_tree_using_cache,
    _filter_branches_by_recency,
)

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        repo = Repo(repo_name="acme/api")
        session.add(repo)
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _cache_row(db, branch="main"):
    return (
        db.query(WorkflowTreeCache)
        .filter(WorkflowTreeCache.branch == branch)
        .first()
    )


class TestUnchangedBranchesAreFree:
    def test_first_fetch_stores_the_etag_and_listing(self, db):
        with patch("workflows.fetch_workflow_tree",
                   return_value=({"ci.yml": "sha-1"}, 'W/"etag-1"')) as fetch:
            shas = _fetch_tree_using_cache(db, "acme/api", "acme", "api", "main", "tok")

        assert shas == {"ci.yml": "sha-1"}
        assert fetch.call_count == 1
        row = _cache_row(db)
        assert row.etag == 'W/"etag-1"'
        assert json.loads(row.sha_map_json) == {"ci.yml": "sha-1"}

    def test_second_fetch_sends_the_stored_etag(self, db):
        with patch("workflows.fetch_workflow_tree",
                   return_value=({"ci.yml": "sha-1"}, 'W/"etag-1"')):
            _fetch_tree_using_cache(db, "acme/api", "acme", "api", "main", "tok")

        with patch("workflows.fetch_workflow_tree",
                   side_effect=NotModified("unchanged")) as fetch:
            shas = _fetch_tree_using_cache(db, "acme/api", "acme", "api", "main", "tok")

        # The whole point: the conditional request carried our stored ETag...
        assert fetch.call_args.kwargs["etag"] == 'W/"etag-1"'
        # ...and the cached listing was replayed rather than refetched.
        assert shas == {"ci.yml": "sha-1"}
        assert fetch.call_count == 1

    def test_a_changed_branch_refreshes_the_cache(self, db):
        with patch("workflows.fetch_workflow_tree",
                   return_value=({"ci.yml": "sha-1"}, 'W/"etag-1"')):
            _fetch_tree_using_cache(db, "acme/api", "acme", "api", "main", "tok")

        with patch("workflows.fetch_workflow_tree",
                   return_value=({"ci.yml": "sha-2"}, 'W/"etag-2"')):
            shas = _fetch_tree_using_cache(db, "acme/api", "acme", "api", "main", "tok")

        assert shas == {"ci.yml": "sha-2"}
        row = _cache_row(db)
        assert row.etag == 'W/"etag-2"'
        assert json.loads(row.sha_map_json) == {"ci.yml": "sha-2"}

    def test_branches_are_cached_independently(self, db):
        with patch("workflows.fetch_workflow_tree",
                   return_value=({"ci.yml": "sha-a"}, 'W/"etag-a"')):
            _fetch_tree_using_cache(db, "acme/api", "acme", "api", "release/2.0", "tok")
        with patch("workflows.fetch_workflow_tree",
                   return_value=({"ci.yml": "sha-b"}, 'W/"etag-b"')):
            _fetch_tree_using_cache(db, "acme/api", "acme", "api", "release/2.1", "tok")

        assert _cache_row(db, "release/2.0").etag == 'W/"etag-a"'
        assert _cache_row(db, "release/2.1").etag == 'W/"etag-b"'


class TestNotModifiedIsNeverMistakenForEmpty:
    def test_304_without_a_cached_listing_refetches(self, db):
        """A 304 carries no body. Replaying an empty map would report every
        workflow in the repo as deleted — the same absence-vs-unknown trap
        DriftCheckUnavailable exists for."""
        calls = []

        def fake(owner, repo, branch, token, etag=None):
            calls.append(etag)
            if etag is None:
                return {"ci.yml": "sha-1"}, 'W/"etag-1"'
            raise NotModified("unchanged")

        # Seed a row carrying an ETag but no listing (e.g. a partial write).
        db.add(WorkflowTreeCache(repo_id=db.query(Repo).one().repo_id,
                                 branch="main", etag='W/"stale"', sha_map_json=None))
        db.commit()

        with patch("workflows.fetch_workflow_tree", side_effect=fake):
            shas = _fetch_tree_using_cache(db, "acme/api", "acme", "api", "main", "tok")

        assert shas == {"ci.yml": "sha-1"}
        # Conditional first, then an unconditional retry — never an empty result.
        assert calls == ['W/"stale"', None]

    def test_a_failed_listing_still_raises(self, db):
        with patch("workflows.fetch_workflow_tree",
                   side_effect=DriftCheckUnavailable("rate limited")):
            with pytest.raises(DriftCheckUnavailable):
                _fetch_tree_using_cache(db, "acme/api", "acme", "api", "main", "tok")

    def test_an_empty_repo_is_cached_as_empty(self, db):
        """A genuinely empty .github/workflows is a real answer, not unknown."""
        with patch("workflows.fetch_workflow_tree", return_value=({}, 'W/"etag-empty"')):
            shas = _fetch_tree_using_cache(db, "acme/api", "acme", "api", "main", "tok")

        assert shas == {}
        assert json.loads(_cache_row(db).sha_map_json) == {}


class TestBranchRecencyCache:
    def _filter(self, db, head_shas, repo_name="acme/api"):
        return _filter_branches_by_recency(
            "acme", "api", ["release/2.0", "release/2.1"], 30, {},
            user=None, db=db, repo_name=repo_name, head_shas=head_shas,
        )

    def test_recency_is_asked_once_per_branch_then_cached(self, db):
        heads = {"release/2.0": "head-a", "release/2.1": "head-b"}

        with patch("workflows._is_branch_recent", return_value=True) as recent:
            first = self._filter(db, heads)
            assert recent.call_count == 2

        with patch("workflows._is_branch_recent", return_value=True) as recent:
            second = self._filter(db, heads)
            # Nothing moved, so nothing needed asking.
            assert recent.call_count == 0

        assert first == second == ["release/2.0", "release/2.1"]

    def test_a_moved_branch_is_rechecked(self, db):
        """Invalidation is by head SHA, not a timer — so a branch that just
        became active is never wrongly skipped."""
        with patch("workflows._is_branch_recent", return_value=False):
            assert self._filter(db, {"release/2.0": "head-a", "release/2.1": "head-b"}) == []

        with patch("workflows._is_branch_recent", return_value=True) as recent:
            result = self._filter(db, {"release/2.0": "head-a", "release/2.1": "head-MOVED"})
            # Only the branch whose head changed was re-asked.
            assert recent.call_count == 1

        assert result == ["release/2.1"]

    def test_no_cache_without_a_repo_name(self, db):
        """Delivery leaves repo_name unset and must always ask GitHub, since it
        decides where we actually write."""
        heads = {"release/2.0": "head-a", "release/2.1": "head-b"}

        with patch("workflows._is_branch_recent", return_value=True) as recent:
            self._filter(db, heads, repo_name=None)
            self._filter(db, heads, repo_name=None)
            assert recent.call_count == 4


class TestBranchListingIsConditionalToo:
    """The branch listing was the last chargeable call in a warm check.

    Per-branch Trees reads answered 304 and recency was cached, but the
    listing itself was fetched in full on every check — so "an unchanged repo
    is free" was not quite true until this.
    """

    def _listing(self, status, payload=None, etag=None):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = payload or []
        resp.headers = {"ETag": etag} if etag else {}
        return resp

    def test_first_call_stores_the_listing_and_etag(self, db):
        from workflows import _fetch_all_branches
        payload = [{"name": "main", "commit": {"sha": "head-a"}}]

        with patch("workflows.requests.get",
                   return_value=self._listing(200, payload, 'W/"list-1"')) as get:
            heads = {}
            names = _fetch_all_branches("acme", "api", {}, head_shas=heads,
                                        db=db, repo_name="acme/api")

        assert names == ["main"]
        assert heads == {"main": "head-a"}
        assert get.call_count == 1
        row = (db.query(WorkflowTreeCache)
                 .filter(WorkflowTreeCache.branch == "*").first())
        assert row.etag == 'W/"list-1"'

    def test_second_call_replays_the_cache_on_304(self, db):
        from workflows import _fetch_all_branches
        payload = [{"name": "main", "commit": {"sha": "head-a"}}]
        with patch("workflows.requests.get",
                   return_value=self._listing(200, payload, 'W/"list-1"')):
            _fetch_all_branches("acme", "api", {}, db=db, repo_name="acme/api")

        with patch("workflows.requests.get",
                   return_value=self._listing(304)) as get:
            heads = {}
            names = _fetch_all_branches("acme", "api", {}, head_shas=heads,
                                        db=db, repo_name="acme/api")

        assert names == ["main"]
        assert heads == {"main": "head-a"}          # replayed, not refetched
        assert get.call_args.kwargs["headers"]["If-None-Match"] == 'W/"list-1"'

    def test_multi_page_repos_are_not_cached(self, db):
        """A stored ETag only covers page 1, so caching it would replay an
        incomplete branch list."""
        from workflows import _fetch_all_branches
        full_page = [{"name": f"b{i}", "commit": {"sha": f"s{i}"}} for i in range(100)]

        with patch("workflows.requests.get", side_effect=[
                self._listing(200, full_page, 'W/"list-1"'),   # cache probe
                self._listing(200, full_page, 'W/"list-1"'),   # page 1
                self._listing(200, []),                        # page 2, end
        ]):
            _fetch_all_branches("acme", "api", {}, db=db, repo_name="acme/api")

        assert (db.query(WorkflowTreeCache)
                  .filter(WorkflowTreeCache.branch == "*").first()) is None

    def test_delivery_does_not_use_the_cache(self, db):
        """Delivery decides where we write, so it always asks GitHub."""
        from workflows import _fetch_all_branches
        payload = [{"name": "main", "commit": {"sha": "head-a"}}]

        with patch("workflows._cached_branch_listing") as cached, \
             patch("workflows._fetch_branches_page",
                   return_value=self._listing(200, payload)):
            _fetch_all_branches("acme", "api", {}, db=db)   # no repo_name

        assert cached.call_count == 0
