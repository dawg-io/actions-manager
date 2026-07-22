"""
Regression tests for org-owned reusable workflow (RWX) discovery and repo creation.

These cover the bug where a user could not see/select reusable workflows in a
GitHub organization or create the reusable workflow repository under the org.

The relevant code paths live in ``backend/repos.py``:
- ``_resolve_target_owner`` validates the target owner & detects type via GitHub.
- ``GET /api/rwx-repos`` accepts an optional ``owner`` query parameter and uses
  the *target* owner's type for the search qualifier.
- ``POST /api/rwx-repos`` and ``POST /api/create-repo`` accept an optional
  ``owner`` field in the JSON body to create the repo under that owner.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Account
from repos import (
    _resolve_target_owner,
    _repos_create_url_for_owner,
    get_rwx_repos,
    create_rwx_repo,
    create_github_repo,
)
from fastapi import HTTPException

from sqlalchemy.pool import StaticPool

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _setup():
    Base.metadata.create_all(bind=engine)


def _teardown():
    Base.metadata.drop_all(bind=engine)


def _db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _make_response(status_code: int, json_data=None):
    resp = Mock()
    resp.status_code = status_code
    resp.json = Mock(return_value=json_data if json_data is not None else {})
    return resp


# --------------------- _resolve_target_owner ---------------------

class TestResolveTargetOwner:
    def setup_method(self):
        _setup()
        self.db = next(_db())

    def teardown_method(self):
        self.db.close()
        _teardown()

    def test_defaults_to_user_when_owner_omitted(self):
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()
        owner, otype = _resolve_target_owner("alice", None, "tok", self.db)
        assert owner == "alice"
        assert otype == "User"

    def test_returns_org_type_for_org_account_self(self):
        account = Account(
            github_user="my-org", github_email="org@example.com",
            account_type="enterprise", github_account_type="Organization",
        )
        self.db.add(account); self.db.commit()
        owner, otype = _resolve_target_owner("my-org", "my-org", "tok", self.db)
        assert owner == "my-org"
        assert otype == "Organization"

    @patch("repos.github_get")
    def test_resolves_org_owner_via_github_when_member(self, mock_get):
        # First call: GET /users/{owner} -> Organization
        # Second call: GET /user/memberships/orgs/{owner} -> 200 (member)
        mock_get.side_effect = [
            _make_response(200, {"type": "Organization"}),
            _make_response(200, {"state": "active"}),
        ]
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        owner, otype = _resolve_target_owner("alice", "my-org", "tok", self.db)
        assert owner == "my-org"
        assert otype == "Organization"
        # First call should query users endpoint, second should query memberships
        urls = [c.args[0] for c in mock_get.call_args_list]
        assert urls[0].endswith("/users/my-org")
        assert urls[1].endswith("/user/memberships/orgs/my-org")

    @patch("repos.github_get")
    def test_rejects_org_owner_when_not_a_member(self, mock_get):
        mock_get.side_effect = [
            _make_response(200, {"type": "Organization"}),
            _make_response(404, {"message": "Not Found"}),
        ]
        with pytest.raises(HTTPException) as exc:
            _resolve_target_owner("alice", "secret-org", "tok", self.db)
        assert exc.value.status_code == 403
        assert "secret-org" in exc.value.detail

    @patch("repos.github_get")
    def test_rejects_other_user_owner(self, mock_get):
        mock_get.return_value = _make_response(200, {"type": "User"})
        with pytest.raises(HTTPException) as exc:
            _resolve_target_owner("alice", "bob", "tok", self.db)
        assert exc.value.status_code == 403

    @patch("repos.github_get")
    def test_unknown_owner_returns_404(self, mock_get):
        mock_get.return_value = _make_response(404, {"message": "Not Found"})
        with pytest.raises(HTTPException) as exc:
            _resolve_target_owner("alice", "ghost", "tok", self.db)
        assert exc.value.status_code == 404


# --------------------- _repos_create_url_for_owner ---------------------

def test_repos_create_url_for_owner():
    assert _repos_create_url_for_owner("alice", "User") == "https://api.github.com/user/repos"
    assert _repos_create_url_for_owner("my-org", "Organization") == \
        "https://api.github.com/orgs/my-org/repos"
    # URL-encoding for unusual characters
    assert "/orgs/my%20org/repos" in _repos_create_url_for_owner("my org", "Organization")


# --------------------- GET /api/rwx-repos ---------------------

class TestGetRwxReposOrgSupport:
    def setup_method(self):
        _setup()
        self.db = next(_db())
        self._auth_patch = patch('repos._assert_session_owns_user')
        self._auth_patch.start()

    def teardown_method(self):
        self._auth_patch.stop()
        self.db.close()
        _teardown()

    @patch("repos.github_get")
    @patch("repos.user_tokens", {"my-org": "tok"})
    def test_org_login_auto_discovers_via_orgs_endpoint(self, mock_get):
        """Logged-in org account auto-discovers RWX repos via /orgs/{org}/repos."""
        account = Account(
            github_user="my-org", github_email="org@example.com",
            account_type="enterprise", github_account_type="Organization",
        )
        self.db.add(account); self.db.commit()

        captured_urls = []

        def _gh_get(url, *_args, **_kwargs):
            captured_urls.append(url)
            # Return one RWX repo and one non-RWX repo to verify topic filter.
            return _make_response(200, [
                {"id": 1, "name": "rwx", "full_name": "my-org/rwx",
                 "private": False, "html_url": "https://x", "topics": ["am-rwx"],
                 "owner": {"login": "my-org", "type": "Organization"}},
                {"id": 2, "name": "other", "full_name": "my-org/other",
                 "private": False, "html_url": "https://y", "topics": ["something-else"],
                 "owner": {"login": "my-org", "type": "Organization"}},
            ])

        mock_get.side_effect = _gh_get

        result = asyncio.run(
            get_rwx_repos("my-org", Mock(), self.db, None)
        )
        # Only the am-rwx-topic repo should be returned.
        assert len(result) == 1
        assert result[0]["full_name"] == "my-org/rwx"
        # And the org-scoped listing endpoint should be used (not /search).
        assert any("/orgs/my-org/repos" in u for u in captured_urls)
        assert not any("/search/repositories" in u for u in captured_urls)

    @patch("repos.github_get")
    @patch("repos.user_tokens", {"alice": "tok"})
    def test_personal_user_auto_discovers_org_rwx_repos(self, mock_get):
        """Regression: a personal user auto-sees RWX repos in orgs they belong to.

        This is the bug from comment 4348528442 — the dropdown only showed
        ``dawg-io/my-rwx-workflow`` and never ``whatsupdawg/my-rwx`` even
        though both are accessible. With auto-discovery, ``/user/repos``
        returns both and the topic filter retains both.
        """
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        captured_urls = []

        def _gh_get(url, *_args, **_kwargs):
            captured_urls.append(url)
            # /user/repos returns repos from BOTH the personal account AND
            # every org the user/App has access to. Mix in non-RWX repos
            # and a private repo to validate filtering paths.
            return _make_response(200, [
                {"id": 1, "name": "my-rwx-workflow",
                 "full_name": "dawg-io/my-rwx-workflow",
                 "private": False, "html_url": "https://x",
                 "topics": ["am-rwx"],
                 "owner": {"login": "dawg-io", "type": "User"}},
                {"id": 2, "name": "my-rwx",
                 "full_name": "whatsupdawg/my-rwx",
                 "private": False, "html_url": "https://y",
                 "topics": ["am-rwx", "ci"],
                 "owner": {"login": "whatsupdawg", "type": "Organization"}},
                {"id": 3, "name": "regular-app",
                 "full_name": "whatsupdawg/regular-app",
                 "private": False, "html_url": "https://z",
                 "topics": ["webapp"],
                 "owner": {"login": "whatsupdawg", "type": "Organization"}},
            ])

        mock_get.side_effect = _gh_get

        result = asyncio.run(
            get_rwx_repos("alice", Mock(), self.db, None)
        )
        full_names = sorted(r["full_name"] for r in result)
        assert full_names == ["dawg-io/my-rwx-workflow", "whatsupdawg/my-rwx"], (
            f"Auto-discovery should include both personal and org RWX repos; got {full_names}"
        )
        # And owner_type is preserved so the UI knows which is the org repo.
        org_repo = next(r for r in result if r["full_name"] == "whatsupdawg/my-rwx")
        assert org_repo["owner"] == "whatsupdawg"
        assert org_repo["owner_type"] == "Organization"
        # Discovery should hit the /user/repos endpoint, not /search.
        assert any("/user/repos" in u for u in captured_urls)
        assert not any("/search/repositories" in u for u in captured_urls)

    @patch("repos.github_get")
    @patch("repos.user_tokens", {"alice": "tok"})
    def test_personal_user_auto_discovery_excludes_non_rwx_repos(self, mock_get):
        """Repos without the am-rwx topic must never be returned."""
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        mock_get.side_effect = lambda *a, **k: _make_response(200, [
            {"id": 1, "name": "alice-app", "full_name": "alice/alice-app",
             "private": False, "html_url": "https://x", "topics": ["webapp"],
             "owner": {"login": "alice", "type": "User"}},
            {"id": 2, "name": "no-topics", "full_name": "alice/no-topics",
             "private": False, "html_url": "https://y", "topics": None,
             "owner": {"login": "alice", "type": "User"}},
        ])

        result = asyncio.run(
            get_rwx_repos("alice", Mock(), self.db, None)
        )
        assert result == []

    @patch("repos.httpx.AsyncClient")
    @patch("repos.github_get")
    @patch("repos.user_tokens", {"alice": "tok"})
    def test_explicit_owner_still_uses_search_qualifier(self, mock_get, mock_client_cls):
        """The advanced single-owner override path still works for backward compat."""
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        # _resolve_target_owner GitHub calls (org type + membership active):
        mock_get.side_effect = [
            _make_response(200, {"type": "Organization"}),
            _make_response(200, {"state": "active"}),
        ]

        captured = {}
        async def _async_get(url, headers=None):
            captured.setdefault("urls", []).append(url)
            return _make_response(200, {"items": [
                {"id": 7, "name": "shared-flows",
                 "full_name": "my-org/shared-flows", "private": True,
                 "html_url": "https://x",
                 "owner": {"login": "my-org", "type": "Organization"}}
            ]})
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=_async_get)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(
            get_rwx_repos("alice", Mock(), self.db, "my-org")
        )
        assert len(result) == 1
        assert result[0]["full_name"] == "my-org/shared-flows"
        assert "org%3Amy-org" in captured["urls"][0]
        assert "topic%3Aam-rwx" in captured["urls"][0]

    @patch("repos.github_get")
    @patch("repos.user_tokens", {"alice": "tok"})
    def test_personal_user_blocked_from_unaffiliated_org(self, mock_get):
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        mock_get.side_effect = [
            _make_response(200, {"type": "Organization"}),
            _make_response(404, {"message": "Not Found"}),
        ]
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                get_rwx_repos("alice", Mock(), self.db, "secret-org")
            )
        assert exc.value.status_code == 403


# --------------------- POST /api/rwx-repos ---------------------

class TestCreateRwxRepoOrgSupport:
    def setup_method(self):
        _setup()
        self.db = next(_db())

    def teardown_method(self):
        self.db.close()
        _teardown()

    @patch("repos.github_get")
    @patch("repos.httpx.AsyncClient")
    @patch("repos.user_tokens", {"alice": "tok"})
    def test_personal_user_can_create_rwx_repo_under_org(self, mock_client_cls, mock_get):
        """A personal user who is an org member can create the RWX repo under the org."""
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        # _resolve_target_owner mock chain
        mock_get.side_effect = [
            _make_response(200, {"type": "Organization"}),
            _make_response(200, {"state": "active"}),
        ]

        post_calls = []
        put_calls = []
        async def _async_post(url, json=None, headers=None):
            post_calls.append((url, json))
            return _make_response(201, {
                "html_url": "https://github.com/my-org/shared-flows",
                "full_name": "my-org/shared-flows",
            })
        async def _async_put(url, json=None, headers=None):
            put_calls.append((url, json))
            return _make_response(200, {})
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=_async_post)
        mock_client.put = AsyncMock(side_effect=_async_put)
        mock_client_cls.return_value = mock_client

        request = Mock()
        request.json = AsyncMock(return_value={
            "user": "alice", "repo_name": "shared-flows", "owner": "my-org"
        })

        result = asyncio.run(
            create_rwx_repo(request, self.db)
        )
        # POST should hit the org-scoped repo create endpoint, not /user/repos.
        assert post_calls[0][0] == "https://api.github.com/orgs/my-org/repos"
        # Topic application should target the resulting full_name.
        assert "my-org/shared-flows" in put_calls[0][0]
        assert result.get("owner") == "my-org"
        assert result.get("full_name") == "my-org/shared-flows"

    @patch("repos.user_tokens", {"alice": "tok"})
    def test_personal_user_self_create_uses_user_endpoint(self):
        """When no owner override is provided, fall back to the user-level endpoint."""
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        with patch("repos.httpx.AsyncClient") as mock_client_cls:
            post_calls = []
            async def _async_post(url, json=None, headers=None):
                post_calls.append(url)
                return _make_response(201, {
                    "html_url": "https://github.com/alice/flows",
                    "full_name": "alice/flows",
                })
            async def _async_put(url, json=None, headers=None):
                return _make_response(200, {})
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=_async_post)
            mock_client.put = AsyncMock(side_effect=_async_put)
            mock_client_cls.return_value = mock_client

            request = Mock()
            request.json = AsyncMock(return_value={
                "user": "alice", "repo_name": "flows"
            })
            asyncio.run(
                create_rwx_repo(request, self.db)
            )
            assert post_calls[0] == "https://api.github.com/user/repos"

    @patch("repos.github_get")
    @patch("repos.user_tokens", {"alice": "tok"})
    def test_create_returns_403_when_not_member_of_target_org(self, mock_get):
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        mock_get.side_effect = [
            _make_response(200, {"type": "Organization"}),
            _make_response(404, {"message": "Not Found"}),
        ]
        request = Mock()
        request.json = AsyncMock(return_value={
            "user": "alice", "repo_name": "flows", "owner": "secret-org"
        })
        result = asyncio.run(
            create_rwx_repo(request, self.db)
        )
        # Endpoint catches HTTPException and returns a JSON error payload
        assert result.get("status") == 403
        assert "secret-org" in result.get("error", "")


# --------------------- POST /api/create-repo (am-reuseable-workflow) ---------------------

class TestCreateGithubRepoOrgSupport:
    def setup_method(self):
        _setup()
        self.db = next(_db())

    def teardown_method(self):
        self.db.close()
        _teardown()

    @patch("repos.github_get")
    @patch("repos.httpx.AsyncClient")
    @patch("repos.user_tokens", {"alice": "tok"})
    def test_create_am_reuseable_workflow_under_org(self, mock_client_cls, mock_get):
        account = Account(
            github_user="alice", github_email="alice@example.com",
            account_type="professional", github_account_type="User",
        )
        self.db.add(account); self.db.commit()

        mock_get.side_effect = [
            _make_response(200, {"type": "Organization"}),
            _make_response(200, {"state": "active"}),
        ]

        post_calls = []
        async def _async_post(url, json=None, headers=None):
            post_calls.append(url)
            return _make_response(201, {
                "html_url": "https://github.com/my-org/am-reuseable-workflow"
            })
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=_async_post)
        mock_client_cls.return_value = mock_client

        request = Mock()
        request.json = AsyncMock(return_value={"user": "alice", "owner": "my-org"})

        result = asyncio.run(
            create_github_repo(request, self.db)
        )
        assert post_calls[0] == "https://api.github.com/orgs/my-org/repos"
        assert result.get("owner") == "my-org"
        assert result.get("repo_name") == "am-reuseable-workflow"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
