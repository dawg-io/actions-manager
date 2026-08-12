"""
Whole-installation backup and restore.

Serializes every table to a compressed archive and restores it into a
compatible installation. Both the CLI (``backup_cli.py``) and the first-boot
restore screen call through here, so there is exactly one implementation of
"what is a backup" and "what does restoring one mean".

Serialization goes through SQLAlchemy rather than ``pg_dump``/``sqlite3``:
neither binary ships in the self-hosted image, and the same code has to produce
an interchangeable artifact on SQLite and PostgreSQL.

Two things deliberately never enter the archive:

* Decrypted credentials. ``accounts.github_pat_token_encrypted`` is copied as
  the ciphertext it already is; nothing here calls ``_decrypt_saved_token``.
* Live sessions. ``auth_sessions`` is never written to an archive, and a restore
  clears whatever the target had, so no one stays signed in across one. Carrying
  them would resurrect sessions that were signed out or stolen; leaving the
  target's in place would be worse still, since a surviving session would then
  authenticate against a different set of accounts entirely.

The archive records an HMAC fingerprint of ``SECRET_KEY``, never the key. A
restore into an installation with a different key still succeeds, because the
rest of the data is fine — but it warns, because the restored PATs are
undecryptable and have to be re-entered.
"""

import base64
import hashlib
import hmac
import io
import json
import os
import subprocess
import sys
import tarfile
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import BigInteger, Integer, func, select, text
from sqlalchemy.orm import Session

from authorization import workspace_is_uninitialized
from database import Base, DATABASE_URL
from run_migrations import MIGRATION_SCRIPTS

# Bumped when the archive layout changes in a way an older reader cannot parse.
# Independent of the project-scoped export version in projects.py: that one
# describes a single project's JSON shape, this one describes a whole install.
BACKUP_FORMAT_VERSION = "1.0"

MANIFEST_NAME = "manifest.json"
TABLE_DIR = "tables"

# Sessions are intentionally not portable across a restore.
EXCLUDED_TABLES = frozenset({"auth_sessions"})

_KEYCHECK_CONTEXT = b"actionsmanager-backup-keycheck-v1"

# Bounded well under a typical reverse proxy's read timeout (nginx defaults to
# 60s). Waiting longer does not help: the proxy closes the connection, the
# browser reports a failure for a restore that actually succeeded, and the retry
# then hits 409 because the data is already there. Migrations that outlast this
# keep running — the restore reports that they are unfinished rather than
# pretending the whole thing failed.
MIGRATION_TIMEOUT_SECONDS = 45

# A gzip member expands without bound, and the first-boot restore endpoint is
# reachable before any account exists — so a small upload must not be able to
# exhaust memory. The compressed side is already capped when the upload is
# staged; these bound the decompressed side.
_CHUNK = 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_MEMBER_BYTES = int(os.environ.get("BACKUP_MAX_MEMBER_BYTES", 4 * 1024**3))


class BackupError(Exception):
    """Raised when an archive cannot be produced, read, or safely applied."""


def _app_version() -> str:
    """Release version from the repo-root VERSION file, or "dev"."""
    try:
        return (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
    except OSError:
        return "dev"


def _dialect() -> str:
    return "postgresql" if "postgres" in DATABASE_URL.lower() else "sqlite"


def secret_key_fingerprint() -> Optional[str]:
    """Prove which SECRET_KEY an archive was written under without carrying it.

    None when no key is configured, which is itself worth recording: an archive
    produced without one has no usable encrypted credentials to begin with.
    """
    secret = os.getenv("SECRET_KEY", "").strip()
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), _KEYCHECK_CONTEXT, hashlib.sha256).hexdigest()


def backup_tables():
    """Every table, in foreign-key dependency order, minus the excluded ones."""
    return [t for t in Base.metadata.sorted_tables if t.name not in EXCLUDED_TABLES]


def _encode_value(value: Any) -> Any:
    """JSON-safe form of a column value, tagged where the type is not obvious.

    Datetimes and bytes round-trip through tagged dicts rather than bare
    strings so the decoder never has to guess whether a string was originally
    a string.
    """
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, (bytes, bytearray)):
        return {"__type__": "bytes", "value": base64.b64encode(bytes(value)).decode("ascii")}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"__type__": "repr", "value": str(value)}


def _decode_value(value: Any) -> Any:
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    kind = value["__type__"]
    raw = value["value"]
    if kind == "datetime":
        return datetime.fromisoformat(raw)
    if kind == "bytes":
        return base64.b64decode(raw)
    return raw


def _serialize_table(db: Session, table) -> tuple[bytes, int]:
    """One table as JSONL bytes, plus its row count."""
    buffer = io.StringIO()
    rows = 0
    for row in db.execute(select(table)).mappings():
        buffer.write(json.dumps({k: _encode_value(v) for k, v in row.items()}, sort_keys=True))
        buffer.write("\n")
        rows += 1
    return buffer.getvalue().encode("utf-8"), rows


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(payload)
    # Fixed mtime so two backups of identical data compare equal.
    info.mtime = 0
    info.mode = 0o600
    archive.addfile(info, io.BytesIO(payload))


def create_backup(db: Session, destination: Path) -> dict:
    """Write a full-installation archive to ``destination``. Returns the manifest."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    members: list[tuple[str, bytes]] = []
    table_meta: dict[str, dict] = {}

    for table in backup_tables():
        payload, rows = _serialize_table(db, table)
        member = f"{TABLE_DIR}/{table.name}.jsonl"
        members.append((member, payload))
        table_meta[table.name] = {
            "rows": rows,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "member": member,
        }

    manifest = {
        "backup_format_version": BACKUP_FORMAT_VERSION,
        "app_version": _app_version(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dialect": _dialect(),
        "secret_key_fingerprint": secret_key_fingerprint(),
        "migrations": list(MIGRATION_SCRIPTS),
        "excluded_tables": sorted(EXCLUDED_TABLES),
        "tables": table_meta,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    with tarfile.open(destination, "w:gz") as archive:
        _add_bytes(archive, MANIFEST_NAME, manifest_bytes)
        for name, payload in members:
            _add_bytes(archive, name, payload)

    return manifest


@contextmanager
def _open_archive(source: Path):
    """Open an archive, reporting every way a damaged one fails as BackupError.

    A truncated upload raises EOFError rather than OSError, so catching only
    OSError/TarError lets the most likely real corruption escape as a crash.
    """
    try:
        with tarfile.open(source, "r:gz") as archive:
            yield archive
    except (tarfile.TarError, OSError, EOFError, zlib.error) as exc:
        raise BackupError(f"Archive is unreadable or corrupt: {exc}") from exc


def _read_capped(handle, limit: int, what: str) -> bytes:
    """Read a decompressed member, refusing past `limit`."""
    out = bytearray()
    while chunk := handle.read(_CHUNK):
        out.extend(chunk)
        if len(out) > limit:
            raise BackupError(
                f"Archive {what} expands beyond {limit // (1024 * 1024)} MB; it is corrupt "
                "or crafted to exhaust memory."
            )
    return bytes(out)


def _digest_member(handle, limit: int) -> Optional[str]:
    """SHA-256 of a member, streamed. None if it expands past `limit`."""
    digest = hashlib.sha256()
    total = 0
    while chunk := handle.read(_CHUNK):
        total += len(chunk)
        if total > limit:
            return None
        digest.update(chunk)
    return digest.hexdigest()


def read_manifest(source: Path) -> dict:
    with _open_archive(source) as archive:
        try:
            handle = archive.extractfile(MANIFEST_NAME)
        except KeyError as exc:
            raise BackupError("Archive has no manifest; it is not an ActionsManager backup.") from exc
        if handle is None:
            raise BackupError("Archive has no manifest; it is not an ActionsManager backup.")
        try:
            return json.loads(_read_capped(handle, MAX_MANIFEST_BYTES, "manifest").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BackupError(f"Archive manifest is unreadable: {exc}") from exc


def _version_tuple(version: str) -> tuple[int, ...]:
    """Compare versions numerically. As strings, "2.0" sorts above "10.0" and a
    genuinely older backup gets refused as "newer" — during a recovery, which is
    the worst possible moment to be wrong about it."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


def _check_format_version(manifest: dict) -> tuple[list[str], list[str]]:
    """A newer archive may hold members this reader cannot parse. An older one
    is always readable, because the format only ever gains fields."""
    fmt = str(manifest.get("backup_format_version", ""))
    if fmt == BACKUP_FORMAT_VERSION:
        return [], []
    if _version_tuple(fmt) > _version_tuple(BACKUP_FORMAT_VERSION):
        return [
            f"Backup format {fmt} is newer than this installation supports "
            f"({BACKUP_FORMAT_VERSION}). Upgrade ActionsManager, then restore."
        ], []
    return [], [f"Backup was written in the older {fmt} format."]


def _check_member_integrity(source: Path, table_meta: dict) -> list[str]:
    """Every table listed in the manifest must be present and match its checksum."""
    errors = []
    with _open_archive(source) as archive:
        present = set(archive.getnames())
        for name, meta in sorted(table_meta.items()):
            member = meta.get("member")
            if member not in present:
                errors.append(f"Table '{name}' is listed in the manifest but missing from the archive.")
                continue
            handle = archive.extractfile(member)
            actual = _digest_member(handle, MAX_MEMBER_BYTES) if handle else None
            if actual is None:
                errors.append(
                    f"Table '{name}' expands beyond the decompression limit; the archive is "
                    "corrupt or crafted to exhaust memory."
                )
            elif actual != meta.get("sha256"):
                errors.append(f"Table '{name}' failed its checksum; the archive is corrupt or was edited.")
    return errors


def _check_table_coverage(table_meta: dict) -> list[str]:
    """Tables either side has and the other does not. Never fatal — a release
    boundary in either direction is survivable."""
    warnings = []
    known = {t.name for t in Base.metadata.sorted_tables}
    unknown = sorted(set(table_meta) - known)
    if unknown:
        warnings.append(
            "Backup contains tables this installation does not have, which will be skipped: "
            + ", ".join(unknown)
        )
    missing = sorted(known - set(table_meta) - EXCLUDED_TABLES)
    if missing:
        warnings.append(
            "This installation has tables the backup does not, which will be left empty: "
            + ", ".join(missing)
        )
    return warnings


def _check_schema_version(manifest: dict) -> tuple[list[str], list[str]]:
    """Compare migration lists. This project has no schema_migrations table, so
    the ordered list in run_migrations.py is the schema fingerprint."""
    backup_migrations = manifest.get("migrations") or []
    errors, warnings = [], []

    newer = [m for m in backup_migrations if m not in MIGRATION_SCRIPTS]
    if newer:
        errors.append(
            "Backup came from a newer schema; this installation is missing "
            f"{len(newer)} migration(s), starting with {newer[0]}. Upgrade first."
        )
    pending = [m for m in MIGRATION_SCRIPTS if m not in backup_migrations]
    if pending:
        warnings.append(
            f"Backup predates {len(pending)} migration(s); they will run after the data is applied."
        )
    return errors, warnings


def _check_secret_key(manifest: dict) -> list[str]:
    """Never fatal: everything except saved tokens restores fine under a
    different key, and the operator needs to know that before they discover it."""
    backup_fp = manifest.get("secret_key_fingerprint")
    if not backup_fp:
        return []
    current_fp = secret_key_fingerprint()
    if not current_fp:
        return [
            "This installation has no SECRET_KEY configured, so the backup's saved personal "
            "access tokens cannot be decrypted."
        ]
    if backup_fp != current_fp:
        return [
            "SECRET_KEY differs from the one this backup was written under. Saved personal "
            "access tokens will not decrypt and must be re-entered after restoring."
        ]
    return []


def validate_backup(source: Path, db: Optional[Session] = None) -> dict:
    """Check an archive without touching the database. Never raises on a merely
    incompatible backup — the caller decides what to do with the report.

    Only a structurally unreadable archive raises, because there is nothing to
    report about it.
    """
    manifest = read_manifest(source)
    table_meta = manifest.get("tables") or {}

    format_errors, format_warnings = _check_format_version(manifest)
    schema_errors, schema_warnings = _check_schema_version(manifest)

    errors = format_errors + schema_errors + _check_member_integrity(source, table_meta)
    warnings = format_warnings + schema_warnings + _check_table_coverage(table_meta) + _check_secret_key(manifest)

    if not table_meta:
        errors.append("Manifest lists no tables.")

    report = {
        "manifest": manifest,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
        "tables": {name: meta.get("rows", 0) for name, meta in table_meta.items()},
        "total_rows": sum(meta.get("rows", 0) for meta in table_meta.values()),
    }
    if db is not None:
        report["target_uninitialized"] = workspace_is_uninitialized(db)
    return report


def _iter_rows(archive: tarfile.TarFile, member: str) -> Iterable[dict]:
    handle = archive.extractfile(member)
    if handle is None:
        return
    total = 0
    for line in io.TextIOWrapper(handle, encoding="utf-8"):
        total += len(line)
        if total > MAX_MEMBER_BYTES:
            raise BackupError(
                f"Table member '{member}' expands beyond the decompression limit; the archive "
                "is corrupt or crafted to exhaust memory."
            )
        if line.strip():
            yield json.loads(line)


def _rows_for_table(archive: tarfile.TarFile, table, member: str) -> list[dict]:
    """Decoded rows for one table, dropping columns this installation no longer
    has. A pending migration supplies anything the archive is missing."""
    columns = {c.name for c in table.columns}
    return [
        {k: _decode_value(v) for k, v in raw.items() if k in columns}
        for raw in _iter_rows(archive, member)
    ]


def _apply_archive(db: Session, archive: tarfile.TarFile, manifest: dict,
                   say: Callable[[str], None]) -> dict[str, int]:
    """Replace all data with the archive's, inside the caller's transaction."""
    # Children first, so a delete never trips a foreign key. SQLite enforces
    # them too (database.py sets PRAGMA foreign_keys=ON). This walks every
    # table, not just the backed-up ones: auth_sessions is never carried, but
    # leaving the target's rows behind would be worse than carrying them.
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())

    table_meta = manifest.get("tables") or {}
    applied: dict[str, int] = {}
    for table in backup_tables():
        meta = table_meta.get(table.name)
        if not meta:
            continue
        rows = _rows_for_table(archive, table, meta["member"])
        if rows:
            db.execute(table.insert(), rows)
            say(f"restored {table.name}: {len(rows)} row(s)")
        applied[table.name] = len(rows)
    return applied


def _guard_restore(db: Session, source: Path, force: bool) -> dict:
    """Refuse an unusable archive, or a target that would lose data."""
    report = validate_backup(source, db)
    if not report["ok"]:
        raise BackupError("; ".join(report["errors"]))

    if not force and not workspace_is_uninitialized(db):
        raise BackupError(
            "This installation already has users. Restoring would replace their data. "
            "Re-run with force to overwrite it."
        )
    return report


def restore_backup(
    db: Session,
    source: Path,
    force: bool = False,
    run_migrations: bool = True,
    progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """Replace this installation's data with the archive's.

    Everything happens in one transaction: a failure rolls back to the state
    the installation was in beforehand rather than leaving it half-written.
    """
    say = progress or (lambda _msg: None)
    report = _guard_restore(db, source, force)
    manifest = report["manifest"]

    with _open_archive(source) as archive:
        try:
            applied = _apply_archive(db, archive, manifest, say)
            db.commit()
        except Exception as exc:
            db.rollback()
            raise BackupError(f"Restore failed and was rolled back: {exc}") from exc

    # Outside the transaction on purpose, and deliberately not fatal. The rows
    # are committed by now, so raising here would report a failure for a restore
    # that succeeded — and because the data landed, the installation no longer
    # looks uninitialized, so the operator could neither retry nor understand
    # why. Say what is wrong and how to finish it instead.
    resync_warnings: list[str] = []
    try:
        _resync_sequences(db, say)
    except Exception as exc:  # noqa: BLE001 - the restore itself already succeeded
        db.rollback()
        resync_warnings.append(
            "Data restored, but identity sequences could not be reset, so creating new rows "
            f"will fail until they are: {exc}. Re-run `backup_cli.py restore --in <archive> "
            "--force` once the cause is fixed."
        )
        say(resync_warnings[-1])

    known = {t.name for t in backup_tables()}
    result = {
        "applied": applied,
        "skipped_tables": sorted(set(manifest.get("tables") or {}) - known),
        "warnings": report["warnings"] + resync_warnings,
        "total_rows": sum(applied.values()),
        "migrations_ran": False,
    }

    if run_migrations:
        say("running migrations")
        result["migrations_ran"] = _run_migrations(say)

    return result


def _resync_sequences(db: Session, say: Callable[[str], None]) -> None:
    """Move PostgreSQL identity sequences past the rows a restore just inserted.

    A restore writes primary keys explicitly, which never advances the sequence
    backing them. On a fresh target every sequence still sits at 1, so the first
    insert afterwards — the first person to sign in — collides with a restored
    row, and every write keeps failing until an operator fixes each sequence by
    hand.

    SQLite derives the next rowid from the table's contents and needs nothing
    here, which is exactly why this went unnoticed: the suite runs on SQLite.
    """
    # Ask the session what it is actually bound to rather than the module-level
    # DATABASE_URL: a caller can restore through a session pointed somewhere
    # else, and guessing wrong here silently skips the resync.
    if db.get_bind().dialect.name != "postgresql":
        return

    resynced = 0
    for table in backup_tables():
        for column in table.primary_key.columns:
            if not isinstance(column.type, (Integer, BigInteger)):
                continue
            # Identifiers cannot be bound parameters, so ask PostgreSQL for the
            # sequence by name and bind only values from here on.
            sequence = db.execute(
                text("SELECT pg_get_serial_sequence(:table_name, :column_name)").bindparams(
                    table_name=table.name, column_name=column.name
                )
            ).scalar()
            if not sequence:
                continue  # a plain integer key with no sequence behind it
            highest = db.execute(select(func.max(column))).scalar() or 0
            db.execute(
                text("SELECT setval(:sequence, :next_value, false)").bindparams(
                    sequence=sequence, next_value=highest + 1
                )
            )
            resynced += 1
    db.commit()
    say(f"reset {resynced} identity sequence(s)")


def _run_migrations(say: Callable[[str], None]) -> bool:
    """Bring a restored older database up to this installation's schema."""
    script = Path(__file__).resolve().parent / "run_migrations.py"
    try:
        completed = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            check=False,
            timeout=MIGRATION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # A migration waiting on a lock would otherwise pin this worker until
        # the process restarts — the same failure mode the project already
        # guards against for every requests.* call.
        say(
            f"migrations still running after {MIGRATION_TIMEOUT_SECONDS}s; the data is restored "
            "— check the server log, and run run_migrations.py if they did not finish"
        )
        return False
    if completed.returncode != 0:
        say("migrations reported failures; see output above")
        if completed.stdout:
            print(completed.stdout)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        return False
    return True
