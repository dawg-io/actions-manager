"""
Tests for the campaign last_known_status migration backfill (code review fix, part of #1789).

The column previously defaulted every pre-existing campaign to 'open'
regardless of its true state, which would make an already-completed legacy
campaign look like a fresh open -> terminal transition on the first read
after this migration ships — a backdated campaign.completed notification
once delivery is wired up. This backfills the real status from each
campaign's actual PR states instead.
"""

import sqlite3

import migrate_add_campaign_last_known_status as migration


def _seed_db(db_file):
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE project_pr_campaigns (campaign_id INTEGER PRIMARY KEY, project_id INTEGER)")
    conn.execute(
        "CREATE TABLE project_pull_requests ("
        "pr_id INTEGER PRIMARY KEY, campaign_id INTEGER, pr_state VARCHAR(20))"
    )

    # Campaign 1: already fully merged before this migration ships.
    conn.execute("INSERT INTO project_pr_campaigns (campaign_id, project_id) VALUES (1, 1)")
    conn.execute("INSERT INTO project_pull_requests (campaign_id, pr_state) VALUES (1, 'merged')")
    conn.execute("INSERT INTO project_pull_requests (campaign_id, pr_state) VALUES (1, 'merged')")

    # Campaign 2: still has an open PR.
    conn.execute("INSERT INTO project_pr_campaigns (campaign_id, project_id) VALUES (2, 1)")
    conn.execute("INSERT INTO project_pull_requests (campaign_id, pr_state) VALUES (2, 'open')")
    conn.execute("INSERT INTO project_pull_requests (campaign_id, pr_state) VALUES (2, 'merged')")

    # Campaign 3: partially completed (some merged, some closed without merge).
    conn.execute("INSERT INTO project_pr_campaigns (campaign_id, project_id) VALUES (3, 1)")
    conn.execute("INSERT INTO project_pull_requests (campaign_id, pr_state) VALUES (3, 'merged')")
    conn.execute("INSERT INTO project_pull_requests (campaign_id, pr_state) VALUES (3, 'closed')")

    # Campaign 4: cancelled (all closed, none merged).
    conn.execute("INSERT INTO project_pr_campaigns (campaign_id, project_id) VALUES (4, 1)")
    conn.execute("INSERT INTO project_pull_requests (campaign_id, pr_state) VALUES (4, 'closed')")

    conn.commit()
    conn.close()


def test_backfill_computes_real_status_not_default_open(tmp_path, monkeypatch):
    db_file = tmp_path / "actions_manager.db"
    _seed_db(db_file)

    monkeypatch.setattr(migration, "APP_DATABASE_URL", f"sqlite:///{db_file}")
    migration.run_sqlite_migration()

    conn = sqlite3.connect(str(db_file))
    try:
        statuses = dict(conn.execute("SELECT campaign_id, last_known_status FROM project_pr_campaigns"))
    finally:
        conn.close()

    assert statuses == {
        1: "completed",
        2: "open",
        3: "partially_completed",
        4: "cancelled",
    }


def test_backfill_is_idempotent(tmp_path, monkeypatch):
    db_file = tmp_path / "actions_manager.db"
    _seed_db(db_file)

    monkeypatch.setattr(migration, "APP_DATABASE_URL", f"sqlite:///{db_file}")
    migration.run_sqlite_migration()
    migration.run_sqlite_migration()  # must not fail or change the outcome

    conn = sqlite3.connect(str(db_file))
    try:
        status = conn.execute(
            "SELECT last_known_status FROM project_pr_campaigns WHERE campaign_id = 1"
        ).fetchone()[0]
    finally:
        conn.close()

    assert status == "completed"


def test_campaign_with_no_prs_keeps_default_open(tmp_path, monkeypatch):
    db_file = tmp_path / "actions_manager.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE project_pr_campaigns (campaign_id INTEGER PRIMARY KEY, project_id INTEGER)")
    conn.execute(
        "CREATE TABLE project_pull_requests ("
        "pr_id INTEGER PRIMARY KEY, campaign_id INTEGER, pr_state VARCHAR(20))"
    )
    conn.execute("INSERT INTO project_pr_campaigns (campaign_id, project_id) VALUES (5, 1)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(migration, "APP_DATABASE_URL", f"sqlite:///{db_file}")
    migration.run_sqlite_migration()

    conn = sqlite3.connect(str(db_file))
    try:
        status = conn.execute(
            "SELECT last_known_status FROM project_pr_campaigns WHERE campaign_id = 5"
        ).fetchone()[0]
    finally:
        conn.close()

    assert status == "open"


def test_missing_project_pull_requests_table_skips_backfill_without_crashing(tmp_path, monkeypatch):
    # project_pull_requests can legitimately not exist yet when this migration
    # runs (e.g. migrations run before the app's own table bootstrap on a
    # fresh install) - the column add must still succeed instead of raising.
    db_file = tmp_path / "actions_manager.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE project_pr_campaigns (campaign_id INTEGER PRIMARY KEY, project_id INTEGER)")
    conn.execute("INSERT INTO project_pr_campaigns (campaign_id, project_id) VALUES (6, 1)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(migration, "APP_DATABASE_URL", f"sqlite:///{db_file}")
    migration.run_sqlite_migration()

    conn = sqlite3.connect(str(db_file))
    try:
        status = conn.execute(
            "SELECT last_known_status FROM project_pr_campaigns WHERE campaign_id = 6"
        ).fetchone()[0]
    finally:
        conn.close()

    assert status == "open"
