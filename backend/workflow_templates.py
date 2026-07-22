"""
Workflow Template Generator Module

This module provides template generation functionality for reusable workflows,
including standard workflows that call reusable workflows and the reusable 
workflow templates themselves.
"""

from typing import Dict, Optional

from action_versions import ACTION_VERSIONS


def generate_standard_workflow_template(
    user_org: str, 
    project_code: Optional[str] = None,
    build_type: Optional[str] = None,
    reusable_repo: Optional[str] = None
) -> str:
    """
    Generate a standard workflow template that calls a reusable workflow.
    
    Args:
        user_org: GitHub username or organization
        project_code: Project code for workflow naming (optional)
        build_type: Build type for customization (optional)
        reusable_repo: Full name (owner/repo) of the reusable workflow repository.
                       Defaults to ``{user_org}/am-reuseable-workflow``.
        
    Returns:
        YAML string for the standard workflow
    """
    
    # Determine workflow name suffix based on build type
    workflow_suffix = ""
    if build_type and build_type != "generic":
        workflow_suffix = f"-{build_type}"
    
    # Use project code if available for naming
    workflow_name = "Standard Pipeline"
    if project_code:
        workflow_name = f"{project_code} Pipeline"
    
    # Build the workflow filename with project code
    workflow_filename = "_main-workflow"
    if project_code:
        workflow_filename = f"{project_code}_main-workflow"

    # Use the provided reusable repo name or fall back to the default
    if not reusable_repo:
        reusable_repo = f"{user_org}/am-reuseable-workflow"
    
    template = f"""name: {workflow_name}

on:
  workflow_dispatch:
  push:
    paths-ignore:
      - '.github/workflows/**'
      - 'renovate.json'
      - 'README.md'
    branches:
      - 'main'
      - 'develop'
      - 'feat/**'
  
jobs:
  build:
    uses: {reusable_repo}/.github/workflows/AM_{workflow_filename}{workflow_suffix}.yml@main
    secrets: inherit"""
    
    return template.strip()


def generate_reusable_workflow_template(
    build_type: Optional[str] = None,
    project_code: Optional[str] = None
) -> str:
    """
    Generate a reusable workflow template that can be called by standard workflows.
    
    Args:
        build_type: Build type for the workflow (maven, npm, dotnet, etc.)
        project_code: Project code for workflow naming (optional)
        
    Returns:
        YAML string for the reusable workflow
    """
    
    # Determine workflow name and build workflow reference
    workflow_name = "RX Build"
    build_workflow_name = "am-generic-build"
    
    if build_type and build_type != "generic":
        workflow_name = f"RX {build_type.title()} Build"
        build_workflow_name = f"am-{build_type}-build"
    
    if project_code:
        workflow_name = f"{project_code} {workflow_name}"
    
    # Build the workflow filename with project code
    build_workflow_filename = f"_{build_workflow_name}"
    if project_code:
        build_workflow_filename = f"{project_code}_{build_workflow_name}"
    
    template = f"""name: {workflow_name}

on:
  workflow_call:
    secrets:
      token:
        required: false
jobs:
  build:
    uses: ./.github/workflows/AM_{build_workflow_filename}.yml
    secrets: inherit"""
    
    return template.strip()


def generate_build_specific_workflow_template(build_type: str) -> str:
    """
    Generate a build-specific workflow template for the reusable workflow repository.
    
    Args:
        build_type: The build type (maven, npm, dotnet, etc.)
        
    Returns:
        YAML string for the build-specific workflow
    """
    
    templates = {
        "maven": f"""name: Maven Build

on:
  workflow_call:
    secrets:
      token:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Set up JDK 11
      uses: actions/setup-java@{ACTION_VERSIONS['actions/setup-java']}
      with:
        java-version: '11'
        distribution: 'temurin'
    - name: Cache Maven packages
      uses: actions/cache@{ACTION_VERSIONS['actions/cache']}
      with:
        path: ~/.m2
        key: ${{{{ runner.os }}}}-m2-${{{{ hashFiles('**/pom.xml') }}}}
        restore-keys: ${{{{ runner.os }}}}-m2
    - name: Build with Maven
      run: mvn clean compile
    - name: Run tests
      run: mvn test
    - name: Package
      run: mvn package""",

        "gradle": f"""name: Gradle Build

on:
  workflow_call:
    secrets:
      token:
        required: false
  

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Set up JDK 11
      uses: actions/setup-java@{ACTION_VERSIONS['actions/setup-java']}
      with:
        java-version: '11'
        distribution: 'temurin'
    - name: Grant execute permission for gradlew
      run: chmod +x gradlew
    - name: Cache Gradle packages
      uses: actions/cache@{ACTION_VERSIONS['actions/cache']}
      with:
        path: |
          ~/.gradle/caches
          ~/.gradle/wrapper
        key: ${{{{ runner.os }}}}-gradle-${{{{ hashFiles('**/*.gradle*', '**/gradle-wrapper.properties') }}}}
        restore-keys: |
          ${{{{ runner.os }}}}-gradle-
    - name: Build with Gradle
      run: ./gradlew build
    - name: Run tests
      run: ./gradlew test""",

        "npm": f"""name: Node.js Build

on:
  workflow_call:
    secrets:
      token:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Use Node.js
      uses: actions/setup-node@{ACTION_VERSIONS['actions/setup-node']}
      with:
        node-version: '18'
        cache: 'npm'
    - name: Install dependencies
      run: npm ci
    - name: Build
      run: npm run build --if-present
    - name: Run tests
      run: npm test""",

        "dotnet": f"""name: .NET Build

on:
  workflow_call:
    secrets:
      token:
        required: false
        
jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Setup .NET
      uses: actions/setup-dotnet@{ACTION_VERSIONS['actions/setup-dotnet']}
      with:
        dotnet-version: 6.0.x
    - name: Restore dependencies
      run: dotnet restore
    - name: Build
      run: dotnet build --no-restore
    - name: Test
      run: dotnet test --no-build --verbosity normal""",

        "python": f"""name: Python Build

on:
  workflow_call:
    secrets:
      token:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Set up Python
      uses: actions/setup-python@{ACTION_VERSIONS['actions/setup-python']}
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    - name: Run tests
      run: |
        python -m pytest""",

        "go": f"""name: Go Build

on:
  workflow_call:
    secrets:
      token:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - name: Checkout code
      uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Set up Go
      uses: actions/setup-go@{ACTION_VERSIONS['actions/setup-go']}
      with:
        go-version: 1.19
    - name: Build
      run: go build -v ./...
    - name: Test
      run: go test -v ./...""",

        "generic": """name: Generic Build

on:
  workflow_call:
    secrets:
      token:
        required: false

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - name: Build placeholder
      run: |
        echo "Add your build steps here"
        echo "This is a generic template - customize based on your project needs"
        
    - name: Test placeholder
      run: |
        echo "Add your test steps here"
        echo "Configure your specific testing framework and commands"
        """
    }
    
    return templates.get(build_type, templates["generic"]).strip()


def get_available_template_types() -> Dict[str, str]:
    """
    Get available template types and their descriptions.
    
    Returns:
        Dictionary mapping template types to descriptions
    """
    return {
        "maven": "Java Maven project workflow templates",
        "gradle": "Java Gradle project workflow templates", 
        "npm": "Node.js/npm project workflow templates",
        "dotnet": ".NET project workflow templates",
        "python": "Python project workflow templates",
        "go": "Go project workflow templates",
        "generic": "Generic workflow templates"
    }


def generate_template_set(
    user_org: str,
    build_type: str = "generic",
    project_code: Optional[str] = None
) -> Dict[str, str]:
    """
    Generate a complete set of workflow templates for reusable workflows.
    
    Args:
        user_org: GitHub username or organization
        build_type: Build type for the templates
        project_code: Project code for workflow naming (optional)
        
    Returns:
        Dictionary containing all generated templates
    """
    return {
        "standard_workflow": generate_standard_workflow_template(user_org, project_code, build_type),
        "reusable_workflow": generate_reusable_workflow_template(build_type, project_code),
        "build_workflow": generate_build_specific_workflow_template(build_type)
    }
