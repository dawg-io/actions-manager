"""
Database migration script to add PR tracking functionality.

This migration adds:
1. pr_state column to projects table
2. project_pull_requests table for tracking PRs

Supports both SQLite and PostgreSQL databases.
"""

import sqlite3
import sys
import os
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type

def run_sqlite_migration():
    """Run the migration for SQLite database."""
    db_path = Path(__file__).parent / "actionsmanager.db"
    
    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}")
        print("   Migration will be applied when database is created.")
        return
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if pr_state column already exists in projects table
        cursor.execute("PRAGMA table_info(projects)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'pr_state' not in columns:
            print("✅ Adding pr_state column to projects table (SQLite)...")
            cursor.execute("""
                ALTER TABLE projects 
                ADD COLUMN pr_state VARCHAR(20) NOT NULL DEFAULT 'editing'
            """)
            print("   pr_state column added successfully")
        else:
            print("✅ pr_state column already exists in projects table")
        
        # Check if project_pull_requests table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='project_pull_requests'
        """)
        
        if not cursor.fetchone():
            print("✅ Creating project_pull_requests table (SQLite)...")
            cursor.execute("""
                CREATE TABLE project_pull_requests (
                    pr_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    repo_name VARCHAR(255) NOT NULL,
                    pr_number INTEGER NOT NULL,
                    pr_url VARCHAR(500) NOT NULL,
                    pr_state VARCHAR(20) NOT NULL DEFAULT 'open',
                    branch_name VARCHAR(255) NOT NULL,
                    target_branch VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                    UNIQUE (project_id, repo_name, branch_name, target_branch)
                )
            """)
            
            # Create indexes for better query performance
            cursor.execute("""
                CREATE INDEX idx_project_pull_requests_project_id 
                ON project_pull_requests (project_id)
            """)
            
            print("   project_pull_requests table created successfully")
        else:
            print("✅ project_pull_requests table already exists")
        
        # Commit the changes
        conn.commit()
        print("✅ SQLite migration completed successfully")
        
    except Exception as e:
        print(f"❌ SQLite migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

def run_postgresql_migration():
    """Run the migration for PostgreSQL database."""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 module not installed. Please install it to use PostgreSQL.")
        print("   Run: pip install psycopg2-binary")
        sys.exit(1)
    
    db_url = get_migration_database_url()
    
    if not db_url or ('postgresql' not in db_url and 'postgres' not in db_url):
        print("⚠️ DATABASE_URL environment variable not set for PostgreSQL")
        print("   Migration will be applied when database is configured.")
        return
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        try:
            # Check if pr_state column already exists in projects table
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='projects' AND column_name='pr_state'
            """)
            
            if not cursor.fetchone():
                print("✅ Adding pr_state column to projects table (PostgreSQL)...")
                cursor.execute("""
                    ALTER TABLE projects 
                    ADD COLUMN pr_state VARCHAR(20) NOT NULL DEFAULT 'editing'
                """)
                print("   pr_state column added successfully")
            else:
                print("✅ pr_state column already exists in projects table")
            
            # Check if project_pull_requests table exists
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema='public' AND table_name='project_pull_requests'
            """)
            
            if not cursor.fetchone():
                print("✅ Creating project_pull_requests table (PostgreSQL)...")
                cursor.execute("""
                    CREATE TABLE project_pull_requests (
                        pr_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        project_id INTEGER NOT NULL,
                        repo_name VARCHAR(255) NOT NULL,
                        pr_number INTEGER NOT NULL,
                        pr_url VARCHAR(500) NOT NULL,
                        pr_state VARCHAR(20) NOT NULL DEFAULT 'open',
                        branch_name VARCHAR(255) NOT NULL,
                        target_branch VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (project_id) REFERENCES projects (project_id) ON DELETE CASCADE,
                        CONSTRAINT uq_project_pr_branch_target UNIQUE (project_id, repo_name, branch_name, target_branch)
                    )
                """)
                
                # Create indexes for better query performance
                cursor.execute("""
                    CREATE INDEX idx_project_pull_requests_project_id 
                    ON project_pull_requests (project_id)
                """)
                
                print("   project_pull_requests table created successfully")
            else:
                print("✅ project_pull_requests table already exists")
            
            # Commit the changes
            conn.commit()
            print("✅ PostgreSQL migration completed successfully")
            
        except Exception as e:
            err_msg = str(e).lower()
            if 'must be owner' in err_msg or 'permission denied' in err_msg or 'insufficient privilege' in err_msg:
                print(f"❌ PostgreSQL migration failed: {e}")
                print()
                print("   ℹ️  The migration user does not own one or more tables.")
                print("   To fix this, run the following as a PostgreSQL superuser:")
                print()
                print("     Option 1 – transfer ownership to your app user:")
                pg_user = os.getenv('POSTGRES_USER', '<app_user>')
                print(f"       ALTER TABLE projects OWNER TO {pg_user};")
                print()
                print("     Option 2 – set dedicated migration credentials in your deployment:")
                print("       POSTGRES_MIGRATION_USER=<superuser>")
                print("       POSTGRES_MIGRATION_PASSWORD=<superuser_password>")
            else:
                print(f"❌ PostgreSQL migration failed: {e}")
            conn.rollback()
            sys.exit(1)
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL database: {e}")
        sys.exit(1)

def run_migration():
    """Run the appropriate migration based on database type."""
    db_type = get_database_type()
    print(f"🔄 Running PR tracking migration for {db_type.upper()}...")
    
    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()

if __name__ == "__main__":
    run_migration()

