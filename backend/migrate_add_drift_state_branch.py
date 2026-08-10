"""
Migration: key drift state by branch as well as repo (drift hardening PR 5).

`workflow_drift_states` recorded one row per (workflow, repo). Drift is now
checked against every branch a project delivers to, and each branch drifts
independently, so the key becomes (workflow_id, repo_id, branch).

The old key is a table-level `UNIQUE (workflow_id, repo_id)` declared inside
CREATE TABLE. SQLite cannot drop a table constraint, so SQLite gets a full
table rebuild; PostgreSQL can DROP CONSTRAINT in place.

Existing rows are removed rather than backfilled. The branch a legacy row
referred to is not knowable offline — it needs a GitHub call — and a row
carrying an unknown branch would never match a real check again. It would sit
there with has_drift=1 and permanently inflate the project's drift count via
recompute_project_drift_summary. This table is a derived cache whose only job
is holding "previous state" for transition detection, so the next drift check
repopulates it correctly.

One consequence, deliberate: on the first check after upgrading, each
currently-drifted (workflow, repo, branch) emits one drift.detected. Those
notifications name the branch for the first time, which is information the
user did not previously have.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "workflow_drift_states"
OLD_CONSTRAINT = "uq_workflow_drift_state_workflow_repo"
NEW_INDEX = "uq_workflow_drift_state_workflow_repo_branch"

SQLITE_REBUILD = f"""
CREATE TABLE {TABLE}__new (
    state_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    workflow_id INTEGER NOT NULL REFERENCES workflows (workflow_id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repos (repo_id) ON DELETE CASCADE,
    branch VARCHAR(255) NOT NULL DEFAULT '',
    has_drift BOOLEAN NOT NULL DEFAULT 0,
    content_hash VARCHAR(64),
    drift_cycle_count INTEGER NOT NULL DEFAULT 0,
    last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workflow_id, repo_id, branch)
)
"""


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


def _has_branch_column(conn, database_url: str) -> bool:
    if "sqlite" in database_url:
        cols = conn.execute(text(f"PRAGMA table_info({TABLE})")).fetchall()
        return any(c[1] == "branch" for c in cols)
    row = conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = :t AND column_name = 'branch'
            """
        ),
        {"t": TABLE},
    ).fetchone()
    return bool(row)


def _migrate_sqlite(conn) -> None:
    """Rebuild the table: SQLite cannot drop the old UNIQUE(workflow_id, repo_id)."""
    removed = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
    conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}__new"))
    conn.execute(text(SQLITE_REBUILD))
    # Deliberately no row copy — see the module docstring.
    conn.execute(text(f"DROP TABLE {TABLE}"))
    conn.execute(text(f"ALTER TABLE {TABLE}__new RENAME TO {TABLE}"))
    conn.execute(text(
        f"CREATE INDEX IF NOT EXISTS ix_workflow_drift_states_project_id ON {TABLE} (project_id)"
    ))
    print(f"✅ Rebuilt {TABLE} keyed by (workflow_id, repo_id, branch)")
    if removed:
        print(f"   Cleared {removed} cached drift row(s) — the next drift check repopulates them")


def _migrate_postgres(conn) -> None:
    removed = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
    conn.execute(text(f"DELETE FROM {TABLE}"))
    conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS branch VARCHAR(255) NOT NULL DEFAULT ''"))
    # The original UNIQUE was unnamed in CREATE TABLE, so find it by shape
    # rather than assuming a name PostgreSQL generated.
    conn.execute(text(f"""
        DO $$
        DECLARE c text;
        BEGIN
            FOR c IN
                SELECT conname FROM pg_constraint
                WHERE conrelid = '{TABLE}'::regclass AND contype = 'u'
            LOOP
                EXECUTE format('ALTER TABLE {TABLE} DROP CONSTRAINT %I', c);
            END LOOP;
        END $$;
    """))
    conn.execute(text(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX} ON {TABLE} (workflow_id, repo_id, branch)"
    ))
    print(f"✅ {TABLE} keyed by (workflow_id, repo_id, branch)")
    if removed:
        print(f"   Cleared {removed} cached drift row(s) — the next drift check repopulates them")


def run_migration():
    """Add branch to the drift-state key."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Keying drift state by branch...")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        if not _table_exists(conn, database_url):
            print(f"⏭️ {TABLE} table does not exist yet, skipping migration")
            return

        if _has_branch_column(conn, database_url):
            print("✅ Drift state already keyed by branch, skipping")
            return

        if "sqlite" in database_url:
            _migrate_sqlite(conn)
        else:
            _migrate_postgres(conn)


if __name__ == "__main__":
    run_migration()
