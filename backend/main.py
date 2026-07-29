"""
ActionsManager.xyz Backend API

A FastAPI application for managing GitHub Actions workflows with features including:
- GitHub OAuth authentication
- Project and repository management  
- Workflow creation and deployment
- Build type detection
- Secrets and environment variables management
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import OperationalError
import auth, projects, workflows, repos, github_secrets, github_env_vars, project_deletion, rulesets, marketplace_webhooks, workspace_members, project_memberships, codeowners, workflow_import, custom_files, actions_projects, action_groups
from database import engine, Base, SessionLocal
from models import Account, WorkspaceMember
import config

# The admin panel ships only in the cloud image. The self-hosted Docker build
# physically removes backend/admin.py, so the import must be conditional.
# A try/except guards against a misconfigured INSTALLATION_MODE=cloud on a
# self-hosted image (where admin.py is absent): the app starts cleanly and
# admin routes are simply unavailable rather than crashing on boot.
if config.INSTALLATION_MODE == "cloud":
    try:
        import admin  # noqa: E401
    except ModuleNotFoundError:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "INSTALLATION_MODE=cloud but admin module is not present; "
            "admin routes will be unavailable."
        )
        admin = None
else:
    admin = None
import license
import mode_validation
import anyio
import os
import sys

# FastAPI app with metadata
# Disable interactive docs in production or when DISABLE_API_DOCS=true
_docs_url = None if config.API_DOCS_DISABLED else "/docs"
_redoc_url = None if config.API_DOCS_DISABLED else "/redoc"
_openapi_url = None if config.API_DOCS_DISABLED else "/openapi.json"

app = FastAPI(
    title="ActionsManager.xyz API",
    description="API for managing GitHub Actions workflows",
    version="1.0.0",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

# Write-protection middleware: enforce workspace roles on mutating API requests
# Paths that are exempt from role checking (public, webhooks, auth, admin)
_WRITE_EXEMPT_PREFIXES = ("/auth/", "/webhooks/", "/admin/", "/ws", "/docs", "/redoc", "/openapi.json")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# DB factory used by the middleware — tests can override via app.state.middleware_db_factory
# Stored on app.state so both tests and middleware reference the same object
app.state.middleware_db_factory = SessionLocal


def _set_request_github_user_header(request: Request, github_user: str) -> None:
    """Replace any client-supplied X-GitHub-User with the session-resolved user."""
    raw_headers = [
        (key, value)
        for key, value in request.scope.get("headers", [])
        if key.lower() != b"x-github-user"
    ]
    raw_headers.append((b"x-github-user", github_user.encode("latin-1")))
    request.scope["headers"] = raw_headers
    request._headers = Headers(scope=request.scope)  # noqa: SLF001 - Starlette request cache


class WriteProtectionMiddleware(BaseHTTPMiddleware):
    """
    Middleware that blocks write requests (POST/PUT/PATCH/DELETE) for read-only users.
    
    - Safe HTTP methods (GET, HEAD, OPTIONS) are always allowed.
    - Certain path prefixes are exempt (auth, webhooks, admin panel).
    - If no workspace members exist yet (fresh install), enforcement is skipped
      so existing behavior is preserved until the first user logs in via OAuth.
    - For /api/* write requests, resolves the caller from the app session token.
    - If the caller is a read_only workspace member, the request is rejected with 403.
    - Missing/invalid sessions or unknown users/non-members return 401.
    """

    async def dispatch(self, request: Request, call_next):
        # Allow safe methods unconditionally
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        path = request.url.path

        # Skip exempt paths
        for prefix in _WRITE_EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Only enforce on /api/* paths
        if not path.startswith("/api/"):
            return await call_next(request)

        # Look up workspace members to decide if enforcement is active
        db = request.app.state.middleware_db_factory()
        try:
            # If no workspace members exist yet (fresh install / multi-user not
            # configured / migration not yet applied), skip enforcement so
            # existing behavior is preserved.
            try:
                member_count = db.query(WorkspaceMember).count()
            except OperationalError as e:
                # workspace_members table doesn't exist yet (pre-migration)
                if "no such table" in str(e).lower() or "does not exist" in str(e).lower():
                    return await call_next(request)
                raise  # Re-raise unexpected OperationalErrors

            if member_count == 0:
                return await call_next(request)

            try:
                user = auth.resolve_authenticated_user(request, db)
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                )

            member = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user.user_id).first()
            if not member:
                # Account exists but is not a workspace member
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unknown workspace member"},
                )

            if member.workspace_role == "read_only":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Read-only users cannot perform write operations"},
                )
        finally:
            db.close()

        token = auth.set_request_user(user.github_user)
        _set_request_github_user_header(request, user.github_user)
        try:
            return await call_next(request)
        finally:
            auth.reset_request_user(token)


app.add_middleware(WriteProtectionMiddleware)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to every response.

    - X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and
      Permissions-Policy are set unconditionally.
    - Strict-Transport-Security is only added when the request arrived over
      HTTPS (detected the same way as auth._cookie_secure()).
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        is_https = (
            request.headers.get("X-Forwarded-Proto", "").lower() == "https"
            or request.url.scheme == "https"
        )
        if is_https:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware must be added LAST so it becomes the outermost middleware
# (Starlette wraps middleware in reverse add order). This ensures CORS headers
# are applied to all responses, including those from inner middleware. (sonar:S8414)
#
# Allowed origins are resolved from CORS_ALLOWED_ORIGINS / REACT_APP_FRONTEND_URL
# (see config.get_cors_allowed_origins). When the resolved list is the wildcard
# "*" we disable allow_credentials, because credentialed wildcard CORS is unsafe
# and is also rejected by browsers.
#
# SecurityHeadersMiddleware is registered above CORSMiddleware so that it runs
# on the outermost layer — after CORS — ensuring headers appear on every
# response including CORS preflight (OPTIONS) responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Upgrade", "Connection"],
)

# Create database tables
Base.metadata.create_all(bind=engine)

# Include API routers
app.include_router(auth.router)
app.include_router(projects.router, prefix="/api")
app.include_router(workflows.router)
app.include_router(repos.router)
app.include_router(github_secrets.router)
app.include_router(github_env_vars.router)
app.include_router(project_deletion.router, prefix="/api")
app.include_router(rulesets.router)
# Admin router is cloud-only — module is absent from the self-hosted image.
if config.INSTALLATION_MODE == "cloud" and admin is not None:
    app.include_router(admin.router)
app.include_router(workspace_members.router)
app.include_router(project_memberships.router, prefix="/api")
app.include_router(codeowners.router)
app.include_router(workflow_import.router)
app.include_router(custom_files.router)
app.include_router(actions_projects.router)
app.include_router(action_groups.router)

# Conditionally include marketplace webhooks router only in cloud mode
if config.INSTALLATION_MODE == "cloud":
    app.include_router(marketplace_webhooks.router)


@app.on_event("startup")
async def startup_event():
    """Log application startup information"""
    print("=" * 60)
    print("🚀 ActionsManager.xyz API Starting")
    print(f"📦 Installation Mode: {config.INSTALLATION_MODE}")

    # Strict mode validation — fail closed for unsafe configurations.
    # Skip validation is honored only in self-hosted development, where the
    # validator is already permissive by design.
    skip_requested = os.environ.get(
        "ACTIONS_MANAGER_SKIP_MODE_VALIDATION", ""
    ).lower() in {"1", "true", "yes", "on"}
    active_environment = mode_validation.get_environment()
    skip = (
        skip_requested
        and config.INSTALLATION_MODE == "self-hosted"
        and active_environment == "development"
    )

    if skip_requested and not skip:
        print(
            "⚠️  ACTIONS_MANAGER_SKIP_MODE_VALIDATION is ignored unless "
            "INSTALLATION_MODE=self-hosted and ENVIRONMENT=development; "
            "running full startup validation.",
            file=sys.stderr,
            flush=True,
        )

    if skip:
        # Loud, persistent warning so an accidental setting in production is
        # obvious in logs.
        print(
            "⚠️  STARTUP VALIDATION SKIPPED via ACTIONS_MANAGER_SKIP_MODE_VALIDATION. "
            "This is intended for local development only.",
            file=sys.stderr,
            flush=True,
        )
    else:
        try:
            mode_validation.validate_startup_configuration()
        except mode_validation.ModeValidationError as exc:
            # Print to stderr and exit non-zero so container orchestrators
            # see the failure and don't keep an unsafe process running.
            print(str(exc), file=sys.stderr, flush=True)
            sys.exit(2)

    # Validate and cache license for self-hosted installations
    if config.INSTALLATION_MODE == "self-hosted":
        installation_tier = license.get_installation_tier()
        print(f"🔑 License Tier: {installation_tier}")
        print("🛍️  Marketplace: Disabled (self-hosted mode)")
    else:
        print("🛍️  Marketplace: Enabled (cloud mode)")

    # Log resolved URL configuration so operators can verify OAuth callback URLs.
    backend_url = auth.BACKEND_URL or "(auto-detected from request)"
    frontend_url = auth.FRONTEND_URL or "(auto-detected from request)"
    print(f"🌐 Backend URL:  {backend_url}")
    print(f"🖥️  Frontend URL: {frontend_url}")
    if auth.BACKEND_URL:
        print(f"🔗 GitHub OAuth callback: {auth.BACKEND_URL}/auth/callback")

    print("=" * 60)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "ActionsManager.xyz API is running",
        "version": "1.0.0",
        "allow_insecure_http": auth.ALLOW_INSECURE_HTTP,
    }


@app.get("/gui-workflow-editor-demo", response_class=HTMLResponse)
async def gui_workflow_editor_demo():
    """Demo page for GUI workflow editor feature"""
    try:
        # Get the directory where this script is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "gui-workflow-editor-demo.html")
        
        # Use anyio.open_file to handle file operations asynchronously
        async with await anyio.open_file(file_path, "r") as file:
            content = await file.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>GUI Workflow Editor Demo file not found</h1>", status_code=404)


@app.get("/reusable-workflow-gui-demo", response_class=HTMLResponse)
async def reusable_workflow_gui_demo():
    """Demo page for Reusable Workflow GUI editor feature"""
    try:
        # Get the directory where this script is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "reusable-workflow-gui-demo.html")
        
        # Use anyio.open_file to handle file operations asynchronously
        async with await anyio.open_file(file_path, "r") as file:
            content = await file.read()
        return HTMLResponse(content=content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Reusable Workflow GUI Demo file not found</h1>", status_code=404)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    token = websocket.cookies.get(auth.SESSION_COOKIE_NAME)
    if not token:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        session = (
            db.query(auth.AuthSession)
            .filter(auth.AuthSession.token_hash == auth._hash_session_token(token))
            .first()
        )
        valid = bool(
            session
            and session.revoked_at is None
            and auth._as_utc(session.expires_at) > auth._now_utc()
        )
    finally:
        db.close()

    if not valid:
        await websocket.close(code=1008)
        return

    try:
        await websocket.accept()

        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Message received: {data}")

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket Error: {e}")
