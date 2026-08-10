"""
Migration: take workspace membership away from the reserved seed account and
give admin back to the person who installed the application.

The seed account (`__actionsmanager_seed__`) owns the pre-populated Actions
Projects catalog. It is created by a migration, so on a fresh self-hosted
install it exists before anyone has logged in and therefore holds the lowest
user_id. Two places treated "lowest user_id" as "the installer":

  * migrate_add_workspace_members seeded it as the workspace admin;
  * auth._ensure_workspace_membership counted its membership row, so the first
    real human to log in looked like the second user and got read_only.

The result was a workspace whose only admin was a machine account that cannot
log in, with every human read-only and no one able to change roles — the
lockout _ensure_admin_exists was written to prevent. Both sources are fixed;
this repairs databases that already went through it.

Promotion targets the real account with the lowest user_id: the first human to
log in, which on a self-hosted install is whoever set it up. It only fires when
no real admin is left, so a workspace that already has a human admin keeps the
roles it has.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url
from models import SEED_ACCOUNT_GITHUB_USER

REQUIRED_TABLES = ("accounts", "workspace_members")


def _table_exists(conn, database_url: str, table: str) -> bool:
    if "sqlite" in database_url:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchone()
    else:
        row = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
                """
            ),
            {"t": table},
        ).fetchone()
    return bool(row)


def _revoke_seed_membership(conn) -> int:
    """Delete the seed account's membership row. Returns rows removed."""
    result = conn.execute(
        text(
            """
            DELETE FROM workspace_members
            WHERE user_id IN (SELECT user_id FROM accounts WHERE github_user = :seed)
            """
        ),
        {"seed": SEED_ACCOUNT_GITHUB_USER},
    )
    return result.rowcount or 0


def _restore_human_admin(conn) -> None:
    """Promote the earliest real member if no real admin remains."""
    admin_count = conn.execute(
        text(
            """
            SELECT COUNT(*) FROM workspace_members wm
            JOIN accounts a ON a.user_id = wm.user_id
            WHERE wm.workspace_role = 'admin' AND a.github_user != :seed
            """
        ),
        {"seed": SEED_ACCOUNT_GITHUB_USER},
    ).scalar()

    if admin_count:
        return

    target = conn.execute(
        text(
            """
            SELECT wm.id, a.github_user FROM workspace_members wm
            JOIN accounts a ON a.user_id = wm.user_id
            WHERE a.github_user != :seed
            ORDER BY wm.user_id ASC LIMIT 1
            """
        ),
        {"seed": SEED_ACCOUNT_GITHUB_USER},
    ).fetchone()

    if not target:
        # Nobody has logged in yet. _ensure_workspace_membership will make the
        # first real login an admin now that the seed is not counted.
        print("   No human members yet — the first user to log in becomes admin")
        return

    conn.execute(
        text("UPDATE workspace_members SET workspace_role = 'admin' WHERE id = :id"),
        {"id": target[0]},
    )
    print(f"   👑 Restored workspace admin to {target[1]}")


def run_migration():
    """Remove seed-account membership and ensure a human admin exists."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Checking workspace admin ownership...")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        for table in REQUIRED_TABLES:
            if not _table_exists(conn, database_url, table):
                print(f"⏭️ {table} table does not exist yet, skipping migration")
                return

        removed = _revoke_seed_membership(conn)
        if removed:
            print(f"   Removed {removed} workspace membership from {SEED_ACCOUNT_GITHUB_USER}")

        _restore_human_admin(conn)

    print("✅ Workspace admin ownership verified")


if __name__ == "__main__":
    run_migration()
