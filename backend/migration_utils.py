"""
Shared utilities for database migration scripts.
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

# Must match the canonical self-hosted data directory used by database.py.
_SELF_HOSTED_DATA_DIR = Path("/app/data")


def get_database_url():
    """Get the DATABASE_URL, constructing from individual POSTGRES_* env vars if needed.

    Some deployments (e.g. Kubernetes) expose individual POSTGRES_* environment
    variables rather than a single DATABASE_URL.  This helper replicates the
    same URL-building logic used by database.py so that migration scripts work
    correctly in both configurations.

    Priority (mirrors database.py's resolution order):
      1. Explicit DATABASE_URL env var.
      2. Individual POSTGRES_* env vars.
      3. INSTALLATION_MODE=self-hosted → /app/data/actions_manager.db.
      4. Otherwise, an empty string (callers must explicitly opt into a
         development/test fallback such as ./test.db).
    """
    db_url = os.getenv('DATABASE_URL', '')
    if db_url:
        return db_url

    # Construct URL from individual POSTGRES_* env vars (mirrors database.py)
    user = os.getenv('POSTGRES_USER', '').strip()
    password = os.getenv('POSTGRES_PASSWORD', '').strip()
    db = os.getenv('POSTGRES_DB', '').strip()
    host = os.getenv('POSTGRES_HOST', '').strip()
    port = os.getenv('POSTGRES_PORT', '').strip()

    if all([user, password, db, host, port]):
        safe_password = quote_plus(password)
        return f"postgresql://{user}:{safe_password}@{host}:{port}/{db}"

    # Self-hosted deployments store their SQLite database in the persistent
    # /app/data volume rather than the development ./test.db path.
    if os.getenv('INSTALLATION_MODE', '').strip().lower() == 'self-hosted':
        try:
            _SELF_HOSTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Non-fatal: the directory may already exist or be read-only
            # (e.g. during unit tests running outside the container).
            pass
        return f"sqlite:///{_SELF_HOSTED_DATA_DIR / 'actions_manager.db'}"

    return ''


def get_migration_database_url():
    """Get a database URL for running migrations, preferring a dedicated migration user.

    ALTER TABLE and schema changes require the connecting user to own the target
    tables.  In Kubernetes deployments the application user is typically not the
    table owner (the superuser that ran the initial schema creation is).

    This helper checks for dedicated migration credentials first:
      POSTGRES_MIGRATION_USER     – superuser or table-owner account (optional)
      POSTGRES_MIGRATION_PASSWORD – password for that account (optional)

    If those vars are not set it falls back to get_database_url() (i.e. the
    regular app credentials).  The host, port and database name are always taken
    from the individual POSTGRES_* vars; if only DATABASE_URL is set (without
    individual POSTGRES_* vars) the migration user override is ignored and the
    base DATABASE_URL is returned unchanged.
    """
    migration_user = os.getenv('POSTGRES_MIGRATION_USER', '').strip()
    migration_password = os.getenv('POSTGRES_MIGRATION_PASSWORD', '').strip()

    if migration_user and migration_password:
        # Build URL using migration credentials but the same host/db as the app
        db = os.getenv('POSTGRES_DB', '').strip()
        host = os.getenv('POSTGRES_HOST', '').strip()
        port = os.getenv('POSTGRES_PORT', '').strip()

        if all([db, host, port]):
            safe_user = quote_plus(migration_user)
            safe_password = quote_plus(migration_password)
            return f"postgresql://{safe_user}:{safe_password}@{host}:{port}/{db}"

        # Individual POSTGRES_* vars not set – fall through to base URL below.
        # Migration user override cannot be applied without them.

    # No dedicated migration user (or missing host/db/port vars) – fall back
    return get_database_url()


def get_database_type():
    """Determine if we're using SQLite or PostgreSQL based on environment variables."""
    db_url = get_database_url()
    if 'postgresql' in db_url or 'postgres' in db_url:
        return 'postgresql'
    return 'sqlite'
