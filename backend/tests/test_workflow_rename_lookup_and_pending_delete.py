"""Rename lookups must not use LIKE wildcards, and pending_delete rows must not surface.

Two independent defects covered here, both reachable without touching GitHub:

1. ``create_or_update_workflow``'s rename branch matched the old name with
   ``ilike()``.  ``_`` is a single-character wildcard in SQL LIKE and workflow
   names routinely contain it, so renaming ``ci_build`` could match an unrelated
   ``ciXbuild`` — and the duplicate sweep that follows *deletes* what it matches,
   so the wildcard could destroy a workflow the user never touched.

2. A workflow marked ``pending_delete`` is queued for removal from GitHub by an
   open campaign.  It was still listed by ``GET /api/projects/{name}`` and still
   checked for drift, so between the campaign merging and
   ``_reap_deleted_workflows`` destroying the row, drift reported the file as
   "deleted from GitHub" — drift for a deletion ActionsManager itself asked for.
   Delivery must keep seeing those rows, which is what carries the removal, so
   the exclusion has to be scoped to the read paths only.

No test here reaches GitHub: the one delivery test patches the update helper and
asserts on what it was handed, so a regression shows up as a wrong argument
rather than a live request.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import HTTPException
from fastapi.testclient import TestClient

from auth import user_tokens
from main import app
from models import Account, Project, ProjectWorkflow, Workflow
from tests.conftest import TestingSessionLocal
from workflows import (
    WorkflowSchema,
    _build_regular_workflow_results,
    _get_project_workflows,
    _update_workflow_git_hash,
    create_or_update_workflow,
)

OWNER = "rename-lookup-owner"

client = TestClient(app)


def _workflow(db, project, name, *, content="name: x\non: push", pending_delete=False,
              reusable=False):
    wf = Workflow(
        workflow_name=name,
        workflow_yaml=content,
        reusable_workflow=reusable,
        workflow_git_hash="0" * 40,
        workflow_status="committed_locally",
        pending_delete=pending_delete,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
    db.commit()
    return wf


@pytest.fixture(autouse=True)
def _token():
    user_tokens[OWNER] = "test-token"
    yield
    user_tokens.pop(OWNER, None)


@pytest.fixture
def project():
    """A fresh project per test, owned by OWNER, torn down afterwards."""
    db = TestingSessionLocal()
    try:
        owner = db.query(Account).filter(Account.github_user == OWNER).first()
        if not owner:
            owner = Account(github_user=OWNER, github_email=f"{OWNER}@example.com",
                            account_type="free")
            db.add(owner)
            db.commit()
            db.refresh(owner)

        proj = Project(
            project_name=f"rename_lookup_{os.urandom(4).hex()}",
            project_code=os.urandom(3).hex().upper()[:6],
            user_id=owner.user_id,
            branch_option="default",
            project_type="standard",
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        yield proj

        wf_ids = [
            row.workflow_id
            for row in db.query(ProjectWorkflow).filter_by(project_id=proj.project_id).all()
        ]
        db.query(ProjectWorkflow).filter_by(project_id=proj.project_id).delete()
        if wf_ids:
            db.query(Workflow).filter(Workflow.workflow_id.in_(wf_ids)).delete(
                synchronize_session=False
            )
        db.query(Project).filter_by(project_id=proj.project_id).delete()
        db.commit()
    finally:
        db.close()


def _names(db, project):
    return {
        row.workflow_name
        for row in db.query(Workflow)
        .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
        .filter(ProjectWorkflow.project_id == project.project_id)
        .all()
    }


# --- 1. LIKE wildcards in the rename lookup ---------------------------------


def test_rename_does_not_match_underscore_as_wildcard(project):
    """Renaming 'ci_build' must not pick up the unrelated 'ciXbuild'."""
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "ciXbuild", content="name: decoy\non: push")

        # 'ci_build' does not exist. Under ilike(), '_' matched the 'X' in
        # 'ciXbuild' and that row was renamed instead of a new one being created.
        create_or_update_workflow(
            db,
            WorkflowSchema(name="release", content="name: new\non: push",
                           original_name="ci_build"),
            project.project_id,
            is_reusable=False,
        )

        names = _names(db, project)
        assert "ciXbuild" in names, "the unrelated workflow was renamed by a LIKE wildcard"
        assert "release" in names, "the rename should have fallen through to a create"
    finally:
        db.close()


def test_rename_onto_a_taken_name_destroys_neither_it_nor_its_lookalike(project):
    """Two defects met here, and the rename is now refused before either can bite.

    The sweep that ran after a rename deleted rows matching the new name with
    ``ilike()``, so renaming to 'ci_build' also matched 'ciXbuild' — '_' is a
    single-character wildcard — and destroyed an unrelated workflow. The lookup
    is exact now, and the collision blocker refuses the rename outright, so the
    real 'ci_build' survives too rather than being swept aside.
    """
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "ci_build", content="name: real\non: push")
        _workflow(db, project, "ciXbuild", content="name: decoy\non: push")
        _workflow(db, project, "old-name", content="name: mover\non: push")

        taken = WorkflowSchema(name="ci_build", content="name: mover\non: push",
                               original_name="old-name")
        with pytest.raises(HTTPException) as excinfo:
            create_or_update_workflow(db, taken, project.project_id, is_reusable=False)
        assert excinfo.value.status_code == 409
        assert "already has a workflow named" in excinfo.value.detail

        names = _names(db, project)
        assert "ciXbuild" in names, "an unrelated workflow was deleted by a wildcard match"
        assert "ci_build" in names, "the workflow holding the name was destroyed"
        assert "old-name" in names, "the workflow being renamed lost its name anyway"
    finally:
        db.close()


# --- 2. pending_delete must not be revived by a save ------------------------


def test_rename_does_not_target_a_pending_delete_row(project):
    """A tombstone under the old name is a removal still owed, not a rename target."""
    db = TestingSessionLocal()
    try:
        tombstone = _workflow(db, project, "retired", pending_delete=True)

        create_or_update_workflow(
            db,
            WorkflowSchema(name="fresh", content="name: new\non: push",
                           original_name="retired"),
            project.project_id,
            is_reusable=False,
        )

        db.refresh(tombstone)
        assert tombstone.workflow_name == "retired", "the tombstone was renamed"
        assert tombstone.pending_delete is True, "the queued removal was cancelled"
        assert "fresh" in _names(db, project)
    finally:
        db.close()


def test_saving_over_a_tombstone_name_is_refused(project):
    """Reusing a name a tombstone still owns must be refused, not duplicated.

    An earlier version of this test asserted the duplicate as intended. It is
    not: both rows format to one GitHub path, so a campaign selecting that name
    hands _commit_workflows_to_branch both and the AM branch either deletes the
    file it just wrote or writes the file it was told to remove, depending on
    row order.
    """
    db = TestingSessionLocal()
    try:
        tombstone = _workflow(db, project, "ci", content="name: old\non: push",
                              pending_delete=True)

        # Built outside the block so the only call that can raise inside it is
        # the one under test (S5778).
        saved = WorkflowSchema(name="ci", content="name: brand new\non: push")
        with pytest.raises(HTTPException) as excinfo:
            create_or_update_workflow(db, saved, project.project_id, is_reusable=False)
        assert excinfo.value.status_code == 409
        assert "queued for removal" in excinfo.value.detail

        db.refresh(tombstone)
        assert tombstone.pending_delete is True, "the queued removal was cancelled"
        assert tombstone.workflow_yaml == "name: old\non: push", "the tombstone was overwritten"

        live = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(
                ProjectWorkflow.project_id == project.project_id,
                Workflow.workflow_name == "ci",
            )
            .all()
        )
        assert len(live) == 1, "a second row took the tombstone's name"
    finally:
        db.close()


# --- 3. pending_delete must not surface in the read paths -------------------


def test_drift_skips_pending_delete_workflows(project):
    """Drift must not report a removal ActionsManager itself asked for."""
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "live")
        _workflow(db, project, "going-away", pending_delete=True)
        _workflow(db, project, "rwx-going-away", pending_delete=True, reusable=True)

        regular, reusable = _get_project_workflows(db, project)

        assert [w.workflow_name for w in regular] == ["live"]
        assert reusable == []
    finally:
        db.close()


def test_project_load_omits_pending_delete_workflows(project):
    """A workflow the user already asked to delete should leave the list."""
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "live")
        _workflow(db, project, "going-away", pending_delete=True)
    finally:
        db.close()

    resp = client.get(
        f"/api/projects/{project.project_name}", params={"github_user": OWNER}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    listed = {w["name"] for w in body.get("workflows", [])}
    assert "live" in listed
    assert "going-away" not in listed, "a workflow queued for removal is still listed"


def test_delivery_still_receives_pending_delete_workflows(project):
    """The exclusion is for reads only — delivery is what carries the removal."""
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "going-away", pending_delete=True)
    finally:
        db.close()

    payload = MagicMock()
    payload.selected_workflows = ["going-away"]
    payload.selected_reusable_workflows = None
    payload.github_user = OWNER
    payload.campaign_name = None
    payload.campaign_description = None

    db = TestingSessionLocal()
    try:
        with patch("workflows._process_regular_workflows_update", return_value={}) as update, \
             patch("workflows._campaign_meta", return_value={}):
            _build_regular_workflow_results(
                project, payload, ["acme/api"], {}, db, github_user=OWNER
            )

        assert update.called, "delivery never ran for the pending_delete workflow"
        handed_over = update.call_args.kwargs["workflows"]
        assert [w["name"] for w in handed_over] == ["going-away"]
        assert handed_over[0]["pending_delete"] is True, (
            "delivery lost the flag that tells it to remove rather than upsert"
        )
    finally:
        db.close()


# --- 4. a tombstone's name cannot be taken by a second live row --------------
#
# Excluding pending_delete from the lookups (so a save cannot revive a
# tombstone) opened the opposite hazard: two rows in one project sharing a
# name, both formatting to one GitHub path. A campaign selecting that name then
# hands _commit_workflows_to_branch both, so it removes the file and upserts it
# on the same AM branch with DB order deciding which wins. Refuse the name
# instead. Both create_or_update_workflow implementations must refuse it —
# missing the projects.py copy is what let PUT /api/projects/{id}/ overwrite a
# tombstone's YAML while leaving the flag set.


def test_save_workflows_refuses_a_name_a_tombstone_still_owns(project):
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "ci", pending_delete=True)
    finally:
        db.close()

    resp = client.post(
        "/api/save-workflows",
        json={
            "github_user": OWNER,
            "project_name": project.project_name,
            "workflows": [{"name": "ci", "content": "name: new\non: push"}],
            "rxworkflows": [],
        },
        headers={"X-GitHub-User": OWNER},
    )
    assert resp.status_code == 409, resp.text
    assert "queued for removal" in resp.json()["detail"]

    db = TestingSessionLocal()
    try:
        rows = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(ProjectWorkflow.project_id == project.project_id,
                    Workflow.workflow_name == "ci")
            .all()
        )
        assert len(rows) == 1, "a second row took the tombstone's name"
        assert rows[0].pending_delete is True
        assert rows[0].workflow_yaml == "name: x\non: push", "the tombstone was overwritten"
    finally:
        db.close()


def test_project_update_also_refuses_a_tombstone_name(project):
    """The projects.py copy of create_or_update_workflow, which was missed."""
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "ci", pending_delete=True)
        owner_name = (
            db.query(Account)
            .filter(Account.user_id == project.user_id).first().github_user
        )
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{project.project_id}/",
        json={
            "github_user": owner_name,
            "project_name": project.project_name,
            "selected_repos": [],
            "workflows": [{"name": "ci", "content": "name: new\non: push"}],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": True,
        },
        headers={"X-GitHub-User": owner_name},
    )
    assert resp.status_code == 409, resp.text

    db = TestingSessionLocal()
    try:
        row = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(ProjectWorkflow.project_id == project.project_id,
                    Workflow.workflow_name == "ci")
            .one()
        )
        assert row.pending_delete is True, "the queued removal was cancelled"
        assert row.workflow_yaml == "name: x\non: push", "the tombstone was overwritten"
    finally:
        db.close()


def test_git_hash_stamp_skips_a_tombstone_holding_the_name(project):
    """The blob SHA belongs to the live row, never to a tombstone sharing its name.

    Only the upsert path reaches ``_update_workflow_git_hash`` —
    ``_commit_workflows_to_branch`` routes tombstones to
    ``_remove_workflow_on_branch`` and continues — so a tombstone is never what
    the SHA describes. It can still win the unfiltered ``.first()``, and then
    the live row keeps its stale baseline and real drift on it reads as
    synchronized. The collision is created directly here because that is how it
    reaches the database: rows written before the save-time guard existed.
    """
    db = TestingSessionLocal()
    try:
        tombstone = _workflow(db, project, "ci", pending_delete=True)
        live = _workflow(db, project, "ci")

        _update_workflow_git_hash(db, "ci", "a" * 40, project.project_code, is_reusable=False)

        db.refresh(live)
        db.refresh(tombstone)
        assert live.workflow_git_hash == "a" * 40, "the live row's drift baseline was not updated"
        assert tombstone.workflow_git_hash == "0" * 40, "the SHA landed on the queued removal"
    finally:
        db.close()


def test_renaming_onto_a_tombstone_name_is_refused(project):
    """A rename takes the new name, so it needs the same refusal as a save.

    The guard sat only in the ``existing_workflow is None`` branch — exactly
    the one a rename skips, because the rename lookup already found the row by
    its old name. The duplicate sweep that follows excludes pending_delete, so
    the tombstone survived and the project ended up with two rows named 'ci'
    behind one delivered path: the pair the guard exists to prevent, reached
    through the other door.
    """
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "ci", content="name: queued\non: push", pending_delete=True)
        _workflow(db, project, "other", content="name: other\non: push")

        renamed = WorkflowSchema(name="ci", content="name: other\non: push",
                                 original_name="other")
        with pytest.raises(HTTPException) as excinfo:
            create_or_update_workflow(db, renamed, project.project_id, is_reusable=False)
        assert excinfo.value.status_code == 409
        assert "queued for removal" in excinfo.value.detail

        rows = (
            db.query(Workflow)
            .join(ProjectWorkflow, Workflow.workflow_id == ProjectWorkflow.workflow_id)
            .filter(ProjectWorkflow.project_id == project.project_id,
                    Workflow.workflow_name == "ci")
            .all()
        )
        assert len(rows) == 1, "the rename created a second row under the tombstone's name"
        assert rows[0].pending_delete is True
        assert _names(db, project) == {"ci", "other"}, "the original was renamed anyway"
    finally:
        db.close()


def test_the_project_save_endpoint_renames_instead_of_duplicating(project):
    """Saving a project used to turn a rename into a second workflow.

    Three layers each dropped it: handleSaveProject sent only {name, content},
    projects.WorkflowSchema declared only those two so Pydantic discarded
    original_name, and projects.py kept its own create_or_update_workflow with
    no rename branch. The old workflow stayed and a new one appeared beside it.
    """
    db = TestingSessionLocal()
    try:
        _workflow(db, project, "ci", content="name: old\non: push")
        owner_name = (
            db.query(Account)
            .filter(Account.user_id == project.user_id).first().github_user
        )
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{project.project_id}/",
        json={
            "github_user": owner_name,
            "project_name": project.project_name,
            "selected_repos": [],
            "workflows": [{"name": "ci-v2", "content": "name: old\non: push",
                           "original_name": "ci"}],
            "rxworkflows": [],
            "branch_regex": "",
            "branch_option": "default",
            "branch_max_age_days": 30,
            "reusable_workflows_enabled": False,
            "use_prefix": True,
        },
        headers={"X-GitHub-User": owner_name},
    )
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        assert _names(db, project) == {"ci-v2"}, "the rename left the old workflow behind"
    finally:
        db.close()
