"""
Tests for the drift-configuration migration.

Drift cadence moved out of the DRIFT_* env vars, so an upgrading install needs
both a drift_settings table and a per-project interval column. The migration
runs on every boot, so being idempotent matters as much as being correct: a
second run must not fail or clobber settings an admin has already saved.
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migrate_add_drift_configuration as migration


OLD_SCHEMA = """
CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY,
    project_name VARCHAR(255) NOT NULL,
    drift_status VARCHAR(20) NOT NULL DEFAULT 'unknown'
);
INSERT INTO projects (project_id, project_name) VALUES (1, 'legacy');
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


def _run(path):
    with patch.object(migration, "get_migration_database_url", return_value=f"sqlite:///{path}"):
        migration.run_migration()


def _columns(path, table):
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _tables(path):
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_it_creates_the_settings_table(db_path):
    _run(db_path)

    assert "drift_settings" in _tables(db_path)
    assert {"sweep_enabled", "recheck_interval_minutes", "batch_size",
            "poll_interval_seconds"} <= _columns(db_path, "drift_settings")


def test_it_adds_the_per_project_interval_column(db_path):
    _run(db_path)

    assert "drift_check_interval_minutes" in _columns(db_path, "projects")


def test_existing_projects_default_to_inheriting(db_path):
    """NULL, not 0 — an upgrade must not silently switch drift off."""
    _run(db_path)

    conn = sqlite3.connect(db_path)
    try:
        value = conn.execute(
            "SELECT drift_check_interval_minutes FROM projects WHERE project_id = 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert value is None


def test_running_twice_is_safe(db_path):
    _run(db_path)
    _run(db_path)

    assert "drift_check_interval_minutes" in _columns(db_path, "projects")


def test_a_second_run_keeps_saved_settings(db_path):
    """The migration runs on every boot; it must not reset an admin's config."""
    _run(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO drift_settings (sweep_enabled, recheck_interval_minutes, "
        "batch_size, poll_interval_seconds) VALUES (0, 1440, 3, 120)"
    )
    conn.commit()
    conn.close()

    _run(db_path)

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT sweep_enabled, recheck_interval_minutes FROM drift_settings"
        ).fetchall()
    finally:
        conn.close()
    assert row == [(0, 1440)]


def test_it_skips_the_column_when_projects_does_not_exist_yet(db_path):
    """A fresh database runs migrations before the ORM creates its tables."""
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE projects")
    conn.commit()
    conn.close()

    _run(db_path)

    assert "drift_settings" in _tables(db_path)
