"""
Tests for APP_URL startup validation in mode_validation.py.

Covers the resolve_app_url() helper and the _collect_app_url_violations()
function that enforces:
  - only http:// and https:// schemes
  - http:// on loopback hosts passes without ALLOW_INSECURE_HTTP
  - http:// on non-loopback hosts requires ALLOW_INSECURE_HTTP=true
  - https:// always passes
  - trailing slashes don't produce double-slashed derived URLs
  - no APP_URL → defaults to http://localhost:8080
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# Env vars that could leak from the host and affect results.
_URL_VARS = (
    "APP_URL",
    "VITE_APP_URL",
    "ALLOW_INSECURE_HTTP",
    "INSTALLATION_MODE",
)


def _reload(monkeypatch, env: dict):
    """Clear URL-related env vars, apply *env*, and reload mode_validation."""
    for var in _URL_VARS:
        monkeypatch.setenv(var, "")
    monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import config
    importlib.reload(config)
    import mode_validation
    importlib.reload(mode_validation)
    return mode_validation


# --------------------------------------------------------------------------- #
# resolve_app_url
# --------------------------------------------------------------------------- #


class TestResolveAppUrl:

    def test_no_url_defaults_to_localhost(self, monkeypatch):
        mv = _reload(monkeypatch, {})
        assert mv.resolve_app_url() == "http://localhost:8080"

    def test_app_url_takes_priority_over_vite(self, monkeypatch):
        mv = _reload(monkeypatch, {
            "APP_URL": "https://primary.example.com",
            "VITE_APP_URL": "https://deprecated.example.com",
        })
        assert mv.resolve_app_url() == "https://primary.example.com"

    def test_vite_app_url_used_when_app_url_unset(self, monkeypatch):
        mv = _reload(monkeypatch, {
            "VITE_APP_URL": "https://deprecated.example.com",
        })
        assert mv.resolve_app_url() == "https://deprecated.example.com"

    def test_trailing_slash_stripped(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "https://example.com/"})
        assert mv.resolve_app_url() == "https://example.com"


# --------------------------------------------------------------------------- #
# HTTPS — always accepted
# --------------------------------------------------------------------------- #


class TestHttpsAlwaysAccepted:

    def test_https_any_host(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "https://actions.example.com"})
        mv.validate_startup_configuration()

    def test_https_with_port(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "https://10.0.0.5:8443"})
        mv.validate_startup_configuration()


# --------------------------------------------------------------------------- #
# HTTP + loopback — accepted without ALLOW_INSECURE_HTTP
# --------------------------------------------------------------------------- #


class TestHttpLoopbackAccepted:

    @pytest.mark.parametrize("host", [
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
    ])
    def test_http_loopback_no_opt_in(self, monkeypatch, host):
        if ":" in host and not host.startswith("["):
            # IPv6 — urlsplit needs brackets
            url = f"http://[{host}]:8080"
        else:
            url = f"http://{host}:8080"
        mv = _reload(monkeypatch, {"APP_URL": url})
        mv.validate_startup_configuration()

    def test_http_localhost_no_port(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "http://localhost"})
        mv.validate_startup_configuration()


# --------------------------------------------------------------------------- #
# HTTP + non-loopback — requires ALLOW_INSECURE_HTTP
# --------------------------------------------------------------------------- #


class TestHttpNonLoopbackBlocked:

    def test_non_loopback_without_opt_in_fails(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "http://192.168.1.50:8080"})
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("ALLOW_INSECURE_HTTP" in v for v in exc.value.violations)
        assert any("192.168.1.50" in v for v in exc.value.violations)

    def test_non_loopback_with_opt_in_passes(self, monkeypatch):
        mv = _reload(monkeypatch, {
            "APP_URL": "http://192.168.1.50:8080",
            "ALLOW_INSECURE_HTTP": "true",
        })
        mv.validate_startup_configuration()

    def test_domain_without_opt_in_fails(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "http://actions.example.com"})
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("ALLOW_INSECURE_HTTP" in v for v in exc.value.violations)


# --------------------------------------------------------------------------- #
# Invalid/unsupported schemes
# --------------------------------------------------------------------------- #


class TestInvalidScheme:

    def test_ftp_rejected(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "ftp://files.example.com"})
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("unsupported scheme" in v for v in exc.value.violations)

    def test_ftp_rejected_despite_allow_insecure(self, monkeypatch):
        mv = _reload(monkeypatch, {
            "APP_URL": "ftp://files.example.com",
            "ALLOW_INSECURE_HTTP": "true",
        })
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("unsupported scheme" in v for v in exc.value.violations)

    def test_no_scheme_rejected(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "example.com:8080"})
        with pytest.raises(mv.ModeValidationError) as exc:
            mv.validate_startup_configuration()
        assert any("unsupported scheme" in v for v in exc.value.violations)


# --------------------------------------------------------------------------- #
# Default (no APP_URL) — accepted without opt-in
# --------------------------------------------------------------------------- #


class TestDefaultAccepted:

    def test_no_url_boots_fine(self, monkeypatch):
        mv = _reload(monkeypatch, {})
        mv.validate_startup_configuration()


# --------------------------------------------------------------------------- #
# Trailing slash — no double-slash in derived URLs
# --------------------------------------------------------------------------- #


class TestTrailingSlash:

    def test_trailing_slash_stripped_in_resolve(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "https://example.com/"})
        assert not mv.resolve_app_url().endswith("/")

    def test_multiple_trailing_slashes_stripped(self, monkeypatch):
        mv = _reload(monkeypatch, {"APP_URL": "https://example.com///"})
        resolved = mv.resolve_app_url()
        assert not resolved.endswith("/")
