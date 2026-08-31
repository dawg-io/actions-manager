"""
Migration: record whether a workflow's file was ever really seen on a branch.

Drift decided "this file was deleted from GitHub" from ``workflow_git_hash``
being non-zero. That hash is the blob SHA of whatever branch was last written —
including a PR branch — so a brand-new workflow whose campaign was still open
carried a real hash while having never landed on the target branch. Every repo
in the project then reported "Workflow was deleted from ..." for a file that had
only ever been proposed (issue #1981).

``confirmed_present_at`` is the durable answer to the question the old check was
guessing at: has a drift check actually found this workflow's file on this
(repo, branch)? It is set the first time one does and never cleared while the
pairing exists, so it outlives the check that reports a deletion — unlike
``github_sha``, which that check nulls.

Backfill, in order:

1. Rows whose last check saw a SHA were demonstrably present, so they are
   confirmed as of their last check time.
2. Rows already marked deleted are ambiguous: the old logic wrote that flag for
   both real deletions and the false ones this fixes, and nulled the SHA either
   way, so the row alone cannot tell them apart. A merged PR can: it is recorded
   per (repo, target branch) and names the workflows it carried, so a deleted
   row whose workflow a merged PR delivered to that exact pairing is a real
   deletion and is confirmed. The workflow's own *status* deliberately is not
   used — it is per-workflow, so it would answer for every repo at once.
3. Whatever deleted rows are left after that are the false positives. They are
   cleared here rather than left for the next drift check to take back, because
   that path emits a ``drift.resolved`` event per row per subscriber — a project
   with the bug would announce hundreds of resolutions for drift that never
   existed.

Clearing rows changes the cached ``projects.drift_count``/``drift_status`` the
project list renders from, so those are recomputed from the surviving rows —
only for projects whose status those two columns actually describe. A project
left ``check_failed`` reports no count by design, and rewriting its count from
rows an incomplete check never revisited would put a drift badge on a project
that was never successfully checked.

The column is additive and nullable, so existing rows stay valid, and a
re-run is a no-op: step 1 and 2 only fill nulls, and step 3 only matches rows
that step 1 and 2 left unconfirmed.
"""

from sqlalchemy import create_engine, text

from migration_utils import get_migration_database_url

TABLE = "workflow_drift_states"
COLUMN = "confirmed_present_at"
COLUMN_DDL = "TIMESTAMP"


def _table_exists(conn, database_url: str, table: str) -> bool:
    if "sqlite" in database_url:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": table},
        ).fetchone()
    else:
        row = conn.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
                """
            ),
            {"t": table},
        ).fetchone()
    return bool(row)


def _existing_columns(conn, database_url: str, table: str) -> set:
    if "sqlite" in database_url:
        return {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
    # Scoped to 'public' for the same reason _table_exists is: without it a
    # same-named table in another schema answers for this one, the ADD COLUMN
    # is skipped as already applied, and the UPDATEs below then fail against a
    # column that was never added.
    rows = conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            """
        ),
        {"t": table},
    ).fetchall()
    return {r[0] for r in rows}


def _backfill_seen_rows(conn) -> int:
    """A recorded GitHub SHA means the last check found the file there."""
    result = conn.execute(
        text(
            f"""
            UPDATE {TABLE}
            SET {COLUMN} = last_checked_at
            WHERE {COLUMN} IS NULL
              AND github_sha IS NOT NULL
            """
        )
    )
    return result.rowcount or 0


EVIDENCE_TABLES = ("workflows", "repos", "project_pull_requests")


def _backfill_real_deletions(conn, has_evidence: bool, true_sql: str) -> int:
    """Confirm deleted rows a merged PR really delivered to that (repo, branch).

    The workflow's own status cannot answer this. It is per-workflow while the
    question is per-(repo, branch): a workflow merged into one repo and newly
    added to another is ``synced_with_github`` for both, so reading the status
    confirms the repo that never received it. Nothing ever clears
    ``confirmed_present_at``, so that row would report "deleted" forever — the
    bug this migration exists to undo, reintroduced by the undo (issue #1981).

    A merged PR is recorded per (repo, target branch) and names the workflows it
    carried, so it is the one durable record of a delivery the drift row itself
    has forgotten. Matching it also rescues the deletions the status test lost:
    a workflow delivered to a repo and later moved back to ``under_review`` by a
    new campaign still has its merged PR, so a real deletion there survives
    instead of being cleared into silence.

    Names are matched inside the comma-separated list with spaces stripped,
    because that column is written with both ``", "`` and ``","`` separators.

    Residual gap: a delivery made by direct commit leaves no PR row, so a real
    deletion of a file that only ever arrived that way is still cleared below.
    Confirming those needs evidence the old rows never carried; going forward
    ``clear_workflow_drift`` stamps the confirmation at commit time instead.
    """
    if not has_evidence:
        return 0
    result = conn.execute(
        text(
            f"""
            UPDATE {TABLE}
            SET {COLUMN} = last_checked_at
            WHERE {COLUMN} IS NULL
              AND deleted_in_github = {true_sql}
              AND EXISTS (
                  SELECT 1
                  FROM project_pull_requests p
                  JOIN repos r ON r.repo_name = p.repo_name
                  JOIN workflows w ON w.workflow_id = {TABLE}.workflow_id
                  WHERE p.project_id = {TABLE}.project_id
                    AND r.repo_id = {TABLE}.repo_id
                    AND p.target_branch = {TABLE}.branch
                    AND p.merged_at IS NOT NULL
                    AND p.workflow_names IS NOT NULL
                    AND (',' || REPLACE(p.workflow_names, ' ', '') || ',')
                        LIKE ('%,' || REPLACE(w.workflow_name, ' ', '') || ',%')
              )
            """
        )
    )
    return result.rowcount or 0


def _clear_false_deletions(conn, true_sql: str, false_sql: str) -> int:
    """Take back the deletions the old check invented, without notifying.

    The complement of the step above: what no merged PR ever delivered to this
    (repo, branch) is what the old check invented. Rows left here are cleared
    rather than left for the next drift check to take back, because that path
    emits a ``drift.resolved`` event per row per subscriber.
    """
    result = conn.execute(
        text(
            f"""
            UPDATE {TABLE}
            SET deleted_in_github = {false_sql},
                has_drift = {false_sql}
            WHERE {COLUMN} IS NULL
              AND deleted_in_github = {true_sql}
            """
        )
    )
    return result.rowcount or 0


def _recompute_project_drift(conn, has_projects: bool, true_sql: str) -> None:
    """Realign the cached project counters with the rows that survived."""
    if not has_projects:
        return
    conn.execute(
        text(
            f"""
            UPDATE projects
            SET drift_count = (
                SELECT COUNT(*) FROM {TABLE} s
                WHERE s.project_id = projects.project_id
                  AND s.has_drift = {true_sql}
            )
            WHERE drift_status IN ('drifted', 'clean')
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE projects
            SET drift_status = CASE WHEN drift_count > 0 THEN 'drifted' ELSE 'clean' END
            WHERE drift_status IN ('drifted', 'clean')
            """
        )
    )


def run_migration():
    """Add confirmed_present_at and reconcile the rows the old check wrote."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    print("🔄 Adding drift delivery-confirmation column...")
    engine = create_engine(database_url)

    with engine.begin() as conn:
        if not _table_exists(conn, database_url, TABLE):
            print(f"⏭️ {TABLE} table does not exist yet, skipping migration")
            return

        if COLUMN not in _existing_columns(conn, database_url, TABLE):
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} {COLUMN_DDL}"))
            print(f"   ➕ {COLUMN}")

        # PostgreSQL will not compare a boolean column to an integer, and
        # SQLite stores these as 0/1, so the literal has to match the dialect.
        is_sqlite = "sqlite" in database_url
        true_sql, false_sql = ("1", "0") if is_sqlite else ("TRUE", "FALSE")

        seen = _backfill_seen_rows(conn)
        real = _backfill_real_deletions(
            conn,
            all(_table_exists(conn, database_url, t) for t in EVIDENCE_TABLES),
            true_sql,
        )
        cleared = _clear_false_deletions(conn, true_sql, false_sql)
        _recompute_project_drift(
            conn, _table_exists(conn, database_url, "projects"), true_sql
        )

    print(
        f"✅ Drift delivery confirmation present "
        f"({seen} confirmed from last check, {real} confirmed real deletions, "
        f"{cleared} false deletions cleared)"
    )


if __name__ == "__main__":
    run_migration()
