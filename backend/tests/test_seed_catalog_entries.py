"""
Tests for the default Actions Projects catalog back-fill migration.

Covers:
- An install seeded before an entry was added to SEED_ACTIONS gets that entry
- A fresh install (seed migration ran on this boot) gets no duplicate
- Re-running is a no-op
- Deleting a back-filled entry and re-running does NOT recreate it
- A default deleted before the marker table existed is NOT resurrected
- An entry the user imported themselves is marked, not duplicated
"""

import json
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("INSTALLATION_MODE", "cloud")

from database import Base  # noqa: E402
import models  # noqa: E402,F401 -- populates Base.metadata
from models import SEED_ACCOUNT_GITHUB_USER  # noqa: E402
import migrate_seed_default_actions_projects as seed_migration  # noqa: E402
import migrate_seed_catalog_entries as backfill  # noqa: E402

NEW_SLUG = "dawg-io/am-build-vars"


def _fresh_sqlite_db(tmp_path):
    db_path = tmp_path / "backfill_test.db"
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return db_url, engine


def _drop_marker_table(engine):
    """Undo the ORM's create_all so the migration exercises its own CREATE."""
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {backfill.MARKER_TABLE}"))


def _slugs(db):
    rows = db.execute(text("SELECT owner, repo FROM actions_projects")).fetchall()
    return {f"{r[0]}/{r[1]}" for r in rows}


def _markers(db):
    return {r[0] for r in db.execute(text(f"SELECT slug FROM {backfill.MARKER_TABLE}")).fetchall()}


def _seeded_install(tmp_path, only_original=True):
    """A database that ran the original seed batch, before NEW_SLUG existed."""
    db_url, engine = _fresh_sqlite_db(tmp_path)
    _drop_marker_table(engine)

    original = [a for a in seed_migration.SEED_ACTIONS
                if f"{a['owner']}/{a['repo']}" in backfill.ORIGINAL_SEED_SLUGS]
    saved = seed_migration.SEED_ACTIONS
    try:
        if only_original:
            seed_migration.SEED_ACTIONS = original
        seed_migration.run_migration(database_url=db_url)
    finally:
        seed_migration.SEED_ACTIONS = saved
    return db_url, engine


class TestBackfillCatalogEntries:
    def test_already_seeded_install_gets_the_new_entry(self, tmp_path):
        db_url, engine = _seeded_install(tmp_path)
        db = sessionmaker(bind=engine)()
        try:
            assert NEW_SLUG not in _slugs(db)
        finally:
            db.close()

        backfill.run_migration(database_url=db_url)

        db = sessionmaker(bind=engine)()
        try:
            assert NEW_SLUG in _slugs(db)
            assert _markers(db) == {f"{a['owner']}/{a['repo']}" for a in seed_migration.SEED_ACTIONS}

            row = db.execute(text(
                "SELECT name, ref, branding_icon, branding_color, inputs_json, user_id"
                " FROM actions_projects WHERE repo = 'am-build-vars'"
            )).fetchone()
            assert row.name == "AM Build Vars"
            assert row.ref == "v1.0.0"
            assert (row.branding_icon, row.branding_color) == ("shield", "purple")
            assert "load-shared" in {i["name"] for i in json.loads(row.inputs_json)}

            owner = db.execute(
                text("SELECT github_user FROM accounts WHERE user_id = :uid"),
                {"uid": row.user_id},
            ).fetchone()
            assert owner.github_user == SEED_ACCOUNT_GITHUB_USER
        finally:
            db.close()

    def test_fresh_install_is_not_duplicated(self, tmp_path):
        db_url, engine = _fresh_sqlite_db(tmp_path)
        _drop_marker_table(engine)

        seed_migration.run_migration(database_url=db_url)
        backfill.run_migration(database_url=db_url)

        db = sessionmaker(bind=engine)()
        try:
            count = db.execute(text("SELECT COUNT(*) FROM actions_projects")).scalar()
            assert count == len(seed_migration.SEED_ACTIONS)
            assert len(_markers(db)) == len(seed_migration.SEED_ACTIONS)
        finally:
            db.close()

    def test_running_twice_is_a_noop(self, tmp_path):
        db_url, engine = _seeded_install(tmp_path)

        backfill.run_migration(database_url=db_url)
        backfill.run_migration(database_url=db_url)

        db = sessionmaker(bind=engine)()
        try:
            count = db.execute(text("SELECT COUNT(*) FROM actions_projects")).scalar()
            assert count == len(seed_migration.SEED_ACTIONS)
        finally:
            db.close()

    def test_deleted_backfilled_entry_is_not_recreated(self, tmp_path):
        db_url, engine = _seeded_install(tmp_path)
        backfill.run_migration(database_url=db_url)

        db = sessionmaker(bind=engine)()
        try:
            db.execute(text("DELETE FROM actions_projects WHERE repo = 'am-build-vars'"))
            db.commit()
        finally:
            db.close()

        backfill.run_migration(database_url=db_url)

        db = sessionmaker(bind=engine)()
        try:
            assert NEW_SLUG not in _slugs(db)
        finally:
            db.close()

    def test_original_default_deleted_before_the_marker_table_is_not_resurrected(self, tmp_path):
        db_url, engine = _seeded_install(tmp_path)

        db = sessionmaker(bind=engine)()
        try:
            db.execute(text("DELETE FROM actions_projects WHERE repo = 'cache'"))
            db.commit()
        finally:
            db.close()

        backfill.run_migration(database_url=db_url)

        db = sessionmaker(bind=engine)()
        try:
            slugs = _slugs(db)
            assert "actions/cache" not in slugs
            assert NEW_SLUG in slugs
        finally:
            db.close()

    def test_self_imported_entry_is_marked_not_duplicated(self, tmp_path):
        db_url, engine = _seeded_install(tmp_path)

        db = sessionmaker(bind=engine)()
        try:
            seed_user = db.execute(
                text("SELECT user_id FROM accounts WHERE github_user = :u"),
                {"u": SEED_ACCOUNT_GITHUB_USER},
            ).fetchone()
            new_action = next(a for a in seed_migration.SEED_ACTIONS
                              if f"{a['owner']}/{a['repo']}" == NEW_SLUG)
            row = seed_migration.build_seed_row(new_action, seed_user[0])
            row.name = "My own import"
            db.add(row)
            db.commit()
        finally:
            db.close()

        backfill.run_migration(database_url=db_url)

        db = sessionmaker(bind=engine)()
        try:
            names = [r[0] for r in db.execute(text(
                "SELECT name FROM actions_projects WHERE repo = 'am-build-vars'"
            )).fetchall()]
            assert names == ["My own import"]
            assert NEW_SLUG in _markers(db)
        finally:
            db.close()

    def test_skips_when_seed_account_is_absent(self, tmp_path):
        db_url, engine = _fresh_sqlite_db(tmp_path)
        _drop_marker_table(engine)

        backfill.run_migration(database_url=db_url)

        db = sessionmaker(bind=engine)()
        try:
            assert db.execute(text("SELECT COUNT(*) FROM actions_projects")).scalar() == 0
            assert _markers(db) == set()
        finally:
            db.close()
