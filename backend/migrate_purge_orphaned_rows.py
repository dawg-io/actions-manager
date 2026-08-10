"""
Migration: Purge rows orphaned while SQLite foreign keys were disabled (issue #1811).

Nothing in the backend ever issued `PRAGMA foreign_keys = ON`, and SQLite
defaults it OFF, so every `ON DELETE CASCADE` in models.py was a silent no-op.
Deleting a project (or any other parent) left its children behind. Enforcement
is now switched on in database.py, but SQLite does not validate existing rows
when the pragma flips — the historical orphans stay until something touches
them, at which point an UPDATE of their foreign key column starts failing.

This purges them, once, so the database actually matches its own constraints.

SQLite only: PostgreSQL has always enforced these constraints, so orphans
cannot exist there.

Idempotent — a second run finds nothing to delete.
"""

import sqlite3

from sqlalchemy import create_engine, event, text

from migration_utils import get_migration_database_url

# Re-check until foreign_key_check comes back clean, rather than assuming one
# pass is enough. Today one always is: every FK in models.py is ON DELETE
# CASCADE, so deleting an orphan takes its descendants with it. That is a
# property of the current schema, not of the algorithm — a future non-cascading
# FK would silently leave a second layer behind. Bounded so a pathological
# schema can never spin forever.
MAX_PASSES = 20


def _group_violations_by_table(violations) -> dict:
    """Group (table, rowid, parent_table, fk_index) violation rows by table."""
    by_table: dict = {}
    for row in violations:
        table, rowid = row[0], row[1]
        if rowid is None:
            # WITHOUT ROWID table — nothing to delete by rowid. None exist in
            # this schema today, but skip rather than crash if one is added.
            continue
        by_table.setdefault(table, []).append(rowid)
    return by_table


def _delete_rows(conn, table, rowids) -> int:
    """Delete the given rowids from table in one statement. Returns rows deleted."""
    placeholders = ", ".join(f":id{i}" for i in range(len(rowids)))
    params = {f"id{i}": rowid for i, rowid in enumerate(rowids)}
    # Table name comes from PRAGMA output, not user input, so it cannot
    # be attacker-controlled; rowids are still bound parameters.
    deleted = conn.execute(
        text(f'DELETE FROM "{table}" WHERE rowid IN ({placeholders})'),  # noqa: S608
        params,
    ).rowcount
    return deleted or 0


def _purge_orphans(conn) -> dict:
    """Delete every row failing a foreign key check. Returns {table: rows_deleted}."""
    removed: dict = {}

    for pass_number in range(1, MAX_PASSES + 1):
        # (table, rowid, parent_table, fk_index) for each violating row.
        violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        if not violations:
            break

        # Group by table so each table takes one DELETE regardless of row count.
        by_table = _group_violations_by_table(violations)
        if not by_table:
            break

        for table, rowids in by_table.items():
            removed[table] = removed.get(table, 0) + _delete_rows(conn, table, rowids)

        print(f"   pass {pass_number}: removed {sum(len(v) for v in by_table.values())} "
              f"orphaned row(s) across {len(by_table)} table(s)")
    else:
        # Loop completed without breaking — still dirty after MAX_PASSES.
        remaining = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        if remaining:
            print(f"⚠️ Still {len(remaining)} foreign key violation(s) after "
                  f"{MAX_PASSES} passes; leaving them in place for manual review.")

    return removed


def run_migration():
    """Remove rows left orphaned while foreign key enforcement was off."""
    database_url = get_migration_database_url()
    if not database_url:
        print("⚠️ No database URL configured, skipping migration")
        return

    if "sqlite" not in database_url.lower():
        print("⏭️ Not a SQLite database — PostgreSQL enforces foreign keys natively, "
              "so no orphaned rows can exist. Skipping migration.")
        return

    print("🔄 Purging rows orphaned while SQLite foreign keys were disabled...")

    engine = create_engine(database_url)

    # Run the purge with enforcement ON so cascades remove descendants for free.
    # database.py registers this globally, but run_migrations.py executes each
    # migration as its own subprocess and this one imports only migration_utils.
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, sqlite3.Connection):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as conn:
        removed = _purge_orphans(conn)

    if removed:
        total = sum(removed.values())
        print(f"✅ Purged {total} orphaned row(s):")
        for table in sorted(removed):
            print(f"     {table}: {removed[table]}")
    else:
        print("✅ No orphaned rows found — database already matches its constraints.")


if __name__ == "__main__":
    run_migration()
