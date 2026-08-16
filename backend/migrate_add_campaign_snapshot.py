"""
Migration: Add the campaign name and creation-time snapshot columns.

Adds campaign_name and campaign_description — the name and notes the user gives
a campaign when creating it. Without them a campaign is named by deriving a
title from its PR rows on every read, so every run against the same workflows
reads identically.

Adds target_repos, base_commits, policy_version, branch_protection and
target_pr_urls — JSON strings capturing the resolved target repo list, each
target's base commit SHA and branch protection rules, the workflow versions
applied, and the PR opened against each target, all as of the moment the
campaign was created.

Everything else a campaign displays is derived live from the surviving PR rows,
so without these columns a campaign silently re-reads against today's repo
list, branch heads and workflow content, and targets that produced no PR leave
no trace at all.

All are nullable: pre-existing campaigns keep NULL and fall back to the
derived name and the derived-only rendering. They are deliberately not backfilled — the historical
values are not recoverable, and inventing them from current state would be
exactly the drift this snapshot exists to prevent.

Supports both SQLite and PostgreSQL.
"""

import sqlite3
import sys
from pathlib import Path
from migration_utils import get_migration_database_url, get_database_type
from database import DATABASE_URL as APP_DATABASE_URL

CAMPAIGN_COLUMNS = (
    "campaign_name", "campaign_description",
    "target_repos", "base_commits", "policy_version", "branch_protection", "target_pr_urls",
)


def _resolve_sqlite_db_path() -> Path:
    return Path(APP_DATABASE_URL.replace("sqlite:///", "", 1))


def run_sqlite_migration():
    db_path = _resolve_sqlite_db_path()

    if not db_path.exists():
        print(f"⚠️ SQLite database file not found at {db_path}. "
              "Schema will include the campaign snapshot columns when the database is created.")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='project_pr_campaigns'"
        )
        if not cursor.fetchone():
            print("⚠️ project_pr_campaigns table does not exist yet, skipping migration")
            return

        cursor.execute("PRAGMA table_info(project_pr_campaigns)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        for column in CAMPAIGN_COLUMNS:
            if column in existing_columns:
                print(f"✅ Column already exists (skipped): {column}")
                continue
            cursor.execute(f"ALTER TABLE project_pr_campaigns ADD COLUMN {column} TEXT")
            print(f"✅ Added column: project_pr_campaigns.{column}")

        conn.commit()
        print("✅ SQLite campaign snapshot migration complete.")
    except Exception as exc:
        print(f"❌ SQLite migration failed: {exc}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def run_postgresql_migration():
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 module not installed. Please install it to use PostgreSQL.")
        print("   Run: pip install psycopg2-binary")
        sys.exit(1)

    db_url = get_migration_database_url()

    if not db_url or ('postgresql' not in db_url and 'postgres' not in db_url):
        print("⚠️ DATABASE_URL environment variable not set for PostgreSQL.")
        print("   Migration will be applied when database is configured.")
        return

    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'project_pr_campaigns'
            """)
            if not cursor.fetchone():
                print("⚠️ project_pr_campaigns table does not exist yet, skipping migration")
                return

            for column in CAMPAIGN_COLUMNS:
                cursor.execute(
                    f"ALTER TABLE project_pr_campaigns ADD COLUMN IF NOT EXISTS {column} TEXT"
                )
                print(f"✅ Ensured column exists: project_pr_campaigns.{column}")

            conn.commit()
            print("✅ PostgreSQL campaign snapshot migration complete.")
        except Exception as exc:
            print(f"❌ PostgreSQL migration failed: {exc}")
            conn.rollback()
            sys.exit(1)
        finally:
            cursor.close()
            conn.close()

    except Exception as exc:
        print(f"❌ Failed to connect to PostgreSQL database: {exc}")
        sys.exit(1)


def run_migration():
    db_type = get_database_type()
    print(f"🔄 Running campaign snapshot migration for {db_type.upper()}...")

    if db_type == 'postgresql':
        run_postgresql_migration()
    else:
        run_sqlite_migration()


if __name__ == "__main__":
    run_migration()
