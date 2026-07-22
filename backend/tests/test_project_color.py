"""
Tests for project_color field in project creation, update, and listing.

project_color is a user-selected identity color key used as a decorative accent
on project cards. It must be validated against a fixed allowlist.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Account, Base, Project, ProjectMembership, WorkspaceMember  # noqa: E402
from main import app  # noqa: E402
from projects import get_db  # noqa: E402

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_project_color.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestProjectColor:
    @pytest.fixture(autouse=True)
    def setup_database(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        try:
            db.add(Account(github_user="coloruser", github_email="c@example.com", account_type="free"))
            db.commit()
        finally:
            db.close()

        yield

        Base.metadata.drop_all(bind=engine)
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]

    def setup_method(self):
        self.client = TestClient(app)

    def _payload(self, name: str, color: str | None = None, include_color: bool = True, project_type: str = "standard"):
        body = {
            "github_user": "coloruser",
            "project_name": name,
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False,
            "project_type": project_type,
        }
        if include_color:
            body["project_color"] = color
        return body

    def test_create_project_with_valid_project_color_succeeds(self):
        resp = self.client.post("/api/projects/", json=self._payload("Amber Project", "amber"))
        assert resp.status_code == 200, resp.text

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "Amber Project").first()
            assert project is not None
            assert project.project_color == "amber"
        finally:
            db.close()

    def test_create_project_with_invalid_project_color_fails_validation(self):
        resp = self.client.post("/api/projects/", json=self._payload("Bad Color", "magenta"))
        assert resp.status_code == 422, resp.text

    def test_create_project_without_project_color_succeeds(self):
        resp = self.client.post("/api/projects/", json=self._payload("No Color", include_color=False))
        assert resp.status_code == 200, resp.text

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "No Color").first()
            assert project is not None
            assert project.project_color is None
        finally:
            db.close()

    def test_project_list_includes_project_color(self):
        self.client.post("/api/projects/", json=self._payload("List Color", "cyan"))
        self.client.post("/api/projects/", json=self._payload("List Null", include_color=False))

        resp = self.client.get("/api/projects/?github_user=coloruser")
        assert resp.status_code == 200, resp.text
        items = resp.json()

        assert any(p.get("project_name") == "List Color" and p.get("project_color") == "cyan" for p in items)
        assert any(p.get("project_name") == "List Null" and p.get("project_color") is None for p in items)

    def test_update_project_color_works(self):
        create_resp = self.client.post("/api/projects/", json=self._payload("Update Color", "blue"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]

        update_resp = self.client.put(
            f"/api/projects/{project_id}/",
            json=self._payload("Update Color", "rose"),
        )
        assert update_resp.status_code == 200, update_resp.text

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project is not None
            assert project.project_color == "rose"
        finally:
            db.close()

    def test_update_without_project_color_preserves_existing_color(self):
        create_resp = self.client.post("/api/projects/", json=self._payload("Preserve Color", "slate"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]

        update_resp = self.client.put(
            f"/api/projects/{project_id}/",
            json=self._payload("Preserve Color", include_color=False),
        )
        assert update_resp.status_code == 200, update_resp.text

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project is not None
            assert project.project_color == "slate"
        finally:
            db.close()

    def test_patch_project_color_saves_without_full_project_payload(self):
        create_resp = self.client.post("/api/projects/", json=self._payload("Patch Color", "blue"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]

        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            json={"github_user": "coloruser", "project_color": "orange"},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert patch_resp.json().get("project_color") == "orange"

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project is not None
            assert project.project_color == "orange"
        finally:
            db.close()

    def test_patch_project_color_rejects_invalid_values(self):
        create_resp = self.client.post("/api/projects/", json=self._payload("Patch Bad Color", "blue"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]

        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            json={"github_user": "coloruser", "project_color": "magenta"},
        )
        assert patch_resp.status_code == 422, patch_resp.text

    def _set_color_directly(self, project_id: int, color: str) -> None:
        """Simulate a pre-restriction row by writing the color straight to the DB."""
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            project.project_color = color
            db.commit()
        finally:
            db.close()

    def _get_color(self, project_id: int) -> str | None:
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            return project.project_color
        finally:
            db.close()

    def test_create_standard_project_with_rwx_only_color_fails(self):
        for color in ("purple", "green"):
            resp = self.client.post("/api/projects/", json=self._payload(f"Std {color}", color))
            assert resp.status_code == 422, resp.text
            assert "Reusable Workflow Projects" in resp.json()["detail"]

    def test_create_rwx_project_with_rwx_only_color_succeeds(self):
        resp = self.client.post(
            "/api/projects/", json=self._payload("RWX Purple", "purple", project_type="rwx")
        )
        assert resp.status_code == 200, resp.text

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_name == "RWX Purple").first()
            assert project is not None
            assert project.project_type == "rwx"
            assert project.project_color == "purple"
        finally:
            db.close()

    def test_update_standard_project_to_rwx_only_color_fails(self):
        create_resp = self.client.post("/api/projects/", json=self._payload("Std To Purple", "blue"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]

        update_resp = self.client.put(
            f"/api/projects/{project_id}/",
            json=self._payload("Std To Purple", "purple"),
        )
        assert update_resp.status_code == 422, update_resp.text
        assert self._get_color(project_id) == "blue"

    def test_patch_standard_project_to_rwx_only_color_fails(self):
        create_resp = self.client.post("/api/projects/", json=self._payload("Std Patch Purple", "blue"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]

        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            json={"github_user": "coloruser", "project_color": "green"},
        )
        assert patch_resp.status_code == 422, patch_resp.text
        assert self._get_color(project_id) == "blue"

    def test_patch_rwx_project_to_rwx_only_color_succeeds(self):
        create_resp = self.client.post(
            "/api/projects/", json=self._payload("RWX Patch Green", "purple", project_type="rwx")
        )
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]

        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            json={"github_user": "coloruser", "project_color": "green"},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert self._get_color(project_id) == "green"

    def test_create_rwx_project_with_standard_color_fails(self):
        for color in ("blue", "amber", "rose", "cyan", "slate", "orange", "sky"):
            resp = self.client.post(
                "/api/projects/", json=self._payload(f"RWX {color}", color, project_type="rwx")
            )
            assert resp.status_code == 422, f"Expected 422 for color '{color}', got {resp.status_code}"
            assert "Reusable Workflow Projects" in resp.json()["detail"]

    def test_patch_rwx_project_to_standard_color_fails(self):
        create_resp = self.client.post(
            "/api/projects/", json=self._payload("RWX Reject Blue", "purple", project_type="rwx")
        )
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]

        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            json={"github_user": "coloruser", "project_color": "blue"},
        )
        assert patch_resp.status_code == 422, patch_resp.text
        assert self._get_color(project_id) == "purple"

    def test_grandfathered_standard_project_keeps_rwx_only_color(self):
        # A standard project may already have purple/green from before the
        # restriction existed; re-submitting the unchanged color must succeed.
        create_resp = self.client.post("/api/projects/", json=self._payload("Grandfathered", "blue"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]
        self._set_color_directly(project_id, "purple")

        # PUT re-sending the same grandfathered color succeeds
        update_resp = self.client.put(
            f"/api/projects/{project_id}/",
            json=self._payload("Grandfathered", "purple"),
        )
        assert update_resp.status_code == 200, update_resp.text
        assert self._get_color(project_id) == "purple"

        # PUT omitting the color leaves it untouched
        update_resp = self.client.put(
            f"/api/projects/{project_id}/",
            json=self._payload("Grandfathered", include_color=False),
        )
        assert update_resp.status_code == 200, update_resp.text
        assert self._get_color(project_id) == "purple"

        # But changing to a different RWX-only color is still rejected
        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            json={"github_user": "coloruser", "project_color": "green"},
        )
        assert patch_resp.status_code == 422, patch_resp.text
        assert self._get_color(project_id) == "purple"

    def test_grandfathered_rwx_project_keeps_standard_color(self):
        # An RWX project may already have blue/amber/etc. from before the
        # restriction existed; re-submitting the unchanged color must succeed.
        create_resp = self.client.post(
            "/api/projects/", json=self._payload("RWX Grandfathered", "purple", project_type="rwx")
        )
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]
        self._set_color_directly(project_id, "blue")

        # PATCH re-sending the same grandfathered color succeeds
        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            json={"github_user": "coloruser", "project_color": "blue"},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert self._get_color(project_id) == "blue"

        # But changing to a different standard color is rejected
        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            json={"github_user": "coloruser", "project_color": "amber"},
        )
        assert patch_resp.status_code == 422, patch_resp.text
        assert self._get_color(project_id) == "blue"

    # -----------------------------------------------------------------
    # Authorization: project_viewer must not be able to mutate a project
    # -----------------------------------------------------------------

    def _add_project_viewer(self, project_id: int, github_user: str) -> None:
        """Register *github_user* as a read-only workspace member with an
        explicit ``project_viewer`` membership on *project_id*."""
        db = TestingSessionLocal()
        try:
            viewer = Account(github_user=github_user, github_email=f"{github_user}@example.com", account_type="free")
            db.add(viewer)
            db.commit()
            db.refresh(viewer)
            db.add(WorkspaceMember(user_id=viewer.user_id, workspace_role="read_only"))
            db.add(ProjectMembership(
                user_id=viewer.user_id,
                project_id=project_id,
                project_role="project_viewer",
            ))
            db.commit()
        finally:
            db.close()

    def test_project_viewer_cannot_put_update_project(self):
        create_resp = self.client.post("/api/projects/", json=self._payload("Viewer PUT", "blue"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]
        self._add_project_viewer(project_id, "viewer-put")

        update_resp = self.client.put(
            f"/api/projects/{project_id}/",
            headers={"X-GitHub-User": "viewer-put"},
            json=self._payload("Viewer PUT Renamed", "rose"),
        )
        assert update_resp.status_code == 403, update_resp.text

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter(Project.project_id == project_id).first()
            assert project is not None
            assert project.project_name == "Viewer PUT"
            assert project.project_color == "blue"
        finally:
            db.close()

    def test_project_viewer_cannot_patch_project_color(self):
        create_resp = self.client.post("/api/projects/", json=self._payload("Viewer PATCH", "blue"))
        assert create_resp.status_code == 200, create_resp.text
        project_id = create_resp.json()["project_id"]
        self._add_project_viewer(project_id, "viewer-patch")

        patch_resp = self.client.patch(
            f"/api/projects/{project_id}/project-color",
            headers={"X-GitHub-User": "viewer-patch"},
            json={"github_user": "viewer-patch", "project_color": "orange"},
        )
        assert patch_resp.status_code == 403, patch_resp.text
        assert self._get_color(project_id) == "blue"
