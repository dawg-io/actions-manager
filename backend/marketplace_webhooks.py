"""
GitHub Marketplace Webhook Handler

Handles GitHub Marketplace webhook events for billing and subscription management:
- marketplace_purchase: purchased, cancelled, pending_change, pending_change_cancelled
- Individual webhook events for plan changes

Includes:
- Webhook signature verification
- Event payload storage and auditing
- Account tier updates based on webhook events
- Retry handling for failed processing
"""

import os
import hmac
import hashlib
import json
import ipaddress
from datetime import datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from database import SessionLocal, get_db
from models import Account, MarketplaceWebhookEvent, WorkspaceMember
from authorization import require_role

router = APIRouter()

# GitHub webhook secret for signature verification
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()

# Use stubbed endpoint for testing
USE_STUBBED_ENDPOINT = os.getenv("USE_STUBBED_MARKETPLACE_API", "true").lower() == "true"

# Debug mode - Defaults to false for production safety
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# GitHub webhook IP ranges (from https://api.github.com/meta)
# For production, these should be periodically updated
GITHUB_WEBHOOK_IPS = os.getenv("GITHUB_WEBHOOK_IPS", "").strip()
VERIFY_WEBHOOK_IP = os.getenv("VERIFY_WEBHOOK_IP", "false").lower() == "true"

# Rate limiting for webhook endpoint (requests per minute)
WEBHOOK_RATE_LIMIT = int(os.getenv("WEBHOOK_RATE_LIMIT", "60"))
RATE_LIMIT_WINDOW_SECONDS = 60  # Time window for rate limiting
webhook_request_times = {}  # Dictionary to track request times by IP


def debug_log(message: str):
    """Log debug messages if debug mode is enabled"""
    if DEBUG_MODE:
        print(f"[MARKETPLACE_WEBHOOK] {message}")




def verify_source_ip(source_ip: str) -> bool:
    """
    Verify that webhook request comes from GitHub's IP ranges.
    
    Args:
        source_ip: Source IP address from request
        
    Returns:
        bool: True if IP is from GitHub, False otherwise
    """
    if not VERIFY_WEBHOOK_IP:
        debug_log("ℹ️  IP verification disabled (VERIFY_WEBHOOK_IP=false)")
        return True
    
    if not GITHUB_WEBHOOK_IPS:
        debug_log("⚠️ Warning: GITHUB_WEBHOOK_IPS not configured, skipping IP verification")
        return True
    
    if not source_ip:
        debug_log("❌ Error: No source IP provided")
        return False
    
    try:
        client_ip = ipaddress.ip_address(source_ip)
        
        # Check against configured IP ranges
        allowed_ranges = [r.strip() for r in GITHUB_WEBHOOK_IPS.split(',') if r.strip()]
        
        for ip_range in allowed_ranges:
            try:
                network = ipaddress.ip_network(ip_range, strict=False)
                if client_ip in network:
                    debug_log(f"✅ Source IP {source_ip} verified (in range {ip_range})")
                    return True
            except ValueError as e:
                debug_log(f"⚠️ Invalid IP range in config: {ip_range} - {e}")
                continue
        
        debug_log(f"❌ Source IP {source_ip} not in allowed ranges")
        return False
        
    except ValueError as e:
        debug_log(f"❌ Invalid source IP format: {source_ip} - {e}")
        return False


def check_rate_limit(source_ip: str) -> bool:
    """
    Check if webhook endpoint rate limit is exceeded for given IP.
    
    Args:
        source_ip: Source IP address
        
    Returns:
        bool: True if request is allowed, False if rate limit exceeded
    """
    now = datetime.now(timezone.utc)
    
    # Clean up old entries (older than rate limit window)
    cutoff_time = now.timestamp() - RATE_LIMIT_WINDOW_SECONDS
    for ip in list(webhook_request_times.keys()):
        webhook_request_times[ip] = [
            t for t in webhook_request_times.get(ip, []) 
            if t > cutoff_time
        ]
        if not webhook_request_times[ip]:
            del webhook_request_times[ip]
    
    # Check rate limit for this IP
    request_times = webhook_request_times.get(source_ip, [])
    
    if len(request_times) >= WEBHOOK_RATE_LIMIT:
        debug_log(f"❌ Rate limit exceeded for {source_ip}: {len(request_times)} requests in last minute")
        return False
    
    # Add current request time
    webhook_request_times.setdefault(source_ip, []).append(now.timestamp())
    
    if len(request_times) + 1 > WEBHOOK_RATE_LIMIT * 0.8:  # Warn at 80%
        debug_log(f"⚠️ Rate limit warning for {source_ip}: {len(request_times) + 1}/{WEBHOOK_RATE_LIMIT} requests")
    
    return True


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify GitHub webhook signature using HMAC SHA-256.
    
    Args:
        payload: Raw request body bytes
        signature: X-Hub-Signature-256 header value
        
    Returns:
        bool: True if signature is valid, False otherwise
    """
    if not GITHUB_WEBHOOK_SECRET:
        debug_log("❌ GITHUB_WEBHOOK_SECRET is not set — rejecting webhook to prevent unauthenticated billing changes.")
        return False
    
    if not signature:
        debug_log("❌ Error: No signature provided in webhook request")
        return False
    
    # GitHub sends signature as "sha256=<hash>"
    if not signature.startswith("sha256="):
        debug_log(f"❌ Error: Invalid signature format: {signature}")
        return False
    
    expected_signature = signature[7:]  # Remove "sha256=" prefix
    
    # Calculate HMAC
    mac = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode('utf-8'),
        msg=payload,
        digestmod=hashlib.sha256
    )
    calculated_signature = mac.hexdigest()
    
    # Constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(calculated_signature, expected_signature)
    
    if is_valid:
        debug_log("✅ Webhook signature verified successfully")
    else:
        debug_log("❌ Webhook signature verification failed")
        debug_log(f"   Expected: {expected_signature}")
        debug_log(f"   Calculated: {calculated_signature}")
    
    return is_valid


def store_webhook_event(
    db: Session,
    event_type: str,
    action: Optional[str],
    payload: dict,
    signature: Optional[str],
    source_ip: Optional[str] = None,
    headers: Optional[dict] = None
) -> MarketplaceWebhookEvent:
    """
    Store webhook event in database for auditing.
    
    Args:
        db: Database session
        event_type: Type of webhook event
        action: Action within the event (for marketplace_purchase events)
        payload: Webhook payload dictionary
        signature: Webhook signature
        source_ip: Source IP address of webhook request
        headers: Request headers dictionary
        
    Returns:
        MarketplaceWebhookEvent: Created event record
    """
    # Extract relevant information from payload
    marketplace_purchase = payload.get("marketplace_purchase", {})
    account = marketplace_purchase.get("account", {})
    plan = marketplace_purchase.get("plan", {})
    
    github_user = account.get("login")
    marketplace_account_id = account.get("id")
    plan_name = plan.get("name")
    
    # Extract effective_date if present (ISO 8601 format)
    effective_date = payload.get("effective_date")
    effective_date_obj = None
    if effective_date:
        try:
            # Handle multiple ISO 8601 formats
            # GitHub typically sends: "2025-11-02T00:00:00Z"
            # But also support: "2025-11-02T00:00:00+00:00", "2025-11-02T00:00:00"
            if isinstance(effective_date, str):
                # Replace 'Z' with '+00:00' for fromisoformat compatibility
                date_str = effective_date.replace('Z', '+00:00')
                effective_date_obj = datetime.fromisoformat(date_str)
            debug_log(f"📅 Effective date: {effective_date_obj}")
        except (ValueError, AttributeError, TypeError) as e:
            debug_log(f"⚠️ Warning: Could not parse effective_date: {effective_date} - {str(e)}")
    
    # Create webhook event record
    webhook_event = MarketplaceWebhookEvent(
        event_type=event_type,
        action=action,
        github_user=github_user,
        marketplace_account_id=marketplace_account_id,
        plan_name=plan_name,
        effective_date=effective_date_obj,
        payload=json.dumps(payload),
        signature=signature,
        source_ip=source_ip,
        headers=json.dumps(headers) if headers else None,
        processed=False,
        retry_count=0
    )
    
    db.add(webhook_event)
    db.commit()
    db.refresh(webhook_event)
    
    debug_log(f"✅ Stored webhook event: {event_type} (action: {action}) for user: {github_user}")
    
    return webhook_event


def _check_admin_override(user: Account, github_user: str) -> bool:
    """
    Check if admin override is active for a user.
    
    Args:
        user: User account
        github_user: GitHub username (for logging)
        
    Returns:
        bool: True if admin override is active, False otherwise
    """
    if not user.admin_override:
        return False
    
    if user.admin_override_until is None:
        # Indefinite override
        debug_log(f"🔒 Admin override active (indefinite) for {github_user}, will not update account_type")
        return True
    
    # Ensure both datetimes are timezone-aware
    override_until = user.admin_override_until
    if override_until.tzinfo is None:
        override_until = override_until.replace(tzinfo=timezone.utc)
    
    if override_until > datetime.now(timezone.utc):
        # Override still valid
        debug_log(f"🔒 Admin override active until {user.admin_override_until} for {github_user}, will not update account_type")
        return True
    
    # Override expired
    debug_log(f"⏰ Admin override expired for {github_user}, clearing override")
    user.admin_override = False
    user.admin_override_until = None
    return False


def _handle_plan_purchase_or_change(
    user: Account,
    marketplace_purchase: dict,
    plan_info: dict,
    marketplace_account_id: int,
    admin_override_active: bool,
    action: str,
    github_user: str
):
    """
    Handle plan purchase or change actions.
    
    Args:
        user: User account to update
        marketplace_purchase: Marketplace purchase data
        plan_info: Plan information
        marketplace_account_id: Marketplace account ID
        admin_override_active: Whether admin override is active
        action: Action type (purchased or changed)
        github_user: GitHub username (for logging)
    """
    plan_name = plan_info.get("name", "unknown")
    on_free_trial = marketplace_purchase.get("on_free_trial", False)
    
    # Log free trial status
    if on_free_trial:
        free_trial_ends_on = marketplace_purchase.get("free_trial_ends_on")
        debug_log(f"🎁 Free trial active, ends on: {free_trial_ends_on}")
    
    # Update marketplace metadata (always update these)
    user.marketplace_plan = plan_name
    user.marketplace_account_id = marketplace_account_id
    user.marketplace_unit_count = marketplace_purchase.get("unit_count")
    user.marketplace_on_free_trial = on_free_trial
    
    # Parse next billing date
    next_billing_date = marketplace_purchase.get("next_billing_date")
    if next_billing_date:
        user.marketplace_next_billing_date = datetime.fromisoformat(
            next_billing_date.replace('Z', '+00:00')
        )
    
    user.marketplace_updated_at = datetime.now(timezone.utc)
    
    # Only update account_type if no admin override
    if not admin_override_active:
        user.account_type = plan_name.lower()
        if action == "purchased":
            debug_log(f"✅ New purchase: {github_user} -> {plan_name} (trial: {on_free_trial})")
        else:
            debug_log(f"✅ Plan changed: {github_user} -> {plan_name}")
    else:
        if action == "purchased":
            debug_log(f"✅ New purchase recorded (metadata only): {github_user} -> {plan_name} (trial: {on_free_trial})")
        else:
            debug_log(f"✅ Plan changed recorded (metadata only): {github_user} -> {plan_name}")


def _handle_plan_cancellation(
    user: Account,
    admin_override_active: bool,
    github_user: str
):
    """
    Handle plan cancellation action.
    
    Args:
        user: User account to update
        admin_override_active: Whether admin override is active
        github_user: GitHub username (for logging)
    """
    previous_plan_name = user.marketplace_plan or "unknown"
    
    # Update marketplace metadata (always update these)
    user.marketplace_plan = None
    user.marketplace_unit_count = None
    user.marketplace_on_free_trial = False
    user.marketplace_next_billing_date = None
    user.marketplace_updated_at = datetime.now(timezone.utc)
    
    # Only update account_type if no admin override
    if not admin_override_active:
        user.account_type = "free"
        debug_log(f"✅ Cancelled subscription: {github_user} ({previous_plan_name} -> free)")
    else:
        debug_log(f"✅ Cancelled subscription recorded (metadata only): {github_user} ({previous_plan_name})")


def _handle_pending_change(
    user: Account,
    plan_info: dict,
    webhook_event: MarketplaceWebhookEvent,
    action: str,
    github_user: str
):
    """
    Handle pending change or pending change cancelled actions.
    
    Args:
        user: User account to update
        plan_info: Plan information
        webhook_event: Webhook event record
        action: Action type
        github_user: GitHub username (for logging)
    """
    if action == "pending_change":
        new_plan = plan_info.get("name", "unknown")
        debug_log(f"📅 Pending change: {github_user} -> {new_plan} (effective: {webhook_event.effective_date})")
    else:
        debug_log(f"🚫 Pending change cancelled for {github_user}")
    # Don't modify account_type for pending changes
    user.marketplace_updated_at = datetime.now(timezone.utc)


def update_account_from_webhook(
    db: Session,
    webhook_event: MarketplaceWebhookEvent,
    payload: dict
) -> bool:
    """
    Update user account based on webhook event.
    
    Respects admin overrides - if an admin has manually set the account tier,
    the webhook will update marketplace metadata but not change the account_type.
    
    Args:
        db: Database session
        webhook_event: Webhook event record
        payload: Webhook payload dictionary
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        marketplace_purchase = payload.get("marketplace_purchase", {})
        account_info = marketplace_purchase.get("account", {})
        plan_info = marketplace_purchase.get("plan", {})
        previous_marketplace_purchase = payload.get("previous_marketplace_purchase", {})
        
        github_user = account_info.get("login")
        marketplace_account_id = account_info.get("id")
        
        if not github_user:
            debug_log("❌ Error: No GitHub user found in webhook payload")
            webhook_event.processing_error = "No GitHub user found in webhook payload"
            db.commit()
            return False
        
        # Find user account
        user = db.query(Account).filter(Account.github_user == github_user).first()
        
        if not user:
            debug_log(f"⚠️ Warning: User {github_user} not found in database, creating placeholder")
            # Create a placeholder account for webhook processing
            # The user will complete registration on first login
            user = Account(
                github_user=github_user,
                github_email=f"{github_user}@users.noreply.github.com",
                account_type="unknown",
                marketplace_account_id=marketplace_account_id
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        # Check if admin override is active
        admin_override_active = _check_admin_override(user, github_user)
        
        # Update account based on event action
        action = webhook_event.action or webhook_event.event_type
        
        # Log previous plan if available (useful for auditing upgrades/downgrades)
        if previous_marketplace_purchase:
            previous_plan = previous_marketplace_purchase.get("plan", {})
            previous_plan_name = previous_plan.get("name", "unknown")
            debug_log(f"📋 Previous plan: {previous_plan_name}")
        
        if action in ["purchased", "changed"]:
            _handle_plan_purchase_or_change(
                user, marketplace_purchase, plan_info, marketplace_account_id,
                admin_override_active, action, github_user
            )
        elif action == "cancelled":
            _handle_plan_cancellation(user, admin_override_active, github_user)
        elif action in ["pending_change", "pending_change_cancelled"]:
            _handle_pending_change(user, plan_info, webhook_event, action, github_user)
        else:
            debug_log(f"⚠️ Warning: Unknown action: {action}")
            webhook_event.processing_error = f"Unknown action: {action}"
            db.commit()
            return False
        
        # Mark webhook as processed
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(timezone.utc)
        
        db.commit()
        
        debug_log(f"✅ Successfully processed webhook event {webhook_event.event_id} for {github_user}")
        return True
        
    except Exception as e:
        debug_log(f"❌ Error processing webhook: {str(e)}")
        webhook_event.processing_error = str(e)
        webhook_event.retry_count += 1
        db.commit()
        return False


def process_webhook_async(
    event_id: int,
    payload_dict: dict,
    db: Session
):
    """
    Process webhook event in background.
    
    Args:
        event_id: Webhook event ID
        payload_dict: Parsed webhook payload
        db: Database session
    """
    try:
        webhook_event = db.query(MarketplaceWebhookEvent).filter(
            MarketplaceWebhookEvent.event_id == event_id
        ).first()
        
        if not webhook_event:
            debug_log(f"❌ Error: Webhook event {event_id} not found")
            return
        
        if webhook_event.processed:
            debug_log(f"ℹ️ Webhook event {event_id} already processed, skipping")
            return
        
        # Process the webhook
        success = update_account_from_webhook(db, webhook_event, payload_dict)
        
        if not success and webhook_event.retry_count < 3:
            debug_log(f"⚠️ Webhook processing failed, retry count: {webhook_event.retry_count}")
            # Could implement exponential backoff retry logic here
        
    except Exception as e:
        debug_log(f"❌ Error in async webhook processing: {str(e)}")
    finally:
        db.close()


@router.post("/webhooks/marketplace")
async def marketplace_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)]
):
    """
    Handle GitHub Marketplace webhook events.
    
    Supported events:
    - marketplace_purchase: purchased, cancelled, pending_change, pending_change_cancelled
    
    Security features:
    - HMAC SHA-256 signature verification
    - Source IP verification (optional, configured via VERIFY_WEBHOOK_IP)
    - Rate limiting per IP address
    - Full request logging (headers, payload, source IP)
    
    The endpoint verifies the webhook signature, stores the event for auditing,
    and processes it to update user account tiers.
    """
    # Get source IP address
    source_ip = request.client.host if request.client else None
    
    # Check rate limit
    if not check_rate_limit(source_ip or "unknown"):
        debug_log(f"❌ Rate limit exceeded for {source_ip}")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    
    # Verify source IP (if configured)
    if not verify_source_ip(source_ip):
        debug_log(f"❌ Source IP verification failed for {source_ip}")
        raise HTTPException(status_code=403, detail="Source IP not authorized")
    
    # Get raw body for signature verification
    body = await request.body()
    
    # Get webhook signature from headers
    signature = request.headers.get("X-Hub-Signature-256")
    event_type = request.headers.get("X-GitHub-Event")
    
    # Store headers for audit trail (excluding sensitive data)
    headers_dict = {
        "X-GitHub-Event": event_type,
        "X-GitHub-Delivery": request.headers.get("X-GitHub-Delivery"),
        "X-GitHub-Hook-ID": request.headers.get("X-GitHub-Hook-ID"),
        "X-GitHub-Hook-Installation-Target-ID": request.headers.get("X-GitHub-Hook-Installation-Target-ID"),
        "User-Agent": request.headers.get("User-Agent"),
        "Content-Type": request.headers.get("Content-Type"),
    }
    
    debug_log(f"📥 Received webhook: {event_type} from {source_ip}")
    
    # Verify signature
    if not verify_webhook_signature(body, signature):
        debug_log("❌ Webhook signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Parse payload
    try:
        payload = json.loads(body.decode('utf-8'))
    except json.JSONDecodeError as e:
        debug_log(f"❌ Error parsing webhook payload: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Extract action for marketplace_purchase events
    action = payload.get("action")
    
    # Validate event type
    if event_type != "marketplace_purchase":
        debug_log(f"⚠️ Unsupported event type: {event_type}")
        raise HTTPException(status_code=400, detail=f"Unsupported event type: {event_type}")
    
    # Validate action
    valid_actions = ["purchased", "cancelled", "changed", "pending_change", "pending_change_cancelled"]
    if action not in valid_actions:
        debug_log(f"⚠️ Invalid action: {action}")
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    
    debug_log(f"✅ Processing {event_type} webhook with action: {action}")
    
    # Store webhook event with security context
    webhook_event = store_webhook_event(
        db, event_type, action, payload, signature, 
        source_ip=source_ip,
        headers=headers_dict
    )
    
    # Process webhook in background
    background_tasks.add_task(
        process_webhook_async,
        webhook_event.event_id,
        payload,
        SessionLocal()
    )
    
    # Return success immediately (processing happens in background)
    return {
        "status": "accepted",
        "event_id": webhook_event.event_id,
        "message": "Webhook received and queued for processing"
    }


@router.get("/webhooks/marketplace/events")
async def list_webhook_events(
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
    limit: int = 50,
    offset: int = 0,
    processed: Optional[bool] = None
):
    """
    List stored webhook events for auditing and troubleshooting.
    
    Query parameters:
    - limit: Maximum number of events to return (default: 50)
    - offset: Number of events to skip (default: 0)
    - processed: Filter by processing status (optional)
    """
    query = db.query(MarketplaceWebhookEvent)
    
    if processed is not None:
        query = query.filter(MarketplaceWebhookEvent.processed == processed)
    
    events = query.order_by(
        MarketplaceWebhookEvent.received_at.desc()
    ).limit(limit).offset(offset).all()
    
    return {
        "events": [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "action": event.action,
                "github_user": event.github_user,
                "plan_name": event.plan_name,
                "effective_date": event.effective_date.isoformat() if event.effective_date else None,
                "processed": event.processed,
                "processing_error": event.processing_error,
                "retry_count": event.retry_count,
                "received_at": event.received_at.isoformat() if event.received_at else None,
                "processed_at": event.processed_at.isoformat() if event.processed_at else None,
                "source_ip": event.source_ip,
                "headers": json.loads(event.headers) if event.headers else None
            }
            for event in events
        ],
        "limit": limit,
        "offset": offset
    }


@router.post("/webhooks/marketplace/events/{event_id}/retry")
async def retry_webhook_event(
    event_id: int,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """
    Retry processing a failed webhook event.
    
    This is useful for troubleshooting and recovering from transient errors.
    """
    webhook_event = db.query(MarketplaceWebhookEvent).filter(
        MarketplaceWebhookEvent.event_id == event_id
    ).first()
    
    if not webhook_event:
        raise HTTPException(status_code=404, detail="Webhook event not found")
    
    if webhook_event.processed:
        return {
            "status": "already_processed",
            "message": "Webhook event has already been processed successfully"
        }
    
    # Parse payload
    try:
        payload = json.loads(webhook_event.payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload in stored event")
    
    # Reset processing error
    webhook_event.processing_error = None
    db.commit()
    
    # Process webhook in background
    background_tasks.add_task(
        process_webhook_async,
        webhook_event.event_id,
        payload,
        SessionLocal()
    )
    
    return {
        "status": "retry_queued",
        "event_id": event_id,
        "message": "Webhook event queued for retry processing"
    }


@router.get("/webhooks/marketplace/events/{event_id}")
async def get_webhook_event(
    event_id: int,
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """
    Get detailed information about a specific webhook event.
    
    Returns the full event data including payload and headers for auditing.
    """
    webhook_event = db.query(MarketplaceWebhookEvent).filter(
        MarketplaceWebhookEvent.event_id == event_id
    ).first()
    
    if not webhook_event:
        raise HTTPException(status_code=404, detail="Webhook event not found")
    
    return {
        "event_id": webhook_event.event_id,
        "event_type": webhook_event.event_type,
        "action": webhook_event.action,
        "github_user": webhook_event.github_user,
        "marketplace_account_id": webhook_event.marketplace_account_id,
        "plan_name": webhook_event.plan_name,
        "effective_date": webhook_event.effective_date.isoformat() if webhook_event.effective_date else None,
        "payload": json.loads(webhook_event.payload) if webhook_event.payload else None,
        "signature": webhook_event.signature,
        "source_ip": webhook_event.source_ip,
        "headers": json.loads(webhook_event.headers) if webhook_event.headers else None,
        "processed": webhook_event.processed,
        "processing_error": webhook_event.processing_error,
        "retry_count": webhook_event.retry_count,
        "received_at": webhook_event.received_at.isoformat() if webhook_event.received_at else None,
        "processed_at": webhook_event.processed_at.isoformat() if webhook_event.processed_at else None
    }
