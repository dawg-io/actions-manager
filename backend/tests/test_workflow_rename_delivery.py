"""A rename is delivered as a rename, not as a new file plus an orphan.

Git stores no rename: it is a remove plus an add that the diff detects by
content. So a campaign has to carry both halves on the same AM branch — then
GitHub's pull request shows a rename and merging it completes the change. Before
this, delivery wrote the new filename and nothing removed the old one, so every
rename left a file behind in every repository and the dialog told the user to go
delete it by hand.

The old name is the part that is easy to lose: ``create_or_update_workflow``
reassigns ``workflow_name``, and nothing else in the schema stores a filename
(``WorkflowVersion`` keeps content, ``WorkflowDriftState`` keys on
``workflow_id`` and derives the name). ``Workflow.renamed_from`` is that record.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    Account,
    LinkedReusableWorkflow,
    Project,
    ProjectRepo,
    ProjectWorkflow,
    Repo,
    Workflow,
    WorkflowDriftState,
)
from tests.conftest import TestingSessionLocal
from workflows import (
    DELETE_ABSENT,
    DELETE_DELETED,
    DELETE_FAILED,
    WorkflowSchema,
    _clear_completed_renames,
    _commit_workflows_to_branch,
    create_or_update_workflow,
)

OWNER = "rename-delivery-owner"
REPO = "deliver-org/app"
DELIVERED_SHA = "b" * 40
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


def _project(db, code):
    proj = Project(
        project_name=f"deliver_{os.urandom(4).hex()}",
        project_code=code,
        user_id=_account(db).user_id,
        branch_option="default",
        project_type="standard",
        use_prefix=True,
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    repo = db.query(Repo).filter(Repo.repo_name == REPO).first()
    if not repo:
        repo = Repo(repo_name=REPO)
        db.add(repo)
        db.commit()
        db.refresh(repo)
    db.add(ProjectRepo(project_id=proj.project_id, repo_id=repo.repo_id))
    db.commit()
    return proj


def _workflow(db, project, name, *, git_hash=DELIVERED_SHA, status="synced_with_github"):
    wf = Workflow(
        workflow_name=name,
        workflow_yaml="name: x\non: push",
        reusable_workflow=False,
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


def _rename(db, project, old, new):
    create_or_update_workflow(
        db,
        WorkflowSchema(name=new, content="name: x\non: push", original_name=old),
        project.project_id,
        is_reusable=False,
        last_modified_by=OWNER,
    )


# --- remembering the name GitHub still has ---------------------------------


def test_renaming_a_delivered_workflow_records_the_name_to_remove():
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLV1")
        wf = _workflow(db, proj, "ci")

        _rename(db, proj, "ci", "ci-v2")
        db.refresh(wf)

        assert wf.workflow_name == "ci-v2"
        assert wf.renamed_from == "ci"
    finally:
        db.close()


def test_renaming_a_workflow_that_was_never_delivered_records_nothing():
    """There is no old file on GitHub, so a campaign has nothing to remove."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLV2")
        wf = _workflow(db, proj, "ci", git_hash=LOCAL_ONLY_SHA, status="new")

        _rename(db, proj, "ci", "ci-v2")
        db.refresh(wf)

        assert wf.renamed_from is None
    finally:
        db.close()


def test_renaming_twice_before_delivering_still_removes_the_delivered_name():
    """ci -> ci2 -> ci3 must remove ci.yml: ci2 never reached GitHub."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLV3")
        wf = _workflow(db, proj, "ci")

        _rename(db, proj, "ci", "ci2")
        _rename(db, proj, "ci2", "ci3")
        db.refresh(wf)

        assert wf.workflow_name == "ci3"
        assert wf.renamed_from == "ci"
    finally:
        db.close()


def test_renaming_back_to_the_delivered_name_cancels_the_removal():
    """Otherwise the campaign deletes the file it just wrote.

    ci -> ci2 records ci. ci2 -> ci then leaves renamed_from and workflow_name
    both 'ci', so delivery would PUT AM_X_ci.yml and immediately DELETE it —
    and merging that campaign removes the workflow from every repository.
    """
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLV9")
        wf = _workflow(db, proj, "ci")

        _rename(db, proj, "ci", "ci2")
        _rename(db, proj, "ci2", "ci")
        db.refresh(wf)

        assert wf.workflow_name == "ci"
        assert wf.renamed_from is None
    finally:
        db.close()


def test_a_case_change_is_still_a_rename_with_an_old_file_to_remove():
    """GitHub's contents API is case-sensitive, so ci.yml and CI.yml differ."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLVA")
        wf = _workflow(db, proj, "ci")

        _rename(db, proj, "ci", "ci2")
        _rename(db, proj, "ci2", "CI")
        db.refresh(wf)

        assert wf.workflow_name == "CI"
        assert wf.renamed_from == "ci", "the lowercase file GitHub has still needs removing"
    finally:
        db.close()


def test_the_recorded_name_is_the_stored_one_not_the_requests_spelling():
    """The rename lookup matches case-insensitively, so the two can differ.

    Recording the request's spelling sends the removal after a path GitHub does
    not have; it 404s as "already absent" while the real file stays orphaned.
    """
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLVB")
        wf = _workflow(db, proj, "CI")

        _rename(db, proj, "ci", "deploy")
        db.refresh(wf)

        assert wf.renamed_from == "CI"
    finally:
        db.close()


def test_a_confirmed_delivery_counts_even_when_the_hash_was_zeroed():
    """A local edit zeroes workflow_git_hash; the file is still on GitHub."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLV4")
        wf = _workflow(db, proj, "ci", git_hash=LOCAL_ONLY_SHA, status="committed_locally")
        repo = db.query(Repo).filter(Repo.repo_name == REPO).first()
        db.add(WorkflowDriftState(
            project_id=proj.project_id, workflow_id=wf.workflow_id,
            repo_id=repo.repo_id, branch="main", has_drift=False,
            confirmed_present_at=__import__("datetime").datetime(2026, 9, 1, 12, 0, 0),
        ))
        db.commit()

        _rename(db, proj, "ci", "ci-v2")
        db.refresh(wf)

        assert wf.renamed_from == "ci"
    finally:
        db.close()


# --- carrying both halves on the campaign branch ---------------------------


def _commit(workflow_dict, *, delete_outcome=(DELETE_DELETED, None), status=201):
    """Run one workflow through the campaign's commit loop with GitHub mocked."""
    db = TestingSessionLocal()
    try:
        with patch("workflows._update_workflow_to_github",
                   return_value=(status, "c" * 40)), \
             patch("workflows._update_workflow_git_hash"), \
             patch("workflows._delete_workflow_from_branch",
                   return_value=delete_outcome) as deleter:
            committed, errors = _commit_workflows_to_branch(
                [workflow_dict], "deliver-org", "app", "DLV", "AM_DLV_update",
                {}, REPO, OWNER, db, True,
            )
        return committed, errors, deleter
    finally:
        db.close()


def test_the_campaign_removes_the_old_filename_from_the_same_branch():
    """Both halves on one branch is what makes the pull request read as a rename."""
    committed, errors, deleter = _commit(
        {"name": "ci-v2", "content": "name: x", "renamed_from": "ci"}
    )

    assert committed == ["ci-v2"]
    assert errors == []
    deleter.assert_called_once()
    args = deleter.call_args[0]
    assert args[2] == "ci", "the removed path must be the old name, not the new one"
    assert args[4] == "AM_DLV_update", "the removal belongs on the campaign branch"


def test_a_workflow_with_no_outstanding_rename_deletes_nothing():
    _, errors, deleter = _commit({"name": "ci", "content": "name: x", "renamed_from": None})

    assert errors == []
    deleter.assert_not_called()


def test_an_unchanged_new_file_still_removes_the_old_one():
    """204 means the add already landed — from a campaign closed before the remove did."""
    _, errors, deleter = _commit(
        {"name": "ci-v2", "content": "name: x", "renamed_from": "ci"}, status=204
    )

    assert errors == []
    deleter.assert_called_once()


def test_an_absent_old_file_is_not_an_error():
    """Removed by hand, or carried by an earlier campaign that was then closed."""
    committed, errors, _ = _commit(
        {"name": "ci-v2", "content": "name: x", "renamed_from": "ci"},
        delete_outcome=(DELETE_ABSENT, None),
    )

    assert errors == []
    assert committed == ["ci-v2"]


def test_a_failed_removal_is_reported_rather_than_swallowed():
    """Otherwise the campaign reports success while the old file is still there."""
    _, errors, _ = _commit(
        {"name": "ci-v2", "content": "name: x", "renamed_from": "ci"},
        delete_outcome=(DELETE_FAILED, "ci: HTTP 403 - forbidden"),
    )

    assert errors == ["ci: HTTP 403 - forbidden"]


def test_the_add_is_counted_once_even_though_two_files_changed():
    """Counting the removal too would report more files than the campaign carries."""
    committed, _, _ = _commit(
        {"name": "ci-v2", "content": "name: x", "renamed_from": "ci"}
    )

    assert committed == ["ci-v2"]


def test_the_old_file_is_only_removed_after_the_new_one_lands():
    """Removing first would leave the workflow absent if the write then failed."""
    _, errors, deleter = _commit(
        {"name": "ci-v2", "content": "name: x", "renamed_from": "ci"}, status=500
    )

    assert errors == ["ci-v2: HTTP 500"]
    deleter.assert_not_called()


# --- forgetting it, but only once the rename is really done ----------------


def test_a_merged_campaign_clears_the_recorded_name():
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLV5")
        wf = _workflow(db, proj, "ci-v2")
        wf.renamed_from = "ci"
        db.commit()

        _clear_completed_renames([wf], "synced_with_github")

        assert wf.renamed_from is None
    finally:
        db.close()


def test_a_closed_campaign_keeps_it_so_the_next_one_carries_the_rename():
    """A closed campaign never merged, so the old file is still on GitHub.

    The opposite of _cancel_pending_deletes, which clears on exactly this
    transition: there, a closed campaign means the deletion did not happen and
    the flag must be dropped. Here it means the rename did not happen and the
    name must be kept — clearing it would strand the old file with nothing left
    that knows its name.
    """
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLV6")
        wf = _workflow(db, proj, "ci-v2")
        wf.renamed_from = "ci"
        db.commit()

        _clear_completed_renames([wf], "committed_locally")

        assert wf.renamed_from == "ci"
    finally:
        db.close()


# --- the delivered-evidence gap, and the linked-merge orphan ----------------


def test_an_edited_delivered_workflow_is_not_mistaken_for_a_new_one():
    """Both DB signals fail together for a delivered-then-edited workflow.

    workflow_git_hash is zeroed by any local edit, and no WorkflowDriftState
    exists for a repo that is not one of the project's own ProjectRepo rows.
    That combination reported a live file as never delivered, so the old name
    was never recorded and the delivered file was orphaned forever — while the
    report, which asks GitHub, called the same rename "blocked".
    """
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLVC")
        wf = _workflow(db, proj, "shared", git_hash=LOCAL_ONLY_SHA,
                       status="committed_locally")
        assert db.query(WorkflowDriftState).filter(
            WorkflowDriftState.workflow_id == wf.workflow_id
        ).count() == 0, "the premise: no drift evidence exists"

        _rename(db, proj, "shared", "shared-v2")
        db.refresh(wf)

        assert wf.renamed_from == "shared"
    finally:
        db.close()


def test_a_workflow_still_in_its_initial_state_records_nothing():
    """`new` has never been through a campaign, so there is no old file."""
    db = TestingSessionLocal()
    try:
        proj = _project(db, "DLVD")
        wf = _workflow(db, proj, "ci", git_hash=LOCAL_ONLY_SHA, status="new")

        _rename(db, proj, "ci", "ci-v2")
        db.refresh(wf)

        assert wf.renamed_from is None
    finally:
        db.close()


def test_the_linked_reusable_merge_clears_the_recorded_name():
    """That bulk update is the only sync path for a workflow delivered through
    a caller project, and _clear_completed_renames never sees those rows. The
    name surviving the merge made the next rename keep it, so the campaign after
    that deleted an already-gone file and orphaned the name in between.
    """
    from workflows import _sync_linked_reusable_workflows_after_merge

    db = TestingSessionLocal()
    try:
        rwx = _project(db, "DLVE")
        shared = _workflow(db, rwx, "shared-v2", status="under_review")
        shared.reusable_workflow = True
        shared.renamed_from = "shared"
        db.commit()

        caller = _project(db, "DLVF")
        db.add(LinkedReusableWorkflow(
            standard_project_id=caller.project_id,
            rwx_project_id=rwx.project_id,
            workflow_id=shared.workflow_id,
        ))
        db.commit()

        _sync_linked_reusable_workflows_after_merge(db, caller.project_id)
        db.refresh(shared)

        assert shared.workflow_status == "synced_with_github"
        assert shared.renamed_from is None
    finally:
        db.close()
