"""
Regression tests for campaign rollback — generating a reviewable inverse PR
campaign from a partially or fully merged campaign.

The inverse is computed from the merged pull request itself (merge commit's
first parent + the files the PR touched), never from ActionsManager state, so
these tests drive a fake GitHub routed by URL rather than stubbing the
computation out.

Verifies:
- A simple workflow change inverts to the content at the pre-merge base commit
- A file the campaign created inverts to a delete
- A repo whose file changed after the merge is flagged non-invertible, named,
  and never gets a rollback PR opened for it
- An unreadable merge commit is flagged rather than guessed at
- Only merged repos become rollback targets, and the new campaign links back
- The user's choice about ActionsManager's own copy is applied on merge
"""

import base64
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    Base, Account, Project, ProjectPullRequest, ProjectPRCampaign,
    Workflow, ProjectWorkflow,
)
from main import app
import campaign_rollback
from github_api_tracker import RateLimitExceeded
from workflows import get_db

TEST_USER = "rollbackuser"
TEST_PROJECT = "rollback_project"
REPO = "acme/api"
WORKFLOW_PATH = ".github/workflows/AM_RBK_ci.yml"

OLD_YAML = "name: ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
NEW_YAML = "name: ci\non: [push, pull_request]\njobs:\n  build:\n    runs-on: ubuntu-24.04\n"

BASE_SHA = "b" * 40
MERGE_SHA = "m" * 40
NEW_BLOB = "blobnew"
OLD_BLOB = "blobold"

client = TestClient(app)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine)


# --------------------------------------------------------------------------- #
# Fake GitHub                                                                 #
# --------------------------------------------------------------------------- #


def _response(status_code, payload=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


class FakeGitHub:
    """Routes reads by URL so the tests exercise the real request shapes.

    State is keyed by PR number and path rather than by repository — every test
    here that spans repos gives each one a distinct PR number, which is what
    separates them.
    """

    def __init__(self):
        self.pulls = {}      # pr_number -> pull payload
        self.commits = {}    # sha -> commit payload
        self.files = {}      # pr_number -> list of file entries
        self.contents = {}   # (path, ref) -> {"sha": ..., "text": ...} | None

    def add_merged_pr(self, pr_number, merge_sha=MERGE_SHA, base_sha=BASE_SHA):
        self.pulls[pr_number] = {"merged": True, "merge_commit_sha": merge_sha}
        self.commits[merge_sha] = {"parents": [{"sha": base_sha}]}

    def put_file(self, path, ref, sha, text):
        self.contents[(path, ref)] = {"sha": sha, "text": text}

    def delete_file(self, path, ref):
        self.contents[(path, ref)] = None

    def __call__(self, url, username, db, **kwargs):
        # ".../repos/{owner}/{name}/{tail}" -> tail
        tail = url.split("/repos/", 1)[-1].split("/", 2)[2]
        params = kwargs.get("params") or {}

        if tail.startswith("pulls/") and tail.endswith("/files"):
            number = int(tail.split("/")[1])
            if params.get("page", 1) > 1:
                return _response(200, [])
            return _response(200, self.files.get(number, []))

        if tail.startswith("pulls/"):
            number = int(tail.split("/")[1])
            payload = self.pulls.get(number)
            return _response(200, payload) if payload else _response(404, {})

        if tail.startswith("commits/"):
            sha = tail.split("/", 1)[1]
            payload = self.commits.get(sha)
            return _response(200, payload) if payload else _response(404, {})

        if tail.startswith("contents/"):
            path = tail.split("/", 1)[1]
            entry = self.contents.get((path, params.get("ref")), "missing")
            if entry == "missing" or entry is None:
                return _response(404, {})
            return _response(200, {
                "sha": entry["sha"],
                "encoding": "base64",
                "content": base64.b64encode(entry["text"].encode()).decode(),
            })

        raise AssertionError(f"unexpected GitHub call: {url}")


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _create_project(db):
    account = Account(github_user=TEST_USER, github_email="r@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_name=TEST_PROJECT, project_code="RBK", user_id=account.user_id,
        branch_option="default", reusable_workflows_enabled=False, pr_state="synced",
        use_prefix=True,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _add_workflow(db, project, name="ci", yaml_text=NEW_YAML, status="synced_with_github"):
    workflow = Workflow(
        workflow_name=name, workflow_yaml=yaml_text,
        reusable_workflow=False, workflow_status=status,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=workflow.workflow_id))
    db.commit()
    return workflow


def _add_campaign(db, project, name="Bump runners"):
    campaign = ProjectPRCampaign(
        project_id=project.project_id, created_by=TEST_USER, campaign_name=name,
        target_repos=json.dumps([REPO]),
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


def _add_pr(db, project, campaign, pr_number=42, state="merged", repo=REPO,
            workflow_names="ci", file_names=None):
    pr = ProjectPullRequest(
        project_id=project.project_id, campaign_id=campaign.campaign_id,
        repo_name=repo, pr_number=pr_number,
        pr_url=f"https://github.com/{repo}/pull/{pr_number}",
        pr_state=state, branch_name=f"actions-manager/rbk/api/abc-{pr_number}",
        target_branch="main", workflow_names=workflow_names,
        file_names=file_names,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return pr


def _github_with_simple_change(pr_number=42, entry_status="modified"):
    """A campaign PR that changed one workflow file from OLD_YAML to NEW_YAML."""
    gh = FakeGitHub()
    gh.add_merged_pr(pr_number)
    gh.files[pr_number] = [
        {"filename": WORKFLOW_PATH, "status": entry_status, "sha": NEW_BLOB}
    ]
    gh.put_file(WORKFLOW_PATH, "main", NEW_BLOB, NEW_YAML)
    gh.put_file(WORKFLOW_PATH, BASE_SHA, OLD_BLOB, OLD_YAML)
    return gh


def _preview(gh, campaign_id):
    with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
         patch("campaign_rollback.github_get", gh):
        return client.post("/api/campaign-rollback-preview", json={
            "github_user": TEST_USER,
            "project_name": TEST_PROJECT,
            "campaign_id": f"campaign-{campaign_id}",
        })


# --------------------------------------------------------------------------- #


class TestInverseDiff:
    def test_simple_workflow_change_inverts_to_pre_campaign_content(self, db_session):
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        response = _preview(_github_with_simple_change(), campaign.campaign_id)

        assert response.status_code == 200
        body = response.json()
        assert body["invertible_count"] == 1
        target = body["targets"][0]
        assert target["invertible"] is True
        assert target["reason"] is None
        assert target["repo_name"] == REPO
        assert target["target_branch"] == "main"
        assert target["files"] == [{
            "path": WORKFLOW_PATH,
            "action": "restore",
            "before": NEW_YAML,
            "after": OLD_YAML,
        }]

    def test_file_added_by_campaign_inverts_to_delete(self, db_session):
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        gh = _github_with_simple_change(entry_status="added")
        # The file did not exist before the campaign merged.
        gh.delete_file(WORKFLOW_PATH, BASE_SHA)

        body = _preview(gh, campaign.campaign_id).json()
        assert body["targets"][0]["files"] == [{
            "path": WORKFLOW_PATH,
            "action": "delete",
            "before": NEW_YAML,
            "after": "",
        }]

    def test_file_deleted_by_campaign_inverts_to_restore(self, db_session):
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        gh = FakeGitHub()
        gh.add_merged_pr(42)
        gh.files[42] = [{"filename": WORKFLOW_PATH, "status": "removed", "sha": OLD_BLOB}]
        gh.delete_file(WORKFLOW_PATH, "main")
        gh.put_file(WORKFLOW_PATH, BASE_SHA, OLD_BLOB, OLD_YAML)

        target = _preview(gh, campaign.campaign_id).json()["targets"][0]
        assert target["invertible"] is True
        assert target["files"] == [{
            "path": WORKFLOW_PATH, "action": "restore", "before": "", "after": OLD_YAML,
        }]


class TestNonInvertible:
    def test_file_changed_after_merge_flags_repo(self, db_session):
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        gh = _github_with_simple_change()
        # Someone edited the workflow on main after the campaign merged.
        gh.put_file(WORKFLOW_PATH, "main", "blobsomeoneelse", NEW_YAML + "# hand edit\n")

        body = _preview(gh, campaign.campaign_id).json()
        target = body["targets"][0]
        assert body["invertible_count"] == 0
        assert target["invertible"] is False
        assert WORKFLOW_PATH in target["reason"]
        assert "after this campaign merged" in target["reason"]
        # Flagged, not dropped: the repo is still reported.
        assert target["repo_name"] == REPO
        assert target["files"] == []

    def test_file_removed_after_merge_flags_repo(self, db_session):
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        gh = _github_with_simple_change()
        gh.delete_file(WORKFLOW_PATH, "main")

        target = _preview(gh, campaign.campaign_id).json()["targets"][0]
        assert target["invertible"] is False
        assert "was removed from main" in target["reason"]

    def test_unreadable_merge_commit_flags_repo(self, db_session):
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        gh = _github_with_simple_change()
        gh.commits.pop(MERGE_SHA)

        target = _preview(gh, campaign.campaign_id).json()["targets"][0]
        assert target["invertible"] is False
        assert "pre-campaign state is unknown" in target["reason"]

    def test_renamed_file_is_not_guessed_at(self, db_session):
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        gh = _github_with_simple_change(entry_status="renamed")

        target = _preview(gh, campaign.campaign_id).json()["targets"][0]
        assert target["invertible"] is False
        assert "not computed automatically" in target["reason"]

    def test_rate_limit_is_reported_as_429_not_a_crash(self, db_session):
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        def exhausted(*_args, **_kwargs):
            raise RateLimitExceeded("Limit resets at 2026-08-15T09:00:00Z")

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("campaign_rollback.github_get", exhausted):
            response = client.post("/api/campaign-rollback-preview", json={
                "github_user": TEST_USER, "project_name": TEST_PROJECT,
                "campaign_id": f"campaign-{campaign.campaign_id}",
            })

        assert response.status_code == 429
        assert "rate limit" in response.json()["detail"].lower()

    def test_a_read_only_member_cannot_open_a_rollback(self, db_session):
        """Opening revert PRs across a campaign's repos is a GitHub write, so
        being able to see the project is not enough."""
        project = _create_project(db_session)
        campaign = _add_campaign(db_session, project)
        _add_pr(db_session, project, campaign)

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("workflows._require_drift_editor",
                   side_effect=HTTPException(status_code=403, detail="Insufficient project role")):
            response = client.post("/api/campaign-rollback", json={
                "github_user": TEST_USER, "project_name": TEST_PROJECT,
                "campaign_id": f"campaign-{campaign.campaign_id}", "am_action": "keep",
            })

        assert response.status_code == 403

    def test_legacy_campaign_id_is_rejected(self, db_session):
        _create_project(db_session)
        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.post("/api/campaign-rollback-preview", json={
                "github_user": TEST_USER, "project_name": TEST_PROJECT,
                "campaign_id": "legacy-1-ci-main-2026-01-01",
            })
        assert response.status_code == 400
        assert "predates campaign tracking" in response.json()["detail"]


class TestRollbackCampaignCreation:
    def _create(self, gh, campaign_id, am_action="keep", protection=None):
        finalize = MagicMock(return_value={
            "status": "pr_created", "pr_number": 101,
            "pr_url": f"https://github.com/{REPO}/pull/101",
            "branch_name": "actions-manager/rbk/api/zzz-main",
            "pr_title": "[Actions Manager] Roll back RBK workflows",
            "pr_author": TEST_USER, "pr_body": "body",
            "workflows_committed": ["ci"],
            "custom_files_committed": [WORKFLOW_PATH],
        })
        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("campaign_rollback.github_get", gh), \
             patch("workflows._create_or_get_am_branch",
                   return_value=("actions-manager/rbk/api/zzz-main", True, None)), \
             patch("workflows._fetch_branch_protection",
                   return_value=protection or {"status": "none"}), \
             patch("workflows._commit_custom_files_to_branch",
                   return_value=([WORKFLOW_PATH], [])) as commit, \
             patch("workflows._finalize_pr_result", finalize):
            response = client.post("/api/campaign-rollback", json={
                "github_user": TEST_USER, "project_name": TEST_PROJECT,
                "campaign_id": f"campaign-{campaign_id}", "am_action": am_action,
            })
        return response, commit, finalize

    def test_links_to_source_and_records_the_am_choice(self, db_session):
        project = _create_project(db_session)
        source = _add_campaign(db_session, project)
        _add_pr(db_session, project, source)

        response, _commit, _finalize = self._create(
            _github_with_simple_change(), source.campaign_id, am_action="revert"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["prs_created"] == 1
        rollback = db_session.query(ProjectPRCampaign).filter(
            ProjectPRCampaign.campaign_id == body["campaign_id"]
        ).first()
        assert rollback.rollback_of_campaign_id == source.campaign_id
        assert rollback.rollback_am_action == "revert"
        assert rollback.campaign_name == "Rollback of Bump runners"

    def test_commits_the_pre_campaign_content(self, db_session):
        project = _create_project(db_session)
        source = _add_campaign(db_session, project)
        _add_pr(db_session, project, source)

        _response, commit, _finalize = self._create(
            _github_with_simple_change(), source.campaign_id
        )

        committed_files = commit.call_args[0][0]
        assert committed_files == [{
            "id": None, "file_path": WORKFLOW_PATH,
            "file_content": OLD_YAML, "pending_delete": False,
        }]

    def test_only_merged_repos_are_targeted(self, db_session):
        project = _create_project(db_session)
        source = _add_campaign(db_session, project)
        _add_pr(db_session, project, source, pr_number=42, state="merged")
        _add_pr(db_session, project, source, pr_number=43, state="open", repo="acme/web")
        _add_pr(db_session, project, source, pr_number=44, state="closed", repo="acme/cli")

        response, _commit, finalize = self._create(
            _github_with_simple_change(), source.campaign_id
        )

        assert response.status_code == 200
        assert finalize.call_count == 1
        assert list(response.json()["results"]) == [f"{REPO} on main"]

    def test_non_invertible_target_is_skipped_and_reported(self, db_session):
        project = _create_project(db_session)
        source = _add_campaign(db_session, project)
        _add_pr(db_session, project, source, pr_number=42)
        _add_pr(db_session, project, source, pr_number=43, repo="acme/web")

        gh = _github_with_simple_change()
        gh.add_merged_pr(43)
        gh.files[43] = [{"filename": WORKFLOW_PATH, "status": "modified", "sha": "stale"}]

        response, _commit, finalize = self._create(gh, source.campaign_id)

        body = response.json()
        assert finalize.call_count == 1
        assert len(body["skipped"]) == 1
        assert body["skipped"][0]["repo_name"] == "acme/web"
        assert "after this campaign merged" in body["skipped"][0]["reason"]

    def test_a_partly_committed_repo_opens_no_pr(self, db_session):
        """Three of four files restored is a half-revert — the same rule that
        makes a changed path non-invertible applies to delivery."""
        project = _create_project(db_session)
        source = _add_campaign(db_session, project)
        _add_pr(db_session, project, source)

        finalize = MagicMock()
        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("campaign_rollback.github_get", _github_with_simple_change()), \
             patch("workflows._create_or_get_am_branch",
                   return_value=("actions-manager/rbk/api/zzz-main", True, None)), \
             patch("workflows._fetch_branch_protection", return_value={"status": "none"}), \
             patch("workflows._commit_custom_files_to_branch",
                   return_value=([WORKFLOW_PATH], ["other.yml: HTTP 422"])), \
             patch("workflows._finalize_pr_result", finalize):
            response = client.post("/api/campaign-rollback", json={
                "github_user": TEST_USER, "project_name": TEST_PROJECT,
                "campaign_id": f"campaign-{source.campaign_id}", "am_action": "keep",
            })

        assert finalize.call_count == 0
        body = response.json()
        assert body["prs_created"] == 0
        assert body["campaign_id"] is None
        result = body["results"][f"{REPO} on main"]
        assert result["status"] == "error"
        assert result["custom_file_errors"] == ["other.yml: HTTP 422"]

    def test_delivery_failure_mid_run_still_records_the_prs_already_opened(self, db_session):
        """An untracked revert PR cannot be merged or closed from ActionsManager."""
        project = _create_project(db_session)
        source = _add_campaign(db_session, project)
        _add_pr(db_session, project, source, pr_number=42)
        _add_pr(db_session, project, source, pr_number=43, repo="acme/web")

        gh = _github_with_simple_change()
        gh.add_merged_pr(43)
        gh.files[43] = [{"filename": WORKFLOW_PATH, "status": "modified", "sha": NEW_BLOB}]

        # First repo delivers, second trips the rate limit.
        branches = [("actions-manager/rbk/api/zzz-main", True, None),
                    RateLimitExceeded("API rate limit exceeded. Limit resets at 2026-08-15T09:00:00Z")]

        def flaky_branch(*_args, **_kwargs):
            outcome = branches.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        finalize = MagicMock(return_value={
            "status": "pr_created", "pr_number": 101,
            "pr_url": f"https://github.com/{REPO}/pull/101",
            "branch_name": "actions-manager/rbk/api/zzz-main",
            "pr_title": "t", "pr_author": TEST_USER, "pr_body": "b",
            "workflows_committed": ["ci"], "custom_files_committed": [WORKFLOW_PATH],
        })
        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("campaign_rollback.github_get", gh), \
             patch("workflows._create_or_get_am_branch", flaky_branch), \
             patch("workflows._fetch_branch_protection", return_value={"status": "none"}), \
             patch("workflows._commit_custom_files_to_branch",
                   return_value=([WORKFLOW_PATH], [])), \
             patch("workflows._finalize_pr_result", finalize):
            response = client.post("/api/campaign-rollback", json={
                "github_user": TEST_USER, "project_name": TEST_PROJECT,
                "campaign_id": f"campaign-{source.campaign_id}", "am_action": "keep",
            })

        body = response.json()
        assert body["prs_created"] == 1
        assert body["campaign_id"] is not None
        assert "rate limit" in body["aborted"].lower()
        assert db_session.query(ProjectPullRequest).filter(
            ProjectPullRequest.campaign_id == body["campaign_id"]
        ).count() == 1

    def test_snapshot_records_branch_protection(self, db_session):
        """"none" and "unknown" mean different things, so a rollback must not
        record every target as unprotected by default."""
        project = _create_project(db_session)
        source = _add_campaign(db_session, project)
        _add_pr(db_session, project, source)

        protection = {"status": "protected", "required_reviews": 2}
        response, _commit, _finalize = self._create(
            _github_with_simple_change(), source.campaign_id, protection=protection
        )

        rollback = db_session.query(ProjectPRCampaign).filter(
            ProjectPRCampaign.campaign_id == response.json()["campaign_id"]
        ).first()
        assert json.loads(rollback.branch_protection) == {f"{REPO} on main": protection}

    def test_campaign_with_nothing_invertible_opens_no_prs(self, db_session):
        project = _create_project(db_session)
        source = _add_campaign(db_session, project)
        _add_pr(db_session, project, source)

        gh = _github_with_simple_change()
        gh.commits.pop(MERGE_SHA)

        response, _commit, finalize = self._create(gh, source.campaign_id)

        assert response.status_code == 400
        assert finalize.call_count == 0
        assert db_session.query(ProjectPRCampaign).filter(
            ProjectPRCampaign.rollback_of_campaign_id.isnot(None)
        ).count() == 0


class TestRollbackAmAction:
    def _rollback_pr(self, db, project, action, file_names=WORKFLOW_PATH):
        rollback = ProjectPRCampaign(
            project_id=project.project_id, created_by=TEST_USER,
            campaign_name="Rollback of Bump runners",
            rollback_of_campaign_id=None, rollback_am_action=action,
        )
        db.add(rollback)
        db.commit()
        db.refresh(rollback)
        return _add_pr(db, project, rollback, pr_number=101, state="merged",
                       file_names=file_names)

    def test_keep_marks_workflows_committed_locally(self, db_session):
        project = _create_project(db_session)
        workflow = _add_workflow(db_session, project)
        pr = self._rollback_pr(db_session, project, "keep")

        campaign_rollback.handle_rollback_pr_merged(db_session, pr, TEST_USER)

        db_session.refresh(workflow)
        assert workflow.workflow_status == "committed_locally"
        assert workflow.workflow_yaml == NEW_YAML

    def test_revert_adopts_the_github_content(self, db_session):
        project = _create_project(db_session)
        workflow = _add_workflow(db_session, project)
        pr = self._rollback_pr(db_session, project, "revert")

        gh = FakeGitHub()
        gh.put_file(WORKFLOW_PATH, "main", OLD_BLOB, OLD_YAML)

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("campaign_rollback.github_get", gh):
            campaign_rollback.handle_rollback_pr_merged(db_session, pr, TEST_USER)

        db_session.refresh(workflow)
        assert workflow.workflow_yaml == OLD_YAML
        assert workflow.workflow_git_hash == OLD_BLOB
        assert workflow.workflow_status == "synced_with_github"

    def test_revert_without_a_token_falls_back_to_keep(self, db_session):
        project = _create_project(db_session)
        workflow = _add_workflow(db_session, project)
        pr = self._rollback_pr(db_session, project, "revert")

        # The webhook path has no user token at all.
        with patch("workflows.user_tokens", {}):
            campaign_rollback.handle_rollback_pr_merged(db_session, pr, None)

        db_session.refresh(workflow)
        assert workflow.workflow_yaml == NEW_YAML
        assert workflow.workflow_status == "committed_locally"

    def test_revert_uses_the_delivered_path_not_the_current_prefix_setting(self, db_session):
        """use_prefix may have been flipped since the campaign shipped, so the
        adopt step reads the path the rollback actually committed."""
        project = _create_project(db_session)
        workflow = _add_workflow(db_session, project)
        # The campaign shipped without the prefix; prefix mode was enabled since.
        unprefixed = ".github/workflows/ci.yml"
        pr = self._rollback_pr(db_session, project, "revert", file_names=unprefixed)

        gh = FakeGitHub()
        gh.put_file(unprefixed, "main", OLD_BLOB, OLD_YAML)
        # Nothing lives at the path format_workflow_name() would derive today.

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("campaign_rollback.github_get", gh):
            campaign_rollback.handle_rollback_pr_merged(db_session, pr, TEST_USER)

        db_session.refresh(workflow)
        assert workflow.workflow_yaml == OLD_YAML
        assert workflow.workflow_status == "synced_with_github"

    def test_revert_of_a_deleted_file_is_not_called_synced(self, db_session):
        """The rollback removed the file the campaign added, so ActionsManager
        holds content GitHub does not."""
        project = _create_project(db_session)
        workflow = _add_workflow(db_session, project)
        pr = self._rollback_pr(db_session, project, "revert")

        gh = FakeGitHub()
        gh.delete_file(WORKFLOW_PATH, "main")

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("campaign_rollback.github_get", gh):
            campaign_rollback.handle_rollback_pr_merged(db_session, pr, TEST_USER)

        db_session.refresh(workflow)
        assert workflow.workflow_status == "committed_locally"
        assert workflow.workflow_yaml == NEW_YAML

    def test_ordinary_campaign_pr_is_untouched(self, db_session):
        project = _create_project(db_session)
        workflow = _add_workflow(db_session, project)
        campaign = _add_campaign(db_session, project)
        pr = _add_pr(db_session, project, campaign, pr_number=42)

        campaign_rollback.handle_rollback_pr_merged(db_session, pr, TEST_USER)

        db_session.refresh(workflow)
        assert workflow.workflow_status == "synced_with_github"
