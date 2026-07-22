"""
Migration script to add project_memberships table.

This migration adds the project_memberships table for Phase 2 RBAC
(project-level permissions). Each row grants a workspace member access
to a specific project with a role (project_editor or project_viewer).

Admin workspace members have implicit full access to all
projects and do not need rows in this table.
"""

from sqlalchemy import create_engine, text, inspect
from database import DATABASE_URL


def run_migration():
    """Run the migration to add the project_memberships table."""
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)

    existing_tables = inspector.get_table_names()
    if "project_memberships" in existing_tables:
        print("✅ project_memberships table already exists — skipping migration.")
        return

    # Determine dialect for auto-increment syntax
    is_sqlite = "sqlite" in DATABASE_URL

    if is_sqlite:
        ddl = """
        CREATE TABLE project_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            project_role VARCHAR(30) NOT NULL DEFAULT 'project_viewer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES accounts(user_id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            CONSTRAINT uq_user_project_membership UNIQUE (user_id, project_id)
        );
        """
    else:
        ddl = """
        CREATE TABLE project_memberships (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            project_role VARCHAR(30) NOT NULL DEFAULT 'project_viewer',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES accounts(user_id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            CONSTRAINT uq_user_project_membership UNIQUE (user_id, project_id)
        );
        """

    with engine.begin() as conn:
        conn.execute(text(ddl))

    # Create indexes
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_memberships_user_id ON project_memberships (user_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_memberships_project_id ON project_memberships (project_id);"))

    print("✅ project_memberships table created successfully.")


if __name__ == "__main__":
    run_migration()
