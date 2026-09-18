"""
Migration: deliver a default Actions Project added to SEED_ACTIONS after an
install was already seeded, exactly once.

migrate_seed_default_actions_projects only runs on a database with no seed
account, so an entry added to SEED_ACTIONS in a later release never reaches an
install that is already seeded. Inserting it on every boot instead is not the
answer either - a default the user deletes must stay deleted.

So each offer gets a durable marker of its own, in seeded_actions_catalog_entries.
The marker is written when an entry is offered and never removed, which is what
lets "already offered" and "never offered" be told apart on a database where the
row is simply absent.

Three cases, per SEED_ACTIONS entry:

  * marker present            -> nothing to do, whether or not the row still exists
  * shipped in the original   -> mark only; the original seed already offered it,
    seed batch                   and re-inserting would resurrect a deleted default
  * a row already exists      -> mark only; a fresh install just seeded it, or the
                                 user imported the same action themselves
  * otherwise                 -> insert it and mark it

Safe to re-run, and safe on both SQLite and PostgreSQL.
"""

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from migration_utils import get_migration_database_url
from database import DATABASE_URL as APP_DATABASE_URL
from models import SEED_ACCOUNT_GITHUB_USER
from migrate_seed_default_actions_projects import SEED_ACTIONS, build_seed_row

MARKER_TABLE = "seeded_actions_catalog_entries"

# The batch migrate_seed_default_actions_projects shipped when it was written.
# On an install that already ran it these were offered, whether or not their rows
# still exist - so they are marked without being re-inserted. Never add to this
# list: a new default belongs in SEED_ACTIONS, and this migration delivers it.
ORIGINAL_SEED_SLUGS = frozenset({
    "actions/checkout",
    "actions/setup-node",
    "actions/setup-python",
    "actions/setup-java",
    "actions/cache",
    "actions/upload-artifact",
    "actions/download-artifact",
})


def _create_marker_table(engine, db_url: str) -> None:
    if MARKER_TABLE in inspect(engine).get_table_names():
        return

    timestamp_default = "CURRENT_TIMESTAMP"
    timestamp_type = "DATETIME" if "sqlite" in db_url else "TIMESTAMP"
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE {MARKER_TABLE} (
                slug VARCHAR(511) PRIMARY KEY,
                seeded_at {timestamp_type} DEFAULT {timestamp_default}
            )
        """))
    print(f"✅ Created {MARKER_TABLE}")


def _marked_slugs(db) -> set:
    rows = db.execute(text(f"SELECT slug FROM {MARKER_TABLE}")).fetchall()
    return {row[0] for row in rows}


def _existing_slugs(db) -> set:
    rows = db.execute(text("SELECT owner, repo FROM actions_projects")).fetchall()
    return {f"{row[0]}/{row[1]}" for row in rows}


def run_migration(database_url: str | None = None):
    db_url = database_url or get_migration_database_url() or APP_DATABASE_URL
    engine = create_engine(db_url)

    table_names = inspect(engine).get_table_names()
    if "accounts" not in table_names or "actions_projects" not in table_names:
        print("⚠️ accounts or actions_projects table does not exist yet, skipping")
        return

    _create_marker_table(engine, db_url)

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_account = db.execute(
            text("SELECT user_id FROM accounts WHERE github_user = :github_user"),
            {"github_user": SEED_ACCOUNT_GITHUB_USER},
        ).fetchone()
        if not seed_account:
            print("⚠️ Seed account does not exist, nothing to back-fill")
            return

        marked = _marked_slugs(db)
        present = _existing_slugs(db)
        added = 0

        for action in SEED_ACTIONS:
            slug = f"{action['owner']}/{action['repo']}"
            if slug in marked:
                continue

            if slug not in ORIGINAL_SEED_SLUGS and slug not in present:
                db.add(build_seed_row(action, seed_account[0]))
                added += 1
                print(f"🔧 Adding new default action: {slug}")

            db.execute(
                text(f"INSERT INTO {MARKER_TABLE} (slug) VALUES (:slug)"),
                {"slug": slug},
            )

        db.commit()
        if added:
            print(f"✅ Added {added} new default Actions Project(s)")
        else:
            print("✅ Default Actions Projects catalog is up to date")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
