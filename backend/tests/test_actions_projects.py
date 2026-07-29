"""
Tests for the Actions Projects feature (issue #1687).

Covers:
- URL parsing (repo-root, direct blob-file, and Marketplace listing URLs)
- Marketplace listing page scraping
- Preview: success, extension fallback, invalid YAML, missing name, 404, unauthenticated
- Full CRUD, scoped per-user
"""

import os
import sys
import json
import base64
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("INSTALLATION_MODE", "cloud")

from main import app  # noqa: E402
from actions_projects import (  # noqa: E402
    get_db as ap_get_db,
    parse_actions_yaml_url,
    _resolve_marketplace_action,
    _ApiError,
)
from auth import user_tokens, create_auth_session  # noqa: E402
from models import Base, Account  # noqa: E402

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


def _setup_account(db, github_user="testuser"):
    account = Account(github_user=github_user, github_email=f"{github_user}@example.com", account_type="free")
    db.add(account)
    db.commit()
    db.refresh(account)
    return account.user_id


def _session_headers(db, github_user="testuser") -> dict:
    """A real session for github_user, since routes now verify the caller's
    session actually belongs to the github_user they claim in the request."""
    return {"Authorization": f"Bearer {create_auth_session(github_user, db)}"}


@pytest.fixture(autouse=True)
def db_state():
    _saved = app.dependency_overrides.get(ap_get_db)
    app.dependency_overrides[ap_get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    user_tokens["testuser"] = "fake-token"
    yield
    Base.metadata.drop_all(bind=engine)
    user_tokens.pop("testuser", None)
    if _saved is None:
        app.dependency_overrides.pop(ap_get_db, None)
    else:
        app.dependency_overrides[ap_get_db] = _saved


def _mock_response(status_code=200, json_data=None, text=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text or ""
    return resp


def _encode(content: str) -> str:
    return base64.b64encode(content.encode()).decode()


def _marketplace_html(owner: str, repo: str, subdir: str = "") -> str:
    """Minimal stand-in for a real marketplace listing page's embedded payload."""
    uses_prefix = f"{owner}/{repo}/{subdir}@" if subdir else f"{owner}/{repo}@"
    payload = {"payload": {"action": {"ownerLogin": owner, "externalUsesPathPrefix": uses_prefix}}}
    return (
        '<script type="application/json" data-target="react-app.embeddedData">'
        + json.dumps(payload)
        + "</script>"
    )


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------


class TestParseActionsYamlUrl:
    def test_root_repo_url(self):
        owner, repo, ref, path, search_dir = parse_actions_yaml_url("https://github.com/octo/widgets")
        assert (owner, repo, ref, path, search_dir) == ("octo", "widgets", None, None, "")

    def test_root_repo_url_trailing_slash(self):
        owner, repo, ref, path, search_dir = parse_actions_yaml_url("https://github.com/octo/widgets/")
        assert (owner, repo, ref, path, search_dir) == ("octo", "widgets", None, None, "")

    def test_blob_file_url(self):
        owner, repo, ref, path, search_dir = parse_actions_yaml_url(
            "https://github.com/octo/widgets/blob/main/nested/actions.yaml"
        )
        assert (owner, repo, ref, path, search_dir) == ("octo", "widgets", "main", "nested/actions.yaml", None)

    def test_rejects_path_traversal_in_blob_url(self):
        with pytest.raises(ValueError):
            parse_actions_yaml_url("https://github.com/octo/widgets/blob/main/../secrets.yaml")

    def test_rejects_non_github_url(self):
        with pytest.raises(ValueError):
            parse_actions_yaml_url("https://example.com/octo/widgets")

    def test_marketplace_url_delegates_to_resolver(self):
        with patch(
            "actions_projects._resolve_marketplace_action",
            return_value=("trufflesecurity", "trufflehog", ""),
        ) as mock_resolve:
            owner, repo, ref, path, search_dir = parse_actions_yaml_url(
                "https://github.com/marketplace/actions/trufflehog-oss"
            )
        mock_resolve.assert_called_once_with("trufflehog-oss")
        assert (owner, repo, ref, path, search_dir) == ("trufflesecurity", "trufflehog", None, None, "")

    def test_marketplace_url_with_subdir(self):
        with patch(
            "actions_projects._resolve_marketplace_action",
            return_value=("some-org", "monorepo", "packages/my-action"),
        ):
            owner, repo, ref, path, search_dir = parse_actions_yaml_url(
                "https://github.com/marketplace/actions/my-action"
            )
        assert (owner, repo, search_dir) == ("some-org", "monorepo", "packages/my-action")


# ---------------------------------------------------------------------------
# Marketplace listing resolution
# ---------------------------------------------------------------------------


class TestResolveMarketplaceAction:
    def test_resolves_owner_repo_from_embedded_payload(self):
        html = _marketplace_html("trufflesecurity", "trufflehog")
        with patch("actions_projects.requests.get", return_value=_mock_response(200, text=html)) as mock_get:
            owner, repo, subdir = _resolve_marketplace_action("trufflehog-oss")

        assert (owner, repo, subdir) == ("trufflesecurity", "trufflehog", "")
        assert mock_get.call_args[0][0] == "https://github.com/marketplace/actions/trufflehog-oss"
        # The listing page is public — no Authorization header should be sent.
        assert not mock_get.call_args.kwargs.get("headers")

    def test_resolves_subdir_for_monorepo_actions(self):
        html = _marketplace_html("some-org", "monorepo", subdir="packages/my-action")
        with patch("actions_projects.requests.get", return_value=_mock_response(200, text=html)):
            owner, repo, subdir = _resolve_marketplace_action("my-action")

        assert (owner, repo, subdir) == ("some-org", "monorepo", "packages/my-action")

    def test_slug_not_found(self):
        with patch("actions_projects.requests.get", return_value=_mock_response(404)):
            with pytest.raises(_ApiError) as exc_info:
                _resolve_marketplace_action("does-not-exist")
        assert exc_info.value.status_code == 404

    def test_malformed_page_raises_502(self):
        with patch("actions_projects.requests.get", return_value=_mock_response(200, text="<html>no payload here</html>")):
            with pytest.raises(_ApiError) as exc_info:
                _resolve_marketplace_action("weird-action")
        assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


class TestPreview:
    def test_preview_root_url_success(self):
        """Common case: action.yml (the real GitHub convention) exists at root."""
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = (
            "name: My Action\n"
            "description: Does a thing\n"
            "inputs:\n"
            "  who-to-greet:\n"
            "    description: Who to greet\n"
            "    required: true\n"
            "    default: World\n"
        )
        mock_resp = _mock_response(200, {"content": _encode(yaml_content)})

        with patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Action"
        assert data["ref"] == "main"
        assert data["yaml_path"] == "action.yml"
        assert data["inputs"] == [{
            "name": "who-to-greet", "description": "Who to greet",
            "required": True, "default": "World", "type": "string", "options": None,
        }]

    def test_preview_root_url_falls_back_to_action_yaml(self):
        """If action.yml 404s, falls back to action.yaml before trying the plural spellings."""
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = "name: My Action\ninputs: {}\n"
        not_found_resp = _mock_response(404, {})
        found_resp = _mock_response(200, {"content": _encode(yaml_content)})

        with patch("actions_projects.requests.get", side_effect=[not_found_resp, found_resp]) as mock_get, \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["yaml_path"] == "action.yaml"
        assert mock_get.call_count == 2
        assert "/action.yml?" in mock_get.call_args_list[0][0][0]
        assert "/action.yaml?" in mock_get.call_args_list[1][0][0]

    def test_preview_root_url_falls_back_through_all_candidates(self):
        """Exercises the full fallback chain down to the legacy plural spelling."""
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = "name: My Action\ninputs: {}\n"
        responses = [_mock_response(404, {})] * 3 + [_mock_response(200, {"content": _encode(yaml_content)})]

        with patch("actions_projects.requests.get", side_effect=responses) as mock_get, \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["yaml_path"] == "actions.yaml"
        assert mock_get.call_count == 4

    def test_preview_root_url_neither_extension_found(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        mock_resp = _mock_response(404, {})

        with patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "action.yml" in detail
        assert "action.yaml" in detail
        assert "actions.yml" in detail
        assert "actions.yaml" in detail

    def test_preview_marketplace_url_success(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = "name: TruffleHog OSS\ninputs: {}\n"
        mock_resp = _mock_response(200, {"content": _encode(yaml_content)})

        with patch("actions_projects._resolve_marketplace_action",
                   return_value=("trufflesecurity", "trufflehog", "")), \
             patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={
                    "github_user": "testuser",
                    "url": "https://github.com/marketplace/actions/trufflehog-oss",
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "TruffleHog OSS"
        assert data["owner"] == "trufflesecurity"
        assert data["repo"] == "trufflehog"
        assert data["yaml_path"] == "action.yml"

    def test_preview_marketplace_url_with_subdir_searches_that_path(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = "name: Nested Action\ninputs: {}\n"
        mock_resp = _mock_response(200, {"content": _encode(yaml_content)})

        with patch("actions_projects._resolve_marketplace_action",
                   return_value=("some-org", "monorepo", "packages/my-action")), \
             patch("actions_projects.requests.get", return_value=mock_resp) as mock_get, \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/marketplace/actions/my-action"},
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["yaml_path"] == "packages/my-action/action.yml"
        assert "packages/my-action/action.yml" in mock_get.call_args[0][0]

    def test_preview_marketplace_slug_not_found(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        with patch("actions_projects.requests.get", return_value=_mock_response(404)):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/marketplace/actions/nope"},
                headers=headers,
            )

        assert resp.status_code == 404

    def test_preview_blob_url_success_skips_default_branch_lookup(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = "name: Nested Action\ninputs: {}\n"
        mock_resp = _mock_response(200, {"content": _encode(yaml_content)})

        with patch("actions_projects.requests.get", return_value=mock_resp) as mock_get, \
             patch("actions_projects.get_default_branch") as mock_default_branch:
            resp = client.get(
                "/api/actions-projects/preview",
                params={
                    "github_user": "testuser",
                    "url": "https://github.com/octo/widgets/blob/v2/nested/actions.yaml",
                },
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ref"] == "v2"
        assert data["yaml_path"] == "nested/actions.yaml"
        mock_default_branch.assert_not_called()
        assert "nested/actions.yaml" in mock_get.call_args[0][0]

    def test_preview_invalid_yaml(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        mock_resp = _mock_response(200, {"content": _encode("not: valid: yaml: [")})

        with patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 422

    def test_preview_missing_name_field(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        mock_resp = _mock_response(200, {"content": _encode("description: no name here\n")})

        with patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 422

    def test_preview_file_not_found(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        mock_resp = _mock_response(404, {})

        with patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 404

    def test_preview_unauthenticated(self):
        resp = client.get(
            "/api/actions-projects/preview",
            params={"github_user": "nobody", "url": "https://github.com/octo/widgets"},
        )
        assert resp.status_code == 401

    def test_preview_rejects_bad_url(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        resp = client.get(
            "/api/actions-projects/preview",
            params={"github_user": "testuser", "url": "not-a-url"},
            headers=headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def _create_payload(**overrides):
    payload = {
        "github_user": "testuser",
        "name": "My Action",
        "description": "Does a thing",
        "source_url": "https://github.com/octo/widgets",
        "owner": "octo",
        "repo": "widgets",
        "ref": "main",
        "yaml_path": "action.yml",
        "inputs": [{"name": "who-to-greet", "description": None, "required": True, "default": "World"}],
    }
    payload.update(overrides)
    return payload


class TestCrud:
    def test_create_then_list_then_get(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        create_resp = client.post("/api/actions-projects/", json=_create_payload(), headers=headers)
        assert create_resp.status_code == 201
        created = create_resp.json()
        assert created["name"] == "My Action"
        assert created["inputs"][0]["name"] == "who-to-greet"

        list_resp = client.get("/api/actions-projects/", params={"github_user": "testuser"}, headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        get_resp = client.get(
            f"/api/actions-projects/{created['actions_project_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "My Action"

    def test_update(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        created = client.post("/api/actions-projects/", json=_create_payload(), headers=headers).json()

        update_resp = client.put(
            f"/api/actions-projects/{created['actions_project_id']}",
            json={
                "github_user": "testuser",
                "name": "Renamed Action",
                "description": "Updated",
                "inputs": [],
            },
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["name"] == "Renamed Action"
        assert update_resp.json()["inputs"] == []

    def test_delete(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        created = client.post("/api/actions-projects/", json=_create_payload(), headers=headers).json()

        delete_resp = client.delete(
            f"/api/actions-projects/{created['actions_project_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert delete_resp.status_code == 204

        get_resp = client.get(
            f"/api/actions-projects/{created['actions_project_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert get_resp.status_code == 404

    def test_shared_across_users(self):
        """Actions Projects are a shared, workspace-wide catalog: anyone
        authenticated can see, edit, and delete anyone else's imports."""
        db = TestingSessionLocal()
        _setup_account(db, "testuser")
        _setup_account(db, "otheruser")
        headers = _session_headers(db, "testuser")
        other_headers = _session_headers(db, "otheruser")
        db.close()
        user_tokens["otheruser"] = "other-token"

        try:
            created = client.post("/api/actions-projects/", json=_create_payload(), headers=headers).json()

            other_get = client.get(
                f"/api/actions-projects/{created['actions_project_id']}",
                params={"github_user": "otheruser"},
                headers=other_headers,
            )
            assert other_get.status_code == 200
            assert other_get.json()["name"] == "My Action"

            other_list = client.get(
                "/api/actions-projects/", params={"github_user": "otheruser"}, headers=other_headers
            )
            assert len(other_list.json()) == 1

            other_update = client.put(
                f"/api/actions-projects/{created['actions_project_id']}",
                json={"github_user": "otheruser", "name": "Renamed by other user", "description": None, "inputs": []},
                headers=other_headers,
            )
            assert other_update.status_code == 200
            assert other_update.json()["name"] == "Renamed by other user"

            other_delete = client.delete(
                f"/api/actions-projects/{created['actions_project_id']}",
                params={"github_user": "otheruser"},
                headers=other_headers,
            )
            assert other_delete.status_code == 204
        finally:
            user_tokens.pop("otheruser", None)

    def test_create_unauthenticated(self):
        resp = client.post("/api/actions-projects/", json=_create_payload(github_user="nobody"))
        assert resp.status_code == 401

    def test_cannot_impersonate_another_user_by_claiming_their_username(self):
        """A real session for testuser must not be able to act as otheruser
        just by putting otheruser's name in github_user - github_user is
        client-controlled and GitHub usernames are public, so this is the
        exact impersonation this endpoint must reject."""
        db = TestingSessionLocal()
        _setup_account(db, "testuser")
        _setup_account(db, "otheruser")
        headers = _session_headers(db, "testuser")
        db.close()
        user_tokens["otheruser"] = "other-token"

        try:
            resp = client.post(
                "/api/actions-projects/",
                json=_create_payload(github_user="otheruser"),
                headers=headers,
            )
            assert resp.status_code == 403
        finally:
            user_tokens.pop("otheruser", None)


class TestActionInputType:
    """Issue #1693: inputs can be upgraded from the default 'string' type."""

    def test_defaults_to_string_when_omitted(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        created = client.post("/api/actions-projects/", json=_create_payload(), headers=headers).json()
        assert created["inputs"][0]["type"] == "string"
        assert created["inputs"][0]["options"] is None

    def test_choice_type_with_options_round_trips(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        payload = _create_payload(inputs=[{
            "name": "log-level", "description": "Verbosity", "required": False,
            "default": "info", "type": "choice", "options": ["debug", "info", "warn", "error"],
        }])
        created = client.post("/api/actions-projects/", json=payload, headers=headers).json()
        assert created["inputs"][0]["type"] == "choice"
        assert created["inputs"][0]["options"] == ["debug", "info", "warn", "error"]

        get_resp = client.get(
            f"/api/actions-projects/{created['actions_project_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert get_resp.json()["inputs"][0]["options"] == ["debug", "info", "warn", "error"]

    def test_boolean_and_number_types_round_trip(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        payload = _create_payload(inputs=[
            {"name": "verbose", "description": None, "required": False, "default": "true", "type": "boolean"},
            {"name": "retries", "description": None, "required": False, "default": "3", "type": "number"},
        ])
        created = client.post("/api/actions-projects/", json=payload, headers=headers).json()
        assert [i["type"] for i in created["inputs"]] == ["boolean", "number"]

    def test_rejects_invalid_type(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        payload = _create_payload(inputs=[
            {"name": "bad", "description": None, "required": False, "default": None, "type": "not-a-real-type"},
        ])
        resp = client.post("/api/actions-projects/", json=payload, headers=headers)
        assert resp.status_code == 422

    def test_update_can_upgrade_type_and_add_options(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        created = client.post("/api/actions-projects/", json=_create_payload(), headers=headers).json()

        update_resp = client.put(
            f"/api/actions-projects/{created['actions_project_id']}",
            json={
                "github_user": "testuser",
                "name": created["name"],
                "description": None,
                "inputs": [{
                    "name": "who-to-greet", "description": "Who to greet", "required": True,
                    "default": "World", "type": "choice", "options": ["World", "Universe"],
                }],
            },
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["inputs"][0]["type"] == "choice"
        assert update_resp.json()["inputs"][0]["options"] == ["World", "Universe"]


class TestBranding:
    """Marketplace-style branding.icon/branding.color, parsed from the same
    action.yml already being fetched during preview/create."""

    def test_valid_branding_round_trips_through_preview_create_get(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = (
            "name: My Action\n"
            "description: Does a thing\n"
            "branding:\n"
            "  icon: rocket\n"
            "  color: blue\n"
        )
        mock_resp = _mock_response(200, {"content": _encode(yaml_content)})

        with patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            preview_resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert preview_resp.status_code == 200
        preview_data = preview_resp.json()
        assert preview_data["branding_icon"] == "rocket"
        assert preview_data["branding_color"] == "blue"

        create_payload = _create_payload(
            branding_icon=preview_data["branding_icon"],
            branding_color=preview_data["branding_color"],
        )
        created = client.post("/api/actions-projects/", json=create_payload, headers=headers).json()
        assert created["branding_icon"] == "rocket"
        assert created["branding_color"] == "blue"

        get_resp = client.get(
            f"/api/actions-projects/{created['actions_project_id']}",
            params={"github_user": "testuser"},
            headers=headers,
        )
        assert get_resp.json()["branding_icon"] == "rocket"
        assert get_resp.json()["branding_color"] == "blue"

    def test_missing_branding_defaults_to_none(self):
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = "name: My Action\ninputs: {}\n"
        mock_resp = _mock_response(200, {"content": _encode(yaml_content)})

        with patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["branding_icon"] is None
        assert resp.json()["branding_color"] is None

    def test_invalid_branding_color_ignored_icon_still_parsed(self):
        """A color GitHub Marketplace wouldn't recognize is dropped, but a
        valid icon name is still kept — defensive per-field, not all-or-nothing."""
        db = TestingSessionLocal()
        _setup_account(db)
        headers = _session_headers(db)
        db.close()

        yaml_content = (
            "name: My Action\n"
            "branding:\n"
            "  icon: rocket\n"
            "  color: not-a-real-color\n"
        )
        mock_resp = _mock_response(200, {"content": _encode(yaml_content)})

        with patch("actions_projects.requests.get", return_value=mock_resp), \
             patch("actions_projects.get_default_branch", return_value="main"):
            resp = client.get(
                "/api/actions-projects/preview",
                params={"github_user": "testuser", "url": "https://github.com/octo/widgets"},
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["branding_icon"] == "rocket"
        assert resp.json()["branding_color"] is None
