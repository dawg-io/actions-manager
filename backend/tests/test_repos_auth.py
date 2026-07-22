"""
Regression tests for /api/repos auth behaviour.

Verifies that:
- The endpoint requires a valid session cookie (returns 401 otherwise).
- An authenticated user with a token in user_tokens gets their repos.
- A missing/invalid token for an otherwise authenticated user returns 401.
- GitHub API failures are surfaced cleanly without stack traces.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import Base
from repos import get_db

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

FAKE_TOKEN = "ghp_test_token"


def _github_page(repos, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = repos
    return resp


class TestReposAuth:
    def test_no_session_returns_401(self):
        """No session cookie → 401 Authentication required."""
        resp = client.get("/api/repos", params={"user": "testuser"})
        assert resp.status_code == 401
        assert "authentication" in resp.json()["detail"].lower()

    @patch("repos._assert_session_owns_user")
    @patch("repos.github_get")
    @patch("repos._should_restrict_to_public_repos", return_value=False)
    @patch.dict("repos.user_tokens", {"testuser": FAKE_TOKEN})
    def test_authenticated_user_receives_repos(self, _restrict, mock_get, _auth):
        """Valid session + token → repos returned from GitHub."""
        mock_get.return_value = _github_page([
            {
                "id": 1,
                "name": "repo1",
                "full_name": "testuser/repo1",
                "private": False,
                "owner": {"login": "testuser", "type": "User"},
            }
        ])

        resp = client.get("/api/repos", params={"user": "testuser"})

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(r["name"] == "repo1" for r in data)

    @patch("repos._assert_session_owns_user")
    def test_missing_token_returns_401(self, _auth):
        """Session present but no GitHub token in user_tokens → 401."""
        with patch.dict("repos.user_tokens", {}, clear=True):
            resp = client.get("/api/repos", params={"user": "testuser"})
        assert resp.status_code == 401

    @patch("repos._assert_session_owns_user")
    @patch("repos.github_get")
    @patch("repos._should_restrict_to_public_repos", return_value=False)
    @patch.dict("repos.user_tokens", {"testuser": FAKE_TOKEN})
    def test_github_api_failure_returns_error_payload(self, _restrict, mock_get, _auth):
        """GitHub API non-200 → error payload, not a 500 stack trace."""
        mock_get.return_value = _github_page([], status=502)

        resp = client.get("/api/repos", params={"user": "testuser"})

        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body

    @patch("repos._assert_session_owns_user")
    @patch("repos.github_get")
    @patch("repos._should_restrict_to_public_repos", return_value=True)
    @patch.dict("repos.user_tokens", {"testuser": FAKE_TOKEN})
    def test_free_tier_filters_private_repos(self, _restrict, mock_get, _auth):
        """Free-tier restriction removes private repos from the response."""
        mock_get.return_value = _github_page([
            {"id": 1, "name": "pub", "full_name": "testuser/pub", "private": False, "owner": {"login": "testuser", "type": "User"}},
            {"id": 2, "name": "priv", "full_name": "testuser/priv", "private": True, "owner": {"login": "testuser", "type": "User"}},
        ])

        resp = client.get("/api/repos", params={"user": "testuser"})

        assert resp.status_code == 200
        names = [r["name"] for r in resp.json()]
        assert "pub" in names
        assert "priv" not in names
