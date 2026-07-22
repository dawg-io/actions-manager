#!/usr/bin/env python3
"""
Check for new SonarQube issues introduced today on the current branch or PR.

Reads the CE task ID written by sonar-scanner to .scannerwork/report-task.txt,
waits for the background analysis to complete, then queries SonarQube for any
CONFIRMED or OPEN issues with a creation date matching today.  Exits non-zero
and prints a Markdown summary when new issues are found.

Environment variables (all required unless noted):
  SONAR_HOST_URL           SonarQube server base URL
  SONAR_TOKEN              Authentication token
  SONAR_PROJECT_KEY        Project key (may also be passed as first CLI argument)
  SONAR_REPORT_TASK_PATH   Optional override for .scannerwork/report-task.txt path

Exit codes:
  0  No new issues found today
  1  New issues found (readable summary printed to stdout)
  2  Configuration or API error
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

MAX_WAIT_SECONDS = 300
POLL_INTERVAL_SECONDS = 10
MAX_ISSUES_IN_TABLE = 50
MAX_PAGE_SIZE = 100
DEFAULT_REPORT_TASK_PATH = ".scannerwork/report-task.txt"


def make_auth_header(token: str) -> dict:
    encoded = base64.b64encode(f"{token}:".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def sonar_get(base_url: str, path: str, params: dict, token: str) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{base_url.rstrip('/')}{path}?{query}"
    req = urllib.request.Request(url, headers=make_auth_header(token))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"SonarQube API error {exc.code} for {path}: {body}") from exc


def get_task_id_from_report(report_path: str) -> str | None:
    """Read the CE task ID written by sonar-scanner to report-task.txt."""
    try:
        with open(report_path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("ceTaskId="):
                    return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return None


def wait_for_analysis(base_url: str, token: str, task_id: str) -> None:
    """Poll /api/ce/task until the analysis reaches SUCCESS; exit on failure or timeout."""
    waited = 0
    while waited < MAX_WAIT_SECONDS:
        data = sonar_get(base_url, "/api/ce/task", {"id": task_id}, token)
        status = data.get("task", {}).get("status", "PENDING")
        if status == "SUCCESS":
            return
        if status in ("FAILED", "CANCELED"):
            print(f"SonarQube analysis task {task_id} ended with status: {status}", file=sys.stderr)
            sys.exit(2)
        print(f"  Waiting for analysis task {task_id}… status={status} ({waited}s elapsed)")
        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS
    print(
        f"Timed out waiting for SonarQube analysis task {task_id} after {MAX_WAIT_SECONDS}s",
        file=sys.stderr,
    )
    sys.exit(2)


def query_new_issues(base_url: str, token: str, project_key: str, today: str) -> list:
    """Fetch all CONFIRMED/OPEN issues with a creation date matching today."""
    all_issues: list = []
    page = 1
    while True:
        params = {
            "componentKeys": project_key,
            "createdAfter": today,
            "createdBefore": today,
            "issueStatuses": "CONFIRMED,OPEN",
            "ps": MAX_PAGE_SIZE,
            "p": page,
        }
        data = sonar_get(base_url, "/api/issues/search", params, token)
        issues = data.get("issues", [])
        all_issues.extend(issues)
        total = data.get("total", len(all_issues))
        if len(all_issues) >= total or not issues:
            break
        page += 1
    return all_issues


def _component_path(issue: dict) -> str:
    component = issue.get("component", "")
    project = issue.get("project", "")
    if project and component.startswith(f"{project}:"):
        return component[len(project) + 1:]
    return component or "N/A"


def _line_number(issue: dict) -> str:
    if issue.get("line") is not None:
        return str(issue["line"])
    start = (issue.get("textRange") or {}).get("startLine")
    return str(start) if start is not None else "N/A"


def format_issue_summary(issues: list, base_url: str, project_key: str, today: str) -> str:
    """Return a Markdown table summarising new issues for CI log output."""
    encoded_key = urllib.parse.quote(project_key, safe="")
    query_url = (
        f"{base_url}/project/issues"
        f"?createdAfter={today}"
        f"&createdBefore={today}"
        f"&issueStatuses=CONFIRMED%2COPEN"
        f"&id={encoded_key}"
    )
    lines = [
        f"## \u274c SonarQube: {len(issues)} new issue(s) found on {today}",
        "",
        f"**Project:** `{project_key}`",
        f"**Query:** {query_url}",
        "",
        "| # | Severity | Type | Rule | File | Line | Message |",
        "|---|----------|------|------|------|------|---------|",
    ]
    for i, issue in enumerate(issues[:MAX_ISSUES_IN_TABLE], 1):
        severity = issue.get("severity", "N/A")
        itype = issue.get("type", "N/A")
        rule = issue.get("rule", "N/A")
        file_path = _component_path(issue)
        line = _line_number(issue)
        message = (issue.get("message") or "N/A")[:80]
        lines.append(
            f"| {i} | {severity} | {itype} | `{rule}` | `{file_path}` | {line} | {message} |"
        )
    if len(issues) > MAX_ISSUES_IN_TABLE:
        remaining = len(issues) - MAX_ISSUES_IN_TABLE
        lines.append(f"\n_\u2026and {remaining} more issue(s) not shown._")
    return "\n".join(lines)


def main() -> int:
    base_url = os.environ.get("SONAR_HOST_URL", "").rstrip("/")
    token = os.environ.get("SONAR_TOKEN", "")
    project_key = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("SONAR_PROJECT_KEY", "")
    )

    if not base_url:
        print("Error: SONAR_HOST_URL is not set.", file=sys.stderr)
        return 2
    if not token:
        print("Error: SONAR_TOKEN is not set.", file=sys.stderr)
        return 2
    if not project_key:
        print(
            "Error: project key required (pass as CLI argument or set SONAR_PROJECT_KEY).",
            file=sys.stderr,
        )
        return 2

    today = date.today().isoformat()
    print(f"Checking SonarQube for new issues: project={project_key}, date={today}")

    report_path = os.environ.get("SONAR_REPORT_TASK_PATH", DEFAULT_REPORT_TASK_PATH)
    task_id = get_task_id_from_report(report_path)
    if task_id:
        print(f"Found CE task ID: {task_id}. Waiting for analysis to complete…")
        wait_for_analysis(base_url, token, task_id)
        print("Analysis completed successfully.")
    else:
        print(f"No report-task.txt found at {report_path}; skipping analysis wait.")

    try:
        issues = query_new_issues(base_url, token, project_key, today)
    except RuntimeError as exc:
        print(f"Error querying SonarQube: {exc}", file=sys.stderr)
        return 2

    if not issues:
        print(f"\u2713 No new SonarQube issues found for project '{project_key}' on {today}.")
        return 0

    print(format_issue_summary(issues, base_url, project_key, today))
    return 1


if __name__ == "__main__":
    sys.exit(main())
