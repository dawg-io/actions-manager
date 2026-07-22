#!/usr/bin/env python3
"""
Migration script to fix workflow unique constraints.
This removes ALL unique constraints on workflow_name to allow
multiple projects to have workflows with identical names.
"""

from sqlalchemy import create_engine, text
from database import DATABASE_URL

def migrate_database():
    """Remove all workflow unique constraints to allow multiple projects to have workflows with identical names."""
    print("🔧 Running migration to remove workflow unique constraints...")
    
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
        # SQLite doesn't support dropping constraints directly
        # We need to recreate the table
        print("📌 Checking SQLite workflow table constraints...")
        
        # Check current table schema
        result = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='workflows'"))
        current_schema = result.fetchone()
        if current_schema:
            print(f"Current workflows table schema: {current_schema[0]}")
            
            # Check if the schema contains any unique constraint on workflow_name
            if "UNIQUE" in current_schema[0] and "workflow_name" in current_schema[0]:
                print("⚠️ Found unique constraint involving workflow_name, recreating table...")
                
                # Begin transaction
                connection.execute(text("BEGIN TRANSACTION"))
                
                try:
                    # Create backup table
                    connection.execute(text("""
                        CREATE TABLE workflows_backup AS SELECT * FROM workflows
                    """))
                    
                    # Drop original table
                    connection.execute(text("DROP TABLE workflows"))
                    
                    # Recreate table without any unique constraints on workflow_name
                    connection.execute(text("""
                        CREATE TABLE workflows (
                            workflow_id INTEGER PRIMARY KEY,
                            workflow_name VARCHAR(255) NOT NULL,
                            workflow_yaml VARCHAR NOT NULL,
                            workflow_git_hash VARCHAR(255),
                            reusable_workflow BOOLEAN DEFAULT 0,
                            created_at DATETIME DEFAULT (datetime('now')),
                            updated_at DATETIME DEFAULT (datetime('now'))
                        )
                    """))
                    
                    # Restore data - no longer need OR IGNORE since no unique constraints
                    connection.execute(text("""
                        INSERT INTO workflows 
                        SELECT * FROM workflows_backup
                    """))
                    
                    # Drop backup table
                    connection.execute(text("DROP TABLE workflows_backup"))
                    
                    # Commit transaction
                    connection.execute(text("COMMIT"))
                    print("✅ Table recreated without workflow name unique constraints")
                    print("✅ Projects can now have workflows with identical names")
                    
                except Exception as e:
                    # Rollback on error
                    connection.execute(text("ROLLBACK"))
                    print(f"❌ Error during table recreation: {e}")
                    raise
            else:
                print("✅ No unique constraints on workflow_name found, table schema is correct")

def migrate_postgresql(engine):
    """Migrate PostgreSQL database"""
    with engine.connect() as connection:
        print("📌 Checking PostgreSQL workflow table constraints...")
        
        # Check for existing constraints
        result = connection.execute(text("""
            SELECT conname, contype
            FROM pg_constraint 
            WHERE conrelid = 'workflows'::regclass
        """))
        constraints = result.fetchall()
        
        print("Current constraints on workflows table:")
        for constraint in constraints:
            print(f"  - {constraint[0]} (type: {constraint[1]})")
        
        # Remove the old single-column unique constraint if it exists
        old_constraint_exists = any(
            constraint[0] == 'workflows_workflow_name_key' and constraint[1] == 'u'
            for constraint in constraints
        )
        
        if old_constraint_exists:
            print("⚠️ Found old unique constraint on workflow_name, removing it...")
            connection.execute(text("ALTER TABLE workflows DROP CONSTRAINT workflows_workflow_name_key"))
            print("✅ Old constraint removed")
        else:
            print("✅ No old single-column unique constraint found")
            
        # Remove the composite constraint if it exists (we're removing all uniqueness constraints)
        composite_constraint_exists = any(
            constraint[0] == 'uq_workflow_name_type' and constraint[1] == 'u'
            for constraint in constraints
        )
        
        if composite_constraint_exists:
            print("⚠️ Found composite unique constraint, removing it...")
            connection.execute(text("ALTER TABLE workflows DROP CONSTRAINT uq_workflow_name_type"))
            print("✅ Composite constraint removed")
        else:
            print("✅ No composite constraint found")
            
        print("✅ All workflow name uniqueness constraints have been removed")
        print("✅ Projects can now have workflows with identical names")
        connection.commit()

if __name__ == "__main__":
    migrate_database()