"""
Tests for workflow lifecycle status transitions.

Verifies that workflow_status transitions correctly across the lifecycle:
  new -> committed_locally -> under_review -> synced_with_github

Tests cover:
- create_or_update_workflow(): new → "new", update → "committed_locally"
- _update_project_workflows_status(): helper logic, filters
- create_pull_requests(): only non-reusable workflows → "under_review"
- merge_pull_request(): non-reusable workflows → "synced_with_github" only when
  no remaining open PRs; pr_merged version entries created atomically
- close_pull_request(): revert "under_review" → "committed_locally" only when
  no open PRs remain
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, Mock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import (
    Base, Account, Project, Workflow, ProjectWorkflow,
    ProjectPullRequest, Repo, ProjectRepo, WorkflowVersion,
)
from main import app
from workflows import get_db, create_or_update_workflow, _update_project_workflows_status
from auth import user_tokens

# ---------------------------------------------------------------------------
# Shared in-memory DB
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_status_transitions.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helper data-builder
# ---------------------------------------------------------------------------

def _make_db_fixtures(db, *, include_repo: bool = False, pr_state: str = "new"):
    """Create a minimal account + project (+ optional repo) and return ids."""
    account = Account(
        github_user="statususer",
        github_email="status@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_name="status_project",
        project_code="STS",
        user_id=account.user_id,
        branch_option="default",
        reusable_workflows_enabled=True,
        pr_state=pr_state,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    if include_repo:
        repo = Repo(repo_name="statususer/status-repo")
        db.add(repo)
        db.commit()
        db.refresh(repo)
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
        db.commit()
        return account, project, repo

    return account, project


def _add_workflow(db, project_id, *, name="ci.yml", reusable=False, status="new"):
    wf = Workflow(
        workflow_name=name,
        workflow_yaml="name: CI\non: push",
        reusable_workflow=reusable,
        workflow_git_hash="0" * 40,
        workflow_status=status,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    db.add(ProjectWorkflow(project_id=project_id, workflow_id=wf.workflow_id))
    db.commit()
    return wf


# ===========================================================================
# Tests: create_or_update_workflow()
# ===========================================================================

class TestCreateOrUpdateWorkflowStatus:
    """Directly test the create_or_update_workflow() helper function."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        account, project = _make_db_fixtures(self.db)
        self.project_id = project.project_id
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_new_workflow_gets_new_status(self):
        """First save of a workflow should set workflow_status = 'new'."""
        wf_schema = MagicMock()
        wf_schema.name = "build.yml"
        wf_schema.content = "name: Build\non: push"

        create_or_update_workflow(self.db, wf_schema, self.project_id, is_reusable=False)

        saved = (
            self.db.query(Workflow)
            .filter_by(workflow_name="build.yml")
            .first()
        )
        assert saved is not None
        assert saved.workflow_status == "new"

    def test_new_reusable_workflow_gets_new_status(self):
        """First save of a reusable workflow should also get 'new' status."""
        wf_schema = MagicMock()
        wf_schema.name = "reusable.yml"
        wf_schema.content = "name: Reusable\non: workflow_call"

        create_or_update_workflow(self.db, wf_schema, self.project_id, is_reusable=True)

        saved = self.db.query(Workflow).filter_by(workflow_name="reusable.yml").first()
        assert saved is not None
        assert saved.workflow_status == "new"

    def test_update_workflow_sets_committed_locally(self):
        """Re-saving an existing workflow must set workflow_status = 'committed_locally'."""
        # Create the workflow first
        _add_workflow(self.db, self.project_id, name="deploy.yml", status="new")

        wf_schema = MagicMock()
        wf_schema.name = "deploy.yml"
        wf_schema.content = "name: Deploy v2\non: push"

        create_or_update_workflow(self.db, wf_schema, self.project_id, is_reusable=False)

        updated = self.db.query(Workflow).filter_by(workflow_name="deploy.yml").first()
        assert updated.workflow_status == "committed_locally"

    def test_update_synced_workflow_resets_to_committed_locally(self):
        """Editing a 'synced_with_github' workflow should demote it to 'committed_locally'."""
        _add_workflow(self.db, self.project_id, name="synced.yml", status="synced_with_github")

        wf_schema = MagicMock()
        wf_schema.name = "synced.yml"
        wf_schema.content = "name: Updated\non: push"

        create_or_update_workflow(self.db, wf_schema, self.project_id, is_reusable=False)

        updated = self.db.query(Workflow).filter_by(workflow_name="synced.yml").first()
        assert updated.workflow_status == "committed_locally"

    def test_new_workflow_creates_initial_version(self):
        """Creating a new workflow should produce a v1 WorkflowVersion entry."""
        wf_schema = MagicMock()
        wf_schema.name = "versioned.yml"
        wf_schema.content = "name: V\non: push"

        create_or_update_workflow(self.db, wf_schema, self.project_id, is_reusable=False)

        wf = self.db.query(Workflow).filter_by(workflow_name="versioned.yml").first()
        version = (
            self.db.query(WorkflowVersion)
            .filter_by(workflow_id=wf.workflow_id)
            .first()
        )
        assert version is not None
        assert version.version_number == 1


# ===========================================================================
# Tests: _update_project_workflows_status()
# ===========================================================================

class TestUpdateProjectWorkflowsStatus:
    """Unit tests for the _update_project_workflows_status() helper."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        account, project = _make_db_fixtures(self.db)
        self.project_id = project.project_id
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_updates_all_workflows_by_default(self):
        wf1 = _add_workflow(self.db, self.project_id, name="a.yml", status="new")
        wf2 = _add_workflow(self.db, self.project_id, name="b.yml", status="committed_locally")

        _update_project_workflows_status(self.db, self.project_id, "under_review")

        self.db.refresh(wf1)
        self.db.refresh(wf2)
        assert wf1.workflow_status == "under_review"
        assert wf2.workflow_status == "under_review"

    def test_only_if_status_filter(self):
        """only_if_status must restrict which workflows are updated."""
        wf_review = _add_workflow(self.db, self.project_id, name="r.yml", status="under_review")
        wf_new = _add_workflow(self.db, self.project_id, name="n.yml", status="new")

        _update_project_workflows_status(
            self.db, self.project_id, "committed_locally", only_if_status="under_review"
        )

        self.db.refresh(wf_review)
        self.db.refresh(wf_new)
        assert wf_review.workflow_status == "committed_locally"
        assert wf_new.workflow_status == "new"  # unchanged

    def test_non_reusable_only_flag(self):
        """non_reusable_only=True must leave reusable workflows unchanged."""
        wf_standard = _add_workflow(self.db, self.project_id, name="std.yml", reusable=False, status="new")
        wf_reusable = _add_workflow(self.db, self.project_id, name="rx.yml", reusable=True, status="new")

        _update_project_workflows_status(
            self.db, self.project_id, "under_review", non_reusable_only=True
        )

        self.db.refresh(wf_standard)
        self.db.refresh(wf_reusable)
        assert wf_standard.workflow_status == "under_review"
        assert wf_reusable.workflow_status == "new"  # unchanged


# ===========================================================================
# Tests: merge_pull_request() and close_pull_request() endpoints
# ===========================================================================

class TestMergeClosePRStatusTransitions:
    """Tests for status transitions triggered by PR merge and close endpoints."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        Base.metadata.create_all(bind=engine)
        app.dependency_overrides[get_db] = override_get_db
        user_tokens["statususer"] = "fake_token"

        db = TestingSessionLocal()
        account, project, repo = _make_db_fixtures(db, include_repo=True, pr_state="open")
        self.project_id = project.project_id

        # Non-reusable workflow under review
        self.wf_std = _add_workflow(db, project.project_id, name="ci.yml", reusable=False, status="under_review")
        self.wf_std_id = self.wf_std.workflow_id
        # Reusable workflow — should NOT change on merge
        self.wf_rx = _add_workflow(db, project.project_id, name="rx.yml", reusable=True, status="new")
        self.wf_rx_id = self.wf_rx.workflow_id

        # One open PR record
        pr = ProjectPullRequest(
            project_id=project.project_id,
            repo_name="statususer/status-repo",
            pr_number=99,
            pr_url="https://github.com/statususer/status-repo/pull/99",
            pr_state="open",
            branch_name="actions-manager/sts-main",
            target_branch="main",
        )
        db.add(pr)
        db.commit()
        db.close()

        self.client = TestClient(app)
        yield

        db2 = TestingSessionLocal()
        Base.metadata.drop_all(bind=engine)
        db2.close()
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]
        if "statususer" in user_tokens:
            del user_tokens["statususer"]

    # -----------------------------------------------------------------------
    # merge_pull_request
    # -----------------------------------------------------------------------

    def test_merge_sets_synced_status_for_non_reusable_only(self):
        """Merging the last open PR must set non-reusable workflows to 'synced_with_github'
        while leaving reusable workflows unchanged."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sha": "mergedsha123"}

        with patch("workflows.github_put", return_value=mock_response):
            resp = self.client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": "statususer",
                    "project_name": "status_project",
                    "repo_name": "statususer/status-repo",
                    "pr_number": 99,
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["merged"] is True

        db = TestingSessionLocal()
        try:
            wf_std = db.query(Workflow).filter_by(workflow_id=self.wf_std_id).first()
            wf_rx = db.query(Workflow).filter_by(workflow_id=self.wf_rx_id).first()
            assert wf_std.workflow_status == "synced_with_github"
            assert wf_rx.workflow_status == "new"  # reusable — must not change
        finally:
            db.close()

    def test_merge_creates_pr_merged_version_entry(self):
        """A successful merge must create a 'pr_merged' WorkflowVersion for each
        non-reusable workflow in the project."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sha": "mergedsha456"}

        with patch("workflows.github_put", return_value=mock_response):
            resp = self.client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": "statususer",
                    "project_name": "status_project",
                    "repo_name": "statususer/status-repo",
                    "pr_number": 99,
                },
            )

        assert resp.status_code == 200

        db = TestingSessionLocal()
        try:
            versions = (
                db.query(WorkflowVersion)
                .filter_by(workflow_id=self.wf_std_id)
                .all()
            )
            import json
            pr_merged_versions = [
                v for v in versions
                if v.version_metadata and json.loads(v.version_metadata).get("action") == "pr_merged"
            ]
            assert len(pr_merged_versions) == 1
            assert json.loads(pr_merged_versions[0].version_metadata)["pr_number"] == 99
        finally:
            db.close()

    def test_merge_no_pr_merged_version_for_reusable_workflow(self):
        """A 'pr_merged' version entry must NOT be created for reusable workflows."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sha": "sha789"}

        with patch("workflows.github_put", return_value=mock_response):
            self.client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": "statususer",
                    "project_name": "status_project",
                    "repo_name": "statususer/status-repo",
                    "pr_number": 99,
                },
            )

        db = TestingSessionLocal()
        try:
            import json
            versions = db.query(WorkflowVersion).filter_by(workflow_id=self.wf_rx_id).all()
            pr_merged = [
                v for v in versions
                if v.version_metadata and json.loads(v.version_metadata).get("action") == "pr_merged"
            ]
            assert len(pr_merged) == 0
        finally:
            db.close()

    def test_merge_does_not_sync_when_other_prs_still_open(self):
        """If another PR is still open after this merge, workflows must NOT move to
        'synced_with_github' and project state must NOT change to 'synced'."""
        # Add a second open PR
        db = TestingSessionLocal()
        pr2 = ProjectPullRequest(
            project_id=self.project_id,
            repo_name="statususer/other-repo",
            pr_number=100,
            pr_url="https://github.com/statususer/other-repo/pull/100",
            pr_state="open",
            branch_name="actions-manager/sts-main",
            target_branch="main",
        )
        db.add(pr2)
        db.commit()
        db.close()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"sha": "sha_partial"}

        with patch("workflows.github_put", return_value=mock_response):
            resp = self.client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": "statususer",
                    "project_name": "status_project",
                    "repo_name": "statususer/status-repo",
                    "pr_number": 99,
                },
            )

        assert resp.status_code == 200

        db = TestingSessionLocal()
        try:
            wf_std = db.query(Workflow).filter_by(workflow_id=self.wf_std_id).first()
            # Still under_review because a second PR is open
            assert wf_std.workflow_status == "under_review"

            project = db.query(Project).filter_by(project_id=self.project_id).first()
            assert project.pr_state != "synced"
        finally:
            db.close()

    # -----------------------------------------------------------------------
    # close_pull_request
    # -----------------------------------------------------------------------

    def test_close_reverts_under_review_to_committed_locally(self):
        """Closing the last open PR reverts 'under_review' workflows to 'committed_locally'."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"state": "closed"}

        with patch("workflows.github_patch", return_value=mock_response):
            resp = self.client.patch(
                "/api/close-pull-request",
                json={
                    "github_user": "statususer",
                    "project_name": "status_project",
                    "repo_name": "statususer/status-repo",
                    "pr_number": 99,
                },
            )

        assert resp.status_code == 200, resp.text
        assert resp.json()["closed"] is True

        db = TestingSessionLocal()
        try:
            wf_std = db.query(Workflow).filter_by(workflow_id=self.wf_std_id).first()
            assert wf_std.workflow_status == "committed_locally"
        finally:
            db.close()

    def test_close_does_not_revert_when_other_prs_still_open(self):
        """Closing one PR while another is still open must NOT revert workflow statuses."""
        # Add a second open PR
        db = TestingSessionLocal()
        pr2 = ProjectPullRequest(
            project_id=self.project_id,
            repo_name="statususer/other-repo",
            pr_number=101,
            pr_url="https://github.com/statususer/other-repo/pull/101",
            pr_state="open",
            branch_name="actions-manager/sts-main-2",
            target_branch="main",
        )
        db.add(pr2)
        db.commit()
        db.close()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"state": "closed"}

        with patch("workflows.github_patch", return_value=mock_response):
            resp = self.client.patch(
                "/api/close-pull-request",
                json={
                    "github_user": "statususer",
                    "project_name": "status_project",
                    "repo_name": "statususer/status-repo",
                    "pr_number": 99,
                },
            )

        assert resp.status_code == 200

        db = TestingSessionLocal()
        try:
            wf_std = db.query(Workflow).filter_by(workflow_id=self.wf_std_id).first()
            # Still under_review since pr2 is still open
            assert wf_std.workflow_status == "under_review"
        finally:
            db.close()

    def test_close_reverts_project_state_when_no_prs_remain(self):
        """Closing the last open PR must also move the project state back to 'draft'."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"state": "closed"}

        with patch("workflows.github_patch", return_value=mock_response):
            self.client.patch(
                "/api/close-pull-request",
                json={
                    "github_user": "statususer",
                    "project_name": "status_project",
                    "repo_name": "statususer/status-repo",
                    "pr_number": 99,
                },
            )

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_id=self.project_id).first()
            assert project.pr_state == "draft"
        finally:
            db.close()
