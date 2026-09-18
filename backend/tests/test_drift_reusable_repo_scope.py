"""A reusable workflow that was never delivered must not read as a failed check.

Two ways the drift check turned "nothing has been delivered yet" into
check_failed, which the UI renders as "Needs Attention" plus "Couldn't check N
workflows - GitHub didn't respond":

  * ``_get_reusable_workflow_repo`` falls back to ``{user}/am-reuseable-workflow``
    when a project has neither an RWX repository of its own nor a link. A
    caller (standard) project that owns a reusable workflow always lands there,
    the repository need not exist, and the 404 was reported as an outage.
  * ``_ensure_reusable_repo_exists`` creates that repository with
    ``auto_init=False``, so until the first commit lands GitHub answers the
    Trees API with 409 "Git Repository is empty" - also reported as an outage.

Both now resolve to "not delivered". What must NOT change is detection for a
reusable workflow that *has* been delivered: a caller project can deliver one
(``_build_reusable_workflow_results`` includes rows it owns, not only linked
ones), so silencing those would trade a visible false alarm for a silent miss.
"""

import base64
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (  # noqa: E402
    Base, Account, Project, Repo, Workflow, ProjectRepo, ProjectWorkflow,
)
import workflows as wf_module  # noqa: E402
from workflows import (  # noqa: E402
    DriftCheckUnavailable,
    detect_workflow_drift,
    get_all_workflow_shas,
)

USER = "octocat"
FALLBACK_REPO = f"{USER}/am-reuseable-workflow"
LOCAL_YAML = "name: Shared\non:\n  workflow_call:\n"
EDITED_ON_GITHUB = b"name: Shared\non:\n  workflow_call:\n    inputs:\n      added: {}\n"


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _project(db, *, project_type, repo_name):
    account = Account(github_user=USER, github_email="o@e.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_code="ABCD",
        project_name="Demo",
        user_id=account.user_id,
        project_type=project_type,
        use_prefix=True,
        reusable_workflows_enabled=True,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    repo = Repo(repo_name=repo_name)
    db.add(repo)
    db.commit()
    db.refresh(repo)
    db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
    db.commit()
    return project


def _add_workflow(db, project, *, name, reusable, git_hash, status):
    workflow = Workflow(
        workflow_name=name,
        workflow_yaml=LOCAL_YAML if reusable else "name: CI\non: push\n",
        workflow_git_hash=git_hash,
        reusable_workflow=reusable,
        workflow_status=status,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=workflow.workflow_id))
    db.commit()
    return workflow


def _never_delivered_reusable(db, project):
    return _add_workflow(db, project, name="shared-workflow", reusable=True,
                         git_hash=None, status="new")


def _delivered_reusable(db, project):
    return _add_workflow(db, project, name="shared-workflow", reusable=True,
                         git_hash="aaaa1111", status="synced_with_github")


def _regular_workflow(db, project):
    return _add_workflow(db, project, name="ci", reusable=False,
                         git_hash="realsha1", status="synced_with_github")


def _github(*, reusable_repo_status=200, tree_status=200, reusable_tree=None,
            contents=None, calls=None):
    """Mock GitHub. The project's own repo always resolves and lists cleanly."""
    def _get(url, headers=None, timeout=None, **kwargs):
        if calls is not None:
            calls.append(url)
        response = MagicMock()
        response.headers = {}
        if "/git/trees/" in url:
            if FALLBACK_REPO in url or "shared" in url:
                response.status_code = tree_status
                response.json.return_value = {"tree": reusable_tree or []}
            else:
                response.status_code = 200
                response.json.return_value = {
                    "tree": [{"path": "AM_ABCD_ci.yml", "type": "blob", "sha": "realsha1"}]
                }
        elif "/contents/" in url:
            response.status_code = 200 if contents else 404
            response.json.return_value = contents or {}
        elif FALLBACK_REPO in url or "/shared" in url:
            response.status_code = reusable_repo_status
            response.json.return_value = (
                {"default_branch": "main"} if reusable_repo_status == 200
                else {"message": "Not Found"}
            )
        else:
            response.status_code = 200
            response.json.return_value = {"default_branch": "main"}
        return response
    return _get


def _run_drift(db, project, repo_names, github):
    wf_module.user_tokens[USER] = "token"
    try:
        with patch("workflows.requests.get", side_effect=github), \
             patch("workflows.github_get",
                   side_effect=lambda url, user, session, headers=None, **kw: github(url, headers)):
            return detect_workflow_drift(db, USER, project.project_name, repo_names)
    finally:
        wf_module.user_tokens.pop(USER, None)


class TestMissingReusableRepository:
    def test_never_delivered_workflow_is_not_a_failed_check(self, db_session):
        # The caller-owned case from the report: the fallback repo does not
        # exist, and the workflow has never been written to GitHub.
        project = _project(db_session, project_type="standard", repo_name="acme/app")
        _regular_workflow(db_session, project)
        _never_delivered_reusable(db_session, project)

        results = _run_drift(db_session, project, ["acme/app"],
                             _github(reusable_repo_status=404))

        assert [d for d in results if d.check_failed] == []
        assert [d for d in results if d.drift_type == "reusable_workflow"] == []
        # The regular workflow was still checked, so this is not a silent no-op.
        assert [d for d in results if d.drift_type == "workflow"]

    def test_a_delivered_workflow_still_reports_unchecked(self, db_session):
        # A real blob SHA means it was written to GitHub. 404 cannot tell a
        # deleted repository from a token that lost sight of a private one, so
        # this must stay visible rather than be called clean or deleted.
        project = _project(db_session, project_type="standard", repo_name="acme/app")
        _delivered_reusable(db_session, project)

        results = _run_drift(db_session, project, ["acme/app"],
                             _github(reusable_repo_status=404))

        reusable = [d for d in results if d.drift_type == "reusable_workflow"]
        assert len(reusable) == 1
        assert reusable[0].check_failed is True
        assert reusable[0].deleted_in_github is False

    @pytest.mark.parametrize("status_code", [401, 403, 429, 500, 503])
    def test_other_failures_are_still_unchecked(self, db_session, status_code):
        # Only 404 means "no such repository". Everything else is an outage and
        # must not be downgraded to "never delivered".
        project = _project(db_session, project_type="standard", repo_name="acme/app")
        _never_delivered_reusable(db_session, project)

        results = _run_drift(db_session, project, ["acme/app"],
                             _github(reusable_repo_status=status_code))

        reusable = [d for d in results if d.drift_type == "reusable_workflow"]
        assert len(reusable) == 1
        assert reusable[0].check_failed is True


class TestDeliveredDriftIsStillDetected:
    def test_a_caller_owned_reusable_workflow_edited_on_github_is_reported(self, db_session):
        # A standard project can deliver a reusable workflow it owns, so drift
        # on one must still surface. This is the case an ownership-based skip
        # would have turned into a silent "No drift detected".
        project = _project(db_session, project_type="standard", repo_name="acme/app")
        _delivered_reusable(db_session, project)

        results = _run_drift(db_session, project, ["acme/app"], _github(
            reusable_tree=[{"path": "AM_ABCD_shared-workflow.yml",
                            "type": "blob", "sha": "bbbb2222"}],
            contents={"content": base64.b64encode(EDITED_ON_GITHUB).decode(),
                      "sha": "bbbb2222"},
        ))

        reusable = [d for d in results if d.drift_type == "reusable_workflow"]
        assert len(reusable) == 1
        assert reusable[0].has_drift is True
        assert reusable[0].check_failed is False

    def test_an_rwx_project_repository_is_still_listed(self, db_session):
        project = _project(db_session, project_type="rwx", repo_name="acme/shared")
        _delivered_reusable(db_session, project)
        calls = []

        results = _run_drift(db_session, project, ["acme/shared"], _github(
            reusable_tree=[{"path": "AM_ABCD_shared-workflow.yml",
                            "type": "blob", "sha": "aaaa1111"}],
            calls=calls,
        ))

        assert [url for url in calls if "acme/shared" in url], "the repo must be contacted"
        reusable = [d for d in results if d.drift_type == "reusable_workflow"]
        assert len(reusable) == 1
        assert reusable[0].has_drift is False
        assert reusable[0].check_failed is False


class TestEmptyRepositoryIsNotAnOutage:
    def test_trees_api_409_means_no_workflow_files(self):
        # GitHub answers 409 "Git Repository is empty." for a repo with zero
        # commits. That is an answer, not a failure to reach GitHub.
        with patch("workflows.requests.get") as get:
            get.return_value = MagicMock(status_code=409, headers={})
            assert get_all_workflow_shas("acme", "shared", "main", "token") == {}

    def test_an_empty_reusable_repository_is_not_reported_as_unchecked(self, db_session):
        project = _project(db_session, project_type="rwx", repo_name="acme/shared")
        _never_delivered_reusable(db_session, project)

        results = _run_drift(db_session, project, ["acme/shared"],
                             _github(tree_status=409))

        assert [d for d in results if d.check_failed] == []


class TestUnavailableCarriesItsStatus:
    @pytest.mark.parametrize("status_code", [401, 403, 429, 500])
    def test_the_status_code_is_a_field_not_only_prose(self, status_code):
        # The reusable path branches on this, so it must not have to parse the
        # message to find it.
        with patch("workflows.requests.get") as get:
            get.return_value = MagicMock(status_code=status_code, headers={})
            with pytest.raises(DriftCheckUnavailable) as raised:
                get_all_workflow_shas("acme", "shared", "main", "token")
        assert raised.value.status_code == status_code
