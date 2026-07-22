"""
Database Migration: Add Admin Tracking Columns to Accounts Table

This migration adds the following columns to the accounts table:
- last_login_at: TIMESTAMPTZ to track when users last logged in
- last_login_ip: VARCHAR(45) to track the IP address of the last login (supports IPv6)

These columns are required for the admin users page to display login tracking information.
"""

import sys
from sqlalchemy import text
from database import engine, SessionLocal

def migrate():
    """Add last_login_at and last_login_ip columns to accounts table"""
    
    db = SessionLocal()
    
    try:
        # Check database type (PostgreSQL vs SQLite)
        db_url = str(engine.url)
        is_postgres = db_url.startswith('postgresql')
        
        if is_postgres:
            # PostgreSQL migration
            print("📊 Running PostgreSQL migration...")
            
            # Add last_login_at column
            db.execute(text("""
                ALTER TABLE accounts 
                ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ NULL
            """))
            
            # Add last_login_ip column  
            db.execute(text("""
                ALTER TABLE accounts 
                ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(45) NULL
            """))
            
        else:
            # SQLite migration
            print("📊 Running SQLite migration...")
            
            # SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS
            # We need to check if columns exist first
            result = db.execute(text("PRAGMA table_info(accounts)")).fetchall()
            existing_columns = [row[1] for row in result]
            
            if 'last_login_at' not in existing_columns:
                db.execute(text("""
                    ALTER TABLE accounts 
                    ADD COLUMN last_login_at DATETIME NULL
                """))
                print("✅ Added last_login_at column")
            else:
                print("⏭️  last_login_at column already exists")
            
            if 'last_login_ip' not in existing_columns:
                db.execute(text("""
                    ALTER TABLE accounts 
                    ADD COLUMN last_login_ip VARCHAR(45) NULL
                """))
                print("✅ Added last_login_ip column")
            else:
                print("⏭️  last_login_ip column already exists")
        
        db.commit()
        print("✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Migration: Add Admin Tracking Columns")
    print("=" * 60)
    migrate()
