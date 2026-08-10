"""
Tests for the one-project-per-workflow migration (drift hardening PR 4).

The index is what makes cross-project workflow sharing impossible rather than
merely unreachable. Sharing is not reachable from any current code path, so on
a real upgrade the duplicate branch should never fire — but a migration that
crashes on an unexpected database blocks every later migration behind it, so
the skip path is tested as carefully as the happy one.
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migrate_add_project_workflow_unique as migration


SCHEMA = """
CREATE TABLE projects (project_id INTEGER PRIMARY KEY);
CREATE TABLE workflows (workflow_id INTEGER PRIMARY KEY);
CREATE TABLE project_workflows (
    project_id INTEGER NOT NULL,
    workflow_id INTEGER NOT NULL,
    PRIMARY KEY (project_id, workflow_id)
);
INSERT INTO projects (project_id) VALUES (1), (2);
INSERT INTO workflows (workflow_id) VALUES (10), (20);
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


def _associate(path, pairs):
    conn = sqlite3.connect(path)
    conn.executemany("INSERT INTO project_workflows VALUES (?, ?)", pairs)
    conn.commit()
    conn.close()


def _run(path):
    with patch.object(migration, "get_migration_database_url", return_value=f"sqlite:///{path}"):
        migration.run_migration()


def _index_exists(path):
    conn = sqlite3.connect(path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (migration.INDEX_NAME,),
    ).fetchall()
    conn.close()
    return bool(rows)


def _rows(path):
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT project_id, workflow_id FROM project_workflows ORDER BY 1, 2").fetchall()
    conn.close()
    return rows


class TestHappyPath:
    def test_creates_the_index(self, db_path):
        _associate(db_path, [(1, 10), (2, 20)])

        _run(db_path)

        assert _index_exists(db_path)

    def test_is_idempotent(self, db_path):
        _associate(db_path, [(1, 10)])

        _run(db_path)
        _run(db_path)

        assert _index_exists(db_path)

    def test_upgrade_keeps_same_named_workflows_in_different_projects(self, db_path):
        """The realistic upgrade: two projects each own a workflow called "ci".

        Those are separate workflow rows, so the index does not apply and
        nothing may be deleted.
        """
        _associate(db_path, [(1, 10), (2, 20)])

        _run(db_path)

        assert _index_exists(db_path)
        assert _rows(db_path) == [(1, 10), (2, 20)]

    def test_index_rejects_a_second_project_afterwards(self, db_path):
        _associate(db_path, [(1, 10)])
        _run(db_path)

        conn = sqlite3.connect(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO project_workflows VALUES (2, 10)")
        conn.close()


class TestExistingDuplicates:
    def test_reports_and_skips_instead_of_raising(self, db_path, capsys):
        _associate(db_path, [(1, 10), (2, 10)])

        _run(db_path)

        assert not _index_exists(db_path)
        out = capsys.readouterr().out
        assert "workflow_id=10" in out
        assert "[1, 2]" in out

    def test_deletes_nothing(self, db_path):
        """Choosing which project loses a workflow is not the migration's call."""
        _associate(db_path, [(1, 10), (2, 10)])

        _run(db_path)

        assert _rows(db_path) == [(1, 10), (2, 10)]

    def test_succeeds_once_the_duplicate_is_resolved(self, db_path):
        _associate(db_path, [(1, 10), (2, 10)])
        _run(db_path)

        conn = sqlite3.connect(db_path)
        conn.execute("DELETE FROM project_workflows WHERE project_id = 2")
        conn.commit()
        conn.close()

        _run(db_path)

        assert _index_exists(db_path)


class TestMissingTable:
    def test_skips_when_the_table_does_not_exist(self):
        """Migrations run in order against databases of every vintage."""
        path = tempfile.mktemp(suffix=".db")
        sqlite3.connect(path).close()
        try:
            _run(path)
            assert not _index_exists(path)
        finally:
            os.remove(path)


class _RaisingConn:
    """Wraps a real connection, raising on the CREATE UNIQUE INDEX statement only."""

    def __init__(self, real_conn, error_message):
        self._real = real_conn
        self._error_message = error_message

    def execute(self, stmt, *args, **kwargs):
        if "CREATE UNIQUE INDEX" in str(stmt):
            raise Exception(self._error_message)
        return self._real.execute(stmt, *args, **kwargs)


class _RaisingBeginCtx:
    def __init__(self, real_engine, error_message):
        self._real_engine = real_engine
        self._error_message = error_message

    def __enter__(self):
        self._ctx = self._real_engine.begin()
        real_conn = self._ctx.__enter__()
        return _RaisingConn(real_conn, self._error_message)

    def __exit__(self, exc_type, exc, tb):
        return self._ctx.__exit__(exc_type, exc, tb)


class _RaisingEngine:
    """Engine whose index-creation statement fails, simulating a Postgres
    role that does not own the table (issue: backend startup crash)."""

    def __init__(self, real_engine, error_message):
        self._real_engine = real_engine
        self._error_message = error_message

    def begin(self):
        return _RaisingBeginCtx(self._real_engine, self._error_message)


def _run_with_index_creation_error(path, error_message):
    real_engine = migration.create_engine(f"sqlite:///{path}")
    fake_engine = _RaisingEngine(real_engine, error_message)
    with patch.object(migration, "get_migration_database_url", return_value=f"sqlite:///{path}"), \
         patch.object(migration, "create_engine", return_value=fake_engine):
        migration.run_migration()


class TestPermissionDenied:
    """A migration role that doesn't own the table must not crash startup (issue:
    psycopg2.errors.InsufficientPrivilege: must be owner of table project_workflows)."""

    @pytest.mark.parametrize("error_message", [
        "must be owner of table project_workflows",
        "permission denied for table project_workflows",
        "InsufficientPrivilege: insufficient privilege",
    ])
    def test_reports_and_returns_instead_of_raising(self, db_path, capsys, error_message):
        _associate(db_path, [(1, 10)])

        _run_with_index_creation_error(db_path, error_message)  # must not raise

        out = capsys.readouterr().out
        assert "Could not create" in out
        assert "ALTER TABLE project_workflows OWNER TO" in out
        assert "POSTGRES_MIGRATION_USER" in out

    def test_does_not_swallow_unrelated_errors(self, db_path):
        _associate(db_path, [(1, 10)])

        with pytest.raises(Exception, match="disk I/O error"):
            _run_with_index_creation_error(db_path, "disk I/O error")
