"""
Authorization tests for the two workflow delete endpoints.

`DELETE /api/delete-workflow` and `DELETE /api/delete-reusable-workflow` both
commit deletions to GitHub. Neither authorized the caller against the project:

  - the project was resolved with a global `Project.project_name.ilike(...)`
    lookup, so any signed-in caller could name any project;
  - `delete-workflow` took `repo_names` straight from the request body, so the
    repositories it deleted from were the caller's to choose;
  - neither read `ProjectMembership.project_role`, so a project_viewer — which
    models.py documents as read-only — passed;
  - `delete-reusable-workflow` resolves its target through
    `_get_reusable_workflow_repo`, which for a standard project returns the
    *linked RWX project's* repository. Deleting there removes the copy every
    other caller project linking that project depends on.

No test here reaches GitHub: every one asserts the request is refused before any
GitHub call, and the GitHub clients are patched so a regression shows up as a
call that should not have happened rather than a live request.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from models import (
    Account, Project, ProjectMembership, ProjectRepo, Repo, WorkspaceMember,
)
from tests.conftest import TestingSessionLocal

OWNER = "wfdel-owner"
VIEWER = "wfdel-viewer"
EDITOR = "wfdel-editor"
STRANGER = "wfdel-stranger"

client = TestClient(app)


def _account(db, name):
    acct = Account(github_user=name, github_email=f"{name}@example.com", account_type="free")
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def _member(db, account, workspace_role, project=None, project_role=None):
    db.add(WorkspaceMember(user_id=account.user_id, workspace_role=workspace_role))
    if project is not None and project_role is not None:
        db.add(ProjectMembership(
            user_id=account.user_id, project_id=project.project_id, project_role=project_role,
        ))
    db.commit()


@pytest.fixture
def world():
    """One standard project owned by OWNER, with one repo, plus three other users."""
    db = TestingSessionLocal()
    try:
        owner = _account(db, OWNER)
        project = Project(
            project_name="wfdel_project", project_code="WFD",
            user_id=owner.user_id, branch_option="default", project_type="standard",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        repo = Repo(repo_name="acme/in-project")
        outside = Repo(repo_name="acme/not-in-project")
        db.add_all([repo, outside])
        db.commit()
        db.refresh(repo)
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
        db.commit()

        _member(db, _account(db, VIEWER), "member", project, "project_viewer")
        _member(db, _account(db, EDITOR), "member", project, "project_editor")
        _member(db, _account(db, STRANGER), "member")

        return {"project": project, "project_name": project.project_name}
    finally:
        db.close()


ALL_TOKENS = {OWNER: "t", VIEWER: "t", EDITOR: "t", STRANGER: "t"}


def _delete_workflow(as_user, project_name, repo_names, authenticate_client):
    """Call DELETE /api/delete-workflow with every GitHub client patched."""
    authenticate_client(client, as_user, TestingSessionLocal)
    with patch("workflows.user_tokens", ALL_TOKENS), \
         patch("auth.user_tokens", ALL_TOKENS), \
         patch("workflows.httpx.AsyncClient") as http, \
         patch("workflows.clear_workflow_drift"):
        http.return_value.__aenter__.return_value = AsyncMock()
        resp = client.request(
            "DELETE", "/api/delete-workflow",
            headers={"X-GitHub-User": as_user},
            json={"user": as_user, "repo_names": repo_names,
                  "workflow_name": "ci", "project_name": project_name},
        )
    return resp, http


class TestDeleteWorkflowAuthorization:
    def test_a_stranger_cannot_name_someone_elses_project(self, world, authenticate_client):
        resp, http = _delete_workflow(
            STRANGER, world["project_name"], ["acme/in-project"], authenticate_client
        )

        assert resp.status_code in (403, 404)
        http.assert_not_called()

    def test_a_project_viewer_is_refused(self, world, authenticate_client):
        """models.py documents project_viewer as read-only access."""
        resp, http = _delete_workflow(
            VIEWER, world["project_name"], ["acme/in-project"], authenticate_client
        )

        assert resp.status_code == 403
        http.assert_not_called()

    def test_a_repository_outside_the_project_is_refused(self, world, authenticate_client):
        """repo_names is caller-supplied; without this the target was theirs to pick."""
        resp, http = _delete_workflow(
            EDITOR, world["project_name"], ["acme/not-in-project"], authenticate_client
        )

        assert resp.status_code in (400, 403)
        http.assert_not_called()

    def test_one_bad_repository_refuses_the_whole_request(self, world, authenticate_client):
        """Otherwise the in-project repo is deleted from before the check trips."""
        resp, http = _delete_workflow(
            EDITOR, world["project_name"],
            ["acme/in-project", "acme/not-in-project"], authenticate_client,
        )

        assert resp.status_code in (400, 403)
        http.assert_not_called()

    def test_an_editor_on_an_in_project_repo_is_allowed_through(self, world, authenticate_client):
        resp, _ = _delete_workflow(
            EDITOR, world["project_name"], ["acme/in-project"], authenticate_client
        )

        assert resp.status_code == 200

    def test_the_owner_is_allowed_through(self, world, authenticate_client):
        resp, _ = _delete_workflow(
            OWNER, world["project_name"], ["acme/in-project"], authenticate_client
        )

        assert resp.status_code == 200


def _delete_reusable(as_user, project_name, authenticate_client):
    authenticate_client(client, as_user, TestingSessionLocal)
    with patch("workflows.user_tokens", ALL_TOKENS), \
         patch("auth.user_tokens", ALL_TOKENS), \
         patch("workflows.httpx.AsyncClient") as http:
        http.return_value.__aenter__.return_value = AsyncMock()
        resp = client.request(
            "DELETE", "/api/delete-reusable-workflow",
            headers={"X-GitHub-User": as_user},
            json={"user": as_user, "workflow_name": "shared-deploy",
                  "project_name": project_name},
        )
    return resp, http


class TestDeleteReusableWorkflowAuthorization:
    def test_a_standard_project_cannot_delete_from_the_linked_rwx_repo(
        self, world, authenticate_client
    ):
        """_get_reusable_workflow_repo returns a repository this project does not
        own, so the file deleted there is the copy other projects link to."""
        resp, http = _delete_reusable(OWNER, world["project_name"], authenticate_client)

        assert resp.status_code == 409
        assert "does not own" in resp.json()["detail"]
        http.assert_not_called()

    def test_a_stranger_cannot_name_someone_elses_project(self, world, authenticate_client):
        resp, http = _delete_reusable(STRANGER, world["project_name"], authenticate_client)

        assert resp.status_code in (403, 404)
        http.assert_not_called()

    def test_a_project_viewer_is_refused(self, world, authenticate_client):
        resp, http = _delete_reusable(VIEWER, world["project_name"], authenticate_client)

        assert resp.status_code == 403
        http.assert_not_called()

    def test_an_rwx_project_owner_reaches_github(self, world, authenticate_client):
        """The RWX project owns its repository, so deleting there is its own file."""
        db = TestingSessionLocal()
        try:
            owner = db.query(Account).filter_by(github_user=OWNER).first()
            rwx = Project(
                project_name="wfdel_rwx", project_code="RWX",
                user_id=owner.user_id, branch_option="default", project_type="rwx",
            )
            db.add(rwx)
            db.commit()
            db.refresh(rwx)
            repo = Repo(repo_name="acme/shared-workflows")
            db.add(repo)
            db.commit()
            db.refresh(repo)
            db.add(ProjectRepo(project_id=rwx.project_id, repo_id=repo.repo_id))
            db.commit()
            rwx_name = rwx.project_name
        finally:
            db.close()

        branches = MagicMock()
        branches.status_code = 200
        branches.json.return_value = [{"name": "main"}]
        missing = MagicMock()
        missing.status_code = 404

        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows.httpx.AsyncClient") as http:
            gh = AsyncMock()
            gh.get.side_effect = [branches, missing]
            http.return_value.__aenter__.return_value = gh
            resp = client.request(
                "DELETE", "/api/delete-reusable-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "workflow_name": "shared-deploy",
                      "project_name": rwx_name},
            )

        assert resp.status_code == 200


class TestDeleteWorkflowDelivery:
    """`delivery=campaign` runs a PR Campaign instead of committing directly.

    Direct commit removes the file from every branch with no review; the campaign
    marks the workflow pending_delete and lets the campaign carry the removal,
    the way custom-file deletion already works.
    """

    def _seed_workflow(self, project_name="wfdel_project"):
        from models import ProjectWorkflow, Workflow
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_name=project_name).first()
            wf = Workflow(
                workflow_name="ci", workflow_yaml="name: CI\non: push",
                reusable_workflow=False, workflow_status="synced_with_github",
            )
            db.add(wf)
            db.commit()
            db.refresh(wf)
            db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
            db.commit()
            return wf.workflow_id
        finally:
            db.close()

    @staticmethod
    def _resp(status_code, payload=None):
        r = MagicMock()
        r.status_code = status_code
        r.text = ""
        r.json.return_value = payload if payload is not None else {}
        return r

    def test_an_unknown_delivery_is_refused(self, world, authenticate_client):
        self._seed_workflow()
        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows.httpx.AsyncClient") as http:
            http.return_value.__aenter__.return_value = AsyncMock()
            resp = client.request(
                "DELETE", "/api/delete-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "repo_names": ["acme/in-project"],
                      "workflow_name": "ci", "project_name": "wfdel_project",
                      "delivery": "yolo"},
            )

        assert resp.status_code == 400
        http.assert_not_called()

    def test_campaign_delivery_opens_a_campaign_and_keeps_the_row(
        self, world, authenticate_client
    ):
        from models import Workflow
        workflow_id = self._seed_workflow()
        pr = {"number": 11, "html_url": "https://github.com/acme/in-project/pull/11",
              "title": "t", "user": {"login": OWNER}, "body": "b"}

        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows._resolve_branches_for_repo", return_value=["main"]), \
             patch("workflows._create_or_get_am_branch",
                   return_value=("actions-manager/wfd/in-project/ab12-main", True, None)), \
             patch("workflows._fetch_branch_protection", return_value={"status": "none"}), \
             patch("workflows.github_get", return_value=self._resp(200, {"sha": "abc"})), \
             patch("workflows.requests.delete", return_value=self._resp(200)) as gh_delete, \
             patch("workflows._check_existing_pr", return_value=None), \
             patch("workflows._create_pull_request", return_value=(pr, None)):
            resp = client.request(
                "DELETE", "/api/delete-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "repo_names": ["acme/in-project"],
                      "workflow_name": "ci", "project_name": "wfdel_project",
                      "delivery": "campaign"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["campaign_id"] is not None
        assert body["prs_created"] == 1

        # Deleted on the AM branch, not on the target branch.
        assert gh_delete.call_args.kwargs["json"]["branch"].startswith("actions-manager/")

        db = TestingSessionLocal()
        try:
            wf = db.query(Workflow).filter_by(workflow_id=workflow_id).first()
            # The row survives until the campaign merges — that is what Restore
            # would cancel and what the synced transition cleans up.
            assert wf is not None
            assert wf.pending_delete is True
        finally:
            db.close()

    def test_a_campaign_that_opens_nothing_unmarks_the_workflow(
        self, world, authenticate_client
    ):
        from models import Workflow
        workflow_id = self._seed_workflow()

        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows._resolve_branches_for_repo", return_value=["main"]), \
             patch("workflows._create_or_get_am_branch",
                   return_value=(None, False, "branch is protected")), \
             patch("workflows._create_pull_request") as create_pr:
            resp = client.request(
                "DELETE", "/api/delete-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "repo_names": ["acme/in-project"],
                      "workflow_name": "ci", "project_name": "wfdel_project",
                      "delivery": "campaign"},
            )

        assert resp.status_code == 502
        create_pr.assert_not_called()
        db = TestingSessionLocal()
        try:
            wf = db.query(Workflow).filter_by(workflow_id=workflow_id).first()
            # Otherwise it sits marked for a deletion no pull request will carry.
            assert wf.pending_delete is False
            assert wf.workflow_status == "synced_with_github"
        finally:
            db.close()


class TestPendingDeleteWorkflowIsDroppedOnMerge:
    def test_the_row_goes_when_the_campaign_merges(self, world):
        from models import ProjectWorkflow, Workflow
        from workflows import _update_project_workflows_status

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_name="wfdel_project").first()
            doomed = Workflow(workflow_name="going", workflow_yaml="x",
                              reusable_workflow=False, workflow_status="under_review",
                              pending_delete=True)
            staying = Workflow(workflow_name="staying", workflow_yaml="y",
                               reusable_workflow=False, workflow_status="under_review")
            db.add_all([doomed, staying])
            db.commit()
            db.refresh(doomed)
            db.refresh(staying)
            db.add_all([
                ProjectWorkflow(project_id=project.project_id, workflow_id=doomed.workflow_id),
                ProjectWorkflow(project_id=project.project_id, workflow_id=staying.workflow_id),
            ])
            db.commit()
            doomed_id, staying_id = doomed.workflow_id, staying.workflow_id
            project_id = project.project_id
        finally:
            db.close()

        with patch("workflows.drop_workflow_drift") as drop_drift:
            _update_project_workflows_status(
                TestingSessionLocal(), project_id, "synced_with_github",
                only_if_status="under_review",
            )

        db = TestingSessionLocal()
        try:
            assert db.query(Workflow).filter_by(workflow_id=doomed_id).first() is None
            assert db.query(ProjectWorkflow).filter_by(workflow_id=doomed_id).first() is None
            survivor = db.query(Workflow).filter_by(workflow_id=staying_id).first()
            assert survivor is not None
            assert survivor.workflow_status == "synced_with_github"
        finally:
            db.close()

        # Drift for the removed workflow compares against a file that is gone.
        drop_drift.assert_called_once()
        assert drop_drift.call_args[0][2] == doomed_id


class TestDeleteWorkflowRepoScoping:
    """The repositories a deletion reaches must be the ones it was authorized for.

    Two ways this went wrong. `_require_repo_in_project` deliberately accepts the
    reusable-workflow repo so reusable-workflow drift stays resolvable from the
    UI — that exception let a caller project name the *linked RWX project's*
    repository and delete the shared copy out of it, which is exactly what
    `_require_owns_reusable_repo` refuses on the sibling endpoint. And the
    campaign path passed no `selected_repos`, so `_get_filtered_repo_names`
    returned every repository in the project regardless of what was asked for.
    """

    def test_the_linked_rwx_repo_cannot_be_named_as_a_target(
        self, world, authenticate_client
    ):
        from models import LinkedReusableWorkflow, ProjectWorkflow, Workflow

        db = TestingSessionLocal()
        try:
            owner = db.query(Account).filter_by(github_user=OWNER).first()
            standard = db.query(Project).filter_by(project_name="wfdel_project").first()
            rwx = Project(
                project_name="wfdel_rwx_linked", project_code="RWL",
                user_id=owner.user_id, branch_option="default", project_type="rwx",
            )
            db.add(rwx)
            db.commit()
            db.refresh(rwx)
            shared = Repo(repo_name="acme/shared-rwx-repo")
            db.add(shared)
            db.commit()
            db.refresh(shared)
            db.add(ProjectRepo(project_id=rwx.project_id, repo_id=shared.repo_id))
            shared_wf = Workflow(
                workflow_name="shared-deploy", workflow_yaml="name: Shared\non: push",
                reusable_workflow=True, workflow_status="synced_with_github",
            )
            db.add(shared_wf)
            db.commit()
            db.refresh(shared_wf)
            db.add(ProjectWorkflow(project_id=rwx.project_id, workflow_id=shared_wf.workflow_id))
            db.add(LinkedReusableWorkflow(
                standard_project_id=standard.project_id, rwx_project_id=rwx.project_id,
                workflow_id=shared_wf.workflow_id,
            ))
            db.commit()
        finally:
            db.close()

        resp, http = _delete_workflow(
            OWNER, world["project_name"], ["acme/shared-rwx-repo"], authenticate_client
        )

        assert resp.status_code == 400
        http.assert_not_called()

    def test_a_campaign_only_targets_the_repositories_asked_for(
        self, world, authenticate_client
    ):
        """Without selected_repos the campaign sweeps in every project repo."""
        from models import ProjectWorkflow, Workflow

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_name="wfdel_project").first()
            second = Repo(repo_name="acme/second-in-project")
            db.add(second)
            db.commit()
            db.refresh(second)
            db.add(ProjectRepo(project_id=project.project_id, repo_id=second.repo_id))
            wf = Workflow(
                workflow_name="ci", workflow_yaml="name: CI\non: push",
                reusable_workflow=False, workflow_status="synced_with_github",
            )
            db.add(wf)
            db.commit()
            db.refresh(wf)
            db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
            db.commit()
        finally:
            db.close()

        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows._process_regular_workflows_update") as process:
            process.return_value = {}
            client.request(
                "DELETE", "/api/delete-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "repo_names": ["acme/in-project"],
                      "workflow_name": "ci", "project_name": "wfdel_project",
                      "delivery": "campaign"},
            )

        process.assert_called_once()
        targeted = process.call_args.args[0] if process.call_args.args else process.call_args.kwargs["repo_names"]
        assert targeted == ["acme/in-project"], targeted


class TestPendingDeleteLifecycle:
    """A marked workflow must not be able to strand itself.

    `_unmark` covers the failures inside the delete request, but the campaign can
    also be abandoned later: the PR is opened and then closed on GitHub. That
    reverts the workflow to committed_locally while leaving pending_delete set,
    and nothing surfaces the flag or clears it — so the next campaign the user
    opens for an unrelated edit removes the file instead of updating it.
    """

    def _seed(self, status, pending_delete):
        from models import ProjectWorkflow, Workflow
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_name="wfdel_project").first()
            wf = Workflow(
                workflow_name="ci", workflow_yaml="name: CI\non: push",
                reusable_workflow=False, workflow_status=status,
                pending_delete=pending_delete,
            )
            db.add(wf)
            db.commit()
            db.refresh(wf)
            db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
            db.commit()
            return project.project_id, wf.workflow_id
        finally:
            db.close()

    def test_a_closed_campaign_cancels_the_pending_deletion(self, world):
        from models import Workflow
        from workflows import _update_project_workflows_status

        project_id, workflow_id = self._seed("under_review", True)

        _update_project_workflows_status(
            TestingSessionLocal(), project_id, "committed_locally",
            only_if_status="under_review",
        )

        db = TestingSessionLocal()
        try:
            wf = db.query(Workflow).filter_by(workflow_id=workflow_id).first()
            assert wf is not None, "a closed campaign must not delete the row"
            assert wf.pending_delete is False
            assert wf.workflow_status == "committed_locally"
        finally:
            db.close()

    def test_a_merged_campaign_still_drops_the_row(self, world):
        from models import Workflow
        from workflows import _update_project_workflows_status

        project_id, workflow_id = self._seed("under_review", True)

        _update_project_workflows_status(
            TestingSessionLocal(), project_id, "synced_with_github",
            only_if_status="under_review",
        )

        db = TestingSessionLocal()
        try:
            assert db.query(Workflow).filter_by(workflow_id=workflow_id).first() is None
        finally:
            db.close()


class TestDeleteWorkflowNameHandling:
    """The name reaches a GitHub contents path, so it gets the same validation
    every other path-forming caller applies — and a lookup that matches it
    exactly. `ilike` treats the "_" workflow names routinely contain as a
    wildcard, which CLAUDE.md calls out."""

    def test_a_path_traversing_name_is_refused(self, world, authenticate_client):
        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows.httpx.AsyncClient") as http:
            http.return_value.__aenter__.return_value = AsyncMock()
            resp = client.request(
                "DELETE", "/api/delete-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "repo_names": ["acme/in-project"],
                      "workflow_name": "../../../etc/passwd",
                      "project_name": "wfdel_project", "delivery": "direct"},
            )

        assert resp.status_code == 400
        http.assert_not_called()

    def test_a_name_with_a_query_character_is_refused(self, world, authenticate_client):
        """Unquoted, "?" would truncate the contents path and drop the ref."""
        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows.httpx.AsyncClient") as http:
            http.return_value.__aenter__.return_value = AsyncMock()
            resp = client.request(
                "DELETE", "/api/delete-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "repo_names": ["acme/in-project"],
                      "workflow_name": "ci?ref=main",
                      "project_name": "wfdel_project", "delivery": "direct"},
            )

        assert resp.status_code == 400
        http.assert_not_called()

    def test_an_underscore_does_not_match_a_neighbouring_workflow(
        self, world, authenticate_client
    ):
        """"ci_build" as a LIKE pattern also matches "ci-build"."""
        from models import ProjectWorkflow, Workflow

        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_name="wfdel_project").first()
            ids = {}
            for name in ("ci-build", "ci_build"):
                wf = Workflow(
                    workflow_name=name, workflow_yaml="name: CI\non: push",
                    reusable_workflow=False, workflow_status="synced_with_github",
                )
                db.add(wf)
                db.commit()
                db.refresh(wf)
                db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
                db.commit()
                ids[name] = wf.workflow_id
        finally:
            db.close()

        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows.drop_workflow_drift"):
            resp = client.request(
                "DELETE", "/api/delete-db-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "workflow_name": "ci_build",
                      "project_name": "wfdel_project"},
            )

        assert resp.status_code == 200
        db = TestingSessionLocal()
        try:
            assert db.query(Workflow).filter_by(workflow_id=ids["ci_build"]).first() is None
            assert db.query(Workflow).filter_by(workflow_id=ids["ci-build"]).first() is not None
        finally:
            db.close()


class TestCampaignWithNothingToRemove:
    """A campaign that opens no pull request is not always a failure.

    `_describe_empty_delivery` already separates the two reasons a target gets
    nothing: a real failure, and a pending-delete file the branch never had.
    Only the first is an error — the second means there was no GitHub copy for a
    pull request to review, so answering 502 would leave a workflow the user
    asked to delete both undeleted and unexplained.
    """

    def _seed(self):
        from models import ProjectWorkflow, Workflow
        db = TestingSessionLocal()
        try:
            project = db.query(Project).filter_by(project_name="wfdel_project").first()
            wf = Workflow(
                workflow_name="ci", workflow_yaml="name: CI\non: push",
                reusable_workflow=False, workflow_status="new",
            )
            db.add(wf)
            db.commit()
            db.refresh(wf)
            db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=wf.workflow_id))
            db.commit()
            return wf.workflow_id
        finally:
            db.close()

    def _delete(self, authenticate_client, results):
        authenticate_client(client, OWNER, TestingSessionLocal)
        with patch("workflows.user_tokens", ALL_TOKENS), \
             patch("auth.user_tokens", ALL_TOKENS), \
             patch("workflows._process_regular_workflows_update", return_value=results), \
             patch("workflows.drop_workflow_drift"):
            return client.request(
                "DELETE", "/api/delete-workflow",
                headers={"X-GitHub-User": OWNER},
                json={"user": OWNER, "repo_names": ["acme/in-project"],
                      "workflow_name": "ci", "project_name": "wfdel_project",
                      "delivery": "campaign"},
            )

    def test_a_file_no_branch_had_is_simply_removed(self, world, authenticate_client):
        from models import Workflow
        workflow_id = self._seed()

        resp = self._delete(authenticate_client, {
            "acme/in-project on main": {
                "status": "error",
                "error": "Nothing to deliver: ...",
                "workflow_errors": [],
                "custom_file_errors": [],
                "nothing_to_deliver": True,
            },
        })

        assert resp.status_code == 200, resp.text
        db = TestingSessionLocal()
        try:
            assert db.query(Workflow).filter_by(workflow_id=workflow_id).first() is None
        finally:
            db.close()

    def test_a_target_that_actually_failed_still_answers_502(
        self, world, authenticate_client
    ):
        """Otherwise a real failure silently deletes the row it could not remove."""
        from models import Workflow
        workflow_id = self._seed()

        resp = self._delete(authenticate_client, {
            "acme/in-project on main": {
                "status": "error",
                "error": "No workflows committed: ci: HTTP 403",
                "workflow_errors": ["ci: HTTP 403"],
                "custom_file_errors": [],
                "nothing_to_deliver": False,
            },
        })

        assert resp.status_code == 502
        db = TestingSessionLocal()
        try:
            wf = db.query(Workflow).filter_by(workflow_id=workflow_id).first()
            assert wf is not None, "a failed removal must not delete the row"
            assert wf.pending_delete is False
        finally:
            db.close()
