"""
Tests for repository-level branch configuration overrides.

Covers:
  * Default ``branch_config_mode`` for new ``ProjectRepo`` rows is "inherit".
  * GET project repo branch configs returns inherit + effective values.
  * PATCH override updates a single repo without affecting siblings.
  * PATCH inherit / DELETE reset both clear override columns.
  * ``resolve_branch_config_for_repo`` honours overrides + falls back.
  * Validation rejects bad mode / option / regex / max_age.
  * Unauthenticated / non-owner callers cannot read or modify.
  * Removing a repo from the project also drops its override row.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app  # noqa: E402
from workflows import get_db as real_get_db, resolve_branch_config_for_repo  # noqa: E402
from projects import get_db as projects_get_db  # noqa: E402
from models import (  # noqa: E402
    Base, Account, Project, Repo, ProjectRepo,
)


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def db_state():
    prev_override = app.dependency_overrides.get(real_get_db)
    prev_proj_override = app.dependency_overrides.get(projects_get_db)
    app.dependency_overrides[real_get_db] = override_get_db
    app.dependency_overrides[projects_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        owner = Account(github_user="alice", github_email="a@example.com", account_type="free")
        other = Account(github_user="mallory", github_email="m@example.com", account_type="free")
        db.add_all([owner, other])
        db.commit()
        db.refresh(owner)
        db.refresh(other)

        project = Project(
            project_name="proj1",
            project_code="P001",
            user_id=owner.user_id,
            branch_option="default",
            branch_regex="",
            branch_max_age_days=30,
            use_prefix=True,
            pr_state="new",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        repo1 = Repo(repo_name="whatsupdawg/test1")
        repo2 = Repo(repo_name="whatsupdawg/test2")
        db.add_all([repo1, repo2])
        db.commit()
        db.refresh(repo1)
        db.refresh(repo2)

        # Existing rows default to inherit (model default applies).
        db.add_all([
            ProjectRepo(project_id=project.project_id, repo_id=repo1.repo_id),
            ProjectRepo(project_id=project.project_id, repo_id=repo2.repo_id),
        ])
        db.commit()

        yield {
            "owner": owner,
            "other": other,
            "project": project,
            "repo1": repo1,
            "repo2": repo2,
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        if prev_override is None:
            app.dependency_overrides.pop(real_get_db, None)
        else:
            app.dependency_overrides[real_get_db] = prev_override
        if prev_proj_override is None:
            app.dependency_overrides.pop(projects_get_db, None)
        else:
            app.dependency_overrides[projects_get_db] = prev_proj_override


# ---------------------------------------------------------------------------
# Model defaults / migration parity
# ---------------------------------------------------------------------------

def test_project_repo_default_mode_is_inherit(db_state):
    db = TestingSessionLocal()
    try:
        rows = db.query(ProjectRepo).filter(
            ProjectRepo.project_id == db_state["project"].project_id
        ).all()
        assert rows
        for row in rows:
            assert (row.branch_config_mode or "inherit") == "inherit"
            assert row.branch_option is None
            assert row.branch_regex is None
            assert row.branch_max_age_days is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

def test_resolver_falls_back_to_project_when_inherit(db_state):
    db = TestingSessionLocal()
    try:
        proj = db.query(Project).get(db_state["project"].project_id)
        proj.branch_option = "pattern"
        proj.branch_regex = "release/.*"
        proj.branch_max_age_days = 7
        db.commit()

        cfg = resolve_branch_config_for_repo(db, proj, db_state["repo1"].repo_name)
        assert cfg["branch_option"] == "pattern"
        assert cfg["branch_regex"] == "release/.*"
        assert cfg["branch_max_age_days"] == 7
        assert cfg["using_project_default"] is True
    finally:
        db.close()


def test_resolver_uses_repo_override(db_state):
    db = TestingSessionLocal()
    try:
        proj = db.query(Project).get(db_state["project"].project_id)
        assoc = db.query(ProjectRepo).filter_by(
            project_id=proj.project_id, repo_id=db_state["repo1"].repo_id,
        ).first()
        assoc.branch_config_mode = "override"
        assoc.branch_option = "pattern"
        assoc.branch_regex = "develop"
        assoc.branch_max_age_days = 14
        db.commit()

        cfg = resolve_branch_config_for_repo(db, proj, db_state["repo1"].repo_name)
        assert cfg["branch_option"] == "pattern"
        assert cfg["branch_regex"] == "develop"
        assert cfg["branch_max_age_days"] == 14
        assert cfg["using_project_default"] is False

        # Sibling still inherits the project setting
        cfg2 = resolve_branch_config_for_repo(db, proj, db_state["repo2"].repo_name)
        assert cfg2["using_project_default"] is True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET endpoint
# ---------------------------------------------------------------------------

def test_get_repo_branch_configs_returns_inherit_for_existing(db_state):
    pid = db_state["project"].project_id
    resp = client.get(
        f"/api/projects/{pid}/repo-branch-configs",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == pid
    assert body["project_branch_option"] == "default"
    assert len(body["repos"]) == 2
    for repo in body["repos"]:
        assert repo["branch_config_mode"] == "inherit"
        assert repo["using_project_default"] is True
        assert repo["effective_branch_option"] == "default"


# ---------------------------------------------------------------------------
# PATCH endpoint – override / isolation / reset
# ---------------------------------------------------------------------------

def test_patch_override_only_affects_target_repo(db_state):
    pid = db_state["project"].project_id
    rid1 = db_state["repo1"].repo_id
    rid2 = db_state["repo2"].repo_id

    resp = client.patch(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "alice"},
        json={
            "branch_config_mode": "override",
            "branch_option": "pattern",
            "branch_regex": "develop",
            "branch_max_age_days": 14,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["branch_config_mode"] == "override"
    assert body["branch_option"] == "pattern"
    assert body["branch_regex"] == "develop"
    assert body["branch_max_age_days"] == 14
    assert body["effective_branch_regex"] == "develop"
    assert body["using_project_default"] is False

    # Sibling repo unchanged
    resp2 = client.get(
        f"/api/projects/{pid}/repo-branch-configs",
        params={"github_user": "alice"},
    )
    by_id = {r["repo_id"]: r for r in resp2.json()["repos"]}
    assert by_id[rid2]["branch_config_mode"] == "inherit"
    assert by_id[rid2]["using_project_default"] is True
    assert by_id[rid1]["branch_config_mode"] == "override"


def test_patch_inherit_clears_override_columns(db_state):
    pid = db_state["project"].project_id
    rid1 = db_state["repo1"].repo_id
    # First set an override
    client.patch(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "alice"},
        json={"branch_config_mode": "override", "branch_option": "pattern", "branch_regex": "main"},
    )
    # Then set back to inherit
    resp = client.patch(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "alice"},
        json={"branch_config_mode": "inherit"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["branch_config_mode"] == "inherit"
    assert body["branch_option"] is None
    assert body["branch_regex"] is None
    assert body["branch_max_age_days"] is None
    assert body["using_project_default"] is True


def test_delete_resets_repo_to_project_default(db_state):
    pid = db_state["project"].project_id
    rid1 = db_state["repo1"].repo_id
    client.patch(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "alice"},
        json={"branch_config_mode": "override", "branch_option": "pattern", "branch_regex": "main"},
    )

    resp = client.delete(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "alice"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["branch_config_mode"] == "inherit"
    assert body["using_project_default"] is True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload, hint", [
    ({"branch_config_mode": "weird"}, "branch_config_mode"),
    ({"branch_config_mode": "override", "branch_option": "weird"}, "branch_option"),
    ({"branch_config_mode": "override", "branch_option": "pattern", "branch_regex": ""}, "branch_regex"),
    ({"branch_config_mode": "override", "branch_option": "pattern", "branch_regex": "[unclosed"}, "Invalid branch_regex"),
    ({"branch_config_mode": "override", "branch_option": "pattern", "branch_regex": "main", "branch_max_age_days": 0}, "branch_max_age_days"),
    ({"branch_config_mode": "override", "branch_option": "pattern", "branch_regex": "main", "branch_max_age_days": 99}, "branch_max_age_days"),
])
def test_patch_rejects_invalid_payloads(db_state, payload, hint):
    pid = db_state["project"].project_id
    rid1 = db_state["repo1"].repo_id
    resp = client.patch(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "alice"},
        json=payload,
    )
    assert resp.status_code == 400, resp.text
    assert hint in resp.json()["detail"]


def test_patch_unknown_repo_in_project_returns_404(db_state):
    pid = db_state["project"].project_id
    resp = client.patch(
        f"/api/projects/{pid}/repos/9999/branch-config",
        params={"github_user": "alice"},
        json={"branch_config_mode": "inherit"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

def test_non_owner_cannot_read_or_modify(db_state):
    pid = db_state["project"].project_id
    rid1 = db_state["repo1"].repo_id

    resp = client.get(
        f"/api/projects/{pid}/repo-branch-configs",
        params={"github_user": "mallory"},
    )
    assert resp.status_code in (403, 404)

    resp = client.patch(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "mallory"},
        json={"branch_config_mode": "inherit"},
    )
    assert resp.status_code in (403, 404)


def test_project_viewer_cannot_modify_branch_config(db_state):
    """A read-only workspace member with project_viewer membership can GET but
    not PATCH/DELETE the per-repo branch config."""
    from models import WorkspaceMember, ProjectMembership

    pid = db_state["project"].project_id
    rid1 = db_state["repo1"].repo_id
    other = db_state["other"]  # mallory

    db = TestingSessionLocal()
    try:
        db.add(WorkspaceMember(user_id=other.user_id, workspace_role="read_only"))
        db.add(ProjectMembership(
            user_id=other.user_id,
            project_id=pid,
            project_role="project_viewer",
        ))
        db.commit()
    finally:
        db.close()

    # Viewer can read.
    resp = client.get(
        f"/api/projects/{pid}/repo-branch-configs",
        params={"github_user": "mallory"},
        headers={"X-GitHub-User": "mallory"},
    )
    assert resp.status_code == 200

    # Viewer cannot PATCH.
    resp = client.patch(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "mallory"},
        headers={"X-GitHub-User": "mallory"},
        json={"branch_config_mode": "override", "branch_option": "default"},
    )
    assert resp.status_code == 403

    # Viewer cannot DELETE.
    resp = client.delete(
        f"/api/projects/{pid}/repos/{rid1}/branch-config",
        params={"github_user": "mallory"},
        headers={"X-GitHub-User": "mallory"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Repo removal cascades override drop
# ---------------------------------------------------------------------------

def test_removing_repo_from_project_drops_override(db_state):
    """When ``_process_project_repos`` is called without a repo, its
    ProjectRepo row (and per-repo overrides) must be removed."""
    from projects import _process_project_repos

    pid = db_state["project"].project_id
    rid1 = db_state["repo1"].repo_id

    db = TestingSessionLocal()
    try:
        assoc = db.query(ProjectRepo).filter_by(project_id=pid, repo_id=rid1).first()
        assoc.branch_config_mode = "override"
        assoc.branch_option = "pattern"
        assoc.branch_regex = "develop"
        db.commit()

        # Remove repo1 from selection — only repo2 remains
        _process_project_repos(db, pid, [db_state["repo2"].repo_name])
        db.commit()

        rows = db.query(ProjectRepo).filter_by(project_id=pid).all()
        repo_ids = {r.repo_id for r in rows}
        assert rid1 not in repo_ids
        assert db_state["repo2"].repo_id in repo_ids
    finally:
        db.close()


def test_existing_overrides_preserved_when_repos_resaved(db_state):
    """``_process_project_repos`` should not wipe overrides on surviving repos."""
    from projects import _process_project_repos

    pid = db_state["project"].project_id
    rid1 = db_state["repo1"].repo_id

    db = TestingSessionLocal()
    try:
        assoc = db.query(ProjectRepo).filter_by(project_id=pid, repo_id=rid1).first()
        assoc.branch_config_mode = "override"
        assoc.branch_option = "pattern"
        assoc.branch_regex = "develop"
        db.commit()

        # Re-save the same selection
        _process_project_repos(
            db, pid,
            [db_state["repo1"].repo_name, db_state["repo2"].repo_name],
        )
        db.commit()

        assoc = db.query(ProjectRepo).filter_by(project_id=pid, repo_id=rid1).first()
        assert assoc.branch_config_mode == "override"
        assert assoc.branch_option == "pattern"
        assert assoc.branch_regex == "develop"
    finally:
        db.close()
