import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app  # noqa: E402
from models import (  # noqa: E402
    Account,
    Base,
    Codeowners,
    LinkedReusableWorkflow,
    Project,
    ProjectRepo,
    ProjectRuleset,
    ProjectWorkflow,
    Repo,
    RepoWorkflowOverride,
    Ruleset,
    Workflow,
    WorkflowVersion,
)
from projects import get_db as projects_get_db  # noqa: E402


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_database():
    previous_override = app.dependency_overrides.get(projects_get_db)
    app.dependency_overrides[projects_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        owner = Account(
            github_user="owner-user",
            github_email="owner@example.com",
            account_type="enterprise",
            github_pat_token_encrypted="super-secret-token",
        )
        outsider = Account(
            github_user="outsider-user",
            github_email="outsider@example.com",
            account_type="free",
        )
        db.add_all([owner, outsider])
        db.commit()
        db.refresh(owner)
        db.refresh(outsider)

        standard_project = Project(
            project_name="Backup Project",
            project_code="BKP1",
            user_id=owner.user_id,
            branch_option="pattern",
            branch_regex="release/.*",
            branch_max_age_days=14,
            use_prefix=True,
            pr_state="draft",
            project_type="standard",
        )
        rwx_project = Project(
            project_name="Reusable Source",
            project_code="RWX1",
            user_id=owner.user_id,
            project_type="rwx",
            use_prefix=True,
        )
        outsider_standard_project = Project(
            project_name="Outsider Standard",
            project_code="OUT1",
            user_id=outsider.user_id,
            project_type="standard",
            use_prefix=True,
        )
        db.add_all([standard_project, rwx_project, outsider_standard_project])
        db.commit()
        db.refresh(standard_project)
        db.refresh(rwx_project)
        db.refresh(outsider_standard_project)

        repo_a = Repo(repo_name="octo/alpha")
        repo_b = Repo(repo_name="octo/beta")
        db.add_all([repo_a, repo_b])
        db.commit()
        db.refresh(repo_a)
        db.refresh(repo_b)

        db.add_all(
            [
                ProjectRepo(project_id=standard_project.project_id, repo_id=repo_a.repo_id),
                ProjectRepo(
                    project_id=standard_project.project_id,
                    repo_id=repo_b.repo_id,
                    branch_config_mode="override",
                    branch_option="pattern",
                    branch_regex="hotfix/.*",
                    branch_max_age_days=7,
                ),
            ]
        )

        wf_a = Workflow(
            workflow_name="ci.yml",
            workflow_yaml="name: CI\non: [push]\njobs: {}",
            reusable_workflow=False,
            workflow_git_hash="abc123",
            workflow_status="committed_locally",
            last_modified_by="owner-user",
        )
        wf_b = Workflow(
            workflow_name="deploy.yml",
            workflow_yaml="name: Deploy\non: [workflow_dispatch]\njobs: {}",
            reusable_workflow=False,
            workflow_git_hash="def456",
            workflow_status="synced_with_github",
            last_modified_by="owner-user",
        )
        rwx_wf = Workflow(
            workflow_name="shared.yml",
            workflow_yaml="name: Shared\non: workflow_call\njobs: {}",
            reusable_workflow=True,
            workflow_git_hash="zzz999",
            workflow_status="synced_with_github",
        )
        db.add_all([wf_a, wf_b, rwx_wf])
        db.commit()
        db.refresh(wf_a)
        db.refresh(wf_b)
        db.refresh(rwx_wf)

        db.add_all(
            [
                ProjectWorkflow(project_id=standard_project.project_id, workflow_id=wf_a.workflow_id),
                ProjectWorkflow(project_id=standard_project.project_id, workflow_id=wf_b.workflow_id),
                ProjectWorkflow(project_id=rwx_project.project_id, workflow_id=rwx_wf.workflow_id),
            ]
        )

        db.add_all(
            [
                WorkflowVersion(workflow_id=wf_a.workflow_id, version_number=1, content="v1", version_metadata='{"source":"create"}'),
                WorkflowVersion(workflow_id=wf_a.workflow_id, version_number=2, content="v2", version_metadata='{"source":"edit"}'),
                WorkflowVersion(workflow_id=wf_b.workflow_id, version_number=1, content="deploy-v1", version_metadata='{"source":"create"}'),
            ]
        )

        ruleset = Ruleset(
            ruleset_name="Default Rules",
            ruleset_json='{"enforcement":"active"}',
            description="Protect main",
            user_id=owner.user_id,
        )
        db.add(ruleset)
        db.commit()
        db.refresh(ruleset)
        db.add(ProjectRuleset(project_id=standard_project.project_id, ruleset_id=ruleset.ruleset_id))

        db.add(
            Codeowners(
                project_id=standard_project.project_id,
                repo_id=repo_a.repo_id,
                content="* @octo-org/platform",
                file_path=".github/CODEOWNERS",
                git_hash="codeownershash",
                status="committed_locally",
                last_modified_by="owner-user",
            )
        )

        db.add(
            RepoWorkflowOverride(
                project_id=standard_project.project_id,
                repo_id=repo_b.repo_id,
                workflow_id=wf_a.workflow_id,
                workflow_name="ci.yml",
                workflow_yaml="name: CI override\non: [push]\njobs: {}",
                workflow_git_hash="overridehash",
                source_repo_name="octo/beta",
                last_modified_by="owner-user",
            )
        )

        db.add(
            LinkedReusableWorkflow(
                standard_project_id=standard_project.project_id,
                rwx_project_id=rwx_project.project_id,
                workflow_id=rwx_wf.workflow_id,
            )
        )
        db.add(
            LinkedReusableWorkflow(
                standard_project_id=outsider_standard_project.project_id,
                rwx_project_id=rwx_project.project_id,
                workflow_id=rwx_wf.workflow_id,
            )
        )
        db.commit()

        yield {"project_id": standard_project.project_id, "rwx_project_id": rwx_project.project_id}
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        if previous_override is None:
            app.dependency_overrides.pop(projects_get_db, None)
        else:
            app.dependency_overrides[projects_get_db] = previous_override


def test_export_project_backup_success_includes_expected_shape(setup_database):
    project_id = setup_database["project_id"]
    resp = client.get(
        f"/api/projects/{project_id}/backup-export",
        headers={"X-GitHub-User": "owner-user"},
    )
    assert resp.status_code == 200, resp.text
    assert "attachment; filename=" in resp.headers.get("content-disposition", "")

    payload = resp.json()
    assert payload["backup_schema_version"] == "1.1"
    assert payload["metadata"]["source_metadata"]["project_id"] == project_id
    assert payload["metadata"]["project_name"] == "Backup Project"
    assert payload["metadata"]["exported_by"] == "owner-user"
    assert payload["metadata"]["app_name"] == "ActionsManager"
    assert payload["metadata"]["app_version"] == "1.0.0"
    assert payload["import_policy"]["id_strategy"] == "remap"
    assert payload["import_policy"]["github_sync_strategy"] == "verify_after_import"
    assert payload["import_policy"]["default_workflow_status"] == "committed_locally"
    assert payload["summary"]["repository_count"] == 2
    assert payload["summary"]["workflow_count"] == 2
    assert payload["summary"]["workflow_version_count"] == 3
    assert [repo["repo_name"] for repo in payload["repositories"]] == ["octo/alpha", "octo/beta"]
    alpha_repo = next(repo for repo in payload["repositories"] if repo["repo_name"] == "octo/alpha")
    assert alpha_repo["branch_regex"] is None
    assert sorted(wf["name"] for wf in payload["workflows"]) == ["ci.yml", "deploy.yml"]
    assert payload["project"]["branch_regex"] == "release/.*"
    ci_workflow = next(wf for wf in payload["workflows"] if wf["name"] == "ci.yml")
    assert "workflow_status" not in ci_workflow
    assert "workflow_git_hash" not in ci_workflow
    assert ci_workflow["source_metadata"]["workflow_status"] == "committed_locally"
    assert ci_workflow["source_metadata"]["workflow_git_hash"] == "abc123"
    assert len(ci_workflow["content_sha256"]) == 64
    assert [v["version_number"] for v in ci_workflow["version_history"]] == [1, 2]
    assert ci_workflow["version_history"][0]["metadata"] == {"source": "create"}
    assert ci_workflow["version_history"][1]["metadata"] == {"source": "edit"}
    assert payload["integrity"]["algorithm"] == "sha256"
    assert len(payload["integrity"]["payload_sha256"]) == 64


def test_export_project_backup_blocks_unauthorized_user(setup_database):
    project_id = setup_database["project_id"]
    resp = client.get(
        f"/api/projects/{project_id}/backup-export",
        headers={"X-GitHub-User": "outsider-user"},
    )
    assert resp.status_code in (403, 404)


def test_export_project_backup_requires_authenticated_user(setup_database):
    project_id = setup_database["project_id"]
    resp = client.get(f"/api/projects/{project_id}/backup-export")
    assert resp.status_code == 401


def test_export_project_backup_excludes_sensitive_tokens_and_credentials(setup_database):
    project_id = setup_database["project_id"]
    resp = client.get(
        f"/api/projects/{project_id}/backup-export",
        headers={"X-GitHub-User": "owner-user"},
    )
    assert resp.status_code == 200
    serialized = json.dumps(resp.json()).lower()
    assert "super-secret-token" not in serialized
    assert "github_pat_token_encrypted" not in serialized
    assert "github_oauth_token" not in serialized
    assert "admin_password" not in serialized
    assert "webhook_secret" not in serialized


def test_export_project_backup_includes_repo_overrides_and_linked_workflows(setup_database):
    project_id = setup_database["project_id"]
    resp = client.get(
        f"/api/projects/{project_id}/backup-export",
        headers={"X-GitHub-User": "owner-user"},
    )
    assert resp.status_code == 200
    payload = resp.json()

    assert len(payload["repo_workflow_overrides"]) == 1
    assert payload["repo_workflow_overrides"][0]["repo_name"] == "octo/beta"
    assert payload["repo_workflow_overrides"][0]["workflow_name"] == "ci.yml"
    assert "workflow_git_hash" not in payload["repo_workflow_overrides"][0]
    assert payload["repo_workflow_overrides"][0]["source_metadata"]["workflow_git_hash"] == "overridehash"

    assert len(payload["linked_reusable_workflows"]) == 1
    linked = payload["linked_reusable_workflows"][0]
    assert linked["rwx_project_name"] == "Reusable Source"
    assert linked["workflow_name"] == "shared.yml"
    assert linked["standard_project_code"] == "BKP1"
    assert linked["source_metadata"]["workflow_status"] == "synced_with_github"


def test_export_rwx_project_backup_scopes_linked_standard_projects_to_owner(setup_database):
    rwx_project_id = setup_database["rwx_project_id"]
    resp = client.get(
        f"/api/projects/{rwx_project_id}/backup-export",
        headers={"X-GitHub-User": "owner-user"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert [link["standard_project_code"] for link in payload["linked_standard_projects"]] == ["BKP1"]
