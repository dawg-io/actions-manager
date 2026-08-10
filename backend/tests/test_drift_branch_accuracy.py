"""
Drift must be measured against the branches the project actually delivers to.

Delivery resolves branches through resolve_branch_config_for_repo ->
_resolve_branches_for_repo, honouring the project's branch pattern and any
per-repo override. Drift detection did not: it always read the repo's GitHub
*default* branch. A project delivering to release/* was therefore compared
against main and reported "synchronized" against a file it had never written
to — a silent false negative, which is worse than a missing feature because
the UI positively asserts the workflow is in sync.

Two supporting properties are tested here as well, because without them the
per-branch result is not trustworthy:

  * a failed branch lookup must be *unknown*, not a quiet fallback to "main";
  * resolving drift on one branch must not clear another branch's state.
"""

import os
import sys
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (  # noqa: E402
    Base, Account, Project, Repo, ProjectRepo, Workflow, ProjectWorkflow,
    WorkflowDriftState,
)
from workflows import (  # noqa: E402
    DriftCheckUnavailable, _process_regular_workflows, _prefetch_workflow_shas_per_repo,
)
from drift_notifications import clear_workflow_drift  # noqa: E402

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
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _project(db, *, branch_option="default", branch_regex="", code="P001"):
    account = Account(github_user="alice", github_email="a@example.com", account_type="free")
    db.add(account); db.commit(); db.refresh(account)
    project = Project(
        project_name="proj", project_code=code, user_id=account.user_id,
        use_prefix=False, branch_option=branch_option, branch_regex=branch_regex,
        branch_max_age_days=30,
    )
    db.add(project); db.commit(); db.refresh(project)
    return project


def _repo(db, project, name="acme/api"):
    repo = Repo(repo_name=name)
    db.add(repo); db.commit(); db.refresh(repo)
    db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
    db.commit()
    return repo


def _workflow(db, project, name="ci", git_hash="sha-local"):
    wf = Workflow(
        workflow_name=name, workflow_yaml="name: ci\non: push\n",
        workflow_git_hash=git_hash, reusable_workflow=False,
        workflow_status="synced_with_github",
    )
    db.add(wf); db.commit(); db.refresh(wf)
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
    db.commit()
    return wf


class TestDriftChecksTheProjectsTargetBranches:
    def test_pattern_project_is_not_checked_against_the_default_branch(self, db):
        """The headline bug.

        The project delivers to release/*. The default branch (main) is
        deliberately given *matching* content while the release branches
        differ — so a check that reads main reports "synchronized" and a
        correct check reports drift. Fetching the wrong branch is the only
        way to pass this by accident, which is exactly what it must catch.
        """
        project = _project(db, branch_option="pattern", branch_regex=r"^release/")
        _repo(db, project)
        _workflow(db, project)

        shas = {
            "main": {"ci.yml": "sha-local"},          # identical -> would look clean
            "release/2.0": {"ci.yml": "sha-remote"},  # differs   -> real drift
        }
        checked = []

        def fake_shas(owner, repo, branch, token, etag=None):
            checked.append(branch)
            return shas.get(branch, {}), None

        with patch("workflows.get_default_branch", return_value="main"), \
             patch("workflows._fetch_all_branches", return_value=["main", "release/2.0"]), \
             patch("workflows._filter_branches_by_recency", side_effect=lambda o, r, b, *a, **k: b), \
             patch("workflows.fetch_workflow_tree", side_effect=fake_shas), \
             patch("workflows.get_workflow_from_github",
                   return_value={"content": "name: ci\non: [push, pull_request]\n", "sha": "sha-remote"}):
            results = _process_regular_workflows(
                db, [_only_workflow(db, project)], ["acme/api"], "P001", "tok",
                use_prefix=False, project_id=project.project_id, project=project, user="alice",
            )

        assert "release/2.0" in checked, "drift never looked at the project's target branch"
        assert "main" not in checked, "drift read the default branch the project does not deliver to"
        assert [r.branch for r in results] == ["release/2.0"]
        assert results[0].has_drift is True

    def test_each_matched_branch_is_reported_separately(self, db):
        project = _project(db, branch_option="pattern", branch_regex=r"^release/")
        _repo(db, project)
        _workflow(db, project)

        shas = {
            "release/2.0": {"ci.yml": "sha-local"},   # in sync
            "release/2.1": {"ci.yml": "sha-remote"},  # drifted
        }

        with patch("workflows.get_default_branch", return_value="main"), \
             patch("workflows._fetch_all_branches", return_value=["release/2.0", "release/2.1"]), \
             patch("workflows._filter_branches_by_recency", side_effect=lambda o, r, b, *a, **k: b), \
             patch("workflows.fetch_workflow_tree", side_effect=lambda o, r, b, t, etag=None: (shas.get(b, {}), None)), \
             patch("workflows.get_workflow_from_github",
                   return_value={"content": "name: ci\non: [push, pull_request]\n", "sha": "sha-remote"}):
            results = _process_regular_workflows(
                db, [_only_workflow(db, project)], ["acme/api"], "P001", "tok",
                use_prefix=False, project_id=project.project_id, project=project, user="alice",
            )

        by_branch = {r.branch: r.has_drift for r in results}
        assert by_branch == {"release/2.0": False, "release/2.1": True}

    def test_default_option_still_checks_the_default_branch(self, db):
        """No behaviour change for the ordinary case."""
        project = _project(db, branch_option="default")
        _repo(db, project)
        _workflow(db, project)
        checked = []

        with patch("workflows.get_default_branch", return_value="trunk"), \
             patch("workflows.fetch_workflow_tree",
                   side_effect=lambda o, r, b, t, etag=None: (checked.append(b) or {"ci.yml": "sha-local"}, None)):
            _process_regular_workflows(
                db, [_only_workflow(db, project)], ["acme/api"], "P001", "tok",
                use_prefix=False, project_id=project.project_id, project=project, user="alice",
            )

        assert checked == ["trunk"]

    def test_every_status_carries_its_repo_and_branch(self, db):
        """Carried as data, not recovered by substring-matching the message."""
        project = _project(db)
        _repo(db, project)
        _workflow(db, project)

        with patch("workflows.get_default_branch", return_value="main"), \
             patch("workflows.fetch_workflow_tree", return_value=({"ci.yml": "sha-local"}, None)):
            results = _process_regular_workflows(
                db, [_only_workflow(db, project)], ["acme/api"], "P001", "tok",
                use_prefix=False, project_id=project.project_id, project=project, user="alice",
            )

        assert results[0].repo == "acme/api"
        assert results[0].branch == "main"


class TestUnresolvableBranchIsUnknown:
    def test_failed_branch_lookup_is_not_a_silent_main(self, db):
        """A revoked token must not become "we checked main and it's fine"."""
        with patch("workflows.get_default_branch",
                   side_effect=DriftCheckUnavailable("token revoked")):
            cache = _prefetch_workflow_shas_per_repo(["acme/api"], "tok")

        assert list(cache.values()) == [None]
        assert all(branch == "" for (_repo, branch) in cache)


class TestResolutionIsBranchScoped:
    def _drifted(self, db, project, wf, repo, branch):
        state = WorkflowDriftState(
            project_id=project.project_id, workflow_id=wf.workflow_id,
            repo_id=repo.repo_id, branch=branch, has_drift=True,
            content_hash="h", drift_cycle_count=1,
        )
        db.add(state); db.commit()
        return state

    def test_clearing_one_branch_leaves_the_other_drifted(self, db):
        """Otherwise fixing release/2.1 reports the workflow clean while
        release/2.2 is still wrong — the exact false-clean this PR removes."""
        project = _project(db)
        repo = _repo(db, project)
        wf = _workflow(db, project)
        self._drifted(db, project, wf, repo, "release/2.1")
        self._drifted(db, project, wf, repo, "release/2.2")

        cleared = clear_workflow_drift(db, project, wf.workflow_id, repo.repo_name, "release/2.1")

        assert cleared == 1
        remaining = {s.branch: s.has_drift for s in db.query(WorkflowDriftState).all()}
        assert remaining == {"release/2.1": False, "release/2.2": True}

    def test_clearing_without_a_branch_still_clears_the_whole_repo(self, db):
        """Deleting a workflow from a repo removes it from every branch."""
        project = _project(db)
        repo = _repo(db, project)
        wf = _workflow(db, project)
        self._drifted(db, project, wf, repo, "release/2.1")
        self._drifted(db, project, wf, repo, "release/2.2")

        cleared = clear_workflow_drift(db, project, wf.workflow_id, repo.repo_name)

        assert cleared == 2


def _only_workflow(db, project):
    return (
        db.query(Workflow)
        .join(ProjectWorkflow)
        .filter(ProjectWorkflow.project_id == project.project_id)
        .first()
    )
