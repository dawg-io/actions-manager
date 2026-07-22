"""
Regression tests for linked reusable workflow sync after PR Campaign merge.

Covers:
- Caller Workflow Project with prefix mode enabled
- Reusable Workflow Project with no prefix mode
- Linked reusable workflow edited from the caller project
- PR Campaign completed (all PRs merged)
- Reusable Workflow Project shows the workflow as synced_with_github after completion
- No false drift detected badge appears after the PR merge
- RWX project pr_state transitions to "synced"
"""
import sys
import os
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    Base,
    Account,
    Project,
    Workflow,
    ProjectWorkflow,
    LinkedReusableWorkflow,
    ProjectPullRequest,
    Repo,
    ProjectRepo,
)
from main import app
from projects import get_db as projects_get_db
from workflows import get_db as workflows_get_db

# ---------------------------------------------------------------------------
# Test DB setup (in-memory with StaticPool for isolation)
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

TEST_GITHUB_USER = "testuser"
TEST_STD_PROJECT = "caller-project"
TEST_RWX_PROJECT = "rwx-project"


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    yield
    app.dependency_overrides.pop(projects_get_db, None)
    app.dependency_overrides.pop(workflows_get_db, None)
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with mock.patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_account_and_projects(db):
    """Create an account, a standard project (with prefix), and an RWX project (no prefix)."""
    account = Account(github_user=TEST_GITHUB_USER, github_email="t@t.com", account_type="pro")
    db.add(account)
    db.flush()

    std_project = Project(
        project_name=TEST_STD_PROJECT,
        project_code="CALL1",
        user_id=account.user_id,
        project_type="standard",
        use_prefix=True,
        pr_state="open",
    )
    rwx_project = Project(
        project_name=TEST_RWX_PROJECT,
        project_code="RWX1",
        user_id=account.user_id,
        project_type="rwx",
        use_prefix=False,
        pr_state="new",
    )
    db.add_all([std_project, rwx_project])
    db.flush()
    return account, std_project, rwx_project


def _add_linked_workflow(db, std_project, rwx_project, *, status="under_review", name="deploy.yml"):
    """Create a reusable workflow in the RWX project and link it to the standard project."""
    wf = Workflow(
        workflow_name=name,
        workflow_yaml="on:\n  workflow_call:\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo deploy",
        reusable_workflow=True,
        workflow_status=status,
        workflow_git_hash="0" * 40,
    )
    db.add(wf)
    db.flush()

    pw = ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=wf.workflow_id)
    db.add(pw)

    link = LinkedReusableWorkflow(
        standard_project_id=std_project.project_id,
        rwx_project_id=rwx_project.project_id,
        workflow_id=wf.workflow_id,
    )
    db.add(link)
    db.flush()
    return wf


def _add_regular_workflow(db, project, *, status="under_review"):
    wf = Workflow(
        workflow_name="ci.yml",
        workflow_yaml="on: push\njobs:\n  test:\n    runs-on: ubuntu-latest",
        reusable_workflow=False,
        workflow_status=status,
    )
    db.add(wf)
    db.flush()
    pw = ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id)
    db.add(pw)
    db.flush()
    return wf


def _add_pr(db, project_id, *, repo_name="testuser/myrepo", pr_number=1, pr_state="open"):
    pr = ProjectPullRequest(
        project_id=project_id,
        repo_name=repo_name,
        pr_number=pr_number,
        pr_state=pr_state,
        pr_url=f"https://github.com/{repo_name}/pull/{pr_number}",
        branch_name="actions-manager/call1-main",
        target_branch="main",
    )
    db.add(pr)
    db.flush()
    return pr


# ---------------------------------------------------------------------------
# Tests: merge_pull_request endpoint
# ---------------------------------------------------------------------------

class TestMergePRSyncsLinkedWorkflows:
    """When a caller project merges its last PR, linked RWX workflows must sync."""

    def test_merge_syncs_linked_reusable_workflow(self, client):
        """After merging the last PR for a caller project, the linked reusable
        workflow should transition from 'under_review' to 'synced_with_github'."""
        db = TestingSessionLocal()
        account, std_project, rwx_project = _make_account_and_projects(db)
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")
        regular_wf = _add_regular_workflow(db, std_project, status="under_review")
        _add_pr(db, std_project.project_id, repo_name="testuser/myrepo", pr_number=10)
        db.commit()

        merge_response_mock = mock.Mock()
        merge_response_mock.status_code = 200
        merge_response_mock.json.return_value = {"sha": "abc123merged"}

        with mock.patch("workflows.user_tokens", {TEST_GITHUB_USER: "fake-token"}), \
             mock.patch("workflows.github_put", return_value=merge_response_mock), \
             mock.patch("workflows._delete_actions_manager_branch", return_value=(True, None)):
            resp = client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": TEST_GITHUB_USER,
                    "project_name": TEST_STD_PROJECT,
                    "repo_name": "testuser/myrepo",
                    "pr_number": 10,
                },
            )

        assert resp.status_code == 200, resp.text

        # Refresh from DB
        db.expire_all()
        updated_linked_wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).first()
        updated_regular_wf = db.query(Workflow).filter_by(workflow_id=regular_wf.workflow_id).first()
        updated_std_project = db.query(Project).filter_by(project_id=std_project.project_id).first()
        updated_rwx_project = db.query(Project).filter_by(project_id=rwx_project.project_id).first()

        # Linked reusable workflow should be synced
        assert updated_linked_wf.workflow_status == "synced_with_github"
        # Regular workflow should also be synced
        assert updated_regular_wf.workflow_status == "synced_with_github"
        # Caller project should be synced
        assert updated_std_project.pr_state == "synced"
        # RWX project should also transition to synced
        assert updated_rwx_project.pr_state == "synced"
        db.close()

    def test_merge_does_not_sync_if_prs_remain(self, client):
        """If the caller project still has open PRs, linked workflows stay under_review."""
        db = TestingSessionLocal()
        account, std_project, rwx_project = _make_account_and_projects(db)
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")
        _add_pr(db, std_project.project_id, repo_name="testuser/repo-a", pr_number=10)
        _add_pr(db, std_project.project_id, repo_name="testuser/repo-b", pr_number=11)
        db.commit()

        merge_response_mock = mock.Mock()
        merge_response_mock.status_code = 200
        merge_response_mock.json.return_value = {"sha": "abc123merged"}

        with mock.patch("workflows.user_tokens", {TEST_GITHUB_USER: "fake-token"}), \
             mock.patch("workflows.github_put", return_value=merge_response_mock), \
             mock.patch("workflows._delete_actions_manager_branch", return_value=(True, None)):
            resp = client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": TEST_GITHUB_USER,
                    "project_name": TEST_STD_PROJECT,
                    "repo_name": "testuser/repo-a",
                    "pr_number": 10,
                },
            )

        assert resp.status_code == 200

        db.expire_all()
        updated_linked_wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).first()
        updated_rwx_project = db.query(Project).filter_by(project_id=rwx_project.project_id).first()

        # Should still be under_review — second PR is not merged yet
        assert updated_linked_wf.workflow_status == "under_review"
        assert updated_rwx_project.pr_state == "new"
        db.close()

    def test_rwx_project_stays_open_if_own_workflows_under_review(self, client):
        """RWX project should not transition to synced if it has its own under_review workflows."""
        db = TestingSessionLocal()
        account, std_project, rwx_project = _make_account_and_projects(db)
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review", name="deploy.yml")

        # Add another workflow directly owned by the RWX project that is still under_review
        other_wf = Workflow(
            workflow_name="build.yml",
            workflow_yaml="on: push",
            reusable_workflow=True,
            workflow_status="under_review",
        )
        db.add(other_wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=other_wf.workflow_id))
        db.flush()

        _add_pr(db, std_project.project_id, repo_name="testuser/myrepo", pr_number=10)
        db.commit()

        merge_response_mock = mock.Mock()
        merge_response_mock.status_code = 200
        merge_response_mock.json.return_value = {"sha": "merged-sha"}

        with mock.patch("workflows.user_tokens", {TEST_GITHUB_USER: "fake-token"}), \
             mock.patch("workflows.github_put", return_value=merge_response_mock), \
             mock.patch("workflows._delete_actions_manager_branch", return_value=(True, None)):
            resp = client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": TEST_GITHUB_USER,
                    "project_name": TEST_STD_PROJECT,
                    "repo_name": "testuser/myrepo",
                    "pr_number": 10,
                },
            )

        assert resp.status_code == 200

        db.expire_all()
        updated_linked_wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).first()
        updated_rwx_project = db.query(Project).filter_by(project_id=rwx_project.project_id).first()

        # Linked workflow should be synced
        assert updated_linked_wf.workflow_status == "synced_with_github"
        # But RWX project should NOT be synced because build.yml is still under_review
        assert updated_rwx_project.pr_state != "synced"
        db.close()


# ---------------------------------------------------------------------------
# Tests: webhook merge path
# ---------------------------------------------------------------------------

class TestWebhookMergeSyncsLinkedWorkflows:
    """When a PR merge webhook fires for a caller project, linked RWX workflows must sync."""

    def test_webhook_merge_syncs_linked_workflow(self, client):
        """GitHub webhook for a merged PR should sync linked reusable workflows."""
        db = TestingSessionLocal()
        account, std_project, rwx_project = _make_account_and_projects(db)
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")
        _add_pr(db, std_project.project_id, repo_name="testuser/myrepo", pr_number=5, pr_state="open")
        db.commit()

        webhook_payload = {
            "action": "closed",
            "pull_request": {
                "number": 5,
                "merged": True,
            },
            "repository": {"full_name": "testuser/myrepo"},
        }

        with mock.patch("workflows._verify_pr_webhook_signature", return_value=True):
            resp = client.post(
                "/webhooks/github",
                json=webhook_payload,
                headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=fake"},
            )

        assert resp.status_code == 200, resp.text

        db.expire_all()
        updated_linked_wf = db.query(Workflow).filter_by(workflow_id=linked_wf.workflow_id).first()
        updated_rwx_project = db.query(Project).filter_by(project_id=rwx_project.project_id).first()

        assert updated_linked_wf.workflow_status == "synced_with_github"
        assert updated_rwx_project.pr_state == "synced"
        db.close()


# ---------------------------------------------------------------------------
# Tests: prefix handling for linked reusable workflows
# ---------------------------------------------------------------------------

class TestLinkedWorkflowPrefixHandling:
    """Linked reusable workflows must use the owning RWX project's prefix, not the caller's."""

    def test_build_reusable_workflow_results_uses_rwx_prefix(self, client):
        """When _build_reusable_workflow_results processes linked workflows from a
        standard project with use_prefix=True, it should use the RWX project's
        code and use_prefix instead of the caller project's."""
        import workflows as wf_module

        db = TestingSessionLocal()
        account, std_project, rwx_project = _make_account_and_projects(db)
        # Confirm: std has prefix=True, rwx has prefix=False
        assert std_project.use_prefix is True
        assert rwx_project.use_prefix is False

        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="committed_locally")

        # Add repo for the RWX project (needed by _get_reusable_workflow_repo)
        repo = Repo(repo_name="testuser/am-reuseable-workflow")
        db.add(repo)
        db.flush()
        db.add(ProjectRepo(project_id=rwx_project.project_id, repo_id=repo.repo_id))
        db.commit()

        # Mock the payload to select the linked workflow
        class FakePayload:
            selected_reusable_workflows = [linked_wf.workflow_name]
            github_user = TEST_GITHUB_USER
            branch_regex = ""

        headers = {"Authorization": "token fake"}

        # Capture the args passed to _process_reusable_workflows_update
        captured_calls = []
        original_fn = wf_module._process_reusable_workflows_update

        def mock_process_rx(**kwargs):
            captured_calls.append(kwargs)
            return {}

        with mock.patch.object(wf_module, "_process_reusable_workflows_update", side_effect=mock_process_rx):
            with mock.patch.object(wf_module, "validate_reusable_workflow_link") as mock_val:
                mock_val.return_value = mock.Mock(allowed=True)
                results, names = wf_module._build_reusable_workflow_results(
                    std_project, FakePayload(), headers, db, github_user=TEST_GITHUB_USER
                )

        assert len(captured_calls) == 1
        call_kwargs = captured_calls[0]
        # Should use RWX project's code, not the caller's
        assert call_kwargs["project_code"] == rwx_project.project_code, (
            f"Expected RWX project_code '{rwx_project.project_code}', "
            f"got '{call_kwargs['project_code']}'"
        )
        # Should use RWX project's use_prefix (False), not the caller's (True)
        assert call_kwargs["use_prefix"] is False, (
            f"Expected use_prefix=False (from RWX project), got {call_kwargs['use_prefix']}"
        )
        db.close()

    def test_update_workflow_endpoint_uses_rwx_prefix(self, client):
        """The /api/update-workflow endpoint must use the RWX project's prefix
        settings when pushing linked reusable workflows from a standard project."""
        import workflows as wf_module

        db = TestingSessionLocal()
        account, std_project, rwx_project = _make_account_and_projects(db)
        linked_wf = _add_linked_workflow(db, std_project, rwx_project, status="under_review")

        repo = Repo(repo_name="testuser/am-reuseable-workflow")
        db.add(repo)
        db.flush()
        db.add(ProjectRepo(project_id=rwx_project.project_id, repo_id=repo.repo_id))
        db.commit()

        captured_calls = []

        def mock_process_rx(*args, **kwargs):
            captured_calls.append({"args": args, "kwargs": kwargs})
            return {"testuser/am-reuseable-workflow on main": {"status": "pr_updated", "pr_url": "http://x", "pr_number": 1}}

        with mock.patch("workflows.user_tokens", {TEST_GITHUB_USER: "fake-token"}), \
             mock.patch.object(wf_module, "_process_reusable_workflows_update", side_effect=mock_process_rx), \
             mock.patch.object(wf_module, "validate_reusable_workflow_link", return_value=mock.Mock(allowed=True)):
            resp = client.post(
                "/api/update-workflow",
                json={
                    "user": TEST_GITHUB_USER,
                    "repo_names": [],
                    "workflows": [],
                    "rxworkflows": [{"name": linked_wf.workflow_name, "content": linked_wf.workflow_yaml}],
                    "regex_pattern": "",
                    "branch_option": "default",
                    "project_name": TEST_STD_PROJECT,
                },
            )

        assert resp.status_code == 200, resp.text
        assert len(captured_calls) == 1
        call_args = captured_calls[0]["args"]
        call_kwargs = captured_calls[0]["kwargs"]
        # Positional args: rxworkflows, user, project_code, regex_pattern, branch_max_age_days, headers, db
        # project_code is the 3rd positional arg (index 2)
        assert call_args[2] == rwx_project.project_code.upper(), (
            f"Expected RWX project_code '{rwx_project.project_code.upper()}', "
            f"got '{call_args[2]}'"
        )
        # use_prefix is passed as a keyword arg and should be False (from RWX project)
        assert call_kwargs.get("use_prefix") is False, (
            f"Expected use_prefix=False (from RWX project), got {call_kwargs.get('use_prefix')}"
        )
        db.close()
