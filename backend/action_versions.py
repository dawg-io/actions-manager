"""Pinned GitHub Action versions used by generated/prebuilt workflow templates.

Single source of truth for build_detector.py and workflow_templates.py --
bump a version here once instead of hunting through generated YAML strings.
Checked against `gh api repos/<action>/releases/latest`.
"""

_V7 = "v7.0.0"

ACTION_VERSIONS = {
    "actions/checkout": "v7.0.1",
    "actions/setup-java": "v5.7.0",
    "actions/setup-node": _V7,
    "actions/setup-python": _V7,
    "actions/setup-go": _V7,
    "actions/setup-dotnet": "v6.0.0",
    "actions/cache": "v6.1.0",
}
