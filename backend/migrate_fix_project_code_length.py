"""
Database migration script to fix project_code column length.

This migration alters the project_code column from VARCHAR(4) to VARCHAR(10)
to support the new project key generation logic that can create keys up to 10 characters.

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
        # SQLite doesn't have a direct ALTER COLUMN command for changing data type
        # We need to check the current schema and recreate if needed
        cursor.execute("PRAGMA table_info(projects)")
        columns_info = cursor.fetchall()
        
        # Check if project_code has the correct length
        project_code_col = next((col for col in columns_info if col[1] == 'project_code'), None)
        
        if project_code_col:
            # SQLite stores type as text, check if it's restricted to 4 characters
            # For SQLite, the VARCHAR length is not enforced, so we just verify the column exists
            print("✅ project_code column exists in SQLite (SQLite doesn't enforce VARCHAR length)")
            print("   No migration needed for SQLite - VARCHAR length is not enforced")
        else:
            print("⚠️ project_code column not found in projects table")
        
        # Commit (no actual changes for SQLite)
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
            # Check current column definition
            cursor.execute("""
                SELECT character_maximum_length 
                FROM information_schema.columns 
                WHERE table_name='projects' AND column_name='project_code'
            """)
            
            result = cursor.fetchone()
            
            if result:
                current_length = result[0]
                print(f"📌 Current project_code column length: {current_length}")
                
                if current_length < 10:
                    print(f"🔄 Altering project_code column from VARCHAR({current_length}) to VARCHAR(10) (PostgreSQL)...")
                    cursor.execute("""
                        ALTER TABLE projects 
                        ALTER COLUMN project_code TYPE VARCHAR(10)
                    """)
                    print("   ✅ project_code column altered successfully")
                else:
                    print("✅ project_code column already has sufficient length")
            else:
                print("⚠️ project_code column not found in projects table")
            
            # Commit the changes
            conn.commit()
            print("✅ PostgreSQL migration completed successfully")
            
        except Exception as e:
            err_msg = str(e).lower()
            if 'must be owner' in err_msg or 'permission denied' in err_msg or 'insufficient privilege' in err_msg:
                print(f"❌ PostgreSQL migration failed: {e}")
                print()
                print("   ℹ️  The migration user does not own the 'projects' table.")
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
    print(f"🔄 Running project_code length fix migration for {db_type.upper()}...")
    
    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()

if __name__ == "__main__":
    run_migration()
