"""
Migration script to add per-repository branch override columns to the
``project_repos`` association table.

Adds the following columns (all idempotent / no-op if already present):

- ``branch_config_mode``  VARCHAR(20)  NOT NULL DEFAULT 'inherit'
- ``branch_option``       VARCHAR(50)  NULL
- ``branch_regex``        VARCHAR(255) NULL
- ``branch_max_age_days`` INTEGER      NULL

Existing ``project_repos`` rows default to ``branch_config_mode='inherit'``
so previously-saved projects continue to behave exactly as before.

Supports both SQLite and PostgreSQL.
"""

from sqlalchemy import text, inspect
from database import engine


def _add_column_if_missing(conn, inspector, table: str, column: str, ddl: str, backfill: str = None):
    """Add ``column`` to ``table`` using the provided ``ddl`` if absent.

    Optionally backfills existing rows with ``backfill`` (a full SQL UPDATE
    statement) after the column is created.
    """
    columns = [c["name"] for c in inspector.get_columns(table)]
    if column in columns:
        print(f"⚠️ Column {table}.{column} already exists, skipping creation")
        return False

    print(f"✅ Adding {table}.{column}...")
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
    if backfill:
        conn.execute(text(backfill))
    return True


def run_migration():
    """Run the migration to add per-repo branch override columns."""
    print("🔄 Starting migration: add per-repo branch override columns to project_repos")

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            inspector = inspect(engine)

            # ``branch_config_mode`` – use plain ALTER TABLE syntax (portable
            # across SQLite and PostgreSQL).  SQLite does not support adding
            # a NOT NULL column without a default, so we add it as nullable
            # and backfill, then leave it nullable.  The application enforces
            # the "inherit" default when reading.
            _add_column_if_missing(
                conn,
                inspector,
                "project_repos",
                "branch_config_mode",
                "branch_config_mode VARCHAR(20)",
                backfill="UPDATE project_repos SET branch_config_mode = 'inherit' WHERE branch_config_mode IS NULL",
            )

            # Refresh inspector after each ALTER TABLE so subsequent column
            # checks see the new columns.
            inspector = inspect(engine)
            _add_column_if_missing(
                conn,
                inspector,
                "project_repos",
                "branch_option",
                "branch_option VARCHAR(50)",
            )

            inspector = inspect(engine)
            _add_column_if_missing(
                conn,
                inspector,
                "project_repos",
                "branch_regex",
                "branch_regex VARCHAR(255)",
            )

            inspector = inspect(engine)
            _add_column_if_missing(
                conn,
                inspector,
                "project_repos",
                "branch_max_age_days",
                "branch_max_age_days INTEGER",
            )

            # Final safety backfill so any NULL ``branch_config_mode`` values
            # (e.g., rows inserted between adding the column and the backfill
            # in a prior partial run) get the canonical "inherit" default.
            conn.execute(text(
                "UPDATE project_repos SET branch_config_mode = 'inherit' "
                "WHERE branch_config_mode IS NULL"
            ))

            trans.commit()
            print("✅ Migration completed successfully!")
        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
