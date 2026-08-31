#!/usr/bin/env python3
"""Exercise the real 'Enforce Pipeline Result' script from main-pipeline.yml.

Extracts the step's run: block straight out of the workflow (no copy to drift),
strips the ${{ }} env indirection, and runs it under bash for each scenario.
Also checks the lane graph itself: the pipeline's whole gating model is that
every lane head hangs off resolve-pr-images, so gating that one job off gates
the run off - and that every stage is checked here.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[1] / "workflows" / "main-pipeline.yml"

wf = yaml.safe_load(open(WF))
jobs = wf["jobs"]
steps = jobs["pipeline-summary"]["steps"]
step = next(s for s in steps if s.get("name") == "Enforce Pipeline Result")
script = step["run"]

GATE = "resolve-pr-images"

# Three lanes running in parallel, each listed in the order it runs them.
LANES = {
    "runtime": ["health-check", "performance-testing"],
    "source": ["linting", "sbom-generation"],
    "security": ["security-scan"],
}
STAGES = [job for lane in LANES.values() for job in lane]

structure = []
for lane, stages in LANES.items():
    # The gate propagates only because every lane hangs off it: skip that one
    # job on an unlabeled PR and GitHub's default needs: gate skips the rest.
    if GATE not in (jobs[stages[0]].get("needs") or []):
        structure.append(f"{stages[0]} heads the {lane} lane and must list {GATE} in needs:")
    for earlier, later in zip(stages, stages[1:]):
        if earlier not in (jobs[later].get("needs") or []):
            structure.append(f"{later} must list {earlier} in needs: to keep the {lane} lane in order")

summary_needs = jobs["pipeline-summary"].get("needs") or []
for job in [GATE, *STAGES]:
    if job not in summary_needs:
        structure.append(f"pipeline-summary must list {job} in needs:")

# A stage the gate does not read is a stage that can fail or vanish silently.
gate_refs = " ".join(step["env"].values())
for job in [GATE, *STAGES]:
    if f"needs.{job}.result" not in gate_refs:
        structure.append(f"the summary gate does not check {job}")

BASE = {
    "RESULT_RESOLVE": "success",
    "RESULT_LINTING": "success",
    "RESULT_PERFORMANCE": "success",
    "RESULT_SECURITY_SCAN": "success",
    "RESULT_HEALTH_CHECK": "success",
    "RESULT_SBOM": "success",
}

# The runtime lane failed at its head, so Performance Testing never ran. The
# gate must blame Health Check and not the stage it took down with it.
LANE_CASCADE = {
    "RESULT_HEALTH_CHECK": "failure",
    "RESULT_PERFORMANCE": "skipped",
}

# Same failure, but a stage in a *different* lane also went missing. That skip
# has nothing to do with the runtime lane and must still be reported - this is
# what the per-lane flag exists for.
CROSS_LANE = {**LANE_CASCADE, "RESULT_SBOM": "skipped"}

# The gate feeds every lane, so its failure explains skips in all of them.
GATE_FAILED = {
    "RESULT_RESOLVE": "failure",
    "RESULT_HEALTH_CHECK": "skipped",
    "RESULT_PERFORMANCE": "skipped",
    "RESULT_LINTING": "skipped",
    "RESULT_SBOM": "skipped",
    "RESULT_SECURITY_SCAN": "skipped",
}

# (name, env overrides, expected exit code, substring that must NOT appear,
#  substring that must appear)
CASES = [
    ("all green", {}, 0, None, None),
    # every stage failing is a pipeline failure
    ("resolve failed", {"RESULT_RESOLVE": "failure"}, 1, None, None),
    ("linting failed", {"RESULT_LINTING": "failure"}, 1, None, None),
    ("performance failed", {"RESULT_PERFORMANCE": "failure"}, 1, None, None),
    ("security scan failed", {"RESULT_SECURITY_SCAN": "failure"}, 1, None, None),
    ("health-check failed", {"RESULT_HEALTH_CHECK": "failure"}, 1, None, None),
    ("sbom failed", {"RESULT_SBOM": "failure"}, 1, None, None),
    # the regressions this step exists to catch: a stage that quietly did not
    # run, with no failure in its own lane to explain it
    ("resolve silently skipped", {"RESULT_RESOLVE": "skipped"}, 1, None, None),
    ("linting silently skipped", {"RESULT_LINTING": "skipped"}, 1, None, None),
    ("performance silently skipped", {"RESULT_PERFORMANCE": "skipped"}, 1, None, None),
    ("security scan silently skipped", {"RESULT_SECURITY_SCAN": "skipped"}, 1, None, None),
    ("health-check silently skipped", {"RESULT_HEALTH_CHECK": "skipped"}, 1, None, None),
    ("sbom silently skipped", {"RESULT_SBOM": "skipped"}, 1, None, None),
    ("cancelled counts as a problem", {"RESULT_LINTING": "cancelled"}, 1, None, None),
    # a failure explains the skips behind it in its own lane...
    ("lane cascade blames only the failure", LANE_CASCADE, 1, "SKIPPED", None),
    # ...and nowhere else
    ("a failure does not excuse another lane's skip", CROSS_LANE, 1, None,
     "SBOM Generation was SKIPPED"),
    # the gate feeds every lane, so its failure explains all of them
    ("gate failure explains every lane", GATE_FAILED, 1, "SKIPPED",
     "Resolve PR Images reported"),
]

def read_summary(path):
    with open(path) as handle:
        return handle.read()


failures = []
for name, overrides, expected, forbidden, required in CASES:
    env = dict(os.environ)
    env.update(BASE)
    env.update(overrides)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as summary:
        env["GITHUB_STEP_SUMMARY"] = summary.name
    proc = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True
    )
    ok = proc.returncode == expected
    report = proc.stdout + read_summary(env["GITHUB_STEP_SUMMARY"])
    if ok and forbidden and forbidden in report:
        ok = False
    if ok and required and required not in report:
        ok = False
    print(f"{'PASS' if ok else 'FAIL'}  exit={proc.returncode} (want {expected})  {name}")
    if not ok:
        failures.append(name)
        print("  report:", report.strip()[:400])
        print("  stderr:", proc.stderr.strip()[:400])
    os.unlink(env["GITHUB_STEP_SUMMARY"])

print()
for problem in structure:
    print(f"FAIL  lane graph: {problem}")
if structure:
    print(f"{len(structure)} lane-graph problem(s)")
elif not failures:
    for lane, stages in LANES.items():
        print(f"lane OK: {GATE} -> {' -> '.join(stages)}  ({lane})")

if failures:
    print(f"{len(failures)} scenario(s) failed: {failures}")
if failures or structure:
    sys.exit(1)
print(f"all {len(CASES)} scenarios passed")
