"""
Notification SMTP endpoints for ActionsManager.xyz

Provides:
- POST /api/notifications/test-email — sends a test email using the
  installation's SMTP_* env var configuration, surfacing specific
  connection/TLS/auth errors instead of a generic failure. Admin-only.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from models import WorkspaceMember
from authorization import require_role
from email_sender import EMAIL_RE, get_smtp_config, send_email, SMTPNotConfiguredError, SMTPSendError

router = APIRouter()


class TestEmailRequest(BaseModel):
    recipient_email: str

    @field_validator("recipient_email")
    @classmethod
    def validate_recipient_email(cls, value: str) -> str:
        if not EMAIL_RE.match(value):
            raise ValueError("recipient_email must be a valid email address")
        return value


@router.post(
    "/api/notifications/test-email",
    responses={
        400: {"description": "SMTP is not configured"},
        502: {"description": "SMTP server rejected the request"},
    },
)
def send_test_email(
    body: TestEmailRequest,
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """Send a test email to confirm the installation's SMTP configuration works."""
    try:
        config = get_smtp_config()
    except SMTPNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        send_email(
            to_address=body.recipient_email,
            subject="ActionsManager test email",
            body="This is a test email from ActionsManager confirming your SMTP configuration is working.",
            config=config,
        )
    except SMTPSendError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"message": f"Test email sent to {body.recipient_email}"}
