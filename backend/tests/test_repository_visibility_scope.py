"""
Tests for project repository_visibility_scope functionality.

Covers:
- Creating a public-scope project (any tier)
- Creating a private-scope project on Professional / Enterprise tiers
- Rejecting private-scope project creation on Free tier
- Rejecting invalid repository_visibility_scope values
- Default behavior preserves existing projects (defaults to "public")
- Visibility scope is exposed in GET responses
"""
import os
import sys
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Base, Account, Project  # noqa: E402
from main import app  # noqa: E402
from projects import get_db  # noqa: E402

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_project_visibility_scope.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestRepositoryVisibilityScope:
    """Tests for the per-project repository_visibility_scope setting."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        try:
            db.add(Account(github_user="freevisuser", github_email="f@example.com", account_type="free"))
            db.add(Account(github_user="provisuser", github_email="p@example.com", account_type="professional"))
            db.add(Account(github_user="entvisuser", github_email="e@example.com", account_type="enterprise"))
            db.commit()
        finally:
            db.close()

        yield

        Base.metadata.drop_all(bind=engine)
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]

    def setup_method(self):
        self.client = TestClient(app)

    def _payload(self, github_user, name, scope=None):
        body = {
            "github_user": github_user,
            "project_name": name,
            "selected_repos": ["test/repo1"],
            "workflows": [],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "reusable_workflows_enabled": False,
        }
        if scope is not None:
            body["repository_visibility_scope"] = scope
        return body

    def test_default_visibility_is_public(self):
        """Omitting repository_visibility_scope defaults to 'public' (back-compat)."""
        resp = self.client.post("/api/projects/", json=self._payload("freevisuser", "Default Scope"))
        assert resp.status_code == 200, resp.text

        db = TestingSessionLocal()
        try:
            proj = db.query(Project).filter(Project.project_name == "Default Scope").first()
            assert proj is not None
            assert proj.repository_visibility_scope == "public"
        finally:
            db.close()

    def test_free_user_can_create_public_project(self):
        resp = self.client.post(
            "/api/projects/",
            json=self._payload("freevisuser", "Free Public", scope="public"),
        )
        assert resp.status_code == 200, resp.text

    def test_free_user_blocked_from_private_project(self):
        resp = self.client.post(
            "/api/projects/",
            json=self._payload("freevisuser", "Free Private", scope="private"),
        )
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert "Free" in body["detail"]
        assert "Professional" in body["detail"] or "Enterprise" in body["detail"]

    def test_professional_user_can_create_private_project(self):
        with patch("tier_service.INSTALLATION_MODE", "cloud"):
            resp = self.client.post(
                "/api/projects/",
                json=self._payload("provisuser", "Pro Private", scope="private"),
            )
        assert resp.status_code == 200, resp.text

        db = TestingSessionLocal()
        try:
            proj = db.query(Project).filter(Project.project_name == "Pro Private").first()
            assert proj is not None
            assert proj.repository_visibility_scope == "private"
        finally:
            db.close()

    def test_enterprise_user_can_create_private_project(self):
        with patch("tier_service.INSTALLATION_MODE", "cloud"):
            resp = self.client.post(
                "/api/projects/",
                json=self._payload("entvisuser", "Ent Private", scope="private"),
            )
        assert resp.status_code == 200, resp.text

    def test_invalid_scope_rejected(self):
        """Schema validator rejects values other than 'public'/'private'."""
        with patch("tier_service.INSTALLATION_MODE", "cloud"):
            resp = self.client.post(
                "/api/projects/",
                json=self._payload("provisuser", "Bad Scope", scope="mixed"),
            )
        assert resp.status_code == 422, resp.text

    def test_scope_normalized_case(self):
        with patch("tier_service.INSTALLATION_MODE", "cloud"):
            resp = self.client.post(
                "/api/projects/",
                json=self._payload("provisuser", "Cased Scope", scope="PRIVATE"),
            )
        assert resp.status_code == 200, resp.text
        db = TestingSessionLocal()
        try:
            proj = db.query(Project).filter(Project.project_name == "Cased Scope").first()
            assert proj.repository_visibility_scope == "private"
        finally:
            db.close()

    def test_get_projects_includes_visibility_scope(self):
        with patch("tier_service.INSTALLATION_MODE", "cloud"):
            self.client.post(
                "/api/projects/",
                json=self._payload("provisuser", "Listed Project", scope="private"),
            )
        resp = self.client.get("/api/projects/?github_user=provisuser")
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert any(
            p.get("project_name") == "Listed Project"
            and p.get("repository_visibility_scope") == "private"
            for p in items
        )

    def test_update_without_visibility_scope_preserves_existing_private_scope(self):
        """Legacy update callers that omit the scope must not flip private projects to public."""
        with patch("tier_service.INSTALLATION_MODE", "cloud"):
            create_resp = self.client.post(
                "/api/projects/",
                json=self._payload("provisuser", "Private Update Preserve", scope="private"),
            )
        assert create_resp.status_code == 200, create_resp.text

        project_id = create_resp.json()["project_id"]
        update_resp = self.client.put(
            f"/api/projects/{project_id}/",
            json=self._payload("provisuser", "Private Update Preserve"),
        )
        assert update_resp.status_code == 200, update_resp.text

        db = TestingSessionLocal()
        try:
            proj = db.query(Project).filter(Project.project_name == "Private Update Preserve").first()
            assert proj is not None
            assert proj.repository_visibility_scope == "private"
        finally:
            db.close()

    def test_existing_project_without_scope_defaults_to_public(self):
        """Pre-migration projects (NULL scope) surface as 'public' in API."""
        from sqlalchemy import text

        db = TestingSessionLocal()
        try:
            owner = db.query(Account).filter(Account.github_user == "provisuser").first()
            legacy = Project(
                project_name="Legacy Project",
                project_code="LEG1",
                user_id=owner.user_id,
            )
            db.add(legacy)
            db.commit()

            # The model declares this column NOT NULL, so a plain insert (or a
            # direct UPDATE ... = NULL) would be rejected by SQLite. To
            # faithfully simulate a row predating the migration — where the
            # column was either missing or NULL and the API back-compat
            # fallback is what surfaces "public" — temporarily relax the
            # NOT NULL constraint via SQLite's writable_schema trick, then
            # NULL out the value. The schema change is scoped to this test
            # because the fixture runs `Base.metadata.drop_all` on teardown.
            db.execute(text("PRAGMA writable_schema = ON"))
            db.execute(
                text(
                    "UPDATE sqlite_master "
                    "SET sql = REPLACE(sql, "
                    "  'repository_visibility_scope VARCHAR(10) NOT NULL', "
                    "  'repository_visibility_scope VARCHAR(10)') "
                    "WHERE type = 'table' AND name = 'projects'"
                )
            )
            db.execute(text("PRAGMA writable_schema = OFF"))
            db.commit()
            db.close()

            # Dispose pooled connections so subsequent ones re-read the
            # (now-relaxed) schema rather than using a cached version.
            engine.dispose()

            # New session so the relaxed schema is picked up.
            db = TestingSessionLocal()
            db.execute(
                text(
                    "UPDATE projects SET repository_visibility_scope = NULL "
                    "WHERE project_name = :name"
                ),
                {"name": "Legacy Project"},
            )
            db.commit()

            # Sanity check: the row really is NULL in the DB.
            stored = db.execute(
                text(
                    "SELECT repository_visibility_scope FROM projects "
                    "WHERE project_name = :name"
                ),
                {"name": "Legacy Project"},
            ).scalar()
            assert stored is None
        finally:
            db.close()

        resp = self.client.get("/api/projects/?github_user=provisuser")
        assert resp.status_code == 200
        items = resp.json()
        legacy = next(p for p in items if p["project_name"] == "Legacy Project")
        assert legacy["repository_visibility_scope"] == "public"
