"""
Comprehensive test suite for github_secrets.py module

This test suite provides comprehensive coverage for:
- Secrets CRUD operations
- Free account limit enforcement
- Encryption/decryption functionality
- Batch operations
- Error handling
- Secret validation
"""
import pytest
import sys
import os
import base64
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from fastapi import Request
from sqlalchemy.orm import Session

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))

from github_secrets import (
    router,
    count_project_secrets,
    encrypt_secret,
    _validate_account_limits,
    _get_repo_public_key,
    _process_repository_secrets
)


class TestSecretsCRUD:
    """Test secrets CRUD operations"""
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_create_secrets_success(self):
        """Test successful secret creation"""
        # Mock database
        mock_db = MagicMock()
        
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_account = Mock()
        mock_account.account_type = "pro"
        mock_account.admin_override = False
        mock_account.admin_override_until = None
        mock_account.marketplace_plan = None
        mock_account.marketplace_on_free_trial = False
        mock_account.marketplace_next_billing_date = None
        
        def query_side_effect(model):
            mock_query = Mock()
            if model.__name__ == "Project":
                mock_query.filter.return_value.first.return_value = mock_project
            else:
                mock_query.filter.return_value.first.return_value = mock_account
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        # Mock request
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["test/repo1"],
            "secrets": [{"secret_key": "SECRET1", "secret_value": "value1"}],
            "project_name": "TestProject"
        })
        
        with patch('github_secrets.httpx.AsyncClient') as mock_client:
            # Mock public key response
            mock_key_response = Mock()
            mock_key_response.status_code = 200
            mock_key_response.json.return_value = {
                "key_id": "key123",
                "key": base64.b64encode(b"0" * 32).decode("utf-8")
            }
            
            # Mock secret creation response
            mock_put_response = Mock()
            mock_put_response.status_code = 201
            
            mock_get = AsyncMock(return_value=mock_key_response)
            mock_put = AsyncMock(return_value=mock_put_response)
            
            mock_client.return_value.__aenter__.return_value.get = mock_get
            mock_client.return_value.__aenter__.return_value.put = mock_put
            
            from github_secrets import create_secrets
            result = await create_secrets(mock_request, mock_db)
            
            assert "message" in result
            assert "results" in result
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_get_secrets_success(self):
        """Test successful retrieval of secrets"""
        # Mock database
        mock_db = MagicMock()
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        
        with patch('github_secrets.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "secrets": [
                    {"name": "AM_TEST_SECRET1"},
                    {"name": "AM_TEST_SECRET2"},
                    {"name": "OTHER_SECRET"}
                ]
            }
            
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get
            
            from github_secrets import get_secrets
            result = await get_secrets("testuser", "test/repo1", "TestProject", mock_db)
            
            assert "secrets" in result
            assert len(result["secrets"]) == 2  # Only AM_TEST_* secrets
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_delete_secrets_success(self):
        """Test successful deletion of secrets"""
        # Mock database
        mock_db = MagicMock()
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        
        # Mock request
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["test/repo1"],
            "secret_name": "AM_TEST_SECRET1",
            "project_name": "TestProject"
        })
        
        with patch('github_secrets.httpx.AsyncClient') as mock_client:
            mock_delete_response = Mock()
            mock_delete_response.status_code = 204
            
            mock_delete = AsyncMock(return_value=mock_delete_response)
            mock_client.return_value.__aenter__.return_value.delete = mock_delete
            
            from github_secrets import delete_secrets
            result = await delete_secrets(mock_request, mock_db)
            
            assert "message" in result
            assert "deleted" in result["message"]
            assert "results" in result


class TestFreeAccountLimits:
    """Test free account limit enforcement for secrets"""
    
    @pytest.mark.asyncio
    @patch('github_secrets.count_project_secrets')
    async def test_free_account_limit_exceeded(self, mock_count):
        """Test that free accounts cannot exceed 2 secrets"""
        mock_count.return_value = 2
        
        mock_db = MagicMock()
        mock_user = Mock()
        mock_user.account_type = "free"
        mock_user.admin_override = False
        mock_user.admin_override_until = None
        mock_user.marketplace_plan = None
        mock_user.marketplace_on_free_trial = False
        mock_user.marketplace_next_billing_date = None
        
        mock_project = Mock()
        mock_project.project_code = "TEST"
        
        def query_side_effect(model):
            mock_query = Mock()
            if model.__name__ == "Account":
                mock_query.filter.return_value.first.return_value = mock_user
            else:
                mock_query.filter.return_value.first.return_value = mock_project
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        secrets = [{"secret_key": "SECRET1", "secret_value": "value1"}]
        
        result = await _validate_account_limits(
            "testuser", "TestProject", secrets, ["test/repo"], mock_db
        )
        
        assert result is not None
        assert "error" in result
        assert result["status"] == 403
        assert result["current_count"] == 2
        assert result["limit"] == 2
    
    @pytest.mark.asyncio
    @patch('github_secrets.count_project_secrets')
    async def test_free_account_within_limit(self, mock_count):
        """Test that free accounts can create secrets within limit"""
        mock_count.return_value = 1
        
        mock_db = MagicMock()
        mock_user = Mock()
        mock_user.account_type = "free"
        mock_user.admin_override = False
        mock_user.admin_override_until = None
        mock_user.marketplace_plan = None
        mock_user.marketplace_on_free_trial = False
        mock_user.marketplace_next_billing_date = None
        
        mock_project = Mock()
        mock_project.project_code = "TEST"
        
        def query_side_effect(model):
            mock_query = Mock()
            if model.__name__ == "Account":
                mock_query.filter.return_value.first.return_value = mock_user
            else:
                mock_query.filter.return_value.first.return_value = mock_project
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        secrets = [{"secret_key": "SECRET1", "secret_value": "value1"}]
        
        result = await _validate_account_limits(
            "testuser", "TestProject", secrets, ["test/repo"], mock_db
        )
        
        assert result is None  # No error
    
    @pytest.mark.asyncio
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('github_secrets.count_project_secrets')
    async def test_professional_account_at_limit(self, mock_count):
        """Test that professional accounts are blocked at 10 secret limit"""
        mock_count.return_value = 10
        
        mock_db = MagicMock()
        mock_user = Mock()
        mock_user.account_type = "professional"
        mock_user.admin_override = False
        mock_user.admin_override_until = None
        mock_user.marketplace_plan = None
        mock_user.marketplace_on_free_trial = False
        mock_user.marketplace_next_billing_date = None
        
        mock_project = Mock()
        mock_project.project_code = "TEST"
        
        def query_side_effect(model):
            mock_query = Mock()
            if model.__name__ == "Account":
                mock_query.filter.return_value.first.return_value = mock_user
            else:
                mock_query.filter.return_value.first.return_value = mock_project
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        secrets = [{"secret_key": "SECRET1", "secret_value": "value1"}]
        
        result = await _validate_account_limits(
            "testuser", "TestProject", secrets, ["test/repo"], mock_db
        )
        
        assert result is not None
        assert "error" in result
        assert result["status"] == 403
        assert result["current_count"] == 10
        assert result["limit"] == 10
        assert "Enterprise" in result["error"]
    
    @pytest.mark.asyncio
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('github_secrets.count_project_secrets')
    async def test_professional_account_within_limit(self, mock_count):
        """Test that professional accounts can create secrets within limit"""
        mock_count.return_value = 8
        
        mock_db = MagicMock()
        mock_user = Mock()
        mock_user.account_type = "professional"
        mock_user.admin_override = False
        mock_user.admin_override_until = None
        mock_user.marketplace_plan = None
        mock_user.marketplace_on_free_trial = False
        mock_user.marketplace_next_billing_date = None
        
        mock_project = Mock()
        mock_project.project_code = "TEST"
        
        def query_side_effect(model):
            mock_query = Mock()
            if model.__name__ == "Account":
                mock_query.filter.return_value.first.return_value = mock_user
            else:
                mock_query.filter.return_value.first.return_value = mock_project
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        secrets = [{"secret_key": "SECRET1", "secret_value": "value1"}]
        
        result = await _validate_account_limits(
            "testuser", "TestProject", secrets, ["test/repo"], mock_db
        )
        
        assert result is None  # No error
    
    @pytest.mark.asyncio
    @patch('tier_service.INSTALLATION_MODE', 'cloud')
    @patch('github_secrets.count_project_secrets')
    async def test_enterprise_account_no_limit(self, mock_count):
        """Test that enterprise accounts have no limit"""
        mock_count.return_value = 10
        
        mock_db = MagicMock()
        mock_user = Mock()
        mock_user.account_type = "enterprise"
        mock_user.admin_override = False
        mock_user.admin_override_until = None
        mock_user.marketplace_plan = None
        mock_user.marketplace_on_free_trial = False
        mock_user.marketplace_next_billing_date = None
        
        mock_project = Mock()
        mock_project.project_code = "TEST"
        
        def query_side_effect(model):
            mock_query = Mock()
            if model.__name__ == "Account":
                mock_query.filter.return_value.first.return_value = mock_user
            else:
                mock_query.filter.return_value.first.return_value = mock_project
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        secrets = [{"secret_key": f"SECRET{i}", "secret_value": f"value{i}"} for i in range(10)]
        
        result = await _validate_account_limits(
            "testuser", "TestProject", secrets, ["test/repo"], mock_db
        )
        
        assert result is None  # No limit for enterprise accounts


class TestEncryptionDecryption:
    """Test encryption/decryption for secrets"""
    
    def test_encrypt_secret_success(self):
        """Test successful secret encryption"""
        # Generate a valid public key
        from nacl.public import PrivateKey
        private_key = PrivateKey.generate()
        public_key = private_key.public_key
        public_key_b64 = base64.b64encode(bytes(public_key)).decode("utf-8")
        
        secret_value = "my_secret_value"
        
        encrypted = encrypt_secret(public_key_b64, secret_value)
        
        # Encrypted value should be base64 encoded
        assert encrypted is not None
        assert len(encrypted) > 0
        
        # Should be able to decode base64
        decoded = base64.b64decode(encrypted)
        assert decoded is not None
    
    def test_encrypt_secret_different_values(self):
        """Test that same secret with same key produces consistent encryption"""
        from nacl.public import PrivateKey
        private_key = PrivateKey.generate()
        public_key = private_key.public_key
        public_key_b64 = base64.b64encode(bytes(public_key)).decode("utf-8")
        
        secret_value = "my_secret_value"
        
        # Due to nonce in sealed box, each encryption is different
        encrypted1 = encrypt_secret(public_key_b64, secret_value)
        encrypted2 = encrypt_secret(public_key_b64, secret_value)
        
        # Should both be valid base64
        assert encrypted1 is not None
        assert encrypted2 is not None
        # But values should be different due to random nonce
        assert encrypted1 != encrypted2
    
    def test_encrypt_secret_empty_value(self):
        """Test encryption of empty string"""
        from nacl.public import PrivateKey
        private_key = PrivateKey.generate()
        public_key = private_key.public_key
        public_key_b64 = base64.b64encode(bytes(public_key)).decode("utf-8")
        
        encrypted = encrypt_secret(public_key_b64, "")
        
        assert encrypted is not None
        assert len(encrypted) > 0


class TestBatchOperations:
    """Test batch operations for secrets"""
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_create_multiple_secrets_multiple_repos(self):
        """Test creating multiple secrets across multiple repositories"""
        # Mock database
        mock_db = MagicMock()
        
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_account = Mock()
        mock_account.account_type = "pro"
        mock_account.admin_override = False
        mock_account.admin_override_until = None
        mock_account.marketplace_plan = None
        mock_account.marketplace_on_free_trial = False
        mock_account.marketplace_next_billing_date = None
        
        def query_side_effect(model):
            mock_query = Mock()
            if model.__name__ == "Project":
                mock_query.filter.return_value.first.return_value = mock_project
            else:
                mock_query.filter.return_value.first.return_value = mock_account
            return mock_query
        
        mock_db.query.side_effect = query_side_effect
        
        # Mock request with multiple secrets and repos
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["test/repo1", "test/repo2"],
            "secrets": [
                {"secret_key": "SECRET1", "secret_value": "value1"},
                {"secret_key": "SECRET2", "secret_value": "value2"}
            ],
            "project_name": "TestProject"
        })
        
        with patch('github_secrets.httpx.AsyncClient') as mock_client:
            # Mock public key response
            mock_key_response = Mock()
            mock_key_response.status_code = 200
            mock_key_response.json.return_value = {
                "key_id": "key123",
                "key": base64.b64encode(b"0" * 32).decode("utf-8")
            }
            
            # Mock secret creation response
            mock_put_response = Mock()
            mock_put_response.status_code = 201
            
            mock_get = AsyncMock(return_value=mock_key_response)
            mock_put = AsyncMock(return_value=mock_put_response)
            
            mock_client.return_value.__aenter__.return_value.get = mock_get
            mock_client.return_value.__aenter__.return_value.put = mock_put
            
            from github_secrets import create_secrets
            result = await create_secrets(mock_request, mock_db)
            
            assert "results" in result
            # Should have results for 2 repos
            assert len(result["results"]) == 2
    
    @pytest.mark.asyncio
    async def test_process_repository_secrets(self):
        """Test processing multiple secrets for a repository"""
        secrets = [
            {"secret_key": "SECRET1", "secret_value": "value1"},
            {"secret_key": "SECRET2", "secret_value": "value2"}
        ]
        
        # Mock responses
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_put_response.text = ""
        
        # Create mock client
        mock_client = Mock()
        mock_client.put = AsyncMock(return_value=mock_put_response)
        
        headers = {"Authorization": "token fake_token"}
        public_key = base64.b64encode(b"0" * 32).decode("utf-8")
        
        result = await _process_repository_secrets(
            "test/repo1", secrets, "TEST", "key123", public_key, headers, mock_client
        )
        
        assert len(result) == 2
        assert "AM_TEST_SECRET1" in result
        assert "AM_TEST_SECRET2" in result


class TestErrorHandling:
    """Test error handling for secrets"""
    
    @pytest.mark.asyncio
    async def test_create_secrets_no_auth(self):
        """Test create fails without authentication"""
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "nonexistent_user",
            "repo_names": ["test/repo1"],
            "secrets": [{"secret_key": "SECRET1", "secret_value": "value1"}],
            "project_name": "TestProject"
        })
        
        mock_db = MagicMock()
        
        from github_secrets import create_secrets
        result = await create_secrets(mock_request, mock_db)
        
        assert "error" in result
        assert result["status"] == 401
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_get_secrets_project_not_found(self):
        """Test get secrets fails with invalid project"""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        from github_secrets import get_secrets
        result = await get_secrets("testuser", "test/repo1", "NonexistentProject", mock_db)
        
        assert "error" in result
        assert result["status"] == 404
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_get_secrets_api_error(self):
        """Test get secrets handles API errors"""
        mock_db = MagicMock()
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        
        with patch('github_secrets.httpx.AsyncClient') as mock_client:
            mock_error_response = Mock()
            mock_error_response.status_code = 500
            
            mock_get = AsyncMock(return_value=mock_error_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get
            
            from github_secrets import get_secrets
            result = await get_secrets("testuser", "test/repo1", "TestProject", mock_db)
            
            assert "error" in result
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_get_repo_public_key_failure(self, mock_client):
        """Test handling of public key retrieval failure"""
        mock_error_response = Mock()
        mock_error_response.status_code = 404
        mock_error_response.text = "Not found"
        
        mock_get = AsyncMock(return_value=mock_error_response)
        mock_client.return_value.get = mock_get
        
        headers = {"Authorization": "token fake_token"}
        key_data, error = await _get_repo_public_key("test/repo1", headers, mock_client())
        
        assert key_data is None
        assert error is not None
        assert "error" in error
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_get_repo_public_key_invalid_data(self, mock_client):
        """Test handling of invalid public key data"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "key_id": None,  # Invalid
            "key": None
        }
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.get = mock_get
        
        headers = {"Authorization": "token fake_token"}
        key_data, error = await _get_repo_public_key("test/repo1", headers, mock_client())
        
        assert key_data is None
        assert error is not None


class TestSecretValidation:
    """Test secret validation"""
    
    @pytest.mark.asyncio
    async def test_process_repository_secrets_skip_empty(self):
        """Test that empty secrets are skipped"""
        secrets = [
            {"secret_key": "SECRET1", "secret_value": "value1"},
            {"secret_key": "", "secret_value": "value2"},  # Empty key
            {"secret_key": "SECRET3", "secret_value": ""}   # Empty value
        ]
        
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_put_response.text = ""
        
        # Create mock client
        mock_client = Mock()
        mock_client.put = AsyncMock(return_value=mock_put_response)
        
        headers = {"Authorization": "token fake_token"}
        public_key = base64.b64encode(b"0" * 32).decode("utf-8")
        
        result = await _process_repository_secrets(
            "test/repo1", secrets, "TEST", "key123", public_key, headers, mock_client
        )
        
        # Only SECRET1 should be processed
        assert len(result) == 1
        assert "AM_TEST_SECRET1" in result
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_get_secrets_filters_by_project_code(self):
        """Test that get secrets only returns secrets for the specific project"""
        mock_db = MagicMock()
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        
        with patch('github_secrets.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "secrets": [
                    {"name": "AM_TEST_SECRET1"},
                    {"name": "AM_TEST_SECRET2"},
                    {"name": "AM_OTHER_SECRET"},  # Different project
                    {"name": "RANDOM_SECRET"}     # Not an AM secret
                ]
            }
            
            mock_get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.get = mock_get
            
            from github_secrets import get_secrets
            result = await get_secrets("testuser", "test/repo1", "TestProject", mock_db)
            
            assert "secrets" in result
            assert len(result["secrets"]) == 2
            # Should only include AM_TEST_* secrets
            secret_names = [s["secret_key"] for s in result["secrets"]]
            assert "AM_TEST_SECRET1" in secret_names
            assert "AM_TEST_SECRET2" in secret_names
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_delete_secrets_with_prefix(self):
        """Test deleting secret that already has prefix"""
        mock_db = MagicMock()
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["test/repo1"],
            "secret_name": "AM_TEST_SECRET1",  # Already has prefix
            "project_name": "TestProject"
        })
        
        with patch('github_secrets.httpx.AsyncClient') as mock_client:
            mock_delete_response = Mock()
            mock_delete_response.status_code = 204
            
            mock_delete = AsyncMock(return_value=mock_delete_response)
            mock_client.return_value.__aenter__.return_value.delete = mock_delete
            
            from github_secrets import delete_secrets
            result = await delete_secrets(mock_request, mock_db)
            
            # Should use the provided name as-is
            mock_delete.assert_called()
            call_args = mock_delete.call_args
            assert "AM_TEST_SECRET1" in call_args[0][0]
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_delete_secrets_without_prefix(self):
        """Test deleting secret without prefix"""
        mock_db = MagicMock()
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "repo_names": ["test/repo1"],
            "secret_name": "SECRET1",  # No prefix
            "project_name": "TestProject"
        })
        
        with patch('github_secrets.httpx.AsyncClient') as mock_client:
            mock_delete_response = Mock()
            mock_delete_response.status_code = 204
            
            mock_delete = AsyncMock(return_value=mock_delete_response)
            mock_client.return_value.__aenter__.return_value.delete = mock_delete
            
            from github_secrets import delete_secrets
            result = await delete_secrets(mock_request, mock_db)
            
            # Should add prefix
            mock_delete.assert_called()
            call_args = mock_delete.call_args
            assert "AM_TEST_SECRET1" in call_args[0][0]


class TestSyncOperations:
    """Test sync operations for secrets"""
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_sync_secret_not_supported(self):
        """Test that sync_secret returns appropriate error"""
        mock_db = MagicMock()
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        
        mock_request = AsyncMock()
        mock_request.json = AsyncMock(return_value={
            "user": "testuser",
            "project_name": "TestProject",
            "secret_key": "SECRET1"
        })
        
        from github_secrets import sync_secret
        result = await sync_secret(mock_request, mock_db)
        
        # Should return error because GitHub API doesn't allow reading secret values
        assert "error" in result
        assert result["status"] == 400
        assert "Cannot sync secrets" in result["error"]


class TestCountingFunctions:
    """Test counting helper functions"""
    
    @pytest.mark.asyncio
    async def test_count_project_secrets_no_auth(self):
        """Test count returns 0 when user not authenticated"""
        count = await count_project_secrets("nonexistent_user", "TEST", ["test/repo"])
        assert count == 0
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_secrets_success(self, mock_client):
        """Test count function with mocked GitHub API response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "secrets": [
                {"name": "AM_TEST_SECRET1"},
                {"name": "AM_TEST_SECRET2"},
                {"name": "OTHER_SECRET"},
                {"name": "AM_OTHER_PROJECT_SECRET"}
            ]
        }
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_secrets("testuser", "TEST", ["test/repo"])
        assert count == 2
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    @patch('httpx.AsyncClient')
    async def test_count_project_secrets_multiple_repos(self, mock_client):
        """Test count function with multiple repositories"""
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
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        count = await count_project_secrets("testuser", "TEST", ["test/repo"])
        assert count == 0
    
    @pytest.mark.asyncio
    @patch('github_secrets.user_tokens', {'testuser': 'fake_token'})
    async def test_get_secrets_count_endpoint(self):
        """Test the secrets count API endpoint"""
        mock_db = MagicMock()
        mock_project = Mock()
        mock_project.project_code = "TEST"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_project
        
        with patch('github_secrets.count_project_secrets', return_value=5):
            from github_secrets import get_secrets_count
            result = await get_secrets_count(
                "testuser", "TestProject", "test/repo1,test/repo2", mock_db
            )
            
            assert "count" in result
            assert result["count"] == 5


class TestHelperFunctions:
    """Test helper functions"""
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient')
    async def test_get_repo_public_key_success(self, mock_client):
        """Test successful retrieval of repository public key"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "key_id": "key123",
            "key": base64.b64encode(b"0" * 32).decode("utf-8")
        }
        
        mock_get = AsyncMock(return_value=mock_response)
        mock_client.return_value.get = mock_get
        
        headers = {"Authorization": "token fake_token"}
        key_data, error = await _get_repo_public_key("test/repo1", headers, mock_client())
        
        assert key_data is not None
        assert error is None
        assert key_data[0] == "key123"
        assert len(key_data[1]) > 0


if __name__ == "__main__":
    # Run tests using pytest
    pytest.main([__file__, "-v"])
