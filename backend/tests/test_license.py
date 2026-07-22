"""
Tests for license.py module - JWT-based license key validation (RS256)
"""
import pytest
import jwt
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import license


# Generate a test RSA key pair for use in all tests
_private_key_obj = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PRIVATE_KEY = _private_key_obj.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption()
).decode()
TEST_PUBLIC_KEY = _private_key_obj.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
).decode()

# A second key pair for testing invalid-signature scenarios
_other_key_obj = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_PRIVATE_KEY = _other_key_obj.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption()
).decode()


class TestValidateLicenseKey:
    """Test validate_license_key function"""

    def test_valid_license_professional_tier(self):
        """Test valid license key with professional tier"""
        payload = {"tier": "professional"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is True
        assert tier == "professional"
        assert error is None

    def test_valid_license_enterprise_tier(self):
        """Test valid license key with enterprise tier"""
        payload = {"tier": "enterprise"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is True
        assert tier == "enterprise"
        assert error is None

    def test_valid_license_free_tier(self):
        """Test valid license key with free tier"""
        payload = {"tier": "free"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is True
        assert tier == "free"
        assert error is None

    def test_valid_license_pro_alias(self):
        """Test valid license key with 'pro' as alias for professional"""
        payload = {"tier": "pro"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is True
        assert tier == "professional"
        assert error is None

    def test_valid_license_with_future_expiration(self):
        """Test valid license key with future expiration"""
        future_exp = datetime.now(timezone.utc) + timedelta(days=365)
        payload = {
            "tier": "professional",
            "exp": int(future_exp.timestamp())
        }
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is True
        assert tier == "professional"
        assert error is None

    def test_expired_license_via_exp_field(self):
        """Test license key that has expired via exp field"""
        past_exp = datetime.now(timezone.utc) - timedelta(days=1)
        payload = {
            "tier": "professional",
            "exp": int(past_exp.timestamp())
        }
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is False
        assert tier is None
        assert "expired" in error.lower()

    def test_invalid_signature(self):
        """Test license key signed with a different private key"""
        payload = {"tier": "professional"}
        # Sign with OTHER_PRIVATE_KEY but verify with TEST_PUBLIC_KEY
        token = jwt.encode(payload, OTHER_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is False
        assert tier is None
        assert "signature" in error.lower()

    def test_invalid_format(self):
        """Test license key with invalid format"""
        invalid_token = "not-a-valid-jwt-token"

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(invalid_token)

        assert valid is False
        assert tier is None
        assert "format" in error.lower() or "decode" in error.lower()

    def test_missing_tier_field(self):
        """Test license key missing tier field"""
        payload = {"some_other_field": "value"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is False
        assert tier is None
        assert "tier" in error.lower()

    def test_empty_license_key(self):
        """Test with empty license key"""
        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key("")

        assert valid is False
        assert tier is None
        assert "not provided" in error.lower()

    def test_none_license_key(self):
        """Test with None license key"""
        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(None)

        assert valid is False
        assert tier is None
        assert "not provided" in error.lower()

    def test_unknown_tier_defaults_to_free(self):
        """Test that unknown tier values default to free"""
        payload = {"tier": "unknown_tier"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is True
        assert tier == "free"
        assert error is None


class TestGetInstallationTier:
    """Test get_installation_tier function"""

    def setup_method(self):
        """Reset cache before each test"""
        license.reset_cache()

    def test_cloud_mode_always_returns_free(self, monkeypatch):
        """Test that cloud mode always returns free tier"""
        monkeypatch.setenv("INSTALLATION_MODE", "cloud")

        # Reload config to pick up the new mode
        import importlib
        import config as config_module
        importlib.reload(config_module)

        # Mock config.INSTALLATION_MODE in license module
        with patch('license.config.INSTALLATION_MODE', 'cloud'):
            tier = license.get_installation_tier()
            assert tier == "free"

    def test_self_hosted_no_license_returns_free(self, monkeypatch):
        """Test that self-hosted without license returns free tier"""
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.delenv("LICENSE_KEY", raising=False)

        # Mock config.INSTALLATION_MODE
        with patch('license.config.INSTALLATION_MODE', 'self-hosted'):
            tier = license.get_installation_tier()
            assert tier == "free"

    def test_self_hosted_valid_professional_license(self, monkeypatch):
        """Test self-hosted with valid professional license"""
        payload = {"tier": "professional"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            tier = license.get_installation_tier()
            assert tier == "professional"

    def test_self_hosted_valid_enterprise_license(self, monkeypatch):
        """Test self-hosted with valid enterprise license"""
        payload = {"tier": "enterprise"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            tier = license.get_installation_tier()
            assert tier == "enterprise"

    def test_self_hosted_expired_license_returns_free(self, monkeypatch):
        """Test self-hosted with expired license falls back to free"""
        past_exp = datetime.now(timezone.utc) - timedelta(days=1)
        payload = {
            "tier": "professional",
            "exp": int(past_exp.timestamp())
        }
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            tier = license.get_installation_tier()
            assert tier == "free"

    def test_self_hosted_invalid_license_returns_free(self, monkeypatch):
        """Test self-hosted with invalid license falls back to free"""
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", "invalid-token")

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            tier = license.get_installation_tier()
            assert tier == "free"

    def test_caching_behavior(self, monkeypatch):
        """Test that get_installation_tier caches result"""
        payload = {"tier": "professional"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            # First call should validate
            tier1 = license.get_installation_tier()
            assert tier1 == "professional"

            # Change environment variable (should not affect cached result)
            monkeypatch.setenv("LICENSE_KEY", "different-token")

            # Second call should return cached result
            tier2 = license.get_installation_tier()
            assert tier2 == "professional"

    def test_reset_cache_forces_revalidation(self, monkeypatch):
        """Test that reset_cache forces re-validation"""
        payload1 = {"tier": "professional"}
        token1 = jwt.encode(payload1, TEST_PRIVATE_KEY, algorithm="RS256")

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token1)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            # First call
            tier1 = license.get_installation_tier()
            assert tier1 == "professional"

            # Reset cache and change license
            license.reset_cache()
            payload2 = {"tier": "enterprise"}
            token2 = jwt.encode(payload2, TEST_PRIVATE_KEY, algorithm="RS256")
            monkeypatch.setenv("LICENSE_KEY", token2)

            # Should re-validate and return new tier
            tier2 = license.get_installation_tier()
            assert tier2 == "enterprise"

    def test_empty_license_key_returns_free(self, monkeypatch):
        """Test that empty license key returns free tier"""
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", "")

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'):
            tier = license.get_installation_tier()
            assert tier == "free"

    def test_whitespace_license_key_returns_free(self, monkeypatch):
        """Test that whitespace-only license key returns free tier"""
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", "   ")

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'):
            tier = license.get_installation_tier()
            assert tier == "free"


class TestNormalizeTier:
    """Test _normalize_tier helper function"""

    def test_normalize_professional(self):
        """Test normalizing 'professional' tier"""
        assert license._normalize_tier("professional") == "professional"

    def test_normalize_pro(self):
        """Test normalizing 'pro' to 'professional'"""
        assert license._normalize_tier("pro") == "professional"

    def test_normalize_pro_uppercase(self):
        """Test normalizing 'PRO' to 'professional'"""
        assert license._normalize_tier("PRO") == "professional"

    def test_normalize_enterprise(self):
        """Test normalizing 'enterprise' tier"""
        assert license._normalize_tier("enterprise") == "enterprise"

    def test_normalize_enterprise_uppercase(self):
        """Test normalizing 'ENTERPRISE' to 'enterprise'"""
        assert license._normalize_tier("ENTERPRISE") == "enterprise"

    def test_normalize_free(self):
        """Test normalizing 'free' tier"""
        assert license._normalize_tier("free") == "free"

    def test_normalize_empty_string(self):
        """Test normalizing empty string returns 'free'"""
        assert license._normalize_tier("") == "free"

    def test_normalize_none(self):
        """Test normalizing None returns 'free'"""
        assert license._normalize_tier(None) == "free"

    def test_normalize_unknown_tier(self):
        """Test normalizing unknown tier returns 'free'"""
        assert license._normalize_tier("unknown") == "free"


class TestResetCache:
    """Test reset_cache function"""

    def test_reset_cache_clears_cached_tier(self, monkeypatch):
        """Test that reset_cache clears the cached tier"""
        payload = {"tier": "professional"}
        token = jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256")

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            # Cache a tier
            license.get_installation_tier()

            # Reset cache
            license.reset_cache()

            # Check that cache is cleared
            assert license._cached_tier is None
            assert license._cache_initialized is False
