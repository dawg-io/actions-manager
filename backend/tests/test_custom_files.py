"""
Tests for the Custom Files API (backend/custom_files.py) and PR Campaign integration.

Covers:
- Authentication (401 when no token)
- Path validation (absolute, traversal, .env, .pem)
- CRUD operations (create, list, update, delete, restore)
- Duplicate path rejection (409)
- Unauthorized project access rejection
- Status transitions on save/update
- Hard delete for never-synced files
- Pending delete for synced files
- PR campaign integration: custom files included in _save_prs_and_update_status
- Merge/close status updates for custom files
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, CustomFile
from main import app
from custom_files import get_db, validate_file_path


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


TEST_USER = "cf_testuser"
TEST_PROJECT = "cf_testproject"


def _seed(db):
    account = Account(
        github_user=TEST_USER,
        github_email="cf@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_name=TEST_PROJECT,
        project_code="CFT",
        user_id=account.user_id,
        branch_option="default",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return account, project


class TestPathValidation:
    def test_valid_github_actions_path(self):
        assert validate_file_path(".github/actions/build/action.yml") is None

    def test_valid_github_scripts_path(self):
        assert validate_file_path(".github/scripts/deploy.sh") is None

    def test_valid_sonar_properties(self):
        assert validate_file_path("sonar-project.properties") is None

    def test_valid_yamllint(self):
        assert validate_file_path(".yamllint.yml") is None

    def test_valid_hadolint(self):
        assert validate_file_path(".hadolint.yaml") is None

    def test_valid_dependabot(self):
        assert validate_file_path(".github/dependabot.yml") is None

    def test_absolute_path_rejected(self):
        assert validate_file_path("/etc/passwd") is not None

    def test_path_traversal_rejected(self):
        assert validate_file_path("../../etc/passwd") is not None
        assert validate_file_path(".github/../../../secret") is not None

    def test_dotenv_rejected(self):
        assert validate_file_path(".env") is not None
        assert validate_file_path(".env.production") is not None
        assert validate_file_path(".env.local") is not None

    def test_pem_rejected(self):
        assert validate_file_path("cert.pem") is not None
        assert validate_file_path("secrets/private.key") is not None

    def test_pfx_rejected(self):
        assert validate_file_path("keystore.p12") is not None
        assert validate_file_path("keystore.pfx") is not None

    def test_crt_rejected(self):
        assert validate_file_path("ca.crt") is not None
        assert validate_file_path("ca.cert") is not None

    def test_jks_rejected(self):
        assert validate_file_path("keystore.jks") is not None

    def test_git_dir_rejected(self):
        assert validate_file_path(".git/config") is not None
        assert validate_file_path("something/.git/hooks/pre-commit") is not None

    def test_empty_path_rejected(self):
        assert validate_file_path("") is not None
        assert validate_file_path("   ") is not None


class TestCustomFilesAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        self.client = TestClient(app)
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    def test_list_unauthenticated_returns_401(self):
        _, project = _seed(self.db)
        resp = self.client.get(f"/api/projects/{project.project_id}/custom-files")
        assert resp.status_code == 401

    def test_list_returns_empty_for_new_project(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.get(
                f"/api/projects/{project.project_id}/custom-files",
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 200
        assert resp.json()["custom_files"] == []

    def test_create_custom_file_success(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={
                    "github_user": TEST_USER,
                    "file_path": ".github/scripts/build.sh",
                    "file_content": "#!/bin/bash\necho hello",
                    "display_name": "Build Script",
                },
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 200
        data = resp.json()["custom_file"]
        assert data["file_path"] == ".github/scripts/build.sh"
        assert data["file_status"] == "new"
        assert data["git_hash"] is None
        assert data["pending_delete"] is False

    def test_create_duplicate_path_returns_409(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "sonar-project.properties", "file_content": ""},
                headers={"X-GitHub-User": TEST_USER},
            )
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "sonar-project.properties", "file_content": "x"},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 409

    def test_create_invalid_path_absolute_returns_400(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "/etc/passwd", "file_content": ""},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 400

    def test_create_invalid_path_traversal_returns_400(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "../../secret", "file_content": ""},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 400

    def test_create_dotenv_path_returns_400(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": ".env.production", "file_content": ""},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 400

    def test_create_pem_path_returns_400(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "private.pem", "file_content": ""},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 400

    def test_create_wrong_project_returns_403(self):
        account, project = _seed(self.db)
        # Create another user/project
        other_account = Account(github_user="other_user", github_email="other@example.com", account_type="free")
        self.db.add(other_account)
        self.db.commit()
        self.db.refresh(other_account)
        other_project = Project(
            project_name="other_project", project_code="OTH",
            user_id=other_account.user_id, branch_option="default",
        )
        self.db.add(other_project)
        self.db.commit()
        self.db.refresh(other_project)

        # TEST_USER tries to create a file in other_project
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{other_project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "sonar.properties", "file_content": ""},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code in (403, 404)

    def test_update_sets_status_committed_locally(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            create_resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": ".yamllint.yml", "file_content": "---"},
                headers={"X-GitHub-User": TEST_USER},
            )
            file_id = create_resp.json()["custom_file"]["id"]
            update_resp = self.client.put(
                f"/api/projects/{project.project_id}/custom-files/{file_id}",
                json={"github_user": TEST_USER, "file_content": "---\nextend: default"},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert update_resp.status_code == 200
        data = update_resp.json()["custom_file"]
        assert data["file_status"] == "committed_locally"
        assert data["git_hash"] is None

    def test_update_clears_git_hash(self):
        _, project = _seed(self.db)
        # Manually set a git_hash to simulate a previously synced file
        cf = CustomFile(
            project_id=project.project_id,
            file_path="sonar-project.properties",
            file_content="sonar.projectKey=old",
            file_status="synced_with_github",
            git_hash="abc123" * 7,
        )
        self.db.add(cf)
        self.db.commit()
        self.db.refresh(cf)

        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.put(
                f"/api/projects/{project.project_id}/custom-files/{cf.id}",
                json={"github_user": TEST_USER, "file_content": "sonar.projectKey=new"},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 200
        data = resp.json()["custom_file"]
        assert data["git_hash"] is None
        assert data["file_status"] == "committed_locally"

    def test_delete_new_file_hard_deletes(self):
        _, project = _seed(self.db)
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            create_resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": ".hadolint.yaml", "file_content": ""},
                headers={"X-GitHub-User": TEST_USER},
            )
            file_id = create_resp.json()["custom_file"]["id"]
            del_resp = self.client.delete(
                f"/api/projects/{project.project_id}/custom-files/{file_id}",
                headers={"X-GitHub-User": TEST_USER},
                params={"github_user": TEST_USER},
            )
        assert del_resp.status_code == 200
        assert del_resp.json()["hard_deleted"] is True
        # Confirm gone from DB
        assert self.db.query(CustomFile).filter_by(id=file_id).first() is None

    def test_delete_synced_file_marks_pending_delete(self):
        _, project = _seed(self.db)
        cf = CustomFile(
            project_id=project.project_id,
            file_path="sonar-project.properties",
            file_content="sonar.projectKey=x",
            file_status="synced_with_github",
            git_hash="a" * 40,
        )
        self.db.add(cf)
        self.db.commit()
        self.db.refresh(cf)

        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.delete(
                f"/api/projects/{project.project_id}/custom-files/{cf.id}",
                headers={"X-GitHub-User": TEST_USER},
                params={"github_user": TEST_USER},
            )
        assert resp.status_code == 200
        assert resp.json()["pending_delete"] is True
        self.db.refresh(cf)
        assert cf.pending_delete is True
        assert cf.file_status == "committed_locally"

    def test_restore_clears_pending_delete(self):
        _, project = _seed(self.db)
        cf = CustomFile(
            project_id=project.project_id,
            file_path="sonar-project.properties",
            file_content="x",
            file_status="committed_locally",
            git_hash="a" * 40,
            pending_delete=True,
        )
        self.db.add(cf)
        self.db.commit()
        self.db.refresh(cf)

        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files/{cf.id}/restore",
                headers={"X-GitHub-User": TEST_USER},
                params={"github_user": TEST_USER},
            )
        assert resp.status_code == 200
        assert resp.json()["custom_file"]["pending_delete"] is False

    def test_list_returns_all_project_files(self):
        _, project = _seed(self.db)
        paths = [".yamllint.yml", ".hadolint.yaml", "sonar-project.properties"]
        for p in paths:
            self.db.add(CustomFile(project_id=project.project_id, file_path=p, file_content=""))
        self.db.commit()

        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.get(
                f"/api/projects/{project.project_id}/custom-files",
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 200
        returned_paths = {f["file_path"] for f in resp.json()["custom_files"]}
        assert returned_paths == set(paths)


class TestCustomFilesStatusTransitions:
    """Tests for _update_project_custom_files_status used in merge/close lifecycle."""

    @pytest.fixture(autouse=True)
    def setup(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def _make_project_and_file(self, status="under_review", pending_delete=False):
        account = Account(github_user="lifecycle_user", github_email="lc@x.com", account_type="free")
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        project = Project(
            project_name="lc_project", project_code="LC1",
            user_id=account.user_id, branch_option="default",
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        cf = CustomFile(
            project_id=project.project_id,
            file_path="sonar-project.properties",
            file_content="x",
            file_status=status,
            git_hash="a" * 40,
            pending_delete=pending_delete,
        )
        self.db.add(cf)
        self.db.commit()
        self.db.refresh(cf)
        return project, cf

    def test_status_becomes_synced_on_merge(self):
        from workflows import _update_project_custom_files_status
        project, cf = self._make_project_and_file(status="under_review")
        _update_project_custom_files_status(self.db, project.project_id, "synced_with_github", only_if_status="under_review")
        self.db.refresh(cf)
        assert cf.file_status == "synced_with_github"

    def test_status_becomes_committed_on_close(self):
        from workflows import _update_project_custom_files_status
        project, cf = self._make_project_and_file(status="under_review")
        _update_project_custom_files_status(self.db, project.project_id, "committed_locally", only_if_status="under_review")
        self.db.refresh(cf)
        assert cf.file_status == "committed_locally"

    def test_pending_delete_row_is_hard_deleted_on_sync(self):
        from workflows import _update_project_custom_files_status
        project, cf = self._make_project_and_file(status="under_review", pending_delete=True)
        cf_id = cf.id
        _update_project_custom_files_status(self.db, project.project_id, "synced_with_github", only_if_status="under_review")
        assert self.db.query(CustomFile).filter_by(id=cf_id).first() is None

    def test_only_if_status_filter_respected(self):
        from workflows import _update_project_custom_files_status
        project, cf = self._make_project_and_file(status="committed_locally")
        _update_project_custom_files_status(self.db, project.project_id, "synced_with_github", only_if_status="under_review")
        self.db.refresh(cf)
        # Should NOT change because file was committed_locally, not under_review
        assert cf.file_status == "committed_locally"


class TestBuildCustomFilesForDelivery:
    """Tests for _build_custom_files_for_delivery."""

    @pytest.fixture(autouse=True)
    def setup(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def _seed(self):
        account = Account(github_user="del_user", github_email="del@x.com", account_type="free")
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        project = Project(
            project_name="del_project", project_code="DEL",
            user_id=account.user_id, branch_option="default",
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def test_returns_new_and_committed_files(self):
        from workflows import _build_custom_files_for_delivery, CreatePullRequestsRequest
        project = self._seed()
        self.db.add(CustomFile(project_id=project.project_id, file_path="a.yml", file_content="", file_status="new"))
        self.db.add(CustomFile(project_id=project.project_id, file_path="b.yml", file_content="", file_status="committed_locally"))
        self.db.add(CustomFile(project_id=project.project_id, file_path="c.yml", file_content="", file_status="synced_with_github"))
        self.db.commit()

        payload = CreatePullRequestsRequest(project_name="del_project")
        result = _build_custom_files_for_delivery(project, payload, self.db)
        paths = {r["file_path"] for r in result}
        assert "a.yml" in paths
        assert "b.yml" in paths
        assert "c.yml" not in paths

    def test_returns_pending_delete_files(self):
        from workflows import _build_custom_files_for_delivery, CreatePullRequestsRequest
        project = self._seed()
        self.db.add(CustomFile(
            project_id=project.project_id, file_path="old.yml", file_content="",
            file_status="synced_with_github", pending_delete=True,
        ))
        self.db.commit()

        payload = CreatePullRequestsRequest(project_name="del_project")
        result = _build_custom_files_for_delivery(project, payload, self.db)
        assert any(r["file_path"] == "old.yml" for r in result)

    def test_selected_ids_empty_returns_nothing(self):
        from workflows import _build_custom_files_for_delivery, CreatePullRequestsRequest
        project = self._seed()
        self.db.add(CustomFile(project_id=project.project_id, file_path="x.yml", file_content="", file_status="new"))
        self.db.commit()

        payload = CreatePullRequestsRequest(project_name="del_project", selected_custom_file_ids=[])
        result = _build_custom_files_for_delivery(project, payload, self.db)
        assert result == []


class TestBug1ProjectDraftPromotion:
    """Regression tests for Bug 1: creating/editing/deleting a Custom File must
    promote project.pr_state to 'draft' so the Create PR Campaign button enables."""

    @pytest.fixture(autouse=True)
    def setup(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        self.client = TestClient(app)
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    def _seed_with_state(self, pr_state: str):
        account = Account(github_user=TEST_USER, github_email="b1@x.com", account_type="free")
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        project = Project(
            project_name="b1_project", project_code="B1T",
            user_id=account.user_id, branch_option="default",
            pr_state=pr_state,
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def test_create_promotes_new_to_draft(self):
        project = self._seed_with_state("new")
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "sonar.properties", "file_content": "x"},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 200
        self.db.refresh(project)
        assert project.pr_state == "draft"

    def test_create_promotes_synced_to_draft(self):
        project = self._seed_with_state("synced")
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "sonar.properties", "file_content": "x"},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 200
        self.db.refresh(project)
        assert project.pr_state == "draft"

    def test_create_does_not_change_open_state(self):
        project = self._seed_with_state("open")
        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            self.client.post(
                f"/api/projects/{project.project_id}/custom-files",
                json={"github_user": TEST_USER, "file_path": "sonar.properties", "file_content": "x"},
                headers={"X-GitHub-User": TEST_USER},
            )
        self.db.refresh(project)
        assert project.pr_state == "open"

    def test_update_promotes_synced_to_draft(self):
        project = self._seed_with_state("synced")
        cf = CustomFile(
            project_id=project.project_id, file_path="sonar.properties",
            file_content="old", file_status="synced_with_github", git_hash="a" * 40,
        )
        self.db.add(cf)
        self.db.commit()
        self.db.refresh(cf)

        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.put(
                f"/api/projects/{project.project_id}/custom-files/{cf.id}",
                json={"github_user": TEST_USER, "file_content": "new"},
                headers={"X-GitHub-User": TEST_USER},
            )
        assert resp.status_code == 200
        self.db.refresh(project)
        assert project.pr_state == "draft"

    def test_delete_promotes_synced_to_draft(self):
        project = self._seed_with_state("synced")
        cf = CustomFile(
            project_id=project.project_id, file_path="sonar.properties",
            file_content="x", file_status="synced_with_github", git_hash="a" * 40,
        )
        self.db.add(cf)
        self.db.commit()
        self.db.refresh(cf)

        with patch("custom_files.user_tokens", {TEST_USER: "fake-token"}):
            resp = self.client.delete(
                f"/api/projects/{project.project_id}/custom-files/{cf.id}",
                headers={"X-GitHub-User": TEST_USER},
                params={"github_user": TEST_USER},
            )
        assert resp.status_code == 200
        self.db.refresh(project)
        assert project.pr_state == "draft"


class TestBug2CustomFileSurvivesMerge:
    """Regression tests for Bug 2: non-pending-delete Custom Files must remain in
    the DB after a PR Campaign merge and be returned by the list API."""

    @pytest.fixture(autouse=True)
    def setup(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def _seed(self):
        account = Account(github_user="b2_user", github_email="b2@x.com", account_type="free")
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        project = Project(
            project_name="b2_project", project_code="B2T",
            user_id=account.user_id, branch_option="default",
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def test_newly_added_file_survives_merge(self):
        from workflows import _update_project_custom_files_status
        project = self._seed()
        cf = CustomFile(
            project_id=project.project_id,
            file_path="sonar-project.properties",
            file_content="sonar.projectKey=myapp",
            file_status="under_review",
            git_hash=None,
            pending_delete=False,
        )
        self.db.add(cf)
        self.db.commit()
        self.db.refresh(cf)
        cf_id = cf.id

        _update_project_custom_files_status(self.db, project.project_id, "synced_with_github", only_if_status="under_review")

        surviving = self.db.query(CustomFile).filter_by(id=cf_id).first()
        assert surviving is not None, "Custom file must not be deleted after merge"
        assert surviving.file_status == "synced_with_github"
        assert surviving.pending_delete is False

    def test_updated_file_survives_merge(self):
        from workflows import _update_project_custom_files_status
        project = self._seed()
        cf = CustomFile(
            project_id=project.project_id,
            file_path=".yamllint.yml",
            file_content="extend: default",
            file_status="under_review",
            git_hash="a" * 40,
            pending_delete=False,
        )
        self.db.add(cf)
        self.db.commit()
        self.db.refresh(cf)
        cf_id = cf.id

        _update_project_custom_files_status(self.db, project.project_id, "synced_with_github", only_if_status="under_review")

        surviving = self.db.query(CustomFile).filter_by(id=cf_id).first()
        assert surviving is not None
        assert surviving.file_status == "synced_with_github"

    def test_pending_delete_file_is_removed_on_merge(self):
        from workflows import _update_project_custom_files_status
        project = self._seed()
        cf = CustomFile(
            project_id=project.project_id,
            file_path="old-script.sh",
            file_content="",
            file_status="under_review",
            git_hash="b" * 40,
            pending_delete=True,
        )
        self.db.add(cf)
        self.db.commit()
        cf_id = cf.id

        _update_project_custom_files_status(self.db, project.project_id, "synced_with_github", only_if_status="under_review")

        assert self.db.query(CustomFile).filter_by(id=cf_id).first() is None

    def test_non_pending_and_pending_in_same_project_mixed_correctly(self):
        from workflows import _update_project_custom_files_status
        project = self._seed()
        keep = CustomFile(
            project_id=project.project_id, file_path="keep.yml",
            file_content="x", file_status="under_review", git_hash="a" * 40, pending_delete=False,
        )
        remove = CustomFile(
            project_id=project.project_id, file_path="remove.yml",
            file_content="y", file_status="under_review", git_hash="b" * 40, pending_delete=True,
        )
        self.db.add_all([keep, remove])
        self.db.commit()
        keep_id, remove_id = keep.id, remove.id

        _update_project_custom_files_status(self.db, project.project_id, "synced_with_github", only_if_status="under_review")

        assert self.db.query(CustomFile).filter_by(id=keep_id).first() is not None
        assert self.db.query(CustomFile).filter_by(id=remove_id).first() is None

    def test_project_get_endpoint_returns_custom_files_after_merge(self):
        """The GET /api/projects/{name} response must include custom_files so the
        frontend loadProjectFromAPI call populates the component after merge."""
        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        project = self._seed()
        cf = CustomFile(
            project_id=project.project_id,
            file_path="sonar-project.properties",
            file_content="sonar.projectKey=myapp",
            file_status="synced_with_github",
            git_hash="c" * 40,
            pending_delete=False,
        )
        self.db.add(cf)
        self.db.commit()

        resp = client.get(
            "/api/projects/b2_project",
            params={"github_user": "b2_user"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "custom_files" in data, "project GET must include custom_files key"
        assert len(data["custom_files"]) == 1
        assert data["custom_files"][0]["file_path"] == "sonar-project.properties"
        assert data["custom_files"][0]["file_status"] == "synced_with_github"

        app.dependency_overrides.pop(get_db, None)
