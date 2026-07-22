"""
Tests for the GET /api/project-pr-history endpoint.

Verifies:
- Returns only merged/closed PRs (open PRs are excluded)
- state_filter param works for "merged", "closed", and "all"
- repo_filter narrows results to the specified repo
- workflow_filter narrows results to rows containing the substring
- Correct counts (total, merged_count, closed_count) in the response
- Unauthenticated requests are rejected with 401
- Requests for non-existent projects are rejected with 404
- Empty history returns an empty list with an appropriate message in the payload
- Cross-project visibility: Standard project shows PRs from linked RWX project
- Cross-project visibility: RWX project shows PRs from linked Standard project
- source_project_name is set for cross-linked PRs and None for direct PRs
"""

import sys
import os
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import Base, Account, Project, ProjectPullRequest, LinkedReusableWorkflow, Workflow, ProjectWorkflow
from main import app
from workflows import get_db

# ---------------------------------------------------------------------------
# In-memory test database
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_pr_history.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# TestClient is created once; dependency override is applied/removed per test.
client = TestClient(app)

TEST_USER = "historyuser"
TEST_PROJECT = "history_project"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_account_and_project(db):
    account = Account(
        github_user=TEST_USER,
        github_email="history@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    project = Project(
        project_name=TEST_PROJECT,
        project_code="HPS",
        user_id=account.user_id,
        branch_option="default",
        reusable_workflows_enabled=False,
        pr_state="synced",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return account, project


def _add_pr(db, project_id, *, repo_name, pr_number, pr_state, title=None,
            author=None, workflow_names=None, merged_at=None, closed_at=None):
    # Use pr_number in the branch name to ensure uniqueness per-PR in tests
    pr = ProjectPullRequest(
        project_id=project_id,
        repo_name=repo_name,
        pr_number=pr_number,
        pr_url=f"https://github.com/{repo_name}/pull/{pr_number}",
        pr_state=pr_state,
        branch_name=f"actions-manager/hps-main-{pr_number}",
        target_branch="main",
        title=title,
        author=author,
        workflow_names=workflow_names,
        merged_at=merged_at,
        closed_at=closed_at,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return pr


def _add_workflow(db, project_id, *, name="campaign.yml", status="under_review"):
    workflow = Workflow(
        workflow_name=name,
        workflow_yaml="name: Campaign\non: push",
        reusable_workflow=False,
        workflow_status=status,
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    db.add(ProjectWorkflow(project_id=project_id, workflow_id=workflow.workflow_id))
    db.commit()
    return workflow


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPRHistory:

    @pytest.fixture(autouse=True)
    def setup_db(self):
        # Apply the test DB override for this class's tests only, then clean up.
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    # ------------------------------------------------------------------
    # Authentication / authorisation
    # ------------------------------------------------------------------

    def test_unauthenticated_request_rejected(self):
        """Requests without a valid session token return 401."""
        response = client.get(
            "/api/project-pr-history",
            params={"github_user": "nobody", "project_name": "x"},
        )
        assert response.status_code == 401

    def test_unknown_project_returns_404(self):
        _, _ = _create_account_and_project(self.db)
        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": "nonexistent"},
            )
        assert response.status_code == 404

    # ------------------------------------------------------------------
    # Basic filtering: open PRs are excluded
    # ------------------------------------------------------------------

    def test_open_prs_excluded(self):
        _, project = _create_account_and_project(self.db)
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=1, pr_state="open")
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=2, pr_state="merged",
                merged_at=datetime.now(timezone.utc))

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.status_code == 200
        data = response.json()
        # Only the merged PR should appear
        assert data["total"] == 1
        assert data["pull_requests"][0]["pr_number"] == 2
        assert data["pull_requests"][0]["pr_state"] == "merged"

    # ------------------------------------------------------------------
    # Empty history
    # ------------------------------------------------------------------

    def test_empty_history(self):
        _, _ = _create_account_and_project(self.db)
        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["merged_count"] == 0
        assert data["closed_count"] == 0
        assert data["pull_requests"] == []

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------

    def test_counts_are_correct(self):
        _, project = _create_account_and_project(self.db)
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=1, pr_state="merged",
                merged_at=datetime.now(timezone.utc))
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=2, pr_state="merged",
                merged_at=datetime.now(timezone.utc))
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=3, pr_state="closed",
                closed_at=datetime.now(timezone.utc))

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["merged_count"] == 2
        assert data["closed_count"] == 1

    # ------------------------------------------------------------------
    # state_filter
    # ------------------------------------------------------------------

    def test_state_filter_merged(self):
        _, project = _create_account_and_project(self.db)
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=1, pr_state="merged",
                merged_at=datetime.now(timezone.utc))
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=2, pr_state="closed",
                closed_at=datetime.now(timezone.utc))

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT, "state_filter": "merged"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["pull_requests"][0]["pr_state"] == "merged"

    def test_state_filter_closed(self):
        _, project = _create_account_and_project(self.db)
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=1, pr_state="merged",
                merged_at=datetime.now(timezone.utc))
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=2, pr_state="closed",
                closed_at=datetime.now(timezone.utc))

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT, "state_filter": "closed"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["pull_requests"][0]["pr_state"] == "closed"

    def test_state_filter_all(self):
        _, project = _create_account_and_project(self.db)
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=1, pr_state="merged",
                merged_at=datetime.now(timezone.utc))
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=2, pr_state="closed",
                closed_at=datetime.now(timezone.utc))

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT, "state_filter": "all"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    # ------------------------------------------------------------------
    # repo_filter
    # ------------------------------------------------------------------

    def test_repo_filter(self):
        _, project = _create_account_and_project(self.db)
        _add_pr(self.db, project.project_id, repo_name="org/repo-a", pr_number=1, pr_state="merged",
                merged_at=datetime.now(timezone.utc))
        _add_pr(self.db, project.project_id, repo_name="org/repo-b", pr_number=2, pr_state="merged",
                merged_at=datetime.now(timezone.utc))

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT, "repo_filter": "org/repo-a"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["pull_requests"][0]["repo_name"] == "org/repo-a"

    # ------------------------------------------------------------------
    # workflow_filter
    # ------------------------------------------------------------------

    def test_workflow_filter(self):
        _, project = _create_account_and_project(self.db)
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=1, pr_state="merged",
                workflow_names="ci.yml, deploy.yml", merged_at=datetime.now(timezone.utc))
        _add_pr(self.db, project.project_id, repo_name="org/repo", pr_number=2, pr_state="merged",
                workflow_names="release.yml", merged_at=datetime.now(timezone.utc))

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT, "workflow_filter": "ci.yml"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "ci.yml" in data["pull_requests"][0]["workflow_names"]

    # ------------------------------------------------------------------
    # Response fields
    # ------------------------------------------------------------------

    def test_response_includes_extended_fields(self):
        _, project = _create_account_and_project(self.db)
        merged_ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        _add_pr(
            self.db, project.project_id,
            repo_name="org/repo", pr_number=10, pr_state="merged",
            title="[Actions Manager] Update HPS workflows",
            author="octokitten",
            workflow_names="ci.yml",
            merged_at=merged_ts,
        )

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )
        assert response.status_code == 200
        pr = response.json()["pull_requests"][0]
        assert pr["title"] == "[Actions Manager] Update HPS workflows"
        assert pr["author"] == "octokitten"
        assert pr["workflow_names"] == "ci.yml"
        assert pr["merged_at"] is not None
        assert pr["closed_at"] is None
        assert pr["pr_url"].startswith("https://github.com/")


# ---------------------------------------------------------------------------
# Cross-project PR history helpers
# ---------------------------------------------------------------------------

CROSS_USER = "crossuser"
STD_PROJECT = "std_project"
RWX_PROJECT = "rwx_project"


def _create_cross_project_setup(db):
    """
    Create an account, a Standard project, and an RWX project, link them via a
    LinkedReusableWorkflow row, and return (account, std_proj, rwx_proj).
    """
    account = Account(
        github_user=CROSS_USER,
        github_email="cross@example.com",
        account_type="free",
    )
    db.add(account)
    db.commit()
    db.refresh(account)

    std_proj = Project(
        project_name=STD_PROJECT,
        project_code="STD",
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
        project_name=RWX_PROJECT,
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

    # Create a stub workflow belonging to the RWX project so the link row has a
    # valid workflow_id foreign key.
    wf = Workflow(
        workflow_name="reusable.yml",
        workflow_yaml="name: reusable",
        reusable_workflow=True,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)

    db.add(ProjectWorkflow(project_id=rwx_proj.project_id, workflow_id=wf.workflow_id))
    db.commit()

    # Link the Standard project to the RWX project via the shared workflow.
    link = LinkedReusableWorkflow(
        standard_project_id=std_proj.project_id,
        rwx_project_id=rwx_proj.project_id,
        workflow_id=wf.workflow_id,
    )
    db.add(link)
    db.commit()

    return account, std_proj, rwx_proj


def _add_pr_for_project(db, project_id, pr_number):
    """Add a merged PR belonging to ``project_id``."""
    pr = ProjectPullRequest(
        project_id=project_id,
        repo_name="org/repo",
        pr_number=pr_number,
        pr_url=f"https://github.com/org/repo/pull/{pr_number}",
        pr_state="merged",
        branch_name=f"actions-manager/branch-{project_id}-{pr_number}",
        target_branch="main",
        title=f"PR #{pr_number} from project {project_id}",
        merged_at=datetime.now(timezone.utc),
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return pr


# ---------------------------------------------------------------------------
# Cross-project PR history tests
# ---------------------------------------------------------------------------

class TestCrossProjectPRHistory:
    """
    Verify that PR history is shared bidirectionally across linked Standard ↔
    RWX project pairs.
    """

    @pytest.fixture(autouse=True)
    def setup_db(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    # ------------------------------------------------------------------
    # Standard Project sees RWX Project PRs
    # ------------------------------------------------------------------

    def test_standard_project_includes_rwx_prs(self):
        """Standard project history includes merged PRs from its linked RWX project."""
        _, std_proj, rwx_proj = _create_cross_project_setup(self.db)

        # One PR on each side
        _add_pr_for_project(self.db, std_proj.project_id, pr_number=1)
        _add_pr_for_project(self.db, rwx_proj.project_id, pr_number=2)

        with patch("workflows.user_tokens", {CROSS_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": CROSS_USER, "project_name": STD_PROJECT},
            )

        assert response.status_code == 200
        data = response.json()
        # Both PRs must appear when querying the Standard project
        assert data["total"] == 2
        pr_numbers = {pr["pr_number"] for pr in data["pull_requests"]}
        assert pr_numbers == {1, 2}

    def test_rwx_pr_carries_source_project_name_in_standard_query(self):
        """PRs from the RWX project carry source_project_name when queried via the Standard project."""
        _, std_proj, rwx_proj = _create_cross_project_setup(self.db)

        _add_pr_for_project(self.db, rwx_proj.project_id, pr_number=10)

        with patch("workflows.user_tokens", {CROSS_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": CROSS_USER, "project_name": STD_PROJECT},
            )

        assert response.status_code == 200
        prs = response.json()["pull_requests"]
        assert len(prs) == 1
        # The PR originates from the RWX project, not the Standard project
        assert prs[0]["source_project_name"] == RWX_PROJECT

    def test_own_prs_have_no_source_project_name(self):
        """PRs that belong to the queried project have source_project_name=None."""
        _, std_proj, _ = _create_cross_project_setup(self.db)

        _add_pr_for_project(self.db, std_proj.project_id, pr_number=5)

        with patch("workflows.user_tokens", {CROSS_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": CROSS_USER, "project_name": STD_PROJECT},
            )

        assert response.status_code == 200
        prs = response.json()["pull_requests"]
        assert len(prs) == 1
        assert prs[0]["source_project_name"] is None

    # ------------------------------------------------------------------
    # RWX Project sees Standard Project PRs
    # ------------------------------------------------------------------

    def test_rwx_project_includes_standard_prs(self):
        """RWX project history includes merged PRs from each linked Standard project."""
        _, std_proj, rwx_proj = _create_cross_project_setup(self.db)

        _add_pr_for_project(self.db, std_proj.project_id, pr_number=3)
        _add_pr_for_project(self.db, rwx_proj.project_id, pr_number=4)

        with patch("workflows.user_tokens", {CROSS_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": CROSS_USER, "project_name": RWX_PROJECT},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        pr_numbers = {pr["pr_number"] for pr in data["pull_requests"]}
        assert pr_numbers == {3, 4}

    def test_standard_pr_carries_source_project_name_in_rwx_query(self):
        """PRs from the Standard project carry source_project_name when queried via RWX."""
        _, std_proj, rwx_proj = _create_cross_project_setup(self.db)

        _add_pr_for_project(self.db, std_proj.project_id, pr_number=20)

        with patch("workflows.user_tokens", {CROSS_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": CROSS_USER, "project_name": RWX_PROJECT},
            )

        assert response.status_code == 200
        prs = response.json()["pull_requests"]
        assert len(prs) == 1
        assert prs[0]["source_project_name"] == STD_PROJECT

    # ------------------------------------------------------------------
    # No cross-project leakage without a link
    # ------------------------------------------------------------------

    def test_unlinked_project_does_not_see_other_project_prs(self):
        """Projects without a LinkedReusableWorkflow link do not see each other's PRs."""
        _, std_proj, rwx_proj = _create_cross_project_setup(self.db)

        # Create a completely separate unlinked project
        unlinked = Project(
            project_name="unlinked_project",
            project_code="UNL",
            user_id=std_proj.user_id,
            branch_option="default",
            reusable_workflows_enabled=False,
            pr_state="synced",
            project_type="standard",
        )
        self.db.add(unlinked)
        self.db.commit()
        self.db.refresh(unlinked)

        # Add a PR to the RWX project (which the unlinked project should NOT see)
        _add_pr_for_project(self.db, rwx_proj.project_id, pr_number=99)

        with patch("workflows.user_tokens", {CROSS_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-history",
                params={"github_user": CROSS_USER, "project_name": "unlinked_project"},
            )

        assert response.status_code == 200
        assert response.json()["total"] == 0


class TestPRCampaigns:

    @pytest.fixture(autouse=True)
    def setup_db(self):
        app.dependency_overrides[get_db] = override_get_db
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        yield
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    def test_lists_active_campaign_from_open_prs(self):
        _, project = _create_account_and_project(self.db)
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-a",
            pr_number=10,
            pr_state="open",
            workflow_names="okok.yml",
            author="aireland1010",
        )

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-campaigns",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["active_campaigns"] == 1
        assert data["completed_campaigns"] == 0
        assert data["open_prs"] == 1
        campaign = data["campaigns"][0]
        assert campaign["campaign_name"] == "Update okok.yml"
        assert campaign["campaign_status"] == "open"
        assert campaign["open_count"] == 1
        assert campaign["created_by"] == "aireland1010"
        assert campaign["completion_percentage"] == 0

    def test_lists_completed_cancelled_and_mixed_campaign_states(self):
        _, project = _create_account_and_project(self.db)
        now = datetime.now(timezone.utc)
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-a",
            pr_number=20,
            pr_state="merged",
            workflow_names="merged.yml",
            merged_at=now,
        )
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-b",
            pr_number=21,
            pr_state="closed",
            workflow_names="closed.yml",
            closed_at=now,
        )
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-c",
            pr_number=22,
            pr_state="merged",
            workflow_names="mixed.yml",
            merged_at=now,
        )
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-d",
            pr_number=23,
            pr_state="closed",
            workflow_names="mixed.yml",
            closed_at=now,
        )

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}):
            response = client.get(
                "/api/project-pr-campaigns",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )

        assert response.status_code == 200
        data = response.json()
        statuses = {campaign["campaign_name"]: campaign["campaign_status"] for campaign in data["campaigns"]}
        assert statuses["Update merged.yml"] == "completed"
        assert statuses["Update closed.yml"] == "cancelled"
        assert statuses["Update mixed.yml"] == "partially_completed"
        assert data["completed_campaigns"] == 3
        assert data["merged_prs"] == 2
        assert data["closed_prs"] == 2
        mixed = next(campaign for campaign in data["campaigns"] if campaign["campaign_name"] == "Update mixed.yml")
        assert mixed["completion_percentage"] == 100

    def test_campaigns_reject_another_users_project(self):
        _, _ = _create_account_and_project(self.db)
        other = Account(
            github_user="otheruser",
            github_email="other@example.com",
            account_type="free",
        )
        self.db.add(other)
        self.db.commit()

        with patch("workflows.user_tokens", {"otheruser": "fake-token"}):
            response = client.get(
                "/api/project-pr-campaigns",
                params={"github_user": "otheruser", "project_name": TEST_PROJECT},
            )

        assert response.status_code == 404

    def test_merge_and_close_update_campaign_and_project_state(self):
        _, project = _create_account_and_project(self.db)
        project.pr_state = "open"
        self.db.commit()
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-a",
            pr_number=30,
            pr_state="open",
            workflow_names="rollout.yml",
        )
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-b",
            pr_number=31,
            pr_state="open",
            workflow_names="rollout.yml",
        )
        merge_response = Mock()
        merge_response.status_code = 200
        merge_response.json.return_value = {"sha": "merged-sha"}
        close_response = Mock()
        close_response.status_code = 200
        close_response.json.return_value = {"state": "closed"}

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("workflows.github_put", return_value=merge_response), \
             patch("workflows.github_patch", return_value=close_response), \
             patch("workflows._delete_actions_manager_branch", return_value=(True, None)):
            merge = client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "repo_name": "org/repo-a",
                    "pr_number": 30,
                },
            )
            close = client.patch(
                "/api/close-pull-request",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "repo_name": "org/repo-b",
                    "pr_number": 31,
                },
            )
            campaigns = client.get(
                "/api/project-pr-campaigns",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )

        assert merge.status_code == 200
        assert close.status_code == 200
        assert campaigns.status_code == 200
        campaign = campaigns.json()["campaigns"][0]
        assert campaign["campaign_status"] == "partially_completed"
        assert campaign["merged_count"] == 1
        assert campaign["closed_count"] == 1

        self.db.expire_all()
        updated_project = self.db.query(Project).filter_by(project_id=project.project_id).first()
        assert updated_project.pr_state == "draft"

    def test_final_merge_updates_project_workflow_and_campaign_state(self):
        _, project = _create_account_and_project(self.db)
        project.pr_state = "open"
        self.db.commit()
        workflow = _add_workflow(self.db, project.project_id, name="synced.yml")
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-a",
            pr_number=40,
            pr_state="open",
            workflow_names="synced.yml",
        )
        merge_response = Mock()
        merge_response.status_code = 200
        merge_response.json.return_value = {"sha": "merged-sha"}

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("workflows.github_put", return_value=merge_response), \
             patch("workflows._delete_actions_manager_branch", return_value=(True, None)):
            merge = client.put(
                "/api/merge-pull-request",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "repo_name": "org/repo-a",
                    "pr_number": 40,
                },
            )
            campaigns = client.get(
                "/api/project-pr-campaigns",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )

        assert merge.status_code == 200
        assert campaigns.status_code == 200
        data = campaigns.json()
        assert data["active_campaigns"] == 0
        assert data["completed_campaigns"] == 1
        assert data["campaigns"][0]["campaign_status"] == "completed"

        self.db.expire_all()
        updated_project = self.db.query(Project).filter_by(project_id=project.project_id).first()
        updated_workflow = self.db.query(Workflow).filter_by(workflow_id=workflow.workflow_id).first()
        assert updated_project.pr_state == "synced"
        assert updated_workflow.workflow_status == "synced_with_github"

    def test_final_close_updates_project_workflow_and_campaign_state(self):
        _, project = _create_account_and_project(self.db)
        project.pr_state = "open"
        self.db.commit()
        workflow = _add_workflow(self.db, project.project_id, name="closed.yml")
        _add_pr(
            self.db,
            project.project_id,
            repo_name="org/repo-a",
            pr_number=41,
            pr_state="open",
            workflow_names="closed.yml",
        )
        close_response = Mock()
        close_response.status_code = 200
        close_response.json.return_value = {"state": "closed"}

        with patch("workflows.user_tokens", {TEST_USER: "fake-token"}), \
             patch("workflows.github_patch", return_value=close_response):
            close = client.patch(
                "/api/close-pull-request",
                json={
                    "github_user": TEST_USER,
                    "project_name": TEST_PROJECT,
                    "repo_name": "org/repo-a",
                    "pr_number": 41,
                },
            )
            campaigns = client.get(
                "/api/project-pr-campaigns",
                params={"github_user": TEST_USER, "project_name": TEST_PROJECT},
            )

        assert close.status_code == 200
        assert campaigns.status_code == 200
        data = campaigns.json()
        assert data["active_campaigns"] == 0
        assert data["completed_campaigns"] == 1
        assert data["campaigns"][0]["campaign_status"] == "cancelled"

        self.db.expire_all()
        updated_project = self.db.query(Project).filter_by(project_id=project.project_id).first()
        updated_workflow = self.db.query(Workflow).filter_by(workflow_id=workflow.workflow_id).first()
        assert updated_project.pr_state == "draft"
        assert updated_workflow.workflow_status == "committed_locally"
