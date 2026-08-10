"""
Shared notification event emission + subscription fan-out (code review fix, part of #1789).

Both drift_notifications.py and campaign_notifications.py call into this
module instead of each defining their own dedup-check-then-insert logic.

This is also where the previously-missing NotificationEvent ->
NotificationDelivery fan-out happens: without it, events were recorded but
nothing ever created a delivery row for a matching subscription, so
notification_worker.py's outbox was always empty and no subscription-driven
email was ever actually sent (only the manual Send Test Email button
worked).
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from models import NotificationEvent, NotificationSubscription, NotificationDelivery


def _subscription_matches(sub: NotificationSubscription, project_id: int, event_type: str) -> bool:
    if sub.project_id is not None and sub.project_id != project_id:
        return False
    if sub.event_types:
        allowed = {e.strip() for e in sub.event_types.split(",")}
        if event_type not in allowed:
            return False
    if event_type == "drift.resolved" and not sub.notify_on_resolved:
        return False
    return True


def emit_notification_event(
    db: Session, project_id: int, event_type: str, dedup_key: str, payload: dict
) -> Optional[NotificationEvent]:
    """Insert a deduplicated NotificationEvent and fan it out to matching
    subscriptions as pending NotificationDelivery rows.

    Returns None (no-op) if an event with this dedup_key already exists —
    the caller's repeated-scan/repeated-read case.
    """
    existing = db.query(NotificationEvent).filter(NotificationEvent.dedup_key == dedup_key).first()
    if existing:
        return None

    event = NotificationEvent(
        project_id=project_id,
        event_type=event_type,
        dedup_key=dedup_key,
        payload=json.dumps(payload),
    )
    db.add(event)
    db.flush()  # populate event.event_id for the deliveries below

    subscriptions = db.query(NotificationSubscription).all()
    for sub in subscriptions:
        if _subscription_matches(sub, project_id, event_type):
            db.add(NotificationDelivery(event_id=event.event_id, recipient_email=sub.recipient_email))

    return event
