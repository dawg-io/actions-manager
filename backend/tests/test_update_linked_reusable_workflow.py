"""
Regression tests for the linked reusable workflow update endpoint.

Verifies that editing a reusable workflow that is linked into a standard
project via ``LinkedReusableWorkflow`` updates the *existing* canonical
``Workflow`` row in the source RWX project — and never creates a duplicate
``Workflow`` or duplicate ``ProjectWorkflow`` row.

Endpoint under test:
    PUT /api/projects/{project_name}/linked-reusable-workflows/{workflow_id}

These tests cover the success criteria from the issue
"Fix linked reusable workflow updates creating duplicate workflow files":

* Existing workflows row is updated (not duplicated)
* No new ProjectWorkflow association is created
* A new workflow_versions row is appended for the same workflow_id
* LinkedReusableWorkflow row is unchanged
* The RWX project still contains exactly one reusable workflow with that name
* Unauthorized users cannot update linked workflows
* Resolution is by workflow_id, not by workflow_name (so the display-formatted
  name returned by the project API does not produce a duplicate)
"""
import os
import sys

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (  # noqa: E402
    Base,
    Account,
    Project,
    Workflow,
    ProjectWorkflow,
    LinkedReusableWorkflow,
    ProjectPullRequest,
    WorkflowVersion,
    WorkspaceMember,
    ProjectMembership,
)
from main import app  # noqa: E402
from projects import get_db as projects_get_db  # noqa: E402


SQLALCHEMY_DATABASE_URL = "sqlite:///./test_update_linked_rwx_workflow.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_and_teardown_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app.dependency_overrides[projects_get_db] = override_get_db
    with patch("mode_validation.validate_startup_configuration"):
        with TestClient(app) as c:
            yield c
    app.dependency_overrides.pop(projects_get_db, None)


def _seed(db, *, owner="alice"):
    """Create owner + standard project + RWX project + one linked reusable workflow."""
    user = Account(github_user=owner, github_email=f"{owner}@example.com",
                   account_type="pro")
    db.add(user)
    db.flush()

    rwx = Project(
        project_name="MyDawgRWX",
        project_code="RWW1",
        user_id=user.user_id,
        project_type="rwx",
        use_prefix=True,
    )
    std = Project(
        project_name="MyConsumer",
        project_code="STD1",
        user_id=user.user_id,
        project_type="standard",
        use_prefix=False,
    )
    db.add_all([rwx, std])
    db.flush()

    wf = Workflow(
        workflow_name="testrwx",  # canonical stem stored in DB
        workflow_yaml="name: Old\non:\n  workflow_call: {}\n",
        reusable_workflow=True,
        workflow_status="synced",
        workflow_git_hash="a" * 40,
    )
    db.add(wf)
    db.flush()
    db.add(ProjectWorkflow(project_id=rwx.project_id, workflow_id=wf.workflow_id))
    db.add(LinkedReusableWorkflow(
        standard_project_id=std.project_id,
        rwx_project_id=rwx.project_id,
        workflow_id=wf.workflow_id,
    ))
    db.commit()
    db.refresh(wf)
    db.refresh(std)
    db.refresh(rwx)
    return user, std, rwx, wf


def test_update_linked_workflow_updates_existing_row_in_place(client):
    """Happy path: the canonical workflow row is updated, not duplicated."""
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)
        original_workflow_id = wf.workflow_id
    finally:
        db.close()

    new_yaml = "name: New\non:\n  workflow_call: {}\njobs:\n  build: {}\n"
    resp = client.put(
        f"/api/projects/{std.project_name}/linked-reusable-workflows/{original_workflow_id}",
        json={"github_user": "alice", "content": new_yaml},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workflow_id"] == original_workflow_id
    assert body["rwx_project_name"] == "MyDawgRWX"
    assert "MyDawgRWX" in body["message"]

    db = TestingSessionLocal()
    try:
        # The same row was updated in place
        wf_after = db.query(Workflow).filter_by(workflow_id=original_workflow_id).one()
        assert wf_after.workflow_yaml.strip() == new_yaml.strip()
        assert wf_after.workflow_status == "committed_locally"
        assert wf_after.workflow_git_hash == "0" * 40
        # No duplicate workflow was created in the RWX project
        rwx_workflows = (
            db.query(Workflow)
            .join(ProjectWorkflow)
            .filter(
                ProjectWorkflow.project_id == rwx.project_id,
                Workflow.reusable_workflow.is_(True),
            )
            .all()
        )
        assert len(rwx_workflows) == 1
        assert rwx_workflows[0].workflow_id == original_workflow_id
        assert rwx_workflows[0].workflow_name == "testrwx"
        # ProjectWorkflow association count unchanged
        pw_rows = db.query(ProjectWorkflow).filter_by(
            workflow_id=original_workflow_id).all()
        assert len(pw_rows) == 1
        assert pw_rows[0].project_id == rwx.project_id
        # LinkedReusableWorkflow unchanged
        link_rows = db.query(LinkedReusableWorkflow).filter_by(
            workflow_id=original_workflow_id).all()
        assert len(link_rows) == 1
        assert link_rows[0].standard_project_id == std.project_id
        assert link_rows[0].rwx_project_id == rwx.project_id
        # A new workflow_versions row was appended for the same workflow_id
        versions = db.query(WorkflowVersion).filter_by(
            workflow_id=original_workflow_id).order_by(
            WorkflowVersion.version_number).all()
        assert len(versions) >= 1
        assert versions[-1].content.strip() == new_yaml.strip()
    finally:
        db.close()


def test_update_linked_workflow_resolves_by_workflow_id_not_name(client):
    """The display-formatted workflow_name (with prefix + .yml) must NOT be
    used for resolution — workflow_id is the source of truth.

    Reproduces the exact bug: the API normally returns the linked workflow as
    ``AM_RWW1_testrwx.yml``.  Sending an update via the new endpoint with that
    formatted name would have created a duplicate under the old code path; here
    we simulate that scenario by using only the workflow_id and confirm that
    the original canonical row (stored as bare ``testrwx``) is updated."""
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)
        original_workflow_id = wf.workflow_id
        original_name = wf.workflow_name
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std.project_name}/linked-reusable-workflows/{original_workflow_id}",
        json={"github_user": "alice", "content": "name: Updated\non:\n  workflow_call: {}\n"},
    )
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        # Name is unchanged — we update by id, not by name
        wf_after = db.query(Workflow).filter_by(
            workflow_id=original_workflow_id).one()
        assert wf_after.workflow_name == original_name
        # And there is no second workflow with the formatted display name
        formatted = "AM_RWW1_testrwx.yml"
        assert (
            db.query(Workflow).filter(Workflow.workflow_name == formatted).count() == 0
        )
    finally:
        db.close()


def test_update_linked_workflow_returns_404_when_not_linked(client):
    """If the workflow is not linked into the named standard project, the
    endpoint must return 404 instead of creating a new workflow."""
    db = TestingSessionLocal()
    try:
        user = Account(github_user="alice", github_email="a@a.com",
                       account_type="pro")
        db.add(user)
        db.flush()
        rwx = Project(project_name="RWX", project_code="RWW9",
                      user_id=user.user_id, project_type="rwx")
        std = Project(project_name="Std", project_code="STD9",
                      user_id=user.user_id, project_type="standard")
        db.add_all([rwx, std])
        db.flush()
        wf = Workflow(workflow_name="not-linked", workflow_yaml="x:",
                      reusable_workflow=True)
        db.add(wf)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx.project_id,
                               workflow_id=wf.workflow_id))
        # Note: NO LinkedReusableWorkflow row.
        db.commit()
        db.refresh(wf)
        db.refresh(std)
        wf_id = wf.workflow_id
        std_name = std.project_name
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "alice", "content": "name: New\n"},
    )
    assert resp.status_code == 404
    assert "Linked reusable workflow not found" in resp.json()["detail"]

    db = TestingSessionLocal()
    try:
        # No mutation occurred
        wf_after = db.query(Workflow).filter_by(workflow_id=wf_id).one()
        assert wf_after.workflow_yaml == "x:"
        assert db.query(Workflow).count() == 1
    finally:
        db.close()


def test_unauthorized_user_cannot_update_linked_workflow(client):
    """A user with no access to either project must receive a 404/403 and
    must not be able to mutate the workflow."""
    db = TestingSessionLocal()
    try:
        _owner, std, _rwx, wf = _seed(db, owner="alice")
        wf_id = wf.workflow_id
        std_name = std.project_name
        original_yaml = wf.workflow_yaml
        # Create a second, unrelated user with no membership/ownership
        intruder = Account(github_user="mallory",
                           github_email="m@example.com", account_type="free")
        db.add(intruder)
        db.commit()
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "mallory", "content": "name: Pwn\n"},
    )
    assert resp.status_code in (403, 404), resp.text

    db = TestingSessionLocal()
    try:
        wf_after = db.query(Workflow).filter_by(workflow_id=wf_id).one()
        assert wf_after.workflow_yaml == original_yaml, (
            "Unauthorized request must not mutate the workflow"
        )
    finally:
        db.close()


def test_update_linked_workflow_appends_new_version_each_call(client):
    """Each successful update must append a new workflow_versions row tied to
    the same canonical workflow_id."""
    db = TestingSessionLocal()
    try:
        _user, std, _rwx, wf = _seed(db)
        wf_id = wf.workflow_id
        std_name = std.project_name
    finally:
        db.close()

    for i in range(3):
        resp = client.put(
            f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
            json={"github_user": "alice",
                  "content": f"name: V{i}\non:\n  workflow_call: {{}}\n"},
        )
        assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        versions = db.query(WorkflowVersion).filter_by(workflow_id=wf_id).all()
        assert len(versions) == 3
        # Single workflow row, single ProjectWorkflow row, single link row
        assert db.query(Workflow).filter_by(workflow_id=wf_id).count() == 1
        assert db.query(ProjectWorkflow).filter_by(workflow_id=wf_id).count() == 1
        assert db.query(LinkedReusableWorkflow).filter_by(
            workflow_id=wf_id).count() == 1
    finally:
        db.close()


def test_update_linked_workflow_cleans_up_pre_existing_duplicate(client):
    """If a previous (buggy) save created a duplicate reusable workflow with
    the same name in the RWX project, the canonical row is preserved and
    updated, and the duplicate is removed so the RWX project shows a single
    workflow."""
    db = TestingSessionLocal()
    try:
        user, std, rwx, wf = _seed(db)
        # Simulate a duplicate created by the old buggy path.
        dup = Workflow(
            workflow_name=wf.workflow_name,  # same name -> duplicate
            workflow_yaml="name: Dup\n",
            reusable_workflow=True,
            workflow_status="new",
        )
        db.add(dup)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx.project_id,
                               workflow_id=dup.workflow_id))
        db.commit()
        wf_id = wf.workflow_id
        std_name = std.project_name
        rwx_id = rwx.project_id
        dup_id = dup.workflow_id
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "alice", "content": "name: Cleaned\n"},
    )
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        # The canonical workflow still exists with new content
        wf_after = db.query(Workflow).filter_by(workflow_id=wf_id).one()
        assert "Cleaned" in wf_after.workflow_yaml
        # The duplicate is removed
        assert db.query(Workflow).filter_by(workflow_id=dup_id).first() is None
        # Single reusable workflow remains in the RWX project
        rwx_workflows = (
            db.query(Workflow)
            .join(ProjectWorkflow)
            .filter(
                ProjectWorkflow.project_id == rwx_id,
                Workflow.reusable_workflow.is_(True),
            )
            .all()
        )
        assert len(rwx_workflows) == 1
        assert rwx_workflows[0].workflow_id == wf_id
    finally:
        db.close()


def test_update_linked_workflow_cleans_up_display_formatted_duplicate(client):
    """Recovery for projects already corrupted by the prior bug.

    The previous (buggy) save path round-tripped the *display-formatted* name
    (``AM_{code}_{stem}.yml``) back through ``/api/save-workflows`` and inserted
    a duplicate row stored under that formatted name — not under the canonical
    bare stem.  The cleanup must normalize candidate names (strip extension and
    ``AM_<code>_`` prefix) so it can recognise and remove these legacy
    duplicates, otherwise corrupted projects would remain corrupted forever.
    """
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)
        # Simulate the legacy bug: the display-formatted name was inserted as
        # a separate workflow.  Source RWX project is "RWW1" with use_prefix=True
        # so the formatted name is "AM_RWW1_testrwx.yml".
        formatted_dup = Workflow(
            workflow_name="AM_RWW1_testrwx.yml",
            workflow_yaml="name: LegacyDup\n",
            reusable_workflow=True,
            workflow_status="new",
        )
        db.add(formatted_dup)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx.project_id,
                               workflow_id=formatted_dup.workflow_id))
        db.commit()
        wf_id = wf.workflow_id
        std_name = std.project_name
        rwx_id = rwx.project_id
        formatted_dup_id = formatted_dup.workflow_id
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "alice", "content": "name: Cleaned\n"},
    )
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        # Canonical row updated, legacy display-formatted dup removed
        wf_after = db.query(Workflow).filter_by(workflow_id=wf_id).one()
        assert "Cleaned" in wf_after.workflow_yaml
        assert db.query(Workflow).filter_by(
            workflow_id=formatted_dup_id).first() is None
        rwx_workflows = (
            db.query(Workflow)
            .join(ProjectWorkflow)
            .filter(
                ProjectWorkflow.project_id == rwx_id,
                Workflow.reusable_workflow.is_(True),
            )
            .all()
        )
        assert len(rwx_workflows) == 1
        assert rwx_workflows[0].workflow_id == wf_id
    finally:
        db.close()


def test_update_linked_workflow_does_not_delete_unrelated_underscore_names(client):
    """The duplicate-detection comparison must use exact (case-insensitive)
    equality on the normalized stem.  Workflow names commonly contain ``_``
    which is a wildcard in SQL LIKE/ILIKE; if the cleanup query used ILIKE on
    the raw name, any name matching the LIKE pattern (e.g. ``test_rwx`` would
    match ``testrwx`` because ``_`` is a single-char wildcard) could be
    deleted by mistake.
    """
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)  # canonical name = "testrwx"
        # An *unrelated* reusable workflow whose name would falsely match
        # ``testrwx`` if compared with raw ILIKE wildcards (``_`` wildcard
        # would let "tXstrwx" / "testrwX" / etc match).  Pick one that is
        # the same length and differs only in characters that ``_`` would
        # match: the canonical is "testrwx" (7 chars).  Use a name of the
        # same length so a buggy ILIKE on ``workflow_name`` could match it.
        unrelated = Workflow(
            workflow_name="testrwy",  # not a duplicate; differs by last char
            workflow_yaml="name: Unrelated\n",
            reusable_workflow=True,
            workflow_status="synced",
        )
        db.add(unrelated)
        db.flush()
        db.add(ProjectWorkflow(project_id=rwx.project_id,
                               workflow_id=unrelated.workflow_id))
        db.commit()
        wf_id = wf.workflow_id
        std_name = std.project_name
        unrelated_id = unrelated.workflow_id
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "alice", "content": "name: Updated\n"},
    )
    assert resp.status_code == 200, resp.text

    db = TestingSessionLocal()
    try:
        # The unrelated workflow must NOT have been deleted as a "duplicate".
        unrelated_after = db.query(Workflow).filter_by(
            workflow_id=unrelated_id).first()
        assert unrelated_after is not None, (
            "Unrelated workflow must not be deleted by duplicate cleanup"
        )
        assert unrelated_after.workflow_yaml == "name: Unrelated\n"
    finally:
        db.close()


def _grant_membership(db, user_id, project_id, *, role):
    db.add(ProjectMembership(
        user_id=user_id, project_id=project_id, project_role=role,
    ))
    db.flush()


def test_project_viewer_member_cannot_update_linked_workflow(client):
    """A workspace member with only project_viewer role on either the
    consuming standard project or the source RWX project must receive 403.
    """
    db = TestingSessionLocal()
    try:
        _owner, std, rwx, wf = _seed(db)
        # Create a separate, non-admin workspace member with project_viewer
        # access on BOTH projects — read access only.
        viewer = Account(github_user="viewer",
                         github_email="v@v.com", account_type="pro")
        db.add(viewer)
        db.flush()
        db.add(WorkspaceMember(
            user_id=viewer.user_id, workspace_role="member",
        ))
        _grant_membership(db, viewer.user_id, std.project_id,
                          role="project_viewer")
        _grant_membership(db, viewer.user_id, rwx.project_id,
                          role="project_viewer")
        db.commit()
        wf_id = wf.workflow_id
        std_name = std.project_name
        original_yaml = wf.workflow_yaml
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "viewer", "content": "name: Pwn\n"},
        headers={"X-GitHub-User": "viewer"},
    )
    assert resp.status_code == 403, resp.text
    assert "project_editor" in resp.json()["detail"]

    db = TestingSessionLocal()
    try:
        wf_after = db.query(Workflow).filter_by(workflow_id=wf_id).one()
        assert wf_after.workflow_yaml == original_yaml, (
            "project_viewer must not be able to mutate a linked workflow"
        )
    finally:
        db.close()


def test_project_editor_on_consumer_only_cannot_update_linked_workflow(client):
    """A workspace member who is project_editor on the *consuming* standard
    project but only project_viewer on the *source* RWX project must receive
    403 — write access is required on both sides because the mutation lands
    in the RWX project's data."""
    db = TestingSessionLocal()
    try:
        _owner, std, rwx, wf = _seed(db)
        editor = Account(github_user="halfeditor",
                         github_email="h@h.com", account_type="pro")
        db.add(editor)
        db.flush()
        db.add(WorkspaceMember(
            user_id=editor.user_id, workspace_role="member",
        ))
        _grant_membership(db, editor.user_id, std.project_id,
                          role="project_editor")
        _grant_membership(db, editor.user_id, rwx.project_id,
                          role="project_viewer")
        db.commit()
        wf_id = wf.workflow_id
        std_name = std.project_name
        original_yaml = wf.workflow_yaml
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "halfeditor", "content": "name: Half\n"},
        headers={"X-GitHub-User": "halfeditor"},
    )
    assert resp.status_code == 403, resp.text
    assert "RWX" in resp.json()["detail"]

    db = TestingSessionLocal()
    try:
        wf_after = db.query(Workflow).filter_by(workflow_id=wf_id).one()
        assert wf_after.workflow_yaml == original_yaml
    finally:
        db.close()


def test_project_editor_on_both_can_update_linked_workflow(client):
    """A workspace member with project_editor on both projects can update."""
    db = TestingSessionLocal()
    try:
        _owner, std, rwx, wf = _seed(db)
        editor = Account(github_user="editor",
                         github_email="e@e.com", account_type="pro")
        db.add(editor)
        db.flush()
        db.add(WorkspaceMember(
            user_id=editor.user_id, workspace_role="member",
        ))
        _grant_membership(db, editor.user_id, std.project_id,
                          role="project_editor")
        _grant_membership(db, editor.user_id, rwx.project_id,
                          role="project_editor")
        db.commit()
        wf_id = wf.workflow_id
        std_name = std.project_name
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "editor", "content": "name: OK\n"},
        headers={"X-GitHub-User": "editor"},
    )
    assert resp.status_code == 200, resp.text


def test_update_preserves_under_review_while_campaign_open(client):
    """
    REGRESSION (issue: reusable workflow with an open PR campaign must stay
    locked everywhere).

    Editing a linked reusable workflow previously reset ``workflow_status`` to
    ``committed_locally`` unconditionally — bypassing the global under_review
    lock while an open PR campaign (from any project) still referenced the
    workflow.

    EXPECTED: while the campaign is open, the PUT update keeps the workflow
    ``under_review`` (content still saves); once the campaign is merged the
    same update resets it to ``committed_locally`` as usual.
    """
    db = TestingSessionLocal()
    try:
        _user, std, rwx, wf = _seed(db)
        wf_id = wf.workflow_id
        std_name = std.project_name
        wf.workflow_status = "under_review"
        # Open campaign referencing the workflow via its display-formatted
        # name, stored against the dedicated reusable workflow repo.
        db.add(ProjectPullRequest(
            project_id=std.project_id,
            repo_name="alice/am-reuseable-workflow",
            pr_number=41,
            pr_url="https://github.com/alice/am-reuseable-workflow/pull/41",
            branch_name="AM-STD1-campaign",
            target_branch="main",
            pr_state="open",
            workflow_names="AM_RWW1_testrwx.yml",
        ))
        db.commit()
    finally:
        db.close()

    locked_yaml = "name: LockedEdit\non:\n  workflow_call: {}\n"
    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "alice", "content": locked_yaml},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["workflow_status"] == "under_review", (
        f"Open campaign must keep the workflow under_review, "
        f"got {resp.json()['workflow_status']!r}"
    )

    db = TestingSessionLocal()
    try:
        wf_after = db.query(Workflow).filter_by(workflow_id=wf_id).one()
        assert wf_after.workflow_status == "under_review"
        assert wf_after.workflow_yaml.strip() == locked_yaml.strip()
        assert wf_after.workflow_git_hash == "0" * 40
        # Negative control: resolve the campaign → normal reset applies.
        pr = db.query(ProjectPullRequest).filter_by(pr_number=41).one()
        pr.pr_state = "merged"
        db.commit()
    finally:
        db.close()

    resp = client.put(
        f"/api/projects/{std_name}/linked-reusable-workflows/{wf_id}",
        json={"github_user": "alice", "content": "name: Unlocked\non:\n  workflow_call: {}\n"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["workflow_status"] == "committed_locally"

    db = TestingSessionLocal()
    try:
        wf_after = db.query(Workflow).filter_by(workflow_id=wf_id).one()
        assert wf_after.workflow_status == "committed_locally"
    finally:
        db.close()
