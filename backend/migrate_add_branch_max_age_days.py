"""
Migration script to add branch_max_age_days column to projects table
and migrate legacy branch_option values.

This migration:
1. Adds the branch_max_age_days column with default value of 30
2. Migrates legacy branch_option values:
   - "all" → "default" (safest migration)
   - "regex" → "pattern"
"""

from sqlalchemy import create_engine, text, inspect
from database import SQLALCHEMY_DATABASE_URL

def run_migration():
    """Run the migration to add branch_max_age_days and migrate legacy values."""
    print("🔄 Starting migration: add branch_max_age_days and migrate branch_option values")
    
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
    
    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()
        
        try:
            # Check if column already exists using SQLAlchemy inspector (portable across databases)
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('projects')]
            
            if 'branch_max_age_days' not in columns:
                print("✅ Adding branch_max_age_days column...")
                # Use portable ALTER TABLE syntax
                conn.execute(text("""
                    ALTER TABLE projects 
                    ADD COLUMN branch_max_age_days INTEGER
                """))
                # Set default value separately for better portability
                conn.execute(text("""
                    UPDATE projects 
                    SET branch_max_age_days = 30 
                    WHERE branch_max_age_days IS NULL
                """))
                print("✅ Column added successfully")
            else:
                print("⚠️ Column branch_max_age_days already exists, skipping creation")
            
            # Migrate legacy branch_option values
            print("🔄 Migrating legacy branch_option values...")
            
            # Migrate "all" to "default"
            result = conn.execute(text("""
                UPDATE projects 
                SET branch_option = 'default' 
                WHERE branch_option = 'all'
            """))
            all_count = result.rowcount
            if all_count > 0:
                print(f"✅ Migrated {all_count} projects from 'all' to 'default'")
            
            # Migrate "regex" to "pattern"
            result = conn.execute(text("""
                UPDATE projects 
                SET branch_option = 'pattern' 
                WHERE branch_option = 'regex'
            """))
            regex_count = result.rowcount
            if regex_count > 0:
                print(f"✅ Migrated {regex_count} projects from 'regex' to 'pattern'")
            
            # Set default value for any NULL branch_max_age_days
            result = conn.execute(text("""
                UPDATE projects 
                SET branch_max_age_days = 30 
                WHERE branch_max_age_days IS NULL
            """))
            null_count = result.rowcount
            if null_count > 0:
                print(f"✅ Set default value (30) for {null_count} projects with NULL branch_max_age_days")
            
            # Commit transaction
            trans.commit()
            print("✅ Migration completed successfully!")
            
        except Exception as e:
            trans.rollback()
            print(f"❌ Migration failed: {e}")
            raise

if __name__ == "__main__":
    run_migration()
