# GitHub Marketplace Webhooks Documentation

> **Not part of the self-hosted beta:** GitHub Marketplace billing and hosted Cloud/SaaS subscriptions are not active offerings for the first public self-hosted beta. This document is retained for future Cloud/SaaS planning and internal validation only. Do not configure Marketplace billing for a self-hosted beta install.

This document provides documentation for the GitHub Marketplace webhook integration code path in ActionsManager, covering implementation, setup, testing, and troubleshooting for future cloud work.

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Event Schema](#event-schema)
5. [Setup & Configuration](#setup--configuration)
6. [Webhook Endpoint](#webhook-endpoint)
7. [Event Handling Flow](#event-handling-flow)
8. [Security & Validation](#security--validation)
9. [Testing](#testing)
10. [Troubleshooting](#troubleshooting)
11. [API Reference](#api-reference)
12. [Compliance](#compliance)

No formal compliance certification is claimed for the self-hosted beta.

---

## Overview

The GitHub Marketplace webhook integration is a future Cloud/SaaS code path. If a Marketplace offering is launched later, webhook events would support billing and subscription management. No Marketplace subscription plans are currently available for the self-hosted beta.

Cloud/SaaS account tiers are marketplace-managed. Do not use self-hosted `LICENSE_KEY` values as the cloud source of truth for billing or tier management.

### Key Benefits

- **Automated Billing**: No manual intervention required for subscription changes
- **Real-time Updates**: Account tiers update immediately when marketplace events occur
- **Audit Trail**: Complete event logging for compliance and troubleshooting
- **Reliable Processing**: Retry logic and error handling for failed events
- **Security**: HMAC SHA-256 signature verification and optional IP whitelisting

---

## Features

The marketplace webhook implementation provides the following features:

- ✅ **Webhook Signature Verification**: HMAC SHA-256 signature verification for security
- ✅ **Source IP Verification**: Optional verification of webhook source IP against GitHub's IP ranges
- ✅ **Rate Limiting**: Per-IP rate limiting to prevent abuse (60 requests/minute default)
- ✅ **Event Storage**: All webhook events are stored for auditing with full context
- ✅ **Header Logging**: Request headers are stored for audit trail
- ✅ **Account Tier Updates**: Automatic account tier updates based on subscription events
- ✅ **Retry Handling**: Failed webhook processing can be retried (up to 3 times)
- ✅ **Background Processing**: Webhook processing happens asynchronously
- ✅ **Debug Logging**: Detailed logging for troubleshooting
- ✅ **Free Trial Support**: Automatic handling of free trial subscriptions
- ✅ **Effective Date Tracking**: Store and track when plan changes take effect
- ✅ **Admin Panel**: Web UI for viewing and analyzing webhook events

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                       GitHub Marketplace                         │
│                                                                   │
│  User Action: Purchase / Change / Cancel Subscription           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ HTTPS POST
                             │ marketplace_purchase event
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ActionsManager Backend                      │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         POST /webhooks/marketplace                        │  │
│  │                                                            │  │
│  │  1. Rate Limit Check (per IP)                            │  │
│  │  2. Source IP Verification (optional)                    │  │
│  │  3. Signature Verification (HMAC SHA-256)                │  │
│  │  4. Event Validation                                      │  │
│  │  5. Store Event (with headers, IP, payload)              │  │
│  │  6. Queue for Background Processing                       │  │
│  │  7. Return 200 OK                                         │  │
│  └─────────────────┬────────────────────────────────────────┘  │
│                    │                                             │
│                    ▼                                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │       Background Task: Process Webhook Event             │  │
│  │                                                            │  │
│  │  1. Find/Create User Account                             │  │
│  │  2. Update Account Tier based on action:                 │  │
│  │     - purchased → Upgrade to plan tier                   │  │
│  │     - changed → Update to new plan tier                  │  │
│  │     - cancelled → Downgrade to free tier                 │  │
│  │     - pending_change → Log but don't update              │  │
│  │  3. Update marketplace metadata                          │  │
│  │  4. Mark event as processed                              │  │
│  │  5. On failure: Retry (up to 3 times)                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### Database Tables

The implementation uses two main database tables:

1. **marketplace_webhook_events**: Stores all webhook events for auditing
2. **accounts**: User accounts with marketplace metadata fields

See [Database Schema](#database-schema) section for detailed table structure.

---

## Event Schema

### Supported Events

The webhook handler supports the `marketplace_purchase` event type with the following actions:

| Action | Description | Account Tier Effect |
|--------|-------------|---------------------|
| `purchased` | User purchased a new plan (including free trials) | Account tier upgraded to purchased plan, trial status tracked |
| `cancelled` | User cancelled their subscription | Account downgraded to free tier |
| `changed` | User changed their plan (upgrade/downgrade) | Account tier updated to new plan |
| `pending_change` | User initiated a plan change | Logged with effective_date but account tier unchanged until change completes |
| `pending_change_cancelled` | User cancelled a pending plan change | Logged but no account tier change |

### Event Payload Structure

GitHub sends webhook events with the following payload structure:

```json
{
  "action": "purchased",
  "marketplace_purchase": {
    "account": {
      "id": 12345,
      "login": "github_username",
      "type": "User",
      "email": "user@example.com"
    },
    "plan": {
      "id": 1234,
      "name": "professional",
      "description": "Professional plan with advanced features",
      "monthly_price_in_cents": 4000,
      "yearly_price_in_cents": 40000,
      "price_model": "flat-rate",
      "has_free_trial": true,
      "unit_name": null,
      "bullets": [
        "10 projects",
        "Private repositories",
        "10 secrets per project"
      ]
    },
    "billing_cycle": "monthly",
    "unit_count": 1,
    "on_free_trial": false,
    "free_trial_ends_on": null,
    "next_billing_date": "2025-12-01T00:00:00Z"
  },
  "sender": {
    "login": "github_username",
    "id": 12345
  }
}
```

### Webhook Headers

GitHub includes the following headers with each webhook request:

| Header | Description | Example |
|--------|-------------|---------|
| `X-Hub-Signature-256` | HMAC SHA-256 signature | `sha256=abc123...` |
| `X-GitHub-Event` | Event type | `marketplace_purchase` |
| `X-GitHub-Delivery` | Unique delivery ID | `12345-67890-abcde` |
| `X-GitHub-Hook-ID` | Hook ID | `12345` |
| `User-Agent` | GitHub webhook user agent | `GitHub-Hookshot/abc123` |
| `Content-Type` | Content type | `application/json` |

### Free Trial Handling

When a user starts a free trial, the webhook includes:

```json
{
  "action": "purchased",
  "marketplace_purchase": {
    "on_free_trial": true,
    "free_trial_ends_on": "2025-12-15T00:00:00Z",
    "next_billing_date": "2025-12-15T00:00:00Z",
    ...
  }
}
```

The system automatically:
- Sets `marketplace_on_free_trial` flag on the account
- Tracks trial status in the database
- Logs trial start in debug mode
- Updates billing date when trial converts to paid

### Pending Change Events

For plan changes that take effect at a future date:

```json
{
  "action": "pending_change",
  "effective_date": "2025-12-01T00:00:00Z",
  "marketplace_purchase": {
    "plan": {
      "name": "enterprise"
    }
  },
  "previous_marketplace_purchase": {
    "plan": {
      "name": "professional"
    }
  }
}
```

The system:
- Stores `effective_date` in the database for audit purposes
- Logs pending changes with their effective dates
- Does not modify the account tier until the change is actually effective
- Tracks the previous plan for comparison

---

## Setup & Configuration

### Prerequisites

Before setting up the webhook integration:

1. **GitHub Marketplace App**: Your app must be listed on GitHub Marketplace
2. **Backend Server**: FastAPI backend must be running and accessible via HTTPS
3. **Database**: SQLite or PostgreSQL database configured
4. **SSL Certificate**: Valid SSL certificate for HTTPS (required in production)

### Step 1: Database Migration

Apply the database migrations to add marketplace webhook support:

```bash
cd backend

# First migration: Create webhook events table
python migrate_add_marketplace_webhooks.py

# Second migration: Add security fields (source_ip, headers)
python migrate_add_webhook_security.py
```

This creates:
- `marketplace_webhook_events` table for event storage
- Marketplace metadata columns in `accounts` table
- Security audit fields (`source_ip`, `headers`)

### Step 2: Configure Webhook Secret

Set the `GITHUB_WEBHOOK_SECRET` environment variable for webhook signature verification:

```bash
# Generate a secure random secret
export GITHUB_WEBHOOK_SECRET="$(openssl rand -hex 32)"
```

⚠️ **Important**: 
- In production, **always** configure a webhook secret for security
- Store the secret securely (e.g., in environment variables, secrets manager)
- In development/testing without a secret, signature verification will be skipped (not recommended)

### Step 3: Configure Security Features (Optional)

Enable additional security features via environment variables:

```bash
# Enable source IP verification (disabled by default)
export VERIFY_WEBHOOK_IP=true

# Configure GitHub's webhook IP ranges (comma-separated CIDR notation)
# Update these periodically from https://api.github.com/meta
export GITHUB_WEBHOOK_IPS="192.30.252.0/22,185.199.108.0/22,140.82.112.0/20,143.55.64.0/20"

# Configure rate limiting (requests per minute, default: 60)
export WEBHOOK_RATE_LIMIT=60
```

### Step 4: Configure GitHub Marketplace App

In your GitHub Marketplace app settings:

1. Navigate to **GitHub Settings** → **Developer settings** → **GitHub Apps** → Your App
2. Scroll to **Webhooks** section
3. Set the **Webhook URL** to: `https://yourdomain.com/webhooks/marketplace`
4. Set the **Webhook secret** (same as `GITHUB_WEBHOOK_SECRET`)
5. Enable webhook events:
   - ✅ `Marketplace purchase`
6. Save changes

### Step 5: Configure Admin Panel Access (Optional)

Set admin credentials for the webhook admin panel:

```bash
# Do not use placeholder credentials such as admin/admin123
# Change these in production!
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=your_secure_password
```

### Step 6: Verify Setup

Test the webhook configuration:

```bash
# Start the backend server
cd backend
uvicorn main:app --reload --port 8000

# In another terminal, run the manual test
cd /path/to/actions-manager
python manual_test_marketplace_webhook.py
```

Or use the GitHub App settings page to send a test webhook event.

### Security Best Practices

**Production Security Checklist:**

- ✅ **Always enable signature verification** by setting `GITHUB_WEBHOOK_SECRET`
- ✅ **Enable IP verification** for production by setting `VERIFY_WEBHOOK_IP=true`
- ✅ **Update GitHub IP ranges** periodically from [GitHub's Meta API](https://api.github.com/meta)
- ✅ **Monitor rate limiting** to detect potential abuse
- ✅ **Use HTTPS** for webhook endpoints in production
- ✅ **Change default admin credentials** for the admin panel
- ✅ **Disable debug mode** in production to avoid logging sensitive data
- ✅ **Rotate webhook secrets** periodically
- ✅ **Review webhook event logs** regularly for suspicious activity

---

## Webhook Endpoint

### POST /webhooks/marketplace

The main webhook endpoint that receives GitHub Marketplace events.

**URL**: `https://yourdomain.com/webhooks/marketplace`

**Method**: `POST`

**Authentication**: HMAC SHA-256 signature verification (via `X-Hub-Signature-256` header)

#### Request Processing Flow

1. **Rate Limit Check**: Verify request doesn't exceed rate limit (60/min per IP by default)
2. **Source IP Verification**: Check if request comes from GitHub's IP ranges (if enabled)
3. **Signature Verification**: Validate HMAC SHA-256 signature
4. **Event Validation**: Ensure event type is `marketplace_purchase` and action is supported
5. **Event Storage**: Store event with full payload, headers, and metadata
6. **Background Processing**: Queue event for asynchronous processing
7. **Immediate Response**: Return 200 OK to acknowledge receipt

#### Security Checks

The endpoint performs the following security checks in order:

1. **Source IP Verification** (if `VERIFY_WEBHOOK_IP=true`):
   - Validates request originates from GitHub's documented IP ranges
   - Supports both IPv4 and IPv6 addresses
   - Returns `403 Forbidden` if IP is not authorized

2. **Rate Limiting**:
   - Tracks requests per source IP address
   - Default limit: 60 requests per minute per IP
   - Automatically cleans up old request records
   - Returns `429 Too Many Requests` if limit exceeded

3. **Signature Verification**:
   - Validates `X-Hub-Signature-256` header matches expected HMAC
   - Uses constant-time comparison to prevent timing attacks
   - Returns `401 Unauthorized` if signature is invalid

4. **Event Validation**:
   - Ensures `X-GitHub-Event` header is `marketplace_purchase`
   - Validates action is one of the supported types
   - Returns `400 Bad Request` if validation fails

#### Request Headers (Required)

```
X-Hub-Signature-256: sha256=abc123...
X-GitHub-Event: marketplace_purchase
Content-Type: application/json
```

#### Request Headers (Optional, Logged)

```
X-GitHub-Delivery: 12345-67890-abcde
X-GitHub-Hook-ID: 12345
User-Agent: GitHub-Hookshot/abc123
```

#### Success Response

**Status Code**: `200 OK`

```json
{
  "status": "accepted",
  "event_id": 123,
  "message": "Webhook received and queued for processing"
}
```

#### Error Responses

| Status Code | Condition | Response |
|-------------|-----------|----------|
| `400 Bad Request` | Invalid event type or action | `{"detail": "Unsupported event type or action"}` |
| `401 Unauthorized` | Invalid webhook signature | `{"detail": "Invalid webhook signature"}` |
| `403 Forbidden` | Source IP not authorized | `{"detail": "Source IP not authorized"}` |
| `429 Too Many Requests` | Rate limit exceeded | `{"detail": "Rate limit exceeded. Try again later."}` |
| `500 Internal Server Error` | Server error during processing | `{"detail": "Internal server error"}` |

---

## Event Handling Flow

### Processing Steps

When a webhook event is received, the following processing flow occurs:

```
1. Webhook Received (POST /webhooks/marketplace)
   ↓
2. Security Validation
   ├─→ Rate Limit Check
   ├─→ Source IP Verification (optional)
   ├─→ Signature Verification
   └─→ Event Type Validation
   ↓
3. Event Storage
   ├─→ Store full payload
   ├─→ Store request headers
   ├─→ Store source IP
   └─→ Set processed=false
   ↓
4. Return 200 OK (immediate response)
   ↓
5. Background Processing (async)
   ├─→ Parse event payload
   ├─→ Extract account info
   ├─→ Find or create user account
   └─→ Update account based on action:
       ├─→ purchased: Upgrade to plan tier
       ├─→ changed: Update to new plan tier
       ├─→ cancelled: Downgrade to free tier
       └─→ pending_change: Log only (no tier change)
   ↓
6. Mark Event as Processed
   ├─→ Set processed=true
   ├─→ Set processed_at timestamp
   └─→ Clear processing_error (if any)
   ↓
7. On Failure:
   ├─→ Log error in processing_error field
   ├─→ Increment retry_count
   └─→ Can be retried via API (up to 3 times)
```

### Account Tier Mapping

The webhook handler maps GitHub Marketplace plan names to internal account tiers:

| Marketplace Plan | Account Tier | Features |
|------------------|--------------|----------|
| `free` | `free` | 3 projects, public repos only, 2 secrets |
| `professional` | `professional` | 10 projects, private repos, 10 secrets |
| `enterprise` | `enterprise` | Unlimited projects, private repos, unlimited secrets |

### Processing Actions

#### Action: `purchased`

User purchases a new plan (including free trials).

**Effect**: Account tier is upgraded to the purchased plan tier.

```python
# Example: User purchases professional plan
{
  "action": "purchased",
  "marketplace_purchase": {
    "plan": {"name": "professional"},
    "on_free_trial": false
  }
}

# Result: account.account_type = "professional"
```

**Free Trial Handling**:
```python
# Example: User starts free trial of professional plan
{
  "action": "purchased",
  "marketplace_purchase": {
    "plan": {"name": "professional"},
    "on_free_trial": true,
    "free_trial_ends_on": "2025-12-15T00:00:00Z"
  }
}

# Result: 
#   account.account_type = "professional"
#   account.marketplace_on_free_trial = true
```

#### Action: `cancelled`

User cancels their subscription.

**Effect**: Account tier is downgraded to free tier.

```python
# Example: User cancels professional plan
{
  "action": "cancelled",
  "marketplace_purchase": {
    "plan": {"name": "professional"}
  }
}

# Result: account.account_type = "free"
```

#### Action: `changed`

User changes their plan (upgrade or downgrade).

**Effect**: Account tier is updated to the new plan tier.

```python
# Example: User upgrades from professional to enterprise
{
  "action": "changed",
  "marketplace_purchase": {
    "plan": {"name": "enterprise"}
  },
  "previous_marketplace_purchase": {
    "plan": {"name": "professional"}
  }
}

# Result: account.account_type = "enterprise"
```

#### Action: `pending_change`

User initiates a plan change that takes effect at a future date.

**Effect**: Event is logged but account tier is NOT changed until the change becomes effective.

```python
# Example: User schedules upgrade to enterprise for next billing cycle
{
  "action": "pending_change",
  "effective_date": "2025-12-01T00:00:00Z",
  "marketplace_purchase": {
    "plan": {"name": "enterprise"}
  }
}

# Result: Event logged, but account.account_type remains unchanged
```

#### Action: `pending_change_cancelled`

User cancels a pending plan change.

**Effect**: Event is logged but no account tier change occurs.

```python
# Example: User cancels pending upgrade
{
  "action": "pending_change_cancelled",
  "marketplace_purchase": {
    "plan": {"name": "professional"}
  }
}

# Result: Event logged, account.account_type remains unchanged
```

### Retry Logic

If webhook processing fails:

1. Error is logged in `processing_error` field
2. `retry_count` is incremented
3. Event can be retried via API: `POST /webhooks/marketplace/events/{event_id}/retry`
4. Maximum 3 automatic retry attempts
5. After 3 failed attempts, manual intervention required

---

## Security & Validation

### Signature Verification

All webhook requests are verified using HMAC SHA-256 signature verification.

#### Algorithm

```python
import hmac
import hashlib

def verify_signature(payload_bytes, signature_header, secret):
    """Verify HMAC SHA-256 signature"""
    expected_mac = hmac.new(
        secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    )
    expected_signature = f"sha256={expected_mac.hexdigest()}"
    
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature_header)
```

#### Signature Header Format

```
X-Hub-Signature-256: sha256=<hex_digest>
```

Example:
```
X-Hub-Signature-256: sha256=abc123def456...
```

#### Configuration

Set the webhook secret in your environment:

```bash
export GITHUB_WEBHOOK_SECRET="your_secret_from_github"
```

⚠️ **Security Note**: If `GITHUB_WEBHOOK_SECRET` is not set, signature verification will be **skipped** with a warning. This should only be used for local development.

### Source IP Verification

Optional feature to verify webhook requests originate from GitHub's IP ranges.

#### Configuration

```bash
# Enable IP verification
export VERIFY_WEBHOOK_IP=true

# Configure GitHub's webhook IP ranges (comma-separated CIDR notation)
export GITHUB_WEBHOOK_IPS="192.30.252.0/22,185.199.108.0/22,140.82.112.0/20,143.55.64.0/20"
```

#### IP Range Updates

GitHub periodically updates their IP ranges. Keep them current:

```bash
# Fetch current IP ranges from GitHub's Meta API
curl https://api.github.com/meta | jq -r '.hooks[]'
```

#### IPv6 Support

The implementation supports both IPv4 and IPv6 addresses:

```python
import ipaddress

def verify_source_ip(source_ip, allowed_ranges):
    """Verify source IP is in allowed ranges"""
    client_ip = ipaddress.ip_address(source_ip)
    
    for ip_range in allowed_ranges:
        network = ipaddress.ip_network(ip_range)
        if client_ip in network:
            return True
    
    return False
```

### Rate Limiting

Per-IP rate limiting protects against abuse and DDoS attacks.

#### Configuration

```bash
# Set rate limit (requests per minute, default: 60)
export WEBHOOK_RATE_LIMIT=60
```

#### Implementation

- Tracks request timestamps per source IP address
- Sliding window algorithm (60-second window)
- Automatically cleans up old entries
- Returns `429 Too Many Requests` if limit exceeded

#### Algorithm

```python
from datetime import datetime, timedelta

def check_rate_limit(source_ip, limit=60):
    """Check if IP has exceeded rate limit"""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=60)
    
    # Get recent requests from this IP
    recent_requests = [
        ts for ts in webhook_request_times.get(source_ip, [])
        if ts > cutoff
    ]
    
    if len(recent_requests) >= limit:
        return False  # Rate limit exceeded
    
    # Add current request
    webhook_request_times[source_ip] = recent_requests + [now]
    return True  # Within rate limit
```

### Audit Logging

All webhook events are logged with complete context for security audits:

**Logged Information**:
- Full event payload (JSON)
- All request headers (JSON)
- Source IP address (IPv4 or IPv6)
- Webhook signature
- Event type and action
- GitHub user and marketplace account ID
- Processing status and errors
- Timestamps (received_at, processed_at)

**Storage**:
- Events stored in `marketplace_webhook_events` table
- Retention: Indefinite (recommended: archive old events periodically)
- Access: Via API endpoints or admin panel

### Constant-Time Comparison

Signature verification uses constant-time comparison to prevent timing attacks:

```python
import hmac

# Use hmac.compare_digest() for constant-time comparison
result = hmac.compare_digest(expected_signature, provided_signature)
```

This prevents attackers from using timing differences to guess the signature.

---

## Testing

### Local Testing Setup

#### Prerequisites

1. Backend server running:
   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```

2. Environment variables set:
   ```bash
   export GITHUB_WEBHOOK_SECRET="test_secret_123"
   export DEBUG_MODE=true
   ```

#### Manual Test Script

Run the provided manual test script:

```bash
cd /path/to/actions-manager
python manual_test_marketplace_webhook.py
```

This script demonstrates:
1. Sending webhook events to the API
2. Verifying events are stored correctly
3. Checking account tier updates
4. Listing webhook events
5. Retrying failed events

#### Test Event Payloads

##### Test 1: Purchase Professional Plan

```bash
curl -X POST http://localhost:8000/webhooks/marketplace \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: marketplace_purchase" \
  -H "X-Hub-Signature-256: sha256=<calculated_signature>" \
  -d '{
    "action": "purchased",
    "marketplace_purchase": {
      "account": {
        "id": 12345,
        "login": "testuser"
      },
      "plan": {
        "name": "professional",
        "price": 4000
      },
      "unit_count": 1,
      "on_free_trial": false,
      "next_billing_date": "2025-12-01T00:00:00Z"
    }
  }'
```

Expected Result:
- Event stored with `processed=true`
- User account created/updated with `account_type="professional"`
- Response: `{"status": "accepted", "event_id": 1, "message": "Webhook received and queued for processing"}`

##### Test 2: Start Free Trial

```bash
curl -X POST http://localhost:8000/webhooks/marketplace \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: marketplace_purchase" \
  -H "X-Hub-Signature-256: sha256=<calculated_signature>" \
  -d '{
    "action": "purchased",
    "marketplace_purchase": {
      "account": {
        "id": 12345,
        "login": "testuser"
      },
      "plan": {
        "name": "professional",
        "price": 4000
      },
      "unit_count": 1,
      "on_free_trial": true,
      "free_trial_ends_on": "2025-12-15T00:00:00Z",
      "next_billing_date": "2025-12-15T00:00:00Z"
    }
  }'
```

Expected Result:
- Event stored with `processed=true`
- User account updated with:
  - `account_type="professional"`
  - `marketplace_on_free_trial=true`
  - `marketplace_next_billing_date="2025-12-15T00:00:00Z"`

##### Test 3: Upgrade Plan

```bash
curl -X POST http://localhost:8000/webhooks/marketplace \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: marketplace_purchase" \
  -H "X-Hub-Signature-256: sha256=<calculated_signature>" \
  -d '{
    "action": "changed",
    "marketplace_purchase": {
      "account": {
        "id": 12345,
        "login": "testuser"
      },
      "plan": {
        "name": "enterprise",
        "price": 20000
      },
      "unit_count": 1,
      "on_free_trial": false,
      "next_billing_date": "2025-12-01T00:00:00Z"
    },
    "previous_marketplace_purchase": {
      "plan": {
        "name": "professional"
      }
    }
  }'
```

Expected Result:
- Event stored with `processed=true`
- User account updated with `account_type="enterprise"`
- Previous plan logged in event payload

##### Test 4: Cancel Subscription

```bash
curl -X POST http://localhost:8000/webhooks/marketplace \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: marketplace_purchase" \
  -H "X-Hub-Signature-256: sha256=<calculated_signature>" \
  -d '{
    "action": "cancelled",
    "marketplace_purchase": {
      "account": {
        "id": 12345,
        "login": "testuser"
      },
      "plan": {
        "name": "professional",
        "price": 4000
      },
      "unit_count": 1
    }
  }'
```

Expected Result:
- Event stored with `processed=true`
- User account downgraded to `account_type="free"`

##### Test 5: Pending Plan Change

```bash
curl -X POST http://localhost:8000/webhooks/marketplace \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: marketplace_purchase" \
  -H "X-Hub-Signature-256: sha256=<calculated_signature>" \
  -d '{
    "action": "pending_change",
    "effective_date": "2025-12-01T00:00:00Z",
    "marketplace_purchase": {
      "account": {
        "id": 12345,
        "login": "testuser"
      },
      "plan": {
        "name": "enterprise",
        "price": 20000
      },
      "unit_count": 1
    }
  }'
```

Expected Result:
- Event stored with `processed=true`
- `effective_date` stored in database
- User account tier **NOT changed** (remains at current tier)

#### Calculating Signatures for Testing

Use the following Python code to calculate webhook signatures:

```python
import hmac
import hashlib
import json

def calculate_signature(payload, secret):
    """Calculate HMAC SHA-256 signature for webhook payload"""
    payload_bytes = json.dumps(payload).encode('utf-8')
    mac = hmac.new(
        secret.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha256
    )
    return f"sha256={mac.hexdigest()}"

# Example usage
payload = {"action": "purchased", "marketplace_purchase": {...}}
secret = "test_secret_123"
signature = calculate_signature(payload, secret)
print(f"X-Hub-Signature-256: {signature}")
```

### Automated Testing

Run the comprehensive test suite:

```bash
cd backend
source ../venv/bin/activate

# Run all marketplace webhook tests (25 tests)
PYTHONPATH=. pytest tests/test_marketplace_webhooks.py -v

# Run security-specific tests (20 tests)
PYTHONPATH=. pytest tests/test_webhook_security.py -v

# Run all tests
PYTHONPATH=. pytest tests/test_marketplace_webhooks.py tests/test_webhook_security.py -v
```

#### Test Coverage

**Marketplace Webhook Tests (25 tests)**:
- Webhook signature verification (5 tests)
- Event storage (2 tests)
- Account updates for all actions (8 tests)
  - Standard purchases and cancellations
  - Free trial scenarios
  - Plan changes with effective_date
  - Previous plan tracking
- API endpoints (8 tests)
- Error handling (2 tests)
- Retry logic

**Security Tests (20 tests)**:
- Source IP verification (7 tests)
  - IPv4 and IPv6 support
  - IP range matching
  - Invalid IP handling
- Rate limiting (5 tests)
  - Per-IP tracking
  - Rate limit enforcement
  - Automatic cleanup
- Header and IP logging (2 tests)
- Security endpoint integration (3 tests)
- Event details API (2 tests)
- List events with new fields (1 test)

**Total: 45 comprehensive tests ensuring all webhook scenarios and security features are properly handled.**

### GitHub Stubbed API Testing

GitHub provides a stubbed marketplace API for testing. To use it:

```bash
# Enable stubbed API mode
export USE_STUBBED_MARKETPLACE_API=true
```

Use the stubbed endpoint for testing:
```
https://api.github.com/marketplace_listing/stubbed
```

See: [GitHub Marketplace Testing Documentation](https://docs.github.com/en/apps/github-marketplace/using-the-github-marketplace-api-in-your-app/testing-your-app#testing-apis)

### Integration Testing

Test the complete flow from GitHub Marketplace to account updates:

1. **Setup Test Environment**:
   ```bash
   # Start backend
   cd backend
   uvicorn main:app --reload --port 8000
   
   # Set environment variables
   export GITHUB_WEBHOOK_SECRET="test_secret_123"
   export DEBUG_MODE=true
   ```

2. **Send Test Webhook**:
   ```bash
   python manual_test_marketplace_webhook.py
   ```

3. **Verify in Database**:
   ```bash
   sqlite3 backend/actions_manager.db
   
   -- Check webhook events
   SELECT * FROM marketplace_webhook_events ORDER BY received_at DESC LIMIT 5;
   
   -- Check account updates
   SELECT github_user, account_type, marketplace_plan, 
          marketplace_on_free_trial, marketplace_next_billing_date
   FROM accounts WHERE github_user = 'testuser';
   ```

4. **Verify via API**:
   ```bash
   # List events
   curl http://localhost:8000/webhooks/marketplace/events
   
   # Get specific event
   curl http://localhost:8000/webhooks/marketplace/events/1
   ```

5. **Test Admin Panel**:
   ```bash
   # Open in browser
   open http://localhost:8000/admin/webhooks
   
   # Do not use placeholder credentials such as admin / admin123
   ```

---

## Troubleshooting

### Common Issues

#### Issue: Invalid Webhook Signature

**Symptoms**:
- Webhook requests return `401 Unauthorized`
- Error message: "Invalid webhook signature"

**Causes**:
- Webhook secret mismatch between GitHub and application
- Secret not set in environment variables
- Signature calculation error

**Solutions**:

1. Verify webhook secret matches:
   ```bash
   # Check environment variable
   echo $GITHUB_WEBHOOK_SECRET
   
   # Should match secret in GitHub App settings
   ```

2. Check GitHub App webhook settings:
   - Go to GitHub App settings → Webhooks
   - Verify webhook secret is set
   - Regenerate secret if necessary

3. Enable debug logging:
   ```bash
   export DEBUG_MODE=true
   ```
   Check logs for signature verification details.

4. Test with manual signature calculation:
   ```python
   import hmac
   import hashlib
   
   secret = "your_secret"
   payload = b'{"action": "purchased"}'
   mac = hmac.new(secret.encode(), payload, hashlib.sha256)
   print(f"Expected: sha256={mac.hexdigest()}")
   ```

#### Issue: User Not Found

**Symptoms**:
- Webhook processed but account not updated
- Error message: "User not found"

**Causes**:
- User hasn't logged in to ActionsManager yet
- GitHub username mismatch

**Solutions**:

1. The system automatically creates a placeholder account for users who haven't logged in yet:
   ```python
   # Automatic account creation
   account = Account(
       github_user=github_user,
       github_email=f"{github_user}@marketplace.github.com",
       account_type=tier,
       marketplace_account_id=marketplace_account_id
   )
   ```

2. User can log in later with GitHub OAuth to complete account setup

3. Verify GitHub username in webhook payload:
   ```bash
   curl http://localhost:8000/webhooks/marketplace/events/1 | jq '.payload.marketplace_purchase.account.login'
   ```

#### Issue: Webhook Events Not Processing

**Symptoms**:
- Events stored but `processed=false`
- No account tier updates

**Causes**:
- Background task not running
- Database connection error
- Processing error in event handling

**Solutions**:

1. Check event processing errors:
   ```bash
   # List failed events
   curl http://localhost:8000/webhooks/marketplace/events?processed=false
   ```

2. Check database for processing errors:
   ```sql
   SELECT event_id, github_user, action, processing_error, retry_count
   FROM marketplace_webhook_events
   WHERE processed = false;
   ```

3. Retry failed events:
   ```bash
   # Retry specific event
   curl -X POST http://localhost:8000/webhooks/marketplace/events/123/retry
   ```

4. Check background task execution:
   - Ensure FastAPI server is running properly
   - Check server logs for error messages
   - Verify database connection is working

#### Issue: Rate Limit Exceeded

**Symptoms**:
- Webhook requests return `429 Too Many Requests`
- Error message: "Rate limit exceeded"

**Causes**:
- Too many requests from same IP address
- DDoS attack or misconfigured client
- Rate limit set too low

**Solutions**:

1. Check rate limit configuration:
   ```bash
   echo $WEBHOOK_RATE_LIMIT  # Default: 60
   ```

2. Increase rate limit if needed:
   ```bash
   export WEBHOOK_RATE_LIMIT=120
   ```

3. Check request patterns in admin panel:
   ```bash
   open http://localhost:8000/admin/webhooks
   ```

4. Investigate suspicious activity:
   ```sql
   SELECT source_ip, COUNT(*) as request_count
   FROM marketplace_webhook_events
   WHERE received_at > datetime('now', '-1 hour')
   GROUP BY source_ip
   ORDER BY request_count DESC;
   ```

#### Issue: Source IP Not Authorized

**Symptoms**:
- Webhook requests return `403 Forbidden`
- Error message: "Source IP not authorized"

**Causes**:
- IP verification enabled but GitHub IP ranges not configured
- GitHub's IP ranges have changed
- Request not coming from GitHub

**Solutions**:

1. Update GitHub IP ranges:
   ```bash
   # Fetch current IP ranges
   curl https://api.github.com/meta | jq -r '.hooks[]'
   
   # Update environment variable
   export GITHUB_WEBHOOK_IPS="192.30.252.0/22,185.199.108.0/22,140.82.112.0/20,143.55.64.0/20"
   ```

2. Disable IP verification for testing:
   ```bash
   export VERIFY_WEBHOOK_IP=false
   ```

3. Check webhook source IP:
   ```sql
   SELECT event_id, source_ip, github_user, received_at
   FROM marketplace_webhook_events
   ORDER BY received_at DESC
   LIMIT 10;
   ```

4. Verify request is coming from GitHub:
   - Check User-Agent header: `GitHub-Hookshot/...`
   - Verify signature is valid
   - Check GitHub App webhook delivery logs

#### Issue: Free Trial Not Tracked

**Symptoms**:
- Free trial flag not set on account
- Trial end date not stored

**Causes**:
- Missing `on_free_trial` field in webhook payload
- Database migration not applied
- Processing error

**Solutions**:

1. Verify webhook payload includes trial info:
   ```bash
   curl http://localhost:8000/webhooks/marketplace/events/1 | \
     jq '.payload.marketplace_purchase.on_free_trial'
   ```

2. Check database for trial fields:
   ```sql
   SELECT github_user, marketplace_on_free_trial, 
          marketplace_next_billing_date
   FROM accounts WHERE github_user = 'testuser';
   ```

3. Ensure database migration was applied:
   ```bash
   cd backend
   python migrate_add_marketplace_webhooks.py
   ```

4. Check processing logs for errors:
   ```bash
   export DEBUG_MODE=true
   # Restart server and send test webhook
   ```

### Debug Logging

Enable detailed debug logging to troubleshoot issues:

```bash
export DEBUG_MODE=true
```

Debug logs include:
- ✅ Webhook signature verification details
- ✅ Event processing steps
- ✅ Account updates
- ✅ Free trial tracking
- ✅ Effective date handling
- ✅ Rate limiting decisions
- ✅ IP verification results
- ✅ Error messages with stack traces

**Example Debug Output**:
```
[MARKETPLACE_WEBHOOK] Received webhook: marketplace_purchase
[MARKETPLACE_WEBHOOK] Action: purchased
[MARKETPLACE_WEBHOOK] GitHub user: testuser
[MARKETPLACE_WEBHOOK] Plan: professional
[MARKETPLACE_WEBHOOK] Free trial: True
[MARKETPLACE_WEBHOOK] ✅ Signature verified
[MARKETPLACE_WEBHOOK] ✅ Event stored (ID: 123)
[MARKETPLACE_WEBHOOK] Processing event 123
[MARKETPLACE_WEBHOOK] Account found: testuser
[MARKETPLACE_WEBHOOK] Updating tier: free → professional
[MARKETPLACE_WEBHOOK] Setting free trial flag: true
[MARKETPLACE_WEBHOOK] ✅ Event processed successfully
```

### Monitoring & Alerts

Set up monitoring for webhook health:

#### Metrics to Monitor

1. **Event Processing Rate**:
   ```sql
   -- Events processed per hour
   SELECT 
     strftime('%Y-%m-%d %H:00', received_at) as hour,
     COUNT(*) as event_count
   FROM marketplace_webhook_events
   WHERE received_at > datetime('now', '-24 hours')
   GROUP BY hour
   ORDER BY hour DESC;
   ```

2. **Failed Events**:
   ```sql
   -- Failed events in last 24 hours
   SELECT COUNT(*) as failed_count
   FROM marketplace_webhook_events
   WHERE processed = false
     AND received_at > datetime('now', '-24 hours');
   ```

3. **Rate Limit Violations**:
   ```sql
   -- Rate limit patterns by IP
   SELECT 
     source_ip,
     COUNT(*) as request_count,
     strftime('%Y-%m-%d %H:%M', received_at) as minute
   FROM marketplace_webhook_events
   WHERE received_at > datetime('now', '-1 hour')
   GROUP BY source_ip, minute
   HAVING request_count > 60
   ORDER BY request_count DESC;
   ```

4. **Processing Latency**:
   ```sql
   -- Average processing time
   SELECT 
     AVG(julianday(processed_at) - julianday(received_at)) * 86400 as avg_seconds
   FROM marketplace_webhook_events
   WHERE processed = true
     AND processed_at IS NOT NULL;
   ```

#### Alert Conditions

Set up alerts for:
- ⚠️ Failed event rate > 5% in last hour
- ⚠️ Event not processed within 5 minutes
- ⚠️ Rate limit violations > 10 per hour
- ⚠️ Source IP not from GitHub (when verification enabled)
- ⚠️ Signature verification failures

### Admin Panel

Use the webhook admin panel for visual troubleshooting:

```bash
# Access admin panel
open http://localhost:8000/admin/webhooks

# Placeholder credentials are unsafe; set strong admin credentials before any exposed future cloud/admin testing
```

**Features**:
- 📊 View all webhook events with pagination
- 🔍 Filter by processing status
- 📍 View source IP addresses
- 📄 Click to view full payload and headers
- 🎨 Color-coded status badges
- 📱 Responsive design

### Diagnostic Queries

Useful SQL queries for troubleshooting:

```sql
-- Recent webhook events
SELECT event_id, event_type, action, github_user, plan_name,
       processed, processing_error, received_at
FROM marketplace_webhook_events
ORDER BY received_at DESC
LIMIT 20;

-- Failed events with errors
SELECT event_id, github_user, action, plan_name,
       processing_error, retry_count, received_at
FROM marketplace_webhook_events
WHERE processed = false
ORDER BY received_at DESC;

-- Account tier history (via webhooks)
SELECT github_user, action, plan_name, received_at
FROM marketplace_webhook_events
WHERE github_user = 'specific_user'
ORDER BY received_at DESC;

-- Free trial accounts
SELECT a.github_user, a.account_type, 
       a.marketplace_on_free_trial, 
       a.marketplace_next_billing_date
FROM accounts a
WHERE a.marketplace_on_free_trial = true;

-- Pending plan changes
SELECT event_id, github_user, plan_name, 
       effective_date, received_at
FROM marketplace_webhook_events
WHERE action = 'pending_change'
  AND processed = true
ORDER BY effective_date DESC;
```

---

## API Reference

### Webhook Event Endpoints

#### POST /webhooks/marketplace

Receive GitHub Marketplace webhook events.

**Authentication**: HMAC SHA-256 signature verification

**Request Headers**:
- `X-Hub-Signature-256` (required): Webhook signature
- `X-GitHub-Event` (required): Event type (`marketplace_purchase`)
- `X-GitHub-Delivery` (optional): Delivery ID
- `X-GitHub-Hook-ID` (optional): Hook ID

**Request Body**: See [Event Schema](#event-schema)

**Response**: `200 OK`
```json
{
  "status": "accepted",
  "event_id": 123,
  "message": "Webhook received and queued for processing"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid event type or action
- `401 Unauthorized`: Invalid signature
- `403 Forbidden`: Source IP not authorized
- `429 Too Many Requests`: Rate limit exceeded

---

#### GET /webhooks/marketplace/events

List stored webhook events.

**Query Parameters**:
- `limit` (optional): Maximum events to return (default: 50, max: 200)
- `offset` (optional): Number of events to skip (default: 0)
- `processed` (optional): Filter by status (`true`, `false`, or omit for all)

**Response**: `200 OK`
```json
{
  "events": [
    {
      "event_id": 123,
      "event_type": "marketplace_purchase",
      "action": "purchased",
      "github_user": "username",
      "plan_name": "professional",
      "source_ip": "192.30.252.100",
      "processed": true,
      "processing_error": null,
      "retry_count": 0,
      "received_at": "2025-11-01T18:30:00Z",
      "processed_at": "2025-11-01T18:30:01Z"
    }
  ],
  "limit": 50,
  "offset": 0
}
```

---

#### GET /webhooks/marketplace/events/{event_id}

Get detailed information about a specific webhook event.

**Path Parameters**:
- `event_id` (required): Event ID

**Response**: `200 OK`
```json
{
  "event_id": 123,
  "event_type": "marketplace_purchase",
  "action": "purchased",
  "github_user": "username",
  "marketplace_account_id": 12345,
  "plan_name": "professional",
  "effective_date": "2025-12-01T00:00:00+00:00",
  "payload": {
    "action": "purchased",
    "marketplace_purchase": {
      "account": {
        "id": 12345,
        "login": "username"
      },
      "plan": {
        "name": "professional"
      }
    }
  },
  "signature": "sha256=abc123...",
  "source_ip": "192.30.252.100",
  "headers": {
    "X-GitHub-Event": "marketplace_purchase",
    "X-GitHub-Delivery": "12345-67890"
  },
  "processed": true,
  "processing_error": null,
  "retry_count": 0,
  "received_at": "2025-11-01T18:30:00Z",
  "processed_at": "2025-11-01T18:30:01Z"
}
```

**Error Responses**:
- `404 Not Found`: Event not found

---

#### POST /webhooks/marketplace/events/{event_id}/retry

Retry processing a failed webhook event.

**Path Parameters**:
- `event_id` (required): Event ID

**Response**: `200 OK`
```json
{
  "status": "retry_queued",
  "event_id": 123,
  "message": "Webhook event queued for retry processing"
}
```

**Error Responses**:
- `404 Not Found`: Event not found
- `400 Bad Request`: Event already processed or retry limit exceeded

---

### Admin Panel

#### GET /admin/webhooks

Admin panel for viewing and analyzing webhook events.

**Authentication**: HTTP Basic Auth

**Query Parameters**:
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Results per page (default: 50, max: 200)
- `processed` (optional): Filter by status (`true`, `false`, or omit for all)

**Response**: HTML page with webhook events table

**Placeholder credentials (do not use for exposed deployments)**:
- Username: `admin`
- Password: `admin123`

⚠️ **Security**: Do not use placeholder credentials in any exposed deployment. Set strong values via environment variables if working on future cloud/admin functionality:
```bash
export ADMIN_USERNAME=your_username
export ADMIN_PASSWORD=your_secure_password
```

---

## Database Schema

### marketplace_webhook_events Table

Stores all marketplace webhook events for auditing and troubleshooting.

| Column | Type | Description |
|--------|------|-------------|
| `event_id` | INTEGER | Primary key, auto-increment |
| `event_type` | VARCHAR(100) | Type of webhook event (e.g., `marketplace_purchase`) |
| `action` | VARCHAR(50) | Action within the event (`purchased`, `cancelled`, `changed`, etc.) |
| `github_user` | VARCHAR(255) | GitHub username from webhook |
| `marketplace_account_id` | INTEGER | GitHub Marketplace account ID |
| `plan_name` | VARCHAR(50) | Plan name from webhook (`free`, `professional`, `enterprise`) |
| `effective_date` | TIMESTAMP | When the plan change takes effect (for pending changes) |
| `payload` | TEXT | Full webhook payload as JSON string |
| `signature` | VARCHAR(255) | Webhook signature for verification (`sha256=...`) |
| `source_ip` | VARCHAR(45) | Source IP address (supports IPv6, 45 chars) |
| `headers` | TEXT | Request headers as JSON string |
| `processed` | BOOLEAN | Processing status (`true` if successfully processed) |
| `processing_error` | VARCHAR(500) | Error message if processing failed |
| `retry_count` | INTEGER | Number of retry attempts (max 3) |
| `received_at` | TIMESTAMP | When webhook was received |
| `processed_at` | TIMESTAMP | When webhook was successfully processed |

**Indexes**:
- Primary key on `event_id`
- Index on `event_type` for filtering
- Index on `action` for filtering
- Index on `github_user` for user lookup
- Index on `received_at` for time-based queries

**Constraints**:
- `event_id`: NOT NULL, AUTO_INCREMENT
- `event_type`: NOT NULL
- `payload`: NOT NULL
- `processed`: NOT NULL, DEFAULT FALSE
- `retry_count`: NOT NULL, DEFAULT 0
- `received_at`: NOT NULL, DEFAULT NOW()

---

### accounts Table (Marketplace Fields)

Extended with marketplace metadata for billing integration.

| Column | Type | Description |
|--------|------|-------------|
| `user_id` | INTEGER | Primary key (existing) |
| `github_user` | VARCHAR(255) | GitHub username (existing) |
| `account_type` | VARCHAR(50) | Account tier (`free`, `professional`, `enterprise`) |
| `marketplace_account_id` | INTEGER | GitHub Marketplace account ID |
| `marketplace_plan` | VARCHAR(50) | Current marketplace plan name |
| `marketplace_unit_count` | INTEGER | Number of units purchased |
| `marketplace_on_free_trial` | BOOLEAN | Free trial status |
| `marketplace_next_billing_date` | TIMESTAMP | Next billing date |
| `marketplace_updated_at` | TIMESTAMP | Last marketplace update timestamp |

**New Columns** (added by migration):
- `marketplace_account_id`: Maps to GitHub Marketplace account
- `marketplace_plan`: Tracks current plan from marketplace
- `marketplace_unit_count`: For per-unit pricing models
- `marketplace_on_free_trial`: Indicates if account is on free trial
- `marketplace_next_billing_date`: Next billing/trial end date
- `marketplace_updated_at`: Timestamp of last webhook update

**Relationships**:
- `marketplace_account_id` → GitHub Marketplace account
- Account tier updates based on marketplace events

---

## Compliance

This implementation meets GitHub Marketplace requirements for webhook handling:

### GitHub Marketplace Requirements

✅ **Webhook Event Support**:
- All required webhook events are supported (`marketplace_purchase`)
- All actions handled: `purchased`, `cancelled`, `changed`, `pending_change`, `pending_change_cancelled`

✅ **Security**:
- HMAC SHA-256 signature verification implemented
- Constant-time comparison to prevent timing attacks
- Optional source IP verification
- Rate limiting to prevent abuse

✅ **Reliability**:
- Events stored immediately before processing
- Background processing for resilience
- Retry logic for failed events (up to 3 attempts)
- Complete audit trail with all events logged

✅ **Audit & Compliance**:
- All events logged with full payload and context
- Request headers stored for security auditing
- Source IP addresses tracked (IPv4 and IPv6)
- Processing errors logged for troubleshooting
- Timestamps for received and processed events

✅ **Billing Integration**:
- Account tiers update correctly based on events
- Free trial support with proper tracking
- Effective date handling for scheduled changes
- Previous plan tracking for change events

✅ **Monitoring & Support**:
- Admin panel for visual monitoring
- API endpoints for programmatic access
- Debug logging for troubleshooting
- Retry endpoints for manual intervention

### Best Practices Followed

✅ **Security**:
- Always verify webhook signatures in production
- Use HTTPS for webhook endpoints
- Enable IP verification for additional security
- Implement rate limiting
- Use constant-time comparison for signatures

✅ **Reliability**:
- Store events before processing
- Process asynchronously to avoid blocking
- Implement retry logic for failures
- Log all errors for troubleshooting
- Provide manual retry mechanism

✅ **Monitoring**:
- Log all events comprehensively
- Track processing status and errors
- Provide admin interface for monitoring
- Enable debug mode for troubleshooting
- Monitor rate limits and abuse patterns

✅ **Documentation**:
- Complete API documentation
- Setup and configuration guide
- Testing procedures
- Troubleshooting guide
- Security best practices

### Marketplace App Checklist

Before submitting to GitHub Marketplace, ensure:

- [ ] Webhook endpoint is accessible via HTTPS
- [ ] Webhook secret is configured in GitHub App settings
- [ ] Webhook URL is set to `https://yourdomain.com/webhooks/marketplace`
- [ ] `marketplace_purchase` event is enabled in GitHub App
- [ ] Database migrations have been applied
- [ ] Signature verification is enabled (`GITHUB_WEBHOOK_SECRET` set)
- [ ] IP verification configured for production (optional but recommended)
- [ ] Rate limiting configured appropriately
- [ ] Admin panel credentials changed from defaults
- [ ] Debug mode disabled in production
- [ ] Monitoring and alerting set up
- [ ] Testing completed with all event types
- [ ] Documentation reviewed and accurate

---

## Support & Resources

### Documentation

- **This Document**: Comprehensive webhook implementation guide
- **[DATABASE_SCHEMA.md](./DATABASE_SCHEMA.md)**: Database structure documentation
- **[README.md](./README.md)**: Main project documentation
- **[API Documentation](http://localhost:8000/docs)**: Interactive API reference (when server running)

### GitHub Resources

- [GitHub Marketplace Documentation](https://docs.github.com/en/apps/github-marketplace)
- [Marketplace Webhook Events](https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads#marketplace_purchase)
- [Testing Your Marketplace App](https://docs.github.com/en/apps/github-marketplace/using-the-github-marketplace-api-in-your-app/testing-your-app)
- [GitHub Meta API (IP Ranges)](https://api.github.com/meta)

### Getting Help

If you encounter issues:

1. **Check Debug Logs**: Enable `DEBUG_MODE=true` for detailed logging
2. **Review Webhook Events**: Use admin panel at `/admin/webhooks`
3. **Check API Endpoints**: Query `/webhooks/marketplace/events` for event details
4. **Retry Failed Events**: Use `/webhooks/marketplace/events/{id}/retry`
5. **Verify Configuration**: Ensure all environment variables are set correctly
6. **Test Locally**: Run `manual_test_marketplace_webhook.py` for testing
7. **Check GitHub Logs**: Review webhook delivery logs in GitHub App settings

### Contact

For additional support:
- **Issues**: [GitHub Issues](https://github.com/dawg-io/actions-manager/issues)
- **Documentation**: [Project Wiki](https://github.com/dawg-io/actions-manager/wiki)

---

## Appendix

### Environment Variables Reference

Complete list of environment variables for marketplace webhook configuration:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_WEBHOOK_SECRET` | Yes (Prod) | "" | Webhook secret for signature verification |
| `VERIFY_WEBHOOK_IP` | No | `false` | Enable source IP verification |
| `GITHUB_WEBHOOK_IPS` | No | "" | Comma-separated list of GitHub IP ranges |
| `WEBHOOK_RATE_LIMIT` | No | `60` | Requests per minute per IP |
| `DEBUG_MODE` | No | `false` | Enable debug logging |
| `ADMIN_USERNAME` | No | `admin` | Admin panel username |
| `ADMIN_PASSWORD` | No | `admin123` | Admin panel password |
| `USE_STUBBED_MARKETPLACE_API` | No | `false` | Use GitHub's stubbed API for testing |

### Migration Scripts

Two migration scripts are provided:

1. **migrate_add_marketplace_webhooks.py**:
   - Creates `marketplace_webhook_events` table
   - Adds marketplace fields to `accounts` table
   - Safe to run multiple times (checks for existing tables)

2. **migrate_add_webhook_security.py**:
   - Adds `source_ip` and `headers` columns
   - Supports IPv6 addresses (45 character field)
   - Safe to run multiple times (checks for existing columns)

### Rate Limiting Algorithm

The rate limiting implementation uses a sliding window algorithm:

```python
def check_rate_limit(source_ip: str, limit: int = 60) -> bool:
    """
    Check if source IP has exceeded rate limit.
    
    Args:
        source_ip: Source IP address
        limit: Maximum requests per minute
        
    Returns:
        True if within limit, False if exceeded
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=60)
    
    # Get recent requests from this IP (within last 60 seconds)
    recent_requests = [
        ts for ts in webhook_request_times.get(source_ip, [])
        if ts > cutoff
    ]
    
    # Check if limit exceeded
    if len(recent_requests) >= limit:
        return False  # Rate limit exceeded
    
    # Add current request timestamp
    webhook_request_times[source_ip] = recent_requests + [now]
    
    return True  # Within rate limit
```

### Common Error Messages

| Error Message | Cause | Solution |
|---------------|-------|----------|
| "Invalid webhook signature" | Signature mismatch | Verify `GITHUB_WEBHOOK_SECRET` matches GitHub settings |
| "Source IP not authorized" | IP not in allowed ranges | Update `GITHUB_WEBHOOK_IPS` or disable verification |
| "Rate limit exceeded" | Too many requests | Wait 60 seconds or increase `WEBHOOK_RATE_LIMIT` |
| "Unsupported event type" | Wrong event type | Ensure `X-GitHub-Event: marketplace_purchase` |
| "User not found" | User hasn't logged in | System creates placeholder account automatically |
| "Processing error" | Database or logic error | Check logs and retry event |

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-04  
**Maintained By**: ActionsManager Team
