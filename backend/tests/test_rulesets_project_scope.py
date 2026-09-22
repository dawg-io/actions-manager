"""Listing a project's rulesets resolved the project by ownership.

`GET /api/rulesets/{project_name}` looked the project up as

    Project.project_name == project_name AND Project.user_id == caller.user_id

and `assert_session_owns_user` forces `github_user` to be the caller — so the
panel only ever loaded for the account that *created* the project. Every other
caller got a 404, which the UI renders as "Error loading rulesets". That
included a workspace admin on a project they did not create, so it was never
only a member-visibility question.

Resolution now goes through the access-aware lookup, the same one the rest of
the project pages use.
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from models import Account, Project, ProjectMembership, Ruleset, ProjectRuleset, WorkspaceMember
from tests.conftest import TestingSessionLocal

OWNER = "scope-owner"
ADMIN = "scope-admin"
MEMBER = "scope-member"
PROJECT = "ScopedProject"

client = TestClient(app)


@pytest.fixture
def seeded():
    """A project owned by OWNER with one ruleset, plus an admin and a member."""
    db = TestingSessionLocal()
    try:
        owner = Account(github_user=OWNER, github_email=f"{OWNER}@example.com", account_type="free")
        admin = Account(github_user=ADMIN, github_email=f"{ADMIN}@example.com", account_type="free")
        member = Account(github_user=MEMBER, github_email=f"{MEMBER}@example.com", account_type="free")
        db.add_all([owner, admin, member])
        db.commit()
        db.refresh(owner)
        db.refresh(admin)
        db.refresh(member)

        db.add(WorkspaceMember(user_id=admin.user_id, workspace_role="admin"))
        db.add(WorkspaceMember(user_id=member.user_id, workspace_role="member"))

        project = Project(
            project_name=PROJECT, project_code="SCOP", user_id=owner.user_id,
            project_type="standard",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        ruleset = Ruleset(
            ruleset_name="require-reviews",
            ruleset_json='{"name": "require-reviews", "target": "branch"}',
            description="Protected branch policy",
            user_id=owner.user_id,
        )
        db.add(ruleset)
        db.commit()
        db.refresh(ruleset)
        db.add(ProjectRuleset(project_id=project.project_id, ruleset_id=ruleset.ruleset_id))
        db.commit()
        return project.project_id
    finally:
        db.close()


def test_the_owner_still_sees_them(seeded, authenticate_client):
    authenticate_client(client, OWNER, TestingSessionLocal)

    resp = client.get(f"/api/rulesets/{PROJECT}", params={"github_user": OWNER})

    assert resp.status_code == 200, resp.text
    assert [r["ruleset_name"] for r in resp.json()["rulesets"]] == ["require-reviews"]


def test_an_admin_sees_a_project_they_did_not_create(seeded, authenticate_client):
    """The case that shows this was never only about members."""
    authenticate_client(client, ADMIN, TestingSessionLocal)

    resp = client.get(f"/api/rulesets/{PROJECT}", params={"github_user": ADMIN})

    assert resp.status_code == 200, resp.text
    assert [r["ruleset_name"] for r in resp.json()["rulesets"]] == ["require-reviews"]


def test_a_member_sees_them_rather_than_an_error(seeded, authenticate_client):
    """A member reads every project in the workspace, rulesets included."""
    authenticate_client(client, MEMBER, TestingSessionLocal)

    resp = client.get(f"/api/rulesets/{PROJECT}", params={"github_user": MEMBER})

    assert resp.status_code == 200, resp.text
    assert [r["ruleset_name"] for r in resp.json()["rulesets"]] == ["require-reviews"]


def test_naming_someone_else_is_still_refused(seeded, authenticate_client):
    """Resolution widened; the session-ownership assertion did not."""
    authenticate_client(client, MEMBER, TestingSessionLocal)

    resp = client.get(f"/api/rulesets/{PROJECT}", params={"github_user": OWNER})

    assert resp.status_code == 403, resp.text
