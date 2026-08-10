"""
Migration: cache workflow tree listings and their GitHub ETags.

Drift asks GitHub what is in every branch a project delivers to, on every
check, even when nothing has changed. GitHub answers a conditional request
(``If-None-Match``) for unchanged content with a 304, and 304 responses do not
count against the rate limit — so an untouched branch becomes free to
re-verify. Storing the ETag alongside the listing it produced is what makes
that possible: a 304 carries no body, so without the cached mapping there
would be nothing to compare against.

Also holds the cached answer to "has this branch had a recent commit", which
otherwise costs one API call per matched branch per check.

Purely a cache. Dropping a row costs one extra API call and nothing else, so
this migration is safe to re-run and safe to roll back by dropping the table.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "workflow_tree_cache"

SQLITE_CREATE = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id INTEGER NOT NULL REFERENCES repos (repo_id) ON DELETE CASCADE,
    branch VARCHAR(255) NOT NULL,
    etag VARCHAR(255),
    sha_map_json TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    branch_is_recent BOOLEAN,
    branch_head_sha VARCHAR(64),
    UNIQUE (repo_id, branch)
)
"""

POSTGRES_CREATE = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id SERIAL PRIMARY KEY,
    repo_id INTEGER NOT NULL REFERENCES repos (repo_id) ON DELETE CASCADE,
    branch VARCHAR(255) NOT NULL,
    etag VARCHAR(255),
    sha_map_json TEXT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    branch_is_recent BOOLEAN,
    branch_head_sha VARCHAR(64),
    UNIQUE (repo_id, branch)
)
"""

CREATE_REPO_INDEX = (
    f"CREATE INDEX IF NOT EXISTS ix_{TABLE}_repo_id ON {TABLE} (repo_id)"
)


def _repos_table_exists(conn, database_url: str) -> bool:
    if "sqlite" in database_url:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='repos'")
        ).fetchone()
    else:
        row = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'repos'
                """
            )
        ).fetchone()
    return bool(row)


def run_migration():
    """Create the workflow tree cache table."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Adding workflow tree cache...")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        if not _repos_table_exists(conn, database_url):
            print("⏭️ repos table does not exist yet, skipping migration")
            return

        conn.execute(text(SQLITE_CREATE if "sqlite" in database_url else POSTGRES_CREATE))
        conn.execute(text(CREATE_REPO_INDEX))

    print(f"✅ Ensured {TABLE} exists")


if __name__ == "__main__":
    run_migration()
