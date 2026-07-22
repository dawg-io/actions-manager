"""
Tests for check_repo_status endpoint, including the org-owner query parameter.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import Base
from repos import get_db

# ---------- test DB wiring ----------
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _db_and_overrides():
    Base.metadata.create_all(bind=engine)

    def _override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)

FAKE_TOKEN = "ghp_fake_token_for_tests"


# ---------- helpers ----------
def _mock_github_response(status_code):
    resp = MagicMock()
    resp.status_code = status_code
    return resp


# ---------- tests ----------
@patch("repos._assert_session_owns_user")
class TestCheckRepoStatusOwner:
    """Verify that the optional `owner` query param changes the GitHub API URL."""

    @patch("repos.github_get")
    @patch.dict("repos.user_tokens", {"testuser": FAKE_TOKEN})
    def test_defaults_to_user_when_no_owner(self, mock_get, _mock_auth):
        """Without ?owner=, the endpoint should query /repos/{user}/{repo}."""
        mock_get.return_value = _mock_github_response(200)

        resp = client.get("/api/repos/status/testuser/my-repo")
        assert resp.status_code == 200
        assert resp.json() == {"exists": True}

        called_url = mock_get.call_args[0][0]
        assert called_url == "https://api.github.com/repos/testuser/my-repo"

    @patch("repos.github_get")
    @patch.dict("repos.user_tokens", {"testuser": FAKE_TOKEN})
    def test_uses_owner_for_org_repo(self, mock_get, _mock_auth):
        """With ?owner=my-org, the endpoint should query /repos/my-org/{repo}."""
        mock_get.return_value = _mock_github_response(200)

        resp = client.get("/api/repos/status/testuser/org-repo?owner=my-org")
        assert resp.status_code == 200
        assert resp.json() == {"exists": True}

        called_url = mock_get.call_args[0][0]
        assert called_url == "https://api.github.com/repos/my-org/org-repo"

    @patch("repos.github_get")
    @patch.dict("repos.user_tokens", {"testuser": FAKE_TOKEN})
    def test_returns_not_found_for_org_repo(self, mock_get, _mock_auth):
        """404 from GitHub should be surfaced as exists=False."""
        mock_get.return_value = _mock_github_response(404)

        resp = client.get("/api/repos/status/testuser/missing?owner=my-org")
        assert resp.status_code == 200
        assert resp.json() == {"exists": False}

    @patch("repos.github_get")
    @patch.dict("repos.user_tokens", {"testuser": FAKE_TOKEN})
    def test_returns_error_for_unexpected_status(self, mock_get, _mock_auth):
        """Non-200/404 status codes should be reported as an error."""
        mock_get.return_value = _mock_github_response(403)

        resp = client.get("/api/repos/status/testuser/restricted?owner=my-org")
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_unauthenticated_user_returns_401(self, _mock_auth):
        """Unrecognised user should get a 401."""
        resp = client.get("/api/repos/status/unknown-user/repo")
        assert resp.status_code == 401
