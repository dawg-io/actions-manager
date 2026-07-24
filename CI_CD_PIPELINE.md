# CI/CD Pipeline Documentation

## 🎯 Workflow Optimization (October 2025)

**IMPORTANT**: This pipeline has been recently optimized to reduce parallel job execution and prevent K8s worker node overload. 

**Key improvements**:
- 80% reduction in peak concurrent jobs (20+ → 3-4)
- Sequential staging for better resource management
- Fail-fast approach for faster feedback
- Fixed critical bug in frontend container image tagging
- **Main orchestrator workflow for unified pipeline view** ⭐ NEW

---

## 🚀 Main Pipeline (Orchestrator)

The project now uses a **main orchestrator workflow** (`main-pipeline.yml`) that coordinates all CI/CD activities. This provides:

✅ **Single unified view** of the entire build process
✅ **Clear stage progression** from quality checks to deployment
✅ **Consolidated summary** of all pipeline activities
✅ **Easy debugging** with all stages in one place

---

## Overview

The Actions Manager project uses a comprehensive CI/CD pipeline with multiple workflows to ensure code quality, security, and reliability.

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Actions Workflows                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   PR Check   │  │   Linting    │  │    Security     │  │
│  │  Validation  │  │   (Code      │  │    Scanning     │  │
│  │              │  │   Quality)   │  │                 │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   Docker     │  │   Coverage   │  │   SonarQube     │  │
│  │   Build      │  │   Reports    │  │   Analysis      │  │
│  │              │  │              │  │                 │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ Performance  │  │     SBOM     │  │   Dependabot    │  │
│  │   Testing    │  │  Generation  │  │   Updates       │  │
│  │              │  │              │  │                 │  │
│  └──────────────┘  └──────────────┘  └─────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Workflows

### 1. Pull Request Validation (`pr-validation.yml`)

**Trigger**: Pull requests to `develop` or `main`

**Purpose**: Gate merges with comprehensive validation

**Jobs**:
- PR metadata validation (title format, size)
- Backend unit tests with coverage
- Frontend unit tests with coverage
- Build validation (both backend and frontend)
- Docker build validation
- Security quick check
- Summary report

**Exit Criteria**: All critical jobs must pass

### 2. Security Scanning (`security-scan.yml`)

**Trigger**: Push, PR, scheduled daily

**Purpose**: Comprehensive security analysis

**Jobs**:
- **Dependency Scan**: Trivy filesystem and config scanning
- **Python Security**: Bandit and Safety checks
- **Container Security**: Docker image vulnerability scanning
- **Secret Detection**: Gitleaks for exposed secrets

**Tools**:
- Trivy: Multi-purpose security scanner
- Bandit: Python security linter
- Safety: Python dependency vulnerability scanner
- Gitleaks: Secret detection

### 3. Code Linting (`linting.yml`)

**Trigger**: Push, PR

**Purpose**: Enforce code quality standards

**Jobs**:
- **Python Linting**:
  - Black (code formatting)
  - isort (import ordering)
  - Flake8 (style guide)
  - Pylint (code analysis)
  
- **Frontend Linting**:
  - ESLint (JavaScript/TypeScript)
  - TypeScript type checking
  
- **Docker Linting**:
  - Hadolint (Dockerfile best practices)
  
- **YAML Linting**:
  - yamllint (workflow files)

### 4. Docker Build (`docker-image.yml`)

**Trigger**: Push to main/develop/feature branches

**Purpose**: Build and deploy container images

**Features**:
- Builds backend and frontend images
- Tags with timestamp
- Pushes to GitHub Container Registry
- Updates Kubernetes manifests via Flux
- Cleanup of old images
- Triggers SonarQube scan

### 5. Coverage Reports (`coverage.yml`)

**Trigger**: Workflow call

**Purpose**: Generate test coverage reports

**Jobs**:
- Run frontend tests with coverage
- Run backend tests with coverage
- Verify coverage thresholds

### 6. SonarQube Analysis (`sonarqube_scan.yml`)

**Trigger**: Called from docker-image workflow

**Purpose**: Code quality and security analysis

**Features**:
- Multi-language support (Python, JavaScript/TypeScript)
- Coverage report integration
- Quality gate validation
- Technical debt tracking

### 7. SBOM Generation (`sbom-generation.yml`)

**Trigger**: Push to main/develop, tags, scheduled weekly

**Purpose**: Software Bill of Materials for supply chain security

**Jobs**:
- Generate backend SBOM (Python dependencies)
- Generate frontend SBOM (npm dependencies)
- Generate container SBOMs
- Generate repository-wide SBOM
- Validate SBOM quality
- Attach to releases

**Tools**:
- CycloneDX for dependency BOM
- Syft for container analysis

### 8. Performance Testing (`performance-testing.yml`)

**Trigger**: Push to main, PRs to main, scheduled weekly

**Purpose**: Monitor application performance

**Jobs**:
- **Backend Performance**:
  - Locust load testing
  - API response time analysis
  
- **Frontend Performance**:
  - Lighthouse CI audits
  - Bundle size analysis
  
- **Docker Performance**:
  - Image size analysis
  - Layer efficiency (Dive)
  - Container startup time

### 9. Dependabot (`dependabot.yml`)

**Trigger**: Scheduled weekly

**Purpose**: Automated dependency updates

**Ecosystems**:
- npm (frontend dependencies)
- pip (backend dependencies)
- GitHub Actions (workflow dependencies)

**Configuration**:
- Weekly updates
- Auto-assigned reviewers
- Labeled by component

### 10. Docker Image Cleanup (`delete-docker-image.yml`)

**Trigger**: Scheduled daily, manual

**Purpose**: Remove old container images

**Configuration**:
- Keeps latest 5 versions
- Runs on ubuntu-latest
- Cleans both frontend and backend images

## Runner Configuration

All new workflows use `arc-runner-set` for consistency and reliability. This provides:
- Self-hosted runner capabilities
- Consistent environment
- Better resource control

## Security Features

### Multi-Layer Security

1. **Pre-commit**: Local checks (optional)
2. **PR Validation**: Automated testing
3. **Security Scanning**: Vulnerability detection
4. **Code Quality**: SonarQube analysis
5. **Container Security**: Image scanning
6. **Supply Chain**: SBOM generation

### Secret Management

- GitHub Secrets for sensitive data
- Never commit credentials
- Gitleaks for detection
- Regular secret rotation

### Vulnerability Response

1. Dependabot creates PR
2. Security scan identifies issue
3. Automated or manual fix
4. Re-scan validates fix
5. Deploy updated version

## Best Practices

### For Developers

1. **Before Committing**:
   ```bash
   # Backend
   cd backend
   black . --check
   flake8 .
   pytest
   
   # Frontend
   cd frontend
   npm run lint
   npm test
   ```

2. **Creating PRs**:
   - Use semantic commit messages
   - Keep PRs small (<50 files, <1000 lines)
   - Wait for all checks to pass
   - Address security findings

3. **Reviewing PRs**:
   - Check security scan results
   - Review coverage reports
   - Validate build artifacts
   - Test locally if needed

### For Maintainers

1. **Dependency Management**:
   - Review Dependabot PRs weekly
   - Test security updates promptly
   - Keep actions up to date

2. **Security Response**:
   - Monitor security advisories
   - Triage critical issues immediately
   - Document fixes in CHANGELOG

3. **Performance Monitoring**:
   - Review performance reports monthly
   - Address degradation promptly
   - Optimize bundle sizes

## Workflow Triggers

| Workflow | Push | PR | Schedule | Manual |
|----------|------|-----|----------|--------|
| PR Validation | ❌ | ✅ | ❌ | ❌ |
| Security Scan | ✅ | ✅ | ✅ (daily) | ✅ |
| Linting | ✅ | ✅ | ❌ | ✅ |
| Docker Build | ✅ | ❌ | ❌ | ✅ |
| Coverage | Called | Called | ❌ | ✅ |
| SonarQube | Called | ❌ | ❌ | ✅ |
| SBOM | ✅ (main/dev) | ❌ | ✅ (weekly) | ✅ |
| Performance | ✅ (main) | ✅ (to main) | ✅ (weekly) | ✅ |
| Cleanup | ❌ | ❌ | ✅ (daily) | ✅ |

## Artifact Management

### Artifacts Generated

- Test coverage reports (30 days)
- Security scan results (30 days)
- Linting reports (30 days)
- Performance reports (30 days)
- SBOM files (90 days)
- Build artifacts (7 days)

### Container Images

- Development: `ghcr.io/dawg-io/actions-manager/dev-{backend|frontend}:TIMESTAMP`
- Production: `ghcr.io/dawg-io/actions-manager/{backend|frontend}:stable`
- Retention: Latest 5 versions

## Troubleshooting

### Common Issues

**Workflow Fails on Security Scan**:
- Check Trivy results in workflow artifacts
- Review Bandit findings
- Update vulnerable dependencies

**Build Fails**:
- Check Docker build logs
- Verify Dockerfile syntax
- Ensure dependencies are available

**Tests Fail**:
- Review test output
- Check coverage thresholds
- Validate environment setup

**Performance Degradation**:
- Review Lighthouse reports
- Analyze bundle sizes
- Check API response times

## Monitoring and Metrics

### Key Metrics

- **Build Success Rate**: Target >95%
- **Test Coverage**: Backend >5%, Frontend >4%
- **Security Vulnerabilities**: Target 0 critical/high
- **Build Time**: Monitor and optimize
- **Container Image Size**: Track and reduce

### Dashboards

- GitHub Actions tab: Workflow runs
- Security tab: Security advisories
- SonarQube: Code quality metrics
- Artifacts: Download reports

## Future Enhancements

Potential additions to the pipeline:

1. **End-to-End Testing**: Playwright/Cypress integration
2. **Chaos Engineering**: Reliability testing
3. **A/B Testing**: Feature flag integration
4. **Rollback Automation**: Automated failure recovery
5. **Multi-Environment**: Staging, production pipelines
6. **GitOps**: Full Flux CD integration
7. **Monitoring Integration**: Prometheus/Grafana
8. **Notification Integration**: Slack/Teams alerts

## Contributing

When adding new workflows:

1. Use `arc-runner-set` for runners
2. Follow existing naming conventions
3. Add appropriate triggers
4. Include error handling
5. Document in this file
6. Test thoroughly

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [SonarQube Documentation](https://docs.sonarqube.org/)
- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
