# Admin Users Page

This feature adds an administrative interface to view and manage user accounts in ActionsManager.xyz.

## Features

### Endpoint
- **URL**: `/admin/users`
- **Method**: GET
- **Authentication**: HTTP Basic Auth

### Security
- ✅ Requires HTTP Basic Authentication
- ✅ HTTPS-only in production (configured via reverse proxy)
- ✅ Cache-Control: no-store (prevents caching of sensitive data)
- ✅ X-Robots-Tag: noindex, nofollow (prevents search engine indexing)
- ✅ X-Content-Type-Options: nosniff (prevents MIME sniffing)
- ✅ X-Frame-Options: DENY (prevents clickjacking)
- ✅ Logs all authentication attempts (success and failure)

### Display Columns
The admin page displays the following user information:

| Column | Description | Null Display |
|--------|-------------|--------------|
| User ID | Auto-incremented primary key | N/A |
| Avatar | GitHub avatar image | — |
| GitHub User | GitHub username | — |
| GitHub Email | Email address from GitHub | — |
| Account Type | Billing plan (enterprise/pro/unknown) | Badge display |
| GitHub Type | User or Organization | — |
| Last Login | Last login timestamp (UTC) | — |
| Last Login IP | IP address of last login | — |

Null values are displayed as "—" (em-dash).

### Pagination
- Default: 50 users per page
- Configurable: `?per_page=N` (max 200)
- Page navigation: `?page=N`
- Shows total users, current page, and page count

### Sorting
- Default: `last_login_at DESC` (most recent logins first)
- Sortable columns:
  - `user_id`
  - `github_user`
  - `github_email`
  - `account_type`
  - `github_account_type`
  - `last_login_at`
- Sort direction: `?sort_order=asc` or `?sort_order=desc`

## Configuration

### Environment Variables

Add the following to your `.env` file:

```bash
# Admin Panel Configuration
ADMIN_USERNAME=unique_admin_user
ADMIN_PASSWORD=replace_with_strong_random_password
```

**⚠️ IMPORTANT**: Do not use placeholder credentials in any exposed deployment.

### Recommended Production Setup

1. **Strong Credentials**: Use a strong, randomly generated password
   ```bash
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=$(openssl rand -base64 32)
   ```

2. **HTTPS Only**: Configure your reverse proxy (nginx/Apache) to enforce HTTPS for `/admin/*` routes

3. **IP Restrictions**: Consider restricting admin access to specific IP addresses via firewall rules

4. **Rate Limiting**: Implement rate limiting on `/admin/*` routes to prevent brute force attacks

## Database Changes

### Migration

The following columns were added to the `accounts` table:

```sql
ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ NULL,
  ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(45) NULL;
```

For SQLite (development):
```sql
ALTER TABLE accounts ADD COLUMN last_login_at DATETIME NULL;
ALTER TABLE accounts ADD COLUMN last_login_ip VARCHAR(45) NULL;
```

### Automatic Migration

Run the migration script:
```bash
cd backend
python migrate_add_admin_columns.py
```

The migration is idempotent and safe to run multiple times.

### Login Tracking

User login information is automatically tracked when users authenticate via GitHub OAuth:
- `last_login_at`: Set to current UTC timestamp on each login
- `last_login_ip`: Extracted from `X-Forwarded-For` header or direct client IP

## Usage

### Accessing the Admin Page

1. Navigate to: `http://your-domain.com/admin/users`
2. Enter admin credentials when prompted
3. View and manage user accounts

### Example Queries

```bash
# Basic access
curl -u admin:admin123 https://your-domain.com/admin/users

# Pagination
curl -u admin:admin123 https://your-domain.com/admin/users?page=2&per_page=25

# Sorting
curl -u admin:admin123 https://your-domain.com/admin/users?sort_by=github_user&sort_order=asc

# Combined
curl -u admin:admin123 https://your-domain.com/admin/users?page=1&per_page=100&sort_by=last_login_at&sort_order=desc
```

## Logging

All admin access attempts are logged to the application logs:

```
✅ Successful admin login from 192.168.1.100
❌ Failed admin login attempt from 203.0.113.50 with username: hacker
```

Monitor these logs for security incidents.

## Testing

Run the test suite:
```bash
cd backend
PYTHONPATH=. pytest tests/test_admin.py -v
```

Test coverage includes:
- Authentication (valid/invalid credentials)
- Security headers verification
- User listing and display
- Pagination functionality
- Sorting functionality
- Empty database handling
- Null value display

## UI Features

The admin page includes:
- ✅ Responsive design (works on desktop and mobile)
- ✅ Statistics panel (total users, current page, per-page count)
- ✅ Interactive sorting controls
- ✅ Color-coded account type badges
- ✅ Avatar image display
- ✅ Clean, professional styling
- ✅ Pagination controls

## Browser Compatibility

The admin page works in all modern browsers:
- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

No JavaScript frameworks required - pure HTML/CSS with minimal JavaScript for sorting controls.
