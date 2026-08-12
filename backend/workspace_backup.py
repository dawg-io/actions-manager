"""
Workspace backup download (issue #1878).

Provides:
- GET /api/workspace/backup       — download a full-installation backup archive
- GET /api/workspace/backup/info  — what a backup would contain, for the UI

Admin-only, matching the other workspace-scoped settings endpoints.

Restore deliberately has no counterpart here. It happens either at first boot,
before anyone has signed in, or through backup_cli.py — never as an authenticated
action against a running installation, which would mean overwriting the very
session authorizing the request.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from authorization import require_role
from backup_engine import BACKUP_FORMAT_VERSION, EXCLUDED_TABLES, create_backup, backup_tables
from database import get_db
from models import WorkspaceMember

router = APIRouter()


@router.get("/api/workspace/backup/info")
def backup_info(
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """Row counts a backup would capture, so the operator can sanity-check it."""
    from sqlalchemy import func, select

    tables = {}
    for table in backup_tables():
        tables[table.name] = db.execute(select(func.count()).select_from(table)).scalar_one()

    return {
        "backup_format_version": BACKUP_FORMAT_VERSION,
        "table_count": len(tables),
        "total_rows": sum(tables.values()),
        "tables": tables,
        "excluded_tables": sorted(EXCLUDED_TABLES),
    }


@router.get("/api/workspace/backup")
def download_backup(
    db: Annotated[Session, Depends(get_db)],
    _auth: Annotated[WorkspaceMember, Depends(require_role("admin"))],
):
    """Stream a full backup archive as a download."""
    workdir = Path(tempfile.mkdtemp(prefix="actionsmanager-backup-"))
    archive = workdir / "backup.tar.gz"
    try:
        manifest = create_backup(db, archive)
    except Exception:
        # Otherwise a failed backup leaves a partial multi-hundred-MB archive
        # behind, once per attempt.
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    stamp = manifest["created_at"].replace(":", "-")
    filename = f"actionsmanager-backup-{stamp}.tar.gz"

    # The archive is a temp file only because it has to exist on disk to be
    # streamed; delete it once the response is finished either way.
    def _cleanup() -> None:
        # rmtree, not rmdir: anything else left in the directory would otherwise
        # raise after the response has already been sent.
        shutil.rmtree(workdir, ignore_errors=True)

    return FileResponse(
        path=archive,
        media_type="application/gzip",
        filename=filename,
        background=BackgroundTask(_cleanup),
    )
