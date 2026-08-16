#!/usr/bin/env python3
"""
Fail if a workflow treats "main" as a branch of this repository.

dawg-io/actions-manager has no main branch - develop is the default and the
only long-lived branch, and releases are cut as release/<version> by
promote-to-public.yml. main exists only in the public production repo
(dawg-io/actions-manager), which runs no pipelines. So a main trigger or ref
condition here is dead code in both directions: the branch does not exist, and
these workflows never execute where it does.

Referring to the *public* repo's main as a push target is fine, and is what
EXEMPT covers.

Usage: python3 .github/scripts/check_no_main_refs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"

# Workflows allowed to say "main" because they mean the public repo's branch.
EXEMPT = {
    "promote-to-public.yml": (
        "pushes the sanitised release tree to dawg-io/actions-manager's main"
    ),
}

# A branch-of-this-repo reference: a trigger list entry, or a ref comparison.
PATTERNS = (
    re.compile(r"^\s*-\s*[\"']?main[\"']?\s*(?:#.*)?$"),
    re.compile(r"(?:ref_name|head_branch|base_ref|base\.ref)\s*==\s*[\"']main[\"']"),
    re.compile(r"github\.ref\s*==\s*[\"']refs/heads/main[\"']"),
    re.compile(r"==\s*[\"']refs/heads/main[\"']"),
)


def main() -> int:
    problems: list[str] = []

    for path in sorted(WORKFLOWS.glob("*.yml")):
        if path.name in EXEMPT:
            print(f"exempt: {path.name} - {EXEMPT[path.name]}")
            continue

        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue  # commented-out code is inert, not a live reference
            if any(pattern.search(line) for pattern in PATTERNS):
                problems.append(
                    f"{path.name}:{lineno}: refers to a 'main' branch of this "
                    f"repo, which does not exist - use 'develop' or "
                    f"'release/**'\n      {stripped}"
                )

    if problems:
        print("\nDead 'main' branch reference check FAILED:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
            print(f"::error::{problem.splitlines()[0]}")
        return 1

    print("OK: no workflow refers to a 'main' branch of this repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
