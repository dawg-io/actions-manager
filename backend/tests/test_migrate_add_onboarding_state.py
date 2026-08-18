"""
Tests for the onboarding state migration.

The migration runs on every boot, so being idempotent matters as much as being
correct. It must also leave existing accounts NULL — a default of "completed"
would silently deny the welcome screen to every user of an upgrading install,
and a default of "not completed" written as a value would be indistinguishable
from a genuine new account only by luck.
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migrate_add_onboarding_state as migration


OLD_SCHEMA = """
CREATE TABLE accounts (
    user_id INTEGER PRIMARY KEY,
    github_user VARCHAR(255) NOT NULL,
    github_email VARCHAR(255) NOT NULL,
    account_type VARCHAR(50) NOT NULL
);
INSERT INTO accounts (user_id, github_user, github_email, account_type)
VALUES (1, 'legacy', 'legacy@example.com', 'free');
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


def _columns(path):
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    finally:
        conn.close()


def test_adds_both_columns(db_path):
    _run(db_path)

    assert {"onboarding_completed_at", "onboarding_step"} <= _columns(db_path)


def test_existing_accounts_are_left_null(db_path):
    _run(db_path)

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT onboarding_completed_at, onboarding_step FROM accounts WHERE user_id = 1"
        ).fetchone()
    finally:
        conn.close()

    assert row == (None, None)


def test_is_idempotent(db_path):
    _run(db_path)
    _run(db_path)  # must not raise on the second boot

    assert {"onboarding_completed_at", "onboarding_step"} <= _columns(db_path)


def test_skips_when_accounts_table_is_missing():
    path = tempfile.mktemp(suffix=".db")
    sqlite3.connect(path).close()
    try:
        _run(path)  # fresh install: models.py creates the table instead
    finally:
        if os.path.exists(path):
            os.remove(path)
