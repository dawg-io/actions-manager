"""
Test module for ai_workflows.py - generate_progressive_suggestions function
Tests the function before and after refactoring to ensure functionality is preserved.
"""
import pytest
from ai_workflows import generate_progressive_suggestions, analyze_workflow_capabilities


class TestGenerateProgressiveSuggestions:
    """Test the generate_progressive_suggestions function."""
    
    def test_empty_workflow_suggests_build(self):
        """Test that empty workflow suggests build setup."""
        result = generate_progressive_suggestions("", [])
        assert len(result) <= 4
        assert any("build" in suggestion.lower() for suggestion in result)
    
    def test_maven_build_type_suggestion(self):
        """Test Maven-specific suggestion for empty workflow."""
        result = generate_progressive_suggestions("", ["maven"])
        assert "Set up Maven build with Java" in result
    
    def test_npm_build_type_suggestion(self):
        """Test npm-specific suggestion for empty workflow."""
        result = generate_progressive_suggestions("", ["npm"])
        assert "Configure Node.js build with npm" in result
    
    def test_dotnet_build_type_suggestion(self):
        """Test .NET-specific suggestion for empty workflow."""
        result = generate_progressive_suggestions("", ["dotnet"])
        assert "Set up .NET build pipeline" in result
    
    def test_workflow_with_build_suggests_test(self):
        """Test that workflow with build suggests adding tests."""
        workflow_yaml = """
        name: CI
        on: [push]
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v2
              - run: npm run build
        """
        result = generate_progressive_suggestions(workflow_yaml, [])
        assert any("test" in suggestion.lower() for suggestion in result)
    
    def test_workflow_with_build_and_test_suggests_linting(self):
        """Test that workflow with build and test suggests linting."""
        workflow_yaml = """
        name: CI
        on: [push]
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v2
              - run: npm run build
              - run: npm test
        """
        result = generate_progressive_suggestions(workflow_yaml, [])
        assert any("lint" in suggestion.lower() or "quality" in suggestion.lower() for suggestion in result)
    
    def test_comprehensive_workflow_suggests_artifact_publishing(self):
        """Test that comprehensive workflow suggests artifact publishing."""
        comprehensive_workflow = """
        name: Comprehensive CI/CD
        on: [push, workflow_dispatch]
        jobs:
          test:
            runs-on: ubuntu-latest
            strategy:
              matrix:
                node-version: [14, 16, 18]
            steps:
              - uses: actions/checkout@v2
              - run: npm install
              - run: npm run build
              - run: npm test
              - run: npm run lint
              - uses: github/codeql-action/analyze@v2
              - uses: docker/build-push-action@v2
              - run: |
                  coverage run -m pytest
                  codecov
          deploy:
            needs: test
            runs-on: ubuntu-latest
            environment: production
            steps:
              - run: echo "Deploying..."
                env:
                  SECRET: ${{ secrets.DEPLOY_TOKEN }}
        """
        result = generate_progressive_suggestions(comprehensive_workflow, ["npm"])
        
        # This workflow has most capabilities but is missing artifact publishing
        assert "Set up artifact publishing to package registry" in result
    
    def test_suggestions_limited_to_four(self):
        """Test that function returns at most 4 suggestions."""
        result = generate_progressive_suggestions("", ["maven", "npm", "dotnet"])
        assert len(result) <= 4
    
    def test_docker_without_security_scan_suggests_trivy(self):
        """Test Docker workflow without security scan suggests Trivy."""
        docker_workflow = """
        name: Docker Build
        on: [push]
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v2
              - run: npm run build
              - uses: docker/build-push-action@v2
        """
        result = generate_progressive_suggestions(docker_workflow, [])
        assert any("trivy" in suggestion.lower() or "vulnerability" in suggestion.lower() for suggestion in result)
    
    def test_build_types_parameter_default(self):
        """Test that build_types parameter defaults to empty list."""
        result1 = generate_progressive_suggestions("", None)
        result2 = generate_progressive_suggestions("", [])
        # Both should return the same fallback build suggestion
        assert result1 == result2
    
    def test_simple_workflow_with_build_types_suggests_linting_first(self):
        """Test simple workflow with build types suggests linting first, not matrix."""
        simple_workflow = """
        name: Simple Build
        on: [push]
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - run: npm run build
        """
        result = generate_progressive_suggestions(simple_workflow, ["npm", "node"])
        # The function prioritizes linting over matrix builds
        assert "Include code quality checks and linting" in result
    
    def test_truly_comprehensive_workflow_returns_fallback(self):
        """Test that a truly comprehensive workflow returns fallback suggestions."""
        comprehensive_workflow = """
        name: Complete CI/CD
        on: [push, workflow_dispatch]
        jobs:
          test:
            runs-on: ubuntu-latest
            strategy:
              matrix:
                node-version: [14, 16, 18]
            steps:
              - uses: actions/checkout@v2
              - run: npm install
              - run: npm run build
              - run: npm test
              - run: npm run lint
              - uses: github/codeql-action/analyze@v2
              - uses: docker/build-push-action@v2
              - run: npm publish
              - run: |
                  coverage run -m pytest
                  codecov
          deploy:
            needs: test
            runs-on: ubuntu-latest
            environment: production
            steps:
              - run: echo "Deploying..."
                env:
                  SECRET: ${{ secrets.DEPLOY_TOKEN }}
        """
        result = generate_progressive_suggestions(comprehensive_workflow, ["npm"])
        
        # Should return fallback suggestions since workflow has all capabilities
        expected_fallback = [
            "Add advanced deployment strategies (blue-green, canary)",
            "Set up monitoring and alerting integration", 
            "Configure automatic rollback on deployment failure",
            "Add performance testing to the pipeline"
        ]
        
        assert len(result) == 4
        for suggestion in result:
            assert suggestion in expected_fallback