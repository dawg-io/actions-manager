"""
Database Migration: Add effective_date column to marketplace_webhook_events

This migration adds:
1. effective_date column to marketplace_webhook_events table

Run this script to update an existing database:
    python migrate_add_effective_date.py
"""

import os
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# Load PostgreSQL connection details, fallback to SQLite for testing
POSTGRES_USER = os.getenv("POSTGRES_USER", "").strip()
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "").strip()
POSTGRES_DB = os.getenv("POSTGRES_DB", "").strip()
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "").strip()
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "").strip()

# Use SQLite if PostgreSQL not configured (for testing)
if not all([POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT]):
    DATABASE_URL = "sqlite:///./test.db"
    print("⚠️ Using SQLite for testing - PostgreSQL not configured")
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
else:
    # PostgreSQL configuration
    safe_password = quote_plus(POSTGRES_PASSWORD)
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{safe_password}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False
    )

def migrate():
    """Apply migration to add effective_date column"""
    
    with engine.begin() as conn:  # Use begin() for automatic transaction management
        print("🔄 Starting effective_date migration...")
        
        # Check if we're using SQLite or PostgreSQL
        is_sqlite = "sqlite" in DATABASE_URL
        
        try:
            # Add effective_date column to marketplace_webhook_events table
            print("📝 Adding effective_date column to marketplace_webhook_events table...")
            
            column_type = "DATETIME" if is_sqlite else "TIMESTAMP"
            
            try:
                sql = f"ALTER TABLE marketplace_webhook_events ADD COLUMN effective_date {column_type}"
                conn.execute(text(sql))
                print(f"✅ Added column: effective_date")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"ℹ️ Column effective_date already exists, skipping")
                else:
                    print(f"⚠️ Warning adding column effective_date: {str(e)}")
                    raise  # Re-raise to trigger rollback
            
            print("✅ Migration completed successfully!")
            # Transaction will auto-commit when exiting the 'with' block
            
        except Exception as e:
            print(f"❌ Error during migration: {str(e)}")
            # Transaction will auto-rollback when exiting the 'with' block on exception
            raise

if __name__ == "__main__":
    migrate()
