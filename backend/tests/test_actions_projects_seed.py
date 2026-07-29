"""
Tests for the default Actions Projects seed migration.

Covers:
- Fresh DB gets the system account + 7 seeded rows
- Running it twice is a no-op
- Deleting the seeded rows and re-running does NOT recreate them
  (the system account's existence is the idempotency marker, not row count)
"""

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("INSTALLATION_MODE", "cloud")

from database import Base  # noqa: E402
import models  # noqa: E402,F401 -- populates Base.metadata
import migrate_seed_default_actions_projects as seed_migration  # noqa: E402


def _fresh_sqlite_db(tmp_path):
    db_path = tmp_path / "seed_test.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return db_url, engine


class TestSeedDefaultActionsProjects:
    def test_seeds_system_account_and_seven_actions(self, tmp_path):
        db_url, engine = _fresh_sqlite_db(tmp_path)

        seed_migration.run_migration(database_url=db_url)

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            accounts = db.execute(
                text("SELECT github_user FROM accounts WHERE github_user = :u"),
                {"u": seed_migration.SEED_ACCOUNT_GITHUB_USER},
            ).fetchall()
            assert len(accounts) == 1

            projects = db.execute(text("SELECT name, owner, repo FROM actions_projects")).fetchall()
            assert len(projects) == 7
            slugs = {(row.owner, row.repo) for row in projects}
            assert slugs == {
                ("actions", "checkout"),
                ("actions", "setup-node"),
                ("actions", "setup-python"),
                ("actions", "setup-java"),
                ("actions", "cache"),
                ("actions", "upload-artifact"),
                ("actions", "download-artifact"),
            }
        finally:
            db.close()

    def test_running_twice_is_a_noop(self, tmp_path):
        db_url, engine = _fresh_sqlite_db(tmp_path)

        seed_migration.run_migration(database_url=db_url)
        seed_migration.run_migration(database_url=db_url)

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            count = db.execute(text("SELECT COUNT(*) FROM actions_projects")).scalar()
            assert count == 7
        finally:
            db.close()

    def test_deleted_rows_are_not_recreated_on_rerun(self, tmp_path):
        db_url, engine = _fresh_sqlite_db(tmp_path)

        seed_migration.run_migration(database_url=db_url)

        Session = sessionmaker(bind=engine)
        db = Session()
        try:
            db.execute(text("DELETE FROM actions_projects"))
            db.commit()
        finally:
            db.close()

        seed_migration.run_migration(database_url=db_url)

        db = Session()
        try:
            count = db.execute(text("SELECT COUNT(*) FROM actions_projects")).scalar()
            assert count == 0
        finally:
            db.close()
