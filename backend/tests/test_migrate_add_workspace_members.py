"""
Tests for the workspace_members seeding migration.

This is where the wrong account became admin. The migration backfills a
membership row for every account that lacks one and makes the lowest user_id
an admin. The reserved seed account is created by an earlier migration — before
any human has logged in — so it holds the lowest user_id and won that election.
It cannot log in, which left the workspace with no usable admin.
"""
import os
import sqlite3
import sys
import tempfile

import pytest
from sqlalchemy import create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migrate_add_workspace_members as migration
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


def _accounts(path, names):
    conn = sqlite3.connect(path)
    conn.executemany("INSERT INTO accounts (github_user) VALUES (?)", [(n,) for n in names])
    conn.commit()
    conn.close()


def _seed(path):
    """Run the migration's backfill against a real connection."""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        migration._seed_existing_users(conn)


def _roles(path):
    conn = sqlite3.connect(path)
    rows = conn.execute("""
        SELECT a.github_user, w.workspace_role
        FROM accounts a LEFT JOIN workspace_members w ON a.user_id = w.user_id
        ORDER BY a.user_id
    """).fetchall()
    conn.close()
    return dict(rows)


class TestSeedAccountIsSkipped:
    def test_admin_goes_to_the_first_human_not_the_seed(self, db_path):
        """The seed account sorts first by user_id but is not a candidate."""
        _accounts(db_path, [SEED_ACCOUNT_GITHUB_USER, "installer", "colleague"])

        _seed(db_path)

        assert _roles(db_path) == {
            SEED_ACCOUNT_GITHUB_USER: None,
            "installer": "admin",
            "colleague": "read_only",
        }

    def test_seed_account_gets_no_membership_row(self, db_path):
        _accounts(db_path, [SEED_ACCOUNT_GITHUB_USER, "installer"])

        _seed(db_path)

        conn = sqlite3.connect(db_path)
        count = conn.execute("""
            SELECT COUNT(*) FROM workspace_members w
            JOIN accounts a ON a.user_id = w.user_id
            WHERE a.github_user = ?
        """, (SEED_ACCOUNT_GITHUB_USER,)).fetchone()[0]
        conn.close()
        assert count == 0

    def test_seed_only_database_seeds_nobody(self, db_path):
        """Nobody has logged in yet — leave it to the first real login."""
        _accounts(db_path, [SEED_ACCOUNT_GITHUB_USER])

        _seed(db_path)

        assert _roles(db_path) == {SEED_ACCOUNT_GITHUB_USER: None}

    def test_rerun_does_not_belatedly_add_the_seed(self, db_path):
        """Every boot re-runs migrations; the seed must stay out on each one."""
        _accounts(db_path, [SEED_ACCOUNT_GITHUB_USER, "installer"])

        _seed(db_path)
        _seed(db_path)

        assert _roles(db_path)[SEED_ACCOUNT_GITHUB_USER] is None
        assert _roles(db_path)["installer"] == "admin"


class TestEnsureAdminExists:
    def test_a_seed_admin_does_not_satisfy_the_check(self, db_path):
        """The safety net must look for a *human* admin, or it papers over the bug."""
        _accounts(db_path, [SEED_ACCOUNT_GITHUB_USER, "installer"])
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO workspace_members (user_id, workspace_role) VALUES (1, 'admin')")
        conn.execute("INSERT INTO workspace_members (user_id, workspace_role) VALUES (2, 'read_only')")
        conn.commit()
        conn.close()

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            migration._ensure_admin_exists(conn)

        assert _roles(db_path)["installer"] == "admin"

    def test_existing_human_admin_is_left_alone(self, db_path):
        _accounts(db_path, ["alice", "bob"])
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO workspace_members (user_id, workspace_role) VALUES (1, 'read_only')")
        conn.execute("INSERT INTO workspace_members (user_id, workspace_role) VALUES (2, 'admin')")
        conn.commit()
        conn.close()

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            migration._ensure_admin_exists(conn)

        assert _roles(db_path) == {"alice": "read_only", "bob": "admin"}


class TestOrdinaryUpgrade:
    def test_workspace_without_a_seed_account_is_unchanged_in_behaviour(self, db_path):
        """Installs predating the seed account must still elect their first user."""
        _accounts(db_path, ["alice", "bob", "carol"])

        _seed(db_path)

        assert _roles(db_path) == {"alice": "admin", "bob": "read_only", "carol": "read_only"}
