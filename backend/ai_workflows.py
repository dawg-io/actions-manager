"""
AI Workflow Generation Module

This module provides AI-powered workflow generation with interactive chat functionality
using OpenAI to create and customize GitHub Actions workflows based on user input.
"""

import os
import json
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import openai
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# OpenAI client initialization
openai.api_key = os.getenv("OPENAI_API_KEY")

# Session storage for ongoing conversations (in production, use Redis or database)
conversation_sessions: Dict[str, Dict] = {}

# Constants
SESSION_NOT_FOUND_MESSAGE = "Session not found"
YAML_CODE_BLOCK = "```yaml"
VALID_WORKFLOW_ACTIONS = {"generate", "improve", "make_reusable"}

class WorkflowGenerationRequest(BaseModel):
    user: str
    project_name: str
    project_code: Optional[str] = None
    repository_info: Optional[Dict] = None
    build_types: Optional[List[str]] = None
    user_requirements: Optional[str] = None

class ChatInteractionRequest(BaseModel):
    session_id: str
    user_message: str
    current_workflow: Optional[str] = None

class WorkflowGenerationResponse(BaseModel):
    workflow_yaml: str
    session_id: str
    suggested_questions: List[str]
    explanation: str

class ChatInteractionResponse(BaseModel):
    response_message: str
    updated_workflow: Optional[str] = None
    suggested_questions: List[str]
    workflow_updates: List[str]  # List of changes made to the workflow

class WorkflowEditRequest(BaseModel):
    user: str
    project_name: str
    project_code: Optional[str] = None
    workflow_name: str
    current_workflow: str
    action: Optional[str] = "improve"
    optional_instruction: Optional[str] = None
    repository_info: Optional[Dict] = None
    build_types: Optional[List[str]] = None

class WorkflowEditResponse(BaseModel):
    workflow_analysis: str
    updated_workflow: Optional[str] = None
    session_id: str
    suggested_questions: List[str]
    enhancement_suggestions: List[str]
    changes_summary: List[str] = []

class ReusableWorkflowGenerationRequest(BaseModel):
    user: str
    project_name: str
    project_code: Optional[str] = None
    repository_info: Optional[Dict] = None
    build_types: Optional[List[str]] = None
    user_requirements: Optional[str] = None
    reusable_workflow_name: Optional[str] = None

class ReusableWorkflowGenerationResponse(BaseModel):
    reusable_workflow_yaml: str
    caller_workflow_yaml: str
    session_id: str
    suggested_questions: List[str]
    explanation: str


def _find_json_boundaries(ai_response: str, start_idx: int) -> tuple[int, bool]:
    """
    Find the end index of a JSON block by counting braces.
    Returns (end_index, is_complete_json).
    """
    brace_count = 0
    end_idx = start_idx
    
    for i, char in enumerate(ai_response[start_idx:], start_idx):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i + 1
                break
    
    return end_idx, brace_count == 0


def extract_json_from_response(ai_response: str, fallback_workflow: str) -> Dict:
    """
    Extract JSON from AI response that may contain extra text before/after JSON.
    Returns a properly formatted response dict even if no JSON is found.
    """
    
    # Try to find JSON block between curly braces
    start_idx = ai_response.find('{')
    if start_idx != -1:
        end_idx, is_complete = _find_json_boundaries(ai_response, start_idx)
        
        if is_complete:
            json_str = ai_response[start_idx:end_idx]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass  # Fall through to manual parsing
    
    # If JSON extraction failed, try to parse the response manually
    # Look for common patterns in AI responses
    
    # Extract explanation from the response
    explanation = ai_response.strip()
    if len(explanation) > 500:
        explanation = explanation[:497] + "..."
    
    # Create a fallback response with the original workflow
    return {
        "updated_workflow": fallback_workflow,
        "explanation": f"I understand your request: {explanation}",
        "suggested_questions": [
            "Can you be more specific about the build requirements?",
            "What testing framework would you like to use?",
            "Do you need any specific deployment steps?"
        ],
        "changes_summary": []
    }

def analyze_workflow_capabilities(workflow_yaml: str) -> Dict[str, bool]:
    """Analyze what capabilities the current workflow has to suggest next steps."""
    if not workflow_yaml:
        return {}
    
    workflow_lower = workflow_yaml.lower()
    
    capabilities = {
        'has_build': any(keyword in workflow_lower for keyword in ['build', 'compile', 'maven', 'gradle', 'npm install', 'dotnet build', 'make']),
        'has_test': any(keyword in workflow_lower for keyword in ['test', 'pytest', 'jest', 'junit', 'mocha']),
        'has_security_scan': any(keyword in workflow_lower for keyword in ['codeql', 'sonarqube', 'snyk', 'security']),
        'has_docker': any(keyword in workflow_lower for keyword in ['docker', 'build-push-action', 'dockerfile']),
        'has_deployment': any(keyword in workflow_lower for keyword in ['deploy', 'kubernetes', 'helm', 'aws', 'azure', 'gcp']),
        'has_artifact_publish': any(keyword in workflow_lower for keyword in ['publish', 'nexus', 'packages', 'registry']),
        'has_environment_setup': any(keyword in workflow_lower for keyword in ['environment', 'staging', 'production', 'development']),
        'has_secrets': any(keyword in workflow_lower for keyword in ['secrets', '${{ secrets']),
        'has_coverage': any(keyword in workflow_lower for keyword in ['coverage', 'codecov', 'coveralls']),
        'has_linting': any(keyword in workflow_lower for keyword in ['lint', 'eslint', 'flake8', 'pylint']),
        'has_matrix_build': 'matrix:' in workflow_lower or 'strategy:' in workflow_lower,
        'has_manual_trigger': 'workflow_dispatch' in workflow_lower
    }
    
    return capabilities

def _get_build_suggestion(build_types: List[str]) -> str:
    """Get build suggestion based on build types."""
    if 'maven' in build_types or 'java' in str(build_types).lower():
        return "Set up Maven build with Java"
    elif 'npm' in build_types or 'node' in str(build_types).lower():
        return "Configure Node.js build with npm"
    elif 'dotnet' in build_types or '.net' in str(build_types).lower():
        return "Set up .NET build pipeline"
    else:
        return "Configure build automation for your project"

def _suggest_basic_build_and_test(capabilities: Dict[str, bool], build_types: List[str]) -> List[str]:
    """Generate Phase 1: Basic Build & Test suggestions."""
    suggestions = []
    
    if not capabilities.get('has_build'):
        suggestions.append(_get_build_suggestion(build_types))
    
    if capabilities.get('has_build') and not capabilities.get('has_test'):
        suggestions.append("Add comprehensive testing (unit, integration)")
    
    if capabilities.get('has_build') and not capabilities.get('has_linting'):
        suggestions.append("Include code quality checks and linting")
    
    return suggestions

def _suggest_security_and_quality(capabilities: Dict[str, bool]) -> List[str]:
    """Generate Phase 2: Security & Quality suggestions."""
    suggestions = []
    
    if capabilities.get('has_build') and not capabilities.get('has_security_scan'):
        suggestions.append("Add security scanning with CodeQL analysis")
    
    if capabilities.get('has_test') and not capabilities.get('has_coverage'):
        suggestions.append("Set up test coverage reporting")
    
    return suggestions

def _suggest_containerization(capabilities: Dict[str, bool]) -> List[str]:
    """Generate Phase 3: Containerization suggestions."""
    suggestions = []
    
    if capabilities.get('has_build') and not capabilities.get('has_docker'):
        suggestions.append("Add Docker image building and pushing")
    
    if capabilities.get('has_docker') and not capabilities.get('has_security_scan'):
        suggestions.append("Add container vulnerability scanning with Trivy")
    
    return suggestions

def _suggest_artifact_and_deployment(capabilities: Dict[str, bool]) -> List[str]:
    """Generate Phase 4: Artifact Management & Deployment suggestions."""
    suggestions = []
    
    if capabilities.get('has_build') and not capabilities.get('has_artifact_publish'):
        suggestions.append("Set up artifact publishing to package registry")
    
    has_docker_or_artifact = capabilities.get('has_docker') or capabilities.get('has_artifact_publish')
    if has_docker_or_artifact and not capabilities.get('has_deployment'):
        suggestions.append("Configure deployment to staging environment")
    
    return suggestions

def _suggest_advanced_features(capabilities: Dict[str, bool], build_types: List[str]) -> List[str]:
    """Generate Phase 5 & 6: Advanced CI/CD Features and Secrets Management suggestions."""
    suggestions = []
    
    if capabilities.get('has_deployment') and not capabilities.get('has_environment_setup'):
        suggestions.append("Set up multiple environments (staging, production)")
    
    if not capabilities.get('has_manual_trigger'):
        suggestions.append("Add manual workflow triggers for releases")
    
    if not capabilities.get('has_matrix_build') and len(build_types) > 0:
        suggestions.append("Configure matrix builds for multiple environments")
    
    if capabilities.get('has_deployment') and not capabilities.get('has_secrets'):
        suggestions.append("Configure secrets and environment variables")
    
    return suggestions

def _get_fallback_suggestions() -> List[str]:
    """Get fallback suggestions when workflow is already comprehensive."""
    return [
        "Add advanced deployment strategies (blue-green, canary)",
        "Set up monitoring and alerting integration",
        "Configure automatic rollback on deployment failure",
        "Add performance testing to the pipeline"
    ]

def generate_progressive_suggestions(workflow_yaml: str, build_types: List[str] = None) -> List[str]:
    """Generate progressive CI/CD suggestions based on current workflow state."""
    capabilities = analyze_workflow_capabilities(workflow_yaml)
    build_types = build_types or []
    
    suggestions = []
    
    # Collect suggestions from each phase
    suggestions.extend(_suggest_basic_build_and_test(capabilities, build_types))
    suggestions.extend(_suggest_security_and_quality(capabilities))
    suggestions.extend(_suggest_containerization(capabilities))
    suggestions.extend(_suggest_artifact_and_deployment(capabilities))
    suggestions.extend(_suggest_advanced_features(capabilities, build_types))
    
    # Fallback suggestions if workflow is already comprehensive
    if len(suggestions) == 0:
        suggestions = _get_fallback_suggestions()
    
    # Return top 3-4 most relevant suggestions
    return suggestions[:4]

def get_base_workflow_prompt(project_name: str, project_code: str = None, build_types: List[str] = None, repository_info: Dict = None) -> str:
    """Generate the base prompt for workflow generation."""
    
    prompt = f"""You are an expert GitHub Actions workflow creator. Create a professional CI/CD workflow for the project "{project_name}"."""
    
    if project_code:
        prompt += f" Use the project code '{project_code}' in the workflow name."
    
    if build_types:
        prompt += f" The detected build types are: {', '.join(build_types)}."
    
    if repository_info:
        prompt += f" Repository details: {json.dumps(repository_info, indent=2)}"
    
    prompt += """

Create a GitHub Actions workflow that includes:
1. Basic CI/CD structure (checkout, setup, build, test)
2. Appropriate triggers (push, pull_request)
3. Environment setup based on detected technologies
4. Security best practices
5. Clear job names and step descriptions

Return ONLY the YAML content for the workflow file, no markdown formatting or explanations.
The workflow should be production-ready and follow GitHub Actions best practices."""

    return prompt

def get_reusable_workflow_prompt(project_name: str, project_code: str = None, build_types: List[str] = None, repository_info: Dict = None) -> str:
    """Generate the base prompt for reusable workflow generation."""
    
    prompt = f"""You are an expert GitHub Actions reusable workflow creator. Create a professional reusable CI/CD workflow for the project "{project_name}"."""
    
    if project_code:
        prompt += f" Use the project code '{project_code}' in the workflow name."
    
    if build_types:
        prompt += f" The detected build types are: {', '.join(build_types)}."
    
    if repository_info:
        prompt += f" Repository details: {json.dumps(repository_info, indent=2)}"
    
    prompt += f"""

Create a REUSABLE GitHub Actions workflow that includes:
1. Input parameters to make the workflow flexible and reusable
2. Basic CI/CD structure (checkout, setup, build, test, container build, container push, container test)
3. Appropriate workflow_call trigger
4. Environment setup based on detected technologies
5. Security best practices
6. Clear job names and step descriptions
7. Outputs that calling workflows can use

IMPORTANT: This must be a REUSABLE workflow format with:
- on: workflow_call trigger
- inputs: section for parameters
- outputs: section for return values
- secrets: section for required secrets

Return ONLY the YAML content for the reusable workflow file, no markdown formatting or explanations.
The workflow should be production-ready and follow GitHub Actions reusable workflow best practices."""

    return prompt

def get_caller_workflow_prompt(project_name: str, project_code: str = None, reusable_workflow_content: str = "", user_name: str = "", reusable_workflow_name: str = "") -> str:
    """Generate prompt for creating a workflow that calls the reusable workflow."""
    
    prompt = f"""You are an expert GitHub Actions workflow creator. Create a standard workflow that calls the reusable workflow for project "{project_name}"."""
    
    if project_code:
        prompt += f" Use the project code '{project_code}' in the workflow name."
    
    # Determine the actual filename to reference
    reusable_filename = f"{reusable_workflow_name}.yml" if reusable_workflow_name else "reusable-workflow.yml"
    
    prompt += f"""

The reusable workflow content is:
```yaml
{reusable_workflow_content}
```

Create a standard GitHub Actions workflow that:
1. Uses appropriate triggers (push, pull_request)
2. Calls the reusable workflow using the 'uses' keyword
3. Passes appropriate inputs based on the reusable workflow's input parameters
4. References the reusable workflow from {user_name}/am-reusable-workflows/.github/workflows/{reusable_filename}
5. Uses appropriate branch reference (e.g., @develop or @main)
6. Follows GitHub Actions best practices

The workflow MUST call the reusable workflow with this EXACT syntax:
uses: {user_name}/am-reusable-workflows/.github/workflows/{reusable_filename}@develop

Return ONLY the YAML content for the standard workflow file, no markdown formatting or explanations.
The workflow should be production-ready and properly call the reusable workflow."""

    return prompt

def get_workflow_analysis_prompt(workflow_yaml: str, project_name: str, build_types: List[str] = None) -> str:
    """Generate prompt for analyzing an existing workflow and suggesting improvements."""
    
    build_context = ""
    if build_types:
        build_context = f" The project uses these technologies: {', '.join(build_types)}."
    
    return f"""You are an expert GitHub Actions workflow analyst. Analyze the following workflow for the project "{project_name}"{build_context}

Current workflow:
```yaml
{workflow_yaml}
```

Please analyze this workflow and provide improvement suggestions. Consider:

1. **Security enhancements**: CodeQL, security scanning, dependency checking
2. **Build optimizations**: Caching, parallelization, build matrix
3. **Testing improvements**: Coverage reports, multiple test environments, integration tests
4. **Deployment enhancements**: Docker builds, staging environments, rollback strategies
5. **CI/CD best practices**: Branch protection, approval workflows, notifications

For technology-specific improvements:
- **Maven/Java projects**: Suggest adding test execution, Checkstyle, PMD, packaging with Docker
- **Helm Charts**: Suggest adding helm lint, security scanning, chart testing
- **Node.js projects**: Suggest adding npm audit, ESLint, test coverage
- **Python projects**: Suggest adding pytest, pylint, security checks
- **Docker projects**: Suggest multi-stage builds, vulnerability scanning

Return ONLY a JSON object with this exact format:
{{
    "analysis": "Brief analysis of the current workflow structure and what it does",
    "enhancement_suggestions": [
        "Specific improvement suggestion 1",
        "Specific improvement suggestion 2", 
        "Specific improvement suggestion 3"
    ],
    "suggested_questions": [
        "Would you like me to add security scanning with CodeQL?",
        "Should I include Docker image building and publishing?",
        "Do you want to add test coverage reporting?"
    ]
}}

CRITICAL: Return ONLY valid JSON. No markdown, no explanatory text, just the JSON object."""

def _clean_workflow_yaml_response(workflow_yaml: str) -> str:
    """Remove markdown fences from AI-generated workflow YAML."""
    cleaned = (workflow_yaml or "").strip()
    if YAML_CODE_BLOCK in cleaned:
        return cleaned.split(YAML_CODE_BLOCK)[1].split("```")[0].strip()
    if "```" in cleaned:
        return cleaned.split("```")[1].strip()
    return cleaned

def get_structured_workflow_action_prompt(
    action: str,
    workflow_yaml: str,
    project_name: str,
    project_code: str = None,
    build_types: List[str] = None,
    repository_info: Dict = None,
    optional_instruction: str = None,
) -> str:
    """Generate a prompt that returns a full workflow for a structured AI action."""
    action_labels = {
        "generate": "Generate Workflow",
        "improve": "Improve Workflow",
        "make_reusable": "Make Reusable",
    }
    action_label = action_labels.get(action, "Improve Workflow")
    build_context = f"Detected build types: {', '.join(build_types)}." if build_types else "No detected build types were provided."
    repo_context = json.dumps(repository_info or {}, indent=2)
    instruction_context = optional_instruction.strip() if optional_instruction else "No optional user instruction."
    current_workflow = workflow_yaml or "(No existing workflow was provided.)"

    if action == "generate":
        outcome = """
Generate a complete GitHub Actions workflow tailored for the selected repositories and detected build types.
It must be suitable for multi-repository use and include sensible triggers, checkout, setup, build, and test steps.
"""
    elif action == "make_reusable":
        outcome = """
Convert the existing workflow into a reusable workflow pattern.
Remove repository-specific hardcoding, generalize inputs and secrets, and ensure it uses on.workflow_call with appropriate inputs/secrets.
"""
    else:
        outcome = """
Improve the existing workflow.
Clean up structure, update deprecated actions, improve readability, preserve intent, and apply GitHub Actions best practices.
"""

    return f"""You are an expert GitHub Actions workflow assistant.

Action: {action_label}
Project: {project_name}
Project code: {project_code or ""}
{build_context}
Repository context:
{repo_context}
Optional user instruction: {instruction_context}

Current workflow:
```yaml
{current_workflow}
```

Required outcome:
{outcome}

CRITICAL REQUIREMENTS:
- Return a FULL valid GitHub Actions workflow YAML, never a partial snippet.
- Never append content to the existing YAML. Replace the complete workflow with the updated YAML.
- Do not include markdown fences in updated_workflow.
- The YAML must start with a complete workflow structure such as name, on, and jobs.

Return ONLY this JSON object:
{{
  "updated_workflow": "FULL updated workflow YAML as a JSON string",
  "analysis": "Brief explanation of the workflow-aware changes",
  "enhancement_suggestions": ["suggestion 1", "suggestion 2"],
  "suggested_questions": ["follow-up question 1", "follow-up question 2"],
  "changes_summary": ["change 1", "change 2"]
}}"""

def get_chat_enhancement_prompt(current_workflow: str, user_message: str) -> str:
    """Generate prompt for chat-based workflow enhancement."""
    
    # Analyze current workflow capabilities to provide contextual suggestions
    capabilities = analyze_workflow_capabilities(current_workflow)
    
    return f"""You are an expert GitHub Actions workflow specialist helping to enhance an existing workflow based on user requirements. You should guide users through building a complete CI/CD pipeline progressively.

Current workflow:
```yaml
{current_workflow}
```

User request: {user_message}

WORKFLOW ANALYSIS CONTEXT:
Current workflow capabilities: {capabilities}

PROGRESSIVE CI/CD GUIDANCE:
Follow this flow when suggesting next steps:
1. Basic Build → Testing → Code Quality
2. Security Scanning → Container Building
3. Artifact Publishing → Deployment
4. Environment Management → Secrets & Variables
5. Advanced Features (monitoring, rollback, performance testing)

IMPORTANT: You must respond with ONLY a valid JSON object. Do not include any explanatory text before or after the JSON.

Please:
1. Analyze the user's request and determine what changes are needed
2. Modify the workflow YAML to implement the requested changes
3. Provide a brief explanation of what was changed showing the newly added yaml
4. Suggest 2-3 progressive follow-up questions that guide toward a complete CI/CD pipeline

Focus your suggestions on the next logical steps in the CI/CD journey. Consider what's missing and what would add the most value next.

Respond with ONLY this JSON format (no markdown, no extra text):
{{
    "updated_workflow": "the complete updated YAML workflow as a string with proper escaping",
    "explanation": "brief explanation of changes made, the yaml code example, and how it advances the CI/CD pipeline",
    "suggested_questions": ["progressive question 1", "progressive question 2", "progressive question 3"],
    "changes_summary": ["change 1: Workflow YAML Change 1", "change 2: Workflow YAML Change 2, "change 3: Workflow YAML Change 3"]
}}

CRITICAL: Return ONLY valid JSON. No markdown formatting, no explanatory text, just the JSON object."""

def get_reusable_chat_enhancement_prompt(current_workflow: str, user_message: str) -> str:
    """Generate prompt for chat-based reusable workflow enhancement."""
    
    # Analyze current workflow capabilities to provide contextual suggestions
    capabilities = analyze_workflow_capabilities(current_workflow)
    
    return f"""You are an expert GitHub Actions reusable workflow specialist helping to enhance an existing reusable workflow based on user requirements. Guide users through building comprehensive, flexible reusable workflows.

Current reusable workflow:
```yaml
{current_workflow}
```

User request: {user_message}

WORKFLOW ANALYSIS CONTEXT:
Current workflow capabilities: {capabilities}

REUSABLE WORKFLOW GUIDANCE:
Focus on making the workflow flexible and reusable:
1. Add input parameters for different environments and configurations
2. Include optional features that can be enabled/disabled via inputs
3. Provide outputs that calling workflows can use
4. Support multiple build types and deployment targets

IMPORTANT: You must respond with ONLY a valid JSON object. Do not include any explanatory text before or after the JSON.

Please enhance this REUSABLE workflow by:
1. Analyzing the user's request and determining what changes are needed
2. Modifying the reusable workflow YAML to implement the requested changes
3. Ensuring the workflow maintains proper reusable workflow structure:
   - on: workflow_call trigger
   - inputs: section for parameters
   - outputs: section for return values
   - secrets: section for required secrets
4. Adding or modifying input parameters as needed for flexibility
5. Providing a brief explanation of what was changed
6. Suggesting progressive follow-up questions that guide toward a comprehensive reusable CI/CD workflow

Respond with ONLY this JSON format (no markdown, no extra text):
{{
    "updated_workflow": "the complete updated reusable YAML workflow as a string with proper escaping",
    "explanation": "brief explanation of changes made, the yaml code example, and how it advances the CI/CD pipeline",
    "suggested_questions": ["progressive question 1", "progressive question 2", "progressive question 3"],
    "changes_summary": ["change 1: Workflow YAML Change 1", "change 2: Workflow YAML Change 2, "change 3: Workflow YAML Change 3"]
}}

CRITICAL: Return ONLY valid JSON. No markdown formatting, no explanatory text, just the JSON object."""

async def call_openai_completion(prompt: str, max_tokens: int = 2000) -> str:
    """Call OpenAI API with error handling."""
    try:
        if not openai.api_key:
            raise HTTPException(
                status_code=500, 
                detail="OpenAI API key not configured. Please set OPENAI_API_KEY environment variable."
            )
        
        client = openai.OpenAI(api_key=openai.api_key)
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a GitHub Actions workflow expert."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.7
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

@router.post("/api/ai/generate-workflow", response_model=WorkflowGenerationResponse)
async def generate_workflow_with_ai(request: WorkflowGenerationRequest):
    """Generate an initial workflow using AI based on project requirements."""
    
    try:
        # Generate session ID
        session_id = f"{request.user}_{request.project_name}_{len(conversation_sessions)}"
        
        # Create base prompt
        prompt = get_base_workflow_prompt(
            project_name=request.project_name,
            project_code=request.project_code,
            build_types=request.build_types,
            repository_info=request.repository_info
        )
        
        if request.user_requirements:
            prompt += f"\n\nAdditional user requirements: {request.user_requirements}"
        
        # Get AI response
        workflow_yaml = await call_openai_completion(prompt)
        
        # Clean up the response (remove markdown formatting if present)
        if YAML_CODE_BLOCK in workflow_yaml:
            workflow_yaml = workflow_yaml.split(YAML_CODE_BLOCK)[1].split("```")[0].strip()
        elif "```" in workflow_yaml:
            workflow_yaml = workflow_yaml.split("```")[1].strip()
        
        # Store session data
        conversation_sessions[session_id] = {
            "user": request.user,
            "project_name": request.project_name,
            "project_code": request.project_code,
            "initial_workflow": workflow_yaml,
            "current_workflow": workflow_yaml,
            "conversation_history": [],
            "build_types": request.build_types or []
        }
        
        # Generate progressive suggested follow-up questions based on workflow content
        suggested_questions = generate_progressive_suggestions(workflow_yaml, request.build_types)
        
        explanation = f"Generated initial CI/CD workflow for {request.project_name}. The workflow includes basic build and test steps based on your project requirements. I can help you extend this into a complete CI/CD pipeline."
        
        return WorkflowGenerationResponse(
            workflow_yaml=workflow_yaml,
            session_id=session_id,
            suggested_questions=suggested_questions,
            explanation=explanation
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating workflow: {str(e)}")

@router.post("/api/ai/generate-reusable-workflow", response_model=ReusableWorkflowGenerationResponse)
async def generate_reusable_workflow_with_ai(request: ReusableWorkflowGenerationRequest):
    """Generate a reusable workflow and companion regular workflow using AI."""
    
    try:
        # Generate session ID
        session_id = f"{request.user}_{request.project_name}_reusable_{len(conversation_sessions)}"
        
        # Create reusable workflow prompt
        reusable_prompt = get_reusable_workflow_prompt(
            project_name=request.project_name,
            project_code=request.project_code,
            build_types=request.build_types,
            repository_info=request.repository_info
        )
        
        if request.user_requirements:
            reusable_prompt += f"\n\nAdditional user requirements: {request.user_requirements}"
        
        # Get AI response for reusable workflow
        reusable_workflow_yaml = await call_openai_completion(reusable_prompt)
        
        # Clean up the response (remove markdown formatting if present)
        if YAML_CODE_BLOCK in reusable_workflow_yaml:
            reusable_workflow_yaml = reusable_workflow_yaml.split(YAML_CODE_BLOCK)[1].split("```")[0].strip()
        elif "```" in reusable_workflow_yaml:
            reusable_workflow_yaml = reusable_workflow_yaml.split("```")[1].strip()
        
        # Generate the caller workflow
        caller_prompt = get_caller_workflow_prompt(
            project_name=request.project_name,
            project_code=request.project_code,
            reusable_workflow_content=reusable_workflow_yaml,
            user_name=request.user,
            reusable_workflow_name=request.reusable_workflow_name or "ai-reusable-workflow"
        )
        
        # Get AI response for caller workflow
        caller_workflow_yaml = await call_openai_completion(caller_prompt)
        
        # Clean up the caller workflow response
        if YAML_CODE_BLOCK in caller_workflow_yaml:
            caller_workflow_yaml = caller_workflow_yaml.split(YAML_CODE_BLOCK)[1].split("```")[0].strip()
        elif "```" in caller_workflow_yaml:
            caller_workflow_yaml = caller_workflow_yaml.split("```")[1].strip()
        
        # Store session data
        conversation_sessions[session_id] = {
            "user": request.user,
            "project_name": request.project_name,
            "project_code": request.project_code,
            "initial_reusable_workflow": reusable_workflow_yaml,
            "initial_caller_workflow": caller_workflow_yaml,
            "current_reusable_workflow": reusable_workflow_yaml,
            "current_caller_workflow": caller_workflow_yaml,
            "conversation_history": [],
            "build_types": request.build_types or [],
            "workflow_type": "reusable",
            "reusable_workflow_name": request.reusable_workflow_name or "ai-reusable-workflow"
        }
        
        # Generate progressive suggested follow-up questions for reusable workflows
        suggested_questions = generate_progressive_suggestions(reusable_workflow_yaml, request.build_types)
        # Add reusable-workflow specific suggestions
        reusable_specific = [
            "Add input parameters for environment-specific configurations",
            "Include optional security scanning inputs",
            "Add support for different deployment targets"
        ]
        # Combine and limit to 4 suggestions
        suggested_questions = (suggested_questions + reusable_specific)[:4]
        
        explanation = f"Generated reusable CI/CD workflow for {request.project_name} with a companion workflow that calls it. The reusable workflow includes input parameters for flexibility and can be reused across multiple projects. I can help you extend this into a comprehensive CI/CD pipeline."
        
        return ReusableWorkflowGenerationResponse(
            reusable_workflow_yaml=reusable_workflow_yaml,
            caller_workflow_yaml=caller_workflow_yaml,
            session_id=session_id,
            suggested_questions=suggested_questions,
            explanation=explanation
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating reusable workflow: {str(e)}")

@router.post("/api/ai/edit-workflow", response_model=WorkflowEditResponse)
async def edit_workflow_with_ai(request: WorkflowEditRequest):
    """Run a structured AI workflow action and return a full workflow preview."""
    
    try:
        # Generate session ID for the editing session
        session_id = f"{request.user}_{request.project_name}_edit_{len(conversation_sessions)}"
        action = request.action if request.action in VALID_WORKFLOW_ACTIONS else "improve"
        
        prompt = get_structured_workflow_action_prompt(
            action,
            request.current_workflow,
            request.project_name,
            request.project_code,
            request.build_types or [],
            request.repository_info,
            request.optional_instruction,
        )
        
        print(f"🤖 Running structured AI workflow action '{action}' with prompt: {prompt[:200]}...")
        
        ai_response = await call_openai_completion(prompt, max_tokens=3000)
        
        print(f"🤖 AI Workflow Action Response: {ai_response[:200]}...")
        
        # Parse JSON response
        try:
            analysis_data = json.loads(ai_response)
            print("✅ Direct JSON parsing successful for workflow analysis")
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing failed, attempting extraction: {e}")
            analysis_data = {
                "updated_workflow": _clean_workflow_yaml_response(ai_response) or request.current_workflow,
                "analysis": f"I prepared a full workflow update for {request.workflow_name}.",
                "enhancement_suggestions": [
                    "Review the generated YAML before applying it",
                    "Run workflow validation after saving"
                ],
                "suggested_questions": [
                    "Should I add a tests step?",
                    "Should I pin additional action versions?"
                ],
                "changes_summary": []
            }
            # Try to extract JSON from response
            start_idx = ai_response.find('{')
            end_idx = ai_response.rfind('}') + 1
            if start_idx != -1 and end_idx > start_idx:
                try:
                    analysis_data = json.loads(ai_response[start_idx:end_idx])
                    print("✅ JSON extraction successful")
                except json.JSONDecodeError:
                    print("⚠️ Using fallback workflow response")
        
        # Store session data for future chat interactions
        conversation_sessions[session_id] = {
            "user": request.user,
            "project_name": request.project_name,
            "project_code": request.project_code,
            "workflow_name": request.workflow_name,
            "initial_workflow": request.current_workflow,
            "current_workflow": request.current_workflow,
            "conversation_history": [],
            "build_types": request.build_types or [],
            "mode": "edit",
            "action": action,
        }
        
        # Extract data from analysis
        workflow_analysis = analysis_data.get("analysis", "Workflow analysis completed")
        updated_workflow = _clean_workflow_yaml_response(analysis_data.get("updated_workflow", ""))
        if not updated_workflow:
            updated_workflow = request.current_workflow
        enhancement_suggestions = analysis_data.get("enhancement_suggestions", [])
        suggested_questions = analysis_data.get("suggested_questions", [
            "How would you like to improve this workflow?",
            "What additional features should I add?",
            "Would you like me to optimize the existing steps?"
        ])
        changes_summary = analysis_data.get("changes_summary", [])
        conversation_sessions[session_id]["current_workflow"] = updated_workflow
        
        return WorkflowEditResponse(
            workflow_analysis=workflow_analysis,
            updated_workflow=updated_workflow,
            session_id=session_id,
            suggested_questions=suggested_questions,
            enhancement_suggestions=enhancement_suggestions,
            changes_summary=changes_summary,
        )
        
    except Exception as e:
        print(f"❌ Error in edit_workflow_with_ai: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze workflow: {str(e)}")

def _validate_session_and_get_context(request: ChatInteractionRequest):
    """Validate session exists and extract session context."""
    if request.session_id not in conversation_sessions:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND_MESSAGE)
    
    session = conversation_sessions[request.session_id]
    is_reusable_session = session.get("workflow_type") == "reusable"
    
    return session, is_reusable_session

def _get_workflow_content_and_prompt(request: ChatInteractionRequest, session: Dict, is_reusable_session: bool):
    """Get workflow content and generate appropriate prompt based on workflow type."""
    if is_reusable_session:
        current_workflow = request.current_workflow or session["current_reusable_workflow"]
        prompt = get_reusable_chat_enhancement_prompt(current_workflow, request.user_message)
    else:
        current_workflow = request.current_workflow or session["current_workflow"]
        prompt = get_chat_enhancement_prompt(current_workflow, request.user_message)
    
    return current_workflow, prompt

async def _process_ai_response(prompt: str, current_workflow: str):
    """Get AI response and parse it with error handling."""
    ai_response = await call_openai_completion(prompt, max_tokens=2500)
    
    # Debug output
    print(f"🤖 AI Raw Response: {ai_response[:200]}...")
    
    # Parse JSON response with improved error handling
    try:
        response_data = json.loads(ai_response)
        print("✅ Direct JSON parsing successful")
    except json.JSONDecodeError as e:
        print(f"⚠️  Direct JSON parsing failed: {e}")
        response_data = extract_json_from_response(ai_response, current_workflow)
        print("🔧 Using extracted/fallback response")
    
    return response_data

async def _update_session_workflows(session: Dict, response_data: Dict, current_workflow: str, is_reusable_session: bool):
    """Update session workflows based on workflow type."""
    if is_reusable_session:
        updated_reusable_workflow = response_data.get("updated_workflow", current_workflow)
        session["current_reusable_workflow"] = updated_reusable_workflow
        
        # Regenerate caller workflow if reusable workflow was updated
        if updated_reusable_workflow != current_workflow:
            caller_prompt = get_caller_workflow_prompt(
                project_name=session["project_name"],
                project_code=session["project_code"],
                reusable_workflow_content=updated_reusable_workflow,
                user_name=session["user"],
                reusable_workflow_name=session.get("reusable_workflow_name", "ai-reusable-workflow")
            )
            updated_caller_workflow = await call_openai_completion(caller_prompt)
            
            # Clean up caller workflow response
            if YAML_CODE_BLOCK in updated_caller_workflow:
                updated_caller_workflow = updated_caller_workflow.split(YAML_CODE_BLOCK)[1].split("```")[0].strip()
            elif "```" in updated_caller_workflow:
                updated_caller_workflow = updated_caller_workflow.split("```")[1].strip()
            
            session["current_caller_workflow"] = updated_caller_workflow
    else:
        session["current_workflow"] = response_data.get("updated_workflow", current_workflow)

def _update_conversation_history(session: Dict, request: ChatInteractionRequest, response_data: Dict):
    """Update conversation history with current interaction."""
    session["conversation_history"].append({
        "user_message": request.user_message,
        "ai_response": response_data.get("explanation", ""),
        "changes": response_data.get("changes_summary", [])
    })

def _process_suggestions(response_data: Dict, current_workflow: str, session: Dict):
    """Process and deduplicate suggestions from AI and progressive enhancement."""
    ai_suggestions = response_data.get("suggested_questions", [])
    updated_workflow = response_data.get("updated_workflow", current_workflow)
    build_types = session.get("build_types", [])
    
    # Generate additional progressive suggestions
    progressive_suggestions = generate_progressive_suggestions(updated_workflow, build_types)
    
    # Combine and deduplicate suggestions
    all_suggestions = ai_suggestions + progressive_suggestions
    unique_suggestions = []
    seen = set()
    
    for suggestion in all_suggestions:
        suggestion_lower = suggestion.lower()
        if suggestion_lower not in seen:
            unique_suggestions.append(suggestion)
            seen.add(suggestion_lower)
    
    return unique_suggestions[:4], updated_workflow

@router.post("/api/ai/chat-interaction", response_model=ChatInteractionResponse)
async def chat_interaction(request: ChatInteractionRequest):
    """Handle interactive chat to enhance the workflow."""
    
    try:
        # Validate session and get context
        session, is_reusable_session = _validate_session_and_get_context(request)
        
        # Get workflow content and generate prompt
        current_workflow, prompt = _get_workflow_content_and_prompt(request, session, is_reusable_session)
        
        # Process AI response
        response_data = await _process_ai_response(prompt, current_workflow)
        
        # Update session workflows
        await _update_session_workflows(session, response_data, current_workflow, is_reusable_session)
        
        # Update conversation history
        _update_conversation_history(session, request, response_data)
        
        # Process and generate suggestions
        final_suggestions, updated_workflow = _process_suggestions(response_data, current_workflow, session)
        
        return ChatInteractionResponse(
            response_message=response_data.get("explanation", "Workflow updated successfully."),
            updated_workflow=updated_workflow,
            suggested_questions=final_suggestions,
            workflow_updates=response_data.get("changes_summary", [])
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat interaction: {str(e)}")

@router.get("/api/ai/session/{session_id}")
async def get_session_info(session_id: str):
    """Get information about a chat session."""
    
    if session_id not in conversation_sessions:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND_MESSAGE)
    
    session = conversation_sessions[session_id]
    
    return {
        "session_id": session_id,
        "project_name": session["project_name"],
        "project_code": session["project_code"],
        "build_types": session["build_types"],
        "conversation_length": len(session["conversation_history"]),
        "current_workflow_length": len(session.get("current_workflow", "")),
        "workflow_type": session.get("workflow_type", "regular")
    }

@router.get("/api/ai/session/{session_id}/workflows")
async def get_session_workflows(session_id: str):
    """Get both reusable and caller workflows from a reusable workflow session."""
    
    if session_id not in conversation_sessions:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND_MESSAGE)
    
    session = conversation_sessions[session_id]
    
    if session.get("workflow_type") != "reusable":
        raise HTTPException(status_code=400, detail="Session is not a reusable workflow session")
    
    return {
        "reusable_workflow": session.get("current_reusable_workflow", ""),
        "caller_workflow": session.get("current_caller_workflow", ""),
        "session_id": session_id
    }

@router.delete("/api/ai/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    
    if session_id not in conversation_sessions:
        raise HTTPException(status_code=404, detail=SESSION_NOT_FOUND_MESSAGE)
    
    del conversation_sessions[session_id]
    
    return {"message": "Session deleted successfully"}

@router.get("/api/ai/test")
async def test_ai_integration():
    """Test endpoint to verify AI integration is working."""
    
    try:
        if not openai.api_key:
            return {
                "status": "error",
                "message": "OpenAI API key not configured",
                "suggestion": "Set OPENAI_API_KEY environment variable"
            }
        
        # Simple test call
        test_response = await call_openai_completion("Say 'AI integration working' in exactly those words.", max_tokens=50)
        
        return {
            "status": "success",
            "message": "AI integration working correctly",
            "test_response": test_response
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"AI integration test failed: {str(e)}"
        }
