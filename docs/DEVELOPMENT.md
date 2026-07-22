# Development Guide

This guide covers local development setup, workflows, testing procedures, and best practices for contributing to Actions Manager.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Common Tasks](#common-tasks)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

- **Python 3.9+** - Backend runtime
- **Node.js 16+** - Frontend runtime
- **Git** - Version control
- **Docker 20.10+** (optional) - For containerized development
- **PostgreSQL 12+** (optional) - For database development (SQLite works by default)

### Accounts & Access

- **GitHub Account** - For OAuth testing
- **GitHub OAuth App** - See [OAuth Setup](#github-oauth-setup)

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/dawg-io/actions-manager.git
cd actions-manager
```

### 2. Backend Setup

#### Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

#### Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

**Note:** Installation takes approximately 45 seconds. If you encounter SSL/timeout errors, see [Troubleshooting](#backend-dependency-issues).

#### Configure Environment Variables

Create `backend/.env`:

```bash
# GitHub OAuth Configuration (required)
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# Application URLs (read by the backend for OAuth redirect URI and CORS)
VITE_BACKEND_URL=http://localhost:8000
VITE_FRONTEND_URL=http://localhost:3000

# Database (optional - defaults to SQLite)
# POSTGRES_USER=your_postgres_user
# POSTGRES_PASSWORD=your_postgres_password
# POSTGRES_DB=your_database_name
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
```

For complete configuration options, see [Environment Variables Guide](ENVIRONMENT_VARIABLES.md).

#### Start Backend Server

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The backend will be available at:
- API: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`
- Startup time: ~3 seconds

### 3. Frontend Setup

#### Install Dependencies

```bash
cd frontend
npm install
```

**⚠️ IMPORTANT:** This takes **12-13 minutes**. Do not cancel the process.

#### Start Development Server

```bash
npm start
```

The frontend will be available at:
- Application: `http://localhost:3000`
- Startup time: ~30 seconds

### 4. GitHub OAuth Setup

For local development, create a GitHub OAuth App:

1. Go to **GitHub Settings → Developer settings → OAuth Apps**
2. Click **"New OAuth App"**
3. Configure:
   - **Application name**: Actions Manager (Local Dev)
   - **Homepage URL**: `http://localhost:3000`
   - **Authorization callback URL**: `http://localhost:8000/auth/callback`
4. Copy the **Client ID** and **Client Secret** to `backend/.env`

**Important:** The callback URL must match exactly. For Docker deployments, use different URLs (see deployment guides).

## Project Structure

```
actions-manager/
├── backend/                    # Python FastAPI backend
│   ├── main.py                # Application entry point
│   ├── models.py              # Database models
│   ├── database.py            # Database configuration
│   ├── auth.py                # OAuth authentication
│   ├── workflows.py           # Workflow management
│   ├── projects.py            # Project management
│   ├── repos.py               # Repository management
│   ├── github_secrets.py      # Secrets management
│   ├── build_detector.py      # Build type detection
│   └── requirements.txt       # Python dependencies
│
├── frontend/                   # React frontend
│   ├── src/
│   │   ├── App.js             # Main component
│   │   ├── components/        # React components
│   │   └── api/               # API integration
│   ├── package.json           # Node dependencies
│   └── public/                # Static assets
│
├── docs/                       # Documentation
├── tools/                      # Utility scripts
├── .github/                    # GitHub Actions workflows
└── tests/                      # Test files
```

## Development Workflow

### Starting Development

1. **Activate Python virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Start backend (Terminal 1):**
   ```bash
   cd backend
   uvicorn main:app --reload --port 8000
   ```

3. **Start frontend (Terminal 2):**
   ```bash
   cd frontend
   npm start
   ```

4. **Open application:**
   - Frontend: `http://localhost:3000`
   - Backend API docs: `http://localhost:8000/docs`

### Making Changes

1. **Create feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following code style guidelines

3. **Test your changes** (see [Testing](#testing))

4. **Commit with clear messages:**
   ```bash
   git add .
   git commit -m "Description of changes"
   ```

5. **Push and create PR:**
   ```bash
   git push origin feature/your-feature-name
   ```

## Testing

### Backend Tests

#### Drift Detection Tests

```bash
# From repository root
source venv/bin/activate
PYTHONPATH=./backend python test_drift_detection.py
```

**Note:** `PYTHONPATH=./backend` is required for imports to work correctly.

#### Manual Testing

```bash
# Test drift detection workflow
python manual_test_drift.py

# Test marketplace webhooks
python manual_test_marketplace_webhook.py

# Test repository filtering
python manual_test_repo_filtering.py
```

### Frontend Tests

```bash
cd frontend
npm test
```

Tests run with Vitest (single-pass). Use `npm run test:coverage` for a coverage report.

### Integration Testing

1. Start both backend and frontend servers
2. Navigate to `http://localhost:3000`
3. Test OAuth flow: Click "Login with GitHub"
4. Test core functionality:
   - Create a project
   - Add repositories
   - Create/edit workflows
   - Test drift detection
   - Manage secrets

### API Testing

```bash
# Test build detection API
curl http://localhost:8000/api/test/build-patterns

# Test workflow templates API
curl http://localhost:8000/api/test/workflow-templates

# Check API health
curl http://localhost:8000/health
```

## Code Quality

### Linting

#### Backend (Python)

```bash
cd backend

# Format code with Black
black .

# Check with flake8
flake8 .

# Type checking (if configured)
mypy .
```

#### Frontend (JavaScript/TypeScript)

```bash
cd frontend

# Run ESLint
npm run lint

# Fix auto-fixable issues
npm run lint -- --fix
```

### SonarQube

SonarQube scanning runs automatically in CI on pushes to `copilot/*` and `feat/*` branches that touch `frontend/**` or `backend/**` files (see `.github/workflows/sonarqube_scan.yml`). The scan covers both the `frontend/src` and `backend` directories and requires a running SonarQube server.

**To run SonarQube locally:**

1. Ensure a SonarQube server is reachable (e.g., `https://sonarqube.local.updawg.xyz` or a local Docker instance).
2. Generate a user token in SonarQube → **My Account → Security**.
3. From the repository root, run:

   ```bash
   # Generate coverage reports first
   # Frontend: SonarQube reads the lcov.info report (sonar.javascript.lcov.reportPaths / sonar.typescript.lcov.reportPaths)
   cd frontend && npm run test:coverage && cd ..
   # Backend: SonarQube reads coverage.xml (sonar.python.coverage.reportPaths) and coverage.lcov (sonar.python.lcov.reportPaths)
   cd backend && PYTHONPATH=. pytest tests/ --cov=. --cov-report=xml:coverage.xml --cov-report=lcov:coverage.lcov && cd ..

   # Run the scanner (replace values as needed)
   docker run --rm \
     -e SONAR_HOST_URL="https://your-sonarqube-host" \
     -e SONAR_TOKEN="your-token" \
     -v "$(pwd):/usr/src" \
     sonarsource/sonar-scanner-cli \
     -Dsonar.projectKey=actions-manager-feature
   ```

   Alternatively, install the [SonarScanner CLI](https://docs.sonarsource.com/sonarqube/latest/analyzing-source-code/scanners/sonarscanner/) and run:

   ```bash
   sonar-scanner \
     -Dsonar.projectKey=actions-manager-feature \
     -Dsonar.host.url=https://your-sonarqube-host \
     -Dsonar.token=your-token
   ```

The project-level configuration lives in `sonar-project.properties` at the repository root. SonarQube is **not** required to pass locally for a PR to merge, but the CI quality gate runs on every feature branch push and results are visible in the SonarQube dashboard.

### Code Style Guidelines

**Python:**
- Follow PEP 8
- Use Black for formatting
- Type hints where beneficial
- Docstrings for public functions

**JavaScript/TypeScript:**
- Use ESLint configuration
- Prefer TypeScript for new components
- Follow React best practices
- Use functional components with hooks

## Common Tasks

### Adding a New API Endpoint

1. **Define route in appropriate module** (`workflows.py`, `projects.py`, etc.)
2. **Add database model** if needed in `models.py`
3. **Update database schema** if needed
4. **Add API documentation** (FastAPI auto-generates from code)
5. **Test endpoint** with curl or Postman
6. **Add frontend integration** if needed

### Adding a New Frontend Component

1. **Create component file** in `frontend/src/components/`
2. **Use TypeScript** for new components (`.tsx` extension)
3. **Follow existing patterns** for styling and state management
4. **Import and use** in parent components
5. **Test in browser** with hot reload

### Database Migrations

```bash
cd backend

# For marketplace webhooks
python migrate_add_marketplace_webhooks.py

# For webhook security
python migrate_add_webhook_security.py
```

**Note:** Create migration scripts for schema changes, don't modify `models.py` directly without migrations.

### Updating Dependencies

**Backend:**
```bash
cd backend
pip install --upgrade package-name
pip freeze > requirements.txt
```

**Frontend:**
```bash
cd frontend
npm update package-name
# or for major versions
npm install package-name@latest
```

## Troubleshooting

### Backend Dependency Issues

**SSL/Timeout Errors during pip install:**
```bash
pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt
```

**Module Import Errors:**
```bash
# Always set PYTHONPATH for backend tests
export PYTHONPATH=./backend
# or inline
PYTHONPATH=./backend python test_drift_detection.py
```

### Frontend Issues

**npm install hangs:**
```bash
# Clear cache and retry
cd frontend
rm -rf node_modules package-lock.json
npm cache clean --force
npm install
```

**Build fails with ESLint errors:**
```bash
# Use non-CI mode
CI=false npm run build
```

### OAuth Issues

**OAuth callback fails:**
- Verify callback URL in GitHub OAuth app matches exactly
- Check Client ID and Secret in `.env` file
- Ensure backend is running on correct port (8000)

**"Invalid credentials" error:**
- Regenerate Client Secret in GitHub OAuth app
- Update `.env` file with new secret
- Restart backend server

### Database Issues

**SQLite locked errors:**
- Close other connections to database
- Restart backend server

**PostgreSQL connection fails:**
- Verify PostgreSQL is running
- Check connection settings in `.env`
- Ensure database exists

## Additional Resources

- **[Architecture Guide](ARCHITECTURE.md)** - System design and components
- **[Frontend Development](FRONTEND_DEVELOPMENT.md)** - React/TypeScript guide
- **[Deployment Guide](DEPLOYMENT.md)** - Production deployment
- **[Contributing Guidelines](../CONTRIBUTING.md)** - Contribution policy
- **[Troubleshooting](TROUBLESHOOTING.md)** - Common issues

## Getting Help

- **Issues:** Check [GitHub Issues](https://github.com/dawg-io/actions-manager/issues)
- **Discussions:** Use GitHub Discussions for questions
- **Documentation:** See [docs/README.md](README.md) for full documentation index

---

**Last Updated:** 2026-02-14  
**Maintainer:** Actions Manager Team
