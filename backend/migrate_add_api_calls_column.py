"""
Database Migration: Add API Calls Tracking Column to Accounts Table

This migration adds the following columns to the accounts table:
- github_api_calls: INTEGER to track the total number of GitHub API calls made by each user
- github_api_calls_today: INTEGER to track API calls in the last 24 hours (resets daily)
- api_calls_reset_at: TIMESTAMP to track when the daily counter was last reset

This column is required for the admin users page to display API usage information.
"""

import sys
from sqlalchemy import text
from database import engine, SessionLocal

def migrate():
    """Add github_api_calls, github_api_calls_today, and api_calls_reset_at columns to accounts table"""
    
    db = SessionLocal()
    
    try:
        # Check database type (PostgreSQL vs SQLite)
        db_url = str(engine.url)
        is_postgres = db_url.startswith('postgresql')
        
        if is_postgres:
            # PostgreSQL migration
            print("📊 Running PostgreSQL migration...")
            
            # Add github_api_calls column
            db.execute(text("""
                ALTER TABLE accounts 
                ADD COLUMN IF NOT EXISTS github_api_calls INTEGER NOT NULL DEFAULT 0
            """))
            
            # Add github_api_calls_today column
            db.execute(text("""
                ALTER TABLE accounts 
                ADD COLUMN IF NOT EXISTS github_api_calls_today INTEGER NOT NULL DEFAULT 0
            """))
            
            # Add api_calls_reset_at column
            db.execute(text("""
                ALTER TABLE accounts 
                ADD COLUMN IF NOT EXISTS api_calls_reset_at TIMESTAMPTZ NULL
            """))
            
        else:
            # SQLite migration
            print("📊 Running SQLite migration...")
            
            # SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS
            # We need to check if column exists first
            result = db.execute(text("PRAGMA table_info(accounts)")).fetchall()
            existing_columns = [row[1] for row in result]
            
            if 'github_api_calls' not in existing_columns:
                db.execute(text("""
                    ALTER TABLE accounts 
                    ADD COLUMN github_api_calls INTEGER NOT NULL DEFAULT 0
                """))
                print("✅ Added github_api_calls column")
            else:
                print("⏭️  github_api_calls column already exists")
            
            if 'github_api_calls_today' not in existing_columns:
                db.execute(text("""
                    ALTER TABLE accounts 
                    ADD COLUMN github_api_calls_today INTEGER NOT NULL DEFAULT 0
                """))
                print("✅ Added github_api_calls_today column")
            else:
                print("⏭️  github_api_calls_today column already exists")
            
            if 'api_calls_reset_at' not in existing_columns:
                db.execute(text("""
                    ALTER TABLE accounts 
                    ADD COLUMN api_calls_reset_at DATETIME NULL
                """))
                print("✅ Added api_calls_reset_at column")
            else:
                print("⏭️  api_calls_reset_at column already exists")
        
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
    print("Migration: Add API Calls Tracking Column")
    print("=" * 60)
    migrate()
