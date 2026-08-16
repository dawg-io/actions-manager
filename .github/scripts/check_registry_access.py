#!/usr/bin/env python3
"""
Fail if a workflow builds or pulls an image without registry access.

backend/Dockerfile and frontend/Dockerfile both FROM the *private*
ghcr.io/<repo>/base-backend and base-frontend images, so any job that runs
`docker build` or `docker pull` needs BOTH:

  * a docker/login-action step   - missing => 401 Unauthorized
  * packages: read permission    - missing => 403 Forbidden

This exact bug has now been fixed five separate times:
  security-scan.yml, health-check.yml, performance-testing.yml (401s), and
  pr-validation.yml (403, missing permission rather than missing login).
It keeps recurring because the failure only appears at runtime, in whichever
job happens to take the local-build path.

Usage: python3 .github/scripts/check_registry_access.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"

BUILD_MARKERS = ("docker build", "docker pull")

# Workflows that touch images but legitimately need no private-base access.
EXEMPT = {
    # Retags an existing published image by digest; never builds from a
    # Dockerfile, so no private base image is ever resolved.
    "retag-self-hosted-image.yml": "retags published images, never builds",
}


def job_text(job: dict) -> str:
    return "\n".join(
        str(step.get("run", "")) for step in job.get("steps", []) or [] if isinstance(step, dict)
    )


def has_login(job: dict) -> bool:
    return any(
        "docker/login-action" in str(step.get("uses", ""))
        for step in job.get("steps", []) or []
        if isinstance(step, dict)
    )


def packages_ok(perms) -> bool:
    if perms == "write-all":
        return True
    return isinstance(perms, dict) and perms.get("packages") in {"read", "write"}


def main() -> int:
    problems: list[str] = []

    for path in sorted(WORKFLOWS.glob("*.yml")):
        if path.name in EXEMPT:
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue

        top_perms = data.get("permissions")

        for job_id, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict) or "steps" not in job:
                continue
            body = job_text(job)
            if not any(marker in body for marker in BUILD_MARKERS):
                continue

            where = f"{path.name}: job '{job_id}'"
            if not has_login(job):
                problems.append(
                    f"{where} runs docker build/pull with no docker/login-action "
                    "step - the private base image pull will 401"
                )
            if not packages_ok(job.get("permissions") or top_perms):
                problems.append(
                    f"{where} runs docker build/pull without 'packages: read' "
                    "permission - the private base image pull will 403"
                )

    if problems:
        print("\nRegistry access check FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
            print(f"::error::{problem}")
        return 1

    print("OK: every image-building job has a registry login and packages access.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
