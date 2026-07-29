#!/usr/bin/env python3
"""
Migration script to add the action_groups and action_group_memberships tables.

Lets users organize the shared Actions catalog into named, workspace-wide
groups (e.g. "Deployment"). An action can belong to any number of groups.
This script can be run on existing databases.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL

def migrate_database():
    """Add action_groups and action_group_memberships tables if they don't exist."""
    print("🔧 Running migration to add action_groups tables...")

    try:
        engine = create_engine(DATABASE_URL)

        if "sqlite" in DATABASE_URL:
            migrate_sqlite(engine)
        else:
            migrate_postgresql(engine)

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise

def migrate_sqlite(engine):
    """Migrate SQLite database"""
    with engine.begin() as connection:
        result = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='action_groups'"
        ))

        if not result.fetchone():
            print("📌 Creating action_groups table...")
            connection.execute(text("""
                CREATE TABLE action_groups (
                    action_group_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_modified_by VARCHAR(255)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_action_groups_action_group_id ON action_groups (action_group_id)"
            ))
            print("✅ Table action_groups created successfully")
        else:
            print("✅ Table action_groups already exists, skipping")

        result = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='action_group_memberships'"
        ))

        if not result.fetchone():
            print("📌 Creating action_group_memberships table...")
            connection.execute(text("""
                CREATE TABLE action_group_memberships (
                    action_group_id INTEGER NOT NULL,
                    actions_project_id INTEGER NOT NULL,
                    PRIMARY KEY (action_group_id, actions_project_id),
                    FOREIGN KEY (action_group_id) REFERENCES action_groups (action_group_id) ON DELETE CASCADE,
                    FOREIGN KEY (actions_project_id) REFERENCES actions_projects (actions_project_id) ON DELETE CASCADE
                )
            """))
            print("✅ Table action_group_memberships created successfully")
        else:
            print("✅ Table action_group_memberships already exists, skipping")

def migrate_postgresql(engine):
    """Migrate PostgreSQL database"""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'action_groups'
        """))

        if not result.fetchone():
            print("📌 Creating action_groups table...")
            connection.execute(text("""
                CREATE TABLE action_groups (
                    action_group_id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_modified_by VARCHAR(255)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_action_groups_action_group_id ON action_groups (action_group_id)"
            ))
            print("✅ Table action_groups created successfully")
        else:
            print("✅ Table action_groups already exists, skipping")

        result = connection.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'action_group_memberships'
        """))

        if not result.fetchone():
            print("📌 Creating action_group_memberships table...")
            connection.execute(text("""
                CREATE TABLE action_group_memberships (
                    action_group_id INTEGER NOT NULL,
                    actions_project_id INTEGER NOT NULL,
                    PRIMARY KEY (action_group_id, actions_project_id),
                    FOREIGN KEY (action_group_id) REFERENCES action_groups (action_group_id) ON DELETE CASCADE,
                    FOREIGN KEY (actions_project_id) REFERENCES actions_projects (actions_project_id) ON DELETE CASCADE
                )
            """))
            print("✅ Table action_group_memberships created successfully")
        else:
            print("✅ Table action_group_memberships already exists, skipping")

if __name__ == "__main__":
    migrate_database()
