"""
Build Type Detection Module

This module provides functionality to detect build types in GitHub repositories
by analyzing the presence of specific files and configurations.
"""

import requests
from typing import Dict, List, Optional
from dataclasses import dataclass

from action_versions import ACTION_VERSIONS


@dataclass
class BuildType:
    """Represents a detected build type"""
    name: str
    technology: str
    confidence: float
    files_found: List[str]
    suggested_workflow: Optional[str] = None


class BuildTypeDetector:
    """Detects build types in GitHub repositories"""
    
    # Build type definitions with file patterns and confidence scores
    BUILD_PATTERNS = {
        "maven": {
            "technology": "Java",
            "files": ["pom.xml"],
            "confidence": 0.9
        },
        "gradle": {
            "technology": "Java", 
            "files": ["build.gradle", "build.gradle.kts", "gradlew"],
            "confidence": 0.9
        },
        "ant": {
            "technology": "Java",
            "files": ["build.xml"],
            "confidence": 0.8
        },
        "npm": {
            "technology": "Node.js",
            "files": ["package.json"],
            "confidence": 0.9
        },
        "dotnet": {
            "technology": "C#/.NET",
            "files": [".csproj", ".sln", ".fsproj", ".vbproj"],
            "confidence": 0.9
        },
        "python": {
            "technology": "Python",
            "files": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
            "confidence": 0.8
        },
        "go": {
            "technology": "Go",
            "files": ["go.mod", "go.sum"],
            "confidence": 0.9
        },
        "rust": {
            "technology": "Rust",
            "files": ["Cargo.toml"],
            "confidence": 0.9
        }
    }

    def __init__(self, github_token: str):
        self.github_token = github_token
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            self.headers["Authorization"] = f"token {github_token}"

    def detect_build_types(self, owner: str, repo: str) -> List[BuildType]:
        """
        Detect build types in a GitHub repository
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            List of detected build types
        """
        try:
            # Get repository contents from root directory
            contents = self._get_repo_contents(owner, repo)
            if not contents:
                return []
            
            detected_types = []
            
            # Check each build pattern
            for build_name, pattern in self.BUILD_PATTERNS.items():
                found_files = self._check_files_exist(contents, pattern["files"])
                
                if found_files:
                    build_type = BuildType(
                        name=build_name,
                        technology=pattern["technology"],
                        confidence=pattern["confidence"],
                        files_found=found_files,
                        suggested_workflow=self._get_suggested_workflow(build_name)
                    )
                    detected_types.append(build_type)
            
            # Sort by confidence score
            detected_types.sort(key=lambda x: x.confidence, reverse=True)
            
            return detected_types
            
        except Exception as e:
            print(f"Error detecting build types: {e}")
            return []

    def _get_repo_contents(self, owner: str, repo: str, path: str = "") -> Optional[List[Dict]]:
        """Get repository contents from GitHub API"""
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            print(f"Error fetching repo contents: {e}")
            return None

    def _check_files_exist(self, contents: List[Dict], target_files: List[str]) -> List[str]:
        """Check which target files exist in the repository contents"""
        found_files = []
        
        # Get list of files and directories in the repo
        file_names = [item["name"] for item in contents if isinstance(contents, list)]
        
        for target_file in target_files:
            # Check for exact matches or file extension matches
            if target_file in file_names:
                found_files.append(target_file)
            elif target_file.startswith('.'):
                # Check for files with specific extensions
                extension_matches = [f for f in file_names if f.endswith(target_file)]
                found_files.extend(extension_matches)
        
        return found_files

    def _get_suggested_workflow(self, build_type: str) -> str:
        """Get suggested workflow YAML for a build type"""
        workflows = {
            "maven": f"""
name: Java CI with Maven

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
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
    - name: Run tests
      run: mvn clean test
    - name: Build with Maven
      run: mvn clean compile package
""".strip(),

            "gradle": f"""
name: Java CI with Gradle

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Set up JDK 11
      uses: actions/setup-java@{ACTION_VERSIONS['actions/setup-java']}
      with:
        java-version: '11'
        distribution: 'temurin'
    - name: Grant execute permission for gradlew
      run: chmod +x gradlew
    - name: Build with Gradle
      run: ./gradlew build
    - name: Run tests
      run: ./gradlew test
""".strip(),

            "npm": f"""
name: Node.js CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest

    strategy:
      matrix:
        node-version: [16.x, 18.x, 20.x]

    steps:
    - uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Use Node.js ${{{{ matrix.node-version }}}}
      uses: actions/setup-node@{ACTION_VERSIONS['actions/setup-node']}
      with:
        node-version: ${{{{ matrix.node-version }}}}
        cache: 'npm'
    - run: npm ci
    - run: npm run build --if-present
    - run: npm test
""".strip(),

            "dotnet": f"""
name: .NET CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Setup .NET
      uses: actions/setup-dotnet@{ACTION_VERSIONS['actions/setup-dotnet']}
      with:
        dotnet-version: 6.0.x
    - name: Restore dependencies
      run: dotnet restore
    - name: Build
      run: dotnet build --no-restore
    - name: Test
      run: dotnet test --no-build --verbosity normal
""".strip(),

            "python": f"""
name: Python CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest

    strategy:
      matrix:
        python-version: [3.8, 3.9, "3.10"]

    steps:
    - uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Set up Python ${{{{ matrix.python-version }}}}
      uses: actions/setup-python@{ACTION_VERSIONS['actions/setup-python']}
      with:
        python-version: ${{{{ matrix.python-version }}}}
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    - name: Run tests
      run: |
        python -m pytest
""".strip(),

            "go": f"""
name: Go CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Set up Go
      uses: actions/setup-go@{ACTION_VERSIONS['actions/setup-go']}
      with:
        go-version: 1.19
    - name: Build
      run: go build -v ./...
    - name: Test
      run: go test -v ./...
""".strip(),

            "rust": f"""
name: Rust CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@{ACTION_VERSIONS['actions/checkout']}
    - name: Install Rust
      uses: dtolnay/rust-toolchain@stable
    - name: Build
      run: cargo build --verbose
    - name: Run tests
      run: cargo test --verbose
""".strip()
        }
        
        return workflows.get(build_type, "")