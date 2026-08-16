#!/usr/bin/env python3
"""
Fail if a workflow job runs on a GitHub-hosted runner.

This repo is private, so GitHub-hosted minutes are billed. Everything that can
run on our own infra must, and anything that genuinely cannot needs an explicit
entry in EXEMPT below with a reason - so the next one is a deliberate decision
rather than a surprise on the invoice.

Usage: python3 .github/scripts/check_runner_labels.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"

# Runner labels we own. Anything containing "self-hosted" is ours by definition.
SELF_HOSTED_LABELS = {"pmox-runner", "claude-runner"}

# (workflow filename, job id) -> why this one is allowed to bill.
EXEMPT = {
    (
        "self-hosted-image.yml",
        "build-fork-validation",
    ): (
        "Fork PRs must never execute untrusted code on our persistent "
        "self-hosted runners. Validation-only, never pushed, and skipped "
        "entirely on same-repo PRs."
    ),
}


def is_self_hosted(runs_on) -> bool:
    labels = [runs_on] if isinstance(runs_on, str) else list(runs_on or [])
    return any(
        label in SELF_HOSTED_LABELS or "self-hosted" in str(label)
        for label in labels
    )


def main() -> int:
    problems: list[str] = []
    exempt_seen: set[tuple[str, str]] = set()

    for path in sorted(WORKFLOWS.glob("*.yml")):
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: not valid YAML: {exc}")
            continue
        if not isinstance(data, dict):
            continue

        for job_id, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict) or "runs-on" not in job:
                continue  # reusable-workflow call, or malformed - not ours to judge

            key = (path.name, job_id)
            runs_on = job["runs-on"]

            if is_self_hosted(runs_on):
                if key in EXEMPT:
                    exempt_seen.add(key)
                    problems.append(
                        f"{path.name}: job '{job_id}' is exempted in "
                        f"check_runner_labels.py but now runs on {runs_on!r} - "
                        "drop the stale EXEMPT entry"
                    )
                continue

            if key in EXEMPT:
                exempt_seen.add(key)
                print(f"exempt: {path.name}: {job_id} ({runs_on}) - {EXEMPT[key]}")
                continue

            problems.append(
                f"{path.name}: job '{job_id}' runs on {runs_on!r}, a "
                "GitHub-hosted runner. This repo is private, so those minutes "
                "are billed. Use 'pmox-runner', or add an EXEMPT entry with a "
                "reason in .github/scripts/check_runner_labels.py."
            )

    for key in EXEMPT.keys() - exempt_seen:
        problems.append(
            f"{key[0]}: EXEMPT entry for job '{key[1]}' no longer matches any "
            "GitHub-hosted job - remove it"
        )

    if problems:
        print("\nGitHub-hosted runner check FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
            print(f"::error::{problem}")
        return 1

    print("OK: every workflow job runs on self-hosted infra (or is exempt).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
