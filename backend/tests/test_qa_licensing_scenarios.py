"""
QA Test Suite for License Validation Scenarios

This comprehensive test suite validates:
1. Expired license handling and fallback to free tier
2. Invalid license format handling
3. License upgrade/downgrade flows
4. Tier gate enforcement across features
5. Self-hosted vs cloud mode behavior

All licenses use the production RS256 signing scheme. The previous HS256/HMAC
``LICENSE_SECRET`` path has been removed; tests sign with an ephemeral RSA key
pair and patch the embedded ``LICENSE_PUBLIC_KEY`` constant for verification.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import license  # noqa: E402
import config  # noqa: E402,F401  (imported for module side-effects/parity)


# --------------------------------------------------------------------------- #
# Test signing material — RS256 (matches production validation path)
# --------------------------------------------------------------------------- #

_private_key_obj = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PRIVATE_KEY = _private_key_obj.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
TEST_PUBLIC_KEY = _private_key_obj.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

# A second key pair used to simulate forged / wrong-signature licenses.
_other_key_obj = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_PRIVATE_KEY = _other_key_obj.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
).decode()


def _sign(payload: dict, key: str = TEST_PRIVATE_KEY) -> str:
    """Encode ``payload`` as an RS256 JWT using the given private key."""
    return jwt.encode(payload, key, algorithm="RS256")


class TestExpiredLicenseHandling:
    """Test expired license scenarios and fallback behavior"""

    def setup_method(self):
        license.reset_cache()

    def test_expired_license_falls_back_to_free_tier(self, monkeypatch):
        past_exp = datetime.now(timezone.utc) - timedelta(days=30)
        token = _sign({
            "tier": "professional",
            "exp": int(past_exp.timestamp()),
            "email": "test@example.com",
        })

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            assert license.get_installation_tier() == "free"

    def test_expired_enterprise_license_graceful_degradation(self, monkeypatch):
        past_exp = datetime.now(timezone.utc) - timedelta(hours=1)
        token = _sign({"tier": "enterprise", "exp": int(past_exp.timestamp())})

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            assert license.get_installation_tier() == "free"

    def test_recently_expired_license_within_grace_period(self):
        past_exp = datetime.now(timezone.utc) - timedelta(minutes=30)
        token = _sign({"tier": "professional", "exp": int(past_exp.timestamp())})

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is False
        assert "expired" in error.lower()

    def test_license_expiring_soon_still_valid(self):
        future_exp = datetime.now(timezone.utc) + timedelta(hours=24)
        token = _sign({"tier": "enterprise", "exp": int(future_exp.timestamp())})

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is True
        assert tier == "enterprise"
        assert error is None


class TestInvalidLicenseHandling:
    """Test invalid license format and signature handling"""

    def setup_method(self):
        license.reset_cache()

    def test_completely_invalid_jwt_format(self, monkeypatch):
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", "not-a-jwt-token-at-all")

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            assert license.get_installation_tier() == "free"

    def test_jwt_with_wrong_signature(self, monkeypatch):
        # Sign with OTHER_PRIVATE_KEY but verify against TEST_PUBLIC_KEY.
        token = _sign({"tier": "enterprise"}, key=OTHER_PRIVATE_KEY)

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            assert license.get_installation_tier() == "free"

    def test_jwt_missing_required_tier_field(self):
        token = _sign({
            "email": "test@example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(days=365)).timestamp()),
        })

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is False
        assert tier is None
        assert "tier" in error.lower()

    def test_jwt_with_invalid_tier_value(self):
        token = _sign({"tier": "platinum"})  # Invalid tier name

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(token)

        assert valid is True
        assert tier == "free"  # Unknown tiers normalise to free

    def test_empty_license_key_string(self, monkeypatch):
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", "")

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'):
            assert license.get_installation_tier() == "free"

    def test_whitespace_only_license_key(self, monkeypatch):
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", "   \t\n   ")

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'):
            assert license.get_installation_tier() == "free"

    def test_malformed_base64_in_jwt(self):
        malformed_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.INVALID_BASE64.signature"

        with patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            valid, tier, error = license.validate_license_key(malformed_jwt)

        assert valid is False
        assert tier is None


class TestLicenseUpgradeDowngradeFlows:
    """Test license tier upgrade and downgrade scenarios"""

    def setup_method(self):
        license.reset_cache()

    def test_upgrade_free_to_professional_license(self):
        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            with patch.dict(os.environ, {"LICENSE_KEY": ""}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "free"

            professional_token = _sign({"tier": "professional"})
            with patch.dict(os.environ, {"LICENSE_KEY": professional_token}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "professional"

    def test_upgrade_professional_to_enterprise_license(self):
        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            professional_token = _sign({"tier": "professional"})
            with patch.dict(os.environ, {"LICENSE_KEY": professional_token}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "professional"

            enterprise_token = _sign({"tier": "enterprise"})
            with patch.dict(os.environ, {"LICENSE_KEY": enterprise_token}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "enterprise"

    def test_downgrade_enterprise_to_professional_license(self):
        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            enterprise_token = _sign({"tier": "enterprise"})
            with patch.dict(os.environ, {"LICENSE_KEY": enterprise_token}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "enterprise"

            professional_token = _sign({"tier": "professional"})
            with patch.dict(os.environ, {"LICENSE_KEY": professional_token}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "professional"

    def test_downgrade_professional_to_free_license(self):
        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            professional_token = _sign({"tier": "professional"})
            with patch.dict(os.environ, {"LICENSE_KEY": professional_token}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "professional"

            with patch.dict(os.environ, {"LICENSE_KEY": ""}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "free"

    def test_license_change_requires_cache_reset(self):
        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            professional_token = _sign({"tier": "professional"})
            with patch.dict(os.environ, {"LICENSE_KEY": professional_token}, clear=False):
                license.reset_cache()
                assert license.get_installation_tier() == "professional"

                # Change license without cache reset — cached tier wins.
                enterprise_token = _sign({"tier": "enterprise"})
                os.environ["LICENSE_KEY"] = enterprise_token
                assert license.get_installation_tier() == "professional"

                # Reset cache to pick up the new tier.
                license.reset_cache()
                assert license.get_installation_tier() == "enterprise"


class TestSelfHostedVsCloudMode:
    """Test behavior differences between self-hosted and cloud mode"""

    def setup_method(self):
        license.reset_cache()

    def test_cloud_mode_ignores_license_key(self, monkeypatch):
        enterprise_token = _sign({"tier": "enterprise"})

        monkeypatch.setenv("INSTALLATION_MODE", "cloud")
        monkeypatch.setenv("LICENSE_KEY", enterprise_token)

        with patch('license.config.INSTALLATION_MODE', 'cloud'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            assert license.get_installation_tier() == "free"

    def test_self_hosted_mode_uses_license_key(self, monkeypatch):
        enterprise_token = _sign({"tier": "enterprise"})

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", enterprise_token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            assert license.get_installation_tier() == "enterprise"

    def test_self_hosted_without_license_uses_free_tier(self, monkeypatch):
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.delenv("LICENSE_KEY", raising=False)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'):
            assert license.get_installation_tier() == "free"


class TestTierGateEnforcement:
    """Test that tier gates properly enforce limits"""

    def test_tier_limits_for_free_tier(self):
        from tier_service import TIER_LIMITS

        free_limits = TIER_LIMITS.get("free", {})
        assert free_limits.get("projects") == 3
        assert free_limits.get("repos_per_project") == 10
        assert free_limits.get("secrets_per_project") == 2
        assert free_limits.get("private_repos") is True
        assert free_limits.get("reusable_workflows") is True

    def test_tier_limits_for_professional_tier(self):
        from tier_service import TIER_LIMITS

        pro_limits = TIER_LIMITS.get("professional", {})
        assert pro_limits.get("projects") == 10
        assert pro_limits.get("repos_per_project") == 50
        assert pro_limits.get("secrets_per_project") == 10
        assert pro_limits.get("private_repos") is True
        assert pro_limits.get("reusable_workflows") is True

    def test_tier_limits_for_enterprise_tier(self):
        from tier_service import TIER_LIMITS

        enterprise_limits = TIER_LIMITS.get("enterprise", {})
        assert enterprise_limits.get("projects") is None
        assert enterprise_limits.get("repos_per_project") is None
        assert enterprise_limits.get("secrets_per_project") is None
        assert enterprise_limits.get("private_repos") is True
        assert enterprise_limits.get("reusable_workflows") is True


class TestLicenseCacheManagement:
    """Test license validation caching behavior"""

    def setup_method(self):
        license.reset_cache()

    def test_cache_persists_across_multiple_calls(self, monkeypatch):
        professional_token = _sign({"tier": "professional"})

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", professional_token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            assert license.get_installation_tier() == "professional"

            monkeypatch.setenv("LICENSE_KEY", "invalid")
            assert license.get_installation_tier() == "professional"

    def test_cache_reset_clears_state(self, monkeypatch):
        professional_token = _sign({"tier": "professional"})

        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("LICENSE_KEY", professional_token)

        with patch('license.config.INSTALLATION_MODE', 'self-hosted'), \
             patch.object(license, 'LICENSE_PUBLIC_KEY', TEST_PUBLIC_KEY):
            assert license.get_installation_tier() == "professional"

            license.reset_cache()

            enterprise_token = _sign({"tier": "enterprise"})
            monkeypatch.setenv("LICENSE_KEY", enterprise_token)

            assert license.get_installation_tier() == "enterprise"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
