"""
Tests for the orphan-purge migration (issue #1811).

While SQLite foreign keys were disabled, deleting a parent left its children
behind. Enabling the pragma does not retroactively validate existing rows, so
those historical orphans linger until an UPDATE of their foreign key column
starts failing. This migration removes them once.
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migrate_purge_orphaned_rows as migration


SCHEMA = """
CREATE TABLE parent (id INTEGER PRIMARY KEY);
CREATE TABLE child (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES parent(id) ON DELETE CASCADE
);
CREATE TABLE grandchild (
    id INTEGER PRIMARY KEY,
    child_id INTEGER NOT NULL REFERENCES child(id) ON DELETE CASCADE
);
"""


@pytest.fixture()
def db_path():
    path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


def _seed_orphans(path, *, levels=1):
    """Create rows, then delete the parent with enforcement OFF to orphan them."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("INSERT INTO parent (id) VALUES (1)")
    conn.execute("INSERT INTO child (id, parent_id) VALUES (1, 1)")
    if levels > 1:
        conn.execute("INSERT INTO grandchild (id, child_id) VALUES (1, 1)")
    conn.execute("DELETE FROM parent WHERE id = 1")
    conn.commit()
    conn.close()


def _violations(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()


def _run(path):
    with patch.object(migration, "get_migration_database_url", return_value=f"sqlite:///{path}"):
        migration.run_migration()


def _count(path, table):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


class TestPurge:
    def test_orphans_are_removed(self, db_path):
        _seed_orphans(db_path)
        assert _violations(db_path), "fixture should have produced an orphan"

        _run(db_path)

        assert _violations(db_path) == []
        assert _count(db_path, "child") == 0

    def test_multi_level_orphans_are_fully_removed(self, db_path):
        # A whole orphaned subtree must go, not just its top row. With every FK
        # cascading this is currently satisfied in one pass — deleting the
        # orphaned child takes the grandchild with it — so this pins the
        # outcome rather than the number of passes.
        _seed_orphans(db_path, levels=2)

        _run(db_path)

        assert _violations(db_path) == []
        assert _count(db_path, "child") == 0
        assert _count(db_path, "grandchild") == 0

    def test_valid_rows_are_left_alone(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO parent (id) VALUES (1)")
        conn.execute("INSERT INTO child (id, parent_id) VALUES (1, 1)")
        conn.commit()
        conn.close()

        _run(db_path)

        assert _count(db_path, "parent") == 1
        assert _count(db_path, "child") == 1

    def test_is_idempotent(self, db_path):
        _seed_orphans(db_path)
        _run(db_path)
        _run(db_path)

        assert _violations(db_path) == []

    def test_clean_database_is_a_no_op(self, db_path, capsys):
        _run(db_path)

        assert "No orphaned rows found" in capsys.readouterr().out


class TestDialectGuards:
    def test_postgresql_is_skipped(self, capsys):
        # PostgreSQL has always enforced these constraints, so orphans cannot
        # exist there and the migration must not pretend to do work.
        with patch.object(
            migration, "get_migration_database_url",
            return_value="postgresql://user:pw@localhost:5432/db",
        ):
            migration.run_migration()

        assert "Skipping migration" in capsys.readouterr().out

    def test_missing_database_url_is_skipped(self, capsys):
        with patch.object(migration, "get_migration_database_url", return_value=""):
            migration.run_migration()

        assert "No database URL configured" in capsys.readouterr().out
