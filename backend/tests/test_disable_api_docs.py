"""
Tests for DISABLE_API_DOCS configuration and API docs endpoint availability.
"""
import os
import sys
import importlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestIsApiDocsDisabled:
    """Unit tests for config.is_api_docs_disabled()."""

    def test_disabled_when_env_true(self, monkeypatch):
        """DISABLE_API_DOCS=true disables docs regardless of ENVIRONMENT."""
        monkeypatch.setenv("DISABLE_API_DOCS", "true")
        monkeypatch.setenv("ENVIRONMENT", "development")
        import config
        importlib.reload(config)
        assert config.API_DOCS_DISABLED is True

    def test_enabled_when_env_false(self, monkeypatch):
        """DISABLE_API_DOCS=false keeps docs enabled even in production."""
        monkeypatch.setenv("DISABLE_API_DOCS", "false")
        monkeypatch.setenv("ENVIRONMENT", "production")
        import config
        importlib.reload(config)
        assert config.API_DOCS_DISABLED is False

    def test_disabled_in_production_by_default(self, monkeypatch):
        """Docs auto-disable when ENVIRONMENT=production and no explicit flag."""
        monkeypatch.delenv("DISABLE_API_DOCS", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        import config
        importlib.reload(config)
        assert config.API_DOCS_DISABLED is True

    def test_enabled_in_development_by_default(self, monkeypatch):
        """Docs stay enabled when ENVIRONMENT=development and no explicit flag."""
        monkeypatch.delenv("DISABLE_API_DOCS", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        import config
        importlib.reload(config)
        assert config.API_DOCS_DISABLED is False

    def test_disabled_when_environment_unset(self, monkeypatch):
        """When ENVIRONMENT is unset it defaults to production, so docs disable."""
        monkeypatch.delenv("DISABLE_API_DOCS", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        import config
        importlib.reload(config)
        assert config.API_DOCS_DISABLED is True

    def test_case_insensitive_true(self, monkeypatch):
        """DISABLE_API_DOCS=True (mixed case) is treated as true."""
        monkeypatch.setenv("DISABLE_API_DOCS", "True")
        monkeypatch.setenv("ENVIRONMENT", "development")
        import config
        importlib.reload(config)
        assert config.API_DOCS_DISABLED is True


class TestApiDocsEndpoints:
    """Integration tests verifying docs endpoints respond based on config."""

    @pytest.fixture
    def _enable_docs(self, monkeypatch):
        monkeypatch.setenv("DISABLE_API_DOCS", "false")
        monkeypatch.setenv("ENVIRONMENT", "development")

    @pytest.fixture
    def _disable_docs(self, monkeypatch):
        monkeypatch.setenv("DISABLE_API_DOCS", "true")
        monkeypatch.setenv("ENVIRONMENT", "development")

    def test_docs_accessible_when_enabled(self, _enable_docs):
        importlib.reload(__import__("config"))
        import main
        importlib.reload(main)
        from fastapi.testclient import TestClient
        client = TestClient(main.app)
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200
        assert client.get("/openapi.json").status_code == 200

    def test_docs_404_when_disabled(self, _disable_docs):
        importlib.reload(__import__("config"))
        import main
        importlib.reload(main)
        from fastapi.testclient import TestClient
        client = TestClient(main.app)
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
