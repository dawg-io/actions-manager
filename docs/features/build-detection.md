---
layout: default
title: Build Detection
parent: Features
nav_order: 9
---

# Build Detection
{: .no_toc }

Automatically detect build types and suggest workflow templates for repositories by analyzing project files.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Overview

The build detection feature analyzes GitHub repositories to identify their build systems and programming languages by scanning for characteristic configuration files. When a build type is detected, ActionsManager provides pre-configured GitHub Actions workflow templates optimized for that technology stack.

This feature helps teams quickly bootstrap CI/CD workflows without manually writing YAML from scratch, ensuring consistency and best practices across repositories.

## How Build Detection Works

Build detection operates by:

1. **Scanning repository contents** — The detector examines the root directory of a GitHub repository through the GitHub API
2. **Pattern matching** — It looks for specific files that identify build tools (e.g., `pom.xml` for Maven, `package.json` for npm)
3. **Confidence scoring** — Each detected build type receives a confidence score (0.0 to 1.0) based on the specificity of the matched files
4. **Workflow template generation** — For each detected build type, a ready-to-use GitHub Actions workflow template is provided

## Supported Build Types

ActionsManager can detect and provide workflow templates for the following build systems and languages:

### Java Ecosystem

| Build Type | Technology | Detection Files | Confidence |
|------------|-----------|----------------|------------|
| **Maven** | Java | `pom.xml` | 0.9 |
| **Gradle** | Java | `build.gradle`, `build.gradle.kts`, `gradlew` | 0.9 |
| **Ant** | Java | `build.xml` | 0.8 |

### JavaScript/Node.js

| Build Type | Technology | Detection Files | Confidence |
|------------|-----------|----------------|------------|
| **npm** | Node.js | `package.json` | 0.9 |

### .NET

| Build Type | Technology | Detection Files | Confidence |
|------------|-----------|----------------|------------|
| **dotnet** | C#/.NET | `.csproj`, `.sln`, `.fsproj`, `.vbproj` | 0.9 |

### Python

| Build Type | Technology | Detection Files | Confidence |
|------------|-----------|----------------|------------|
| **python** | Python | `requirements.txt`, `setup.py`, `pyproject.toml`, `Pipfile` | 0.8 |

### Go

| Build Type | Technology | Detection Files | Confidence |
|------------|-----------|----------------|------------|
| **go** | Go | `go.mod`, `go.sum` | 0.9 |

### Rust

| Build Type | Technology | Detection Files | Confidence |
|------------|-----------|----------------|------------|
| **rust** | Rust | `Cargo.toml` | 0.9 |

## Confidence Scores

Build types are assigned confidence scores to help prioritize when multiple build systems are detected in the same repository:

- **0.9** — High confidence (unique, definitive markers like `Cargo.toml` or `go.mod`)
- **0.8** — Medium-high confidence (common patterns that may have slight ambiguity like Python dependency files)
- **0.7 or lower** — Lower confidence (less specific markers)

When multiple build types are detected, results are sorted by confidence score in descending order, and the highest confidence match is typically used as the default.

## Using Build Detection

### From the Web UI

When creating or editing a workflow in ActionsManager:

1. Navigate to your project workspace
2. Click **Add Workflow** → **Regular Workflow**
3. Select **Detect Build Types** from the workflow creation options
4. ActionsManager will scan the selected repository and present:
   - All detected build types with their confidence scores
   - The detected files that matched each pattern
   - A preview of the suggested workflow template
5. Choose a detected build type or select a different one if multiple were found
6. The workflow editor opens with a pre-populated, ready-to-customize workflow

### Via API

#### Detect Build Types

Detect all build types in a repository:

```http
GET /api/repos/detect-build-type/{user}/{owner}/{repo}
```

**Response:**

```json
{
  "repository": "myorg/backend-service",
  "detected_build_types": [
    {
      "name": "maven",
      "technology": "Java",
      "confidence": 0.9,
      "files_found": ["pom.xml"],
      "suggested_workflow": "name: Java CI with Maven\n..."
    },
    {
      "name": "docker",
      "technology": "Docker",
      "confidence": 0.8,
      "files_found": ["Dockerfile"],
      "suggested_workflow": "name: Docker Build\n..."
    }
  ],
  "total_detected": 2
}
```

#### Get Suggested Workflow

Get a workflow template for a specific build type or auto-detect and return the highest confidence match:

```http
GET /api/repos/suggest-workflow/{user}/{owner}/{repo}?build_type=maven
```

**Optional Query Parameter:**
- `build_type` — If omitted, automatically detects and returns the highest confidence build type

**Response (with specific build type):**

```json
{
  "repository": "myorg/backend-service",
  "build_type": "maven",
  "workflow": "name: Java CI with Maven\n\non:\n  push:\n..."
}
```

**Response (auto-detected):**

```json
{
  "repository": "myorg/backend-service",
  "detected_build_type": "maven",
  "technology": "Java",
  "confidence": 0.9,
  "files_found": ["pom.xml"],
  "workflow": "name: Java CI with Maven\n\non:\n  push:\n..."
}
```

## Workflow Templates

### Maven (Java)

```yaml
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
    - uses: actions/checkout@v3
    - name: Set up JDK 11
      uses: actions/setup-java@v3
      with:
        java-version: '11'
        distribution: 'temurin'
    - name: Cache Maven packages
      uses: actions/cache@v3
      with:
        path: ~/.m2
        key: ${{ runner.os }}-m2-${{ hashFiles('**/pom.xml') }}
    - name: Run tests
      run: mvn clean test
    - name: Build with Maven
      run: mvn clean compile package
```

### Gradle (Java)

```yaml
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
    - uses: actions/checkout@v3
    - name: Set up JDK 11
      uses: actions/setup-java@v3
      with:
        java-version: '11'
        distribution: 'temurin'
    - name: Grant execute permission for gradlew
      run: chmod +x gradlew
    - name: Build with Gradle
      run: ./gradlew build
    - name: Run tests
      run: ./gradlew test
```

### npm (Node.js)

```yaml
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
    - uses: actions/checkout@v3
    - name: Use Node.js ${{ matrix.node-version }}
      uses: actions/setup-node@v3
      with:
        node-version: ${{ matrix.node-version }}
        cache: 'npm'
    - run: npm ci
    - run: npm run build --if-present
    - run: npm test
```

### .NET

```yaml
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
    - uses: actions/checkout@v3
    - name: Setup .NET
      uses: actions/setup-dotnet@v3
      with:
        dotnet-version: 6.0.x
    - name: Restore dependencies
      run: dotnet restore
    - name: Build
      run: dotnet build --no-restore
    - name: Test
      run: dotnet test --no-build --verbosity normal
```

### Python

```yaml
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
    - uses: actions/checkout@v3
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    - name: Run tests
      run: |
        python -m pytest
```

### Go

```yaml
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
    - uses: actions/checkout@v3
    - name: Set up Go
      uses: actions/setup-go@v3
      with:
        go-version: 1.19
    - name: Build
      run: go build -v ./...
    - name: Test
      run: go test -v ./...
```

### Rust

```yaml
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
    - uses: actions/checkout@v3
    - name: Install Rust
      uses: actions-rs/toolchain@v1
      with:
        toolchain: stable
    - name: Build
      uses: actions-rs/cargo@v1
      with:
        command: build
    - name: Run tests
      uses: actions-rs/cargo@v1
      with:
        command: test
```

## Customizing Generated Workflows

The provided templates are starting points designed to work for common project structures. You should customize them based on your project's specific needs:

- **Adjust branch triggers** — Add or remove branches in the `on.push.branches` and `on.pull_request.branches` lists
- **Modify version matrices** — Update language/runtime versions to match your project requirements
- **Add deployment steps** — Include deployment, artifact upload, or release publication steps
- **Integrate security scanning** — Add CodeQL, Dependabot, or third-party security tools
- **Configure caching** — Optimize build times with additional caching strategies
- **Add environment-specific configurations** — Set up staging, production, or other deployment targets

## Multi-Language Repositories

When a repository contains multiple build systems (e.g., a monorepo with both Python and Node.js components), build detection returns all detected build types. You can:

- Use the highest confidence match as the primary workflow
- Create separate workflows for each detected build type
- Manually combine templates into a single multi-stage workflow
- Apply filters or path-based triggers to isolate builds by directory

## Limitations

- **Root directory scanning only** — Build detection examines only the repository root directory, not subdirectories or monorepo subpackages
- **Single-file indicators** — Detection is based on the presence of specific files; it does not parse file contents or validate build tool versions
- **No Docker detection** — While workflow templates can include Docker steps, ActionsManager does not currently detect `Dockerfile` as a standalone build type pattern
- **Template versions** — Workflow templates use reasonable default versions (e.g., JDK 11, Node 18.x) that may not match your project's actual requirements

## Authentication

Build detection uses the same authentication context as other GitHub API operations:

- **OAuth token** (when signed in via GitHub OAuth)
- **Personal Access Token** (when configured in user settings)

The token must have **read access** to the repository contents. No write permissions are required for detection — only for workflow creation and deployment.

## Error Handling

Build detection gracefully handles common errors:

- **Repository not found** — Returns 404 with a clear error message
- **Permission denied** — Returns 403 if the token cannot access the repository
- **No build types detected** — Returns an empty list with `total_detected: 0`
- **GitHub API errors** — Logs errors and returns an empty result rather than failing the request

## Implementation

Build detection is implemented in `backend/build_detector.py` and exposed through FastAPI endpoints in `backend/repos.py`. The detector uses the GitHub Contents API to list repository files and matches them against predefined build patterns.

The feature is stateless — detection results are computed on-demand and not cached or stored in the database. This ensures detection always reflects the current state of the repository.

## Related Topics

- [Workflows]({% link features/workflows.md %}) — create and manage workflows in ActionsManager
- [Projects]({% link features/projects.md %}) — group repositories for bulk workflow operations
