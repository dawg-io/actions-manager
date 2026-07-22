"""
Database Migration: Add Marketplace Webhook Support

This migration adds:
1. Marketplace billing metadata columns to accounts table
2. New marketplace_webhook_events table for webhook auditing

Run this script to update an existing database:
    python migrate_add_marketplace_webhooks.py
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

def add_marketplace_columns(conn, is_sqlite):
    """Add marketplace metadata columns to accounts table"""
    print("📝 Adding marketplace metadata columns to accounts table...")
    
    columns_to_add = [
        ("marketplace_account_id", "INTEGER"),
        ("marketplace_plan", "VARCHAR(50)"),
        ("marketplace_unit_count", "INTEGER"),
        ("marketplace_on_free_trial", "BOOLEAN DEFAULT FALSE" if not is_sqlite else "INTEGER DEFAULT 0"),
        ("marketplace_next_billing_date", "TIMESTAMP" if not is_sqlite else "DATETIME"),
        ("marketplace_updated_at", "TIMESTAMP" if not is_sqlite else "DATETIME"),
    ]
    
    for column_name, column_type in columns_to_add:
        try:
            sql = f"ALTER TABLE accounts ADD COLUMN {column_name} {column_type}"
            conn.execute(text(sql))
            print(f"✅ Added column: {column_name}")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print(f"ℹ️ Column {column_name} already exists, skipping")
            else:
                print(f"⚠️ Warning adding column {column_name}: {str(e)}")
    
    conn.commit()


def create_webhook_events_table(conn, is_sqlite):
    """Create marketplace_webhook_events table"""
    print("📝 Creating marketplace_webhook_events table...")
    
    if is_sqlite:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS marketplace_webhook_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type VARCHAR(100) NOT NULL,
            action VARCHAR(50),
            github_user VARCHAR(255),
            marketplace_account_id INTEGER,
            plan_name VARCHAR(50),
            payload TEXT NOT NULL,
            signature VARCHAR(255),
            processed INTEGER DEFAULT 0 NOT NULL,
            processing_error VARCHAR(500),
            retry_count INTEGER DEFAULT 0 NOT NULL,
            received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        )
        """
    else:
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS marketplace_webhook_events (
            event_id SERIAL PRIMARY KEY,
            event_type VARCHAR(100) NOT NULL,
            action VARCHAR(50),
            github_user VARCHAR(255),
            marketplace_account_id INTEGER,
            plan_name VARCHAR(50),
            payload TEXT NOT NULL,
            signature VARCHAR(255),
            processed BOOLEAN DEFAULT FALSE NOT NULL,
            processing_error VARCHAR(500),
            retry_count INTEGER DEFAULT 0 NOT NULL,
            received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )
        """
    
    conn.execute(text(create_table_sql))
    conn.commit()
    print("✅ Created marketplace_webhook_events table")


def create_webhook_indexes(conn):
    """Create indexes for marketplace_webhook_events table"""
    print("📝 Creating indexes...")
    
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_webhook_event_type ON marketplace_webhook_events(event_type)",
        "CREATE INDEX IF NOT EXISTS idx_webhook_action ON marketplace_webhook_events(action)",
        "CREATE INDEX IF NOT EXISTS idx_webhook_github_user ON marketplace_webhook_events(github_user)",
        "CREATE INDEX IF NOT EXISTS idx_webhook_received_at ON marketplace_webhook_events(received_at)",
    ]
    
    for index_sql in indexes:
        try:
            conn.execute(text(index_sql))
            print("✅ Created index")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("ℹ️ Index already exists, skipping")
            else:
                print(f"⚠️ Warning creating index: {str(e)}")
    
    conn.commit()


def migrate():
    """Apply migration to add marketplace webhook support"""
    
    with engine.connect() as conn:
        print("🔄 Starting marketplace webhook migration...")
        
        # Check if we're using SQLite or PostgreSQL
        is_sqlite = "sqlite" in DATABASE_URL
        
        try:
            add_marketplace_columns(conn, is_sqlite)
            create_webhook_events_table(conn, is_sqlite)
            create_webhook_indexes(conn)
            
            print("✅ Migration completed successfully!")
            
        except Exception as e:
            print(f"❌ Error during migration: {str(e)}")
            conn.rollback()
            raise

if __name__ == "__main__":
    migrate()
