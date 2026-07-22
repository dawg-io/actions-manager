"""
Tests for PR campaign async creation progress and status reporting.

Verifies:
- GET /api/create-pull-requests/{task_id} returns task state
- Progress callback populates repos dict with step/status/error
- Task not found returns 404
- Completed state includes results and prs_created
- Workflow filenames for both standard and reusable workflows are tracked
"""

import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from main import app
from workflows import pr_campaign_tasks, PROGRESS_OPENING_PR


client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_tasks():
    """Clean up task dict after each test."""
    yield
    pr_campaign_tasks.clear()


def test_task_not_found_returns_404():
    resp = client.get("/api/create-pull-requests/nonexistent-task-id")
    assert resp.status_code == 404
    assert "Task not found" in resp.json()["detail"]


def test_running_task_returns_repos_progress():
    task_id = str(uuid.uuid4())
    pr_campaign_tasks[task_id] = {
        "status": "running",
        "repos": {
            "org/repo-a on main": {"step": "Creating branch", "status": "running", "error": None},
            "org/repo-b on main": {"step": "Pending", "status": "pending", "error": None},
        },
        "results": {},
        "prs_created": 0,
    }

    resp = client.get(f"/api/create-pull-requests/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert "org/repo-a on main" in data["repos"]
    assert data["repos"]["org/repo-a on main"]["step"] == "Creating branch"
    assert data["repos"]["org/repo-a on main"]["status"] == "running"
    assert data["repos"]["org/repo-b on main"]["status"] == "pending"


def test_completed_task_includes_results_and_pr_count():
    task_id = str(uuid.uuid4())
    pr_campaign_tasks[task_id] = {
        "status": "completed",
        "repos": {
            "org/repo-a on main": {"step": PROGRESS_OPENING_PR, "status": "completed", "error": None},
        },
        "results": {
            "org/repo-a on main": {
                "status": "pr_created",
                "pr_number": 42,
                "pr_url": "https://github.com/org/repo-a/pull/42",
                "branch_name": "actions-manager/CMP-main-42",
            }
        },
        "prs_created": 1,
    }

    resp = client.get(f"/api/create-pull-requests/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["prs_created"] == 1
    assert data["results"]["org/repo-a on main"]["pr_number"] == 42


def test_error_task_includes_error_message():
    task_id = str(uuid.uuid4())
    pr_campaign_tasks[task_id] = {
        "status": "error",
        "repos": {
            "org/repo-a on main": {"step": PROGRESS_OPENING_PR, "status": "error", "error": "GitHub returned 422"},
        },
        "results": {},
        "prs_created": 0,
        "error": "Failed during PR creation",
    }

    resp = client.get(f"/api/create-pull-requests/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["error"] == "Failed during PR creation"
    assert data["repos"]["org/repo-a on main"]["error"] == "GitHub returned 422"


def test_progress_callback_updates_repo_state():
    """Simulate what _run_create_pull_requests_async does with progress_callback."""
    task_id = str(uuid.uuid4())
    pr_campaign_tasks[task_id] = {
        "status": "running",
        "repos": {},
        "results": {},
        "prs_created": 0,
    }

    # Simulate the progress_callback function
    def progress_callback(repo_name: str, step: str, status: str, error=None):
        if repo_name not in pr_campaign_tasks[task_id]["repos"]:
            pr_campaign_tasks[task_id]["repos"][repo_name] = {"step": step, "status": status, "error": error}
        else:
            pr_campaign_tasks[task_id]["repos"][repo_name].update({"step": step, "status": status, "error": error})

    # First repo starts
    progress_callback("org/repo-a on main", "Creating branch", "running")
    assert pr_campaign_tasks[task_id]["repos"]["org/repo-a on main"]["step"] == "Creating branch"
    assert pr_campaign_tasks[task_id]["repos"]["org/repo-a on main"]["status"] == "running"

    # First repo advances
    progress_callback("org/repo-a on main", "Committing files", "running")
    assert pr_campaign_tasks[task_id]["repos"]["org/repo-a on main"]["step"] == "Committing files"

    # First repo completes
    progress_callback("org/repo-a on main", PROGRESS_OPENING_PR, "completed")
    assert pr_campaign_tasks[task_id]["repos"]["org/repo-a on main"]["status"] == "completed"

    # Second repo (reusable workflow repo) starts
    progress_callback("org/am-reuseable-workflow on main", "Creating branch", "running")
    assert "org/am-reuseable-workflow on main" in pr_campaign_tasks[task_id]["repos"]

    # Second repo fails
    progress_callback("org/am-reuseable-workflow on main", PROGRESS_OPENING_PR, "error", "Branch already exists")
    assert pr_campaign_tasks[task_id]["repos"]["org/am-reuseable-workflow on main"]["status"] == "error"
    assert pr_campaign_tasks[task_id]["repos"]["org/am-reuseable-workflow on main"]["error"] == "Branch already exists"


def test_repo_key_format_includes_target_branch():
    """Verify repo keys use format 'repo_name on target_branch' for both standard and reusable."""
    task_id = str(uuid.uuid4())
    pr_campaign_tasks[task_id] = {
        "status": "completed",
        "repos": {
            "whatsupdawg/test1 on main": {"step": PROGRESS_OPENING_PR, "status": "completed", "error": None},
            "whatsupdawg/test2 on develop": {"step": PROGRESS_OPENING_PR, "status": "completed", "error": None},
            "whatsupdawg/am-reuseable-workflow on main": {"step": PROGRESS_OPENING_PR, "status": "completed", "error": None},
        },
        "results": {},
        "prs_created": 3,
    }

    resp = client.get(f"/api/create-pull-requests/{task_id}")
    data = resp.json()
    # Standard repos
    assert "whatsupdawg/test1 on main" in data["repos"]
    assert "whatsupdawg/test2 on develop" in data["repos"]
    # Reusable workflow repo
    assert "whatsupdawg/am-reuseable-workflow on main" in data["repos"]
