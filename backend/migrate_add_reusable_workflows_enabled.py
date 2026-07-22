#!/usr/bin/env python3
"""
Migration script to add reusable_workflows_enabled column to projects table.
This script can be run on existing databases to add the new feature.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL

def migrate_database():
    """Add reusable_workflows_enabled column to projects table if it doesn't exist."""
    print("🔧 Running migration to add reusable_workflows_enabled column...")
    
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
    with engine.connect() as connection:
        # Check if column already exists
        result = connection.execute(text("PRAGMA table_info(projects)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'reusable_workflows_enabled' not in columns:
            print("📌 Adding reusable_workflows_enabled column to projects table...")
            connection.execute(text(
                "ALTER TABLE projects ADD COLUMN reusable_workflows_enabled BOOLEAN DEFAULT 0 NOT NULL"
            ))
            connection.commit()
            print("✅ Column added successfully")
        else:
            print("✅ Column already exists, skipping migration")

def migrate_postgresql(engine):
    """Migrate PostgreSQL database"""
    with engine.connect() as connection:
        # Check if column already exists
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'projects' AND column_name = 'reusable_workflows_enabled'
        """))
        
        if not result.fetchone():
            print("📌 Adding reusable_workflows_enabled column to projects table...")
            connection.execute(text(
                "ALTER TABLE projects ADD COLUMN reusable_workflows_enabled BOOLEAN DEFAULT FALSE NOT NULL"
            ))
            connection.commit()
            print("✅ Column added successfully")
        else:
            print("✅ Column already exists, skipping migration")

if __name__ == "__main__":
    migrate_database()