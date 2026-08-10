"""
Tests for the webhook readiness check.

Webhooks need GitHub to reach *in*, which most self-hosted instances cannot do
without a tunnel or reverse proxy. Everything else in ActionsManager calls out
to GitHub and works fine without one, so an unreachable instance is a normal
configuration — not a fault.

This check exists so the UI can say "here is why this is unavailable, here is
how to fix it" instead of a webhook-driven feature appearing broken. The
assertions are about *what the user is told*, since that is the whole purpose.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """APP_URL is read at call time; the secret is a module constant.

    Deliberately no importlib.reload here: reloading workflows would leave the
    running app holding the *previous* module object, so any later test that
    patched workflows.<name> would patch something the app no longer uses.
    """
    monkeypatch.delenv("APP_URL", raising=False)
    monkeypatch.delenv("VITE_APP_URL", raising=False)


def _readiness(monkeypatch, app_url=None, secret=None):
    import workflows
    if app_url is not None:
        monkeypatch.setenv("APP_URL", app_url)
    monkeypatch.setattr(workflows, "GITHUB_PR_WEBHOOK_SECRET", secret or "")
    return workflows.get_webhook_readiness()


class TestUnreachableInstances:
    def test_default_localhost_is_not_reachable(self, monkeypatch):
        """The out-of-the-box config: nothing set at all."""
        result = _readiness(monkeypatch, secret="s3cret")

        assert result["ready"] is False
        assert result["public_url_configured"] is False
        assert result["webhook_url"] is None
        assert any("only resolves on the machine" in b for b in result["blockers"])

    @pytest.mark.parametrize("url", [
        "http://192.168.1.100:8080",   # RFC1918
        "http://10.0.0.5:8080",
        "http://172.16.4.4:8080",
        "http://169.254.10.1:8080",    # link-local
    ])
    def test_private_addresses_are_not_reachable(self, url, monkeypatch):
        result = _readiness(monkeypatch, app_url=url, secret="s3cret")

        assert result["ready"] is False
        assert any("private address" in b for b in result["blockers"])

    def test_every_unready_result_points_at_the_docs(self, monkeypatch):
        """The entire point: never just say no."""
        result = _readiness(monkeypatch)

        assert result["ready"] is False
        assert result["docs_url"].startswith("https://actionsmanager.io/")
        assert "WEBHOOK_ENDPOINT" in result["docs_url"]


class TestReachableInstances:
    @pytest.mark.parametrize("url", [
        "https://actions.example.com",          # Cloudflare Tunnel / reverse proxy
        "https://am.tail1234.ts.net",           # Tailscale Funnel
        "https://actions.example.com:8443",
    ])
    def test_public_hostnames_are_accepted(self, url, monkeypatch):
        result = _readiness(monkeypatch, app_url=url, secret="s3cret")

        assert result["ready"] is True
        assert result["public_url_configured"] is True
        assert result["webhook_url"] == f"{url}/webhooks/github"
        assert result["blockers"] == []

    def test_a_public_ip_is_accepted(self, monkeypatch):
        # A genuinely routable address. Note 203.0.113.x (TEST-NET-3) would
        # *not* qualify — Python classifies the RFC 5737 documentation ranges
        # as private, which is correct: they are not routable either.
        result = _readiness(monkeypatch, app_url="https://8.8.8.8", secret="s3cret")

        assert result["public_url_configured"] is True

    def test_documentation_ranges_are_rejected(self, monkeypatch):
        result = _readiness(monkeypatch, app_url="https://203.0.113.10", secret="s3cret")

        assert result["public_url_configured"] is False


class TestSecretIsSeparateFromReachability:
    def test_reachable_but_no_secret_is_not_ready(self, monkeypatch):
        result = _readiness(monkeypatch, app_url="https://actions.example.com")

        assert result["ready"] is False
        # The URL is fine, so still show it — the user only needs the secret.
        assert result["public_url_configured"] is True
        assert result["webhook_url"] == "https://actions.example.com/webhooks/github"
        assert any("GITHUB_PR_WEBHOOK_SECRET" in b for b in result["blockers"])

    def test_missing_secret_says_nothing_is_exposed(self, monkeypatch):
        """An operator reading this must not think they have a hole open."""
        result = _readiness(monkeypatch, app_url="https://actions.example.com")

        secret_blocker = next(b for b in result["blockers"] if "GITHUB_PR_WEBHOOK_SECRET" in b)
        assert "rejected" in secret_blocker

    def test_both_missing_reports_both(self, monkeypatch):
        result = _readiness(monkeypatch)

        assert len(result["blockers"]) == 2

    def test_the_secret_value_is_never_returned(self, monkeypatch):
        result = _readiness(monkeypatch, app_url="https://actions.example.com", secret="super-secret-value")

        assert "super-secret-value" not in str(result)
