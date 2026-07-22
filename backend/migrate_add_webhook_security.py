#!/usr/bin/env python3
"""
Database migration to add security and audit fields to marketplace_webhook_events table.

This migration adds:
- source_ip: Source IP address of webhook request
- headers: Request headers as JSON for audit trail

Run this migration:
    python migrate_add_webhook_security.py
"""

import sqlite3
import os

def migrate():
    """Add security and audit columns to marketplace_webhook_events table"""
    
    # Determine database path
    db_path = os.getenv("DATABASE_URL", "sqlite:///./actionsmanager.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    
    print(f"Connecting to database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='marketplace_webhook_events'
        """)
        
        if not cursor.fetchone():
            print("⚠️  Table 'marketplace_webhook_events' does not exist yet.")
            print("   This is normal if you haven't run the marketplace webhook migration yet.")
            print("   Run migrate_add_marketplace_webhooks.py first.")
            conn.close()
            return
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(marketplace_webhook_events)")
        columns = [row[1] for row in cursor.fetchall()]
        
        changes_made = False
        
        # Add source_ip column if it doesn't exist
        if 'source_ip' not in columns:
            print("Adding 'source_ip' column...")
            cursor.execute("""
                ALTER TABLE marketplace_webhook_events 
                ADD COLUMN source_ip VARCHAR(45)
            """)
            changes_made = True
            print("✅ Added 'source_ip' column")
        else:
            print("ℹ️  Column 'source_ip' already exists")
        
        # Add headers column if it doesn't exist
        if 'headers' not in columns:
            print("Adding 'headers' column...")
            cursor.execute("""
                ALTER TABLE marketplace_webhook_events 
                ADD COLUMN headers TEXT
            """)
            changes_made = True
            print("✅ Added 'headers' column")
        else:
            print("ℹ️  Column 'headers' already exists")
        
        if changes_made:
            conn.commit()
            print("\n✅ Migration completed successfully!")
        else:
            print("\n✅ No migration needed - all columns already exist")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return

if __name__ == "__main__":
    print("="*60)
    print("Webhook Security Migration")
    print("="*60)
    migrate()
