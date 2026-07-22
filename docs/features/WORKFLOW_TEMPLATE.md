# Workflow Template Guide

This guide helps you create new workflows following the project's standards.

## Template Structure

```yaml
name: Workflow Name

on:
  workflow_dispatch:
  push:
    branches: 
      - 'copilot/*'
      - 'feat/*'
      - "develop"
      - "main"
  pull_request:
    branches:
      - "develop"
      - "main"
  schedule:
    # Define schedule if needed (cron format)
    - cron: '0 0 * * *'

permissions:
  contents: read
  # Add other permissions as needed

jobs:
  job-name:
    name: Human Readable Job Name
    runs-on: arc-runner-set  # ALWAYS use arc-runner-set
    steps:
      - name: Checkout Code
        uses: actions/checkout@v5
        with:
          fetch-depth: 0  # Use if git history is needed

      - name: Setup Environment
        # Add language-specific setup
        # Python: uses: actions/setup-python@v5
        # Node: uses: actions/setup-node@v5

      - name: Cache Dependencies
        uses: actions/cache@v4
        with:
          path: # Cache path
          key: # Cache key
          restore-keys: # Restore keys

      - name: Install Dependencies
        run: |
          # Installation commands

      - name: Run Main Task
        run: |
          # Main workflow logic

      - name: Upload Artifacts
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: artifact-name
          path: |
            path/to/artifacts
          retention-days: 30
```

## Standard Patterns

### Python Job
```yaml
python-job:
  name: Python Task
  runs-on: arc-runner-set
  steps:
    - uses: actions/checkout@v5
    
    - name: Setup Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
        cache: 'pip'
    
    - name: Install Dependencies
      run: |
        cd backend
        python -m pip install --upgrade pip
        pip install -r requirements.txt
    
    - name: Run Task
      run: |
        cd backend
        # Your commands here
```

### Node.js Job
```yaml
nodejs-job:
  name: Node.js Task
  runs-on: arc-runner-set
  steps:
    - uses: actions/checkout@v5
    
    - name: Setup Node.js
      uses: actions/setup-node@v5
      with:
        node-version: '20'
        cache: 'npm'
        cache-dependency-path: 'frontend/package-lock.json'
    
    - name: Install Dependencies
      run: |
        cd frontend
        npm ci
    
    - name: Run Task
      run: |
        cd frontend
        # Your commands here
```

### Docker Job
```yaml
docker-job:
  name: Docker Task
  runs-on: arc-runner-set
  steps:
    - uses: actions/checkout@v5
    
    - name: Build Image
      run: |
        docker build -t image-name:tag ./path
    
    - name: Run Container Task
      run: |
        docker run image-name:tag command
    
    - name: Clean Up
      if: always()
      run: |
        docker rmi image-name:tag || true
```

### Security Scanning Job
```yaml
security-scan:
  name: Security Scan
  runs-on: arc-runner-set
  steps:
    - uses: actions/checkout@v5
    
    - name: Run Trivy Scanner
      uses: aquasecurity/trivy-action@master
      with:
        scan-type: 'fs'
        scan-ref: '.'
        format: 'sarif'
        output: 'trivy-results.sarif'
        severity: 'CRITICAL,HIGH'
    
    - name: Upload Results
      uses: github/codeql-action/upload-sarif@v3
      if: always()
      with:
        sarif_file: 'trivy-results.sarif'
```

## Best Practices

### 1. Always Use arc-runner-set
```yaml
runs-on: arc-runner-set  # ✅ Correct
runs-on: ubuntu-latest   # ❌ Avoid unless specifically needed
```

### 2. Use Checkout v5
```yaml
- uses: actions/checkout@v5  # ✅ Latest version
```

### 3. Enable Caching
```yaml
- name: Setup Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.12'
    cache: 'pip'  # ✅ Enable caching
```

### 4. Use Continue-on-error Appropriately
```yaml
- name: Non-Critical Task
  run: command
  continue-on-error: true  # ✅ For informational tasks
```

### 5. Always Clean Up Resources
```yaml
- name: Clean Up
  if: always()  # ✅ Run even if previous steps fail
  run: |
    docker system prune -f
```

### 6. Upload Artifacts for Debugging
```yaml
- name: Upload Logs
  uses: actions/upload-artifact@v4
  if: always()  # ✅ Upload even on failure
  with:
    name: debug-logs
    path: |
      **/*.log
    retention-days: 7
```

### 7. Use Meaningful Job Names
```yaml
backend-tests:
  name: Backend Unit Tests  # ✅ Clear and descriptive
```

### 8. Add Appropriate Permissions
```yaml
permissions:
  contents: read          # ✅ Minimum required
  # security-events: write  # Not needed - using artifacts instead
  pull-requests: write    # ✅ Only if commenting on PRs
```

## Common Triggers

### Push Events
```yaml
on:
  push:
    branches:
      - 'main'
      - 'develop'
      - 'copilot/*'
      - 'feat/*'
    paths:
      - 'backend/**'
      - 'frontend/**'
```

### Pull Request Events
```yaml
on:
  pull_request:
    branches:
      - 'main'
      - 'develop'
    types: [opened, synchronize, reopened]
```

### Scheduled Events
```yaml
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
    - cron: '0 0 * * 0'  # Weekly on Sundays
```

### Manual Trigger
```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy'
        required: true
        default: 'dev'
        type: choice
        options:
          - dev
          - staging
          - production
```

## Conditional Execution

### Run on Specific Branches
```yaml
- name: Production Only Task
  if: github.ref == 'refs/heads/main'
  run: echo "Running on main"
```

### Run on PR Only
```yaml
- name: PR Check
  if: github.event_name == 'pull_request'
  run: echo "This is a PR"
```

### Run Based on Job Result
```yaml
- name: On Success
  if: success()
  run: echo "Previous steps succeeded"

- name: On Failure
  if: failure()
  run: echo "Previous steps failed"

- name: Always Run
  if: always()
  run: echo "Runs regardless of previous steps"
```

## Workflow Dependencies

### Sequential Jobs
```yaml
job-a:
  runs-on: arc-runner-set
  steps:
    - run: echo "First job"

job-b:
  needs: job-a  # ✅ Runs after job-a completes
  runs-on: arc-runner-set
  steps:
    - run: echo "Second job"
```

### Multiple Dependencies
```yaml
final-job:
  needs: [job-a, job-b, job-c]  # ✅ Waits for all
  runs-on: arc-runner-set
  steps:
    - run: echo "All jobs complete"
```

### Conditional Dependencies
```yaml
summary:
  needs: [test, build]
  if: always()  # ✅ Run even if dependencies fail
  runs-on: arc-runner-set
  steps:
    - run: |
        echo "Test: ${{ needs.test.result }}"
        echo "Build: ${{ needs.build.result }}"
```

## Testing Workflows Locally

### Using act
```bash
# Install act
brew install act  # macOS
# or
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Run workflow
act -W .github/workflows/your-workflow.yml

# Run specific job
act -j job-name

# Run with secrets
act --secret-file .secrets
```

### Validation
```bash
# Validate workflow syntax
yamllint .github/workflows/your-workflow.yml

# Check action versions
actionlint .github/workflows/your-workflow.yml
```

## Checklist for New Workflows

- [ ] Uses `arc-runner-set` for all jobs
- [ ] Uses latest action versions (@v5, @v4, etc.)
- [ ] Has meaningful workflow and job names
- [ ] Includes appropriate permissions
- [ ] Implements caching where applicable
- [ ] Uploads artifacts for debugging
- [ ] Cleans up resources in finally blocks
- [ ] Has proper error handling
- [ ] Documents purpose in comments
- [ ] Tests locally before pushing
- [ ] Updates CI_CD_PIPELINE.md documentation

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Actions Marketplace](https://github.com/marketplace?type=actions)
- [Workflow Syntax](https://docs.github.com/en/actions/reference/workflow-syntax-for-github-actions)
- [Project CI/CD Documentation](CI_CD_PIPELINE.md)
