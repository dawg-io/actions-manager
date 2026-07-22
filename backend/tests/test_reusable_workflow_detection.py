"""
Tests for reusable workflow YAML detection helper.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from reusable_workflow_detection import is_reusable_workflow_yaml


class TestIsReusableWorkflowYaml:
    """Unit tests for is_reusable_workflow_yaml."""

    def test_simple_workflow_call_string(self):
        """on: workflow_call as a simple string trigger."""
        yaml_content = "name: Reusable\non: workflow_call\njobs:\n  build:\n    runs-on: ubuntu-latest"
        assert is_reusable_workflow_yaml(yaml_content) is True

    def test_workflow_call_dict_form(self):
        """on:\n  workflow_call: (dict with workflow_call key)."""
        yaml_content = "name: Reusable\non:\n  workflow_call:\njobs:\n  build:\n    runs-on: ubuntu-latest"
        assert is_reusable_workflow_yaml(yaml_content) is True

    def test_workflow_call_with_inputs(self):
        """workflow_call with inputs defined."""
        yaml_content = """name: Reusable
on:
  workflow_call:
    inputs:
      environment:
        type: string
jobs:
  deploy:
    runs-on: ubuntu-latest
"""
        assert is_reusable_workflow_yaml(yaml_content) is True

    def test_quoted_on_key(self):
        """'on' key is quoted as \"on\"."""
        yaml_content = '"on":\n  workflow_call:\njobs:\n  build:\n    runs-on: ubuntu-latest'
        assert is_reusable_workflow_yaml(yaml_content) is True

    def test_multiple_triggers_including_workflow_call(self):
        """Multiple triggers with workflow_call among them."""
        yaml_content = """name: Multi Trigger
on:
  push:
    branches: [main]
  workflow_call:
    inputs:
      env:
        type: string
jobs:
  build:
    runs-on: ubuntu-latest
"""
        assert is_reusable_workflow_yaml(yaml_content) is True

    def test_list_form_with_workflow_call(self):
        """on: [push, workflow_call] list syntax."""
        yaml_content = "name: List\non: [push, workflow_call]\njobs:\n  build:\n    runs-on: ubuntu-latest"
        assert is_reusable_workflow_yaml(yaml_content) is True

    def test_normal_workflow_without_workflow_call(self):
        """Standard workflow with push/PR triggers - not reusable."""
        yaml_content = """name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
"""
        assert is_reusable_workflow_yaml(yaml_content) is False

    def test_workflow_dispatch_only(self):
        """Workflow dispatch only - not reusable."""
        yaml_content = "name: Manual\non: workflow_dispatch\njobs:\n  deploy:\n    runs-on: ubuntu-latest"
        assert is_reusable_workflow_yaml(yaml_content) is False

    def test_malformed_yaml(self):
        """Malformed YAML should return False, not raise."""
        yaml_content = "name: Bad\non:\n  - [invalid: yaml: {{{"
        assert is_reusable_workflow_yaml(yaml_content) is False

    def test_empty_string(self):
        """Empty string returns False."""
        assert is_reusable_workflow_yaml("") is False

    def test_none_input(self):
        """None input returns False."""
        assert is_reusable_workflow_yaml(None) is False

    def test_non_string_input(self):
        """Non-string input returns False."""
        assert is_reusable_workflow_yaml(123) is False

    def test_yaml_with_no_on_key(self):
        """YAML without 'on' key returns False."""
        yaml_content = "name: No Trigger\njobs:\n  build:\n    runs-on: ubuntu-latest"
        assert is_reusable_workflow_yaml(yaml_content) is False

    def test_workflow_call_in_job_uses_not_trigger(self):
        """workflow_call appearing in a job 'uses' field, not as trigger."""
        yaml_content = """name: Caller
on: push
jobs:
  call-workflow:
    uses: org/repo/.github/workflows/reusable.yml@main
"""
        assert is_reusable_workflow_yaml(yaml_content) is False

    def test_workflow_call_dict_with_empty_value(self):
        """workflow_call: {} (empty dict value)."""
        yaml_content = "name: Deploy\non:\n  workflow_call: {}\n"
        assert is_reusable_workflow_yaml(yaml_content) is True
