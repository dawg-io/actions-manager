"""
Regression tests for self-hosted startup reliability.

Validates that:
- backend/main.py can be imported when admin.py is absent (self-hosted scenario).
- The admin router is skipped cleanly when INSTALLATION_MODE=self-hosted.
- A cloud image with admin.py absent logs a warning but still starts up.

These tests guard against the failure mode described in the issue:
  ERROR: Error loading ASGI app. Could not import module "main".
caused by an unguarded import of admin.py that is intentionally absent from
the self-hosted Docker image.
"""

import importlib
import sys
import os
import types
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_main_without_admin(installation_mode: str):
    """
    Reload the main module with admin removed from sys.modules, simulating the
    self-hosted image where admin.py has been physically deleted.

    Returns the reloaded main module so callers can inspect app routes.
    """
    # Remove cached modules so the import runs from scratch
    for mod_name in list(sys.modules.keys()):
        if mod_name in ("main", "admin"):
            del sys.modules[mod_name]

    with patch.dict(os.environ, {"INSTALLATION_MODE": installation_mode}):
        # Ensure config picks up the patched env var
        if "config" in sys.modules:
            config_mod = sys.modules["config"]
            original_mode = getattr(config_mod, "INSTALLATION_MODE", None)
            config_mod.INSTALLATION_MODE = installation_mode
        else:
            original_mode = None

        # Block admin from being importable (simulates the file being deleted)
        original_admin = sys.modules.pop("admin", None)

        # Install a meta path finder that raises ModuleNotFoundError for "admin"
        class _BlockAdmin(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                if fullname == "admin":
                    raise ModuleNotFoundError(f"No module named '{fullname}'")
                return None

        blocker = _BlockAdmin()
        sys.meta_path.insert(0, blocker)

        try:
            import main as main_mod
            return main_mod
        finally:
            sys.meta_path.remove(blocker)
            # Restore admin if it was present before (cloud test environment)
            if original_admin is not None:
                sys.modules["admin"] = original_admin
            # Restore config mode
            if original_mode is not None and "config" in sys.modules:
                sys.modules["config"].INSTALLATION_MODE = original_mode


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSelfHostedStartup:
    """Validates that main.py starts cleanly without admin.py present."""

    def test_main_imports_without_admin_self_hosted(self):
        """
        Self-hosted scenario: INSTALLATION_MODE=self-hosted, admin.py absent.
        main.py must import successfully (no ImportError / ModuleNotFoundError).
        """
        main_mod = _reload_main_without_admin("self-hosted")
        assert hasattr(main_mod, "app"), "main.py must expose a FastAPI 'app' object"

    def test_admin_router_not_included_in_self_hosted(self):
        """
        When INSTALLATION_MODE=self-hosted the admin router must not be registered,
        so /admin/* endpoints are unreachable.
        """
        main_mod = _reload_main_without_admin("self-hosted")
        app = main_mod.app
        route_paths = [getattr(r, "path", "") for r in app.routes]
        admin_routes = [p for p in route_paths if p.startswith("/admin")]
        assert admin_routes == [], (
            f"Admin routes must not be present in self-hosted mode, found: {admin_routes}"
        )

    def test_main_imports_without_admin_cloud_mode_warns(self, caplog):
        """
        Misconfigured scenario: INSTALLATION_MODE=cloud but admin.py is absent.
        main.py must still import successfully and log a warning rather than crash.
        """
        import logging

        with caplog.at_level(logging.WARNING, logger="main"):
            main_mod = _reload_main_without_admin("cloud")

        assert hasattr(main_mod, "app"), (
            "main.py must expose a FastAPI 'app' object even when admin is absent in cloud mode"
        )
        # A warning should have been emitted
        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("admin" in msg.lower() for msg in warning_messages), (
            f"Expected a warning about the missing admin module, got: {warning_messages}"
        )

    def test_main_py_file_exists(self):
        """
        Regression guard: backend/main.py must be present in the source tree.
        This catches accidental deletion or mis-naming of the entry point.
        """
        backend_dir = os.path.join(os.path.dirname(__file__), "..")
        main_path = os.path.join(backend_dir, "main.py")
        assert os.path.isfile(main_path), (
            f"backend/main.py is missing at {os.path.abspath(main_path)}. "
            "Uvicorn requires this file as its entry point."
        )

    def test_main_import_exposes_app(self):
        """
        The 'main' module must expose a 'app' attribute that Uvicorn can bind to
        via 'uvicorn main:app'.
        """
        # Use the already-imported module from the test suite's sys.modules
        # (or import fresh if needed)
        if "main" not in sys.modules:
            import main  # noqa: F401
        main_mod = sys.modules["main"]
        assert hasattr(main_mod, "app"), (
            "main.py must define 'app' for 'uvicorn main:app' to work"
        )
