"""
Migration: track consecutive drift-check failures per project, for backoff.

A project whose owner's token was revoked (or whose repo was deleted, or any
other persistent failure) was re-checked by the sweep every
DRIFT_RECHECK_INTERVAL_MINUTES forever, at full batch cost, with no way to
back off. This column is the counter that makes backoff possible: incremented
whenever a check ends in "check_failed", reset to 0 whenever a check produces
real signal ("clean" or "drifted" - both mean GitHub actually answered).

Additive and nullable-defaulted, so existing rows stay valid and start at 0.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "projects"
COLUMNS = {
    "drift_check_failure_count": "INTEGER NOT NULL DEFAULT 0",
}
POSTGRES_COLUMNS = {
    "drift_check_failure_count": "INTEGER NOT NULL DEFAULT 0",
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
    """Add the drift-check-failure-count column to the projects table."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Adding drift_check_failure_count...")
    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url
    wanted = COLUMNS if is_sqlite else POSTGRES_COLUMNS

    with engine.begin() as conn:
        if not _table_exists(conn, database_url):
            print(f"⏭️ {TABLE} table does not exist yet, skipping migration")
            return

        present = _existing_columns(conn, database_url)
        added = 0
        for name, ddl in wanted.items():
            if name in present:
                continue
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}"))
            added += 1
            print(f"   ➕ {name}")

    print(f"✅ drift_check_failure_count present ({added} added)")


if __name__ == "__main__":
    run_migration()
