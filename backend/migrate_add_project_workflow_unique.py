"""
Migration: enforce one project per workflow (issue: drift hardening PR 4).

A Workflow row belongs to exactly one Project. Every code path that creates a
project_workflows association also creates a fresh Workflow, so sharing was
never reachable — but the schema permitted it, and the drift/hash code assumed
it could not happen. This makes the invariant explicit so a future change cannot
silently reintroduce cross-project interference.

A unique INDEX rather than a UniqueConstraint: SQLite cannot add a constraint to
an existing table, so a constraint would require rebuilding project_workflows on
every upgrade. CREATE UNIQUE INDEX works unchanged on both SQLite and PostgreSQL.

Idempotent, and safe to run on a database that somehow does contain a shared
workflow: duplicates are reported and the index is skipped rather than failing,
because deciding which project loses a workflow is not a call this should make.
"""

import os

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "project_workflows"
INDEX_NAME = "uq_project_workflows_workflow_id"

FIND_DUPLICATES = """
SELECT workflow_id, COUNT(*) AS project_count
FROM project_workflows
GROUP BY workflow_id
HAVING COUNT(*) > 1
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


def _report_duplicates(conn) -> int:
    """Print any workflow shared by more than one project. Returns how many."""
    duplicates = conn.execute(text(FIND_DUPLICATES)).fetchall()
    if not duplicates:
        return 0

    print(f"⚠️ {len(duplicates)} workflow(s) are associated with more than one project.")
    print("   The unique index cannot be created until each belongs to exactly one.")
    for workflow_id, project_count in duplicates:
        projects = conn.execute(
            text("SELECT project_id FROM project_workflows WHERE workflow_id = :w ORDER BY project_id"),
            {"w": workflow_id},
        ).fetchall()
        print(f"     workflow_id={workflow_id} is in {project_count} projects: "
              f"{[p[0] for p in projects]}")
    print("   Skipping index creation — resolve these manually, then re-run migrations.")
    return len(duplicates)


def run_migration():
    """Add the unique index enforcing one project per workflow."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Enforcing one project per workflow...")
    engine = create_engine(database_url)

    try:
        with engine.begin() as conn:
            if not _table_exists(conn, database_url):
                print(f"⏭️ {TABLE} table does not exist yet, skipping migration")
                return

            if _report_duplicates(conn):
                return

            conn.execute(text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} ON {TABLE} (workflow_id)"
            ))
            print(f"✅ Ensured unique index exists: {INDEX_NAME}")
    except Exception as e:
        # The `with engine.begin()` block above has already rolled back on its
        # way out, so it's safe to just report and return here rather than
        # crashing the whole migration run over a skippable hardening step.
        err_msg = str(e).lower()
        if 'must be owner' in err_msg or 'permission denied' in err_msg or 'insufficient privilege' in err_msg:
            print(f"⚠️ Could not create {INDEX_NAME}: {e}")
            print()
            print("   ℹ️  The migration user does not own the "
                  f"{TABLE} table, so this hardening step is being skipped.")
            print("   To enable it, either:")
            print()
            print("     Option 1 – transfer ownership to your app user:")
            pg_user = os.getenv('POSTGRES_USER', '<app_user>')
            print(f"       ALTER TABLE {TABLE} OWNER TO {pg_user};")
            print()
            print("     Option 2 – set dedicated migration credentials in your deployment:")
            print("       POSTGRES_MIGRATION_USER=<superuser>")
            print("       POSTGRES_MIGRATION_PASSWORD=<superuser_password>")
            return
        raise


if __name__ == "__main__":
    run_migration()
