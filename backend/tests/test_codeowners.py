"""
Tests for the CODEOWNERS management endpoints in ``backend/codeowners.py``.

Covers:
- Authentication (401 when no token)
- Project / repo lookup (404 on bad ids)
- Saving a draft persists into the ``codeowners`` table
- Drift detection across the four cases (synced, content_mismatch,
  missing_locally, missing_on_github)
- Deploy in direct mode commits via the GitHub Contents API and updates
  the local ``git_hash`` and ``status``
"""

import os
import sys
import base64
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, Repo, ProjectRepo, Codeowners, ProjectPullRequest  # noqa: E402
from main import app  # noqa: E402
from codeowners import get_db  # noqa: E402


SQLALCHEMY_DATABASE_URL = "sqlite:///./test_codeowners.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)

TEST_USER = "co_user"
TEST_PROJECT = "co_project"
TEST_REPO = "octo/repo"


def _seed(db):
    account = Account(
        github_user=TEST_USER,
        github_email="co@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_name=TEST_PROJECT,
        project_code="COX",
        user_id=account.user_id,
        branch_option="default",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    repo = Repo(repo_name=TEST_REPO)
    db.add(repo)
    db.commit()
    db.refresh(repo)

    db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
    db.commit()

    return account, project, repo


class TestCodeowners:

    @pytest.fixture(autouse=True)
    def setup_db(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    # ------------------------------------------------------------------
    # Authentication / lookup
    # ------------------------------------------------------------------

    def test_get_unauthenticated_returns_401(self):
        _, _, repo = _seed(self.db)
        response = client.get(
            f"/api/repos/{repo.repo_id}/codeowners",
            params={"github_user": "nobody", "project_name": TEST_PROJECT},
        )
        assert response.status_code == 401

    def test_get_unknown_project_returns_404(self):
        _, _, repo = _seed(self.db)
        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                f"/api/repos/{repo.repo_id}/codeowners",
                params={"github_user": TEST_USER, "project_name": "missing"},
            )
        assert response.status_code == 404

    def test_get_repo_not_in_project_returns_404(self):
        _, _, _ = _seed(self.db)
        # Create a different repo not linked to project
        orphan = Repo(repo_name="other/orphan")
        self.db.add(orphan)
        self.db.commit()
        self.db.refresh(orphan)

        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                f"/api/repos/{orphan.repo_id}/codeowners",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.status_code == 404

    # ------------------------------------------------------------------
    # GET — fetch from GitHub
    # ------------------------------------------------------------------

    def test_get_returns_github_content_when_present(self):
        _, _, repo = _seed(self.db)

        def fake_get(url, headers=None, timeout=None):
            mock = MagicMock()
            if url.endswith("/.github/CODEOWNERS"):
                mock.status_code = 200
                # base64 of "* @octo/owners\n"

                mock.json.return_value = {
                    "content": base64.b64encode(b"* @octo/owners\n").decode(),
                    "sha": "deadbeef",
                }
            elif url.endswith("/CODEOWNERS"):
                mock.status_code = 404
            else:
                mock.status_code = 200
                mock.json.return_value = {"default_branch": "main"}
            return mock

        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}), \
                patch("codeowners.requests.get", side_effect=fake_get):
            response = client.get(
                f"/api/repos/{repo.repo_id}/codeowners",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["github"]["exists"] is True
        assert data["github"]["content"] == "* @octo/owners\n"
        assert data["github"]["sha"] == "deadbeef"
        assert data["github"]["path"] == ".github/CODEOWNERS"
        assert data["local"] is None

    # ------------------------------------------------------------------
    # POST — save draft
    # ------------------------------------------------------------------

    def test_save_draft_creates_record(self):
        _, project, repo = _seed(self.db)
        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}):
            response = client.post(
                f"/api/repos/{repo.repo_id}/codeowners",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "content": "* @octo/owners\n",
                    "file_path": ".github/CODEOWNERS",
                },
                headers={"X-GitHub-User": TEST_USER},
            )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["codeowners"]["content"] == "* @octo/owners\n"
        assert data["codeowners"]["status"] == "committed_locally"
        assert data["codeowners"]["last_modified_by"] == TEST_USER

        record = (
            self.db.query(Codeowners)
            .filter_by(project_id=project.project_id, repo_id=repo.repo_id)
            .first()
        )
        assert record is not None
        assert record.content == "* @octo/owners\n"

    def test_save_draft_supports_repo_name_in_url(self):
        """Endpoints accept either numeric repo_id or full owner/repo path."""
        _, project, repo = _seed(self.db)
        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}):
            response = client.post(
                f"/api/repos/{TEST_REPO}/codeowners",  # 'octo/repo'
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "content": "* @x\n",
                },
                headers={"X-GitHub-User": TEST_USER},
            )
        assert response.status_code == 200, response.text
        record = (
            self.db.query(Codeowners)
            .filter_by(project_id=project.project_id, repo_id=repo.repo_id)
            .first()
        )
        assert record is not None
        assert record.content == "* @x\n"

    def test_save_draft_rejects_invalid_path(self):
        _, _, repo = _seed(self.db)
        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}):
            response = client.post(
                f"/api/repos/{repo.repo_id}/codeowners",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "content": "* @octo/owners\n",
                    "file_path": "docs/CODEOWNERS",
                },
                headers={"X-GitHub-User": TEST_USER},
            )
        assert response.status_code == 400

    def test_save_draft_returns_validation_warnings(self):
        _, _, repo = _seed(self.db)
        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}):
            response = client.post(
                f"/api/repos/{repo.repo_id}/codeowners",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "content": "* notanowner\n/docs/ \n",
                },
                headers={"X-GitHub-User": TEST_USER},
            )
        assert response.status_code == 200
        warnings = response.json()["validation_warnings"]
        assert len(warnings) >= 2

    # ------------------------------------------------------------------
    # GET drift
    # ------------------------------------------------------------------

    def test_drift_synced_when_local_matches_github(self):
        _, project, repo = _seed(self.db)
        self.db.add(Codeowners(
            project_id=project.project_id,
            repo_id=repo.repo_id,
            content="* @octo/owners\n",
            file_path=".github/CODEOWNERS",
            status="synced_with_github",
        ))
        self.db.commit()

        def fake_get(url, headers=None, timeout=None):
            mock = MagicMock()
            if url.endswith("/.github/CODEOWNERS"):
                mock.status_code = 200

                mock.json.return_value = {
                    "content": base64.b64encode(b"* @octo/owners\n").decode(),
                    "sha": "abc123",
                }
            else:
                mock.status_code = 404
            return mock

        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}), \
                patch("codeowners.requests.get", side_effect=fake_get):
            response = client.get(
                f"/api/repos/{repo.repo_id}/codeowners/drift",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["drift_status"] == "synced"
        assert data["has_drift"] is False

    def test_drift_content_mismatch(self):
        _, project, repo = _seed(self.db)
        self.db.add(Codeowners(
            project_id=project.project_id,
            repo_id=repo.repo_id,
            content="* @octo/local-owners\n",
            file_path=".github/CODEOWNERS",
            status="committed_locally",
        ))
        self.db.commit()

        def fake_get(url, headers=None, timeout=None):
            mock = MagicMock()
            if url.endswith("/.github/CODEOWNERS"):
                mock.status_code = 200

                mock.json.return_value = {
                    "content": base64.b64encode(b"* @octo/remote-owners\n").decode(),
                    "sha": "abc123",
                }
            else:
                mock.status_code = 404
            return mock

        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}), \
                patch("codeowners.requests.get", side_effect=fake_get):
            response = client.get(
                f"/api/repos/{repo.repo_id}/codeowners/drift",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.json()["drift_status"] == "content_mismatch"
        assert response.json()["has_drift"] is True

    def test_drift_missing_on_github(self):
        _, project, repo = _seed(self.db)
        self.db.add(Codeowners(
            project_id=project.project_id,
            repo_id=repo.repo_id,
            content="* @x\n",
            file_path=".github/CODEOWNERS",
            status="committed_locally",
        ))
        self.db.commit()

        def fake_get(url, headers=None, timeout=None):
            mock = MagicMock()
            mock.status_code = 404
            return mock

        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}), \
                patch("codeowners.requests.get", side_effect=fake_get):
            response = client.get(
                f"/api/repos/{repo.repo_id}/codeowners/drift",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.json()["drift_status"] == "missing_on_github"

    def test_drift_missing_locally(self):
        _, _, repo = _seed(self.db)

        def fake_get(url, headers=None, timeout=None):
            mock = MagicMock()
            if url.endswith("/.github/CODEOWNERS"):
                mock.status_code = 200

                mock.json.return_value = {
                    "content": base64.b64encode(b"* @x\n").decode(),
                    "sha": "abc",
                }
            else:
                mock.status_code = 404
            return mock

        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}), \
                patch("codeowners.requests.get", side_effect=fake_get):
            response = client.get(
                f"/api/repos/{repo.repo_id}/codeowners/drift",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.json()["drift_status"] == "missing_locally"
        assert response.json()["has_drift"] is True

    # ------------------------------------------------------------------
    # POST deploy
    # ------------------------------------------------------------------

    def test_deploy_direct_commits_to_github_and_updates_local(self):
        _, project, repo = _seed(self.db)

        # Pre-existing draft
        self.db.add(Codeowners(
            project_id=project.project_id,
            repo_id=repo.repo_id,
            content="* @octo/owners\n",
            file_path=".github/CODEOWNERS",
            status="committed_locally",
        ))
        self.db.commit()

        def fake_get(url, headers=None, timeout=None):
            mock = MagicMock()
            if url.endswith(f"/repos/octo/repo"):
                mock.status_code = 200
                mock.json.return_value = {"default_branch": "main"}
            else:
                # File doesn't exist on GitHub yet
                mock.status_code = 404
            return mock

        def fake_put(url, headers=None, json=None, timeout=None):
            mock = MagicMock()
            mock.status_code = 201
            mock.json.return_value = {"content": {"sha": "newsha123"}}
            return mock

        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}), \
                patch("codeowners.requests.get", side_effect=fake_get), \
                patch("codeowners.requests.put", side_effect=fake_put):
            response = client.post(
                f"/api/repos/{repo.repo_id}/codeowners/deploy",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "mode": "direct",
                },
                headers={"X-GitHub-User": TEST_USER},
            )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["mode"] == "direct"
        assert data["branch"] == "main"
        assert data["git_hash"] == "newsha123"
        assert data["pull_request"] is None

        record = (
            self.db.query(Codeowners)
            .filter_by(project_id=project.project_id, repo_id=repo.repo_id)
            .first()
        )
        assert record.git_hash == "newsha123"
        assert record.status == "synced_with_github"

    def test_deploy_rejects_invalid_mode(self):
        _, _, repo = _seed(self.db)
        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}):
            response = client.post(
                f"/api/repos/{repo.repo_id}/codeowners/deploy",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "mode": "invalid",
                },
                headers={"X-GitHub-User": TEST_USER},
            )
        assert response.status_code == 400

    def test_deploy_without_content_or_draft_returns_400(self):
        _, _, repo = _seed(self.db)
        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}):
            response = client.post(
                f"/api/repos/{repo.repo_id}/codeowners/deploy",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "mode": "direct",
                },
                headers={"X-GitHub-User": TEST_USER},
            )
        assert response.status_code == 400

    def test_deploy_pr_mode_creates_pull_request_tracking_entry(self):
        """Verify that CODEOWNERS PRs are tracked in ProjectPullRequest table."""
        account, project, repo = _seed(self.db)

        # Save a draft first
        draft = Codeowners(
            project_id=project.project_id,
            repo_id=repo.repo_id,
            content="* @owner\n",
            file_path=".github/CODEOWNERS",
            status="committed_locally",
            last_modified_by=TEST_USER,
        )
        self.db.add(draft)
        self.db.commit()

        # Mock GitHub API calls
        def fake_get(url, headers=None, timeout=None, params=None):
            mock = MagicMock()
            # Default branch lookup
            if "/repos/" in url and url.endswith("/branches/main"):
                mock.status_code = 200
                mock.json.return_value = {"name": "main", "commit": {"sha": "basesha"}}
            # Base branch ref lookup for creating new branch
            elif "/git/refs/heads/main" in url:
                mock.status_code = 200
                mock.json.return_value = {"object": {"sha": "basesha"}}
            # Check if branch exists (actions-manager/codeowners-COX)
            elif "/git/refs/heads/actions-manager/codeowners-" in url:
                mock.status_code = 404  # Branch doesn't exist yet
            # Check existing file
            elif "/contents/.github/CODEOWNERS" in url:
                mock.status_code = 404  # File doesn't exist
            else:
                mock.status_code = 404
            return mock

        def fake_post(url, headers=None, json=None, timeout=None):
            mock = MagicMock()
            # Create branch
            if "/git/refs" in url and "/pulls" not in url:
                mock.status_code = 201
                mock.json.return_value = {"ref": "refs/heads/actions-manager/codeowners-COX"}
            # Create PR
            elif "/pulls" in url:
                mock.status_code = 201
                mock.json.return_value = {
                    "number": 42,
                    "html_url": "https://github.com/octo/repo/pull/42",
                    "title": "[Actions Manager] Update .github/CODEOWNERS",
                    "user": {"login": TEST_USER},
                    "body": "Automated update of `.github/CODEOWNERS` from project **co_project** (COX).",
                }
            else:
                mock.status_code = 404
            return mock

        def fake_put(url, headers=None, json=None, timeout=None):
            mock = MagicMock()
            mock.status_code = 201
            mock.json.return_value = {"content": {"sha": "prsha456"}}
            return mock

        with patch("codeowners.user_tokens", {TEST_USER: "fake-token"}), \
                patch("codeowners.requests.get", side_effect=fake_get), \
                patch("codeowners.requests.post", side_effect=fake_post), \
                patch("codeowners.requests.put", side_effect=fake_put):
            response = client.post(
                f"/api/repos/{repo.repo_id}/codeowners/deploy",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "mode": "pr",
                },
                headers={"X-GitHub-User": TEST_USER},
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["mode"] == "pr"
        assert data["pull_request"]["number"] == 42
        assert data["pull_request"]["url"] == "https://github.com/octo/repo/pull/42"

        # Verify PR tracking entry was created
        pr_entry = (
            self.db.query(ProjectPullRequest)
            .filter_by(
                project_id=project.project_id,
                repo_name=repo.repo_name,
                pr_number=42,
            )
            .first()
        )
        assert pr_entry is not None, "ProjectPullRequest entry should be created"
        assert pr_entry.pr_state == "open"
        assert pr_entry.pr_url == "https://github.com/octo/repo/pull/42"
        assert pr_entry.branch_name == "actions-manager/codeowners-COX"
        assert pr_entry.target_branch == "main"
        assert pr_entry.workflow_names == "CODEOWNERS"
        assert pr_entry.title == "[Actions Manager] Update .github/CODEOWNERS"
        assert pr_entry.author == TEST_USER

