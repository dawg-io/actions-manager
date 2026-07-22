# Contributing to Actions Manager

Thank you for your interest in contributing to Actions Manager! This document provides guidelines and best practices for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Documentation Policy](#documentation-policy)
- [Submitting Changes](#submitting-changes)
- [Code Review Process](#code-review-process)

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please be respectful and professional in all interactions.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment (see [Development Setup](#development-setup))
4. Create a feature branch for your changes
5. Make your changes following our guidelines
6. Submit a pull request

## Development Setup

For detailed development setup instructions, see:
- **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Complete backend/frontend development guide
- **[docs/FRONTEND_DEVELOPMENT.md](docs/FRONTEND_DEVELOPMENT.md)** - Frontend stack, component patterns, testing

## Making Changes

### Code Guidelines

For comprehensive coding standards and best practices, see the **[AI Coding Template](.github/ai-coding-template.md)**.

The template provides detailed guidance on:
- Tech stack and architecture
- File organization and naming conventions
- TypeScript/React and Python/FastAPI patterns
- Component and API structure with examples
- Security and performance considerations
- Testing guidelines

**Quick Guidelines:**
- **Python Backend**: Follow PEP 8 style guidelines
- **React Frontend**: Follow the existing code style and component patterns
- **TypeScript**: Use TypeScript for new React components (migration in progress)
- **Tests**: Add tests for new features and bug fixes when possible
- **Commits**: Write clear, descriptive commit messages

### Branch Naming

Use descriptive branch names:
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation changes
- `refactor/description` - Code refactoring

## Documentation Policy

**⚠️ IMPORTANT: Documentation guidelines to prevent clutter**

### Core Principle
**Do NOT create new markdown documentation files without explicit approval.** Instead, update existing documentation or propose changes through issues.

### Approved Documentation Structure

The following are the **ONLY** approved locations for documentation:

#### Root Level
- `README.md` - Project overview, quick start, main entry point
- `SECURITY.md` - Security policy and vulnerability reporting
- `CONTRIBUTING.md` - This file
- `LICENSE` - Project license

#### `/.github/` Directory
- `.github/copilot-instructions.md` - GitHub Copilot workspace instructions
- `.github/ai-coding-template.md` - AI coding standards and patterns guide
- `.github/workflows/` - CI/CD workflow definitions

#### `/docs/` Directory
- `docs/README.md` - Documentation index and navigation
- `docs/DEVELOPMENT.md` - Development workflows, local setup, testing
- `docs/ARCHITECTURE.md` - High-level design, system architecture
- `docs/DEPLOYMENT.md` - Deployment guides and CI/CD
- `docs/TROUBLESHOOTING.md` - Common issues and solutions
- `docs/FRONTEND_DEVELOPMENT.md` - Frontend-specific development guide
- Subdirectories:
  - `docs/deployment/` - Deployment-specific guides (SELF_HOSTED_INSTALL.md, CLOUD_DEPLOYMENT.md, etc.)
  - `docs/features/` - Feature-specific documentation
  - `docs/guides/` - How-to guides and tutorials

#### Specialized Documentation
- `tools/README.md` - Documentation for tools directory
- Feature-specific documentation in appropriate subdirectories (with approval)

### Documentation Guidelines

#### DO:
✅ Update existing documentation when making changes  
✅ Fix typos, improve clarity, or add missing information to existing docs  
✅ Propose new documentation through GitHub issues first  
✅ Consolidate information into existing documents  
✅ Use inline code comments for complex logic  

#### DO NOT:
❌ Create new `*_SUMMARY.md`, `*_COMPLETE.md`, or `*_IMPLEMENTATION.md` files  
❌ Create dated completion reports or progress documents  
❌ Create issue-specific documentation files (use issue comments instead)  
❌ Generate AI/Copilot documentation for context preservation (use PR descriptions)  
❌ Create temporary documentation files in the root directory  
❌ Add documentation in formats other than specified without approval  

### Proposing New Documentation

If you believe new documentation is needed:

1. **Open an issue** describing:
   - What information is missing
   - Why existing docs don't cover it
   - Proposed location and structure
   
2. **Wait for approval** from maintainers before creating new files

3. **Submit PR** with approved documentation only

### AI/Copilot Users

If you're using GitHub Copilot or similar AI tools:
- **Do not** generate summary documents for context sharing
- **Do not** create documentation files to preserve session context
- **Use PR descriptions** and commit messages for implementation details
- **Update existing docs** rather than creating new ones

### Archival Policy

Completed feature implementations, bug fixes, and migrations should be documented in:
- Git commit history and PR descriptions
- Issue comments and discussions
- Release notes when applicable

Temporary documentation files will be moved to `docs/archive/` and are excluded from the repository via `.gitignore`.

## Submitting Changes

### Before Submitting

1. **Test your changes** thoroughly
2. **Update documentation** (existing docs only, see policy above)
3. **Run linters and tests**:
   ```bash
   # Backend
   cd backend && black . && flake8 .
   
   # Frontend
   cd frontend && npm run lint
   ```
4. **Ensure no unintended documentation files** are included
5. **Write clear PR description** explaining your changes

### Pull Request Guidelines

1. **Title**: Clear, concise description of changes
2. **Description**: 
   - What problem does this solve?
   - What changes were made?
   - How to test the changes?
3. **Link related issues**: Use `Fixes #123` or `Relates to #456`
4. **Keep PRs focused**: One feature/fix per PR when possible
5. **Documentation**: Note any documentation updates made to existing files

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests added/updated (if applicable)
- [ ] Existing tests pass
- [ ] Documentation updated (existing files only)
- [ ] No new documentation files created without approval
- [ ] Commit messages are clear and descriptive
- [ ] PR description explains changes thoroughly
- [ ] Related issues are linked

## Code Review Process

1. **Automated checks** run on all PRs (linting, tests, security scans)
2. **Maintainer review** - at least one maintainer must approve
3. **Address feedback** - make requested changes and push updates
4. **Merge** - once approved and checks pass, maintainers will merge

### Review Timeline

- **Small changes**: Usually reviewed within 2-3 days
- **Large changes**: May take up to a week
- **Documentation-only**: Typically faster review

## Questions?

If you have questions about contributing:
- Open an issue for discussion
- Check existing issues and documentation
- Review closed PRs for examples

Thank you for contributing to Actions Manager! 🚀
