"""
Tests for the optional name/visibility parameters on POST /api/create-repo.

The endpoint originally hardcoded 'am-reuseable-workflow' and private=True.
The onboarding tour needs a throwaway demo repository instead, so the name is
now caller-supplied — which makes it a trust boundary, since the value is sent
straight to the GitHub API on the user's behalf.
"""

import pytest
from fastapi import HTTPException

from repos import DEFAULT_NEW_REPO_NAME, _validated_repo_name


class TestRepoNameValidation:
    def test_missing_name_keeps_the_historical_default(self):
        # The reusable-workflow flow sends no name and must be unaffected.
        assert _validated_repo_name(None) == DEFAULT_NEW_REPO_NAME
        assert _validated_repo_name("") == DEFAULT_NEW_REPO_NAME

    @pytest.mark.parametrize(
        "name",
        ["actionsmanager-demo", "demo", "a", "with.dots", "with_underscores", "a" * 100],
    )
    def test_accepts_valid_github_repository_names(self, name):
        assert _validated_repo_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "has spaces",
            "../../etc/passwd",       # path traversal
            "owner/repo",             # would retarget the API path
            "repo?foo=bar",           # query injection into the URL
            "a" * 101,                # longer than GitHub allows
            "emoji-🚀",
            "<script>",
        ],
    )
    def test_rejects_anything_that_is_not_a_repository_name(self, name):
        with pytest.raises(HTTPException) as excinfo:
            _validated_repo_name(name)
        assert excinfo.value.status_code == 400

    def test_rejects_non_string_input(self):
        with pytest.raises(HTTPException):
            _validated_repo_name({"name": "nested"})
