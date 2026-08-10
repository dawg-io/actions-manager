"""
SMTP email transport for ActionsManager notifications.

Configuration is env-var only (SMTP_HOST/PORT/USERNAME/PASSWORD/USE_TLS/
FROM_ADDRESS/FROM_NAME) — matches every other self-hosted config in this app.
No DB-backed settings: one installation sends through one SMTP account;
recipients are handled separately via notification_subscriptions.
"""

import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Optional

# Shared with notification_subscriptions.py's SubscriptionCreate validator so
# the same address is never accepted for a subscription but rejected by the
# Send Test Email endpoint (or vice versa).
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


class SMTPNotConfiguredError(Exception):
    """Raised when required SMTP env vars are missing."""


class SMTPSendError(Exception):
    """Raised when the SMTP server rejects the connection, TLS handshake, auth, or send."""


@dataclass
class SMTPConfig:
    host: str
    port: int
    username: Optional[str]
    password: Optional[str]
    use_tls: bool
    from_address: str
    from_name: Optional[str]


def get_smtp_config() -> SMTPConfig:
    """Read SMTP configuration from environment variables. Raises SMTPNotConfiguredError if incomplete."""
    host = os.environ.get("SMTP_HOST")
    from_address = os.environ.get("SMTP_FROM_ADDRESS")
    if not host or not from_address:
        raise SMTPNotConfiguredError(
            "SMTP is not configured: SMTP_HOST and SMTP_FROM_ADDRESS environment variables are required."
        )
    return SMTPConfig(
        host=host,
        port=int(os.environ.get("SMTP_PORT", "587")),
        username=os.environ.get("SMTP_USERNAME") or None,
        password=os.environ.get("SMTP_PASSWORD") or None,
        use_tls=os.environ.get("SMTP_USE_TLS", "true").strip().lower() not in ("false", "0", "no"),
        from_address=from_address,
        from_name=os.environ.get("SMTP_FROM_NAME") or None,
    )


def _build_message(cfg: SMTPConfig, to_address: str, subject: str, body: str) -> str:
    from_header = f"{cfg.from_name} <{cfg.from_address}>" if cfg.from_name else cfg.from_address
    message = MIMEText(body, "plain")
    message["Subject"] = subject
    message["From"] = from_header
    message["To"] = to_address
    return message.as_string()


def send_email(to_address: str, subject: str, body: str, config: Optional[SMTPConfig] = None) -> None:
    """Send a plain-text email. Raises SMTPSendError with a specific, user-facing reason on failure."""
    cfg = config or get_smtp_config()
    raw_message = _build_message(cfg, to_address, subject, body)

    try:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=10) as server:
            if cfg.use_tls:
                server.starttls()
            if cfg.username and cfg.password:
                server.login(cfg.username, cfg.password)
            server.sendmail(cfg.from_address, [to_address], raw_message)
    except smtplib.SMTPAuthenticationError as exc:
        raise SMTPSendError(f"SMTP authentication failed: {exc}") from exc
    except ssl.SSLError as exc:
        raise SMTPSendError(f"TLS handshake failed: {exc}") from exc
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as exc:
        raise SMTPSendError(f"Could not connect to SMTP server {cfg.host}:{cfg.port}: {exc}") from exc
    except smtplib.SMTPException as exc:
        # NOTE: smtplib.SMTPException subclasses OSError, so this must be
        # caught before the bare OSError branch below or protocol-level
        # errors (e.g. SMTPSenderRefused) get mislabeled as connection failures.
        raise SMTPSendError(f"SMTP server rejected the request: {exc}") from exc
    except OSError as exc:
        raise SMTPSendError(f"Could not connect to SMTP server {cfg.host}:{cfg.port}: {exc}") from exc
