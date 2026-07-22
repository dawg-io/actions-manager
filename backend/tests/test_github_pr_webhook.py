"""
Tests for the GitHub pull_request webhook endpoint.

Verifies that when a PR is closed or merged directly on GitHub,
the corresponding workflow statuses and project state are updated correctly.

Scenarios:
- PR merged on GitHub → workflows → synced_with_github, project state → synced
- PR closed (not merged) on GitHub → workflows → committed_locally, project state → draft
- Non-tracked PR is ignored
- Invalid signatures are rejected (when secret is configured)
- Non-pull_request event types are ignored
- Non-closed actions (e.g. opened) are ignored
- Remaining open PRs prevent premature status promotion/demotion
"""
import hashlib
import hmac
import json
import sys
import os
from unittest.mock import patch, MagicMock

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
    ProjectPullRequest,
)
from main import app
from workflows import get_db, _verify_pr_webhook_signature as _real_verify_pr_webhook_signature

# ---------------------------------------------------------------------------
# In-memory test database
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def override_workflows_db():
    previous_override = app.dependency_overrides.get(get_db)
    previous_factory = app.state.middleware_db_factory
    app.dependency_overrides[get_db] = override_get_db
    app.state.middleware_db_factory = TestingSessionLocal
    try:
        yield
    finally:
        app.state.middleware_db_factory = previous_factory
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fixtures(db, *, pr_state: str = "open", project_pr_state: str = "open"):
    account = Account(
        github_user="webhookuser",
        github_email="webhook@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_name="webhook_project",
        project_code="WHP",
        user_id=account.user_id,
        branch_option="default",
        reusable_workflows_enabled=False,
        pr_state=project_pr_state,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    wf = Workflow(
        workflow_name="ci.yml",
        workflow_yaml="name: CI\non: push",
        reusable_workflow=False,
        workflow_git_hash="0" * 40,
        workflow_status="under_review",
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
    db.commit()

    pr = ProjectPullRequest(
        project_id=project.project_id,
        repo_name="webhookuser/test-repo",
        pr_number=99,
        pr_url="https://github.com/webhookuser/test-repo/pull/99",
        pr_state=pr_state,
        branch_name="actions-manager/whp-main",
        target_branch="main",
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)

    return account, project, wf, pr


def _make_payload(action: str, merged: bool, pr_number: int = 99,
                  repo_full_name: str = "webhookuser/test-repo") -> bytes:
    payload = {
        "action": action,
        "pull_request": {"number": pr_number, "merged": merged},
        "repository": {"full_name": repo_full_name},
    }
    return json.dumps(payload).encode("utf-8")


def _sign(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGitHubPRWebhook:

    @pytest.fixture(autouse=True)
    def setup_db(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        # Bypass HMAC check — these tests exercise business logic, not signature verification
        with patch("workflows._verify_pr_webhook_signature", return_value=True):
            yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    # ------------------------------------------------------------------
    # Merge path
    # ------------------------------------------------------------------

    def test_merged_pr_updates_workflows_to_synced(self):
        """Merged PR should set non-reusable workflows to synced_with_github."""
        _, project, wf, _ = _make_fixtures(self.db)

        body = _make_payload("closed", merged=True)
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["action"] == "merged"

        self.db.refresh(wf)
        assert wf.workflow_status == "synced_with_github"

    def test_merged_pr_updates_project_state_to_synced(self):
        """Merged PR should transition project state to 'synced'."""
        _, project, _, _ = _make_fixtures(self.db)

        body = _make_payload("closed", merged=True)
        client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )

        self.db.refresh(project)
        assert project.pr_state == "synced"

    def test_merged_pr_does_not_sync_when_other_prs_remain(self):
        """If other open PRs still exist, don't promote to synced yet."""
        _, project, wf, _ = _make_fixtures(self.db)

        # Add a second open PR for the same project
        pr2 = ProjectPullRequest(
            project_id=project.project_id,
            repo_name="webhookuser/other-repo",
            pr_number=100,
            pr_url="https://github.com/webhookuser/other-repo/pull/100",
            pr_state="open",
            branch_name="actions-manager/whp-main",
            target_branch="main",
        )
        self.db.add(pr2)
        self.db.commit()

        body = _make_payload("closed", merged=True)
        client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )

        self.db.refresh(wf)
        # The workflow for the merged PR's project should still be under_review
        # because a sibling PR is still open
        assert wf.workflow_status == "under_review"

        self.db.refresh(project)
        assert project.pr_state != "synced"

    def test_merged_pr_does_not_sync_when_sibling_pr_is_closed_not_merged(self):
        """
        If a sibling PR was closed without merging, merging the remaining PR should
        NOT transition the project to 'synced' — not all PRs ended as merged.
        """
        _, project, wf, _ = _make_fixtures(self.db)

        # Add a sibling PR that has already been closed without merging
        pr2 = ProjectPullRequest(
            project_id=project.project_id,
            repo_name="webhookuser/other-repo",
            pr_number=102,
            pr_url="https://github.com/webhookuser/other-repo/pull/102",
            pr_state="closed",  # already closed, not merged
            branch_name="actions-manager/whp2-main",
            target_branch="main",
        )
        self.db.add(pr2)
        self.db.commit()

        # Now close the original PR as merged
        body = _make_payload("closed", merged=True)
        client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )

        # Because a sibling PR was closed (not merged), project should NOT be "synced"
        self.db.refresh(project)
        assert project.pr_state != "synced"

    # ------------------------------------------------------------------
    # Close (no merge) path
    # ------------------------------------------------------------------

    def test_closed_pr_reverts_workflows_to_committed_locally(self):
        """Closed-without-merge PR should revert under_review workflows to committed_locally."""
        _, project, wf, _ = _make_fixtures(self.db)

        body = _make_payload("closed", merged=False)
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["action"] == "closed"

        self.db.refresh(wf)
        assert wf.workflow_status == "committed_locally"

    def test_closed_pr_updates_project_state_to_draft(self):
        """Closed-without-merge PR should transition project state to 'draft'."""
        _, project, _, _ = _make_fixtures(self.db)

        body = _make_payload("closed", merged=False)
        client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )

        self.db.refresh(project)
        assert project.pr_state == "draft"

    def test_closed_pr_does_not_revert_when_other_prs_remain(self):
        """If other open PRs remain, workflows should stay under_review."""
        _, project, wf, _ = _make_fixtures(self.db)

        pr2 = ProjectPullRequest(
            project_id=project.project_id,
            repo_name="webhookuser/other-repo",
            pr_number=101,
            pr_url="https://github.com/webhookuser/other-repo/pull/101",
            pr_state="open",
            branch_name="actions-manager/whp-main",
            target_branch="main",
        )
        self.db.add(pr2)
        self.db.commit()

        body = _make_payload("closed", merged=False)
        client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )

        self.db.refresh(wf)
        assert wf.workflow_status == "under_review"

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_unknown_pr_is_ignored(self):
        """PRs not in the database should be silently ignored."""
        body = _make_payload("closed", merged=False, pr_number=9999,
                             repo_full_name="someone/unknown-repo")
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_non_pull_request_event_is_ignored(self):
        """Events other than pull_request should be ignored."""
        body = json.dumps({"action": "completed"}).encode("utf-8")
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "check_run", "Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_non_closed_action_is_ignored(self):
        """pull_request events with action other than 'closed' should be ignored."""
        body = _make_payload("opened", merged=False)
        response = client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_invalid_signature_rejected_when_secret_configured(self):
        """Requests with wrong signature should be rejected with 401."""
        body = _make_payload("closed", merged=False)
        # Override the autouse mock so the real HMAC check runs for this test.
        # _real_verify_pr_webhook_signature is captured at import time, before any patch.
        with patch("workflows.GITHUB_PR_WEBHOOK_SECRET", "mysecret"), \
             patch("workflows._verify_pr_webhook_signature", side_effect=_real_verify_pr_webhook_signature):
            response = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": "sha256=invalidsignature",
                    "Content-Type": "application/json",
                },
            )
        assert response.status_code == 401


# ===========================================================================
# Tests: get_project_pr_status with refresh_from_github=True (page-load sync)
# ===========================================================================

class TestPageLoadPRSync:
    """
    Tests for the page-load synchronisation path in GET /api/project-pr-status.
    When refresh_from_github=true and all open PRs are now resolved on GitHub,
    the endpoint should apply the same workflow/project state transitions that
    the webhook or explicit merge/close actions would apply.
    """

    @pytest.fixture(autouse=True)
    def setup_db(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def _make_fixtures_with_token(self, pr_state: str = "open",
                                  workflow_status: str = "under_review",
                                  project_pr_state: str = "open"):
        """Create fixtures and register a fake token."""
        from auth import user_tokens
        user_tokens["syncuser"] = "fake_token"

        account = Account(
            github_user="syncuser",
            github_email="sync@example.com",
            account_type="free",
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)

        project = Project(
            project_name="sync_project",
            project_code="SYN",
            user_id=account.user_id,
            branch_option="default",
            reusable_workflows_enabled=False,
            pr_state=project_pr_state,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        wf = Workflow(
            workflow_name="ci.yml",
            workflow_yaml="name: CI\non: push",
            reusable_workflow=False,
            workflow_git_hash="0" * 40,
            workflow_status=workflow_status,
        )
        self.db.add(wf)
        self.db.commit()
        self.db.refresh(wf)
        self.db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
        self.db.commit()

        pr = ProjectPullRequest(
            project_id=project.project_id,
            repo_name="syncuser/test-repo",
            pr_number=77,
            pr_url="https://github.com/syncuser/test-repo/pull/77",
            pr_state=pr_state,
            branch_name="actions-manager/syn-main",
            target_branch="main",
        )
        self.db.add(pr)
        self.db.commit()

        return account, project, wf, pr

    def test_page_load_refresh_syncs_merged_pr(self):
        """
        When refresh_from_github=true and GitHub reports the PR as merged,
        workflow status should become synced_with_github and project state synced.
        """
        _, project, wf, _ = self._make_fixtures_with_token()

        # Simulate GitHub returning the PR as merged
        mock_gh_response = MagicMock()
        mock_gh_response.status_code = 200
        mock_gh_response.json.return_value = {"state": "closed", "merged": True}

        with patch("workflows.github_get", return_value=mock_gh_response):
            response = client.get(
                "/api/project-pr-status",
                params={
                    "github_user": "syncuser",
                    "project_name": "sync_project",
                    "refresh_from_github": "true",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["project_state"] == "synced"
        assert data["merged_prs"] == 1
        assert data["open_prs"] == 0

        self.db.refresh(wf)
        assert wf.workflow_status == "synced_with_github"
        self.db.refresh(project)
        assert project.pr_state == "synced"

    def test_page_load_refresh_syncs_closed_pr(self):
        """
        When refresh_from_github=true and GitHub reports the PR as closed (not merged),
        workflow status should revert to committed_locally and project state to draft.
        """
        _, project, wf, _ = self._make_fixtures_with_token()

        # Simulate GitHub returning the PR as closed without merge
        mock_gh_response = MagicMock()
        mock_gh_response.status_code = 200
        mock_gh_response.json.return_value = {"state": "closed", "merged": False}

        with patch("workflows.github_get", return_value=mock_gh_response):
            response = client.get(
                "/api/project-pr-status",
                params={
                    "github_user": "syncuser",
                    "project_name": "sync_project",
                    "refresh_from_github": "true",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["project_state"] == "draft"
        assert data["closed_prs"] == 1
        assert data["open_prs"] == 0

        self.db.refresh(wf)
        assert wf.workflow_status == "committed_locally"
        self.db.refresh(project)
        assert project.pr_state == "draft"

    def test_page_load_no_refresh_uses_cached_state(self):
        """
        Without refresh_from_github, the endpoint should return cached state
        and not trigger any workflow status changes.
        """
        _, project, wf, _ = self._make_fixtures_with_token()

        # No GitHub API call should be made
        with patch("workflows.github_get") as mock_gh:
            response = client.get(
                "/api/project-pr-status",
                params={
                    "github_user": "syncuser",
                    "project_name": "sync_project",
                    "refresh_from_github": "false",
                },
            )
            mock_gh.assert_not_called()

        assert response.status_code == 200
        data = response.json()
        assert data["open_prs"] == 1  # Cached "open" state unchanged

        self.db.refresh(wf)
        assert wf.workflow_status == "under_review"  # Unchanged

    def test_page_load_does_not_sync_when_pr_still_open(self):
        """
        If GitHub still shows the PR as open, no workflow/project state
        transitions should occur.
        """
        _, project, wf, _ = self._make_fixtures_with_token()

        mock_gh_response = MagicMock()
        mock_gh_response.status_code = 200
        mock_gh_response.json.return_value = {"state": "open", "merged": False}

        with patch("workflows.github_get", return_value=mock_gh_response):
            response = client.get(
                "/api/project-pr-status",
                params={
                    "github_user": "syncuser",
                    "project_name": "sync_project",
                    "refresh_from_github": "true",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["open_prs"] == 1

        self.db.refresh(wf)
        assert wf.workflow_status == "under_review"  # No change
        self.db.refresh(project)
        assert project.pr_state == "open"  # No change


    def test_valid_signature_accepted(self):
        """Requests with correct HMAC signature should be accepted."""
        _make_fixtures(self.db)
        secret = "testsecret"
        body = _make_payload("closed", merged=False)
        sig = _sign(body, secret)

        with patch("workflows.GITHUB_PR_WEBHOOK_SECRET", secret):
            response = client.post(
                "/webhooks/github",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
        assert response.status_code == 200
        assert response.json()["status"] == "processed"

    def test_active_pr_status_excludes_merged_and_closed_prs(self):
        """
        Regression: GET /api/project-pr-status powers the "Pull Requests Open"
        banner and the right-side active PR panel. The `pull_requests` array
        in the response must only include genuinely open PRs, even though
        the count summary (open/merged/closed) reflects all states.

        Merged and closed PRs belong to the separate "PR History" view served
        by /api/project-pr-history, and must never appear in the active panel
        — otherwise users see resolved PRs as if they still required action.
        """
        from auth import user_tokens
        user_tokens["syncuser"] = "fake_token"

        account = Account(
            github_user="syncuser",
            github_email="sync@example.com",
            account_type="free",
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)

        project = Project(
            project_name="sync_project",
            project_code="SYN",
            user_id=account.user_id,
            branch_option="default",
            reusable_workflows_enabled=False,
            pr_state="open",
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        # Mix of open / merged / closed PRs in the same project.
        for pr_number, state in [(101, "open"), (102, "merged"), (103, "closed")]:
            self.db.add(ProjectPullRequest(
                project_id=project.project_id,
                repo_name="syncuser/test-repo",
                pr_number=pr_number,
                pr_url=f"https://github.com/syncuser/test-repo/pull/{pr_number}",
                pr_state=state,
                branch_name=f"actions-manager/syn-{pr_number}-main",
                target_branch="main",
            ))
        self.db.commit()

        response = client.get(
            "/api/project-pr-status",
            params={
                "github_user": "syncuser",
                "project_name": "sync_project",
                "refresh_from_github": "false",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Counts still reflect the full picture so the summary stays accurate.
        assert data["total_prs"] == 3
        assert data["open_prs"] == 1
        assert data["merged_prs"] == 1
        assert data["closed_prs"] == 1

        # But the active panel list contains *only* open PRs.
        assert len(data["pull_requests"]) == 1
        assert data["pull_requests"][0]["pr_number"] == 101
        assert data["pull_requests"][0]["pr_state"] == "open"
        states = {p["pr_state"] for p in data["pull_requests"]}
        assert "merged" not in states
        assert "closed" not in states

    def test_active_pr_status_empty_when_all_prs_merged(self):
        """
        After every PR has been merged the active panel must surface an
        empty list so the "Pull Requests Open" banner / count UI no longer
        treat the project as having work-in-progress PRs. The historical
        merged PR remains accessible via /api/project-pr-history.
        """
        from auth import user_tokens
        user_tokens["syncuser"] = "fake_token"

        account = Account(
            github_user="syncuser",
            github_email="sync@example.com",
            account_type="free",
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)

        project = Project(
            project_name="sync_project",
            project_code="SYN",
            user_id=account.user_id,
            branch_option="default",
            reusable_workflows_enabled=False,
            pr_state="synced",
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        self.db.add(ProjectPullRequest(
            project_id=project.project_id,
            repo_name="syncuser/test-repo",
            pr_number=201,
            pr_url="https://github.com/syncuser/test-repo/pull/201",
            pr_state="merged",
            branch_name="actions-manager/syn-201-main",
            target_branch="main",
        ))
        self.db.commit()

        response = client.get(
            "/api/project-pr-status",
            params={
                "github_user": "syncuser",
                "project_name": "sync_project",
                "refresh_from_github": "false",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_prs"] == 1
        assert data["merged_prs"] == 1
        assert data["open_prs"] == 0
        assert data["pull_requests"] == []

    def test_page_load_refresh_syncs_workflow_with_null_reusable_workflow(self):
        """
        When a workflow has reusable_workflow=NULL (older DB record), it should
        still be updated by _update_project_workflows_status(non_reusable_only=True).
        The isnot(True) filter matches both False and NULL.
        """
        from auth import user_tokens
        user_tokens["syncuser"] = "fake_token"

        account = Account(
            github_user="syncuser",
            github_email="sync@example.com",
            account_type="free",
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)

        project = Project(
            project_name="sync_project",
            project_code="SYN",
            user_id=account.user_id,
            branch_option="default",
            reusable_workflows_enabled=False,
            pr_state="open",
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)

        # Explicitly set reusable_workflow to NULL to simulate old DB records
        wf = Workflow(
            workflow_name="ci.yml",
            workflow_yaml="name: CI\non: push",
            workflow_git_hash="0" * 40,
            workflow_status="under_review",
        )
        wf.reusable_workflow = None  # Explicitly NULL
        self.db.add(wf)
        self.db.commit()
        self.db.refresh(wf)
        self.db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
        self.db.commit()

        pr = ProjectPullRequest(
            project_id=project.project_id,
            repo_name="syncuser/test-repo",
            pr_number=88,
            pr_url="https://github.com/syncuser/test-repo/pull/88",
            pr_state="open",
            branch_name="actions-manager/syn-main",
            target_branch="main",
        )
        self.db.add(pr)
        self.db.commit()

        mock_gh_response = MagicMock()
        mock_gh_response.status_code = 200
        mock_gh_response.json.return_value = {"state": "closed", "merged": True}

        with patch("workflows.github_get", return_value=mock_gh_response):
            response = client.get(
                "/api/project-pr-status",
                params={
                    "github_user": "syncuser",
                    "project_name": "sync_project",
                    "refresh_from_github": "true",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["project_state"] == "synced"

        # The workflow with reusable_workflow=NULL must be updated
        self.db.refresh(wf)
        assert wf.workflow_status == "synced_with_github", (
            f"Expected 'synced_with_github', got '{wf.workflow_status}'. "
            "NULL reusable_workflow should be treated as non-reusable."
        )
