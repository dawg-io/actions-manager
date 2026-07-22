"""
Database Migration: Normalize Professional Account Tier

This migration updates any accounts with account_type='pro' to 'professional'
to maintain consistency across the application. The 'pro' alias is still
supported in code for backward compatibility, but the canonical value in the
database should be 'professional'.
"""

import sys
from sqlalchemy import text
from database import SessionLocal

def migrate():
    """Normalize 'pro' account types to 'professional'"""
    
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("Migration: Normalize Professional Account Tier")
        print("=" * 60)
        
        # Count accounts with 'pro' account_type
        result = db.execute(text("""
            SELECT COUNT(*) as count FROM accounts WHERE account_type = 'pro'
        """))
        count = result.fetchone()[0]
        
        print(f"📊 Found {count} accounts with account_type='pro'")
        
        if count > 0:
            # Update 'pro' to 'professional'
            db.execute(text("""
                UPDATE accounts 
                SET account_type = 'professional' 
                WHERE account_type = 'pro'
            """))
            
            db.commit()
            print(f"✅ Updated {count} accounts from 'pro' to 'professional'")
        else:
            print("⏭️  No accounts to update")
        
        # Show current account type distribution
        result = db.execute(text("""
            SELECT account_type, COUNT(*) as count 
            FROM accounts 
            GROUP BY account_type
            ORDER BY account_type
        """))
        
        print("\n📊 Current Account Type Distribution:")
        print("-" * 40)
        for row in result:
            print(f"  {row[0]}: {row[1]} accounts")
        print("-" * 40)
        
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
