import pytest

from ai_workflows import WorkflowEditRequest, edit_workflow_with_ai


@pytest.mark.asyncio
async def test_structured_ai_action_returns_full_updated_workflow(monkeypatch):
    async def fake_completion(prompt: str, max_tokens: int = 2000) -> str:
        assert "Return a FULL valid GitHub Actions workflow YAML" in prompt
        assert "Never append content to the existing YAML" in prompt
        return """
        {
          "updated_workflow": "name: CI\\non: [push]\\njobs:\\n  test:\\n    runs-on: ubuntu-latest\\n    steps:\\n      - uses: actions/checkout@v4",
          "analysis": "Updated deprecated actions and kept a complete workflow.",
          "enhancement_suggestions": ["Review test coverage"],
          "suggested_questions": ["Add CodeQL?"],
          "changes_summary": ["Updated checkout to v4"]
        }
        """

    monkeypatch.setattr("ai_workflows.call_openai_completion", fake_completion)

    response = await edit_workflow_with_ai(
        WorkflowEditRequest(
            user="octocat",
            project_name="Actions Manager",
            workflow_name="ci",
            current_workflow="name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest",
            action="improve",
            optional_instruction="Use Node 20",
            repository_info={"selected_repos": ["octocat/demo"]},
            build_types=["node"],
        )
    )

    assert response.updated_workflow.startswith("name: CI")
    assert "actions/checkout@v4" in response.updated_workflow
    assert response.workflow_analysis == "Updated deprecated actions and kept a complete workflow."
    assert response.changes_summary == ["Updated checkout to v4"]
