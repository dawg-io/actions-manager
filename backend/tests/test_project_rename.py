"""
Tests for PATCH /projects/{id}/project-name — rename-only endpoint.

Verifies that project_name persists and project_code remains unchanged.
Regression coverage for GitHub issue #1570.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Account, Base, Project  # noqa: E402
from main import app  # noqa: E402
from projects import get_db  # noqa: E402

engine = create_engine(
    "sqlite:///:memory:",
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


class TestProjectRename:
    @pytest.fixture(autouse=True)
    def setup_database(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        try:
            db.add(Account(github_user="renameuser", github_email="r@example.com", account_type="free"))
            db.commit()
        finally:
            db.close()

        yield

        Base.metadata.drop_all(bind=engine)
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]

    def setup_method(self):
        self.client = TestClient(app)

    def _create_project(self, name: str = "Original Name") -> dict:
        payload = {
            "github_user": "renameuser",
            "project_name": name,
            "selected_repos": ["owner/repo1"],
            "workflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": False,
        }
        resp = self.client.post("/api/projects/", json=payload)
        assert resp.status_code == 200, resp.text
        return resp.json()

    def test_rename_succeeds_and_project_code_unchanged(self):
        created = self._create_project("My Project")
        project_id = created["project_id"]
        original_code = created["project_code"]

        resp = self.client.patch(
            f"/api/projects/{project_id}/project-name",
            json={"github_user": "renameuser", "project_name": "Renamed Project"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["project_name"] == "Renamed Project"
        assert data["project_code"] == original_code

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project is not None
            assert project.project_name == "Renamed Project"
            assert project.project_code == original_code
        finally:
            db.close()

    def test_rename_trims_whitespace(self):
        created = self._create_project()
        project_id = created["project_id"]

        resp = self.client.patch(
            f"/api/projects/{project_id}/project-name",
            json={"github_user": "renameuser", "project_name": "  Trimmed Name  "},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["project_name"] == "Trimmed Name"

    def test_rename_empty_name_rejected(self):
        created = self._create_project()
        project_id = created["project_id"]

        resp = self.client.patch(
            f"/api/projects/{project_id}/project-name",
            json={"github_user": "renameuser", "project_name": "   "},
        )
        assert resp.status_code == 422, resp.text

    def test_rename_nonexistent_project_returns_404(self):
        resp = self.client.patch(
            "/api/projects/99999/project-name",
            json={"github_user": "renameuser", "project_name": "New Name"},
        )
        assert resp.status_code == 404, resp.text
