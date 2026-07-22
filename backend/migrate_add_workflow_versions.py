#!/usr/bin/env python3
"""
Migration script to add workflow_versions table for version history tracking.
This script can be run on existing databases to add the new feature.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL

def migrate_database():
    """Add workflow_versions table if it doesn't exist."""
    print("🔧 Running migration to add workflow_versions table...")
    
    try:
        # Create engine
        engine = create_engine(DATABASE_URL)
        
        # Check if we're using SQLite or PostgreSQL
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
        # Check if table already exists
        result = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_versions'"
        ))
        
        if not result.fetchone():
            print("📌 Creating workflow_versions table...")
            connection.execute(text("""
                CREATE TABLE workflow_versions (
                    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id INTEGER NOT NULL,
                    version_number INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    version_metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY (workflow_id) REFERENCES workflows (workflow_id) ON DELETE CASCADE,
                    UNIQUE (workflow_id, version_number)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_workflow_versions_workflow_id ON workflow_versions (workflow_id)"
            ))
            connection.execute(text(
                "CREATE INDEX ix_workflow_versions_version_id ON workflow_versions (version_id)"
            ))
            print("✅ Table created successfully")
        else:
            print("✅ Table already exists, skipping migration")

def migrate_postgresql(engine):
    """Migrate PostgreSQL database"""
    with engine.begin() as connection:
        # Check if table already exists
        result = connection.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'workflow_versions'
        """))
        
        if not result.fetchone():
            print("📌 Creating workflow_versions table...")
            connection.execute(text("""
                CREATE TABLE workflow_versions (
                    version_id SERIAL PRIMARY KEY,
                    workflow_id INTEGER NOT NULL,
                    version_number INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    version_metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY (workflow_id) REFERENCES workflows (workflow_id) ON DELETE CASCADE,
                    UNIQUE (workflow_id, version_number)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_workflow_versions_workflow_id ON workflow_versions (workflow_id)"
            ))
            connection.execute(text(
                "CREATE INDEX ix_workflow_versions_version_id ON workflow_versions (version_id)"
            ))
            print("✅ Table created successfully")
        else:
            print("✅ Table already exists, skipping migration")

if __name__ == "__main__":
    migrate_database()
