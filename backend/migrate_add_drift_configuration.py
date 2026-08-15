"""
Migration: move drift sweep configuration from env vars into the database.

Drift cadence used to be settable only through DRIFT_SWEEP_ENABLED,
DRIFT_RECHECK_INTERVAL_MINUTES, DRIFT_SWEEP_BATCH_SIZE and
DRIFT_SWEEP_POLL_SECONDS, so tuning it needed shell access and a redeploy, and
every project on the install shared one interval.

Two additions:
  * drift_settings - single row of global defaults, edited by workspace admins.
    No row is created here; the worker treats "no row" as "use the defaults",
    which is the same contract notification_settings uses.
  * projects.drift_check_interval_minutes - per-project override. NULL means
    inherit the global default, 0 means never sweep this project.

Both are additive: existing rows keep inheriting the previous behaviour, and
the defaults match the old env-var defaults, so an operator who never set them
sees no change.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "projects"
COLUMNS = {
    "drift_check_interval_minutes": "INTEGER",
}
POSTGRES_COLUMNS = {
    "drift_check_interval_minutes": "INTEGER",
}

SQLITE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS drift_settings (
        settings_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sweep_enabled BOOLEAN NOT NULL DEFAULT 1,
        recheck_interval_minutes INTEGER NOT NULL DEFAULT 15,
        batch_size INTEGER NOT NULL DEFAULT 5,
        poll_interval_seconds INTEGER NOT NULL DEFAULT 60,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

POSTGRES_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS drift_settings (
        settings_id SERIAL PRIMARY KEY,
        sweep_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        recheck_interval_minutes INTEGER NOT NULL DEFAULT 15,
        batch_size INTEGER NOT NULL DEFAULT 5,
        poll_interval_seconds INTEGER NOT NULL DEFAULT 60,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


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
    """Create drift_settings and add the per-project drift interval column."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Adding drift configuration...")
    engine = create_engine(database_url)
    is_sqlite = "sqlite" in database_url

    with engine.begin() as conn:
        for statement in (SQLITE_STATEMENTS if is_sqlite else POSTGRES_STATEMENTS):
            conn.execute(text(statement))
        print("   ➕ drift_settings")

        if not _table_exists(conn, database_url):
            print(f"⏭️ {TABLE} table does not exist yet, skipping column")
            return

        present = _existing_columns(conn, database_url)
        added = 0
        for name, ddl in (COLUMNS if is_sqlite else POSTGRES_COLUMNS).items():
            if name in present:
                continue
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl}"))
            added += 1
            print(f"   ➕ {name}")

    print(f"✅ drift configuration present ({added} column(s) added)")


if __name__ == "__main__":
    run_migration()
