"""
Tests for the SMTP email transport (issue #1791, part of #1789).

Mocks smtplib.SMTP at the boundary — no fake SMTP server needed to verify
config resolution, TLS/auth/connect handling, and specific error surfacing.
"""

import smtplib
import ssl
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import email_sender
from email_sender import (
    get_smtp_config,
    send_email,
    SMTPConfig,
    SMTPNotConfiguredError,
    SMTPSendError,
)


@pytest.fixture(autouse=True)
def clean_smtp_env(monkeypatch):
    for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_USE_TLS", "SMTP_FROM_ADDRESS", "SMTP_FROM_NAME"):
        monkeypatch.delenv(var, raising=False)


class TestGetSmtpConfig:
    def test_raises_when_host_missing(self, monkeypatch):
        monkeypatch.setenv("SMTP_FROM_ADDRESS", "notify@example.com")
        with pytest.raises(SMTPNotConfiguredError):
            get_smtp_config()

    def test_raises_when_from_address_missing(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        with pytest.raises(SMTPNotConfiguredError):
            get_smtp_config()

    def test_defaults_port_587_and_tls_enabled(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM_ADDRESS", "notify@example.com")
        config = get_smtp_config()
        assert config.port == 587
        assert config.use_tls is True

    def test_use_tls_false_is_honored(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM_ADDRESS", "notify@example.com")
        monkeypatch.setenv("SMTP_USE_TLS", "false")
        config = get_smtp_config()
        assert config.use_tls is False

    def test_reads_all_fields(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "2525")
        monkeypatch.setenv("SMTP_USERNAME", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")
        monkeypatch.setenv("SMTP_FROM_ADDRESS", "notify@example.com")
        monkeypatch.setenv("SMTP_FROM_NAME", "ActionsManager")
        config = get_smtp_config()
        assert config == SMTPConfig(
            host="smtp.example.com", port=2525, username="user", password="pass",
            use_tls=True, from_address="notify@example.com", from_name="ActionsManager",
        )


class TestSendEmail:
    def _config(self, **overrides):
        base = dict(
            host="smtp.example.com", port=587, username="user", password="pass",
            use_tls=True, from_address="notify@example.com", from_name="ActionsManager",
        )
        base.update(overrides)
        return SMTPConfig(**base)

    def test_successful_send_calls_starttls_login_sendmail(self):
        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            send_email("to@example.com", "Subject", "Body", config=self._config())

            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("user", "pass")
            mock_server.sendmail.assert_called_once()
            args = mock_server.sendmail.call_args[0]
            assert args[0] == "notify@example.com"
            assert args[1] == ["to@example.com"]

    def test_skips_login_when_no_credentials(self):
        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            send_email("to@example.com", "Subject", "Body", config=self._config(username=None, password=None))

            mock_server.login.assert_not_called()

    def test_skips_starttls_when_tls_disabled(self):
        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            send_email("to@example.com", "Subject", "Body", config=self._config(use_tls=False))

            mock_server.starttls.assert_not_called()

    def test_auth_error_maps_to_specific_message(self):
        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            with pytest.raises(SMTPSendError, match="authentication failed"):
                send_email("to@example.com", "Subject", "Body", config=self._config())

    def test_tls_error_maps_to_specific_message(self):
        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.starttls.side_effect = ssl.SSLError("certificate verify failed")
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            with pytest.raises(SMTPSendError, match="TLS handshake failed"):
                send_email("to@example.com", "Subject", "Body", config=self._config())

    def test_connection_error_maps_to_specific_message(self):
        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_smtp_cls.side_effect = ConnectionRefusedError("connection refused")

            with pytest.raises(SMTPSendError, match="Could not connect to SMTP server"):
                send_email("to@example.com", "Subject", "Body", config=self._config())

    def test_generic_smtp_exception_maps_to_rejection_message(self):
        with patch.object(email_sender.smtplib, "SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_server.sendmail.side_effect = smtplib.SMTPSenderRefused(550, b"refused", "notify@example.com")
            mock_smtp_cls.return_value.__enter__.return_value = mock_server

            with pytest.raises(SMTPSendError, match="SMTP server rejected the request"):
                send_email("to@example.com", "Subject", "Body", config=self._config())
