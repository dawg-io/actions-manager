"""
Tests for the seed-account admin repair migration.

The seed account is created by a migration, so on a fresh self-hosted install
it exists before anyone logs in and holds the lowest user_id. The membership
seed treated that as "the installer", handing workspace admin to an account
that cannot log in and leaving every human read_only — with role changes
requiring admin, nobody could fix it from the UI.
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migrate_revoke_seed_workspace_membership as migration
from models import SEED_ACCOUNT_GITHUB_USER


SCHEMA = """
CREATE TABLE accounts (
    user_id INTEGER PRIMARY KEY,
    github_user VARCHAR(255) NOT NULL UNIQUE
);
CREATE TABLE workspace_members (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    workspace_role VARCHAR(20) NOT NULL DEFAULT 'read_only'
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


def _seed_workspace(path, members):
    """members: [(github_user, role_or_None)] in user_id order."""
    conn = sqlite3.connect(path)
    for github_user, role in members:
        cur = conn.execute("INSERT INTO accounts (github_user) VALUES (?)", (github_user,))
        if role is not None:
            conn.execute(
                "INSERT INTO workspace_members (user_id, workspace_role) VALUES (?, ?)",
                (cur.lastrowid, role),
            )
    conn.commit()
    conn.close()


def _run(path):
    with patch.object(migration, "get_migration_database_url", return_value=f"sqlite:///{path}"):
        migration.run_migration()


def _roles(path):
    conn = sqlite3.connect(path)
    rows = conn.execute("""
        SELECT a.github_user, w.workspace_role
        FROM accounts a LEFT JOIN workspace_members w ON a.user_id = w.user_id
        ORDER BY a.user_id
    """).fetchall()
    conn.close()
    return dict(rows)


class TestRepairsTheBrokenInstall:
    def test_seed_loses_admin_and_the_installer_gets_it(self, db_path):
        """The exact reported state: seed is admin, both humans are read_only."""
        _seed_workspace(db_path, [
            (SEED_ACCOUNT_GITHUB_USER, "admin"),
            ("installer", "read_only"),
            ("colleague", "read_only"),
        ])

        _run(db_path)

        assert _roles(db_path) == {
            SEED_ACCOUNT_GITHUB_USER: None,
            "installer": "admin",
            "colleague": "read_only",
        }

    def test_colleague_is_not_promoted(self, db_path):
        """Only the earliest real member gets admin, not everyone."""
        _seed_workspace(db_path, [
            (SEED_ACCOUNT_GITHUB_USER, "admin"),
            ("installer", "read_only"),
            ("colleague", "read_only"),
        ])

        _run(db_path)

        assert _roles(db_path)["colleague"] == "read_only"

    def test_is_idempotent(self, db_path):
        _seed_workspace(db_path, [
            (SEED_ACCOUNT_GITHUB_USER, "admin"),
            ("installer", "read_only"),
        ])

        _run(db_path)
        _run(db_path)

        assert _roles(db_path)["installer"] == "admin"


class TestLeavesHealthyWorkspacesAlone:
    def test_existing_human_admin_is_kept(self, db_path):
        """A workspace that already elected an admin must not be reshuffled."""
        _seed_workspace(db_path, [
            (SEED_ACCOUNT_GITHUB_USER, "admin"),
            ("alice", "read_only"),
            ("bob", "admin"),
        ])

        _run(db_path)

        roles = _roles(db_path)
        assert roles["bob"] == "admin"
        assert roles["alice"] == "read_only"

    def test_no_seed_membership_is_a_no_op(self, db_path):
        _seed_workspace(db_path, [
            (SEED_ACCOUNT_GITHUB_USER, None),
            ("alice", "admin"),
            ("bob", "member"),
        ])

        _run(db_path)

        assert _roles(db_path) == {
            SEED_ACCOUNT_GITHUB_USER: None,
            "alice": "admin",
            "bob": "member",
        }

    def test_nobody_has_logged_in_yet(self, db_path):
        """Seed-only workspace: leave it empty so the first real login is admin."""
        _seed_workspace(db_path, [(SEED_ACCOUNT_GITHUB_USER, "admin")])

        _run(db_path)

        assert _roles(db_path) == {SEED_ACCOUNT_GITHUB_USER: None}


class TestMissingTables:
    def test_skips_when_tables_do_not_exist(self):
        path = tempfile.mktemp(suffix=".db")
        sqlite3.connect(path).close()
        try:
            _run(path)  # must not raise
        finally:
            os.remove(path)
