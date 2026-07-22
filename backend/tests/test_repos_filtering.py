"""
Test cases for repository filtering based on account type.
Ensures free users only see public repositories while paid users see all.
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Account
from repos import _should_restrict_to_public_repos, get_repos
from fastapi import HTTPException
from fastapi.testclient import TestClient


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_repos_filtering.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def setup_test_db():
    """Create test database tables"""
    Base.metadata.create_all(bind=engine)


def teardown_test_db():
    """Clean up test database"""
    Base.metadata.drop_all(bind=engine)


def get_test_db():
    """Get test database session"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestShouldRestrictToPublicRepos:
    """Test the helper function that determines if a user should be restricted"""
    
    def setup_method(self):
        setup_test_db()
        self.db = next(get_test_db())
        # Reset license cache to avoid interference from other tests
        import license
        license.reset_cache()

    def teardown_method(self):
        self.db.close()
        teardown_test_db()

    def test_free_account_is_restricted(self):
        """Free account users should be restricted to public repos only"""
        # Create a free account
        account = Account(
            github_user="free_user",
            github_email="free@example.com",
            account_type="free"
        )
        self.db.add(account)
        self.db.commit()
        
        result = _should_restrict_to_public_repos("free_user", self.db)
        assert result is True

    def test_unknown_account_is_restricted(self):
        """Unknown account type users should be restricted to public repos only"""
        # Create an unknown account
        # Note: With tier_service, unknown types are normalized to "free" tier
        account = Account(
            github_user="unknown_user",
            github_email="unknown@example.com",
            account_type="unknown"
        )
        self.db.add(account)
        self.db.commit()
        
        result = _should_restrict_to_public_repos("unknown_user", self.db)
        # Should be restricted because "unknown" normalizes to "free" tier
        assert result is True

    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_professional_account_not_restricted(self):
        """Professional account users should have full access to all repos"""
        # Create a professional account
        account = Account(
            github_user="professional_user",
            github_email="professional@example.com",
            account_type="professional"
        )
        self.db.add(account)
        self.db.commit()
        
        result = _should_restrict_to_public_repos("professional_user", self.db)
        assert result is False

    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    def test_enterprise_account_not_restricted(self):
        """Enterprise account users should have full access to all repos"""
        # Create an enterprise account
        account = Account(
            github_user="enterprise_user",
            github_email="enterprise@example.com",
            account_type="enterprise"
        )
        self.db.add(account)
        self.db.commit()
        
        result = _should_restrict_to_public_repos("enterprise_user", self.db)
        assert result is False

    def test_missing_user_is_restricted(self):
        """Users not in database should be restricted by default for safety"""
        result = _should_restrict_to_public_repos("nonexistent_user", self.db)
        assert result is True

    def test_unexpected_account_type_is_restricted(self):
        """Users with unexpected account types should be restricted by default"""
        # Create account with unexpected type
        account = Account(
            github_user="weird_user",
            github_email="weird@example.com",
            account_type="some_weird_type"
        )
        self.db.add(account)
        self.db.commit()
        
        result = _should_restrict_to_public_repos("weird_user", self.db)
        assert result is True


class TestGetReposFiltering:
    """Test the main get_repos endpoint filtering behavior"""

    def setup_method(self):
        setup_test_db()
        self.db = next(get_test_db())
        self._auth_patch = patch('repos._assert_session_owns_user')
        self._auth_patch.start()
        import license
        license.reset_cache()

    def teardown_method(self):
        self._auth_patch.stop()
        self.db.close()
        teardown_test_db()

    @patch('repos.github_get')
    @patch('repos.user_tokens')
    @patch('repos.get_github_api_endpoints')
    def test_free_user_only_gets_public_repos(self, mock_endpoints, mock_tokens, mock_github_get):
        """Free users should only receive public repositories"""
        # Setup mocks
        mock_tokens.__contains__ = Mock(return_value=True)
        mock_tokens.__getitem__ = Mock(return_value="fake_token")
        mock_endpoints.return_value = {"repos_list": "https://api.github.com/user/repos"}
        
        # Mock GitHub API response with mixed public/private repos
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "name": "public-repo", "full_name": "user/public-repo", "private": False},
            {"id": 2, "name": "private-repo", "full_name": "user/private-repo", "private": True},
            {"id": 3, "name": "another-public", "full_name": "user/another-public", "private": False}
        ]
        mock_github_get.return_value = mock_response
        
        # Create free user
        account = Account(
            github_user="free_user",
            github_email="free@example.com", 
            account_type="free"
        )
        self.db.add(account)
        self.db.commit()
        
        # Call the endpoint
        result = get_repos("free_user", Mock(), self.db)
        
        # Should only return public repos
        assert len(result) == 2
        assert result[0]["name"] == "public-repo"
        assert result[1]["name"] == "another-public"
        # Private repo should be filtered out
        repo_names = [r["name"] for r in result]
        assert "private-repo" not in repo_names

    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('repos.github_get')
    @patch('repos.user_tokens')
    @patch('repos.get_github_api_endpoints')
    def test_professional_user_gets_all_repos(self, mock_endpoints, mock_tokens, mock_github_get):
        """Professional users should receive both public and private repositories"""
        # Setup mocks
        mock_tokens.__contains__ = Mock(return_value=True)
        mock_tokens.__getitem__ = Mock(return_value="fake_token")
        mock_endpoints.return_value = {"repos_list": "https://api.github.com/user/repos"}
        
        # Mock GitHub API response with mixed public/private repos
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "name": "public-repo", "full_name": "user/public-repo", "private": False},
            {"id": 2, "name": "private-repo", "full_name": "user/private-repo", "private": True},
            {"id": 3, "name": "another-public", "full_name": "user/another-public", "private": False}
        ]
        mock_github_get.return_value = mock_response
        
        # Create professional user
        account = Account(
            github_user="professional_user",
            github_email="professional@example.com",
            account_type="professional"
        )
        self.db.add(account)
        self.db.commit()
        
        # Call the endpoint
        result = get_repos("professional_user", Mock(), self.db)
        
        # Should return all repos
        assert len(result) == 3
        repo_names = [r["name"] for r in result]
        assert "public-repo" in repo_names
        assert "private-repo" in repo_names  # Professional user should see private repos
        assert "another-public" in repo_names

    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('repos.github_get')
    @patch('repos.user_tokens')
    @patch('repos.get_github_api_endpoints')
    def test_enterprise_user_gets_all_repos(self, mock_endpoints, mock_tokens, mock_github_get):
        """Enterprise users should receive both public and private repositories"""
        # Setup mocks
        mock_tokens.__contains__ = Mock(return_value=True)
        mock_tokens.__getitem__ = Mock(return_value="fake_token")
        mock_endpoints.return_value = {"repos_list": "https://api.github.com/user/repos"}
        
        # Mock GitHub API response with mixed public/private repos
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "name": "public-repo", "full_name": "user/public-repo", "private": False},
            {"id": 2, "name": "private-repo", "full_name": "user/private-repo", "private": True}
        ]
        mock_github_get.return_value = mock_response
        
        # Create enterprise user
        account = Account(
            github_user="enterprise_user",
            github_email="enterprise@example.com",
            account_type="enterprise"
        )
        self.db.add(account)
        self.db.commit()
        
        # Call the endpoint
        result = get_repos("enterprise_user", Mock(), self.db)
        
        # Should return all repos
        assert len(result) == 2
        repo_names = [r["name"] for r in result]
        assert "public-repo" in repo_names
        assert "private-repo" in repo_names  # Enterprise user should see private repos

    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('repos.github_get')
    @patch('repos.user_tokens')
    @patch('repos.get_github_api_endpoints')
    def test_repos_include_owner_and_type_fields(self, mock_endpoints, mock_tokens, mock_github_get):
        """Repo listing should include owner login and owner_type for org support"""
        mock_tokens.__contains__ = Mock(return_value=True)
        mock_tokens.__getitem__ = Mock(return_value="fake_token")
        mock_endpoints.return_value = {"repos_list": "https://api.github.com/orgs/my-org/repos"}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": 10,
                "name": "org-repo",
                "full_name": "my-org/org-repo",
                "private": False,
                "owner": {"login": "my-org", "type": "Organization"},
            }
        ]
        mock_github_get.return_value = mock_response

        account = Account(
            github_user="my-org",
            github_email="org@example.com",
            account_type="enterprise",
            github_account_type="Organization",
        )
        self.db.add(account)
        self.db.commit()

        result = get_repos("my-org", Mock(), self.db)

        assert len(result) == 1
        assert result[0]["owner"] == "my-org"
        assert result[0]["owner_type"] == "Organization"
        assert result[0]["private"] is False

    @patch('repos.github_get')
    @patch('repos.user_tokens')
    @patch('repos.get_github_api_endpoints')
    def test_repos_pagination_collects_all_pages(self, mock_endpoints, mock_tokens, mock_github_get):
        """get_repos should paginate through all pages of the GitHub API"""
        mock_tokens.__contains__ = Mock(return_value=True)
        mock_tokens.__getitem__ = Mock(return_value="fake_token")
        mock_endpoints.return_value = {"repos_list": "https://api.github.com/user/repos"}

        # Build two pages of 100 repos each + a partial third page
        def _repo(i):
            return {"id": i, "name": f"repo-{i}", "full_name": f"user/repo-{i}", "private": False,
                    "owner": {"login": "paginated_user", "type": "User"}}

        page1 = [_repo(i) for i in range(100)]
        page2 = [_repo(i) for i in range(100, 200)]
        page3 = [_repo(200)]

        responses = iter([page1, page2, page3])

        def mock_get_side_effect(*args, **kwargs):
            resp = Mock()
            resp.status_code = 200
            resp.json.return_value = next(responses)
            return resp

        mock_github_get.side_effect = mock_get_side_effect

        # No account = restricted to public repos (which all are)
        account = Account(
            github_user="paginated_user",
            github_email="page@example.com",
            account_type="free",
        )
        self.db.add(account)
        self.db.commit()

        result = get_repos("paginated_user", Mock(), self.db)

        assert len(result) == 201
        # Ensure github_get was called 3 times (one per page)
        assert mock_github_get.call_count == 3

    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('repos.github_get')
    @patch('repos.user_tokens')
    @patch('repos.get_github_api_endpoints')
    def test_repos_api_includes_type_all_parameter(self, mock_endpoints, mock_tokens, mock_github_get):
        """get_repos should include type=all in GitHub API calls to get all accessible repos"""
        mock_tokens.__contains__ = Mock(return_value=True)
        mock_tokens.__getitem__ = Mock(return_value="fake_token")
        mock_endpoints.return_value = {"repos_list": "https://api.github.com/user/repos"}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": 1, "name": "public-repo", "full_name": "user/public-repo", "private": False,
             "owner": {"login": "test_user", "type": "User"}},
            {"id": 2, "name": "private-repo", "full_name": "user/private-repo", "private": True,
             "owner": {"login": "test_user", "type": "User"}},
            {"id": 3, "name": "org-repo", "full_name": "my-org/org-repo", "private": False,
             "owner": {"login": "my-org", "type": "Organization"}}
        ]
        mock_github_get.return_value = mock_response

        # Create professional user to test that API is called with correct params
        account = Account(
            github_user="test_user",
            github_email="test@example.com",
            account_type="professional"
        )
        self.db.add(account)
        self.db.commit()

        result = get_repos("test_user", Mock(), self.db)

        # Verify the API was called with type=all parameter
        # Note: visibility parameter is NOT used as it's only for GitHub Enterprise
        assert mock_github_get.call_count == 1
        call_args = mock_github_get.call_args
        url_called = call_args[0][0]
        assert "type=all" in url_called, f"Expected 'type=all' in URL: {url_called}"
        # Should NOT include visibility=all (only for GitHub Enterprise)
        assert "visibility=" not in url_called, f"Unexpected 'visibility=' in URL: {url_called}"

        # Should return all repos for professional user (including org repos)
        assert len(result) == 3
        repo_names = [r["name"] for r in result]
        assert "public-repo" in repo_names
        assert "private-repo" in repo_names
        assert "org-repo" in repo_names


if __name__ == "__main__":
    pytest.main([__file__])