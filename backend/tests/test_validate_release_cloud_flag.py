"""
Tests for the _check_cloud_prelaunch_flag guard in scripts/validate_release.py.

Ensures release validation fails when _CLOUD_PRELAUNCH_RELAXED = True is
present in backend/mode_validation.py, preventing cloud builds from shipping
with weakened billing/security controls (issue #1324).

The guard is scoped to release refs, so these tests pin the release context
explicitly rather than depending on whatever CI env they happen to run under.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the release validation script.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_release  # noqa: E402


@pytest.fixture
def release_ref(monkeypatch):
    """Pin the environment to a release ref (push to a release/* branch)."""
    monkeypatch.delenv("RELEASE_VALIDATION_FORCE_RELEASE", raising=False)
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/release/1.7.0-beta.1")


class TestCloudPrelaunchFlagCheck:
    def test_fails_when_flag_is_true(self, tmp_path, release_ref):
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

    def test_passes_when_flag_is_false(self, tmp_path, release_ref):
        """Release validation must pass when the flag is disabled."""
        mode_val = tmp_path / "backend" / "mode_validation.py"
        mode_val.parent.mkdir(parents=True)
        mode_val.write_text("_CLOUD_PRELAUNCH_RELAXED = False\n")

        failures = []
        with patch.object(validate_release, "REPO_ROOT", tmp_path):
            validate_release._check_cloud_prelaunch_flag(failures)

        assert failures == []

    def test_fails_when_file_missing(self, tmp_path, release_ref):
        """Release validation must fail if mode_validation.py is absent."""
        failures = []
        with patch.object(validate_release, "REPO_ROOT", tmp_path):
            validate_release._check_cloud_prelaunch_flag(failures)

        assert len(failures) == 1
        assert "not found" in failures[0]

    def test_flag_is_not_enforced_off_release_refs(self, tmp_path, monkeypatch):
        """
        On develop - this repo's default and only long-lived branch - the
        flag is deliberately True while cloud is pre-launch.
        Asserting there made this script fail on every develop push, which
        stopped the checks after it from running at all.
        """
        monkeypatch.delenv("RELEASE_VALIDATION_FORCE_RELEASE", raising=False)
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
        monkeypatch.setenv("GITHUB_REF", "refs/heads/develop")

        mode_val = tmp_path / "backend" / "mode_validation.py"
        mode_val.parent.mkdir(parents=True)
        mode_val.write_text("_CLOUD_PRELAUNCH_RELAXED = True\n")

        failures = []
        with patch.object(validate_release, "REPO_ROOT", tmp_path):
            validate_release._check_cloud_prelaunch_flag(failures)

        assert failures == []


class TestIsReleaseContext:
    @pytest.mark.parametrize(
        "env,expected",
        [
            # release/* branches are how promote-to-public.yml cuts a release
            # back into this repo - these are the real release refs.
            ({"GITHUB_REF": "refs/heads/release/1.7.0-beta.1"}, True),
            ({"GITHUB_REF": "refs/heads/release/2.0.0"}, True),
            # tags
            ({"GITHUB_REF": "refs/tags/v1.0.0"}, True),
            ({"GITHUB_REF": "refs/tags/2025.03.02"}, True),
            # this repo has no main branch; develop is the default and only
            # long-lived branch, and is explicitly NOT a release ref
            ({"GITHUB_REF": "refs/heads/develop"}, False),
            ({"GITHUB_REF": "refs/heads/main"}, False),
            ({"GITHUB_REF": "refs/heads/feat/something"}, False),
            # a branch merely named like a release, but not under release/
            ({"GITHUB_REF": "refs/heads/releases-notes"}, False),
            # pull_request: base_ref decides, and wins over GITHUB_REF, which
            # on a PR points at refs/pull/N/merge rather than the target branch
            (
                {
                    "GITHUB_BASE_REF": "release/1.7.0-beta.1",
                    "GITHUB_REF": "refs/pull/12/merge",
                },
                True,
            ),
            ({"GITHUB_BASE_REF": "develop", "GITHUB_REF": "refs/pull/12/merge"}, False),
            # running locally: no CI env at all
            ({}, False),
            # explicit manual override
            ({"RELEASE_VALIDATION_FORCE_RELEASE": "1"}, True),
        ],
    )
    def test_release_context_detection(self, monkeypatch, env, expected):
        for var in (
            "GITHUB_REF",
            "GITHUB_BASE_REF",
            "RELEASE_VALIDATION_FORCE_RELEASE",
        ):
            monkeypatch.delenv(var, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        assert validate_release._is_release_context() is expected
