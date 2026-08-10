"""
Regression test: drift must be attributed to the right repo when one repo's
name is a prefix of another's.

_match_repo_for_status pins a drift status to a repo by scanning the status
message for a repo name. Scanning in list order meant "acme/api" matched a
message about "acme/api-gateway" first, so the longer repo's drift was
recorded against the shorter one. Because WorkflowDriftState is unique per
(workflow_id, repo_id), every drifted repo then collapsed onto a single row —
the project reported drift in a repo that was actually clean, and none in the
repos that had really drifted.
"""

import sys
import os
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workflows import _match_repo_for_status


def _status(message):
    return SimpleNamespace(message=message)


REPOS = ["acme/api", "acme/api-gateway", "acme/api-gateway-v2"]


def test_prefix_named_repo_does_not_shadow_the_longer_one():
    matched = _match_repo_for_status(
        _status("Workflow content differs between local and acme/api-gateway"), REPOS
    )
    assert matched == "acme/api-gateway"


def test_longest_matching_repo_wins():
    matched = _match_repo_for_status(
        _status("Workflow content differs between local and acme/api-gateway-v2"), REPOS
    )
    assert matched == "acme/api-gateway-v2"


def test_exact_shorter_repo_still_matches_itself():
    matched = _match_repo_for_status(
        _status("Workflow synchronized with acme/api"), REPOS
    )
    assert matched == "acme/api"


def test_single_candidate_is_used_even_without_a_message_match():
    # Pre-existing fallback: with exactly one repo there is nothing to confuse.
    assert _match_repo_for_status(_status("no repo named here"), ["acme/api"]) == "acme/api"


def test_no_match_across_multiple_candidates_returns_none():
    assert _match_repo_for_status(_status("no repo named here"), REPOS) is None
