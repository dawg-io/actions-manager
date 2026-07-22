"""
Tests for no_prefix mode retrieval of secrets and environment variables.
Verifies that the GET endpoints correctly retrieve secrets/vars from database for no_prefix projects.
"""
import pytest
import sys
import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, AsyncMock, MagicMock

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Base, Account, Project, ProjectSecret, ProjectEnvVar
from main import app
from projects import get_db
import github_secrets
import github_env_vars

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_no_prefix_retrieval.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    """Override the database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


class TestNoPrefixRetrieval:
    """Test class for no_prefix secrets and env vars retrieval."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        # Set up database dependency overrides for all modules that define their own get_db
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[github_secrets.get_db] = override_get_db
        app.dependency_overrides[github_env_vars.get_db] = override_get_db

        # Drop any leftover tables from a previous run, then recreate clean
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        # Create test user and project
        db = TestingSessionLocal()
        try:
            test_user = Account(
                github_user="testuser",
                github_email="testuser@example.com",
                account_type="free"
            )
            db.add(test_user)
            db.commit()

            # Create a no_prefix project
            no_prefix_project = Project(
                project_name="No Prefix Test Project",
                project_code="NPTP",
                user_id=test_user.user_id,
                use_prefix=False,
                pr_state="new"
            )
            db.add(no_prefix_project)
            db.commit()

            # Store the project_id for tests
            self.project_id = no_prefix_project.project_id

            # Add test secrets to database
            test_secrets = [
                ProjectSecret(project_id=self.project_id, secret_name="DATABASE_PASSWORD"),
                ProjectSecret(project_id=self.project_id, secret_name="API_KEY"),
                ProjectSecret(project_id=self.project_id, secret_name="JWT_SECRET"),
            ]
            for secret in test_secrets:
                db.add(secret)

            # Add test env vars to database
            test_env_vars = [
                ProjectEnvVar(project_id=self.project_id, env_var_name="DEBUG_MODE"),
                ProjectEnvVar(project_id=self.project_id, env_var_name="LOG_LEVEL"),
                ProjectEnvVar(project_id=self.project_id, env_var_name="ENVIRONMENT"),
            ]
            for env_var in test_env_vars:
                db.add(env_var)

            db.commit()

        finally:
            db.close()

        yield

        # Clean up after test
        Base.metadata.drop_all(bind=engine)
        # Clean up all dependency overrides added during setup
        for dep in [get_db, github_secrets.get_db, github_env_vars.get_db]:
            if dep in app.dependency_overrides:
                del app.dependency_overrides[dep]

    def setup_method(self):
        """Set up test client"""
        self.client = TestClient(app)

    @patch('github_secrets.user_tokens', {'testuser': 'mock_token'})
    @patch('github_secrets.httpx.AsyncClient')
    def test_get_secrets_no_prefix_mode(self, mock_async_client):
        """Test that get_secrets retrieves secrets from database for no_prefix projects."""
        # Mock GitHub API response with all secrets (including ones not in DB)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "secrets": [
                {"name": "DATABASE_PASSWORD"},
                {"name": "API_KEY"},
                {"name": "JWT_SECRET"},
                {"name": "OTHER_SECRET"},  # Not in database
                {"name": "AM_NPTP_PREFIXED_SECRET"}  # Has prefix but shouldn't be returned
            ]
        }

        # Set up async client mock
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        # Call the endpoint
        response = self.client.get(
            "/api/get-secrets",
            params={
                "user": "testuser",
                "repo_name": "testuser/test-repo",
                "project_name": "No Prefix Test Project"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "secrets" in data

        # Should return only secrets that are both in database AND in GitHub
        secrets = data["secrets"]
        assert len(secrets) == 3

        secret_names = {secret["secret_key"] for secret in secrets}
        assert secret_names == {"DATABASE_PASSWORD", "API_KEY", "JWT_SECRET"}

        # Should NOT include OTHER_SECRET (not in DB) or AM_NPTP_PREFIXED_SECRET
        assert "OTHER_SECRET" not in secret_names
        assert "AM_NPTP_PREFIXED_SECRET" not in secret_names

    @patch('github_env_vars.user_tokens', {'testuser': 'mock_token'})
    @patch('github_env_vars.httpx.AsyncClient')
    def test_get_env_vars_no_prefix_mode(self, mock_async_client):
        """Test that get_env_vars retrieves env vars from database for no_prefix projects."""
        # Track pagination calls to prevent infinite loop
        page_calls = 0

        # Mock individual variable value responses
        async def async_mock_get_response(*args, **kwargs):
            nonlocal page_calls
            url = args[0] if args else kwargs.get('url', '')

            if 'variables?' in url:
                # Track pagination - return empty on page 2 to exit the loop
                page_calls += 1
                if page_calls == 1:
                    # First page returns the variables
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "variables": [
                            {"name": "DEBUG_MODE"},
                            {"name": "LOG_LEVEL"},
                            {"name": "ENVIRONMENT"},
                            {"name": "OTHER_VAR"},  # Not in database
                            {"name": "AM_NPTP_PREFIXED_VAR"}  # Has prefix but shouldn't be returned
                        ]
                    }
                    return mock_response
                else:
                    # Subsequent pages return empty to exit the pagination loop
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"variables": []}
                    return mock_response
            elif 'variables/DEBUG_MODE' in url:
                value_response = MagicMock()
                value_response.status_code = 200
                value_response.json.return_value = {"value": "true"}
                return value_response
            elif 'variables/LOG_LEVEL' in url:
                value_response = MagicMock()
                value_response.status_code = 200
                value_response.json.return_value = {"value": "info"}
                return value_response
            elif 'variables/ENVIRONMENT' in url:
                value_response = MagicMock()
                value_response.status_code = 200
                value_response.json.return_value = {"value": "production"}
                return value_response
            else:
                # For any other variable
                value_response = MagicMock()
                value_response.status_code = 404
                return value_response

        # Set up async client mock
        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = async_mock_get_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        # Call the endpoint
        response = self.client.get(
            "/api/get-env-vars",
            params={
                "user": "testuser",
                "repo_name": "testuser/test-repo",
                "project_name": "No Prefix Test Project"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "env_vars" in data

        # Should return only env vars that are both in database AND in GitHub
        env_vars = data["env_vars"]
        assert len(env_vars) == 3

        env_var_names = {var["env_key"] for var in env_vars}
        assert env_var_names == {"DEBUG_MODE", "LOG_LEVEL", "ENVIRONMENT"}

        # Should NOT include OTHER_VAR (not in DB) or AM_NPTP_PREFIXED_VAR
        assert "OTHER_VAR" not in env_var_names
        assert "AM_NPTP_PREFIXED_VAR" not in env_var_names

        # Verify values are included
        env_var_values = {var["env_key"]: var["value"] for var in env_vars}
        assert env_var_values["DEBUG_MODE"] == "true"
        assert env_var_values["LOG_LEVEL"] == "info"
        assert env_var_values["ENVIRONMENT"] == "production"

    @patch('github_secrets.user_tokens', {'testuser': 'mock_token'})
    @patch('github_secrets.httpx.AsyncClient')
    def test_get_secrets_prefix_mode_still_works(self, mock_async_client):
        """Verify that prefix mode still works correctly (regression test)."""
        # Create a prefix-mode project
        db = TestingSessionLocal()
        try:
            user = db.query(Account).filter(Account.github_user == "testuser").first()
            prefix_project = Project(
                project_name="Prefix Test Project",
                project_code="PTP",
                user_id=user.user_id,
                use_prefix=True,
                pr_state="new"
            )
            db.add(prefix_project)
            db.commit()
        finally:
            db.close()

        # Mock GitHub API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "secrets": [
                {"name": "AM_PTP_DATABASE_PASSWORD"},
                {"name": "AM_PTP_API_KEY"},
                {"name": "OTHER_SECRET"},  # Should not be returned
                {"name": "AM_OTHER_SECRET"}  # Different prefix, should not be returned
            ]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_async_client.return_value.__aenter__.return_value = mock_client_instance

        # Call the endpoint
        response = self.client.get(
            "/api/get-secrets",
            params={
                "user": "testuser",
                "repo_name": "testuser/test-repo",
                "project_name": "Prefix Test Project"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "secrets" in data

        # Should return only secrets with AM_PTP_ prefix
        secrets = data["secrets"]
        assert len(secrets) == 2

        secret_names = {secret["secret_key"] for secret in secrets}
        assert secret_names == {"AM_PTP_DATABASE_PASSWORD", "AM_PTP_API_KEY"}
