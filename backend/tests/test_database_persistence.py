"""
Regression tests for self-hosted database persistence.

Validates that:
- INSTALLATION_MODE=self-hosted resolves the SQLite path to /app/data/actions_manager.db
- Development / test environments fall back to ./test.db (relative to CWD)
- An explicit DATABASE_URL env var is always honoured regardless of INSTALLATION_MODE
- PostgreSQL env vars produce a PostgreSQL connection URL
- The SELF_HOSTED_DATA_DIR constant is /app/data

These tests guard against the bug described in the issue where the volume was
mounted to /app/data but the database was created at /app/backend/test.db,
causing data loss on container image updates.
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _restore_database_module():
    """
    _reload_database_module() below replaces sys.modules["database"] with a
    reloaded module object, which orphans the get_db reference that
    already-imported modules (project_deletion.py, admin.py, auth.py) hold —
    those modules keep pointing at the pre-reload get_db, so FastAPI's
    dependency_overrides can no longer intercept their routes' database
    dependency once this file has run. Restore the original module object
    afterward so other test files' `from database import get_db` still
    resolves to the same object those routes were wired with.
    """
    original = sys.modules.get("database")
    yield
    if original is not None:
        sys.modules["database"] = original
    else:
        sys.modules.pop("database", None)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _reload_database_module(tmp_data_dir: Path | None = None, **env_overrides):
    """
    Reload the database module with a controlled environment.

    Removes the cached module so that module-level code (which computes
    DATABASE_URL at import time) re-runs with the patched env.

    Patches ``create_engine`` to return a MagicMock so that ``Base.metadata.
    create_all`` never tries to open or create an actual SQLite file.  This
    lets the test run on machines where /app/data does not exist.

    ``tmp_data_dir`` is accepted for API compatibility but is not used;
    all path assertions operate against the DATABASE_URL resolved from the
    patched environment rather than a rewritten URL.
    """
    for mod_name in list(sys.modules.keys()):
        if mod_name == "database":
            del sys.modules[mod_name]

    # Scrub the PostgreSQL env vars that the test environment might inherit
    clean_env = {
        k: v for k, v in os.environ.items()
        if k not in {
            "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
            "POSTGRES_HOST", "POSTGRES_PORT", "DATABASE_URL",
            "INSTALLATION_MODE",
        }
    }
    clean_env.update(env_overrides)

    mock_engine = MagicMock()

    with patch.dict(os.environ, clean_env, clear=True), \
         patch("sqlalchemy.create_engine", return_value=mock_engine), \
         patch("sqlalchemy.orm.sessionmaker", return_value=MagicMock()):
        import database as db_mod
        importlib.reload(db_mod)

    # Ensure create_all on the (possibly real) Base metadata is also a no-op
    db_mod.Base.metadata.create_all = MagicMock()
    db_mod.engine = mock_engine

    return db_mod


# ---------------------------------------------------------------------------
# Tests: SQLite path resolution
# ---------------------------------------------------------------------------

class TestSelfHostedDatabasePath:
    """DATABASE_URL should point at /app/data/actions_manager.db in self-hosted mode."""

    def test_self_hosted_uses_app_data_path(self):
        """INSTALLATION_MODE=self-hosted → sqlite:////app/data/actions_manager.db"""
        db = _reload_database_module(INSTALLATION_MODE="self-hosted")
        assert "sqlite" in db.DATABASE_URL.lower()
        assert "/app/data/actions_manager.db" in db.DATABASE_URL

    def test_development_uses_relative_test_db(self):
        """No INSTALLATION_MODE (or non-self-hosted) → sqlite:///./test.db"""
        db = _reload_database_module(INSTALLATION_MODE="development")
        assert db.DATABASE_URL == "sqlite:///./test.db"

    def test_no_installation_mode_uses_relative_test_db(self):
        """INSTALLATION_MODE unset → sqlite:///./test.db"""
        db = _reload_database_module()
        assert db.DATABASE_URL == "sqlite:///./test.db"

    def test_self_hosted_data_dir_constant(self):
        """SELF_HOSTED_DATA_DIR must always be /app/data."""
        db = _reload_database_module(INSTALLATION_MODE="development")
        assert str(db.SELF_HOSTED_DATA_DIR) == "/app/data"

    def test_self_hosted_url_does_not_use_test_db(self):
        """self-hosted mode must not produce the development ./test.db path."""
        db = _reload_database_module(INSTALLATION_MODE="self-hosted")
        assert db.DATABASE_URL != "sqlite:///./test.db"


# ---------------------------------------------------------------------------
# Tests: explicit DATABASE_URL always wins
# ---------------------------------------------------------------------------

class TestExplicitDatabaseURL:
    """An explicit DATABASE_URL env var overrides all auto-resolution logic."""

    def test_explicit_sqlite_url_overrides_self_hosted(self):
        """Explicit DATABASE_URL wins even when INSTALLATION_MODE=self-hosted."""
        explicit = "sqlite:////some/custom/path.db"
        db = _reload_database_module(
            INSTALLATION_MODE="self-hosted",
            DATABASE_URL=explicit,
        )
        assert db.DATABASE_URL == explicit

    def test_explicit_postgres_url_overrides_self_hosted(self):
        """Explicit PostgreSQL DATABASE_URL wins over self-hosted SQLite default."""
        explicit = "******host:5432/mydb"
        db = _reload_database_module(
            INSTALLATION_MODE="self-hosted",
            DATABASE_URL=explicit,
        )
        assert db.DATABASE_URL == explicit

    def test_explicit_legacy_test_db_url(self):
        """Allows pinning back to the legacy path for backwards compatibility."""
        legacy = "sqlite:////app/backend/test.db"
        db = _reload_database_module(
            INSTALLATION_MODE="self-hosted",
            DATABASE_URL=legacy,
        )
        assert db.DATABASE_URL == legacy


# ---------------------------------------------------------------------------
# Tests: PostgreSQL env vars
# ---------------------------------------------------------------------------

class TestPostgresEnvVars:
    """Full PostgreSQL config via env vars should build a postgres:// URL."""

    def test_postgres_env_vars_produce_postgres_url(self):
        db = _reload_database_module(
            INSTALLATION_MODE="self-hosted",
            POSTGRES_USER="admin",
            POSTGRES_PASSWORD="secret",
            POSTGRES_DB="actionsdb",
            POSTGRES_HOST="db.example.com",
            POSTGRES_PORT="5432",
        )
        assert db.DATABASE_URL.startswith("postgresql://")
        # Verify the host appears immediately after the '@' separator so we
        # confirm an exact positional match, not just a substring anywhere.
        assert db.DATABASE_URL.split("@", 1)[1] == "db.example.com:5432/actionsdb"

    def test_partial_postgres_env_vars_falls_back_to_sqlite(self):
        """Missing any one of the five required PG vars → SQLite fallback."""
        db = _reload_database_module(
            INSTALLATION_MODE="self-hosted",
            POSTGRES_USER="admin",
            POSTGRES_PASSWORD="secret",
            # POSTGRES_DB deliberately omitted
            POSTGRES_HOST="db.example.com",
            POSTGRES_PORT="5432",
        )
        assert "sqlite" in db.DATABASE_URL.lower()
