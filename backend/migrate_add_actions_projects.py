#!/usr/bin/env python3
"""
Migration script to add the actions_projects table.

Stores custom GitHub Actions imported from a repo's actions.yaml file
(issue #1687). This script can be run on existing databases.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL

def migrate_database():
    """Add actions_projects table if it doesn't exist."""
    print("🔧 Running migration to add actions_projects table...")

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
            "SELECT name FROM sqlite_master WHERE type='table' AND name='actions_projects'"
        ))

        if not result.fetchone():
            print("📌 Creating actions_projects table...")
            connection.execute(text("""
                CREATE TABLE actions_projects (
                    actions_project_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    source_url VARCHAR(500) NOT NULL,
                    owner VARCHAR(255) NOT NULL,
                    repo VARCHAR(255) NOT NULL,
                    ref VARCHAR(255) NOT NULL,
                    yaml_path VARCHAR(500) NOT NULL DEFAULT 'actions.yaml',
                    inputs_json TEXT NOT NULL DEFAULT '[]',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_modified_by VARCHAR(255),
                    FOREIGN KEY (user_id) REFERENCES accounts (user_id) ON DELETE CASCADE
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_actions_projects_user_id ON actions_projects (user_id)"
            ))
            connection.execute(text(
                "CREATE INDEX ix_actions_projects_actions_project_id ON actions_projects (actions_project_id)"
            ))
            print("✅ Table created successfully")
        else:
            print("✅ Table already exists, skipping migration")

def migrate_postgresql(engine):
    """Migrate PostgreSQL database"""
    with engine.begin() as connection:
        result = connection.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'actions_projects'
        """))

        if not result.fetchone():
            print("📌 Creating actions_projects table...")
            connection.execute(text("""
                CREATE TABLE actions_projects (
                    actions_project_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    source_url VARCHAR(500) NOT NULL,
                    owner VARCHAR(255) NOT NULL,
                    repo VARCHAR(255) NOT NULL,
                    ref VARCHAR(255) NOT NULL,
                    yaml_path VARCHAR(500) NOT NULL DEFAULT 'actions.yaml',
                    inputs_json TEXT NOT NULL DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_modified_by VARCHAR(255),
                    FOREIGN KEY (user_id) REFERENCES accounts (user_id) ON DELETE CASCADE
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_actions_projects_user_id ON actions_projects (user_id)"
            ))
            connection.execute(text(
                "CREATE INDEX ix_actions_projects_actions_project_id ON actions_projects (actions_project_id)"
            ))
            print("✅ Table created successfully")
        else:
            print("✅ Table already exists, skipping migration")

if __name__ == "__main__":
    migrate_database()
