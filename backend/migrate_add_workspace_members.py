"""
Migration script to create the workspace_members table.

This table tracks application/workspace membership and roles for multi-user support.
Each user has a single membership record with a workspace_role:
  - admin: Full management access
  - member: Standard workspace access
  - read_only: View-only access (default for new users)

Supports both SQLite and PostgreSQL databases.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL


def run_migration():
    """Create the workspace_members table if it does not exist."""
    print("🔄 Starting migration: create workspace_members table")

    try:
        engine = create_engine(DATABASE_URL)

        if "sqlite" in DATABASE_URL:
            _migrate_sqlite(engine)
        else:
            _migrate_postgresql(engine)

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise


def _migrate_sqlite(engine):
    """Create the table for SQLite databases."""
    with engine.begin() as conn:
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_members'"
        ))

        if result.fetchone():
            print("⏭️ Table workspace_members already exists, skipping creation")
        else:
            print("✅ Creating workspace_members table (SQLite)...")
            conn.execute(text("""
                CREATE TABLE workspace_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE
                        REFERENCES accounts(user_id) ON DELETE CASCADE,
                    workspace_role VARCHAR(20) NOT NULL DEFAULT 'read_only',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE INDEX ix_workspace_members_user_id
                    ON workspace_members (user_id)
            """))
            print("✅ Table and index created successfully")

        # Seed existing users who don't yet have a membership record.
        # The first user (lowest user_id) is promoted to admin; others get read_only.
        _seed_existing_users(conn)

    print("✅ SQLite migration completed successfully!")


def _migrate_postgresql(engine):
    """Create the table for PostgreSQL databases."""
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'workspace_members'
        """))

        if result.fetchone():
            print("⏭️ Table workspace_members already exists, skipping creation")
        else:
            print("✅ Creating workspace_members table (PostgreSQL)...")
            conn.execute(text("""
                CREATE TABLE workspace_members (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE
                        REFERENCES accounts(user_id) ON DELETE CASCADE,
                    workspace_role VARCHAR(20) NOT NULL DEFAULT 'read_only',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                CREATE INDEX ix_workspace_members_user_id
                    ON workspace_members (user_id)
            """))
            print("✅ Table and index created successfully")

        # Seed existing users
        _seed_existing_users(conn)

    print("✅ PostgreSQL migration completed successfully!")


def _accounts_table_exists(conn) -> bool:
    """Return True if the 'accounts' table is present in the database."""
    if "sqlite" in DATABASE_URL:
        row = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'"
        )).fetchone()
    else:
        row = conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'accounts'"
        )).fetchone()
    return row is not None


def _seed_existing_users(conn):
    """
    For every Account that does not yet have a workspace_members row,
    insert one.  The account with the lowest user_id is made 'admin';
    all others default to 'read_only'.

    If the 'accounts' table does not yet exist (e.g. a fresh CI database
    that has not run the base schema migration), this function exits
    gracefully so that the workspace_members migration can still succeed.
    """
    if not _accounts_table_exists(conn):
        print("⏭️ 'accounts' table not found — skipping user seed (no existing users)")
        return

    # Find the first (oldest) user_id
    first_row = conn.execute(text(
        "SELECT MIN(user_id) AS first_id FROM accounts"
    )).fetchone()

    first_user_id = first_row[0] if first_row else None
    if first_user_id is None:
        print("⏭️ No existing accounts to seed")
        return

    # Get all accounts that do NOT already have a membership row
    rows = conn.execute(text("""
        SELECT a.user_id
        FROM accounts a
        LEFT JOIN workspace_members wm ON a.user_id = wm.user_id
        WHERE wm.id IS NULL
        ORDER BY a.user_id
    """)).fetchall()

    if not rows:
        print("⏭️ All existing accounts already have workspace membership")
        _ensure_admin_exists(conn)
        return

    for row in rows:
        uid = row[0]
        role = "admin" if uid == first_user_id else "read_only"
        conn.execute(text(
            "INSERT INTO workspace_members (user_id, workspace_role) VALUES (:uid, :role)"
        ), {"uid": uid, "role": role})
        print(f"  ✅ Seeded user {uid} as {role}")

    print(f"✅ Seeded {len(rows)} existing user(s) into workspace_members")

    # Post-seed sanity check
    _ensure_admin_exists(conn)


def _ensure_admin_exists(conn):
    """
    Post-seed sanity check: if workspace_members has rows but zero admins,
    promote the member with the lowest user_id to admin.
    This prevents permanently locking out admin-only operations.
    """
    total = conn.execute(text(
        "SELECT COUNT(*) FROM workspace_members"
    )).scalar()

    if total == 0:
        return  # No members at all — nothing to fix

    admin_count = conn.execute(text(
        "SELECT COUNT(*) FROM workspace_members WHERE workspace_role = 'admin'"
    )).scalar()

    if admin_count > 0:
        return  # At least one admin exists

    # Promote the member with the lowest user_id to admin
    lowest = conn.execute(text(
        "SELECT id, user_id FROM workspace_members ORDER BY user_id ASC LIMIT 1"
    )).fetchone()

    if lowest:
        conn.execute(text(
            "UPDATE workspace_members SET workspace_role = 'admin' WHERE id = :member_id"
        ), {"member_id": lowest[0]})
        print(f"  ⚠️ No admin found — promoted user {lowest[1]} to admin")


if __name__ == "__main__":
    run_migration()
