#!/usr/bin/env python3
"""
Backup and restore an ActionsManager installation from the command line.

    python backup_cli.py backup  --out /app/data/backup.tar.gz
    python backup_cli.py validate --in /app/data/backup.tar.gz
    python backup_cli.py restore --in /app/data/backup.tar.gz [--dry-run] [--force]

This is the recovery path the web UI cannot provide. The first-boot restore
screen only exists while the application is running and serving requests; the
case backups exist for is an installation that no longer starts after a failed
upgrade, which is reachable only from here.

Restoring replaces all data. It refuses an installation that already has users
unless --force is given, so the everyday mistake — restoring over a live
workspace — takes a deliberate second step.
"""

import argparse
import sys
from pathlib import Path

from backup_engine import (
    BackupError,
    create_backup,
    restore_backup,
    validate_backup,
    workspace_is_uninitialized,
)
from database import SessionLocal


def _print_report(report: dict) -> None:
    manifest = report["manifest"]
    print(f"  Written by:   ActionsManager {manifest.get('app_version', 'unknown')}")
    print(f"  Created at:   {manifest.get('created_at', 'unknown')}")
    print(f"  Source DB:    {manifest.get('dialect', 'unknown')}")
    print(f"  Tables:       {len(report['tables'])}")
    print(f"  Total rows:   {report['total_rows']}")

    for warning in report["warnings"]:
        print(f"  ⚠️  {warning}")
    for error in report["errors"]:
        print(f"  ❌ {error}")


def cmd_backup(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        manifest = create_backup(db, Path(args.out))
    finally:
        db.close()

    total = sum(t["rows"] for t in manifest["tables"].values())
    size = Path(args.out).stat().st_size
    print(f"✅ Backup written to {args.out}")
    print(f"   {len(manifest['tables'])} table(s), {total} row(s), {size} bytes")
    if not manifest["secret_key_fingerprint"]:
        print("   ⚠️  No SECRET_KEY is configured, so this backup has no encrypted credentials.")
    else:
        print("   Keep SECRET_KEY safe: without it, restored access tokens cannot be decrypted.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        report = validate_backup(Path(args.source), db)
    finally:
        db.close()

    print(f"📦 {args.source}")
    _print_report(report)
    if report["ok"]:
        print("✅ Backup is valid and compatible with this installation.")
        return 0
    print("❌ Backup cannot be restored into this installation.")
    return 1


def cmd_restore(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        report = validate_backup(Path(args.source), db)
        print(f"📦 {args.source}")
        _print_report(report)

        if not report["ok"]:
            print("❌ Refusing to restore an invalid or incompatible backup.")
            return 1

        occupied = not workspace_is_uninitialized(db)
        if occupied and not args.force:
            print("❌ This installation already has users; restoring would replace their data.")
            print("   Re-run with --force if that is what you want.")
            return 1

        if args.dry_run:
            print("✅ Dry run only; nothing was written.")
            return 0

        if occupied:
            print("⚠️  Overwriting an installation that already has users (--force).")

        result = restore_backup(db, Path(args.source), force=args.force,
                                progress=lambda msg: print(f"   {msg}"))
    except BackupError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"✅ Restored {result['total_rows']} row(s) into {len(result['applied'])} table(s).")
    if result["skipped_tables"]:
        print(f"   Skipped unknown table(s): {', '.join(result['skipped_tables'])}")
    if not result["migrations_ran"]:
        print("   ⚠️  Migrations did not complete cleanly; run run_migrations.py and check the output.")
    print("   Sign in again — sessions are deliberately not carried across a restore.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backup_cli.py",
        description="Back up and restore an ActionsManager installation.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_backup = sub.add_parser("backup", help="Write a full backup archive")
    p_backup.add_argument("--out", required=True, help="Path to write the archive to")
    p_backup.set_defaults(func=cmd_backup)

    p_validate = sub.add_parser("validate", help="Check an archive without changing anything")
    p_validate.add_argument("--in", dest="source", required=True, help="Archive to check")
    p_validate.set_defaults(func=cmd_validate)

    p_restore = sub.add_parser("restore", help="Replace this installation's data with an archive")
    p_restore.add_argument("--in", dest="source", required=True, help="Archive to restore")
    p_restore.add_argument("--dry-run", action="store_true",
                           help="Report what would happen without writing")
    p_restore.add_argument("--force", action="store_true",
                           help="Allow overwriting an installation that already has users")
    p_restore.set_defaults(func=cmd_restore)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except BackupError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
