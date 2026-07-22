"""
Regression tests for first-class PR campaign tracking.

Each PR campaign creation run must produce a NEW unique campaign record
(project_pr_campaigns) and attach the PR rows created during that run to it,
instead of appending new PRs to a previous campaign
(https://github.com/dawg-io/actions-manager/issues/1360).

Verifies:
- _save_prs_and_update_status creates a new campaign per run and links PR rows
- A second campaign run never regroups or modifies the first campaign's PRs
- "pr_updated" results (commits added to an existing open PR) keep their
  original campaign and do not leave empty campaign records behind
- /api/project-pr-campaigns groups PRs by campaign_id, so two runs with the
  same workflows/branch/day render as separate campaigns
- Campaign status is derived only from that campaign's PRs
- Legacy PR rows without a campaign_id still group heuristically
- Campaign created_by/created_at come from the campaign record
"""

import sys
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    Base, Account, Project, ProjectPullRequest, ProjectPRCampaign, Repo, ProjectRepo, Codeowners,
    LinkedReusableWorkflow, Workflow, ProjectWorkflow,
)
from main import app
from workflows import get_db, _save_prs_and_update_status

TEST_USER = "campaignuser"
TEST_PROJECT = "campaign_project"

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


def _create_account_and_project(db):
    account = Account(
        github_user=TEST_USER,
        github_email="campaign@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_name=TEST_PROJECT,
        project_code="CMP",
        user_id=account.user_id,
        branch_option="default",
        reusable_workflows_enabled=False,
        pr_state="synced",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return account, project


def _pr_result(pr_number, branch_name, status="pr_created"):
    return {
        "status": status,
        "pr_number": pr_number,
        "pr_url": f"https://github.com/org/repo/pull/{pr_number}",
        "branch_name": branch_name,
        "pr_title": f"Update workflows #{pr_number}",
        "pr_author": TEST_USER,
        "pr_body": "Automated workflow update",
    }


def _get_campaigns(github_user=TEST_USER, project_name=TEST_PROJECT):
    with patch("workflows.user_tokens", {github_user: "fake-token"}):
        return client.get(
            "/api/project-pr-campaigns",
            params={"github_user": github_user, "project_name": project_name},
        )


class TestCampaignRecordCreation:

    def test_first_run_creates_campaign_with_linked_prs(self, db_session):
        _, project = _create_account_and_project(db_session)
        results = {
            "org/repo-a on main": _pr_result(10, "actions-manager/cmp/a/111-main"),
            "org/repo-b on main": _pr_result(11, "actions-manager/cmp/b/222-main"),
        }

        pr_count, _ = _save_prs_and_update_status(
            results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
        )

        assert pr_count == 2
        campaigns = db_session.query(ProjectPRCampaign).all()
        assert len(campaigns) == 1
        assert campaigns[0].created_by == TEST_USER
        assert campaigns[0].project_id == project.project_id
        prs = db_session.query(ProjectPullRequest).all()
        assert len(prs) == 2
        assert all(pr.campaign_id == campaigns[0].campaign_id for pr in prs)

    def test_second_run_creates_new_campaign_and_does_not_regroup_first(self, db_session):
        _, project = _create_account_and_project(db_session)
        first_results = {
            "org/repo-a on main": _pr_result(10, "actions-manager/cmp/a/111-main"),
        }
        _save_prs_and_update_status(
            first_results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
        )
        campaign_a = db_session.query(ProjectPRCampaign).one()
        pr_a = db_session.query(ProjectPullRequest).one()
        original_campaign_a_id = pr_a.campaign_id

        # Simulate the first campaign's PR being merged
        pr_a.pr_state = "merged"
        pr_a.merged_at = datetime.now(timezone.utc)
        db_session.commit()

        second_results = {
            "org/repo-a on main": _pr_result(14, "actions-manager/cmp/a/333-main"),
            "org/repo-b on main": _pr_result(54, "actions-manager/cmp/b/444-main"),
        }
        _save_prs_and_update_status(
            second_results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
        )

        campaigns = db_session.query(ProjectPRCampaign).order_by(
            ProjectPRCampaign.campaign_id
        ).all()
        assert len(campaigns) == 2
        campaign_b = campaigns[1]
        assert campaign_b.campaign_id != campaign_a.campaign_id

        prs = db_session.query(ProjectPullRequest).order_by(
            ProjectPullRequest.pr_id
        ).all()
        assert len(prs) == 3
        # Campaign A's PR was not modified or regrouped
        assert prs[0].campaign_id == original_campaign_a_id
        assert prs[0].pr_state == "merged"
        # New PRs belong only to campaign B
        assert prs[1].campaign_id == campaign_b.campaign_id
        assert prs[2].campaign_id == campaign_b.campaign_id

    def test_pr_updated_rows_keep_original_campaign_and_no_empty_campaign_remains(self, db_session):
        _, project = _create_account_and_project(db_session)
        first_results = {
            "org/repo-a on main": _pr_result(10, "actions-manager/cmp/a/111-main"),
        }
        _save_prs_and_update_status(
            first_results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
        )
        campaign_a = db_session.query(ProjectPRCampaign).one()

        # Same branch gets new commits: the PR is updated, not recreated
        update_results = {
            "org/repo-a on main": _pr_result(
                10, "actions-manager/cmp/a/111-main", status="pr_updated"
            ),
        }
        _save_prs_and_update_status(
            update_results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
        )

        pr = db_session.query(ProjectPullRequest).one()
        assert pr.campaign_id == campaign_a.campaign_id
        # No empty campaign record was left behind
        assert db_session.query(ProjectPRCampaign).count() == 1

    def test_legacy_row_reopened_by_pr_updated_joins_new_campaign(self, db_session):
        _, project = _create_account_and_project(db_session)
        legacy_pr = ProjectPullRequest(
            project_id=project.project_id,
            campaign_id=None,
            repo_name="org/repo-a",
            pr_number=5,
            pr_url="https://github.com/org/repo-a/pull/5",
            pr_state="open",
            branch_name="actions-manager/cmp-main",
            target_branch="main",
        )
        db_session.add(legacy_pr)
        db_session.commit()

        results = {
            "org/repo-a on main": _pr_result(
                5, "actions-manager/cmp-main", status="pr_updated"
            ),
        }
        _save_prs_and_update_status(
            results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
        )

        campaign = db_session.query(ProjectPRCampaign).one()
        pr = db_session.query(ProjectPullRequest).one()
        assert pr.campaign_id == campaign.campaign_id


class TestCampaignEndpointGrouping:

    def _add_pr(self, db, project_id, *, pr_number, campaign_id, pr_state="open",
                workflow_names="wf222.yml", merged_at=None, closed_at=None):
        pr = ProjectPullRequest(
            project_id=project_id,
            campaign_id=campaign_id,
            repo_name="org/repo-a",
            pr_number=pr_number,
            pr_url=f"https://github.com/org/repo-a/pull/{pr_number}",
            pr_state=pr_state,
            branch_name=f"actions-manager/cmp/{pr_number}-main",
            target_branch="main",
            title=f"Update wf222 #{pr_number}",
            author=TEST_USER,
            workflow_names=workflow_names,
            merged_at=merged_at,
            closed_at=closed_at,
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)
        return pr

    def _add_campaign(self, db, project_id, created_by=TEST_USER):
        campaign = ProjectPRCampaign(project_id=project_id, created_by=created_by)
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign

    def test_two_campaigns_same_day_and_workflows_render_separately(self, db_session):
        """Regression: new PRs must not be appended to a prior campaign card."""
        _, project = _create_account_and_project(db_session)
        now = datetime.now(timezone.utc)
        campaign_a = self._add_campaign(db_session, project.project_id)
        campaign_b = self._add_campaign(db_session, project.project_id)
        self._add_pr(db_session, project.project_id, pr_number=11,
                     campaign_id=campaign_a.campaign_id, pr_state="merged", merged_at=now)
        self._add_pr(db_session, project.project_id, pr_number=51,
                     campaign_id=campaign_a.campaign_id, pr_state="merged", merged_at=now)
        self._add_pr(db_session, project.project_id, pr_number=14,
                     campaign_id=campaign_b.campaign_id, pr_state="open")
        self._add_pr(db_session, project.project_id, pr_number=54,
                     campaign_id=campaign_b.campaign_id, pr_state="open")

        response = _get_campaigns()

        assert response.status_code == 200
        data = response.json()
        assert data["total_campaigns"] == 2
        assert data["active_campaigns"] == 1
        assert data["completed_campaigns"] == 1

        by_id = {campaign["campaign_id"]: campaign for campaign in data["campaigns"]}
        campaign_a_resp = by_id[f"campaign-{campaign_a.campaign_id}"]
        campaign_b_resp = by_id[f"campaign-{campaign_b.campaign_id}"]

        # Status derived only from each campaign's own PRs
        assert campaign_a_resp["campaign_status"] == "completed"
        assert campaign_a_resp["merged_count"] == 2
        assert campaign_a_resp["open_count"] == 0
        assert campaign_b_resp["campaign_status"] == "open"
        assert campaign_b_resp["open_count"] == 2
        assert campaign_b_resp["merged_count"] == 0

        # Older merged PRs are not displayed inside the new campaign
        campaign_b_numbers = {pr["pr_number"] for pr in campaign_b_resp["pull_requests"]}
        assert campaign_b_numbers == {14, 54}
        campaign_a_numbers = {pr["pr_number"] for pr in campaign_a_resp["pull_requests"]}
        assert campaign_a_numbers == {11, 51}

    def test_campaign_created_by_comes_from_campaign_record(self, db_session):
        _, project = _create_account_and_project(db_session)
        campaign = self._add_campaign(db_session, project.project_id, created_by="opener-user")
        self._add_pr(db_session, project.project_id, pr_number=14,
                     campaign_id=campaign.campaign_id)

        response = _get_campaigns()

        assert response.status_code == 200
        data = response.json()
        assert data["campaigns"][0]["created_by"] == "opener-user"

    def test_legacy_prs_without_campaign_id_still_grouped(self, db_session):
        _, project = _create_account_and_project(db_session)
        now = datetime.now(timezone.utc)
        # Legacy rows (no campaign) plus one tracked campaign
        self._add_pr(db_session, project.project_id, pr_number=1,
                     campaign_id=None, pr_state="merged", merged_at=now,
                     workflow_names="legacy.yml")
        self._add_pr(db_session, project.project_id, pr_number=2,
                     campaign_id=None, pr_state="merged", merged_at=now,
                     workflow_names="legacy.yml")
        campaign = self._add_campaign(db_session, project.project_id)
        self._add_pr(db_session, project.project_id, pr_number=14,
                     campaign_id=campaign.campaign_id)

        response = _get_campaigns()

        assert response.status_code == 200
        data = response.json()
        assert data["total_campaigns"] == 2
        legacy = next(
            campaign_resp for campaign_resp in data["campaigns"]
            if campaign_resp["campaign_id"] != f"campaign-{campaign.campaign_id}"
        )
        # Legacy NULL-campaign rows are isolated under a distinct "legacy-" id
        assert legacy["campaign_id"].startswith("legacy-")
        assert legacy["merged_count"] == 2
        assert legacy["campaign_status"] == "completed"
        tracked = next(
            campaign_resp for campaign_resp in data["campaigns"]
            if campaign_resp["campaign_id"] == f"campaign-{campaign.campaign_id}"
        )
        assert {pr["pr_number"] for pr in tracked["pull_requests"]} == {14}

    def test_unauthenticated_user_is_rejected(self, db_session):
        _create_account_and_project(db_session)

        with patch("workflows.user_tokens", {}):
            response = client.get(
                "/api/project-pr-campaigns",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )

        assert response.status_code == 401

    def test_merged_campaign_then_new_run_same_day_renders_two_campaigns(self, db_session):
        """End-to-end regression for the reported failure: create campaign A,
        merge its PRs, then create campaign B with the same workflows and target
        branch on the same day. The API must return two separate campaigns and
        campaign B must not include campaign A's merged PRs."""
        _, project = _create_account_and_project(db_session)

        first_results = {
            "whatsupdawg/test1 on main": _pr_result(56, "actions-manager/cmp/test1/aaa-main"),
            "whatsupdawg/test2 on main": _pr_result(57, "actions-manager/cmp/test2/bbb-main"),
        }
        _save_prs_and_update_status(
            first_results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
        )
        campaign_a = db_session.query(ProjectPRCampaign).one()
        now = datetime.now(timezone.utc)
        for pr in db_session.query(ProjectPullRequest).all():
            pr.pr_state = "merged"
            pr.merged_at = now
        db_session.commit()

        second_results = {
            "whatsupdawg/test1 on main": _pr_result(57, "actions-manager/cmp/test1/ccc-main"),
            "whatsupdawg/test2 on main": _pr_result(58, "actions-manager/cmp/test2/ddd-main"),
        }
        _save_prs_and_update_status(
            second_results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
        )
        campaign_b = db_session.query(ProjectPRCampaign).filter(
            ProjectPRCampaign.campaign_id != campaign_a.campaign_id
        ).one()

        # Every new PR row must carry the new campaign id — never NULL
        assert all(
            pr.campaign_id is not None
            for pr in db_session.query(ProjectPullRequest).all()
        )

        response = _get_campaigns()
        assert response.status_code == 200
        data = response.json()
        assert data["total_campaigns"] == 2

        by_id = {campaign["campaign_id"]: campaign for campaign in data["campaigns"]}
        campaign_a_resp = by_id[f"campaign-{campaign_a.campaign_id}"]
        campaign_b_resp = by_id[f"campaign-{campaign_b.campaign_id}"]

        a_prs = {(pr["repo_name"], pr["pr_number"]) for pr in campaign_a_resp["pull_requests"]}
        b_prs = {(pr["repo_name"], pr["pr_number"]) for pr in campaign_b_resp["pull_requests"]}
        assert a_prs == {("whatsupdawg/test1", 56), ("whatsupdawg/test2", 57)}
        assert b_prs == {("whatsupdawg/test1", 57), ("whatsupdawg/test2", 58)}
        assert campaign_a_resp["campaign_status"] == "completed"
        assert campaign_b_resp["campaign_status"] == "open"
        assert campaign_b_resp["merged_count"] == 0


class TestCodeownersMergedIntoRepoPR:
    """
    CODEOWNERS must join the same per-repo PR as workflows/custom files
    instead of opening a second PR for a repo already getting one (PR #1506).
    """

    def _add_repo(self, db, project, repo_name):
        repo = Repo(repo_name=repo_name)
        db.add(repo)
        db.commit()
        db.refresh(repo)
        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
        db.commit()
        return repo

    def test_build_codeowners_for_delivery_only_includes_repos_in_scope(self, db_session):
        from workflows import _build_codeowners_for_delivery, CreatePullRequestsRequest
        db = db_session
        _, project = _create_account_and_project(db)
        repo_a = self._add_repo(db, project, "whatsupdawg/repo-a")
        repo_b = self._add_repo(db, project, "whatsupdawg/repo-b")
        db.add(Codeowners(project_id=project.project_id, repo_id=repo_a.repo_id, content="* @a"))
        db.add(Codeowners(project_id=project.project_id, repo_id=repo_b.repo_id, content="* @b"))
        db.commit()

        payload = CreatePullRequestsRequest(
            project_name=TEST_PROJECT,
            selected_codeowners_repos=["whatsupdawg/repo-a", "whatsupdawg/repo-b"],
        )
        # repo-b is deselected from the caller-repo scope for this run, so it
        # must be left for the standalone CODEOWNERS-only deploy path.
        result = _build_codeowners_for_delivery(project, payload, ["whatsupdawg/repo-a"], db)

        assert set(result.keys()) == {"whatsupdawg/repo-a"}
        assert result["whatsupdawg/repo-a"]["content"] == "* @a"
        assert result["whatsupdawg/repo-a"]["repo_id"] == repo_a.repo_id

    def test_build_codeowners_for_delivery_empty_when_none_selected(self, db_session):
        from workflows import _build_codeowners_for_delivery, CreatePullRequestsRequest
        db = db_session
        _, project = _create_account_and_project(db)
        payload = CreatePullRequestsRequest(project_name=TEST_PROJECT)
        assert _build_codeowners_for_delivery(project, payload, ["whatsupdawg/repo-a"], db) == {}

    def test_codeowners_merged_repos_only_counts_successful_merges(self):
        from workflows import _codeowners_merged_repos
        results = {
            "whatsupdawg/repo-a on main": {"status": "pr_created", "codeowners_committed": True},
            "whatsupdawg/repo-b on main": {"status": "pr_updated", "codeowners_committed": False},
            "whatsupdawg/repo-c on main": {"status": "error", "codeowners_committed": True},
        }
        assert _codeowners_merged_repos(results) == ["whatsupdawg/repo-a"]

    def test_codeowners_only_repo_still_gets_one_pr_on_shared_branch(self, db_session):
        """A repo with CODEOWNERS as its only selected change (but still in the
        caller-repo scope) must land on the same AM branch/PR the regular
        workflow path would create — not a second, CODEOWNERS-only branch."""
        from unittest.mock import MagicMock
        from workflows import _process_regular_workflows_update

        db = db_session
        _, project = _create_account_and_project(db)
        repo = self._add_repo(db, project, "whatsupdawg/repo-a")
        db.add(Codeowners(project_id=project.project_id, repo_id=repo.repo_id, content="* @a"))
        db.commit()

        codeowners_files = {
            "whatsupdawg/repo-a": {
                "file_path": ".github/CODEOWNERS",
                "content": "* @a",
                "repo_id": repo.repo_id,
                "project_id": project.project_id,
            }
        }

        not_found = MagicMock()
        not_found.status_code = 404
        put_ok = MagicMock()
        put_ok.status_code = 201
        put_ok.json.return_value = {"content": {"sha": "newsha"}}
        new_pr = {
            "number": 42, "html_url": "https://github.com/whatsupdawg/repo-a/pull/42",
            "title": "t", "user": {"login": TEST_USER}, "body": "b",
        }

        with patch("workflows._resolve_branches_for_repo", return_value=["main"]), \
             patch("workflows._create_or_get_am_branch", return_value=("actions-manager/cmp-main", True, None)), \
             patch("workflows.github_get", return_value=not_found), \
             patch("workflows.requests.put", return_value=put_ok), \
             patch("workflows._check_existing_pr", return_value=None), \
             patch("workflows._create_pull_request", return_value=new_pr):
            results = _process_regular_workflows_update(
                repo_names=["whatsupdawg/repo-a"],
                workflows=[],
                project_code="CMP",
                branch_option="default",
                regex_pattern="",
                branch_max_age_days=30,
                headers={},
                db=db,
                user=TEST_USER,
                project=project,
                codeowners_files=codeowners_files,
            )

        key = "whatsupdawg/repo-a on main"
        assert results[key]["status"] == "pr_created"
        assert results[key]["codeowners_committed"] == ".github/CODEOWNERS"

        record = db.query(Codeowners).filter_by(repo_id=repo.repo_id).first()
        assert record.status == "under_review"
        assert record.git_hash == "newsha"


class TestSchemaSafety:

    def test_missing_campaign_column_raises_backend_error(self, db_session):
        """If the campaign migration has not been applied to the runtime
        database, saving a new PR must raise a loud backend error instead of
        silently writing rows that fall back to heuristic grouping."""
        from fastapi import HTTPException
        from sqlalchemy import text

        _, project = _create_account_and_project(db_session)
        # Recreate the table in its pre-migration shape (no campaign_id column)
        db_session.execute(text("DROP TABLE project_pull_requests"))
        db_session.execute(text(
            "CREATE TABLE project_pull_requests ("
            "pr_id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, "
            "repo_name VARCHAR(255) NOT NULL, pr_number INTEGER NOT NULL, "
            "pr_url VARCHAR(500) NOT NULL, pr_state VARCHAR(20) NOT NULL, "
            "branch_name VARCHAR(255) NOT NULL, target_branch VARCHAR(255) NOT NULL, "
            "title VARCHAR(500), author VARCHAR(255), body TEXT, "
            "merged_at TIMESTAMP, closed_at TIMESTAMP, workflow_names TEXT, "
            "created_at TIMESTAMP, updated_at TIMESTAMP)"
        ))
        db_session.commit()

        results = {"org/repo-a on main": _pr_result(10, "actions-manager/cmp/a/111-main")}
        with pytest.raises(HTTPException) as exc_info:
            _save_prs_and_update_status(
                results, project, ["wf222.yml"], [], db_session, github_user=TEST_USER
            )
        assert exc_info.value.status_code == 500
        assert "could not be recorded" in exc_info.value.detail

    def test_sqlite_migration_adds_column_to_runtime_database(self, tmp_path, monkeypatch):
        """The SQLite migration must target the application's resolved database
        (e.g. /app/data/actions_manager.db in self-hosted mode), not a
        hard-coded file next to the migration script."""
        import sqlite3
        import migrate_add_pr_campaigns as migration

        db_file = tmp_path / "actions_manager.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE projects (project_id INTEGER PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE project_pull_requests ("
            "pr_id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, "
            "repo_name VARCHAR(255) NOT NULL, pr_number INTEGER NOT NULL, "
            "pr_url VARCHAR(500) NOT NULL, pr_state VARCHAR(50), "
            "branch_name VARCHAR(255), target_branch VARCHAR(255))"
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(migration, "APP_DATABASE_URL", f"sqlite:///{db_file}")
        migration.run_sqlite_migration()

        conn = sqlite3.connect(str(db_file))
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(project_pull_requests)")}
            assert "campaign_id" in columns
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert "project_pr_campaigns" in tables
            # Idempotent: running again must not fail
            migration.run_sqlite_migration()
        finally:
            conn.close()

    def test_other_user_cannot_access_campaigns(self, db_session):
        _create_account_and_project(db_session)
        other = Account(
            github_user="intruder",
            github_email="intruder@example.com",
            account_type="free",
        )
        db_session.add(other)
        db_session.commit()

        response = _get_campaigns(github_user="intruder")

        assert response.status_code == 404


class TestPerPRWorkflowNames:
    """Regression tests for per-PR workflow_names scoping (issue #1508).

    Each PR row must record only the workflows actually committed to that
    specific repo/branch, not the union of all workflows selected across the
    entire PR-creation run.
    """

    def test_per_pr_workflow_names_uses_workflows_committed_not_all_selected(self, db_session):
        """Caller workflows must not bleed onto the RWX repo's PR record."""
        _, project = _create_account_and_project(db_session)

        # Simulate a run that includes two caller-repo PRs (regular workflows)
        # and one RWX-repo PR (reusable workflow only).
        caller_wf1 = "wwff11.yml"
        caller_wf2 = "test.yml"
        rwx_wf = "rwx1.yml"

        results = {
            "org/caller-repo-a on main": {
                "status": "pr_created",
                "pr_number": 10,
                "pr_url": "https://github.com/org/caller-repo-a/pull/10",
                "branch_name": "actions-manager/cmp/a/111-main",
                "pr_title": "Update workflows",
                "pr_author": TEST_USER,
                "pr_body": "body",
                "workflows_committed": [caller_wf1, caller_wf2],
            },
            "org/rwx-repo on main": {
                "status": "pr_created",
                "pr_number": 50,
                "pr_url": "https://github.com/org/rwx-repo/pull/50",
                "branch_name": "actions-manager/cmp/rwx/2ce531e-main",
                "pr_title": "Update reusable workflow",
                "pr_author": TEST_USER,
                "pr_body": "body",
                "workflows_committed": [rwx_wf],
            },
        }

        _save_prs_and_update_status(
            results,
            project,
            [caller_wf1, caller_wf2],
            [rwx_wf],
            db_session,
            github_user=TEST_USER,
        )

        prs = {
            pr.repo_name: pr
            for pr in db_session.query(ProjectPullRequest).all()
        }

        # Caller repo PR must list only its own workflows
        caller_pr = prs["org/caller-repo-a"]
        assert caller_pr.workflow_names == f"{caller_wf1}, {caller_wf2}"

        # RWX repo PR must list only the reusable workflow — not the caller workflows
        rwx_pr = prs["org/rwx-repo"]
        assert rwx_pr.workflow_names == rwx_wf
        assert caller_wf1 not in (rwx_pr.workflow_names or "")
        assert caller_wf2 not in (rwx_pr.workflow_names or "")

    def test_custom_file_only_pr_has_null_workflow_names(self, db_session):
        """A PR that commits only custom files (no workflows) must have
        workflow_names=None so the UI renders 'No workflows recorded'."""
        _, project = _create_account_and_project(db_session)

        results = {
            "org/repo-a on main": {
                "status": "pr_created",
                "pr_number": 20,
                "pr_url": "https://github.com/org/repo-a/pull/20",
                "branch_name": "actions-manager/cmp/a/111-main",
                "pr_title": "Add custom file",
                "pr_author": TEST_USER,
                "pr_body": "body",
                "workflows_committed": [],
            },
        }

        _save_prs_and_update_status(
            results, project, [], [], db_session, github_user=TEST_USER
        )

        pr = db_session.query(ProjectPullRequest).one()
        assert pr.workflow_names is None


class TestPerPRFileNames:
    """Regression tests for per-PR file_names storage (custom files + CODEOWNERS).

    Each PR row must record only the custom files and CODEOWNERS paths actually
    committed to that specific repo/branch — not files from other repos in the run.
    """

    def test_custom_files_stored_per_pr(self, db_session):
        """custom_files_committed paths must be recorded in file_names on the PR row."""
        _, project = _create_account_and_project(db_session)

        results = {
            "org/repo-a on main": {
                "status": "pr_created",
                "pr_number": 10,
                "pr_url": "https://github.com/org/repo-a/pull/10",
                "branch_name": "actions-manager/cmp/a/111-main",
                "pr_title": "Deploy files",
                "pr_author": TEST_USER,
                "pr_body": "body",
                "workflows_committed": ["deploy.yml"],
                "custom_files_committed": [".github/myfiles/test.txt", ".github/scripts/run.sh"],
                "codeowners_committed": "",
            },
        }

        _save_prs_and_update_status(results, project, ["deploy.yml"], [], db_session, github_user=TEST_USER)

        pr = db_session.query(ProjectPullRequest).one()
        assert pr.file_names == ".github/myfiles/test.txt, .github/scripts/run.sh"

    def test_codeowners_path_stored_per_pr(self, db_session):
        """codeowners_committed path must be appended to file_names on the PR row."""
        _, project = _create_account_and_project(db_session)

        results = {
            "org/repo-b on main": {
                "status": "pr_created",
                "pr_number": 20,
                "pr_url": "https://github.com/org/repo-b/pull/20",
                "branch_name": "actions-manager/cmp/b/111-main",
                "pr_title": "Add CODEOWNERS",
                "pr_author": TEST_USER,
                "pr_body": "body",
                "workflows_committed": ["ci.yml"],
                "custom_files_committed": [],
                "codeowners_committed": ".github/CODEOWNERS",
            },
        }

        _save_prs_and_update_status(results, project, ["ci.yml"], [], db_session, github_user=TEST_USER)

        pr = db_session.query(ProjectPullRequest).one()
        assert pr.file_names == ".github/CODEOWNERS"

    def test_mixed_workflows_custom_files_codeowners_per_pr(self, db_session):
        """All three file types are stored correctly and scoped per repo."""
        _, project = _create_account_and_project(db_session)

        results = {
            "org/repo-a on main": {
                "status": "pr_created",
                "pr_number": 30,
                "pr_url": "https://github.com/org/repo-a/pull/30",
                "branch_name": "actions-manager/cmp/a/111-main",
                "pr_title": "Mixed PR",
                "pr_author": TEST_USER,
                "pr_body": "body",
                "workflows_committed": ["build.yml"],
                "custom_files_committed": [".github/scripts/setup.sh"],
                "codeowners_committed": ".github/CODEOWNERS",
            },
            "org/repo-b on main": {
                "status": "pr_created",
                "pr_number": 31,
                "pr_url": "https://github.com/org/repo-b/pull/31",
                "branch_name": "actions-manager/cmp/b/111-main",
                "pr_title": "Workflow only PR",
                "pr_author": TEST_USER,
                "pr_body": "body",
                "workflows_committed": ["build.yml"],
                "custom_files_committed": [],
                "codeowners_committed": "",
            },
        }

        _save_prs_and_update_status(results, project, ["build.yml"], [], db_session, github_user=TEST_USER)

        prs = {pr.repo_name: pr for pr in db_session.query(ProjectPullRequest).all()}

        # repo-a gets both custom file and CODEOWNERS in file_names
        assert prs["org/repo-a"].file_names == ".github/scripts/setup.sh, .github/CODEOWNERS"
        # repo-b has no custom files or CODEOWNERS
        assert prs["org/repo-b"].file_names is None

    def test_no_custom_files_or_codeowners_gives_null_file_names(self, db_session):
        """A PR with only workflow commits must have file_names=None."""
        _, project = _create_account_and_project(db_session)

        results = {
            "org/repo-a on main": {
                "status": "pr_created",
                "pr_number": 40,
                "pr_url": "https://github.com/org/repo-a/pull/40",
                "branch_name": "actions-manager/cmp/a/111-main",
                "pr_title": "Workflow only",
                "pr_author": TEST_USER,
                "pr_body": "body",
                "workflows_committed": ["release.yml"],
                "custom_files_committed": [],
                "codeowners_committed": "",
            },
        }

        _save_prs_and_update_status(results, project, ["release.yml"], [], db_session, github_user=TEST_USER)

        pr = db_session.query(ProjectPullRequest).one()
        assert pr.file_names is None


class TestReusableWorkflowPRHighlighting:
    """
    /api/project-pr-campaigns must mark PR rows as ``is_reusable_workflow_pr``
    when the committed workflow is a linked reusable workflow, so the frontend
    can render the row purple — regardless of whether the PR happens to also
    carry a ``source_project_name`` (https://github.com/dawg-io/actions-manager
    PR feedback: the row stayed blue for real reusable-workflow PRs).

    A reusable workflow rollout to a caller ("standard") project creates its PR
    row with ``project_id`` set to the *caller* project, not the RWX project —
    so ``is_reusable_workflow_pr`` cannot be derived from ``pr.project_id``
    alone. It must be derived from whether the PR's committed workflow name
    matches a workflow actually linked via ``LinkedReusableWorkflow``.
    """

    def _create_linked_setup(self, db):
        account = Account(
            github_user=TEST_USER,
            github_email="campaign@example.com",
            account_type="free",
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        std_proj = Project(
            project_name=TEST_PROJECT,
            project_code="CMP",
            user_id=account.user_id,
            branch_option="default",
            reusable_workflows_enabled=True,
            pr_state="synced",
            project_type="standard",
        )
        db.add(std_proj)
        db.commit()
        db.refresh(std_proj)

        rwx_proj = Project(
            project_name="rwx_source_project",
            project_code="RWX",
            user_id=account.user_id,
            branch_option="default",
            reusable_workflows_enabled=True,
            pr_state="synced",
            project_type="rwx",
        )
        db.add(rwx_proj)
        db.commit()
        db.refresh(rwx_proj)

        wf = Workflow(
            workflow_name="reusable",
            workflow_yaml="name: reusable",
            reusable_workflow=True,
        )
        db.add(wf)
        db.commit()
        db.refresh(wf)
        db.add(ProjectWorkflow(project_id=rwx_proj.project_id, workflow_id=wf.workflow_id))
        db.add(LinkedReusableWorkflow(
            standard_project_id=std_proj.project_id,
            rwx_project_id=rwx_proj.project_id,
            workflow_id=wf.workflow_id,
        ))
        db.commit()

        return std_proj, rwx_proj

    def test_reusable_workflow_pr_committed_on_caller_project_is_flagged(self, db_session):
        """A reusable-workflow rollout PR row lives on the caller project_id
        (not the RWX project) but must still be flagged as reusable."""
        std_proj, _ = self._create_linked_setup(db_session)

        results = {
            "org/repo-a on main": _pr_result(50, "actions-manager/cmp/a/rwx-main"),
        }
        results["org/repo-a on main"]["workflows_committed"] = ["AM_RWX_reusable.yml"]

        _save_prs_and_update_status(
            results, std_proj, [], ["reusable.yml"], db_session, github_user=TEST_USER
        )

        response = _get_campaigns()
        assert response.status_code == 200
        prs = response.json()["pull_requests"]
        assert len(prs) == 1
        assert prs[0]["is_reusable_workflow_pr"] is True

    def test_regular_caller_workflow_pr_is_not_flagged(self, db_session):
        """A PR for the caller's own (non-reusable) workflow stays unflagged/blue."""
        std_proj, _ = self._create_linked_setup(db_session)

        results = {
            "org/repo-a on main": _pr_result(51, "actions-manager/cmp/a/build-main"),
        }
        results["org/repo-a on main"]["workflows_committed"] = ["build.yml"]

        _save_prs_and_update_status(
            results, std_proj, ["build.yml"], [], db_session, github_user=TEST_USER
        )

        response = _get_campaigns()
        assert response.status_code == 200
        prs = response.json()["pull_requests"]
        assert len(prs) == 1
        assert prs[0]["is_reusable_workflow_pr"] is False
