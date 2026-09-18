"""A rename reaches GitHub as two file changes on one campaign branch.

The user's requirement, stated plainly: opening the pull request must do two
things — write the new filename, and delete the old one — so the PR carries two
changes rather than a new file plus an orphan nobody removes.

The existing delivery tests mock ``_delete_workflow_from_branch``, which proves
the branch is wired but not what actually reaches GitHub. These assert on the
HTTP calls themselves: the PUT path, the DELETE path, and that both name the
same AM branch.
"""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import TestingSessionLocal
from workflows import _commit_workflows_to_branch

OWNER, REPO, CODE, AM_BRANCH = "acme", "app", "MYP1", "AM_MYP1_update"


def _run(workflow_dict):
    """Drive the campaign's commit loop with GitHub's HTTP surface mocked."""
    db = TestingSessionLocal()
    puts, deletes = [], []

    def fake_put(url, *a, **kwargs):
        puts.append((url, kwargs.get("json", {})))
        return MagicMock(status_code=201, json=lambda: {"content": {"sha": "f" * 40}})

    def fake_delete(url, **kwargs):
        deletes.append((url, kwargs.get("json", {})))
        return MagicMock(status_code=200, json=lambda: {})

    def fake_get(url, *a, **kw):
        # The new path is absent (so the write is a create, not an update); the
        # old path is present, so the delete has a sha to send. Everything else
        # — the AM branch existence check — answers 200.
        if "AM_MYP1_renamed.yml" in url:
            return MagicMock(status_code=404, json=lambda: {})
        return MagicMock(status_code=200, json=lambda: {"sha": "a" * 40})

    try:
        with patch("workflows.github_put", side_effect=fake_put), \
             patch("workflows.requests.delete", side_effect=fake_delete), \
             patch("workflows.github_get", side_effect=fake_get), \
             patch("workflows.requests.get", side_effect=fake_get), \
             patch("workflows._update_workflow_git_hash"):
            committed, errors = _commit_workflows_to_branch(
                [workflow_dict], OWNER, REPO, CODE, AM_BRANCH,
                {}, f"{OWNER}/{REPO}", "octocat", db, True,
            )
        return committed, errors, puts, deletes
    finally:
        db.close()


def test_opening_the_pr_writes_the_new_file_and_deletes_the_old_one():
    committed, errors, puts, deletes = _run(
        {"name": "renamed", "content": "name: x\non: push", "renamed_from": "okokok"}
    )

    assert errors == []
    assert committed == ["renamed"]

    assert len(puts) == 1, "the new filename is written once"
    assert ".github/workflows/AM_MYP1_renamed.yml" in puts[0][0]
    assert puts[0][1]["branch"] == AM_BRANCH

    assert len(deletes) == 1, "the old filename is removed — this is the second change"
    assert ".github/workflows/AM_MYP1_okokok.yml" in deletes[0][0]
    assert deletes[0][1]["branch"] == AM_BRANCH
    assert deletes[0][1]["sha"] == "a" * 40


def test_an_ordinary_edit_deletes_nothing():
    _, errors, puts, deletes = _run({"name": "renamed", "content": "name: x", "renamed_from": None})

    assert errors == []
    assert len(puts) == 1
    assert deletes == [], "only a rename removes a file"


# --- the delete must never target the path the same campaign just wrote ------


def _run_unprefixed(workflow_dict):
    """Same as _run, without the AM_<CODE>_ prefix, where names collide."""
    db = TestingSessionLocal()
    puts, deletes = [], []

    def fake_put(url, *a, **kwargs):
        puts.append(url)
        return MagicMock(status_code=201, json=lambda: {"content": {"sha": "f" * 40}})

    def fake_delete(url, **kwargs):
        deletes.append(url)
        return MagicMock(status_code=200, json=lambda: {})

    def fake_get(url, *a, **kw):
        return MagicMock(status_code=200, json=lambda: {"sha": "a" * 40})

    try:
        with patch("workflows.github_put", side_effect=fake_put), \
             patch("workflows.requests.delete", side_effect=fake_delete), \
             patch("workflows.github_get", side_effect=fake_get), \
             patch("workflows.requests.get", side_effect=fake_get), \
             patch("workflows._update_workflow_git_hash"):
            _commit_workflows_to_branch(
                [workflow_dict], OWNER, REPO, CODE, AM_BRANCH,
                {}, f"{OWNER}/{REPO}", "octocat", db, False,
            )
        return puts, deletes
    finally:
        db.close()


def test_adding_the_yml_suffix_does_not_delete_the_file_just_written():
    """Without a prefix, `ci` and `ci.yml` are both `ci.yml`.

    renamed_from records a NAME; the guard used to compare names, so `ci` !=
    `ci.yml` and the removal went ahead — PUT ci.yml then DELETE ci.yml on the
    same branch. Merging that campaign removed the workflow from every target
    repository while ActionsManager reported the rename as delivered.
    """
    puts, deletes = _run_unprefixed(
        {"name": "ci.yml", "content": "name: x", "renamed_from": "ci"}
    )

    assert len(puts) == 1
    assert puts[0].endswith("/.github/workflows/ci.yml")
    assert deletes == [], "the file just written must not be deleted"


def test_dropping_the_yml_suffix_is_the_same_collision():
    puts, deletes = _run_unprefixed(
        {"name": "ci", "content": "name: x", "renamed_from": "ci.yml"}
    )

    assert len(puts) == 1
    assert deletes == []


def test_a_case_only_difference_does_not_delete_the_file_just_written():
    """`ci` -> `ci2` -> `CI` is the two-step route the case-only refusal
    recommends, and it leaves renamed_from='ci' against workflow_name='CI'.
    If GitHub's contents API folds case, deleting `ci.yml` destroys `CI.yml`.
    Leaving an orphan is the cheaper mistake, so the comparison ignores case.
    """
    puts, deletes = _run_unprefixed(
        {"name": "CI", "content": "name: x", "renamed_from": "ci"}
    )

    assert len(puts) == 1
    assert deletes == []


def test_a_genuine_rename_still_removes_the_old_file():
    """The guard must skip the collision and nothing else."""
    puts, deletes = _run_unprefixed(
        {"name": "ci-v2", "content": "name: x", "renamed_from": "ci"}
    )

    assert len(puts) == 1
    assert puts[0].endswith("/.github/workflows/ci-v2.yml")
    assert len(deletes) == 1
    assert deletes[0].endswith("/.github/workflows/ci.yml")
