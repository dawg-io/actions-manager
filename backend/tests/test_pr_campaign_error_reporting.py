"""
Regression tests for what a PR Campaign tells the user when a target fails.

A campaign whose only change was a custom file marked for deletion reported
``Successfully created 0 pull request(s)`` plus a bare red "Error" per repo. The
cause was three layers of discarded information:

  1. ``_delete_custom_file_from_branch`` treated "the file was already absent"
     as a commit, so the AM branch was byte-identical to its base.
  2. ``_create_pull_request`` dropped GitHub's 422 ("No commits between ...")
     and returned ``None``.
  3. ``_build_pr_error_result`` replaced whatever happened with the constant
     ``"Failed to create PR"``.

Nothing here calls GitHub; every request is mocked.
"""
import sys
import os
from unittest.mock import MagicMock, patch

from requests.models import PreparedRequest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workflows import (  # noqa: E402
    DELETE_ABSENT,
    DELETE_DELETED,
    DELETE_FAILED,
    NO_WORKFLOWS_COMMITTED,
    _build_pr_error_result,
    _commit_custom_files_to_branch,
    _create_pull_request,
    _delete_custom_file_from_branch,
    _describe_empty_delivery,
    _finalize_pr_result,
    _process_regular_workflows_update,
    _github_reason,
)


def _resp(status_code, payload=None, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    if payload is None:
        r.json.side_effect = ValueError("no json")
    else:
        r.json.return_value = payload
    return r


class TestGithubReason:
    def test_joins_message_and_nested_errors(self):
        resp = _resp(422, {
            "message": "Validation Failed",
            "errors": [{"message": "No commits between main and actions-manager/x"}],
        })
        reason = _github_reason(resp)
        assert "Validation Failed" in reason
        assert "No commits between main and actions-manager/x" in reason

    def test_falls_back_to_body_when_the_response_is_not_json(self):
        assert _github_reason(_resp(500, None, text="upstream exploded")) == "upstream exploded"

    def test_survives_a_json_body_that_is_not_an_object(self):
        assert _github_reason(_resp(500, ["nope"], text="raw")) == "raw"


class TestCreatePullRequestReason:
    def test_reports_githubs_own_explanation_on_failure(self):
        failure = _resp(422, {
            "message": "Validation Failed",
            "errors": [{"message": "No commits between main and actions-manager/cmp-main"}],
        })
        with patch("workflows.requests.post", return_value=failure):
            pr, reason = _create_pull_request(
                "o", "r", "actions-manager/cmp-main", "main", "CMP", [], {"Accept": "x"}
            )
        assert pr is None
        assert "422" in reason
        assert "No commits between main and actions-manager/cmp-main" in reason

    def test_returns_no_reason_on_success(self):
        ok = _resp(201, {"number": 7, "html_url": "https://github.com/o/r/pull/7"})
        with patch("workflows.requests.post", return_value=ok):
            pr, reason = _create_pull_request(
                "o", "r", "actions-manager/cmp-main", "main", "CMP", [], {"Accept": "x"}
            )
        assert reason is None
        assert pr["number"] == 7


class TestDeleteOutcome:
    """"Already absent" is a success for intent but produces no commit."""

    def test_absent_file_is_reported_as_absent_not_deleted(self):
        with patch("workflows.github_get", return_value=_resp(404, {})):
            outcome, error = _delete_custom_file_from_branch(
                "o", "r", "scripts/x.sh", "actions-manager/cmp-main", "CMP", "u", None, {}
            )
        assert outcome == DELETE_ABSENT
        assert error is None

    def test_present_file_is_deleted(self):
        with patch("workflows.github_get", return_value=_resp(200, {"sha": "abc"})), \
             patch("workflows.requests.delete", return_value=_resp(200, {})):
            outcome, error = _delete_custom_file_from_branch(
                "o", "r", "scripts/x.sh", "actions-manager/cmp-main", "CMP", "u", None, {}
            )
        assert outcome == DELETE_DELETED
        assert error is None

    def test_a_rejected_delete_carries_githubs_reason(self):
        rejected = _resp(409, {"message": "x.sh does not match abc"})
        with patch("workflows.github_get", return_value=_resp(200, {"sha": "abc"})), \
             patch("workflows.requests.delete", return_value=rejected):
            outcome, error = _delete_custom_file_from_branch(
                "o", "r", "scripts/x.sh", "actions-manager/cmp-main", "CMP", "u", None, {}
            )
        assert outcome == DELETE_FAILED
        assert "409" in error
        assert "does not match" in error


class TestAbsentFileIsNotACommit:
    def test_an_absent_pending_delete_counts_as_neither_commit_nor_error(self):
        """This is what made the campaign open a PR against an unchanged branch."""
        files = [{"id": 1, "file_path": "scripts/x.sh", "file_content": "", "pending_delete": True}]
        with patch("workflows.github_get", return_value=_resp(404, {})):
            committed, errors = _commit_custom_files_to_branch(
                files, "o", "r", "actions-manager/cmp-main", "CMP", "u", None, {}
            )
        assert committed == []
        assert errors == []

    def test_a_real_deletion_still_counts_as_a_commit(self):
        files = [{"id": 1, "file_path": "scripts/x.sh", "file_content": "", "pending_delete": True}]
        with patch("workflows.github_get", return_value=_resp(200, {"sha": "abc"})), \
             patch("workflows.requests.delete", return_value=_resp(200, {})):
            committed, errors = _commit_custom_files_to_branch(
                files, "o", "r", "actions-manager/cmp-main", "CMP", "u", None, {}
            )
        assert committed == ["scripts/x.sh"]
        assert errors == []


class TestEmptyDeliveryMessage:
    def test_says_nothing_to_deliver_when_no_step_actually_failed(self):
        message = _describe_empty_delivery([], [])
        assert "Nothing to deliver" in message
        assert NO_WORKFLOWS_COMMITTED not in message

    def test_lists_the_failures_when_there_were_any(self):
        message = _describe_empty_delivery(["ci: HTTP 403"], ["x.sh: HTTP 409"])
        assert "ci: HTTP 403" in message
        assert "x.sh: HTTP 409" in message


class TestErrorResultCarriesTheReason:
    def test_reason_is_appended_to_the_status_message(self):
        result = _build_pr_error_result([], [], None, "am", "main", None, "k", "HTTP 422: No commits between")
        assert result["status"] == "error"
        assert "No commits between" in result["error"]

    def test_falls_back_to_the_constant_when_nothing_explained_it(self):
        result = _build_pr_error_result([], [], None, "am", "main", None, "k", None)
        assert result["error"] == "Failed to create PR"

    def test_progress_callback_receives_the_same_detail(self):
        seen = []
        _build_pr_error_result(
            [], [], None, "am", "main",
            lambda key, step, status, msg=None: seen.append(msg),
            "k", "HTTP 422: No commits between",
        )
        assert any("No commits between" in (m or "") for m in seen)

    def test_finalize_surfaces_the_creation_failure(self):
        with patch("workflows._check_existing_pr", return_value=None), \
             patch("workflows._create_pull_request", return_value=(None, "HTTP 422: No commits between")), \
             patch("workflows._campaign_pr_body", return_value="body"):
            result = _finalize_pr_result(
                "o", "r", "actions-manager/cmp-main", "main", {}, "u", None, "CMP", None, "k",
                delivery={"workflows_committed": ["ci"]},
            )
        assert result["status"] == "error"
        assert "No commits between" in result["error"]


class TestRequestConstruction:
    """These call through the real ``github_get`` instead of patching it.

    Every other test here patches ``workflows.github_get``, which cannot see a
    malformed headers dict — that only fails when requests prepares the request.
    A ``params`` dict was being merged into the headers, so every custom-file
    delete died with "Header part ({'ref': ...}) must be of type str or bytes,
    not <class 'dict'>" while ``params`` was already being passed correctly on
    its own. The campaign swallowed it into a per-file error and reported the
    target as a bare "Error".
    """

    def _call(self, response, headers=None):
        captured = {}

        def fake_request(method, url, **kwargs):
            # requests' own validator: this is what raised on the merged dict.
            PreparedRequest().prepare_headers(kwargs.get("headers"))
            captured.update(kwargs)
            captured["url"] = url
            return response

        with patch("github_api_tracker.requests.request", side_effect=fake_request), \
             patch("github_api_tracker.track_github_api_call"), \
             patch("rate_limiter.check_rate_limit", return_value=(True, {})):
            outcome, error = _delete_custom_file_from_branch(
                "acme", "app", ".github/test.txt",
                "actions-manager/nop1/test1/fa71c483-main",
                "NOP1", "u", None,
                headers if headers is not None else {"Accept": "application/vnd.github+json"},
            )
        return outcome, error, captured

    def test_the_branch_goes_in_the_query_string_not_the_headers(self):
        outcome, error, captured = self._call(_resp(404, {}))

        assert outcome == DELETE_ABSENT
        assert error is None
        assert captured["params"] == {"ref": "actions-manager/nop1/test1/fa71c483-main"}
        # The regression itself: a dict here is not a header value.
        assert "params" not in captured["headers"]
        assert all(isinstance(v, (str, bytes)) for v in captured["headers"].values())

    def test_the_callers_headers_survive_untouched(self):
        _, _, captured = self._call(_resp(404, {}), headers={"Authorization": "token x"})

        assert captured["headers"]["Authorization"] == "token x"

    def test_a_present_file_is_deleted_through_the_real_request_path(self):
        found = _resp(200, {"sha": "abc"})
        with patch("workflows.requests.delete", return_value=_resp(200, {})) as gh_delete:
            outcome, error, captured = self._call(found)

        assert outcome == DELETE_DELETED
        assert error is None
        assert ".github/test.txt" in captured["url"]
        assert gh_delete.call_args.kwargs["json"]["sha"] == "abc"


class TestEmptyBranchCleanup:
    """A target that received nothing gets its AM branch dropped — but only the
    branch this run created.

    _create_or_get_am_branch returns (name, False, None) when GitHub answers 422
    "Reference already exists". That branch is not ours to delete: it may carry an
    open PR whose work removing the ref would close.
    """

    def _run(self, branch_created):
        with patch("workflows._resolve_branches_for_repo", return_value=["main"]), \
             patch("workflows._create_or_get_am_branch",
                   return_value=("actions-manager/cmp/repo-a/ab12-main", branch_created, None)), \
             patch("workflows._fetch_branch_protection", return_value={"status": "none"}), \
             patch("workflows.github_get", return_value=_resp(404, {})), \
             patch("workflows._delete_actions_manager_branch", return_value=(True, None)) as drop:
            results = _process_regular_workflows_update(
                repo_names=["acme/repo-a"],
                workflows=[],
                project_code="CMP",
                branch_option="default",
                regex_pattern="",
                branch_max_age_days=30,
                headers={},
                db=None,
                user="u",
                custom_files=[{"id": 1, "file_path": "x.sh",
                               "file_content": "", "pending_delete": True}],
            )
        return results, drop

    def test_a_branch_this_run_created_is_dropped(self):
        results, drop = self._run(branch_created=True)

        assert results["acme/repo-a on main"]["status"] == "error"
        assert "Nothing to deliver" in results["acme/repo-a on main"]["error"]
        drop.assert_called_once_with(
            "acme", "repo-a", "actions-manager/cmp/repo-a/ab12-main", "main", "u"
        )

    def test_a_pre_existing_branch_is_left_alone(self):
        results, drop = self._run(branch_created=False)

        assert results["acme/repo-a on main"]["status"] == "error"
        # Deleting it could close an open PR that has unmerged work on it.
        drop.assert_not_called()
