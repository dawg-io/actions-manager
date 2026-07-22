"""
Tests for the _check_cloud_prelaunch_flag guard in scripts/validate_release.py.

Ensures release validation fails when _CLOUD_PRELAUNCH_RELAXED = True is
present in backend/mode_validation.py, preventing cloud builds from shipping
with weakened billing/security controls (issue #1324).
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the release validation script.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_release  # noqa: E402


class TestCloudPrelaunchFlagCheck:
    def test_fails_when_flag_is_true(self, tmp_path):
        """Release validation must reject _CLOUD_PRELAUNCH_RELAXED = True."""
        mode_val = tmp_path / "backend" / "mode_validation.py"
        mode_val.parent.mkdir(parents=True)
        mode_val.write_text("_CLOUD_PRELAUNCH_RELAXED = True\n")

        failures = []
        with patch.object(validate_release, "REPO_ROOT", tmp_path):
            validate_release._check_cloud_prelaunch_flag(failures)

        assert len(failures) == 1
        assert "_CLOUD_PRELAUNCH_RELAXED" in failures[0]
        assert "cloud release targets" in failures[0]

    def test_passes_when_flag_is_false(self, tmp_path):
        """Release validation must pass when the flag is disabled."""
        mode_val = tmp_path / "backend" / "mode_validation.py"
        mode_val.parent.mkdir(parents=True)
        mode_val.write_text("_CLOUD_PRELAUNCH_RELAXED = False\n")

        failures = []
        with patch.object(validate_release, "REPO_ROOT", tmp_path):
            validate_release._check_cloud_prelaunch_flag(failures)

        assert failures == []

    def test_fails_when_file_missing(self, tmp_path):
        """Release validation must fail if mode_validation.py is absent."""
        failures = []
        with patch.object(validate_release, "REPO_ROOT", tmp_path):
            validate_release._check_cloud_prelaunch_flag(failures)

        assert len(failures) == 1
        assert "not found" in failures[0]
