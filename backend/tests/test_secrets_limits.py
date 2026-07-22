"""
Test script for secrets limits feature for free and professional accounts
"""
import pytest
import sys
import os
from unittest.mock import patch, Mock, AsyncMock

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from github_secrets import count_project_secrets, _validate_account_limits
from models import Account, Project
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base


# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_secrets_limits.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestSecretsLimits:
    """Test secrets limits for free and professional accounts"""
    
    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Set up the test database before each test."""
        # Create tables
        Base.metadata.create_all(bind=engine)
        
        # Create test users and projects
        db = TestingSessionLocal()
        try:
            # Free user
            free_user = Account(
                github_user="freeuser",
                github_email="freeuser@example.com",
                account_type="free"
            )
            db.add(free_user)
            
            # Professional user
            pro_user = Account(
                github_user="prouser",
                github_email="prouser@example.com",
                account_type="professional"
            )
            db.add(pro_user)
            
            # Enterprise user
            enterprise_user = Account(
                github_user="enterpriseuser",
                github_email="enterpriseuser@example.com",
                account_type="enterprise"
            )
            db.add(enterprise_user)
            
            db.commit()
            
            # Create test projects
            free_project = Project(
                project_name="Free Project",
                project_code="FREE1",
                user_id=1  # freeuser
            )
            db.add(free_project)
            
            pro_project = Project(
                project_name="Pro Project",
                project_code="PRO1",
                user_id=2  # prouser
            )
            db.add(pro_project)
            
            enterprise_project = Project(
                project_name="Enterprise Project",
                project_code="ENT1",
                user_id=3  # enterpriseuser
            )
            db.add(enterprise_project)
            
            db.commit()
        finally:
            db.close()
        
        yield
        
        # Clean up after test
        Base.metadata.drop_all(bind=engine)
    
    @pytest.mark.asyncio
    async def test_count_project_secrets_no_auth(self):
        """Test count function returns 0 when user not authenticated"""
        count = await count_project_secrets("nonexistent_user", "TEST", ["test/repo"])
        assert count == 0
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_secrets_success(self, mock_client):
        """Test count function with mocked GitHub API response"""
        # Mock GitHub API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "secrets": [
                {"name": "AM_TEST_SECRET1"},
                {"name": "AM_TEST_SECRET2"},
                {"name": "OTHER_SECRET"},  # Should be ignored
                {"name": "AM_OTHER_PROJECT_SECRET"}  # Should be ignored
            ]
        }
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_secrets("testuser", "TEST", ["test/repo"])
        assert count == 2  # Only AM_TEST_* secrets should be counted
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_secrets_multiple_repos(self, mock_client):
        """Test count function with multiple repositories"""
        # Mock GitHub API response for both repos
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "secrets": [
                {"name": "AM_TEST_SECRET1"},
                {"name": "AM_TEST_SECRET2"}
            ]
        }
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_secrets("testuser", "TEST", ["test/repo1", "test/repo2"])
        # Should return unique count (both repos have same secrets)
        assert count == 2
        # Should have called GitHub API for both repos
        assert mock_get.call_count == 2
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_secrets_api_error(self, mock_client):
        """Test count function handles API errors gracefully"""
        # Mock GitHub API error response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_secrets("testuser", "TEST", ["test/repo"])
        assert count == 0  # Should return 0 on error
    
    @pytest.mark.asyncio
    @patch('github_secrets.count_project_secrets')
    async def test_free_user_secrets_limit(self, mock_count):
        """Test that free users can only create up to 2 secrets per project"""
        mock_count.return_value = 1  # Current count

        db = TestingSessionLocal()
        try:
            # Try to add 2 new secrets (total would be 3, exceeding limit of 2)
            secrets = [
                {"secret_key": "SECRET1", "secret_value": "value1"},
                {"secret_key": "SECRET2", "secret_value": "value2"}
            ]

            result = await _validate_account_limits("freeuser", "Free Project", secrets, ["test/repo"], db)

            assert result is not None
            assert result["status"] == 403
            assert "2 secrets per project" in result["error"]
            assert "Professional" in result["error"]
            assert result["limit"] == 2
        finally:
            db.close()
    
    @pytest.mark.asyncio
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('github_secrets.count_project_secrets')
    async def test_professional_user_secrets_limit(self, mock_count):
        """Test that professional users can create up to 10 secrets per project"""
        mock_count.return_value = 9  # Current count
        
        db = TestingSessionLocal()
        try:
            # Try to add 2 new secrets (total would be 11, exceeding limit of 10)
            secrets = [
                {"secret_key": "SECRET1", "secret_value": "value1"},
                {"secret_key": "SECRET2", "secret_value": "value2"}
            ]
            
            result = await _validate_account_limits("prouser", "Pro Project", secrets, ["test/repo"], db)
            
            assert result is not None
            assert result["status"] == 403
            assert "10 secrets per project" in result["error"]
            assert "Enterprise" in result["error"]
            assert result["limit"] == 10
        finally:
            db.close()
    
    @pytest.mark.asyncio
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('github_secrets.count_project_secrets')
    async def test_professional_user_under_limit(self, mock_count):
        """Test that professional users can add secrets when under limit"""
        mock_count.return_value = 8  # Current count
        
        db = TestingSessionLocal()
        try:
            # Try to add 2 new secrets (total would be 10, at limit but allowed)
            secrets = [
                {"secret_key": "SECRET1", "secret_value": "value1"},
                {"secret_key": "SECRET2", "secret_value": "value2"}
            ]
            
            result = await _validate_account_limits("prouser", "Pro Project", secrets, ["test/repo"], db)
            
            assert result is None  # No error, under limit
        finally:
            db.close()
    
    @pytest.mark.asyncio
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('github_secrets.count_project_secrets')
    async def test_enterprise_user_no_limit(self, mock_count):
        """Test that enterprise users have no secrets limit"""
        mock_count.return_value = 100  # High current count
        
        db = TestingSessionLocal()
        try:
            # Try to add 10 new secrets (should be allowed)
            secrets = [{"secret_key": f"SECRET{i}", "secret_value": f"value{i}"} for i in range(10)]
            
            result = await _validate_account_limits("enterpriseuser", "Enterprise Project", secrets, ["test/repo"], db)
            
            assert result is None  # No error, no limit for enterprise
        finally:
            db.close()


if __name__ == "__main__":
    # Run tests using pytest
    pytest.main([__file__, "-v"])