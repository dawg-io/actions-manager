"""
Migration script to add repository_visibility_scope column to projects table.

This migration adds the repository_visibility_scope column with default value 'public'.
Possible values: 'public', 'private'.

Existing projects all default to 'public' to preserve current behavior. Inferring
visibility from linked repositories was considered but is not done here because
the local `repos` table does not store visibility metadata, making any such
inference unreliable at the migration layer. See DATABASE_SCHEMA.md.
"""

from sqlalchemy import create_engine, text, inspect
from database import DATABASE_URL


def run_migration():
    """Run the migration to add repository_visibility_scope column."""
    print("🔄 Starting migration: add repository_visibility_scope column to projects table")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        trans = conn.begin()

        try:
            inspector = inspect(engine)

            if 'projects' not in inspector.get_table_names():
                print("⚠️ projects table does not exist yet.")
                print("   Migration will be applied when database is created.")
                trans.rollback()
                return

            columns = [col['name'] for col in inspector.get_columns('projects')]

            if 'repository_visibility_scope' not in columns:
                print("✅ Adding repository_visibility_scope column...")
                # Add the column with a DB-level DEFAULT and NOT NULL constraint
                # so that non-ORM inserts (or future code paths that bypass the
                # SQLAlchemy model default) cannot persist NULL — keeping the
                # schema consistent with `models.Project.repository_visibility_scope`
                # (`nullable=False`, `default="public"`). Both SQLite and
                # PostgreSQL support `ADD COLUMN ... NOT NULL DEFAULT '...'`,
                # backfilling existing rows with the default in a single step.
                # We do not try to infer from linked repositories here because
                # the local `repos` table does not store visibility metadata —
                # inference is too risky at the migration layer. Defaulting to
                # 'public' is the documented fallback (see DATABASE_SCHEMA.md).
                conn.execute(text("""
                    ALTER TABLE projects
                    ADD COLUMN repository_visibility_scope VARCHAR(10) NOT NULL DEFAULT 'public'
                """))
                # Defensive backfill in case any row was somehow inserted as NULL
                # before the constraint was applied (no-op on a fresh ADD COLUMN).
                conn.execute(text("""
                    UPDATE projects
                    SET repository_visibility_scope = 'public'
                    WHERE repository_visibility_scope IS NULL
                """))
                print("✅ Column added with DEFAULT 'public' NOT NULL; existing rows defaulted to 'public'")
            else:
                print("⚠️ Column repository_visibility_scope already exists, skipping creation")

            trans.commit()
            print("✅ Migration completed successfully!")

        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
