"""
First-boot restore (issue #1878).

Provides:
- GET  /api/setup/status           — is this installation still uninitialized?
- POST /api/setup/restore/validate — stage an uploaded archive and report on it
- POST /api/setup/restore/apply    — apply the staged archive

These are the only unauthenticated write endpoints in the application, and they
are reachable only while nobody has ever signed in. That window is not chosen
for convenience: it is exactly the window in which the next person to sign in
is made workspace admin (see authorization.workspace_is_uninitialized), so an
open restore here grants no privilege the existing first-login-wins rule does
not already grant. The moment any human signs in, every route below returns 409
permanently.

Restoring into an installation that is already in use is deliberately not
offered over HTTP — backup_cli.py does that, and is also the only thing that can
help when the installation no longer starts.
"""

import tempfile
import time
import uuid
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from authorization import lock_first_member_decision, workspace_is_uninitialized
from backup_engine import BackupError, restore_backup, validate_backup
from database import SELF_HOSTED_DATA_DIR, get_db

router = APIRouter()

# Big enough for a large installation, small enough that an unauthenticated
# caller cannot fill the disk. The archive is gzipped JSONL, so this is a lot
# of rows.
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
_CHUNK = 1024 * 1024

_ALREADY_INITIALIZED = (
    "This installation is already in use. Restoring over it would replace existing data — "
    "run backup_cli.py restore from the command line instead."
)

_MSG_INITIALIZED = "Installation already in use; restore is no longer offered here"
_MSG_BAD_ARCHIVE = "Upload is not a readable ActionsManager backup"
_MSG_NO_SUCH_UPLOAD = "Staged upload not found or already consumed"
_MSG_TOO_LARGE = "Backup exceeds the upload limit"
_MSG_STORE_FAILED = "Upload could not be stored on the server"


# Set the first time a fallback is needed, so every request in this process
# shares one directory without it being a name anyone can predict.
_FALLBACK_STAGING_ROOT: Optional[Path] = None


def _staging_root() -> Path:
    """Where uploads are staged.

    SELF_HOSTED_DATA_DIR is only created under INSTALLATION_MODE=self-hosted, so
    using it unconditionally makes first-boot restore unusable anywhere else —
    including local development, where /app/data cannot be created at all.

    The fallback is a fresh mkdtemp rather than a fixed /tmp name: a staged
    archive is a complete dump of the installation, accounts and encrypted
    tokens included, and a predictable path in a world-writable directory can be
    pre-created or symlinked by any local user before the server gets there.
    """
    global _FALLBACK_STAGING_ROOT

    if SELF_HOSTED_DATA_DIR.is_dir():
        return SELF_HOSTED_DATA_DIR / "restore"
    if _FALLBACK_STAGING_ROOT is None or not _FALLBACK_STAGING_ROOT.is_dir():
        _FALLBACK_STAGING_ROOT = Path(tempfile.mkdtemp(prefix="actionsmanager-restore-"))
    return _FALLBACK_STAGING_ROOT


# A staged upload only has to survive the round trip from validate to apply.
# Anything older was abandoned, and on these unauthenticated routes nothing else
# would ever clean it up.
STAGED_UPLOAD_TTL_SECONDS = 60 * 60


def _sweep_stale_uploads(staging: Path) -> None:
    cutoff = time.time() - STAGED_UPLOAD_TTL_SECONDS
    for stale in staging.glob("*.tar.gz"):
        try:
            if stale.stat().st_mtime < cutoff:
                stale.unlink(missing_ok=True)
        except OSError:
            continue  # another request may have just removed it


def _staging_dir() -> Path:
    path = _staging_root()
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    _sweep_stale_uploads(path)
    return path


def _require_uninitialized(db: Session) -> None:
    if not workspace_is_uninitialized(db):
        raise HTTPException(status_code=409, detail=_ALREADY_INITIALIZED)


def _staged_path(token: str) -> Path:
    """Resolve a staging token to its archive, refusing anything that tries to
    point outside the staging directory."""
    if not token or "/" in token or "\\" in token or token.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid upload reference.")
    path = _staging_dir() / f"{token}.tar.gz"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="That upload is no longer available. Upload the backup again.")
    return path


def _discard(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("/api/setup/status")
def setup_status(db: Annotated[Session, Depends(get_db)]):
    """Whether the sign-in screen should offer a restore. Deliberately says
    nothing else about the installation to an anonymous caller."""
    return {"uninitialized": workspace_is_uninitialized(db)}


@router.post(
    "/api/setup/restore/validate",
    responses={
        400: {"description": _MSG_BAD_ARCHIVE},
        409: {"description": _MSG_INITIALIZED},
        413: {"description": _MSG_TOO_LARGE},
        500: {"description": _MSG_STORE_FAILED},
    },
)
def validate_uploaded_backup(
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
):
    """Stage an upload and report what restoring it would do.

    Nothing is written to the database here. The archive is held on disk under
    a random token so the confirm step does not have to re-upload it.
    """
    _require_uninitialized(db)

    token = uuid.uuid4().hex
    try:
        path = _staging_dir() / f"{token}.tar.gz"
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not stage the upload: {exc}") from exc

    written = 0
    try:
        with path.open("wb") as target:
            while chunk := file.file.read(_CHUNK):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Backup exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit. "
                               "Restore it with backup_cli.py instead.",
                    )
                target.write(chunk)
    except HTTPException:
        _discard(path)
        raise
    except OSError as exc:
        _discard(path)
        raise HTTPException(status_code=500, detail=f"Could not store the upload: {exc}") from exc

    try:
        report = validate_backup(path, db)
    except BackupError as exc:
        _discard(path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    manifest = report["manifest"]
    return {
        "upload_token": token,
        "ok": report["ok"],
        "errors": report["errors"],
        "warnings": report["warnings"],
        "total_rows": report["total_rows"],
        "tables": {name: rows for name, rows in report["tables"].items() if rows},
        "app_version": manifest.get("app_version"),
        "created_at": manifest.get("created_at"),
        "dialect": manifest.get("dialect"),
    }


@router.post(
    "/api/setup/restore/apply",
    responses={
        400: {"description": _MSG_BAD_ARCHIVE},
        404: {"description": _MSG_NO_SUCH_UPLOAD},
        409: {"description": _MSG_INITIALIZED},
    },
)
def apply_staged_backup(
    db: Annotated[Session, Depends(get_db)],
    upload_token: Annotated[str, File()],
):
    """Apply a previously staged archive.

    The uninitialized check runs again here, under the same lock first login
    takes, so a restore and someone signing in cannot interleave and leave the
    workspace half-owned.
    """
    lock_first_member_decision(db)
    _require_uninitialized(db)

    path = _staged_path(upload_token)
    try:
        result = restore_backup(db, path)
    except BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        _discard(path)

    return {
        "restored_rows": result["total_rows"],
        # Count populated tables only, matching what the validate step reported;
        # otherwise the UI says "3 table(s)" before and "41 table(s)" after for
        # the same archive.
        "restored_tables": sum(1 for rows in result["applied"].values() if rows),
        "skipped_tables": result["skipped_tables"],
        "warnings": result["warnings"],
        "migrations_ran": result["migrations_ran"],
    }


def discard_staged_uploads() -> None:
    """Drop uploads left behind by an abandoned restore.

    Age-based rather than a blanket rmtree: the staging directory is shared, so
    wiping it at startup would delete an upload another worker is mid-way
    through — the operator would get an unexplained 404 on a report they are
    still reading.
    """
    staging = _staging_root()
    if staging.is_dir():
        _sweep_stale_uploads(staging)
