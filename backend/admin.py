"""
Admin Router for ActionsManager.xyz

Provides administrative endpoints for managing the application.
Includes:
- /admin/users: Display user information with login tracking
- /api/admin/users/{user_id}/account-type: Update user account type
- /admin/webhooks: Display marketplace webhook event logs (cloud mode only)
"""

import os
import secrets
import logging
import html
from datetime import datetime
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from pydantic import BaseModel, field_validator
from database import get_db
from models import Account, MarketplaceWebhookEvent
import config

# Configure logging for admin access
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBasic()

# Admin credentials from environment variables
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
if not ADMIN_PASSWORD:
    import sys
    print("WARNING: ADMIN_PASSWORD env var is not set. Admin panel is disabled.", file=sys.stderr)

# Date format constants
DATETIME_FORMAT_SECONDS = '%Y-%m-%d %H:%M:%S UTC'
DATETIME_FORMAT_MINUTES = '%Y-%m-%d %H:%M UTC'

# HTML constants for null values
NULL_VALUE_HTML = '<span class="null-value">—</span>'

# HTML dropdown separator constant
HTML_OPTION_SEPARATOR = '\n                        '


# Pydantic model for account type update request
class AccountTypeUpdate(BaseModel):
    """Request model for updating user account type"""
    account_type: str
    
    @field_validator('account_type')
    @classmethod
    def validate_account_type(cls, v: str) -> str:
        """Validate that account_type is one of the allowed values"""
        allowed_types = ['free', 'professional', 'enterprise']
        if v not in allowed_types:
            raise ValueError(f'account_type must be one of: {", ".join(allowed_types)}')
        return v




def validate_pagination_params(page: int, per_page: int) -> tuple[int, int]:
    """
    Validate and normalize pagination parameters.
    
    Args:
        page: Page number (must be >= 1)
        per_page: Results per page (must be 1-200)
    
    Returns:
        Tuple of (validated_page, validated_per_page)
    """
    validated_page = max(1, page)
    validated_per_page = max(1, min(200, per_page))
    return validated_page, validated_per_page


def validate_sort_params(sort_by: str, sort_order: str) -> tuple[str, str]:
    """
    Validate and normalize sort parameters.
    
    Args:
        sort_by: Column name to sort by
        sort_order: Sort direction ('asc' or 'desc')
    
    Returns:
        Tuple of (validated_sort_by, validated_sort_order)
    """
    valid_sort_columns = [
        'user_id', 'github_user', 'github_email', 'account_type',
        'github_account_type', 'last_login_at', 'github_api_calls', 'github_api_calls_today',
        'marketplace_plan', 'marketplace_next_billing_date', 'admin_override'
    ]
    
    validated_sort_by = sort_by if sort_by in valid_sort_columns else 'last_login_at'
    validated_sort_order = sort_order if sort_order in ['asc', 'desc'] else 'desc'
    
    return validated_sort_by, validated_sort_order


def build_user_query(db: Session, sort_by: str, sort_order: str):
    """
    Build database query with sorting.
    
    Args:
        db: Database session
        sort_by: Column to sort by
        sort_order: Sort direction ('asc' or 'desc')
    
    Returns:
        SQLAlchemy query object
    """
    query = db.query(Account)
    sort_column = getattr(Account, sort_by)
    
    if sort_order == 'desc':
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    return query


def calculate_pagination_info(total_users: int, page: int, per_page: int) -> dict:
    """
    Calculate pagination metadata.
    
    Args:
        total_users: Total number of users
        page: Current page number
        per_page: Results per page
    
    Returns:
        Dictionary with pagination info
    """
    total_pages = (total_users + per_page - 1) // per_page if total_users > 0 else 1
    has_prev = page > 1
    has_next = page < total_pages
    
    return {
        'total_pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next
    }


def format_null_or_escape(value: Optional[str]) -> str:
    """
    Format value as null placeholder or escaped HTML.
    
    Args:
        value: String value to format
    
    Returns:
        Escaped HTML or null placeholder
    """
    return html.escape(value) if value else NULL_VALUE_HTML


def format_account_type_badge(account_type: Optional[str]) -> tuple[str, str]:
    """
    Format account type as badge HTML.
    
    Args:
        account_type: Account type string
    
    Returns:
        Tuple of (account_type, badge_html)
    """
    safe_account_type = html.escape(account_type) if account_type else "unknown"
    badge_class = f"badge-{safe_account_type}" if safe_account_type in ['enterprise', 'professional', 'pro', 'free', 'unknown'] else "badge-unknown"
    badge_html = f'<span class="badge {badge_class}">{safe_account_type}</span>'
    return safe_account_type, badge_html


def format_avatar_html(avatar_url: Optional[str]) -> str:
    """
    Format avatar as HTML img tag or null placeholder.
    
    Args:
        avatar_url: Avatar URL
    
    Returns:
        HTML img tag or null placeholder
    """
    if avatar_url:
        escaped_url = html.escape(avatar_url)
        return f'<img src="{escaped_url}" alt="Avatar" class="avatar">'
    return NULL_VALUE_HTML


def format_marketplace_status_badge(marketplace_plan: Optional[str], on_free_trial: bool, show_free_plan: bool = False) -> str:
    """
    Format marketplace subscription status as badge HTML.
    
    Args:
        marketplace_plan: Marketplace plan name
        on_free_trial: Whether user is on free trial
        show_free_plan: Whether to show 'Free Plan' badge instead of null value when no plan
    
    Returns:
        HTML badge for subscription status
    """
    if marketplace_plan:
        if on_free_trial:
            return '<span class="badge badge-trial" title="Free Trial">🎁 Trial</span>'
        return '<span class="badge badge-active" title="Active Subscription">✅ Active</span>'
    
    if show_free_plan:
        return '<span class="badge badge-free">Free Plan</span>'
    return NULL_VALUE_HTML


def format_admin_override_badge(admin_override: bool, admin_override_until: Optional[datetime]) -> str:
    """
    Format admin override status as badge HTML.
    
    Args:
        admin_override: Whether admin override is active
        admin_override_until: Expiration date of override (None for indefinite)
    
    Returns:
        HTML badge or null placeholder
    """
    if not admin_override:
        return '<span class="null-value">None</span>'
    
    if admin_override_until is None:
        return '<span class="badge badge-override" title="Admin Override (Indefinite)">🔒 Override</span>'
    
    override_until = admin_override_until.strftime('%Y-%m-%d')
    return f'<span class="badge badge-override" title="Override Until {override_until}">🔒 Until {override_until}</span>'


def format_user_row(user: Account) -> dict:
    """
    Format a user's data for HTML display.
    
    Args:
        user: Account object from database
    
    Returns:
        Dictionary with formatted user data
    """
    # Format and escape all user data
    github_user = format_null_or_escape(user.github_user)
    github_email = format_null_or_escape(user.github_email)
    
    # Account type badge with safe CSS class
    account_type, account_type_badge = format_account_type_badge(user.account_type)
    
    github_account_type = format_null_or_escape(user.github_account_type)
    
    # Avatar with escaping
    avatar_html = format_avatar_html(user.avatar_url)
    
    # Format dates
    last_login = user.last_login_at.strftime(DATETIME_FORMAT_SECONDS) if user.last_login_at else NULL_VALUE_HTML
    last_login_ip = format_null_or_escape(user.last_login_ip)
    
    # API calls count
    api_calls_total = user.github_api_calls if user.github_api_calls is not None else 0
    api_calls_today = user.github_api_calls_today if user.github_api_calls_today is not None else 0
    
    # Marketplace subscription data
    marketplace_plan = format_null_or_escape(user.marketplace_plan)
    marketplace_status = format_marketplace_status_badge(user.marketplace_plan, user.marketplace_on_free_trial)
    
    # Next billing date
    next_billing = user.marketplace_next_billing_date.strftime('%Y-%m-%d') if user.marketplace_next_billing_date else NULL_VALUE_HTML
    
    # Admin override indicator
    admin_override_status = format_admin_override_badge(user.admin_override, user.admin_override_until)
    
    return {
        'user_id': user.user_id,
        'avatar_html': avatar_html,
        'github_user': github_user,
        'github_email': github_email,
        'account_type': account_type,  # Raw account type for JavaScript
        'account_type_badge': account_type_badge,
        'github_account_type': github_account_type,
        'api_calls_today': api_calls_today,
        'api_calls_total': api_calls_total,
        'last_login': last_login,
        'last_login_ip': last_login_ip,
        'marketplace_plan': marketplace_plan,
        'marketplace_status': marketplace_status,
        'next_billing': next_billing,
        'admin_override_status': admin_override_status
    }


def generate_sort_column_options(sort_by: str) -> str:
    """
    Generate HTML options for sort column dropdown.
    
    Args:
        sort_by: Currently selected sort column
    
    Returns:
        HTML option elements
    """
    columns = [
        ('last_login_at', 'Last Login'),
        ('user_id', 'User ID'),
        ('github_user', 'GitHub User'),
        ('github_email', 'Email'),
        ('account_type', 'Account Type'),
        ('marketplace_plan', 'Marketplace Plan'),
        ('marketplace_next_billing_date', 'Next Billing'),
        ('admin_override', 'Admin Override'),
        ('github_api_calls_today', 'API Calls (24h)'),
        ('github_api_calls', 'API Calls (Total)')
    ]
    
    options = []
    for value, label in columns:
        selected = 'selected' if sort_by == value else ''
        options.append(f'<option value="{value}" {selected}>{label}</option>')
    
    return HTML_OPTION_SEPARATOR.join(options)


def generate_sort_order_options(sort_order: str) -> str:
    """
    Generate HTML options for sort order dropdown.
    
    Args:
        sort_order: Currently selected sort order
    
    Returns:
        HTML option elements
    """
    options = [
        ('desc', 'Descending'),
        ('asc', 'Ascending')
    ]
    
    result = []
    for value, label in options:
        selected = 'selected' if sort_order == value else ''
        result.append(f'<option value="{value}" {selected}>{label}</option>')
    
    return HTML_OPTION_SEPARATOR.join(result)


def generate_per_page_options(per_page: int) -> str:
    """
    Generate HTML options for per-page dropdown.
    
    Args:
        per_page: Currently selected per-page value
    
    Returns:
        HTML option elements
    """
    values = [25, 50, 100, 200]
    
    options = []
    for value in values:
        selected = 'selected' if per_page == value else ''
        options.append(f'<option value="{value}" {selected}>{value}</option>')
    
    return HTML_OPTION_SEPARATOR.join(options)


def generate_html_header(total_users: int, page: int, per_page: int, total_pages: int, sort_by: str, sort_order: str) -> str:
    """
    Generate the HTML header section with statistics and controls.
    
    Args:
        total_users: Total number of users
        page: Current page number
        per_page: Results per page
        total_pages: Total number of pages
        sort_by: Current sort column
        sort_order: Current sort order
    
    Returns:
        HTML string for header section
    """
    sort_column_options = generate_sort_column_options(sort_by)
    sort_order_options = generate_sort_order_options(sort_order)
    per_page_options = generate_per_page_options(per_page)
    
    # Build nav links based on installation mode
    nav_links_html = ""
    if config.INSTALLATION_MODE == "cloud":
        nav_links_html = '<a href="/admin/webhooks">View Marketplace Webhooks</a>'
    else:
        nav_links_html = '<span class="disabled" title="Marketplace features are disabled in self-hosted mode">View Marketplace Webhooks (Disabled)</span>'
    
    # Build mode warning message
    mode_message_html = ""
    if config.INSTALLATION_MODE == "self-hosted":
        mode_message_html = """
            <div class="info-message">
                ℹ️ <strong>Self-Hosted Mode:</strong> Marketplace features are disabled. 
                User tiers are managed via license keys instead of GitHub Marketplace subscriptions.
            </div>"""
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="robots" content="noindex, nofollow">
        <title>Admin - User Management</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                margin-top: 0;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 10px;
            }}
            .nav-links {{
                margin-bottom: 20px;
            }}
            .nav-links a {{
                color: #4CAF50;
                text-decoration: none;
                margin-right: 20px;
                font-weight: 500;
            }}
            .nav-links a:hover {{
                text-decoration: underline;
            }}
            .nav-links .disabled {{
                color: #999;
                cursor: not-allowed;
            }}
            .warning-message {{
                background-color: #fff3cd;
                border: 1px solid #ffc107;
                color: #856404;
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 15px;
            }}
            .info-message {{
                background-color: #d1ecf1;
                border: 1px solid #17a2b8;
                color: #0c5460;
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 15px;
            }}
            .stats {{
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
                padding: 15px;
                background: #f9f9f9;
                border-radius: 4px;
            }}
            .stat {{
                flex: 1;
            }}
            .stat-label {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
            }}
            .stat-value {{
                font-size: 24px;
                font-weight: bold;
                color: #4CAF50;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
            }}
            th {{
                background-color: #4CAF50;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: 600;
                cursor: pointer;
                user-select: none;
            }}
            th:hover {{
                background-color: #45a049;
            }}
            th a {{
                color: white;
                text-decoration: none;
                display: block;
            }}
            td {{
                padding: 12px;
                border-bottom: 1px solid #ddd;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .avatar {{
                width: 32px;
                height: 32px;
                border-radius: 50%;
                vertical-align: middle;
            }}
            .pagination {{
                margin-top: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .pagination a, .pagination button {{
                padding: 8px 16px;
                background: #4CAF50;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                border: none;
                cursor: pointer;
            }}
            .pagination a:hover, .pagination button:hover {{
                background: #45a049;
            }}
            .pagination a.disabled {{
                background: #ccc;
                pointer-events: none;
            }}
            .null-value {{
                color: #999;
                font-style: italic;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 12px;
                font-weight: 600;
            }}
            .badge-enterprise {{
                background: #8b5cf6;
                color: white;
            }}
            .badge-pro {{
                background: #3b82f6;
                color: white;
            }}
            .badge-professional {{
                background: #3b82f6;
                color: white;
            }}
            .badge-free {{
                background: #10b981;
                color: white;
            }}
            .badge-unknown {{
                background: #6b7280;
                color: white;
            }}
            .badge-active {{
                background: #10b981;
                color: white;
            }}
            .badge-trial {{
                background: #f59e0b;
                color: white;
            }}
            .badge-override {{
                background: #ef4444;
                color: white;
            }}
            .select-wrapper {{
                display: inline-block;
                margin: 0 10px;
            }}
            .select-wrapper select {{
                padding: 5px 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }}
            
            /* Modal styles */
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.5);
                animation: fadeIn 0.3s;
            }}
            .modal.show {{
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .modal-content {{
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                max-width: 500px;
                width: 90%;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                animation: slideIn 0.3s;
            }}
            .modal-header {{
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid #f0f0f0;
            }}
            .modal-header h2 {{
                margin: 0;
                color: #333;
                font-size: 24px;
            }}
            .modal-body {{
                margin-bottom: 20px;
            }}
            .form-group {{
                margin-bottom: 15px;
            }}
            .form-group label {{
                display: block;
                margin-bottom: 8px;
                font-weight: 600;
                color: #555;
            }}
            .form-group select {{
                width: 100%;
                padding: 10px;
                border: 2px solid #ddd;
                border-radius: 4px;
                font-size: 16px;
                transition: border-color 0.3s;
            }}
            .form-group select:focus {{
                outline: none;
                border-color: #4CAF50;
            }}
            .modal-footer {{
                display: flex;
                justify-content: flex-end;
                gap: 10px;
            }}
            .modal-footer button {{
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                cursor: pointer;
                transition: background-color 0.3s;
            }}
            .btn-cancel {{
                background-color: #6b7280;
                color: white;
            }}
            .btn-cancel:hover {{
                background-color: #4b5563;
            }}
            .btn-save {{
                background-color: #4CAF50;
                color: white;
            }}
            .btn-save:hover {{
                background-color: #45a049;
            }}
            .btn-save:disabled {{
                background-color: #ccc;
                cursor: not-allowed;
            }}
            .action-btn {{
                background: none;
                border: none;
                cursor: pointer;
                font-size: 20px;
                padding: 5px 10px;
                transition: transform 0.2s;
            }}
            .action-btn:hover {{
                transform: scale(1.2);
            }}
            .success-message {{
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                color: #155724;
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 15px;
                display: none;
            }}
            .success-message.show {{
                display: block;
                animation: fadeIn 0.3s;
            }}
            .error-message {{
                background-color: #f8d7da;
                border: 1px solid #f5c6cb;
                color: #721c24;
                padding: 12px;
                border-radius: 4px;
                margin-bottom: 15px;
                display: none;
            }}
            .error-message.show {{
                display: block;
                animation: fadeIn 0.3s;
            }}
            @keyframes fadeIn {{
                from {{ opacity: 0; }}
                to {{ opacity: 1; }}
            }}
            @keyframes slideIn {{
                from {{
                    transform: translateY(-50px);
                    opacity: 0;
                }}
                to {{
                    transform: translateY(0);
                    opacity: 1;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Admin - User Management</h1>
            
            <div class="nav-links">
                {nav_links_html}
            </div>
            {mode_message_html}
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-label">Total Users</div>
                    <div class="stat-value">{total_users}</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Current Page</div>
                    <div class="stat-value">{page} / {total_pages or 1}</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Per Page</div>
                    <div class="stat-value">{per_page}</div>
                </div>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong>Sorting:</strong>
                <div class="select-wrapper">
                    <label>Column: </label>
                    <select id="sort-by" onchange="updateSort()">
                        {sort_column_options}
                    </select>
                </div>
                <div class="select-wrapper">
                    <label>Order: </label>
                    <select id="sort-order" onchange="updateSort()">
                        {sort_order_options}
                    </select>
                </div>
                <div class="select-wrapper">
                    <label>Per Page: </label>
                    <select id="per-page" onchange="updateSort()">
                        {per_page_options}
                    </select>
                </div>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>User ID</th>
                        <th>Avatar</th>
                        <th>GitHub User</th>
                        <th>GitHub Email</th>
                        <th>Account Type</th>
                        <th>Marketplace Plan</th>
                        <th>Subscription Status</th>
                        <th>Next Billing</th>
                        <th>Admin Override</th>
                        <th>API Calls (24h)</th>
                        <th>Last Login</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
    """


def generate_user_rows_html(users: list[Account]) -> str:
    """
    Generate HTML for user table rows.
    
    Args:
        users: List of Account objects
    
    Returns:
        HTML string for table rows
    """
    if not users:
        return """
                    <tr>
                        <td colspan="12" style="text-align: center; padding: 40px; color: #999;">
                            No users found in the database.
                        </td>
                    </tr>
        """
    
    rows_html = ""
    for user in users:
        user_data = format_user_row(user)
        rows_html += f"""
                    <tr>
                        <td>{user_data['user_id']}</td>
                        <td>{user_data['avatar_html']}</td>
                        <td><strong>{user_data['github_user']}</strong></td>
                        <td>{user_data['github_email']}</td>
                        <td>{user_data['account_type_badge']}</td>
                        <td>{user_data['marketplace_plan']}</td>
                        <td>{user_data['marketplace_status']}</td>
                        <td>{user_data['next_billing']}</td>
                        <td>{user_data['admin_override_status']}</td>
                        <td style="text-align: center;"><strong>{user_data['api_calls_today']:,}</strong></td>
                        <td>{user_data['last_login']}</td>
                        <td style="text-align: center;">
                            <button class="action-btn" onclick="openModal({user_data['user_id']}, '{user_data['account_type']}')" title="Edit Account Type">
                                ⚙️
                            </button>
                            <a href="/admin/users/{user_data['user_id']}/subscription" class="action-btn" style="text-decoration: none; display: inline-block;" title="View Subscription">
                                📊
                            </a>
                        </td>
                    </tr>
        """
    
    return rows_html


def generate_html_footer(page: int, per_page: int, sort_by: str, sort_order: str, pagination_info: dict) -> str:
    """
    Generate the HTML footer with pagination controls.
    
    Args:
        page: Current page number
        per_page: Results per page
        sort_by: Current sort column
        sort_order: Current sort order
        pagination_info: Dictionary with pagination metadata
    
    Returns:
        HTML string for footer section
    """
    has_prev = pagination_info['has_prev']
    has_next = pagination_info['has_next']
    total_pages = pagination_info['total_pages']
    
    prev_link = f'?page={page-1}&per_page={per_page}&sort_by={sort_by}&sort_order={sort_order}' if has_prev else '#'
    next_link = f'?page={page+1}&per_page={per_page}&sort_by={sort_by}&sort_order={sort_order}' if has_next else '#'
    
    return f"""
                </tbody>
            </table>
            
            <div class="pagination">
                <a href="{prev_link}" class="{"disabled" if not has_prev else ""}">← Previous</a>
                <span>Page {page} of {total_pages or 1}</span>
                <a href="{next_link}" class="{"disabled" if not has_next else ""}">Next →</a>
            </div>
        </div>
        
        <!-- Account Type Modal -->
        <div id="accountTypeModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Manage User Account</h2>
                </div>
                <div class="modal-body">
                    <div id="successMessage" class="success-message"></div>
                    <div id="errorMessage" class="error-message"></div>
                    <div class="form-group">
                        <label for="accountType">Account Type:</label>
                        <select id="accountType">
                            <option value="free">Free</option>
                            <option value="professional">Professional</option>
                            <option value="enterprise">Enterprise</option>
                        </select>
                    </div>
                    <input type="hidden" id="userId" value="">
                </div>
                <div class="modal-footer">
                    <button class="btn-cancel" onclick="closeModal()">Cancel</button>
                    <button class="btn-save" id="saveBtn" onclick="saveAccountType()">Save Changes</button>
                </div>
            </div>
        </div>
        
        <script>
            let currentUserId = null;
            let currentAccountType = null;
            
            function updateSort() {{
                const sortBy = document.getElementById('sort-by').value;
                const sortOrder = document.getElementById('sort-order').value;
                const perPage = document.getElementById('per-page').value;
                window.location.href = `?page=1&per_page=${{perPage}}&sort_by=${{sortBy}}&sort_order=${{sortOrder}}`;
            }}
            
            function openModal(userId, accountType) {{
                currentUserId = userId;
                currentAccountType = accountType;
                
                document.getElementById('userId').value = userId;
                document.getElementById('accountType').value = accountType;
                document.getElementById('accountTypeModal').classList.add('show');
                
                // Clear any previous messages
                document.getElementById('successMessage').classList.remove('show');
                document.getElementById('errorMessage').classList.remove('show');
            }}
            
            function closeModal() {{
                document.getElementById('accountTypeModal').classList.remove('show');
                currentUserId = null;
                currentAccountType = null;
            }}
            
            // Close modal when clicking outside
            window.onclick = function(event) {{
                const modal = document.getElementById('accountTypeModal');
                if (event.target === modal) {{
                    closeModal();
                }}
            }}
            
            async function saveAccountType() {{
                const userId = currentUserId;
                const newAccountType = document.getElementById('accountType').value;
                const saveBtn = document.getElementById('saveBtn');
                const successMsg = document.getElementById('successMessage');
                const errorMsg = document.getElementById('errorMessage');
                
                // Clear previous messages
                successMsg.classList.remove('show');
                errorMsg.classList.remove('show');
                
                // Disable button during save
                saveBtn.disabled = true;
                saveBtn.textContent = 'Saving...';
                
                try {{
                    // Include credentials to send HTTP Basic Auth
                    const response = await fetch(`/admin/users/${{userId}}/account-type`, {{
                        method: 'PATCH',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        credentials: 'include',  // Ensure authentication credentials are sent
                        body: JSON.stringify({{ account_type: newAccountType }})
                    }});
                    
                    // Check if response is JSON before parsing
                    const contentType = response.headers.get('content-type');
                    if (!contentType || !contentType.includes('application/json')) {{
                        throw new Error('Server returned non-JSON response. Please check authentication.');
                    }}
                    
                    const data = await response.json();
                    
                    if (response.ok) {{
                        // Show success message
                        successMsg.textContent = data.message;
                        successMsg.classList.add('show');
                        
                        // Wait a moment, then reload the page to show updated data
                        setTimeout(() => {{
                            window.location.reload();
                        }}, 1500);
                    }} else {{
                        // Show error message
                        errorMsg.textContent = data.detail || 'Failed to update account type';
                        errorMsg.classList.add('show');
                        saveBtn.disabled = false;
                        saveBtn.textContent = 'Save Changes';
                    }}
                }} catch (error) {{
                    errorMsg.textContent = 'Error: ' + error.message;
                    errorMsg.classList.add('show');
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Save Changes';
                }}
            }}
        </script>
    </body>
    </html>
    """


def create_secure_response(html_content: str):
    """
    Create HTTP response with security headers.
    
    Args:
        html_content: HTML content to return (must be pre-sanitized)
    
    Returns:
        FastAPI Response with security headers
    
    Note:
        All user-provided data must be sanitized using html.escape() before
        being included in html_content. See format_user_row() for proper
        escaping implementation.
    """
    from fastapi import Response
    return Response(
        content=html_content,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Robots-Tag": "noindex, nofollow",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY"
        }
    )


def verify_admin_credentials(credentials: Annotated[HTTPBasicCredentials, Depends(security)], request: Request = None) -> str:
    """
    Verify admin credentials using HTTP Basic Auth.
    Logs all authentication attempts for security auditing.
    """
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin panel is not configured")

    client_ip = "unknown"
    if request:
        # Try to get real IP from X-Forwarded-For header (for proxied requests)
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        if "," in client_ip:  # X-Forwarded-For can contain multiple IPs
            client_ip = client_ip.split(",")[0].strip()
    
    # Use constant-time comparison to prevent timing attacks
    correct_username = secrets.compare_digest(credentials.username.encode("utf8"), ADMIN_USERNAME.encode("utf8"))
    correct_password = secrets.compare_digest(credentials.password.encode("utf8"), ADMIN_PASSWORD.encode("utf8"))
    
    if not (correct_username and correct_password):
        logger.warning(f"❌ Failed admin login attempt from {client_ip} with username: {credentials.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    logger.info(f"✅ Successful admin login from {client_ip}")
    return credentials.username


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_list(
    request: Request,
    admin_user: Annotated[str, Depends(verify_admin_credentials)],
    db: Annotated[Session, Depends(get_db)],
    page: int = 1,
    per_page: int = 50,
    sort_by: str = "last_login_at",
    sort_order: str = "desc",
):
    """
    Admin-only endpoint to view user information.
    
    Security features:
    - Requires HTTP Basic Auth
    - HTTPS-only in production
    - No-cache headers
    - No-index for search engines
    - Logs all access attempts
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Results per page (default: 50, max: 200)
    - sort_by: Column to sort by (default: last_login_at)
    - sort_order: Sort direction - 'asc' or 'desc' (default: desc)
    """
    
    # Validate parameters
    page, per_page = validate_pagination_params(page, per_page)
    sort_by, sort_order = validate_sort_params(sort_by, sort_order)
    
    # Build and execute query
    query = build_user_query(db, sort_by, sort_order)
    total_users = query.count()
    
    # Apply pagination
    offset = (page - 1) * per_page
    users = query.offset(offset).limit(per_page).all()
    
    # Calculate pagination info
    pagination_info = calculate_pagination_info(total_users, page, per_page)
    
    # Generate HTML content
    html_content = generate_html_header(
        total_users, page, per_page, pagination_info['total_pages'], sort_by, sort_order
    )
    html_content += generate_user_rows_html(users)
    html_content += generate_html_footer(page, per_page, sort_by, sort_order, pagination_info)
    
    # Return response with security headers
    return create_secure_response(html_content)


@router.patch("/admin/users/{user_id}/account-type")
async def update_user_account_type(
    user_id: int,
    account_update: AccountTypeUpdate,
    admin_user: Annotated[str, Depends(verify_admin_credentials)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Admin-only endpoint to update a user's account type.
    
    This sets an admin override that prevents marketplace webhooks from
    changing the tier until the override expires or is manually cleared.
    
    Security features:
    - Requires HTTP Basic Auth
    - Validates account type values
    - Logs all account type changes
    
    Args:
        user_id: User ID to update
        account_update: Request body with new account_type
    
    Returns:
        JSON response with updated user information
    """
    # Import tier service here to avoid circular imports
    from tier_service import set_admin_override
    
    # Find the user
    user = db.query(Account).filter(Account.user_id == user_id).first()
    
    if not user:
        logger.warning(f"Admin {admin_user} attempted to update non-existent user ID: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Store old value for logging
    old_account_type = user.account_type
    new_account_type = account_update.account_type
    
    # Set admin override (indefinite by default)
    set_admin_override(user, new_account_type, duration_days=None)
    db.commit()
    db.refresh(user)
    
    # Log the change
    logger.info(
        f"✅ Admin {admin_user} updated user {user.github_user} (ID: {user_id}) "
        f"account type from '{old_account_type}' to '{new_account_type}' (admin override enabled)"
    )
    
    # Return updated user info
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "success": True,
            "message": f"Account type updated successfully to '{new_account_type}' (admin override active)",
            "user": {
                "user_id": user.user_id,
                "github_user": user.github_user,
                "account_type": user.account_type,
                "admin_override": user.admin_override,
                "marketplace_plan": user.marketplace_plan
            }
        }
    )


def build_webhook_query(db: Session, processed: Optional[str], action: Optional[str], github_user: Optional[str]):
    """
    Build filtered query for marketplace webhook events.
    
    Args:
        db: Database session
        processed: Filter by processing status ('true', 'false', or None)
        action: Filter by webhook action
        github_user: Filter by GitHub username
    
    Returns:
        SQLAlchemy query object
    """
    query = db.query(MarketplaceWebhookEvent)
    
    # Apply filters
    if processed == "true":
        query = query.filter(MarketplaceWebhookEvent.processed.is_(True))
    elif processed == "false":
        query = query.filter(MarketplaceWebhookEvent.processed.is_(False))
    
    if action:
        query = query.filter(MarketplaceWebhookEvent.action == action)
    
    if github_user:
        query = query.filter(MarketplaceWebhookEvent.github_user.like(f"%{github_user}%"))
    
    return query


def format_webhook_event_row(event: MarketplaceWebhookEvent) -> dict:
    """
    Format a webhook event's data for HTML display.
    
    Args:
        event: MarketplaceWebhookEvent object from database
    
    Returns:
        Dictionary with formatted event data
    """
    event_id = event.event_id
    received_at = event.received_at.strftime(DATETIME_FORMAT_SECONDS) if event.received_at else '—'
    action = html.escape(event.action or '—')
    github_user = html.escape(event.github_user or '—')
    plan_name = html.escape(event.plan_name or '—')
    source_ip = f'<span class="ip-address">{html.escape(event.source_ip or "—")}</span>'
    
    # Status badge
    if event.processed:
        status_badge = '<span class="badge badge-success">✅ Processed</span>'
    elif event.processing_error:
        status_badge = '<span class="badge badge-error">❌ Error</span>'
    else:
        status_badge = '<span class="badge badge-pending">⏳ Pending</span>'
    
    # Action badge - ensure action is sanitized before using in class name
    safe_action = html.escape(event.action or '—')
    safe_action_lower = safe_action.lower()
    action_class = f"badge-{safe_action_lower}" if safe_action_lower in ['purchased', 'cancelled', 'changed'] else ''
    action_badge = f'<span class="badge {html.escape(action_class)}">{action}</span>'
    
    retry_count = event.retry_count or 0
    
    return {
        'event_id': event_id,
        'received_at': received_at,
        'action_badge': action_badge,
        'github_user': github_user,
        'plan_name': plan_name,
        'source_ip': source_ip,
        'status_badge': status_badge,
        'retry_count': retry_count
    }


def generate_webhook_event_rows_html(events: list[MarketplaceWebhookEvent]) -> str:
    """
    Generate HTML for webhook event table rows.
    
    Args:
        events: List of MarketplaceWebhookEvent objects
    
    Returns:
        HTML string for table rows
    """
    if not events:
        return """
                    <tr>
                        <td colspan="9" style="text-align: center; padding: 40px;">
                            No webhook events found
                        </td>
                    </tr>
        """
    
    rows_html = ""
    for event in events:
        data = format_webhook_event_row(event)
        rows_html += f"""
                    <tr>
                        <td>#{data['event_id']}</td>
                        <td>{data['received_at']}</td>
                        <td>{data['action_badge']}</td>
                        <td>{data['github_user']}</td>
                        <td>{data['plan_name']}</td>
                        <td>{data['source_ip']}</td>
                        <td>{data['status_badge']}</td>
                        <td>{data['retry_count']}</td>
                        <td><a href="#" class="details-link" onclick="showDetails({data['event_id']}); return false;">View Details</a></td>
                    </tr>
        """
    
    return rows_html


def build_filter_params_string(processed: Optional[str], action: Optional[str], github_user: Optional[str]) -> str:
    """
    Build URL query string for filter parameters.
    
    Args:
        processed: Processing status filter
        action: Action filter
        github_user: GitHub username filter
    
    Returns:
        URL query string (with leading & if non-empty)
    """
    filter_params = []
    if processed:
        filter_params.append(f"processed={html.escape(processed)}")
    if action:
        filter_params.append(f"action={html.escape(action)}")
    if github_user:
        filter_params.append(f"github_user={html.escape(github_user)}")
    
    return "&" + "&".join(filter_params) if filter_params else ""


def generate_webhook_filter_form_html(processed: Optional[str], action: Optional[str], github_user: Optional[str], per_page: int) -> str:
    """
    Generate HTML for webhook event filter form.
    
    Args:
        processed: Current processing status filter value
        action: Current action filter value
        github_user: Current GitHub username filter value
        per_page: Current per_page value
    
    Returns:
        HTML string for the filter form
    """
    # Build selected attributes for dropdowns
    processed_all = 'selected' if processed is None else ''
    processed_true = 'selected' if processed == 'true' else ''
    processed_false = 'selected' if processed == 'false' else ''
    
    action_all = 'selected' if action is None else ''
    action_purchased = 'selected' if action == 'purchased' else ''
    action_cancelled = 'selected' if action == 'cancelled' else ''
    action_changed = 'selected' if action == 'changed' else ''
    action_pending_change = 'selected' if action == 'pending_change' else ''
    action_pending_change_cancelled = 'selected' if action == 'pending_change_cancelled' else ''
    
    per_page_50 = 'selected' if per_page == 50 else ''
    per_page_100 = 'selected' if per_page == 100 else ''
    per_page_200 = 'selected' if per_page == 200 else ''
    
    github_user_value = html.escape(github_user) if github_user else ''
    
    return f"""
            <div class="filters">
                <form method="get" style="display: inline;">
                    <label for="processed">Status:</label>
                    <select name="processed" id="processed">
                        <option value="" {processed_all}>All Events</option>
                        <option value="true" {processed_true}>Processed</option>
                        <option value="false" {processed_false}>Pending</option>
                    </select>
                    
                    <label for="action">Action:</label>
                    <select name="action" id="action">
                        <option value="" {action_all}>All Actions</option>
                        <option value="purchased" {action_purchased}>Purchased</option>
                        <option value="cancelled" {action_cancelled}>Cancelled</option>
                        <option value="changed" {action_changed}>Changed</option>
                        <option value="pending_change" {action_pending_change}>Pending Change</option>
                        <option value="pending_change_cancelled" {action_pending_change_cancelled}>Pending Cancelled</option>
                    </select>
                    
                    <label for="github_user">User:</label>
                    <input type="text" name="github_user" id="github_user" value="{github_user_value}" 
                           placeholder="Search username..." style="padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px;">
                    
                    <label for="per_page">Per Page:</label>
                    <select name="per_page" id="per_page">
                        <option value="50" {per_page_50}>50</option>
                        <option value="100" {per_page_100}>100</option>
                        <option value="200" {per_page_200}>200</option>
                    </select>
                    
                    <button type="submit">Filter</button>
                </form>
            </div>
    """


def generate_webhook_pagination_html(page: int, per_page: int, pagination: dict, filter_string: str) -> str:
    """
    Generate HTML for webhook event pagination controls.
    
    Args:
        page: Current page number
        per_page: Results per page
        pagination: Pagination info dictionary with has_prev, has_next, total_pages
        filter_string: URL query string for filters
    
    Returns:
        HTML string for pagination controls
    """
    # Build pagination links and classes
    prev_link = f'?page={page-1}&per_page={per_page}{filter_string}' if pagination['has_prev'] else '#'
    next_link = f'?page={page+1}&per_page={per_page}{filter_string}' if pagination['has_next'] else '#'
    
    prev_class = '' if pagination['has_prev'] else ' class="disabled"'
    next_class = '' if pagination['has_next'] else ' class="disabled"'
    
    return f"""
            <div class="pagination">
                <a href="{prev_link}"{prev_class}>← Previous</a>
                <span>Page {page} of {pagination['total_pages']}</span>
                <a href="{next_link}"{next_class}>Next →</a>
            </div>
    """


def generate_webhook_admin_page_html(
    total_events: int,
    page: int,
    per_page: int,
    pagination: dict,
    processed: Optional[str],
    action: Optional[str],
    github_user: Optional[str],
    events: list[MarketplaceWebhookEvent]
) -> str:
    """
    Generate complete HTML page for webhook admin interface.
    
    Args:
        total_events: Total number of events matching filters
        page: Current page number
        per_page: Results per page
        pagination: Pagination info dictionary
        processed: Processing status filter
        action: Action filter
        github_user: GitHub username filter
        events: List of webhook events to display
    
    Returns:
        Complete HTML page as string
    """
    # Add event rows
    event_rows_html = generate_webhook_event_rows_html(events)
    
    # Pagination - escape user input for URLs and preserve filters
    filter_string = build_filter_params_string(processed, action, github_user)
    
    # Filter form HTML
    filter_form_html = generate_webhook_filter_form_html(processed, action, github_user, per_page)
    
    # Pagination HTML
    pagination_html = generate_webhook_pagination_html(page, per_page, pagination, filter_string)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="robots" content="noindex, nofollow">
        <title>Admin - Marketplace Webhook Events</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 1600px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                margin-top: 0;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 10px;
            }}
            .stats {{
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
                padding: 15px;
                background: #f9f9f9;
                border-radius: 4px;
            }}
            .stat {{
                flex: 1;
            }}
            .stat-label {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
            }}
            .stat-value {{
                font-size: 24px;
                font-weight: bold;
                color: #4CAF50;
            }}
            .filters {{
                margin-bottom: 20px;
                padding: 15px;
                background: #e8f5e9;
                border-radius: 4px;
            }}
            .filters label {{
                margin-right: 10px;
                font-weight: 500;
            }}
            .filters select {{
                padding: 5px 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }}
            .filters button {{
                padding: 6px 15px;
                background: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                margin-left: 10px;
            }}
            .filters button:hover {{
                background: #45a049;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
                font-size: 13px;
            }}
            th {{
                background-color: #4CAF50;
                color: white;
                padding: 12px 8px;
                text-align: left;
                font-weight: 600;
            }}
            td {{
                padding: 10px 8px;
                border-bottom: 1px solid #ddd;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
            }}
            .badge-success {{
                background: #d4edda;
                color: #155724;
            }}
            .badge-pending {{
                background: #fff3cd;
                color: #856404;
            }}
            .badge-error {{
                background: #f8d7da;
                color: #721c24;
            }}
            .badge-purchased {{
                background: #d1ecf1;
                color: #0c5460;
            }}
            .badge-cancelled {{
                background: #f8d7da;
                color: #721c24;
            }}
            .badge-changed {{
                background: #cce5ff;
                color: #004085;
            }}
            .null-value {{
                color: #999;
                font-style: italic;
            }}
            .ip-address {{
                font-family: 'Courier New', monospace;
                font-size: 12px;
                color: #555;
            }}
            .pagination {{
                margin-top: 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .pagination a, .pagination button {{
                padding: 8px 16px;
                background: #4CAF50;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                border: none;
                cursor: pointer;
            }}
            .pagination a:hover, .pagination button:hover {{
                background: #45a049;
            }}
            .pagination a.disabled {{
                background: #ccc;
                cursor: not-allowed;
            }}
            .details-link {{
                color: #4CAF50;
                text-decoration: none;
                font-weight: 500;
            }}
            .details-link:hover {{
                text-decoration: underline;
            }}
            .nav-links {{
                margin-bottom: 20px;
            }}
            .nav-links a {{
                color: #4CAF50;
                text-decoration: none;
                margin-right: 20px;
            }}
            .nav-links a:hover {{
                text-decoration: underline;
            }}
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.5);
            }}
            .modal-content {{
                background-color: white;
                margin: 2% auto;
                padding: 20px;
                border-radius: 8px;
                width: 90%;
                max-width: 1200px;
                max-height: 90vh;
                overflow-y: auto;
            }}
            .close {{
                color: #aaa;
                float: right;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
            }}
            .close:hover {{
                color: black;
            }}
            .json-viewer {{
                background: #f5f5f5;
                padding: 15px;
                border-radius: 4px;
                overflow-x: auto;
                font-family: 'Courier New', monospace;
                font-size: 12px;
                white-space: pre-wrap;
            }}
        </style>
        <script>
            function showDetails(eventId) {{
                fetch(`/webhooks/marketplace/events/${{eventId}}`)
                    .then(response => response.json())
                    .then(event => {{
                        document.getElementById('modalEventId').textContent = event.event_id;
                        document.getElementById('modalPayload').textContent = JSON.stringify(event.payload || {{}}, null, 2);
                        document.getElementById('modalHeaders').textContent = JSON.stringify(event.headers || {{}}, null, 2);
                        document.getElementById('detailsModal').style.display = 'block';
                    }})
                    .catch(error => {{
                        console.error('Error fetching event details:', error);
                        alert('Failed to load event details');
                    }});
            }}
            
            function closeModal() {{
                document.getElementById('detailsModal').style.display = 'none';
            }}
            
            window.onclick = function(event) {{
                const modal = document.getElementById('detailsModal');
                if (event.target == modal) {{
                    modal.style.display = 'none';
                }}
            }}
        </script>
    </head>
    <body>
        <div class="container">
            <div class="nav-links">
                <a href="/admin/users">← Back to Users</a>
            </div>
            
            <h1>🔒 Marketplace Webhook Events</h1>
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-label">Total Events</div>
                    <div class="stat-value">{total_events}</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Page</div>
                    <div class="stat-value">{page} / {pagination['total_pages']}</div>
                </div>
                <div class="stat">
                    <div class="stat-label">Per Page</div>
                    <div class="stat-value">{per_page}</div>
                </div>
            </div>
            {filter_form_html}
            <table>
                <thead>
                    <tr>
                        <th>Event ID</th>
                        <th>Received At</th>
                        <th>Action</th>
                        <th>User</th>
                        <th>Plan</th>
                        <th>Source IP</th>
                        <th>Status</th>
                        <th>Retries</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                {event_rows_html}
                </tbody>
            </table>
            {pagination_html}
        </div>
        
        <!-- Details Modal -->
        <div id="detailsModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="closeModal()">&times;</span>
                <h2>Webhook Event Details - ID: <span id="modalEventId"></span></h2>
                
                <h3>Headers</h3>
                <div class="json-viewer" id="modalHeaders"></div>
                
                <h3>Payload</h3>
                <div class="json-viewer" id="modalPayload"></div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_content


@router.get("/admin/webhooks", response_class=HTMLResponse)
async def admin_webhooks(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    page: int = 1,
    per_page: int = 50,
    processed: Optional[str] = None,
    action: Optional[str] = None,
    github_user: Optional[str] = None,
):
    """
    Admin panel for viewing marketplace webhook event logs.
    Only available in cloud mode.
    
    Query parameters:
    - page: Page number (default: 1)
    - per_page: Results per page (default: 50, max: 200)
    - processed: Filter by processing status ('true', 'false', or None for all)
    - action: Filter by webhook action (purchased, cancelled, changed, etc.)
    - github_user: Filter by GitHub username
    """
    # Validate admin credentials
    admin_user = verify_admin_credentials(credentials, request)
    
    # Log admin access
    logger.info(f"Admin {admin_user} accessed webhook events page from IP: {request.client.host if request.client else 'unknown'}")
    
    # Check if marketplace is enabled (cloud mode only)
    if config.INSTALLATION_MODE == "self-hosted":
        # Show informative page for self-hosted mode
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta name="robots" content="noindex, nofollow">
            <title>Admin - Marketplace Webhooks (Disabled)</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 800px;
                    margin: 50px auto;
                    background: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    text-align: center;
                }
                h1 {
                    color: #333;
                    margin-top: 0;
                }
                .icon {
                    font-size: 64px;
                    margin-bottom: 20px;
                }
                .message {
                    font-size: 18px;
                    color: #666;
                    margin: 20px 0;
                    line-height: 1.6;
                }
                .info-box {
                    background-color: #d1ecf1;
                    border: 1px solid #17a2b8;
                    color: #0c5460;
                    padding: 20px;
                    border-radius: 4px;
                    margin: 30px 0;
                    text-align: left;
                }
                .info-box h3 {
                    margin-top: 0;
                }
                .nav-link {
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: #4CAF50;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                }
                .nav-link:hover {
                    background: #45a049;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">🛍️</div>
                <h1>Marketplace Webhooks Disabled</h1>
                <p class="message">
                    This feature is only available in cloud mode. Your installation is running in self-hosted mode.
                </p>
                <div class="info-box">
                    <h3>ℹ️ About Self-Hosted Mode</h3>
                    <p>
                        In self-hosted mode, user tiers are managed via license keys instead of GitHub Marketplace subscriptions.
                        Marketplace webhook functionality is disabled as it's not needed for self-hosted installations.
                    </p>
                    <p>
                        <strong>To use marketplace features:</strong> Deploy ActionsManager.xyz in cloud mode with 
                        <code>INSTALLATION_MODE=cloud</code> environment variable.
                    </p>
                </div>
                <a href="/admin/users" class="nav-link">← Back to User Management</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    # Validate pagination parameters
    page, per_page = validate_pagination_params(page, per_page)
    
    # Build and execute query
    query = build_webhook_query(db, processed, action, github_user)
    total_events = query.count()
    
    # Get paginated events
    events = query.order_by(
        MarketplaceWebhookEvent.received_at.desc()
    ).limit(per_page).offset((page - 1) * per_page).all()
    
    # Calculate pagination info
    pagination = calculate_pagination_info(total_events, page, per_page)
    
    # Generate HTML page
    html_content = generate_webhook_admin_page_html(
        total_events=total_events,
        page=page,
        per_page=per_page,
        pagination=pagination,
        processed=processed,
        action=action,
        github_user=github_user,
        events=events
    )
    
    return HTMLResponse(content=html_content)


def format_subscription_user_data(user: Account) -> dict:
    """
    Format user subscription data for HTML display.
    
    Args:
        user: Account object from database
    
    Returns:
        Dictionary with formatted subscription data
    """
    github_user_escaped = html.escape(user.github_user) if user.github_user else "Unknown"
    github_email_escaped = format_null_or_escape(user.github_email)
    account_type_escaped = html.escape(user.account_type) if user.account_type else "unknown"
    marketplace_plan_escaped = format_null_or_escape(user.marketplace_plan)
    
    # Format subscription status
    subscription_status = format_marketplace_status_badge(user.marketplace_plan, user.marketplace_on_free_trial, show_free_plan=True)
    
    # Format billing date
    next_billing = user.marketplace_next_billing_date.strftime(DATETIME_FORMAT_MINUTES) if user.marketplace_next_billing_date else "—"
    
    # Format marketplace metadata
    marketplace_updated = user.marketplace_updated_at.strftime(DATETIME_FORMAT_MINUTES) if user.marketplace_updated_at else "—"
    unit_count = user.marketplace_unit_count if user.marketplace_unit_count else "—"
    
    # Admin override status
    admin_override_html = format_admin_override_badge(user.admin_override, user.admin_override_until)
    
    return {
        'user_id': user.user_id,
        'github_user_escaped': github_user_escaped,
        'github_email_escaped': github_email_escaped,
        'account_type_escaped': account_type_escaped,
        'marketplace_plan_escaped': marketplace_plan_escaped,
        'subscription_status': subscription_status,
        'next_billing': next_billing,
        'marketplace_updated': marketplace_updated,
        'unit_count': unit_count,
        'admin_override_html': admin_override_html
    }


def _format_processing_error(error: Optional[str]) -> str:
    """Truncate and HTML-escape a processing error string for display."""
    if not error:
        return '—'
    truncated = error[:50] + '...' if len(error) > 50 else error
    return html.escape(truncated)


def generate_subscription_event_rows_html(events: list[MarketplaceWebhookEvent]) -> str:
    """
    Generate HTML for subscription event table rows.
    
    Args:
        events: List of MarketplaceWebhookEvent objects
    
    Returns:
        HTML string for table rows
    """
    if not events:
        return """
            <p style="text-align: center; padding: 40px; color: #999;">
                No webhook events found for this user.
            </p>
        """
    
    rows_html = """
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Action</th>
                        <th>Plan</th>
                        <th>Status</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody>
        """
    
    for event in events:
        received_at = event.received_at.strftime(DATETIME_FORMAT_SECONDS) if event.received_at else '—'
        action = html.escape(event.action or '—')
        plan_name = html.escape(event.plan_name or '—')
        
        # Status badge
        if event.processed:
            status_badge = '<span class="badge badge-success">✅ Processed</span>'
        elif event.processing_error:
            status_badge = '<span class="badge badge-error">❌ Error</span>'
        else:
            status_badge = '<span class="badge badge-pending">⏳ Pending</span>'
        
        # Action badge
        safe_action_lower = action.lower()
        action_class = f"badge-{safe_action_lower}" if safe_action_lower in ['purchased', 'cancelled', 'changed'] else ''
        action_badge = f'<span class="badge {html.escape(action_class)}">{action}</span>'
        
        processing_error = _format_processing_error(event.processing_error)
        
        rows_html += f"""
                    <tr>
                        <td>{received_at}</td>
                        <td>{action_badge}</td>
                        <td>{plan_name}</td>
                        <td>{status_badge}</td>
                        <td>{processing_error}</td>
                    </tr>
        """
    
    rows_html += """
                </tbody>
            </table>
        """
    
    return rows_html


@router.get("/admin/users/{user_id}/subscription", response_class=HTMLResponse)
async def admin_user_subscription(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
):
    """
    Admin panel for viewing a specific user's subscription history.
    
    Shows:
    - Current subscription status
    - Marketplace webhook events for this user
    - Billing history
    - Admin override status
    """
    # Validate admin credentials
    admin_user = verify_admin_credentials(credentials, request)
    
    # Get user
    user = db.query(Account).filter(Account.user_id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log admin access
    logger.info(f"Admin {admin_user} viewed subscription for user {user.github_user} (ID: {user_id})")
    
    # Get webhook events for this user
    events = db.query(MarketplaceWebhookEvent).filter(
        MarketplaceWebhookEvent.github_user == user.github_user
    ).order_by(
        MarketplaceWebhookEvent.received_at.desc()
    ).limit(50).all()
    
    # Format user data safely
    user_data = format_subscription_user_data(user)
    
    # Build nav links based on installation mode
    webhooks_link = ""
    if config.INSTALLATION_MODE == "cloud":
        webhooks_link = '<a href="/admin/webhooks">View All Webhooks</a>'
    
    # Generate HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="robots" content="noindex, nofollow">
        <title>Admin - User Subscription: {user_data['github_user_escaped']}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
                margin-top: 0;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 10px;
            }}
            h2 {{
                color: #333;
                margin-top: 30px;
                border-bottom: 1px solid #ddd;
                padding-bottom: 10px;
            }}
            .nav-links {{
                margin-bottom: 20px;
            }}
            .nav-links a {{
                color: #4CAF50;
                text-decoration: none;
                margin-right: 20px;
            }}
            .nav-links a:hover {{
                text-decoration: underline;
            }}
            .info-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .info-card {{
                background: #f9f9f9;
                padding: 20px;
                border-radius: 8px;
                border-left: 4px solid #4CAF50;
            }}
            .info-label {{
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
                margin-bottom: 8px;
            }}
            .info-value {{
                font-size: 18px;
                font-weight: 600;
                color: #333;
            }}
            .badge {{
                display: inline-block;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
            }}
            .badge-active {{
                background: #10b981;
                color: white;
            }}
            .badge-trial {{
                background: #f59e0b;
                color: white;
            }}
            .badge-free {{
                background: #6b7280;
                color: white;
            }}
            .badge-override {{
                background: #ef4444;
                color: white;
            }}
            .badge-success {{
                background: #d4edda;
                color: #155724;
            }}
            .badge-pending {{
                background: #fff3cd;
                color: #856404;
            }}
            .badge-error {{
                background: #f8d7da;
                color: #721c24;
            }}
            .badge-purchased {{
                background: #d1ecf1;
                color: #0c5460;
            }}
            .badge-cancelled {{
                background: #f8d7da;
                color: #721c24;
            }}
            .badge-changed {{
                background: #cce5ff;
                color: #004085;
            }}
            .null-value {{
                color: #999;
                font-style: italic;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
                font-size: 13px;
            }}
            th {{
                background-color: #4CAF50;
                color: white;
                padding: 12px 8px;
                text-align: left;
                font-weight: 600;
            }}
            td {{
                padding: 10px 8px;
                border-bottom: 1px solid #ddd;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="nav-links">
                <a href="/admin/users">← Back to Users</a>
                {webhooks_link}
            </div>
            
            <h1>📊 Subscription Details: {user_data['github_user_escaped']}</h1>
            
            <h2>Current Subscription Status</h2>
            <div class="info-grid">
                <div class="info-card">
                    <div class="info-label">User ID</div>
                    <div class="info-value">{user_data['user_id']}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Email</div>
                    <div class="info-value">{user_data['github_email_escaped']}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Account Type</div>
                    <div class="info-value">{user_data['account_type_escaped']}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Marketplace Plan</div>
                    <div class="info-value">{user_data['marketplace_plan_escaped']}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Subscription Status</div>
                    <div class="info-value">{user_data['subscription_status']}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Next Billing Date</div>
                    <div class="info-value">{user_data['next_billing']}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Unit Count</div>
                    <div class="info-value">{user_data['unit_count']}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Last Updated</div>
                    <div class="info-value">{user_data['marketplace_updated']}</div>
                </div>
                <div class="info-card">
                    <div class="info-label">Admin Override</div>
                    <div class="info-value">{user_data['admin_override_html']}</div>
                </div>
            </div>
            
            <h2>Billing History (Webhook Events)</h2>
    """
    
    html_content += generate_subscription_event_rows_html(events)
    
    html_content += """
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


