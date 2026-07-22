"""
Tests for .github/scripts/check_sonar_new_issues.py

Covers: get_task_id_from_report, wait_for_analysis, query_new_issues,
        format_issue_summary, and the main() entry-point.
All HTTP calls and blocking sleeps are mocked — no live SonarQube connection
is required.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

# Make the parent scripts directory importable without installation.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_sonar_new_issues as script


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_issue(key: str = "ISSUE-1", project: str = "proj") -> dict:
    return {
        "key": key,
        "rule": f"rule:{key}",
        "severity": "MAJOR",
        "type": "CODE_SMELL",
        "component": f"{project}:src/file.py",
        "project": project,
        "line": 10,
        "message": f"Message for {key}",
    }


def _api_page(issues: list, total: int | None = None) -> dict:
    return {"issues": issues, "total": total if total is not None else len(issues)}


# ---------------------------------------------------------------------------
# get_task_id_from_report
# ---------------------------------------------------------------------------

class TestGetTaskIdFromReport(unittest.TestCase):
    def test_reads_task_id(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
            fh.write("serverUrl=https://sonarqube.example.com\n")
            fh.write("ceTaskId=abc123\n")
            fh.write("projectKey=my-project\n")
            path = fh.name
        self.assertEqual(script.get_task_id_from_report(path), "abc123")

    def test_returns_none_for_missing_file(self):
        self.assertIsNone(script.get_task_id_from_report("/nonexistent/report-task.txt"))

    def test_returns_none_when_key_absent(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
            fh.write("serverUrl=https://sonarqube.example.com\n")
            path = fh.name
        self.assertIsNone(script.get_task_id_from_report(path))

    def test_handles_value_containing_equals_sign(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
            fh.write("ceTaskId=abc=123\n")
            path = fh.name
        self.assertEqual(script.get_task_id_from_report(path), "abc=123")

    def test_returns_first_matching_line(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
            fh.write("ceTaskId=first\n")
            fh.write("ceTaskId=second\n")
            path = fh.name
        self.assertEqual(script.get_task_id_from_report(path), "first")


# ---------------------------------------------------------------------------
# format_issue_summary
# ---------------------------------------------------------------------------

class TestFormatIssueSummary(unittest.TestCase):
    _BASE = "https://sq.example.com"
    _KEY = "my-proj"
    _TODAY = "2026-07-03"

    def test_zero_issues_shows_count(self):
        result = script.format_issue_summary([], self._BASE, self._KEY, self._TODAY)
        self.assertIn("0 new issue(s)", result)
        self.assertIn(self._KEY, result)
        self.assertIn(self._TODAY, result)

    def test_single_issue_appears_in_table(self):
        issues = [_make_issue()]
        result = script.format_issue_summary(issues, self._BASE, self._KEY, self._TODAY)
        self.assertIn("1 new issue(s)", result)
        self.assertIn("src/file.py", result)
        self.assertIn("MAJOR", result)

    def test_query_url_contains_correct_date_params(self):
        issues = [_make_issue()]
        result = script.format_issue_summary(issues, self._BASE, self._KEY, self._TODAY)
        self.assertIn(f"createdAfter={self._TODAY}", result)
        self.assertIn(f"createdBefore={self._TODAY}", result)
        self.assertIn("issueStatuses=CONFIRMED%2COPEN", result)

    def test_query_url_contains_project_id(self):
        issues = [_make_issue()]
        result = script.format_issue_summary(issues, self._BASE, self._KEY, self._TODAY)
        self.assertIn(f"id={self._KEY}", result)

    def test_project_prefix_stripped_from_component(self):
        issue = {
            "key": "K1",
            "rule": "r:1",
            "severity": "MINOR",
            "type": "BUG",
            "component": "my-proj:src/foo.py",
            "project": "my-proj",
            "line": 5,
            "message": "msg",
        }
        result = script.format_issue_summary([issue], self._BASE, self._KEY, self._TODAY)
        self.assertIn("src/foo.py", result)
        self.assertNotIn("my-proj:src/foo.py", result)

    def test_missing_line_shows_na(self):
        issue = {"key": "K1", "rule": "r:1", "severity": "MINOR", "type": "BUG",
                 "component": "proj:f.py", "project": "proj", "message": "msg"}
        result = script.format_issue_summary([issue], self._BASE, "proj", self._TODAY)
        self.assertIn("N/A", result)

    def test_text_range_used_when_line_absent(self):
        issue = {"key": "K1", "rule": "r:1", "severity": "MINOR", "type": "BUG",
                 "component": "proj:f.py", "project": "proj",
                 "textRange": {"startLine": 42}, "message": "msg"}
        result = script.format_issue_summary([issue], self._BASE, "proj", self._TODAY)
        self.assertIn("42", result)

    def test_truncation_note_shown_beyond_50(self):
        issues = [_make_issue(f"ISSUE-{i}") for i in range(55)]
        result = script.format_issue_summary(issues, self._BASE, self._KEY, self._TODAY)
        self.assertIn("5 more issue(s)", result)

    def test_no_truncation_note_for_exactly_50(self):
        issues = [_make_issue(f"ISSUE-{i}") for i in range(50)]
        result = script.format_issue_summary(issues, self._BASE, self._KEY, self._TODAY)
        self.assertNotIn("more issue(s)", result)

    def test_long_message_truncated_at_80_chars(self):
        long_msg = "x" * 100
        issue = {**_make_issue(), "message": long_msg}
        result = script.format_issue_summary([issue], self._BASE, self._KEY, self._TODAY)
        self.assertNotIn("x" * 100, result)
        self.assertIn("x" * 80, result)


# ---------------------------------------------------------------------------
# query_new_issues
# ---------------------------------------------------------------------------

class TestQueryNewIssues(unittest.TestCase):
    @patch("check_sonar_new_issues.sonar_get")
    def test_returns_empty_list_when_no_issues(self, mock_get):
        mock_get.return_value = _api_page([])
        result = script.query_new_issues("https://sq.example.com", "tok", "proj", "2026-07-03")
        self.assertEqual(result, [])

    @patch("check_sonar_new_issues.sonar_get")
    def test_returns_issues_from_single_page(self, mock_get):
        mock_get.return_value = _api_page([_make_issue()])
        result = script.query_new_issues("https://sq.example.com", "tok", "proj", "2026-07-03")
        self.assertEqual(len(result), 1)

    @patch("check_sonar_new_issues.sonar_get")
    def test_paginates_when_total_exceeds_page_size(self, mock_get):
        page1 = [_make_issue(f"I-{i}") for i in range(100)]
        page2 = [_make_issue("I-100")]
        mock_get.side_effect = [
            {"issues": page1, "total": 101},
            {"issues": page2, "total": 101},
        ]
        result = script.query_new_issues("https://sq.example.com", "tok", "proj", "2026-07-03")
        self.assertEqual(len(result), 101)
        self.assertEqual(mock_get.call_count, 2)

    @patch("check_sonar_new_issues.sonar_get")
    def test_query_params_match_expected_values(self, mock_get):
        mock_get.return_value = _api_page([])
        script.query_new_issues("https://sq.example.com", "tok", "my-proj", "2026-07-03")
        _, _, params, _ = mock_get.call_args[0]
        self.assertEqual(params["createdAfter"], "2026-07-03")
        self.assertEqual(params["createdBefore"], "2026-07-03")
        self.assertEqual(params["issueStatuses"], "CONFIRMED,OPEN")
        self.assertEqual(params["componentKeys"], "my-proj")

    @patch("check_sonar_new_issues.sonar_get")
    def test_stops_when_returned_issues_empty(self, mock_get):
        mock_get.side_effect = [
            {"issues": [], "total": 5},
        ]
        result = script.query_new_issues("https://sq.example.com", "tok", "proj", "2026-07-03")
        self.assertEqual(result, [])
        self.assertEqual(mock_get.call_count, 1)


# ---------------------------------------------------------------------------
# wait_for_analysis
# ---------------------------------------------------------------------------

class TestWaitForAnalysis(unittest.TestCase):
    @patch("check_sonar_new_issues.time.sleep")
    @patch("check_sonar_new_issues.sonar_get")
    def test_returns_immediately_on_success(self, mock_get, mock_sleep):
        mock_get.return_value = {"task": {"status": "SUCCESS"}}
        script.wait_for_analysis("https://sq.example.com", "tok", "T-1")
        mock_sleep.assert_not_called()

    @patch("check_sonar_new_issues.time.sleep")
    @patch("check_sonar_new_issues.sonar_get")
    def test_polls_until_success(self, mock_get, mock_sleep):
        mock_get.side_effect = [
            {"task": {"status": "PENDING"}},
            {"task": {"status": "IN_PROGRESS"}},
            {"task": {"status": "SUCCESS"}},
        ]
        script.wait_for_analysis("https://sq.example.com", "tok", "T-1")
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("check_sonar_new_issues.time.sleep")
    @patch("check_sonar_new_issues.sonar_get")
    def test_exits_2_on_failed_status(self, mock_get, mock_sleep):
        mock_get.return_value = {"task": {"status": "FAILED"}}
        with self.assertRaises(SystemExit) as ctx:
            script.wait_for_analysis("https://sq.example.com", "tok", "T-1")
        self.assertEqual(ctx.exception.code, 2)

    @patch("check_sonar_new_issues.time.sleep")
    @patch("check_sonar_new_issues.sonar_get")
    def test_exits_2_on_canceled_status(self, mock_get, mock_sleep):
        mock_get.return_value = {"task": {"status": "CANCELED"}}
        with self.assertRaises(SystemExit) as ctx:
            script.wait_for_analysis("https://sq.example.com", "tok", "T-1")
        self.assertEqual(ctx.exception.code, 2)

    @patch("check_sonar_new_issues.MAX_WAIT_SECONDS", 20)
    @patch("check_sonar_new_issues.POLL_INTERVAL_SECONDS", 10)
    @patch("check_sonar_new_issues.time.sleep")
    @patch("check_sonar_new_issues.sonar_get")
    def test_exits_2_on_timeout(self, mock_get, mock_sleep):
        mock_get.return_value = {"task": {"status": "PENDING"}}
        with self.assertRaises(SystemExit) as ctx:
            script.wait_for_analysis("https://sq.example.com", "tok", "T-1")
        self.assertEqual(ctx.exception.code, 2)


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

class TestMain(unittest.TestCase):
    _BASE_ENV = {
        "SONAR_HOST_URL": "https://sq.example.com",
        "SONAR_TOKEN": "test-token",
        "SONAR_PROJECT_KEY": "",
    }

    def _run_main(self, argv: list, env_overrides: dict | None = None) -> int:
        env = {**self._BASE_ENV, **(env_overrides or {})}
        with patch.dict(os.environ, env, clear=False):
            with patch.object(sys, "argv", argv):
                return script.main()

    def test_returns_2_when_host_url_missing(self):
        result = self._run_main(["s.py", "my-proj"], {"SONAR_HOST_URL": ""})
        self.assertEqual(result, 2)

    def test_returns_2_when_token_missing(self):
        result = self._run_main(["s.py", "my-proj"], {"SONAR_TOKEN": ""})
        self.assertEqual(result, 2)

    def test_returns_2_when_project_key_missing(self):
        result = self._run_main(["s.py"])
        self.assertEqual(result, 2)

    @patch("check_sonar_new_issues.query_new_issues", return_value=[])
    @patch("check_sonar_new_issues.get_task_id_from_report", return_value=None)
    def test_returns_0_when_no_issues(self, _report, _query):
        result = self._run_main(["s.py", "my-proj"])
        self.assertEqual(result, 0)

    @patch("check_sonar_new_issues.query_new_issues")
    @patch("check_sonar_new_issues.get_task_id_from_report", return_value=None)
    def test_returns_1_when_issues_found(self, _report, mock_query):
        mock_query.return_value = [_make_issue()]
        result = self._run_main(["s.py", "my-proj"])
        self.assertEqual(result, 1)

    @patch("check_sonar_new_issues.wait_for_analysis")
    @patch("check_sonar_new_issues.query_new_issues", return_value=[])
    @patch("check_sonar_new_issues.get_task_id_from_report", return_value="task-abc")
    def test_waits_for_analysis_when_task_id_found(self, _report, _query, mock_wait):
        self._run_main(["s.py", "my-proj"])
        mock_wait.assert_called_once_with("https://sq.example.com", "test-token", "task-abc")

    @patch("check_sonar_new_issues.wait_for_analysis")
    @patch("check_sonar_new_issues.query_new_issues", return_value=[])
    @patch("check_sonar_new_issues.get_task_id_from_report", return_value=None)
    def test_skips_wait_when_no_task_id(self, _report, _query, mock_wait):
        self._run_main(["s.py", "my-proj"])
        mock_wait.assert_not_called()

    @patch("check_sonar_new_issues.query_new_issues", side_effect=RuntimeError("connection refused"))
    @patch("check_sonar_new_issues.get_task_id_from_report", return_value=None)
    def test_returns_2_on_api_error(self, _report, _query):
        result = self._run_main(["s.py", "my-proj"])
        self.assertEqual(result, 2)

    @patch("check_sonar_new_issues.query_new_issues", return_value=[])
    @patch("check_sonar_new_issues.get_task_id_from_report", return_value=None)
    def test_project_key_from_env_when_no_argv(self, _report, _query):
        result = self._run_main(["s.py"], {"SONAR_PROJECT_KEY": "env-proj"})
        self.assertEqual(result, 0)

    @patch("check_sonar_new_issues.query_new_issues", return_value=[])
    @patch("check_sonar_new_issues.get_task_id_from_report", return_value=None)
    def test_argv_project_key_takes_precedence_over_env(self, _report, mock_query):
        self._run_main(["s.py", "argv-proj"], {"SONAR_PROJECT_KEY": "env-proj"})
        _, _, project_key, _ = mock_query.call_args[0]
        self.assertEqual(project_key, "argv-proj")


if __name__ == "__main__":
    unittest.main()
