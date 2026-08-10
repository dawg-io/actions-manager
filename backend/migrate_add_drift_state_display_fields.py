"""
Migration: store enough drift state to render the panel without calling GitHub.

Opening a project ran a full live drift check. The per-(workflow, repo, branch)
state already recorded *whether* something drifted; these two columns add what
the list needs to render faithfully from that state alone:

  github_sha         - lets identical drifts across repos/branches be grouped,
                       and shows the SHA pair without a fetch.
  deleted_in_github  - "deleted" and "drifted" are different states with
                       different actions offered. Without this the cached list
                       would show a deleted workflow as ordinary drift.

The workflow YAML is deliberately *not* cached. A diff is only meaningful
against GitHub's current content, so it is fetched when the user opens one.
Replaying a stored snapshot would risk showing a diff that no longer matches
reality — the same class of problem as reporting a stale "clean".

Both columns are additive and nullable/defaulted, so existing rows stay valid
and the next check fills them in.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "workflow_drift_states"
COLUMNS = {
    "github_sha": "VARCHAR(255)",
    "deleted_in_github": "BOOLEAN NOT NULL DEFAULT 0",
}
POSTGRES_COLUMNS = {
    "github_sha": "VARCHAR(255)",
    "deleted_in_github": "BOOLEAN NOT NULL DEFAULT FALSE",
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
    """Add the display-only columns to the drift state table."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Adding drift-state display fields...")
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

    print(f"✅ Drift-state display fields present ({added} added)")


if __name__ == "__main__":
    run_migration()
