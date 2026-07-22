import os
import sys
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from auth import user_tokens  # noqa: E402
from main import app  # noqa: E402
from models import Account, Base, Project, ProjectRepo, Repo, Workflow, ProjectWorkflow  # noqa: E402
from projects import get_db as projects_get_db  # noqa: E402
from workflows import get_db as workflows_get_db  # noqa: E402

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_validation_preflight.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestValidationPreflight:
    @pytest.fixture(autouse=True)
    def setup_database(self):
        app.dependency_overrides[projects_get_db] = override_get_db
        app.dependency_overrides[workflows_get_db] = override_get_db
        Base.metadata.create_all(bind=engine)
        db = TestingSessionLocal()
        try:
            db.add(Account(github_user="preflightuser", github_email="p@example.com", account_type="professional"))
            db.commit()
        finally:
            db.close()
        user_tokens.clear()
        yield
        user_tokens.clear()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(projects_get_db, None)
        app.dependency_overrides.pop(workflows_get_db, None)

    def setup_method(self):
        self.client = TestClient(app)

    def _payload(self, **overrides):
        body = {
            "github_user": "preflightuser",
            "project_name": "Preflight Project",
            "selected_repos": ["owner/target"],
            "workflows": [{"name": "build", "content": "name: Build\non: push\njobs: {}\n"}],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "repository_visibility_scope": "public",
        }
        body.update(overrides)
        return body

    def _create_project(self, **overrides):
        response = self.client.post("/api/projects/", json=self._payload(**overrides))
        assert response.status_code == 200, response.text
        return response.json()

    def test_configures_changes_and_removes_validation_repository(self):
        created = self._create_project(validation_repo="owner/validation", preflight_required=True)

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            validation = db.query(Repo).filter(Repo.repo_id == project.validation_repo_id).first()
            assert validation.repo_name == "owner/validation"
            assert project.preflight_required is True
            assert project.last_preflight_status == "not_run"
        finally:
            db.close()

        update = self.client.put(
            f"/api/projects/{created['project_id']}/",
            json=self._payload(validation_repo="owner/validation-two", preflight_required=False),
        )
        assert update.status_code == 200, update.text

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            validation = db.query(Repo).filter(Repo.repo_id == project.validation_repo_id).first()
            assert validation.repo_name == "owner/validation-two"
            assert project.preflight_required is False
        finally:
            db.close()

        remove = self.client.put(
            f"/api/projects/{created['project_id']}/",
            json=self._payload(validation_repo=None, preflight_required=True),
        )
        assert remove.status_code == 200, remove.text
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            assert project.validation_repo_id is None
            assert project.preflight_required is False
        finally:
            db.close()

    def test_validation_repository_is_not_a_campaign_target(self):
        created = self._create_project(validation_repo="owner/validation")
        project_response = self.client.get("/api/projects/Preflight Project?github_user=preflightuser")
        assert project_response.status_code == 200, project_response.text
        assert project_response.json()["selected_repos"] == ["owner/target"]
        assert project_response.json()["validation_repo"] == "owner/validation"

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            target_names = [
                repo.repo_name
                for repo in db.query(Repo).join(ProjectRepo, ProjectRepo.repo_id == Repo.repo_id)
                .filter(ProjectRepo.project_id == project.project_id)
            ]
            assert target_names == ["owner/target"]
        finally:
            db.close()

    @patch("workflows._save_prs_and_update_status", return_value=(1, 1))
    @patch("workflows._build_reusable_workflow_results", return_value=({}, []))
    @patch("workflows._build_regular_workflow_results", return_value=({"owner/target on main": {"status": "pr_created"}}, ["build"]))
    def test_campaign_creation_without_validation_repository_is_allowed(self, *_):
        self._create_project()
        user_tokens["preflightuser"] = "token"
        response = self.client.post(
            "/api/create-pull-requests",
            json={"github_user": "preflightuser", "project_name": "Preflight Project"},
        )
        assert response.status_code == 200, response.text

    @patch("workflows._build_regular_workflow_results")
    def test_required_preflight_blocks_campaign_when_not_run(self, mock_build):
        self._create_project(validation_repo="owner/validation", preflight_required=True)
        user_tokens["preflightuser"] = "token"
        response = self.client.post(
            "/api/create-pull-requests",
            json={"github_user": "preflightuser", "project_name": "Preflight Project"},
        )
        assert response.status_code == 400, response.text
        assert "Preflight validation must pass" in response.json()["detail"]
        mock_build.assert_not_called()

    @patch("workflows._save_prs_and_update_status", return_value=(1, 1))
    @patch("workflows._build_reusable_workflow_results", return_value=({}, []))
    @patch("workflows._build_regular_workflow_results", return_value=({"owner/target on main": {"status": "pr_created"}}, ["build"]))
    def test_required_preflight_passed_allows_campaign(self, *_):
        created = self._create_project(validation_repo="owner/validation", preflight_required=True)
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            project.last_preflight_status = "passed"
            db.commit()
        finally:
            db.close()
        user_tokens["preflightuser"] = "token"
        response = self.client.post(
            "/api/create-pull-requests",
            json={"github_user": "preflightuser", "project_name": "Preflight Project"},
        )
        assert response.status_code == 200, response.text

    @patch("workflows._process_regular_workflows_update")
    @patch("workflows.github_get")
    def test_run_preflight_success_records_pr_open(self, mock_get, mock_process):
        self._create_project(validation_repo="owner/validation")
        user_tokens["preflightuser"] = "token"
        mock_get.return_value = Mock(status_code=200)
        mock_process.return_value = {
            "owner/validation on main": {
                "status": "pr_created",
                "pr_url": "https://github.com/owner/validation/pull/1",
                "pr_number": 1,
            }
        }
        response = self.client.post(
            "/api/run-preflight-validation",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "selected_workflows": ["build"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "validation_pr_open"

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Preflight Project").first()
            assert project.last_preflight_status == "validation_pr_open"
            assert project.last_preflight_pr_url == "https://github.com/owner/validation/pull/1"
        finally:
            db.close()

    @patch("workflows._process_regular_workflows_update")
    @patch("workflows.github_get")
    def test_run_preflight_failure_records_error(self, mock_get, mock_process):
        self._create_project(validation_repo="owner/validation")
        user_tokens["preflightuser"] = "token"
        mock_get.return_value = Mock(status_code=200)
        mock_process.return_value = {"owner/validation on main": {"status": "error", "error": "Missing workflow permission"}}
        response = self.client.post(
            "/api/run-preflight-validation",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "selected_workflows": ["build"]},
        )
        assert response.status_code == 400, response.text
        assert "Missing workflow permission" in response.json()["detail"]

    @patch("workflows.github_get")
    def test_run_preflight_handles_inaccessible_validation_repository(self, mock_get):
        self._create_project(validation_repo="owner/validation")
        user_tokens["preflightuser"] = "token"
        mock_get.return_value = Mock(status_code=404)
        response = self.client.post(
            "/api/run-preflight-validation",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "selected_workflows": ["build"]},
        )
        assert response.status_code == 400, response.text
        assert "inaccessible" in response.json()["detail"]

    @patch("workflows.github_get")
    def test_run_preflight_handles_missing_github_permissions(self, mock_get):
        self._create_project(validation_repo="owner/validation")
        user_tokens["preflightuser"] = "token"
        mock_get.return_value = Mock(status_code=403)
        response = self.client.post(
            "/api/run-preflight-validation",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "selected_workflows": ["build"]},
        )
        assert response.status_code == 403, response.text
        assert "403 Forbidden" in response.json()["detail"]

    @patch("workflows.github_get")
    def test_refresh_preflight_status_passes_when_validation_pr_merged(self, mock_get):
        created = self._create_project(validation_repo="owner/validation")
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            project.last_preflight_status = "validation_pr_open"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            db.commit()
        finally:
            db.close()

        user_tokens["preflightuser"] = "token"

        pr_payload = {
            "state": "closed",
            "merged": False,
            "merged_at": "2026-05-27T02:30:00Z",
            "head": {"sha": "abc123", "ref": "AM_PREFLIGHT"},
            "base": {"ref": "main", "repo": {"owner": {"login": "owner"}, "name": "validation"}},
        }
        mock_get.return_value = Mock(status_code=200, json=lambda: pr_payload)

        response = self.client.get(
            "/api/preflight-validation-status",
            params={"github_user": "preflightuser", "project_name": "Preflight Project", "refresh_from_github": "true"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "passed"

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Preflight Project").first()
            assert project.last_preflight_status == "passed"
        finally:
            db.close()

    @patch("workflows.github_get")
    def test_refresh_preflight_status_marks_closed_pr_as_rejected(self, mock_get):
        created = self._create_project(validation_repo="owner/validation")
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            project.last_preflight_status = "validation_pr_open"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            db.commit()
        finally:
            db.close()

        user_tokens["preflightuser"] = "token"

        pr_payload = {
            "state": "closed",
            "merged": False,
            "head": {"sha": "abc123", "ref": "AM_PREFLIGHT"},
            "base": {"ref": "main", "repo": {"owner": {"login": "owner"}, "name": "validation"}},
        }
        mock_get.return_value = Mock(status_code=200, json=lambda: pr_payload)

        response = self.client.get(
            "/api/preflight-validation-status",
            params={"github_user": "preflightuser", "project_name": "Preflight Project", "refresh_from_github": "true"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "closed"
        assert response.json()["pr_state"] == "closed"

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Preflight Project").first()
            assert project.last_preflight_status == "closed"
        finally:
            db.close()

    @patch("workflows._delete_actions_manager_branch", return_value=(True, None))
    @patch("workflows.github_put")
    @patch("workflows.github_get")
    def test_merge_preflight_pr_keeps_passed_outcome_and_cleans_branch(self, mock_get, mock_put, mock_delete):
        created = self._create_project(validation_repo="owner/validation")
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            project.last_preflight_status = "validation_pr_open"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            db.commit()
        finally:
            db.close()

        user_tokens["preflightuser"] = "token"
        pr_payload = {
            "state": "open",
            "merged": False,
            "head": {"sha": "abc123", "ref": "AM_PREFLIGHT"},
            "base": {"ref": "main", "repo": {"owner": {"login": "owner"}, "name": "validation"}},
        }
        mock_get.return_value = Mock(status_code=200, json=lambda: pr_payload)
        mock_put.return_value = Mock(status_code=200, json=lambda: {"sha": "merge-sha"})

        response = self.client.put(
            "/api/merge-preflight-validation-pr",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "cleanup_branch": True},
        )

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "passed"
        assert response.json()["branch_deleted"] is True
        mock_put.assert_called_once()
        assert mock_put.call_args.args[0] == "https://api.github.com/repos/owner/validation/pulls/1/merge"
        mock_delete.assert_called_once_with(
            owner="owner",
            repo="validation",
            branch_name="AM_PREFLIGHT",
            target_branch="main",
            github_user="preflightuser",
        )

    @patch("workflows._delete_actions_manager_branch", return_value=(True, None))
    @patch("workflows.github_put")
    @patch("workflows.github_get")
    def test_merge_preflight_pr_retries_supported_merge_methods(self, mock_get, mock_put, _mock_delete):
        created = self._create_project(validation_repo="owner/validation")
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            project.last_preflight_status = "validation_pr_open"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            db.commit()
        finally:
            db.close()

        user_tokens["preflightuser"] = "token"
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "state": "open",
                "merged": False,
                "head": {"sha": "abc123", "ref": "AM_PREFLIGHT"},
                "base": {"ref": "main", "repo": {"owner": {"login": "owner"}, "name": "validation"}},
            },
        )
        merge_disabled = Mock(status_code=405, text='{"message":"Merge commits are not allowed"}')
        merge_disabled.json.return_value = {"message": "Merge commits are not allowed"}
        mock_put.side_effect = [
            merge_disabled,
            Mock(status_code=200, json=lambda: {"sha": "merge-sha"}),
        ]

        response = self.client.put(
            "/api/merge-preflight-validation-pr",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "cleanup_branch": True},
        )

        assert response.status_code == 200, response.text
        assert response.json()["merge_method"] == "squash"
        assert mock_put.call_args_list[0].kwargs["json"]["merge_method"] == "merge"
        assert mock_put.call_args_list[1].kwargs["json"]["merge_method"] == "squash"

    @patch("workflows.github_put")
    @patch("workflows.github_get")
    def test_merge_preflight_pr_requires_open_pr(self, mock_get, mock_put):
        created = self._create_project(validation_repo="owner/validation")
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            project.last_preflight_status = "validation_pr_open"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            db.commit()
        finally:
            db.close()
        user_tokens["preflightuser"] = "token"

        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {"state": "closed", "merged": False},
        )
        response = self.client.put(
            "/api/merge-preflight-validation-pr",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "cleanup_branch": True},
        )

        assert response.status_code == 400, response.text
        assert "not open" in response.json()["detail"].lower()
        mock_put.assert_not_called()

    @patch("workflows._delete_actions_manager_branch", return_value=(True, None))
    @patch("workflows.github_patch")
    @patch("workflows.github_get")
    def test_close_preflight_pr_keeps_passed_outcome(self, mock_get, mock_patch, *_):
        created = self._create_project(validation_repo="owner/validation")
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            project.last_preflight_status = "passed"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            db.commit()
        finally:
            db.close()

        user_tokens["preflightuser"] = "token"
        pr_payload = {
            "state": "closed",
            "merged": True,
            "head": {"sha": "abc123", "ref": "AM_PREFLIGHT"},
            "base": {"ref": "main", "repo": {"owner": {"login": "owner"}, "name": "validation"}},
        }
        mock_get.return_value = Mock(status_code=200, json=lambda: pr_payload)

        response = self.client.patch(
            "/api/close-preflight-validation-pr",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "cleanup_branch": True},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "passed"
        mock_patch.assert_not_called()

    # ------------------------------------------------------------------
    # Content-hash / stale detection tests
    # ------------------------------------------------------------------

    @patch("workflows.github_get")
    def test_status_becomes_stale_when_workflow_yaml_changes(self, mock_get):
        """Changing a workflow's YAML after approval downgrades status to stale."""
        from workflows import _compute_preflight_content_hash

        created = self._create_project(validation_repo="owner/validation")

        # Compute the hash that matches the initial project state.
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == project.project_id
            ).first()
            initial_hash = _compute_preflight_content_hash(
                [{"name": wf.workflow_name, "content": wf.workflow_yaml}],
                "owner/validation",
            )
            project.last_preflight_status = "passed"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            project.last_preflight_content_hash = initial_hash
            db.commit()
        finally:
            db.close()

        # Edit the workflow YAML so the hash no longer matches.
        db = TestingSessionLocal()
        try:
            wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == created["project_id"]
            ).first()
            wf.workflow_yaml = "name: Build\non: push\njobs:\n  changed: {}\n"
            db.commit()
        finally:
            db.close()

        user_tokens["preflightuser"] = "token"
        # The status endpoint should detect the mismatch and return stale.
        response = self.client.get(
            "/api/preflight-validation-status",
            params={"github_user": "preflightuser", "project_name": "Preflight Project", "refresh_from_github": "false"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "stale"

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Preflight Project").first()
            assert project.last_preflight_status == "stale"
        finally:
            db.close()
        mock_get.assert_not_called()

    @patch("workflows.github_get")
    def test_status_remains_passed_when_content_unchanged(self, mock_get):
        """Status stays passed when workflow content has not changed."""
        from workflows import _compute_preflight_content_hash

        created = self._create_project(validation_repo="owner/validation")

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == created["project_id"]).first()
            wf = db.query(Workflow).join(ProjectWorkflow).filter(
                ProjectWorkflow.project_id == project.project_id
            ).first()
            initial_hash = _compute_preflight_content_hash(
                [{"name": wf.workflow_name, "content": wf.workflow_yaml}],
                "owner/validation",
            )
            project.last_preflight_status = "passed"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            project.last_preflight_content_hash = initial_hash
            db.commit()
        finally:
            db.close()

        user_tokens["preflightuser"] = "token"
        response = self.client.get(
            "/api/preflight-validation-status",
            params={"github_user": "preflightuser", "project_name": "Preflight Project", "refresh_from_github": "false"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "passed"
        mock_get.assert_not_called()

    @patch("workflows._build_regular_workflow_results")
    def test_campaign_blocked_when_preflight_stale(self, mock_build):
        """Campaign creation is blocked when content changed after approval."""
        self._create_project(validation_repo="owner/validation", preflight_required=True)
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Preflight Project").first()
            # Simulate stale: status is passed but stored hash doesn't match current.
            project.last_preflight_status = "passed"
            project.last_preflight_pr_url = "https://github.com/owner/validation/pull/1"
            project.last_preflight_content_hash = "definitely_not_matching_hash"
            db.commit()
        finally:
            db.close()

        user_tokens["preflightuser"] = "token"
        response = self.client.post(
            "/api/create-pull-requests",
            json={"github_user": "preflightuser", "project_name": "Preflight Project"},
        )
        assert response.status_code == 400, response.text
        assert "Preflight validation must pass" in response.json()["detail"]
        mock_build.assert_not_called()

    @patch("workflows._process_regular_workflows_update")
    @patch("workflows.github_get")
    def test_run_preflight_stores_content_hash(self, mock_get, mock_process):
        """Running preflight records a content hash on the project."""
        self._create_project(validation_repo="owner/validation")
        user_tokens["preflightuser"] = "token"
        mock_get.return_value = Mock(status_code=200)
        mock_process.return_value = {
            "owner/validation on main": {
                "status": "pr_created",
                "pr_url": "https://github.com/owner/validation/pull/2",
                "pr_number": 2,
            }
        }
        response = self.client.post(
            "/api/run-preflight-validation",
            json={"github_user": "preflightuser", "project_name": "Preflight Project", "selected_workflows": ["build"]},
        )
        assert response.status_code == 200, response.text

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Preflight Project").first()
            assert project.last_preflight_content_hash is not None
            assert len(project.last_preflight_content_hash) == 64  # SHA-256 hex
        finally:
            db.close()
