"""
Drift Settings Router for ActionsManager

Provides API endpoints for the global drift sweep configuration:
- GET /api/drift/settings — Read the current settings (any workspace member)
- PUT /api/drift/settings — Update them (admin only)

These replace the DRIFT_* environment variables. Reads are open to any member
because the per-project drift control needs the global default to label its
"inherit" option; only admins can change them.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from authorization import get_current_member, require_role
from database import get_db
from drift_worker import get_settings
from models import DriftSettings, WorkspaceMember

router = APIRouter()


class DriftSettingsSchema(BaseModel):
    """Global drift sweep settings. Bounds keep a mistyped value from either
    hammering the GitHub rate limit or silently stalling the sweep."""
    sweep_enabled: bool
    recheck_interval_minutes: int = Field(ge=1, le=10080)
    batch_size: int = Field(ge=1, le=50)
    poll_interval_seconds: int = Field(ge=10, le=3600)


@router.get("/api/drift/settings", response_model=DriftSettingsSchema)
def read_drift_settings(
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(get_current_member)],
):
    """Return the stored settings, or the built-in defaults if none are saved."""
    settings = get_settings(db)
    return DriftSettingsSchema(
        sweep_enabled=bool(settings.sweep_enabled),
        recheck_interval_minutes=settings.recheck_interval_minutes,
        batch_size=settings.batch_size,
        poll_interval_seconds=settings.poll_interval_seconds,
    )


@router.put("/api/drift/settings", response_model=DriftSettingsSchema)
def update_drift_settings(
    body: DriftSettingsSchema,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """Save the settings, creating the single row on first use."""
    settings = db.query(DriftSettings).first()
    if settings is None:
        settings = DriftSettings()
        db.add(settings)

    settings.sweep_enabled = body.sweep_enabled
    settings.recheck_interval_minutes = body.recheck_interval_minutes
    settings.batch_size = body.batch_size
    settings.poll_interval_seconds = body.poll_interval_seconds
    db.commit()

    return body
