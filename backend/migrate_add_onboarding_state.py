"""
Migration: add first-login onboarding state to the accounts table.

Two additive, nullable columns:
  * onboarding_completed_at - set both when the guided tour finishes and when
    it is dismissed, so NULL means "never shown" rather than "not finished".
    Without that distinction a user who skips the tour is prompted forever.
  * onboarding_step - the furthest tour step reached, so an abandoned tour can
    resume where it left off instead of restarting.

Existing rows stay NULL on purpose: every account that predates this migration
is treated as never having seen onboarding, which is what we want the first
time they log in after upgrading.

Uses get_migration_database_url() rather than the app engine because ALTER
TABLE needs the table owner, which on Kubernetes is not the application user.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "accounts"

SQLITE_COLUMNS = {
    "onboarding_completed_at": "DATETIME",
    "onboarding_step": "VARCHAR(40)",
}
POSTGRES_COLUMNS = {
    "onboarding_completed_at": "TIMESTAMP WITH TIME ZONE",
    "onboarding_step": "VARCHAR(40)",
}


def _table_exists(conn, database_url: str) -> bool:
    if "sqlite" in database_url:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": TABLE},
        ).fetchone()
    else:
        row = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
                """
            ),
            {"t": TABLE},
        ).fetchone()
    return bool(row)


def _existing_columns(conn, database_url: str) -> set:
    if "sqlite" in database_url:
        return {r[1] for r in conn.execute(text(f"PRAGMA table_info({TABLE})"))}
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": TABLE},
    ).fetchall()
    return {r[0] for r in rows}


def run_migration():
    """Add the onboarding state columns to accounts."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Adding onboarding state columns...")
    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url

    with engine.begin() as conn:
        if not _table_exists(conn, database_url):
            print(f"⏭️ {TABLE} table does not exist yet, skipping migration")
            return

        present = _existing_columns(conn, database_url)
        added = 0
        for name, ddl in (SQLITE_COLUMNS if is_sqlite else POSTGRES_COLUMNS).items():
            if name in present:
                continue
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}"))
            added += 1
            print(f"   ➕ {name}")

    print(f"✅ onboarding state present ({added} column(s) added)")


if __name__ == "__main__":
    run_migration()
