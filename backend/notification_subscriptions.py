"""
Notification subscriptions and delivery history endpoints (issue #1795, part of #1789).

Provides:
- GET    /api/notifications/subscriptions   — list subscriptions
- POST   /api/notifications/subscriptions   — create a subscription
- DELETE /api/notifications/subscriptions/{subscription_id} — remove a subscription
- GET    /api/notifications/deliveries      — recent delivery history (status + last failure)

All admin-only, matching the SMTP test-email endpoint (#1791).
"""

from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import WorkspaceMember, NotificationSubscription, NotificationDelivery, NotificationEvent, Project
from authorization import require_role
from email_sender import EMAIL_RE

router = APIRouter()

# Event types drift/campaign notifications can actually produce today.
# campaign.updated / campaign.closed are intentionally excluded — no
# campaign-editing or explicit-close endpoint exists yet (see campaign_notifications.py).
VALID_EVENT_TYPES = {
    "drift.detected",
    "drift.resolved",
    "drift.check_failed",
    "campaign.opened",
    "campaign.partially_failed",
    "campaign.completed",
    "campaign_pr.merged",
    "campaign_pr.closed",
    "campaign_pr.failed",
}


class SubscriptionCreate(BaseModel):
    recipient_email: str
    project_id: Optional[int] = None  # None = all projects
    event_types: Optional[List[str]] = None  # None = all event types
    notify_on_resolved: bool = True

    @field_validator("recipient_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not EMAIL_RE.match(value):
            raise ValueError("recipient_email must be a valid email address")
        return value

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value
        invalid = set(value) - VALID_EVENT_TYPES
        if invalid:
            raise ValueError(f"Unknown event type(s): {', '.join(sorted(invalid))}")
        return value


class SubscriptionResponse(BaseModel):
    subscription_id: int
    recipient_email: str
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    event_types: Optional[List[str]] = None
    notify_on_resolved: bool


class DeliveryResponse(BaseModel):
    delivery_id: int
    event_type: str
    project_id: int
    project_name: Optional[str] = None
    recipient_email: str
    status: str
    attempt_count: int
    last_error: Optional[str] = None
    created_at: str
    sent_at: Optional[str] = None


def _to_subscription_response(sub: NotificationSubscription, project_name: Optional[str]) -> SubscriptionResponse:
    return SubscriptionResponse(
        subscription_id=sub.subscription_id,
        recipient_email=sub.recipient_email,
        project_id=sub.project_id,
        project_name=project_name,
        event_types=sub.event_types.split(",") if sub.event_types else None,
        notify_on_resolved=sub.notify_on_resolved,
    )


@router.get("/api/notifications/subscriptions", response_model=List[SubscriptionResponse])
def list_subscriptions(
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    subs = db.query(NotificationSubscription).order_by(NotificationSubscription.created_at.desc()).all()
    project_ids = {s.project_id for s in subs if s.project_id is not None}
    projects_by_id = {}
    if project_ids:
        projects_by_id = {
            p.project_id: p.project_name
            for p in db.query(Project).filter(Project.project_id.in_(project_ids)).all()
        }
    return [_to_subscription_response(s, projects_by_id.get(s.project_id)) for s in subs]


@router.post(
    "/api/notifications/subscriptions",
    response_model=SubscriptionResponse,
    responses={404: {"description": "Project not found"}},
)
def create_subscription(
    body: SubscriptionCreate,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    project_name = None
    if body.project_id is not None:
        project = db.query(Project).filter(Project.project_id == body.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        project_name = project.project_name

    sub = NotificationSubscription(
        recipient_email=body.recipient_email,
        project_id=body.project_id,
        event_types=",".join(body.event_types) if body.event_types else None,
        notify_on_resolved=body.notify_on_resolved,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return _to_subscription_response(sub, project_name)


@router.delete(
    "/api/notifications/subscriptions/{subscription_id}",
    responses={404: {"description": "Subscription not found"}},
)
def delete_subscription(
    subscription_id: int,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    sub = db.query(NotificationSubscription).filter(
        NotificationSubscription.subscription_id == subscription_id
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    db.delete(sub)
    db.commit()
    return {"message": "Subscription removed"}


@router.get("/api/notifications/deliveries", response_model=List[DeliveryResponse])
def list_deliveries(
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
    limit: int = 50,
):
    limit = max(1, min(limit, 200))
    rows = (
        db.query(NotificationDelivery, NotificationEvent)
        .join(NotificationEvent, NotificationDelivery.event_id == NotificationEvent.event_id)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(limit)
        .all()
    )
    project_ids = {event.project_id for _, event in rows}
    projects_by_id = {}
    if project_ids:
        projects_by_id = {
            p.project_id: p.project_name
            for p in db.query(Project).filter(Project.project_id.in_(project_ids)).all()
        }
    return [
        DeliveryResponse(
            delivery_id=delivery.delivery_id,
            event_type=event.event_type,
            project_id=event.project_id,
            project_name=projects_by_id.get(event.project_id),
            recipient_email=delivery.recipient_email,
            status=delivery.status,
            attempt_count=delivery.attempt_count,
            last_error=delivery.last_error,
            created_at=delivery.created_at.isoformat() if delivery.created_at else "",
            sent_at=delivery.sent_at.isoformat() if delivery.sent_at else None,
        )
        for delivery, event in rows
    ]
