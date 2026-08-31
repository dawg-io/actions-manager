"""
The naming contract for a project's GitHub resources, in both prefix modes.

A project either prefixes the resources it manages with ``AM_{PROJECT_CODE}_``
or it does not, and that choice has to hold across every resource type the
product creates. These tests pin the names that actually reach GitHub — the
workflow filename, the variable key, the secret name in the request URL — so a
change to one path cannot quietly diverge from the others.

Deployment environments are deliberately part of this file even though they are
never prefixed: their names are chosen by the user and referenced by name from
workflow `environment:` keys and branch protection rules, so prefixing them
would break those references. That is a decision, not an oversight, and it is
asserted here so it stays one.
"""
import os
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from github_env_vars import _create_missing_environments, _format_env_var_key
from github_secrets import _process_repository_secrets
from workflows import format_workflow_name

PROJECT_CODE = "MYPROJ"


class TestWorkflowFilenames:
    """format_workflow_name — the file that lands in .github/workflows/."""

    def test_prefix_mode_prefixes_and_adds_the_extension(self):
        assert format_workflow_name("ci", PROJECT_CODE, use_prefix=True) == "AM_MYPROJ_ci.yml"

    def test_no_prefix_mode_keeps_the_bare_name(self):
        assert format_workflow_name("ci", PROJECT_CODE, use_prefix=False) == "ci.yml"

    def test_no_prefix_mode_does_not_double_the_extension(self):
        assert format_workflow_name("ci.yml", PROJECT_CODE, use_prefix=False) == "ci.yml"
        assert format_workflow_name("ci.yaml", PROJECT_CODE, use_prefix=False) == "ci.yaml"

    def test_underscores_in_a_name_survive_prefixing(self):
        # Workflow names routinely contain underscores, which is also what the
        # AM_{code}_ prefix is delimited by. Neither may eat the other.
        assert (
            format_workflow_name("build_and_test", PROJECT_CODE, use_prefix=True)
            == "AM_MYPROJ_build_and_test.yml"
        )


class TestEnvironmentVariableKeys:
    """_format_env_var_key — the Actions variable name."""

    def test_prefix_mode_prefixes_and_uppercases(self):
        assert _format_env_var_key("api_url", PROJECT_CODE, use_prefix=True) == "AM_MYPROJ_API_URL"

    def test_no_prefix_mode_only_uppercases(self):
        assert _format_env_var_key("api_url", PROJECT_CODE, use_prefix=False) == "API_URL"

    def test_prefix_mode_does_not_stack_a_second_prefix(self):
        assert (
            _format_env_var_key("AM_MYPROJ_API_URL", PROJECT_CODE, use_prefix=True)
            == "AM_MYPROJ_API_URL"
        )


class TestEnvironmentSecretNames:
    """The secret name in the URL _process_repository_secrets actually PUTs to."""

    @staticmethod
    async def _put_secret(use_prefix: bool) -> str:
        client = AsyncMock()
        client.put.return_value = Mock(status_code=201, text="")

        with patch("github_secrets.encrypt_secret", return_value="encrypted"):
            await _process_repository_secrets(
                repo_name="octo/service-a",
                secrets=[{"secret_key": "db_password", "secret_value": "hunter2"}],
                project_code=PROJECT_CODE,
                key_id="key-id",
                public_key="public-key",
                headers={},
                client=client,
                use_prefix=use_prefix,
            )

        client.put.assert_awaited_once()
        return client.put.await_args.args[0]

    @pytest.mark.asyncio
    async def test_prefix_mode_stores_the_prefixed_name(self):
        url = await self._put_secret(use_prefix=True)
        assert url.endswith("/repos/octo/service-a/actions/secrets/AM_MYPROJ_DB_PASSWORD")

    @pytest.mark.asyncio
    async def test_no_prefix_mode_stores_the_bare_name(self):
        url = await self._put_secret(use_prefix=False)
        assert url.endswith("/repos/octo/service-a/actions/secrets/DB_PASSWORD")

    @pytest.mark.asyncio
    async def test_the_secret_value_never_reaches_the_url(self):
        url = await self._put_secret(use_prefix=True)
        assert "hunter2" not in url


class TestBuildMetricsRunShape:
    """The build-metrics response must carry the field the UI names runs by.

    `RecentRun` is a Pydantic model, so a field it does not declare is silently
    dropped no matter what the caller passes. The UI renders `workflow_filename`;
    when the model omitted it every run row rendered blank, and nothing caught it
    because no test asserted the response shape.
    """

    def test_recent_run_declares_the_filename_the_ui_renders(self):
        from build_metrics import RecentRun

        assert "workflow_filename" in RecentRun.model_fields

    def test_a_serialised_run_carries_the_prefixed_filename(self):
        from build_metrics import RecentRun

        run = RecentRun(
            github_run_id=1,
            run_number=42,
            workflow_name="ci",
            workflow_filename="AM_MYPROJ_ci.yml",
            branch="main",
        )

        # `workflow_name` is the bare stem ActionsManager stores; only
        # `workflow_filename` carries the prefix and the extension, so the two
        # have to survive serialisation independently.
        assert run.model_dump()["workflow_filename"] == "AM_MYPROJ_ci.yml"
        assert run.model_dump()["workflow_name"] == "ci"


class TestDeploymentEnvironmentNames:
    """Deployment environments are never prefixed, in either mode."""

    @pytest.mark.asyncio
    async def test_the_environment_name_is_used_verbatim(self):
        client = AsyncMock()
        client.put.return_value = Mock(status_code=201, text="")

        _, created = await _create_missing_environments(
            repo_names=["octo/service-a"],
            environment_name="production",
            existing_environments={},
            client=client,
            headers={},
        )

        assert created == 1
        url = client.put.await_args.args[0]
        assert url.endswith("/repos/octo/service-a/environments/production")
        # A prefix here would break every workflow `environment:` key and every
        # branch protection rule that names the environment.
        assert "AM_" not in url
