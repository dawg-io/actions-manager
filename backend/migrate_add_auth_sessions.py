#!/usr/bin/env python3
"""
Add database-backed authentication sessions.

The app stores only SHA-256 hashes of opaque session tokens. This migration is
idempotent for SQLite and PostgreSQL via SQLAlchemy's checkfirst support.
"""

import sys

from database import engine
from models import AuthSession


def main() -> int:
    try:
        AuthSession.__table__.create(bind=engine, checkfirst=True)
        print("🎉 Auth sessions migration completed")
        return 0
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
