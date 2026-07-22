"""
Migration: Add admin_override columns to accounts table

Adds columns for tracking manual admin overrides of account tiers:
- admin_override: Boolean flag indicating if tier is manually set
- admin_override_until: Expiration date for override (NULL = indefinite)

This enables admins to manually set account tiers that won't be overridden
by marketplace webhooks.
"""

import os
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./actionsmanager.db")

def run_migration():
    """Run the migration to add admin override columns"""
    print("🔄 Starting migration: Add admin_override columns to accounts table")
    
    # Create engine and session
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Check if accounts table exists
        inspector = inspect(engine)
        if 'accounts' not in inspector.get_table_names():
            print("⚠️ Warning: accounts table does not exist yet")
            print("   Migration will be applied when database is initialized")
            print("   The model already includes the admin_override columns")
            return
        
        # Check if columns already exist
        columns = [col['name'] for col in inspector.get_columns('accounts')]
        
        if 'admin_override' in columns and 'admin_override_until' in columns:
            print("✅ Migration already applied - columns exist")
            return
        
        # Check database type
        is_sqlite = "sqlite" in DATABASE_URL.lower()
        
        # Add admin_override column if it doesn't exist
        if 'admin_override' not in columns:
            print("📝 Adding admin_override column...")
            if is_sqlite:
                session.execute(text("""
                    ALTER TABLE accounts ADD COLUMN admin_override BOOLEAN DEFAULT 0 NOT NULL
                """))
            else:  # PostgreSQL
                session.execute(text("""
                    ALTER TABLE accounts ADD COLUMN admin_override BOOLEAN DEFAULT FALSE NOT NULL
                """))
        
        # Add admin_override_until column if it doesn't exist
        if 'admin_override_until' not in columns:
            print("📝 Adding admin_override_until column...")
            if is_sqlite:
                session.execute(text("""
                    ALTER TABLE accounts ADD COLUMN admin_override_until TIMESTAMP NULL
                """))
            else:  # PostgreSQL
                session.execute(text("""
                    ALTER TABLE accounts ADD COLUMN admin_override_until TIMESTAMP WITH TIME ZONE NULL
                """))
        
        session.commit()
        print("✅ Migration completed successfully!")
        print("   - Added admin_override column (BOOLEAN, default FALSE)")
        print("   - Added admin_override_until column (TIMESTAMP, nullable)")
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


if __name__ == "__main__":
    run_migration()
