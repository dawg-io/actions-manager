# GitHub Marketplace Webhook Integration

This document describes the GitHub Marketplace webhook integration for ActionsManager, which enables automatic billing plan updates based on GitHub Marketplace events.

## Overview

The GitHub Marketplace webhook handler processes subscription events from GitHub Marketplace, automatically updating user account tiers and storing webhook events for auditing and troubleshooting.

## Features

- ✅ **Webhook Signature Verification**: HMAC SHA-256 signature verification for security
- ✅ **Source IP Verification**: Optional verification of webhook source IP against GitHub's IP ranges
- ✅ **Rate Limiting**: Per-IP rate limiting to prevent abuse (60 requests/minute default)
- ✅ **Event Storage**: All webhook events are stored for auditing with full context
- ✅ **Header Logging**: Request headers are stored for audit trail
- ✅ **Account Tier Updates**: Automatic account tier updates based on subscription events
- ✅ **Retry Handling**: Failed webhook processing can be retried
- ✅ **Background Processing**: Webhook processing happens asynchronously
- ✅ **Debug Logging**: Detailed logging for troubleshooting
- ✅ **Free Trial Support**: Automatic handling of free trial subscriptions
- ✅ **Effective Date Tracking**: Store and track when plan changes take effect
- ✅ **Admin Panel**: Web UI for viewing and analyzing webhook events

## Supported Webhook Events

### marketplace_purchase

The `marketplace_purchase` event is sent when a user purchases, cancels, or modifies their marketplace subscription.

#### Actions

| Action | Description | Effect on Account |
|--------|-------------|-------------------|
| `purchased` | User purchased a new plan (including free trials) | Account tier upgraded to purchased plan, trial status tracked |
| `cancelled` | User cancelled their subscription | Account downgraded to free tier |
| `changed` | User changed their plan (upgrade/downgrade) | Account tier updated to new plan |
| `pending_change` | User initiated a plan change | Logged with effective_date but account tier unchanged until change completes |
| `pending_change_cancelled` | User cancelled a pending plan change | Logged but no account tier change |

#### Free Trial Handling

When a user starts a free trial, the webhook includes:
- `on_free_trial: true` - Indicates trial status
- `free_trial_ends_on` - When the trial period ends
- `next_billing_date` - First billing date after trial

The system automatically:
- Sets `marketplace_on_free_trial` flag on the account
- Tracks trial status in the database
- Logs trial start in debug mode
- Updates billing date when trial converts to paid

#### Effective Date Support

For pending changes, GitHub sends an `effective_date` field indicating when the change takes effect. The system:
- Stores `effective_date` in the database for audit purposes
- Logs pending changes with their effective dates
- Does not modify the account tier until the change is actually effective

## Setup

### 1. Configure Webhook Secret

Set the `GITHUB_WEBHOOK_SECRET` environment variable for webhook signature verification:

```bash
export GITHUB_WEBHOOK_SECRET="your_webhook_secret_from_github"
```

⚠️ **Important**: In production, always configure a webhook secret for security. In development/testing without a secret, signature verification will be skipped.

### 2. Configure Security Features (Optional)

Additional security features can be enabled via environment variables:

```bash
# Enable source IP verification (disabled by default)
export VERIFY_WEBHOOK_IP=true

# Configure GitHub's webhook IP ranges (comma-separated CIDR notation)
# Update these periodically from https://api.github.com/meta
export GITHUB_WEBHOOK_IPS="192.30.252.0/22,185.199.108.0/22,140.82.112.0/20,143.55.64.0/20"

# Configure rate limiting (requests per minute, default: 60)
export WEBHOOK_RATE_LIMIT=60
```

**Security Best Practices:**
- **Always enable signature verification** in production by setting `GITHUB_WEBHOOK_SECRET`
- **Enable IP verification** for production environments by setting `VERIFY_WEBHOOK_IP=true`
- **Update GitHub IP ranges** periodically from [GitHub's Meta API](https://api.github.com/meta)
- **Monitor rate limiting** to detect potential abuse
- **Use HTTPS** for webhook endpoints in production

### 3. Configure GitHub Marketplace App

In your GitHub Marketplace app settings:

1. Set the webhook URL to: `https://yourdomain.com/webhooks/marketplace`
2. Set the webhook secret (same as `GITHUB_WEBHOOK_SECRET`)
3. Enable webhook events:
   - `marketplace_purchase`

### 4. Run Database Migrations

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

## API Endpoints

### POST /webhooks/marketplace

Receives GitHub Marketplace webhook events.

**Security Checks:**
1. Source IP verification (if enabled)
2. Rate limiting per IP address
3. HMAC SHA-256 signature verification
4. Event type and action validation

**Headers:**
- `X-Hub-Signature-256`: Webhook signature (required for verification)
- `X-GitHub-Event`: Event type (must be `marketplace_purchase`)
- `X-GitHub-Delivery`: Unique delivery ID (logged for audit)
- `X-GitHub-Hook-ID`: Hook ID (logged for audit)
- `User-Agent`: GitHub webhook user agent (logged for audit)

**Request Body:**
```json
{
  "action": "purchased",
  "marketplace_purchase": {
    "account": {
      "id": 12345,
      "login": "username"
    },
    "plan": {
      "name": "professional",
      "price": 4000
    },
    "unit_count": 1,
    "on_free_trial": false,
    "next_billing_date": "2025-06-01T00:00:00Z"
  }
}
```

**Response:**
```json
{
  "status": "accepted",
  "event_id": 123,
  "message": "Webhook received and queued for processing"
}
```

**Error Responses:**
- `401`: Invalid webhook signature
- `403`: Source IP not authorized
- `429`: Rate limit exceeded
- `400`: Invalid event type or action

### GET /webhooks/marketplace/events

List stored webhook events for auditing.

**Query Parameters:**
- `limit` (optional): Maximum number of events to return (default: 50)
- `offset` (optional): Number of events to skip (default: 0)
- `processed` (optional): Filter by processing status (true/false)

**Response:**
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
  ],
  "limit": 50,
  "offset": 0
}
```

### GET /webhooks/marketplace/events/{event_id}

Get detailed information about a specific webhook event.

**Response:**
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
    "marketplace_purchase": { ... }
  },
  "signature": "sha256=abc123...",
  "source_ip": "192.30.252.100",
  "headers": {
    "X-GitHub-Event": "marketplace_purchase",
    "X-GitHub-Delivery": "12345-67890",
    "User-Agent": "GitHub-Hookshot/abc123"
  },
  "processed": true,
  "processing_error": null,
  "retry_count": 0,
  "received_at": "2025-11-01T18:30:00Z",
  "processed_at": "2025-11-01T18:30:01Z"
}
```

### POST /webhooks/marketplace/events/{event_id}/retry

Retry processing a failed webhook event.

**Response:**
```json
{
  "status": "retry_queued",
  "event_id": 123,
  "message": "Webhook event queued for retry processing"
}
```

### GET /admin/webhooks

Admin panel for viewing and analyzing webhook events (requires basic auth).

**Authentication:** HTTP Basic Auth with admin credentials

**Query Parameters:**
- `page` (optional): Page number (default: 1)
- `per_page` (optional): Results per page (default: 50, max: 200)
- `processed` (optional): Filter by status ('true', 'false', or omit for all)

**Features:**
- View all webhook events with pagination
- Filter by processing status
- View source IP addresses
- Click to view full payload and headers for each event
- Color-coded status badges
- Responsive design

**Access:**
```bash
# Set admin credentials (default: admin/admin123)
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=your_secure_password

# Access the admin panel
https://yourdomain.com/admin/webhooks
```

## Testing with GitHub's Stubbed API

GitHub provides a stubbed marketplace API for testing. To use it:

1. Set the environment variable:
```bash
export USE_STUBBED_MARKETPLACE_API=true
```

2. Use the stubbed endpoint in your tests:
```
https://api.github.com/marketplace_listing/stubbed
```

See: https://docs.github.com/en/apps/github-marketplace/using-the-github-marketplace-api-in-your-app/testing-your-app#testing-apis

## Database Schema

### marketplace_webhook_events Table

| Column | Type | Description |
|--------|------|-------------|
| event_id | INTEGER | Primary key |
| event_type | VARCHAR(100) | Type of webhook event |
| action | VARCHAR(50) | Action within the event |
| github_user | VARCHAR(255) | GitHub username |
| marketplace_account_id | INTEGER | GitHub Marketplace account ID |
| plan_name | VARCHAR(50) | Plan name from webhook |
| effective_date | TIMESTAMP | When the plan change takes effect |
| payload | TEXT | Full webhook payload as JSON (includes previous_marketplace_purchase) |
| signature | VARCHAR(255) | Webhook signature |
| source_ip | VARCHAR(45) | Source IP address (supports IPv6) |
| headers | TEXT | Request headers as JSON |
| processed | BOOLEAN | Processing status |
| processing_error | VARCHAR(500) | Error message if processing failed |
| retry_count | INTEGER | Number of retry attempts |
| received_at | TIMESTAMP | When webhook was received |
| processed_at | TIMESTAMP | When webhook was processed |

### accounts Table (New Columns)

| Column | Type | Description |
|--------|------|-------------|
| marketplace_account_id | INTEGER | GitHub Marketplace account ID |
| marketplace_plan | VARCHAR(50) | Current marketplace plan name |
| marketplace_unit_count | INTEGER | Number of units purchased |
| marketplace_on_free_trial | BOOLEAN | Free trial status |
| marketplace_next_billing_date | TIMESTAMP | Next billing date |
| marketplace_updated_at | TIMESTAMP | Last marketplace update |

## Webhook Event Flow

```
1. GitHub sends webhook → /webhooks/marketplace
2. Check rate limit for source IP
3. Verify source IP (if enabled)
4. Verify webhook signature (HMAC SHA-256)
5. Validate event type and action
6. Store event with full context (payload, headers, IP)
7. Queue event for background processing
8. Return 200 OK immediately
9. Background task processes event:
   - Find or create user account
   - Update account tier based on action
   - Mark event as processed
10. If processing fails, retry up to 3 times
```

## Error Handling

### Webhook Processing Failures

If webhook processing fails:
1. The error is logged in `processing_error` column
2. `retry_count` is incremented
3. Event can be retried via API: `POST /webhooks/marketplace/events/{event_id}/retry`
4. Maximum 3 automatic retry attempts

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Invalid signature | Wrong webhook secret or tampered payload | Verify `GITHUB_WEBHOOK_SECRET` matches GitHub settings |
| User not found | Webhook received before user logged in | System creates placeholder account automatically |
| Processing error | Database error or invalid payload | Check logs and retry event via API |

## Troubleshooting

### Enable Debug Logging

Set the `DEBUG_MODE` environment variable:
```bash
export DEBUG_MODE=true
```

Debug logs include:
- Webhook signature verification details
- Event processing steps
- Account updates
- Error messages

### View Webhook Events

List all webhook events:
```bash
curl http://localhost:8000/webhooks/marketplace/events
```

List failed events:
```bash
curl http://localhost:8000/webhooks/marketplace/events?processed=false
```

### Retry Failed Event

```bash
curl -X POST http://localhost:8000/webhooks/marketplace/events/123/retry
```

### View Event Payload

Use the admin panel for a visual interface:
```
https://yourdomain.com/admin/webhooks
```

Or query the database directly:
```sql
SELECT event_id, event_type, action, github_user, source_ip, 
       payload, headers, processing_error
FROM marketplace_webhook_events
WHERE processed = false
ORDER BY received_at DESC;
```

### View Event Details via API

```bash
# Get full details for a specific event
curl http://localhost:8000/webhooks/marketplace/events/123
```

## Security Considerations

### Authentication & Authorization
1. **Webhook Signature Verification**: Always use webhook secrets in production to prevent unauthorized webhook delivery
2. **HMAC SHA-256 Validation**: All webhooks signatures are verified using constant-time comparison to prevent timing attacks
3. **Admin Panel Access**: Secured with HTTP Basic Auth - change default credentials in production

### Network Security
4. **Source IP Verification**: Enable `VERIFY_WEBHOOK_IP=true` in production and configure GitHub's IP ranges
5. **HTTPS Required**: Always use HTTPS for webhook endpoints in production
6. **Rate Limiting**: Per-IP rate limiting (default: 60 req/min) protects against abuse and DDoS

### Audit & Monitoring
7. **Comprehensive Logging**: All webhook events are logged with headers, payload, source IP, and timestamp
8. **Event Retention**: Keep webhook event logs for security audits and troubleshooting
9. **Monitor Failed Events**: Regularly check for failed webhook processing in admin panel
10. **Debug Mode**: Disable `DEBUG_MODE` in production to avoid logging sensitive data

### Best Practices
11. **Rotate Secrets**: Periodically rotate webhook secrets and update in both GitHub and application
12. **Update IP Ranges**: Keep GitHub webhook IP ranges current from [GitHub's Meta API](https://api.github.com/meta)
13. **Review Logs**: Regularly review webhook event logs for suspicious activity
14. **Secure Admin Credentials**: Use strong passwords for admin panel access

## Compliance

This implementation meets GitHub Marketplace requirements for webhook handling:
- ✅ All required webhook events are supported
- ✅ Webhook signature verification is implemented
- ✅ Source IP verification available (optional, configurable)
- ✅ Rate limiting protects against abuse
- ✅ Events are logged comprehensively for auditing
- ✅ Account tiers are updated correctly
- ✅ Error handling and retry logic is implemented
- ✅ Admin panel for monitoring and troubleshooting

## Testing

Run the comprehensive test suite:

```bash
cd backend
source ../venv/bin/activate

# Run all marketplace webhook tests (25 tests)
PYTHONPATH=. pytest tests/test_marketplace_webhooks.py -v

# Run security-specific tests (20 tests)
PYTHONPATH=. pytest tests/test_webhook_security.py -v
```

Tests cover:

**Marketplace Webhook Tests (25 tests):**
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

**Security Tests (20 tests):**
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

## Support

For issues or questions:
1. Check debug logs with `DEBUG_MODE=true`
2. Review webhook events in admin panel at `/admin/webhooks`
3. Use API endpoint `/webhooks/marketplace/events` for programmatic access
4. Retry failed events via API
4. Check GitHub Marketplace app webhook delivery logs
