"""Security tests: authenticated session identity wins over body/header input."""
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from auth import create_auth_session, user_tokens  # noqa: E402
from main import app  # noqa: E402
from models import Account, Base, Project, ProjectWorkflow, Repo, Workflow, ProjectRepo, WorkspaceMember  # noqa: E402
from projects import get_db as projects_get_db  # noqa: E402
from workflows import get_db as workflows_get_db  # noqa: E402

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_github_user_header_security.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
HEADERUSER_SESSION_TOKEN = ""


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    global HEADERUSER_SESSION_TOKEN
    original_factory = app.state.middleware_db_factory
    original_projects_override = app.dependency_overrides.get(projects_get_db)
    original_workflows_override = app.dependency_overrides.get(workflows_get_db)
    app.state.middleware_db_factory = TestingSessionLocal
    app.dependency_overrides[projects_get_db] = override_get_db
    app.dependency_overrides[workflows_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        account = Account(github_user="headeruser", github_email="h@example.com", account_type="professional")
        db.add(account)
        db.commit()
        db.refresh(account)
        db.add(WorkspaceMember(user_id=account.user_id, workspace_role="admin"))
        db.commit()

        project = Project(
            project_name="SecurityProject",
            project_code="SECP",
            user_id=account.user_id,
            pr_state="draft",
            project_type="standard",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        repo = Repo(repo_name="owner/repo")
        db.add(repo)
        db.commit()
        db.refresh(repo)

        db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))

        workflow = Workflow(
            workflow_name="build",
            workflow_yaml="name: Build\non: push\njobs: {}",
            reusable_workflow=False,
        )
        db.add(workflow)
        db.commit()
        db.refresh(workflow)

        db.add(ProjectWorkflow(project_id=project.project_id, workflow_id=workflow.workflow_id))
        db.commit()
    finally:
        db.close()

    user_tokens["headeruser"] = "test_token"
    db = TestingSessionLocal()
    try:
        HEADERUSER_SESSION_TOKEN = create_auth_session("headeruser", db)
    finally:
        db.close()
    yield
    HEADERUSER_SESSION_TOKEN = ""
    user_tokens.clear()
    client.cookies.clear()
    Base.metadata.drop_all(bind=engine)
    app.state.middleware_db_factory = original_factory
    for dependency, original in (
        (projects_get_db, original_projects_override),
        (workflows_get_db, original_workflows_override),
    ):
        if original is None:
            app.dependency_overrides.pop(dependency, None)
        else:
            app.dependency_overrides[dependency] = original


client = TestClient(app)


def auth_headers(extra_headers=None):
    headers = {"Authorization": "Bearer " + HEADERUSER_SESSION_TOKEN}
    if extra_headers:
        headers.update(extra_headers)
    return headers


# ---------------------------------------------------------------------------
# POST /projects/ — create_project
# ---------------------------------------------------------------------------

class TestCreateProjectHeaderSecurity:
    def test_rejects_when_no_identity_provided(self):
        """No header and no body github_user must be rejected."""
        response = client.post(
            "/api/projects/",
            json={
                "project_name": "NewProject",
                "selected_repos": ["owner/repo"],
                "workflows": [],
                "rxworkflows": [],
            },
        )
        assert response.status_code == 401

    def test_accepts_header_without_body_github_user(self):
        """Header alone is sufficient; body github_user is optional."""
        response = client.post(
            "/api/projects/",
            headers=auth_headers(),
            json={
                "project_name": "HeaderOnlyProject",
                "selected_repos": ["owner/repo"],
                "workflows": [],
                "rxworkflows": [],
            },
        )
        assert response.status_code == 200

    def test_header_overrides_body_github_user(self):
        """Header identity is used even when body supplies a different (attacker-controlled) github_user."""
        # "attacker" is not in user_tokens — if body value were trusted, this would fail auth
        response = client.post(
            "/api/projects/",
            headers=auth_headers(),
            json={
                "github_user": "attacker",
                "project_name": "AttackProject",
                "selected_repos": ["owner/repo"],
                "workflows": [],
                "rxworkflows": [],
            },
        )
        # Should succeed using headeruser (not attacker)
        assert response.status_code == 200

    def test_body_github_user_without_session_is_rejected(self):
        """Body github_user alone is not an authenticated identity."""
        response = client.post(
            "/api/projects/",
            json={
                "github_user": "headeruser",
                "project_name": "BodyUserProject",
                "selected_repos": ["owner/repo"],
                "workflows": [],
                "rxworkflows": [],
            },
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/save-workflows
# ---------------------------------------------------------------------------

class TestSaveWorkflowsHeaderSecurity:
    def test_rejects_when_no_identity_provided(self):
        response = client.post(
            "/api/save-workflows",
            json={"project_name": "SecurityProject", "workflows": []},
        )
        assert response.status_code == 401

    def test_accepts_header_without_body_github_user(self):
        response = client.post(
            "/api/save-workflows",
            headers=auth_headers(),
            json={"project_name": "SecurityProject", "workflows": []},
        )
        # Passes auth; may fail downstream for other reasons but not auth
        assert response.status_code != 401

    def test_header_takes_precedence_over_body(self):
        """Body with wrong user should be overridden by header with correct user."""
        response = client.post(
            "/api/save-workflows",
            headers=auth_headers(),
            json={
                "github_user": "attacker",
                "project_name": "SecurityProject",
                "workflows": [],
            },
        )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# POST /api/detect-drift
# ---------------------------------------------------------------------------

class TestDetectDriftHeaderSecurity:
    def test_rejects_unauthenticated(self):
        response = client.post(
            "/api/detect-drift",
            json={"project_name": "SecurityProject", "repo_names": ["owner/repo"]},
        )
        assert response.status_code == 401

    def test_header_accepted(self):
        response = client.post(
            "/api/detect-drift",
            headers=auth_headers(),
            json={"project_name": "SecurityProject", "repo_names": ["owner/repo"]},
        )
        assert response.status_code != 401

    def test_header_overrides_attacker_body(self):
        response = client.post(
            "/api/detect-drift",
            headers=auth_headers(),
            json={
                "github_user": "attacker",
                "project_name": "SecurityProject",
                "repo_names": ["owner/repo"],
            },
        )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# POST /api/create-pull-requests
# ---------------------------------------------------------------------------

class TestCreatePullRequestsHeaderSecurity:
    def test_rejects_unauthenticated(self):
        response = client.post(
            "/api/create-pull-requests",
            json={"project_name": "SecurityProject"},
        )
        assert response.status_code == 401

    def test_header_accepted(self):
        response = client.post(
            "/api/create-pull-requests",
            headers=auth_headers(),
            json={"project_name": "SecurityProject"},
        )
        # Passes auth check; may fail on workflow processing, but not 401
        assert response.status_code != 401

    def test_header_overrides_attacker_body(self):
        response = client.post(
            "/api/create-pull-requests",
            headers=auth_headers(),
            json={"github_user": "attacker", "project_name": "SecurityProject"},
        )
        assert response.status_code != 401


# ---------------------------------------------------------------------------
# POST /api/drift/adopt-github-version
# ---------------------------------------------------------------------------

class TestAdoptGithubVersionHeaderSecurity:
    def test_rejects_unauthenticated(self):
        response = client.post(
            "/api/drift/adopt-github-version",
            json={"project_id": 1, "workflow_id": 1, "resolution_mode": "adopt_local_only"},
        )
        assert response.status_code == 401

    def test_header_accepted(self):
        response = client.post(
            "/api/drift/adopt-github-version",
            headers=auth_headers(),
            json={"project_id": 1, "workflow_id": 1, "resolution_mode": "adopt_local_only"},
        )
        # Passes auth; may fail on DB lookups, but not 401
        assert response.status_code != 401

    def test_header_overrides_attacker_body(self):
        response = client.post(
            "/api/drift/adopt-github-version",
            headers=auth_headers(),
            json={
                "github_user": "attacker",
                "project_id": 1,
                "workflow_id": 1,
                "resolution_mode": "adopt_local_only",
            },
        )
        assert response.status_code != 401
