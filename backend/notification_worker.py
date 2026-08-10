"""
Notification delivery worker (issue #1792, part of #1789).

An in-process asyncio polling loop — no Celery/APScheduler/Redis — started
at FastAPI startup and stopped at shutdown. Single-instance assumption for
v1: this app has no multi-replica deployment today, so no row-locking is
needed; revisit only if a multi-replica cloud deployment ships.

Producers (drift/campaign instrumentation in later issues) write rows to
notification_events/notification_deliveries; this module just drains the
outbox.
"""

import asyncio
import contextlib
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from models import NotificationDelivery, NotificationEvent, NotificationSettings
from email_sender import send_email, get_smtp_config, SMTPNotConfiguredError, SMTPSendError

MAX_ATTEMPTS = 5
BASE_BACKOFF_MINUTES = 2
MAX_BACKOFF_MINUTES = 60
DEFAULT_POLL_INTERVAL_SECONDS = 30


def _backoff_delay(attempt_count: int) -> timedelta:
    minutes = min(BASE_BACKOFF_MINUTES * (2 ** max(attempt_count - 1, 0)), MAX_BACKOFF_MINUTES)
    return timedelta(minutes=minutes)


def _build_message(event: NotificationEvent) -> tuple[str, str]:
    subject = f"ActionsManager notification: {event.event_type}"
    try:
        payload = json.loads(event.payload)
    except (TypeError, ValueError):
        payload = {}
    lines = [f"Event: {event.event_type}", f"Project ID: {event.project_id}", ""]
    lines += [f"{key}: {value}" for key, value in payload.items()]
    return subject, "\n".join(lines)


def _due_deliveries(db: Session, now: datetime):
    return (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.status == "pending")
        .filter(
            (NotificationDelivery.next_attempt_at.is_(None))
            | (NotificationDelivery.next_attempt_at <= now)
        )
        .all()
    )


def _notifications_enabled(db: Session) -> bool:
    """Global kill switch — defaults to enabled if no NotificationSettings row exists."""
    settings = db.query(NotificationSettings).first()
    return settings is None or settings.notifications_enabled


def deliver_pending_notifications(db: Session, now: Optional[datetime] = None) -> int:
    """Attempt delivery of every due, pending notification. Returns the number processed."""
    if not _notifications_enabled(db):
        return 0

    now = now or datetime.now(timezone.utc)

    try:
        config = get_smtp_config()
    except SMTPNotConfiguredError:
        config = None

    deliveries = _due_deliveries(db, now)
    for delivery in deliveries:
        _process_delivery(db, delivery, config, now)
    return len(deliveries)


def _process_delivery(db: Session, delivery: NotificationDelivery, config, now: datetime) -> None:
    event = db.query(NotificationEvent).filter(NotificationEvent.event_id == delivery.event_id).first()
    if event is None:
        delivery.status = "failed"
        delivery.last_error = "Notification event no longer exists"
        db.commit()
        return

    if config is None:
        _record_failure(db, delivery, "SMTP is not configured", now)
        return

    subject, body = _build_message(event)
    try:
        send_email(delivery.recipient_email, subject, body, config=config)
    except SMTPSendError as exc:
        _record_failure(db, delivery, str(exc), now)
        return

    delivery.status = "sent"
    delivery.sent_at = now
    delivery.last_error = None
    db.commit()


def _record_failure(db: Session, delivery: NotificationDelivery, error: str, now: datetime) -> None:
    delivery.attempt_count += 1
    delivery.last_error = error
    if delivery.attempt_count >= MAX_ATTEMPTS:
        delivery.status = "failed"
    else:
        delivery.next_attempt_at = now + _backoff_delay(delivery.attempt_count)
    db.commit()


async def notification_worker_loop(
    session_factory: Callable[[], Session],
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
) -> None:
    """Sleep-then-poll loop. Sleeps first so a task cancelled shortly after
    startup (e.g. a short-lived test lifespan) never touches the database."""
    loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(poll_interval_seconds)
        try:
            db = session_factory()
            try:
                # deliver_pending_notifications does blocking smtplib I/O (up to
                # its 10s-per-connection timeout); running it directly here would
                # stall every other request on this process's shared event loop.
                await loop.run_in_executor(None, deliver_pending_notifications, db)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 - a bad iteration must never kill the worker
            print(f"⚠️ Notification worker iteration failed: {exc}", file=sys.stderr, flush=True)


def start_notification_worker(session_factory: Callable[[], Session]) -> asyncio.Task:
    return asyncio.create_task(notification_worker_loop(session_factory))


async def stop_notification_worker(task: asyncio.Task) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
