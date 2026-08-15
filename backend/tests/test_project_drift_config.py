"""
Tests for the per-project drift schedule endpoint.

Drift cadence used to be one env var for the whole install. A project can now
opt out entirely or pick its own interval, which is the point of the feature:
a noisy project checked every 15 minutes, an archived one never.

The interval is restricted to the presets the UI offers — a hand-crafted
request setting a 1-minute sweep would burn the install's GitHub rate limit on
every project behind it.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Account, Base, Project, ProjectMembership, WorkspaceMember  # noqa: E402
from main import app  # noqa: E402
from projects import get_db  # noqa: E402

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

OWNER = "driftuser"


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestProjectDriftConfig:
    @pytest.fixture(autouse=True)
    def setup_database(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        try:
            db.add(Account(github_user=OWNER, github_email="d@example.com", account_type="free"))
            db.commit()
        finally:
            db.close()

        yield

        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    def setup_method(self):
        self.client = TestClient(app)

    def _create_project(self, name: str) -> int:
        resp = self.client.post("/api/projects/", json={
            "github_user": OWNER,
            "project_name": name,
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False,
            "project_type": "standard",
        })
        assert resp.status_code == 200, resp.text
        return resp.json()["project_id"]

    def _patch(self, project_id: int, minutes, github_user: str = OWNER, headers=None):
        return self.client.patch(
            f"/api/projects/{project_id}/drift-config",
            headers=headers,
            json={"github_user": github_user, "drift_check_interval_minutes": minutes},
        )

    def _stored_interval(self, project_id: int):
        db = TestingSessionLocal()
        try:
            return db.query(Project).filter(
                Project.project_id == project_id
            ).first().drift_check_interval_minutes
        finally:
            db.close()

    def test_a_new_project_inherits_by_default(self):
        """NULL, not 0 — a project nobody has configured must keep being swept."""
        assert self._stored_interval(self._create_project("Fresh")) is None

    @pytest.mark.parametrize("minutes", [0, 15, 30, 60, 360, 1440])
    def test_every_preset_is_accepted(self, minutes):
        project_id = self._create_project(f"Preset {minutes}")

        resp = self._patch(project_id, minutes)

        assert resp.status_code == 200, resp.text
        assert resp.json()["drift_check_interval_minutes"] == minutes
        assert self._stored_interval(project_id) == minutes

    def test_off_is_stored_as_zero_not_null(self):
        """0 and NULL mean opposite things: never check, versus inherit."""
        project_id = self._create_project("Off")

        self._patch(project_id, 0)

        assert self._stored_interval(project_id) == 0

    def test_null_resets_to_inherit(self):
        project_id = self._create_project("Reset")
        self._patch(project_id, 1440)

        resp = self._patch(project_id, None)

        assert resp.status_code == 200, resp.text
        assert self._stored_interval(project_id) is None

    @pytest.mark.parametrize("minutes", [1, 7, -30, 2, 999999])
    def test_values_outside_the_presets_are_rejected(self, minutes):
        project_id = self._create_project(f"Bad {minutes}")

        resp = self._patch(project_id, minutes)

        assert resp.status_code == 422, resp.text
        assert self._stored_interval(project_id) is None

    def test_the_interval_is_returned_in_the_project_detail(self):
        """The settings control renders from this, so it has to come back."""
        project_id = self._create_project("Detail")
        self._patch(project_id, 30)

        resp = self.client.get("/api/projects/Detail", params={"github_user": OWNER})

        assert resp.status_code == 200, resp.text
        assert resp.json()["drift_check_interval_minutes"] == 30

    def test_an_unknown_project_is_a_404(self):
        assert self._patch(999999, 30).status_code == 404

    def test_a_project_viewer_cannot_change_the_schedule(self):
        project_id = self._create_project("Viewer")
        db = TestingSessionLocal()
        try:
            viewer = Account(github_user="drift-viewer", github_email="v@example.com",
                             account_type="free")
            db.add(viewer)
            db.commit()
            db.refresh(viewer)
            db.add(WorkspaceMember(user_id=viewer.user_id, workspace_role="read_only"))
            db.add(ProjectMembership(user_id=viewer.user_id, project_id=project_id,
                                     project_role="project_viewer"))
            db.commit()
        finally:
            db.close()

        resp = self._patch(project_id, 1440, github_user="drift-viewer",
                           headers={"X-GitHub-User": "drift-viewer"})

        assert resp.status_code == 403, resp.text
        assert self._stored_interval(project_id) is None
