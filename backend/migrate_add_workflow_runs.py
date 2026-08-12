"""
Migration: store GitHub Actions runs so build metrics can be computed locally.

Metrics (success rate, duration, queue time, trend) are aggregated from stored
runs rather than fetched on demand, so opening the panel costs no GitHub API
calls and a repository is only re-listed when the data is stale.

Runs are listed per repository — one call covers every workflow — and attributed
to the project owning the matching workflow file.

Safe to re-run and safe to roll back by dropping the table: the rows are a
rebuildable cache of GitHub's own history.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "workflow_runs"

_COLUMNS = """
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repos (repo_id) ON DELETE CASCADE,
    workflow_id INTEGER REFERENCES workflows (workflow_id) ON DELETE SET NULL,
    github_run_id BIGINT NOT NULL,
    run_number INTEGER,
    run_attempt INTEGER,
    workflow_filename VARCHAR(255) NOT NULL,
    workflow_name VARCHAR(255),
    branch VARCHAR(255) NOT NULL DEFAULT '',
    event VARCHAR(50),
    status VARCHAR(30),
    conclusion VARCHAR(30),
    run_created_at TIMESTAMP,
    run_started_at TIMESTAMP,
    run_updated_at TIMESTAMP,
    duration_seconds INTEGER,
    queue_seconds INTEGER,
    html_url VARCHAR(500),
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, repo_id, github_run_id)
"""

SQLITE_CREATE = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    run_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
{_COLUMNS}
)
"""

POSTGRES_CREATE = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    run_row_id SERIAL PRIMARY KEY,
{_COLUMNS}
)
"""

CREATE_INDEXES = (
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_project_id ON {TABLE} (project_id)",
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_repo_id ON {TABLE} (repo_id)",
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_workflow_id ON {TABLE} (workflow_id)",
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_project_created ON {TABLE} (project_id, run_created_at)",
)

_PARENT_TABLES = ("projects", "repos", "workflows")


def _parent_tables_exist(conn, database_url: str) -> bool:
    for table in _PARENT_TABLES:
        if "sqlite" in database_url:
            row = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": table},
            ).fetchone()
        else:
            row = conn.execute(
                text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = :name
                    """
                ),
                {"name": table},
            ).fetchone()
        if not row:
            return False
    return True


def _project_columns(conn, database_url: str) -> set:
    """Introspect through the caller's connection, not a second one.

    ``inspect(engine)`` checks out another pooled connection, which would read
    the schema while this migration's own DDL transaction is still open and
    holding a write lock. Same-connection introspection is what the other
    add-column migrations here do.
    """
    if "sqlite" in database_url:
        return {row[1] for row in conn.execute(text("PRAGMA table_info(projects)"))}
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = 'projects'")
    ).fetchall()
    return {row[0] for row in rows}


def _add_sync_cursor(conn, database_url: str) -> None:
    """Add projects.last_run_sync_at, the build-metrics staleness cursor."""
    if "last_run_sync_at" in _project_columns(conn, database_url):
        print("⚠️ projects.last_run_sync_at already exists, skipping")
        return

    conn.execute(text("ALTER TABLE projects ADD COLUMN last_run_sync_at TIMESTAMP NULL"))
    print("✅ Added projects.last_run_sync_at")


def run_migration():
    """Create the workflow runs table and the project sync cursor."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Adding workflow runs storage...")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        if not _parent_tables_exist(conn, database_url):
            print("⏭️ parent tables do not exist yet, skipping migration")
            return

        conn.execute(text(SQLITE_CREATE if "sqlite" in database_url else POSTGRES_CREATE))
        for statement in CREATE_INDEXES:
            conn.execute(text(statement))
        _add_sync_cursor(conn, database_url)

    print(f"✅ Ensured {TABLE} exists")


if __name__ == "__main__":
    run_migration()
