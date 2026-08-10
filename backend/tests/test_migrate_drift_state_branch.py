"""
Tests for the drift-state branch migration (drift hardening PR 5).

Drift is checked per branch now, so the state key gains a branch. The old
`UNIQUE (workflow_id, repo_id)` is baked into CREATE TABLE, which SQLite
cannot drop — hence a table rebuild. If that rebuild silently kept the old
constraint, a project delivering to two branches could only ever record drift
for one of them.
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migrate_add_drift_state_branch as migration


OLD_SCHEMA = """
CREATE TABLE projects (project_id INTEGER PRIMARY KEY);
CREATE TABLE workflows (workflow_id INTEGER PRIMARY KEY);
CREATE TABLE repos (repo_id INTEGER PRIMARY KEY);
CREATE TABLE workflow_drift_states (
    state_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects (project_id) ON DELETE CASCADE,
    workflow_id INTEGER NOT NULL REFERENCES workflows (workflow_id) ON DELETE CASCADE,
    repo_id INTEGER NOT NULL REFERENCES repos (repo_id) ON DELETE CASCADE,
    has_drift BOOLEAN NOT NULL DEFAULT 0,
    content_hash VARCHAR(64),
    drift_cycle_count INTEGER NOT NULL DEFAULT 0,
    last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (workflow_id, repo_id)
);
INSERT INTO projects VALUES (1);
INSERT INTO workflows VALUES (10);
INSERT INTO repos VALUES (100);
"""


@pytest.fixture()
def db_path():
    path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.commit()
    conn.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


def _add_state(path, branch=None, has_drift=1):
    conn = sqlite3.connect(path)
    if branch is None:
        conn.execute(
            "INSERT INTO workflow_drift_states (project_id, workflow_id, repo_id, has_drift) "
            "VALUES (1, 10, 100, ?)", (has_drift,))
    else:
        conn.execute(
            "INSERT INTO workflow_drift_states (project_id, workflow_id, repo_id, branch, has_drift) "
            "VALUES (1, 10, 100, ?, ?)", (branch, has_drift))
    conn.commit()
    conn.close()


def _run(path):
    with patch.object(migration, "get_migration_database_url", return_value=f"sqlite:///{path}"):
        migration.run_migration()


def _columns(path):
    conn = sqlite3.connect(path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(workflow_drift_states)")]
    conn.close()
    return cols


def _count(path):
    conn = sqlite3.connect(path)
    n = conn.execute("SELECT COUNT(*) FROM workflow_drift_states").fetchone()[0]
    conn.close()
    return n


class TestRebuild:
    def test_adds_the_branch_column(self, db_path):
        _run(db_path)

        assert "branch" in _columns(db_path)

    def test_two_branches_of_one_workflow_and_repo_can_coexist(self, db_path):
        """The whole point: the old UNIQUE(workflow_id, repo_id) must be gone."""
        _run(db_path)

        _add_state(db_path, "release/2.1")
        _add_state(db_path, "release/2.2")

        assert _count(db_path) == 2

    def test_the_same_branch_twice_is_still_rejected(self, db_path):
        """Dropping the old key must not drop uniqueness altogether."""
        _run(db_path)
        _add_state(db_path, "release/2.1")

        with pytest.raises(sqlite3.IntegrityError):
            _add_state(db_path, "release/2.1")

    def test_is_idempotent(self, db_path):
        _run(db_path)
        _add_state(db_path, "release/2.1")

        _run(db_path)

        assert "branch" in _columns(db_path)
        # A second run must not wipe state written since the first.
        assert _count(db_path) == 1

    def test_project_index_survives_the_rebuild(self, db_path):
        _run(db_path)

        conn = sqlite3.connect(db_path)
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='workflow_drift_states'")]
        conn.close()
        assert "ix_workflow_drift_states_project_id" in names

    def test_no_leftover_scratch_table(self, db_path):
        _run(db_path)

        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        conn.close()
        assert "workflow_drift_states__new" not in tables


class TestLegacyRows:
    def test_cached_rows_are_cleared(self, db_path):
        """They cannot be backfilled — the branch they referred to needs a
        GitHub call — and keeping them would leave has_drift=1 rows that no
        future check ever matches, permanently inflating the drift count."""
        _add_state(db_path)

        _run(db_path)

        assert _count(db_path) == 0


class TestMissingTable:
    def test_skips_when_the_table_does_not_exist(self):
        path = tempfile.mktemp(suffix=".db")
        sqlite3.connect(path).close()
        try:
            _run(path)  # must not raise
        finally:
            os.remove(path)
