"""
Regression tests for the base-schema bootstrap in run_migrations.

A fresh PostgreSQL database could not start: run_migrations ran the migration
list before anything imported models.py, so the ORM tables did not exist yet.
Migrations that create tables with foreign keys into them then failed --
"relation \"accounts\" does not exist" -- and every later migration depending on
what those failed ones create cascaded from there.

SQLite hid the bug because it accepts a foreign key to a table that does not
exist yet, resolving it lazily at DML time; PostgreSQL requires the referenced
table at CREATE TABLE. So the tables below assert the ordering and the effect
rather than relying on a specific engine's FK timing.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import run_migrations


# Tables declared in models.py that migrations create foreign keys into.
# These are exactly the ones the failing cloud deploy reported as missing.
FK_TARGET_TABLES = ["accounts", "workflows", "projects"]


def test_ensure_base_schema_creates_orm_tables(tmp_path, monkeypatch):
    """create_all must produce real tables, not a no-op on empty metadata."""
    db_file = tmp_path / "fresh.db"
    engine = create_engine(f"sqlite:///{db_file}")

    import database

    monkeypatch.setattr(database, "engine", engine)
    run_migrations.ensure_base_schema()

    created = set(inspect(engine).get_table_names())
    missing = [t for t in FK_TARGET_TABLES if t not in created]
    assert not missing, f"base tables not created: {missing}"


def test_ensure_base_schema_is_idempotent(tmp_path, monkeypatch):
    """It runs on every start, so a second call must not raise."""
    db_file = tmp_path / "twice.db"
    engine = create_engine(f"sqlite:///{db_file}")

    import database

    monkeypatch.setattr(database, "engine", engine)
    run_migrations.ensure_base_schema()
    run_migrations.ensure_base_schema()

    assert "accounts" in set(inspect(engine).get_table_names())


def test_base_schema_is_created_before_any_migration_runs(monkeypatch):
    """
    The ordering is the bug. Creating the tables after the loop would leave
    the failure exactly as it was.
    """
    calls = []

    monkeypatch.setattr(
        run_migrations, "ensure_base_schema", lambda: calls.append("base_schema")
    )
    monkeypatch.setattr(
        run_migrations,
        "run_migration_script",
        lambda path: calls.append(f"migration:{path.name}") or True,
    )
    monkeypatch.setattr(run_migrations, "get_database_type", lambda: "sqlite")

    run_migrations.main()

    assert calls, "main() ran neither the bootstrap nor any migration"
    assert calls[0] == "base_schema", f"bootstrap did not run first: {calls[:3]}"
    assert any(c.startswith("migration:") for c in calls), "no migrations ran"


def test_main_stops_when_base_schema_cannot_be_created(monkeypatch):
    """
    Without the base tables every migration fails anyway, so report that cause
    once rather than emitting a wall of derived FK errors.
    """
    def boom():
        raise RuntimeError("could not connect")

    ran = []
    monkeypatch.setattr(run_migrations, "ensure_base_schema", boom)
    monkeypatch.setattr(
        run_migrations,
        "run_migration_script",
        lambda path: ran.append(path.name) or True,
    )
    monkeypatch.setattr(run_migrations, "get_database_type", lambda: "postgresql")

    assert run_migrations.main() == 1
    assert ran == [], "migrations ran despite the base schema failing"
