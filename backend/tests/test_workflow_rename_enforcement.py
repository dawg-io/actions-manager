"""The rename guard, enforced on the write path rather than only previewed.

``POST /api/workflows/rename-impact`` computes what a rename would break, but
for a while nothing consulted it: ``create_or_update_workflow`` performed the
rename regardless, so the report could say "blocked" and the save would go
ahead — orphaning the delivered file under its old name and breaking every
caller's ``uses:`` line with no warning.

``_assert_rename_allowed`` now runs the same ``_rename_blockers`` the report
runs, so the two cannot disagree. These cover each refusal reaching the save,
and — just as important — that an ordinary rename still goes through.

No GitHub call is involved: every blocker is a database query, which is what
makes running them on the save path affordable.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException

from models import (
    Account,
    LinkedReusableWorkflow,
    Project,
    ProjectPullRequest,
    ProjectRepo,
    ProjectWorkflow,
    Repo,
    Workflow,
    WorkflowDriftState,
)
from tests.conftest import TestingSessionLocal
from workflows import WorkflowSchema, create_or_update_workflow

OWNER = "rename-guard-owner"
REPO = "guard-org/app"
DELIVERED_SHA = "a" * 40
LOCAL_ONLY_SHA = "0" * 40


def _account(db):
    owner = db.query(Account).filter(Account.github_user == OWNER).first()
    if not owner:
        owner = Account(github_user=OWNER, github_email=f"{OWNER}@example.com",
                        account_type="free")
        db.add(owner)
        db.commit()
        db.refresh(owner)
    return owner


def _project(db, *, code, project_type="standard", with_repo=True):
    proj = Project(
        project_name=f"guard_{os.urandom(4).hex()}",
        project_code=code,
        user_id=_account(db).user_id,
        branch_option="default",
        project_type=project_type,
        use_prefix=True,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)

    if with_repo:
        repo = db.query(Repo).filter(Repo.repo_name == REPO).first()
        if not repo:
            repo = Repo(repo_name=REPO)
            db.add(repo)
            db.commit()
            db.refresh(repo)
        db.add(ProjectRepo(project_id=proj.project_id, repo_id=repo.repo_id))
        db.commit()
    return proj


def _workflow(db, project, name, *, reusable=False, status="synced_with_github",
              git_hash=DELIVERED_SHA, content="name: x\non: push"):
    wf = Workflow(
        workflow_name=name,
        workflow_yaml=content,
        reusable_workflow=reusable,
        workflow_git_hash=git_hash,
        workflow_status=status,
        pending_delete=False,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
    db.commit()
    return wf


def _rename(db, project, old, new, *, reusable=False):
    """Perform the rename the way /api/save-workflows does."""
    create_or_update_workflow(
        db,
        WorkflowSchema(name=new, content="name: x\non: push", original_name=old),
        project.project_id,
        is_reusable=reusable,
        last_modified_by=OWNER,
    )


def _names(db, project):
    return {
        row.workflow_name
        for row in db.query(Workflow)
        .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
        .filter(ProjectWorkflow.project_id == project.project_id)
        .all()
    }


# --- the refusals that used to be preview-only ------------------------------


def test_a_workflow_under_review_cannot_be_renamed():
    """Its open PR names the old filename; renaming strands that PR."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, code="GRD1")
        _workflow(db, proj, "ci", status="under_review")

        with pytest.raises(HTTPException) as excinfo:
            _rename(db, proj, "ci", "ci-v2")
        assert excinfo.value.status_code == 409
        assert "under review" in excinfo.value.detail
        assert _names(db, proj) == {"ci"}
    finally:
        db.close()


def test_an_open_pr_carrying_the_workflow_blocks_the_rename():
    """project_pull_requests.workflow_names is a name snapshot the rename invalidates."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, code="GRD2")
        _workflow(db, proj, "ci")
        db.add(ProjectPullRequest(
            project_id=proj.project_id, repo_name=REPO, pr_number=11,
            pr_url=f"https://github.com/{REPO}/pull/11", pr_state="open",
            branch_name="AM_GRD2_update", target_branch="main",
            workflow_names="ci, other",
        ))
        db.commit()

        with pytest.raises(HTTPException) as excinfo:
            _rename(db, proj, "ci", "ci-v2")
        assert excinfo.value.status_code == 409
        assert "pull request" in excinfo.value.detail
        assert _names(db, proj) == {"ci"}
    finally:
        db.close()


def test_a_delivered_reusable_workflow_with_consumers_is_refused():
    """Nothing rewrites a caller's uses: line, so renaming breaks their CI silently."""
    db = TestingSessionLocal()
    try:
        rwx = _project(db, code="GRD3", project_type="rwx")
        shared = _workflow(db, rwx, "shared", reusable=True)

        caller = _project(db, code="GRD4", with_repo=False)
        db.add(LinkedReusableWorkflow(
            standard_project_id=caller.project_id,
            rwx_project_id=rwx.project_id,
            workflow_id=shared.workflow_id,
        ))
        db.commit()
        uses = f"uses: {REPO}/.github/workflows/AM_GRD3_shared.yml@main"
        _workflow(db, caller, "deploy",
                  content=f"name: deploy\non: push\njobs:\n  j:\n    {uses}")

        with pytest.raises(HTTPException) as excinfo:
            _rename(db, rwx, "shared", "shared-v2", reusable=True)
        assert excinfo.value.status_code == 409
        assert "uses:" in excinfo.value.detail
        assert _names(db, rwx) == {"shared"}
    finally:
        db.close()


def test_an_undelivered_reusable_workflow_with_consumers_is_allowed():
    """Nothing on GitHub references it yet, so there is no broken uses: to cause.

    The delivered/undelivered split is what keeps the refusal above from
    blocking every reusable rename — it is read from the database, not GitHub.
    """
    db = TestingSessionLocal()
    try:
        rwx = _project(db, code="GRD5", project_type="rwx")
        shared = _workflow(db, rwx, "shared", reusable=True,
                           status="new", git_hash=LOCAL_ONLY_SHA)

        caller = _project(db, code="GRD6", with_repo=False)
        db.add(LinkedReusableWorkflow(
            standard_project_id=caller.project_id,
            rwx_project_id=rwx.project_id,
            workflow_id=shared.workflow_id,
        ))
        db.commit()
        uses = f"uses: {REPO}/.github/workflows/AM_GRD5_shared.yml@main"
        _workflow(db, caller, "deploy",
                  content=f"name: deploy\non: push\njobs:\n  j:\n    {uses}")

        _rename(db, rwx, "shared", "shared-v2", reusable=True)
        assert _names(db, rwx) == {"shared-v2"}
    finally:
        db.close()


def test_a_confirmed_delivery_counts_even_after_a_local_edit():
    """workflow_git_hash alone would under-report: a local edit zeroes it.

    confirmed_present_at is the durable record that the file reached GitHub, and
    it survives the edit — without consulting it, editing a delivered reusable
    workflow would quietly unlock a rename that breaks its consumers.
    """
    db = TestingSessionLocal()
    try:
        rwx = _project(db, code="GRD7", project_type="rwx")
        # Zeroed hash: edited in ActionsManager since it was last pushed.
        shared = _workflow(db, rwx, "shared", reusable=True,
                           status="committed_locally", git_hash=LOCAL_ONLY_SHA)
        repo = db.query(Repo).filter(Repo.repo_name == REPO).first()
        db.add(WorkflowDriftState(
            project_id=rwx.project_id, workflow_id=shared.workflow_id,
            repo_id=repo.repo_id, branch="main", has_drift=False,
            confirmed_present_at=__import__("datetime").datetime(2026, 9, 1, 12, 0, 0),
        ))
        db.commit()

        caller = _project(db, code="GRD8", with_repo=False)
        db.add(LinkedReusableWorkflow(
            standard_project_id=caller.project_id,
            rwx_project_id=rwx.project_id,
            workflow_id=shared.workflow_id,
        ))
        db.commit()
        uses = f"uses: {REPO}/.github/workflows/AM_GRD7_shared.yml@main"
        _workflow(db, caller, "deploy",
                  content=f"name: deploy\non: push\njobs:\n  j:\n    {uses}")

        with pytest.raises(HTTPException) as excinfo:
            _rename(db, rwx, "shared", "shared-v2", reusable=True)
        assert excinfo.value.status_code == 409
        assert "uses:" in excinfo.value.detail
    finally:
        db.close()


def test_a_capitalisation_only_rename_keeps_the_stored_casing_without_failing_the_save():
    """is_rename compares lowercased, so 'Build' -> 'build' never changed anything.

    It used to raise 409 here. create_or_update_workflow commits per workflow
    with no outer transaction, so that abandoned a project save part-way —
    workflows ahead of it committed, workflows behind it silently losing their
    edits — and it repeated on every retry, leaving the project unsaveable after
    a purely cosmetic edit. The refusal belongs in the report, which the dialog
    shows before anything is sent; the save keeps the stored casing instead.
    """
    db = TestingSessionLocal()
    try:
        proj = _project(db, code="GRD9")
        _workflow(db, proj, "Build")

        _rename(db, proj, "Build", "build")

        assert _names(db, proj) == {"Build"}, "the stored casing is kept"
    finally:
        db.close()


def test_a_capitalisation_only_rename_does_not_strand_a_deletion():
    """Keeping the old casing must not leave a renamed_from pointing at it."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, code="GRDB")
        wf = _workflow(db, proj, "Build")

        _rename(db, proj, "Build", "build")
        db.refresh(wf)

        assert wf.renamed_from is None
    finally:
        db.close()


# --- and the ordinary case still works --------------------------------------


def test_an_ordinary_rename_still_goes_through():
    """The guard must refuse the listed cases and nothing else."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, code="GRDA")
        _workflow(db, proj, "ci")

        _rename(db, proj, "ci", "ci-v2")
        assert _names(db, proj) == {"ci-v2"}
    finally:
        db.close()
