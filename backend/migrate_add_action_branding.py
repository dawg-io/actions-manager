"""
Migration script to add branding_icon and branding_color columns to
actions_projects table.

These store the optional `branding: {icon, color}` block from a GitHub
action.yml/action.yaml manifest (the same document GitHub Marketplace reads
to render its icon badges). Both columns are nullable — actions without a
branding block, or with one GitHub Marketplace itself wouldn't recognize,
simply have NULL here and the UI falls back to a generic icon.
"""

from sqlalchemy import create_engine, inspect, text

from database import DATABASE_URL


def run_migration():
    """Run the migration to add branding_icon and branding_color columns."""
    print("🔄 Starting migration: add branding columns to actions_projects table")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            inspector = inspect(engine)

            if "actions_projects" not in inspector.get_table_names():
                print("⚠️ actions_projects table does not exist yet.")
                print("   Migration will be applied when database is created.")
                trans.rollback()
                return

            columns = [col["name"] for col in inspector.get_columns("actions_projects")]

            if "branding_icon" not in columns:
                print("✅ Adding branding_icon column...")
                conn.execute(text("ALTER TABLE actions_projects ADD COLUMN branding_icon VARCHAR(50)"))
                print("✅ Column branding_icon added (nullable)")
            else:
                print("⚠️ Column branding_icon already exists, skipping creation")

            if "branding_color" not in columns:
                print("✅ Adding branding_color column...")
                conn.execute(text("ALTER TABLE actions_projects ADD COLUMN branding_color VARCHAR(20)"))
                print("✅ Column branding_color added (nullable)")
            else:
                print("⚠️ Column branding_color already exists, skipping creation")

            trans.commit()
            print("✅ Migration completed successfully!")
        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run_migration()
