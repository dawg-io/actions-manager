"""
Regression tests for the shared migration database URL resolution.

Covers the self-hosted database path bug: migration scripts must target
/app/data/actions_manager.db when INSTALLATION_MODE=self-hosted, and must
never silently fall back to creating a stray sqlite:///./test.db in the
backend source directory.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import migration_utils  # noqa: E402

_ENV_VARS_TO_CLEAR = (
    "DATABASE_URL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "INSTALLATION_MODE",
)


def _clear_env(monkeypatch):
    for var in _ENV_VARS_TO_CLEAR:
        monkeypatch.delenv(var, raising=False)


class TestGetDatabaseUrlSelfHosted:
    def test_self_hosted_mode_targets_data_volume(self, monkeypatch, tmp_path):
        """INSTALLATION_MODE=self-hosted with no other config must resolve to
        the persistent /app/data volume, not the development ./test.db path."""
        _clear_env(monkeypatch)
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.chdir(tmp_path)

        db_url = migration_utils.get_database_url()

        assert db_url == "sqlite:////app/data/actions_manager.db"
        assert not (tmp_path / "test.db").exists()

    def test_explicit_database_url_wins_over_self_hosted(self, monkeypatch):
        _clear_env(monkeypatch)
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/explicit-example.db")

        assert migration_utils.get_database_url() == "sqlite:////tmp/explicit-example.db"

    def test_postgres_env_vars_win_over_self_hosted(self, monkeypatch):
        _clear_env(monkeypatch)
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")
        monkeypatch.setenv("POSTGRES_USER", "exampleuser")
        monkeypatch.setenv("POSTGRES_PASSWORD", "examplepass")
        monkeypatch.setenv("POSTGRES_DB", "exampledb")
        monkeypatch.setenv("POSTGRES_HOST", "examplehost")
        monkeypatch.setenv("POSTGRES_PORT", "5432")

        expected = "postgresql://" + "exampleuser" + ":" + "examplepass" + "@examplehost:5432/exampledb"
        assert migration_utils.get_database_url() == expected

    def test_no_installation_mode_returns_empty(self, monkeypatch):
        """Non-self-hosted, non-postgres environments must not silently
        resolve a database path here; callers opt into a dev/test fallback
        explicitly (e.g. sqlite:///./test.db)."""
        _clear_env(monkeypatch)

        assert migration_utils.get_database_url() == ""

    def test_get_migration_database_url_uses_self_hosted_path(self, monkeypatch):
        _clear_env(monkeypatch)
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")

        assert (
            migration_utils.get_migration_database_url()
            == "sqlite:////app/data/actions_manager.db"
        )

    def test_get_database_type_reports_sqlite_for_self_hosted(self, monkeypatch):
        _clear_env(monkeypatch)
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")

        assert migration_utils.get_database_type() == "sqlite"

    def test_self_hosted_creates_data_dir_not_backend_test_db(self, monkeypatch, tmp_path):
        """Verify the resolved path lives under the data directory and that
        running migrations from a simulated backend/ working directory never
        creates a stray ./test.db alongside the migration scripts."""
        _clear_env(monkeypatch)
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")

        fake_data_dir = tmp_path / "data"
        monkeypatch.setattr(migration_utils, "_SELF_HOSTED_DATA_DIR", fake_data_dir)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        monkeypatch.chdir(backend_dir)

        db_url = migration_utils.get_database_url()

        assert db_url == f"sqlite:///{fake_data_dir / 'actions_manager.db'}"
        assert fake_data_dir.exists()
        assert not (backend_dir / "test.db").exists()


class TestValidationPreflightMigrationSelfHosted:
    def test_run_migration_self_hosted_does_not_create_backend_test_db(self, monkeypatch, tmp_path):
        """Regression test for the reported bug: running the validation
        preflight migration (which previously fell back to
        sqlite:///./test.db) must target the self-hosted data volume and
        must not create /app/backend/test.db (simulated here via cwd)."""
        _clear_env(monkeypatch)
        monkeypatch.setenv("INSTALLATION_MODE", "self-hosted")

        fake_data_dir = tmp_path / "data"
        monkeypatch.setattr(migration_utils, "_SELF_HOSTED_DATA_DIR", fake_data_dir)

        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        monkeypatch.chdir(backend_dir)

        import migrate_add_validation_preflight as vp_module

        # The module binds get_migration_database_url at import time, but it
        # is the same function object whose globals still point at the
        # (monkeypatched) migration_utils module, so this exercises the real
        # resolution path.
        vp_module.run_migration()

        assert (fake_data_dir / "actions_manager.db").exists()
        assert not (backend_dir / "test.db").exists()
