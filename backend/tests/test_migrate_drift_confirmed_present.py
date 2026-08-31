"""
Tests for the drift delivery-confirmation migration (issue #1981).

Every row the old check wrote is ambiguous in the same way: it nulled
``github_sha`` when reporting a deletion, so a real deletion and one it invented
for a workflow that never landed are byte-identical on the row. The migration
has to separate them from outside the row — via the merged PRs that record which
workflow reached which (repo, branch) — and then take back the false ones
*itself*, because leaving them to the next drift check would emit a
drift.resolved event per row per subscriber for drift that never existed.

The evidence has to be per-(repo, branch). The workflow's own status is not:
it answers for every repo at once, so it both confirms repos that never received
the file and denies repos that did.
"""
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migrate_add_drift_confirmed_present as migration


SCHEMA = """
CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY,
    drift_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    drift_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE workflows (
    workflow_id INTEGER PRIMARY KEY,
    workflow_name VARCHAR(255),
    workflow_status VARCHAR(30)
);
CREATE TABLE repos (repo_id INTEGER PRIMARY KEY, repo_name VARCHAR(255));
CREATE TABLE project_pull_requests (
    pr_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
    target_branch VARCHAR(255) NOT NULL,
    workflow_names TEXT,
    merged_at TIMESTAMP
);
CREATE TABLE workflow_drift_states (
    state_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    workflow_id INTEGER NOT NULL,
    repo_id INTEGER NOT NULL,
    branch VARCHAR(255) NOT NULL DEFAULT '',
    has_drift BOOLEAN NOT NULL DEFAULT 0,
    content_hash VARCHAR(64),
    github_sha VARCHAR(255),
    deleted_in_github BOOLEAN NOT NULL DEFAULT 0,
    drift_cycle_count INTEGER NOT NULL DEFAULT 0,
    last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO projects (project_id, drift_status, drift_count) VALUES (1, 'drifted', 3);
-- A project whose last check never completed: it reports no count by design.
INSERT INTO projects (project_id, drift_status, drift_count) VALUES (2, 'check_failed', 0);

-- 'ci' merged and live; 'release' still under review, so it never landed
-- anywhere; 'deploy' landed once and was then pulled back into a new campaign.
INSERT INTO workflows VALUES (10, 'ci', 'synced_with_github');
INSERT INTO workflows VALUES (20, 'release', 'under_review');
INSERT INTO workflows VALUES (30, 'deploy', 'under_review');
INSERT INTO repos VALUES (100, 'acme/one'), (200, 'acme/two'), (300, 'acme/three');

-- The deliveries that actually happened, per (repo, target branch).
INSERT INTO project_pull_requests (project_id, repo_name, target_branch, workflow_names, merged_at)
VALUES (1, 'acme/two', 'main', 'ci, other', '2026-07-01 09:00:00');
INSERT INTO project_pull_requests (project_id, repo_name, target_branch, workflow_names, merged_at)
VALUES (1, 'acme/three', 'main', 'deploy', '2026-07-02 09:00:00');
-- Open, so it delivered nothing.
INSERT INTO project_pull_requests (project_id, repo_name, target_branch, workflow_names, merged_at)
VALUES (1, 'acme/one', 'main', 'release', NULL);

-- Present at the last check: demonstrably delivered.
INSERT INTO workflow_drift_states
    (project_id, workflow_id, repo_id, branch, has_drift, github_sha, deleted_in_github, last_checked_at)
VALUES (1, 10, 100, 'main', 1, 'sha-abc', 0, '2026-08-01 12:00:00');

-- A real deletion: flagged, SHA nulled by the reporting check, and a merged PR
-- that put 'ci' on acme/two@main.
INSERT INTO workflow_drift_states
    (project_id, workflow_id, repo_id, branch, has_drift, github_sha, deleted_in_github, last_checked_at)
VALUES (1, 10, 200, 'main', 1, NULL, 1, '2026-08-02 12:00:00');

-- The bug's output: same shape, but the workflow never landed anywhere.
INSERT INTO workflow_drift_states
    (project_id, workflow_id, repo_id, branch, has_drift, github_sha, deleted_in_github, last_checked_at)
VALUES (1, 20, 100, 'main', 1, NULL, 1, '2026-08-03 12:00:00');
INSERT INTO workflow_drift_states
    (project_id, workflow_id, repo_id, branch, has_drift, github_sha, deleted_in_github, last_checked_at)
VALUES (1, 20, 200, 'main', 1, NULL, 1, '2026-08-03 12:00:00');

-- Synced workflow, repo it was never delivered to: the same false positive the
-- workflow's status would have confirmed forever.
INSERT INTO workflow_drift_states
    (project_id, workflow_id, repo_id, branch, has_drift, github_sha, deleted_in_github, last_checked_at)
VALUES (1, 10, 300, 'main', 1, NULL, 1, '2026-08-03 12:00:00');

-- Delivered by a merged PR, then pulled back into a campaign, and deleted on
-- GitHub meanwhile: a real deletion the workflow's status would have discarded.
INSERT INTO workflow_drift_states
    (project_id, workflow_id, repo_id, branch, has_drift, github_sha, deleted_in_github, last_checked_at)
VALUES (1, 30, 300, 'main', 1, NULL, 1, '2026-08-03 12:00:00');

-- Stale drifted row under a project whose check never completed.
INSERT INTO workflow_drift_states
    (project_id, workflow_id, repo_id, branch, has_drift, github_sha, deleted_in_github, last_checked_at)
VALUES (2, 20, 300, 'develop', 1, 'sha-old', 0, '2026-08-01 12:00:00');
"""


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    try:
        yield path
    finally:
        os.unlink(path)


def _run(db_path):
    with patch.object(migration, "get_migration_database_url",
                      return_value=f"sqlite:///{db_path}"):
        migration.run_migration()


def _rows(db_path):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return {
            (r["workflow_id"], r["repo_id"]): r
            for r in conn.execute("SELECT * FROM workflow_drift_states")
        }
    finally:
        conn.close()


def test_adds_the_column(db_path):
    _run(db_path)

    conn = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(workflow_drift_states)")}
    finally:
        conn.close()
    assert "confirmed_present_at" in cols


def test_a_row_that_saw_a_sha_is_confirmed(db_path):
    _run(db_path)

    assert _rows(db_path)[(10, 100)]["confirmed_present_at"] is not None


def test_a_real_deletion_is_confirmed_and_kept(db_path):
    """Deleted + a merged PR that delivered it there: a real deletion, so it stays."""
    _run(db_path)

    row = _rows(db_path)[(10, 200)]
    assert row["confirmed_present_at"] is not None
    assert row["deleted_in_github"] == 1
    assert row["has_drift"] == 1


def test_false_deletions_are_taken_back_without_notifying(db_path):
    """Deleted + never delivered: the bug's output, cleared here rather than by a check.

    Clearing it through the drift path would emit a drift.resolved event per row
    per subscriber, announcing that a problem which never existed is fixed.
    """
    _run(db_path)

    rows = _rows(db_path)
    for key in ((20, 100), (20, 200)):
        assert rows[key]["confirmed_present_at"] is None
        assert rows[key]["deleted_in_github"] == 0
        assert rows[key]["has_drift"] == 0


def test_a_synced_workflow_does_not_confirm_a_repo_it_never_reached(db_path):
    """Status is per-workflow, so it cannot answer a per-(repo, branch) question.

    'ci' is synced_with_github because it merged into acme/two. Reading that as
    delivery history would confirm acme/three too, and since nothing ever clears
    confirmed_present_at that repo would report the deletion forever.
    """
    _run(db_path)

    row = _rows(db_path)[(10, 300)]
    assert row["confirmed_present_at"] is None
    assert row["deleted_in_github"] == 0
    assert row["has_drift"] == 0


def test_a_deletion_survives_the_workflow_leaving_synced_status(db_path):
    """'deploy' merged into acme/three, then a new campaign moved it under_review.

    The file really is gone from that branch. Judging by status would clear the
    row, and because the file no longer exists no later check could ever stamp
    the confirmation back — the deletion would vanish silently.
    """
    _run(db_path)

    row = _rows(db_path)[(30, 300)]
    assert row["confirmed_present_at"] is not None
    assert row["deleted_in_github"] == 1
    assert row["has_drift"] == 1


def test_cached_project_counters_follow_the_cleared_rows(db_path):
    """The project list renders from these, so they cannot be left stale."""
    _run(db_path)

    conn = sqlite3.connect(db_path)
    try:
        status, count = conn.execute(
            "SELECT drift_status, drift_count FROM projects WHERE project_id = 1"
        ).fetchone()
    finally:
        conn.close()
    # Three of the six rows were false and are gone; the three real ones remain.
    assert count == 3
    assert status == "drifted"


def test_a_project_whose_check_failed_keeps_its_counters(db_path):
    """drift_count and drift_status describe one state and must agree.

    check_failed deliberately reports no count, so recounting its stale rows
    would put a drift badge on a project that was never successfully checked.
    """
    _run(db_path)

    conn = sqlite3.connect(db_path)
    try:
        status, count = conn.execute(
            "SELECT drift_status, drift_count FROM projects WHERE project_id = 2"
        ).fetchone()
    finally:
        conn.close()
    assert status == "check_failed"
    assert count == 0


def test_running_twice_changes_nothing(db_path):
    """Re-running a migration is normal — it must not re-confirm cleared rows."""
    _run(db_path)
    first = {k: dict(v) for k, v in _rows(db_path).items()}

    _run(db_path)

    assert {k: dict(v) for k, v in _rows(db_path).items()} == first


def test_skips_cleanly_when_the_table_is_absent():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        sqlite3.connect(path).close()
        _run(path)  # must not raise
    finally:
        os.unlink(path)
