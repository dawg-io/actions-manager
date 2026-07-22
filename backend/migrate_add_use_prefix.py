#!/usr/bin/env python3
"""
Migration script to add use_prefix column to projects table and create new tables
for storing secret and environment variable names.

This migration supports making the AM_{PROJECT_CODE}_ prefix optional.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL

def migrate_database():
    """Add use_prefix column to projects table and create new tables."""
    print("🔧 Running migration to add use_prefix support...")
    
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
        # Check if use_prefix column already exists
        result = connection.execute(text("PRAGMA table_info(projects)"))
        columns = [row[1] for row in result.fetchall()]
        
        if 'use_prefix' not in columns:
            print("📌 Adding use_prefix column to projects table...")
            connection.execute(text(
                "ALTER TABLE projects ADD COLUMN use_prefix BOOLEAN DEFAULT 1 NOT NULL"
            ))
            connection.commit()
            print("✅ use_prefix column added successfully")
        else:
            print("✅ use_prefix column already exists, skipping")
        
        # Check if project_secrets table exists
        result = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_secrets'"
        ))
        if not result.fetchone():
            print("📌 Creating project_secrets table...")
            connection.execute(text("""
                CREATE TABLE project_secrets (
                    secret_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    secret_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                    CONSTRAINT uq_project_secret_name UNIQUE (project_id, secret_name)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_project_secrets_project_id ON project_secrets (project_id)"
            ))
            connection.commit()
            print("✅ project_secrets table created successfully")
        else:
            print("✅ project_secrets table already exists, skipping")
        
        # Check if project_env_vars table exists
        result = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_env_vars'"
        ))
        if not result.fetchone():
            print("📌 Creating project_env_vars table...")
            connection.execute(text("""
                CREATE TABLE project_env_vars (
                    env_var_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    env_var_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                    CONSTRAINT uq_project_env_var_name UNIQUE (project_id, env_var_name)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_project_env_vars_project_id ON project_env_vars (project_id)"
            ))
            connection.commit()
            print("✅ project_env_vars table created successfully")
        else:
            print("✅ project_env_vars table already exists, skipping")

def migrate_postgresql(engine):
    """Migrate PostgreSQL database"""
    with engine.connect() as connection:
        # Check if use_prefix column already exists
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'projects' AND column_name = 'use_prefix'
        """))
        
        if not result.fetchone():
            print("📌 Adding use_prefix column to projects table...")
            connection.execute(text(
                "ALTER TABLE projects ADD COLUMN use_prefix BOOLEAN DEFAULT TRUE NOT NULL"
            ))
            connection.commit()
            print("✅ use_prefix column added successfully")
        else:
            print("✅ use_prefix column already exists, skipping")
        
        # Check if project_secrets table exists
        result = connection.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'project_secrets'
        """))
        if not result.fetchone():
            print("📌 Creating project_secrets table...")
            connection.execute(text("""
                CREATE TABLE project_secrets (
                    secret_id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    secret_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_project_secret_name UNIQUE (project_id, secret_name)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_project_secrets_project_id ON project_secrets (project_id)"
            ))
            connection.commit()
            print("✅ project_secrets table created successfully")
        else:
            print("✅ project_secrets table already exists, skipping")
        
        # Check if project_env_vars table exists
        result = connection.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_name = 'project_env_vars'
        """))
        if not result.fetchone():
            print("📌 Creating project_env_vars table...")
            connection.execute(text("""
                CREATE TABLE project_env_vars (
                    env_var_id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    env_var_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_project_env_var_name UNIQUE (project_id, env_var_name)
                )
            """))
            connection.execute(text(
                "CREATE INDEX ix_project_env_vars_project_id ON project_env_vars (project_id)"
            ))
            connection.commit()
            print("✅ project_env_vars table created successfully")
        else:
            print("✅ project_env_vars table already exists, skipping")

if __name__ == "__main__":
    migrate_database()
