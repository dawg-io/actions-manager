#!/usr/bin/env python3
"""Exercise the real 'Enforce Pipeline Result' script from main-pipeline.yml.

Extracts the step's run: block straight out of the workflow (no copy to drift),
strips the ${{ }} env indirection, and runs it under bash for each scenario.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[1] / "workflows" / "main-pipeline.yml"

wf = yaml.safe_load(open(WF))
steps = wf["jobs"]["pipeline-summary"]["steps"]
step = next(s for s in steps if s.get("name") == "Enforce Pipeline Result")
script = step["run"]

BASE = {
    "FULL_PIPELINE": "true",
    "EVENT_NAME": "push",
    "RESULT_LOAD_CONFIG": "success",
    "RESULT_LINTING": "success",
    "RESULT_DOCKER_BUILD": "success",
    "RESULT_SECURITY_SCAN": "success",
    "RESULT_HEALTH_CHECK": "success",
    "RESULT_PERFORMANCE": "success",
    "RESULT_SBOM": "success",
}

# (name, env overrides, expected exit code)
CASES = [
    ("all green on push", {}, 0),
    ("linting failed", {"RESULT_LINTING": "failure"}, 1),
    ("security scan failed", {"RESULT_SECURITY_SCAN": "failure"}, 1),
    ("docker build failed", {"RESULT_DOCKER_BUILD": "failure"}, 1),
    # the regressions this step exists to catch:
    ("health-check silently skipped", {"RESULT_HEALTH_CHECK": "skipped"}, 1),
    ("sbom silently skipped", {"RESULT_SBOM": "skipped"}, 1),
    ("performance silently skipped", {"RESULT_PERFORMANCE": "skipped"}, 1),
    ("health-check failed (was ignored before)", {"RESULT_HEALTH_CHECK": "failure"}, 1),
    ("performance failed (was ignored before)", {"RESULT_PERFORMANCE": "failure"}, 1),
    ("sbom failed (was ignored before)", {"RESULT_SBOM": "failure"}, 1),
    # legitimate skips that must stay green:
    (
        "docker-build skipped on pull_request (intentional)",
        {"EVENT_NAME": "pull_request", "RESULT_DOCKER_BUILD": "skipped"},
        0,
    ),
    (
        "everything skipped when full_pipeline is false",
        {
            "FULL_PIPELINE": "false",
            "RESULT_LINTING": "skipped",
            "RESULT_SECURITY_SCAN": "skipped",
            "RESULT_HEALTH_CHECK": "skipped",
            "RESULT_PERFORMANCE": "skipped",
            "RESULT_SBOM": "skipped",
        },
        0,
    ),
    # docker-build skipped on a push is NOT expected - that is a real problem
    ("docker-build skipped on push", {"RESULT_DOCKER_BUILD": "skipped"}, 1),
    ("cancelled counts as a problem", {"RESULT_LINTING": "cancelled"}, 1),
]

failures = []
for name, overrides, expected in CASES:
    env = dict(os.environ)
    env.update(BASE)
    env.update(overrides)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as summary:
        env["GITHUB_STEP_SUMMARY"] = summary.name
    proc = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True
    )
    ok = proc.returncode == expected
    print(f"{'PASS' if ok else 'FAIL'}  exit={proc.returncode} (want {expected})  {name}")
    if not ok:
        failures.append(name)
        print("  stdout:", proc.stdout.strip()[:400])
        print("  stderr:", proc.stderr.strip()[:400])
    os.unlink(env["GITHUB_STEP_SUMMARY"])

print()
if failures:
    print(f"{len(failures)} scenario(s) failed: {failures}")
    sys.exit(1)
print(f"all {len(CASES)} scenarios passed")
