"""POST /api/workflows/rename-impact — what a rename would do, without doing it.

The report has to be right about two things that are easy to get wrong:

* **Naming mode.** ``format_workflow_name`` produces ``AM_{CODE}_{name}.yml``
  for a prefix project and a bare ``{name}.yml`` otherwise, so the same rename
  describes different paths in the two modes. A no-prefix project also shares
  ``.github/workflows`` with files nobody here delivered, so a new name that
  already exists there is an overwrite waiting to happen — a warning that must
  *not* fire in prefix mode, where ``AM_{CODE}_`` namespaces per project.

* **What "delivered" means.** ``workflow_git_hash`` cannot answer it: it is
  zeroed by any local edit and set to a PR branch SHA by a campaign that has
  not landed. The report uses the tree listing plus
  ``WorkflowDriftState.confirmed_present_at``, which is stamped the first time
  a check actually saw the file and never cleared.

Cost matters — the report runs on every rename attempt — but not more than
being right. Presence is **revalidated** through ``_fetch_tree_using_cache``
rather than replayed from ``workflow_tree_cache``: nothing invalidates that row
when GitHub changes, so replaying it answers from whenever drift last ran, and a
file added since then is invisible. Revalidating costs a round trip and no rate
limit, because the request carries ``If-None-Match`` and a 304 is free. Branches
are likewise resolved live, not read back from ``workflow_drift_states``, so a
branch added since the last drift run is still checked.
"""
import json
import os
import sys
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from auth import user_tokens
from workflows import NotModified
from main import app
from models import (
    Account,
    LinkedReusableWorkflow,
    Project,
    ProjectPullRequest,
    ProjectRepo,
    ProjectWorkflow,
    Repo,
    Workflow,
    WorkflowDriftState,
    WorkflowTreeCache,
)
from tests.conftest import TestingSessionLocal

OWNER = "impact-owner"
REPO = "acme/api"
BRANCH = "main"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _token():
    user_tokens[OWNER] = "test-token"
    yield
    user_tokens.pop(OWNER, None)


def _make_project(db, *, use_prefix=True, code="ACME", project_type="standard"):
    owner = db.query(Account).filter(Account.github_user == OWNER).first()
    if not owner:
        owner = Account(github_user=OWNER, github_email=f"{OWNER}@example.com",
                        account_type="free")
        db.add(owner)
        db.commit()
        db.refresh(owner)

    project = Project(
        project_name=f"impact_{os.urandom(4).hex()}",
        project_code=code,
        user_id=owner.user_id,
        branch_option="default",
        project_type=project_type,
        use_prefix=use_prefix,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    repo = db.query(Repo).filter(Repo.repo_name == REPO).first()
    if not repo:
        repo = Repo(repo_name=REPO)
        db.add(repo)
        db.commit()
        db.refresh(repo)
    db.add(ProjectRepo(project_id=project.project_id, repo_id=repo.repo_id))
    db.commit()
    # Plain values, not ORM instances: these outlive the session the callers close.
    return SimpleNamespace(
        name=project.project_name, id=project.project_id,
        code=project.project_code, use_prefix=project.use_prefix,
    ), repo.repo_id


def _add_workflow(db, project, name, *, reusable=False, status="synced_with_github",
                  pending_delete=False):
    wf = Workflow(
        workflow_name=name,
        workflow_yaml="name: x\non: push",
        reusable_workflow=reusable,
        workflow_git_hash="0" * 40,
        workflow_status=status,
        pending_delete=pending_delete,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    db.add(ProjectWorkflow(project_id=project.id, workflow_id=wf.workflow_id))
    db.commit()
    return wf


def _cache_tree(db, repo_id, filenames, branch=BRANCH):
    """Seed a stale ``workflow_tree_cache`` row.

    Deliberately stale in some tests: the report must revalidate rather than
    trust this, so seeding it is how we prove a newer repo state still wins.
    """
    db.add(WorkflowTreeCache(
        repo_id=repo_id,
        branch=branch,
        etag='W/"seeded"',
        sha_map_json=json.dumps({name: "sha-%d" % i for i, name in enumerate(filenames)}),
    ))
    db.commit()


def _tree(*filenames):
    """What GitHub reports for a branch: {filename: blob_sha}."""
    return {name: "sha-%d" % i for i, name in enumerate(filenames)}


def _drift_state(db, project, workflow_id, repo_id, branch=BRANCH, confirmed_at=None):
    """Record a drift result for this (workflow, repo, branch).

    Only ``confirmed_present_at`` is consumed by the report — the branch list is
    resolved live, precisely so a branch added after the last drift run is not
    skipped.
    """
    db.add(WorkflowDriftState(
        project_id=project.id,
        workflow_id=workflow_id,
        repo_id=repo_id,
        branch=branch,
        has_drift=False,
        confirmed_present_at=confirmed_at,
    ))
    db.commit()


def _ask(project, workflow_name, new_name, *, files=(), branches=(BRANCH,),
         default_branch=BRANCH, is_reusable=None):
    """Call the endpoint with GitHub's answer pinned to ``files``.

    ``fetch_workflow_tree`` is the single boundary every listing goes through,
    so patching it here models the real repo contents rather than a cache we
    hope is fresh.
    """
    tree = _tree(*files)
    body = {
        "github_user": OWNER,
        "project_name": project.name,
        "workflow_name": workflow_name,
        "new_name": new_name,
    }
    if is_reusable is not None:
        body["is_reusable"] = is_reusable
    with patch("workflows._resolve_drift_branches_for_repo", return_value=list(branches)), \
         patch("workflows.get_default_branch", return_value=default_branch), \
         patch("workflows.fetch_workflow_tree",
               return_value=(tree, 'W/"live"')) as fetch:
        resp = client.post(
            "/api/workflows/rename-impact",
            json=body,
            headers={"X-GitHub-User": OWNER},
        )
    return resp, fetch


# --- the wire contract -----------------------------------------------------


def test_the_response_field_names_are_the_ones_the_dialog_reads():
    """The confirmation dialog indexes these by name; renaming one blanks the app.

    ``overrides`` was read as ``override_repos`` in
    ``frontend/src/api/workflows.ts``, so ``impact.override_repos.length`` ran
    against ``undefined`` and threw *during render* — which unmounts the whole
    React tree, not just the dialog. Nothing on either side asserted the wire
    names, so the TypeScript interface and the test fixtures typed from it
    agreed with each other and disagreed with this response.

    Asserted against a real response body rather than ``model_fields`` so it
    also covers whatever the route does to the model on the way out.
    """
    db = TestingSessionLocal()
    try:
        project, _ = _make_project(db, use_prefix=True, code="WIRE")
        _add_workflow(db, project, "ci")
    finally:
        db.close()

    resp, _ = _ask(project, "ci", "build", files=["AM_WIRE_ci.yml"])
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert set(body) == {
        "classification", "blocked_reason", "old_filename", "new_filename",
        "targets", "consumers", "overrides", "warnings",
    }
    assert set(body["targets"][0]) == {
        "repo", "branch", "old_file_present", "new_file_present",
        "confirmed_present_at",
    }


# --- naming modes ----------------------------------------------------------


def test_prefix_project_reports_prefixed_filenames():
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, use_prefix=True, code="ACME")
        _add_workflow(db, project, "ci")
    finally:
        db.close()

    resp, _ = _ask(project, "ci", "build", files=["AM_ACME_ci.yml"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["old_filename"] == "AM_ACME_ci.yml"
    assert body["new_filename"] == "AM_ACME_build.yml"
    assert body["classification"] == "delivered"


def test_no_prefix_project_reports_bare_filenames():
    """Same rename, different project mode, different paths."""
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, use_prefix=False, code="BARE")
        _add_workflow(db, project, "ci")
    finally:
        db.close()

    resp, _ = _ask(project, "ci", "build", files=["ci.yml"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["old_filename"] == "ci.yml"
    assert body["new_filename"] == "build.yml"
    assert body["classification"] == "delivered"


def test_no_prefix_collision_with_a_file_we_never_delivered_is_warned():
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, use_prefix=False, code="BARE")
        _add_workflow(db, project, "ci")
        # 'build.yml' is already in the repo and is not ours.
    finally:
        db.close()

    resp, _ = _ask(project, "ci", "build", files=["ci.yml", "build.yml"])
    body = resp.json()
    assert any("already exists" in w and "overwrite" in w for w in body["warnings"]), body["warnings"]


def test_prefix_mode_does_not_warn_about_collisions():
    """AM_{CODE}_ namespaces per project, so the overwrite case cannot arise."""
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, use_prefix=True, code="ACME")
        _add_workflow(db, project, "ci")
    finally:
        db.close()

    resp, _ = _ask(project, "ci", "build", files=["AM_ACME_ci.yml", "build.yml"])
    body = resp.json()
    assert not any("overwrite" in w for w in body["warnings"]), body["warnings"]


# --- classification --------------------------------------------------------


def test_undelivered_workflow_is_free_to_rename():
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="NEW1")
        _add_workflow(db, project, "ci", status="new")
    finally:
        db.close()

    resp, _ = _ask(project, "ci", "build", files=[])  # nothing in the repo
    body = resp.json()
    assert body["classification"] == "never_delivered"
    assert body["blocked_reason"] is None
    assert body["targets"][0]["old_file_present"] is False


def test_a_zeroed_hash_does_not_make_a_delivered_workflow_look_new():
    """The old-file listing decides, not workflow_git_hash."""
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="ZERO")
        wf = _add_workflow(db, project, "ci", status="committed_locally")
        assert wf.workflow_git_hash == "0" * 40  # a local edit zeroes it
    finally:
        db.close()

    resp, _ = _ask(project, "ci", "build", files=["AM_ZERO_ci.yml"])
    assert resp.json()["classification"] == "delivered"


def test_unreadable_repo_reports_unknown_not_absent():
    """A failed listing must never be read as 'the file is not there'."""
    db = TestingSessionLocal()
    try:
        project, _repo_id = _make_project(db, code="DOWN")
        _add_workflow(db, project, "ci")
        # no cache row seeded, so the endpoint has to ask GitHub
    finally:
        db.close()

    with patch("workflows._resolve_drift_branches_for_repo", return_value=[BRANCH]), \
         patch("workflows._fetch_tree_using_cache", side_effect=RuntimeError("502 from GitHub")):
        resp = client.post(
            "/api/workflows/rename-impact",
            json={"github_user": OWNER, "project_name": project.name,
                  "workflow_name": "ci", "new_name": "build"},
            headers={"X-GitHub-User": OWNER},
        )

    body = resp.json()
    assert body["targets"][0]["old_file_present"] is None
    assert body["targets"][0]["new_file_present"] is None
    assert any("Could not read" in w for w in body["warnings"])
    # Not "never_delivered": we did not look, so we cannot say nothing is there.
    # Reporting absence here is what would hand back a rename that should have
    # been refused.
    assert body["classification"] == "unknown"


# --- cost ------------------------------------------------------------------


def test_presence_is_revalidated_not_replayed_from_cache():
    """A stale cache row must not decide the answer.

    Nothing invalidates workflow_tree_cache when GitHub changes, so replaying it
    reports the repo as it was whenever drift last ran. Here the cache says the
    new name is free and GitHub says it is taken — the report must believe
    GitHub, or the user is told an overwrite is safe.
    """
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, use_prefix=False, code="STAL")
        _add_workflow(db, project, "ci")
        # Stale: recorded before anyone added build.yml.
        _cache_tree(db, repo_id, ["ci.yml"])
    finally:
        db.close()

    # GitHub now also has build.yml.
    body = _ask(project, "ci", "build", files=["ci.yml", "build.yml"])[0].json()
    assert body["targets"][0]["new_file_present"] is True, body["targets"]
    assert any("already exists" in w for w in body["warnings"]), body["warnings"]


def test_listing_is_conditional_so_an_unchanged_repo_costs_no_rate_limit():
    """Revalidation is cheap because it is conditional, not because it is skipped.

    _fetch_tree_using_cache sends If-None-Match from the stored ETag and replays
    the cached map on 304, which does not count against the rate limit. That is
    what makes always-revalidating affordable.
    """
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="COND")
        _add_workflow(db, project, "ci")
        _cache_tree(db, repo_id, ["AM_COND_ci.yml"])
    finally:
        db.close()

    with patch("workflows._resolve_drift_branches_for_repo", return_value=[BRANCH]), \
         patch("workflows.fetch_workflow_tree",
               side_effect=NotModified("unchanged")) as fetch:
        resp = client.post(
            "/api/workflows/rename-impact",
            json={"github_user": OWNER, "project_name": project.name,
                  "workflow_name": "ci", "new_name": "build"},
            headers={"X-GitHub-User": OWNER},
        )

    assert resp.status_code == 200, resp.text
    # The stored ETag was sent, which is what earns the free 304.
    assert fetch.call_args.kwargs.get("etag") == 'W/"seeded"'
    # And the cached map was replayed rather than treated as unknown.
    assert resp.json()["targets"][0]["old_file_present"] is True


def test_a_branch_added_since_the_last_drift_run_is_still_checked():
    """Branches are resolved live, not read back from workflow_drift_states.

    Reusing the recorded branches made a branch added after the last drift run
    invisible — the report would stay silent about a file the rename orphans
    there.
    """
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="NEWB")
        wf = _add_workflow(db, project, "ci")
        # Drift only ever saw main.
        _drift_state(db, project, wf.workflow_id, repo_id, branch="main")
    finally:
        db.close()

    # The project now also delivers to release/2.
    body = _ask(project, "ci", "build",
                files=["AM_NEWB_ci.yml"],
                branches=["main", "release/2"])[0].json()
    assert sorted(t["branch"] for t in body["targets"]) == ["main", "release/2"]


# --- blocked states --------------------------------------------------------


def test_under_review_workflow_is_blocked():
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="REVW")
        _add_workflow(db, project, "ci", status="under_review")
    finally:
        db.close()

    body = _ask(project, "ci", "build", files=["AM_REVW_ci.yml"])[0].json()
    assert body["classification"] == "blocked"
    assert "under review" in body["blocked_reason"]


def test_open_pr_naming_the_workflow_blocks_the_rename():
    """The PR row's workflow_names snapshot is the lookup key a rename breaks."""
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="OPEN")
        _add_workflow(db, project, "ci")
        db.add(ProjectPullRequest(
            project_id=project.id, repo_name=REPO, pr_number=7,
            pr_url="https://github.com/acme/api/pull/7", pr_state="open",
            branch_name="actions-manager/open", target_branch=BRANCH,
            workflow_names="ci",
        ))
        db.commit()
    finally:
        db.close()

    body = _ask(project, "ci", "build", files=["AM_OPEN_ci.yml"])[0].json()
    assert body["classification"] == "blocked"
    assert "open pull request" in body["blocked_reason"]


def test_name_collision_inside_the_project_blocks_the_rename():
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="CLSH")
        _add_workflow(db, project, "ci")
        _add_workflow(db, project, "build")
    finally:
        db.close()

    body = _ask(project, "ci", "build", files=["AM_CLSH_ci.yml"])[0].json()
    assert body["classification"] == "blocked"
    assert "already has a workflow named" in body["blocked_reason"]


def test_delivered_reusable_with_consumers_is_blocked_and_lists_them():
    db = TestingSessionLocal()
    try:
        rwx, repo_id = _make_project(db, code="RWX1", project_type="rwx")
        wf = _add_workflow(db, rwx, "shared", reusable=True)
        caller, _ = _make_project(db, code="CALL")
        db.add(LinkedReusableWorkflow(
            standard_project_id=caller.id,
            rwx_project_id=rwx.id,
            workflow_id=wf.workflow_id,
        ))
        db.commit()
        caller_name = caller.name
        # Two caller workflows really reference it, and one does not. The count
        # must be per referencing workflow, not per linking project.
        uses = f"uses: {REPO}/.github/workflows/AM_RWX1_shared.yml@main"
        for name in ("deploy", "release"):
            ref = _add_workflow(db, caller, name)
            ref.workflow_yaml = f"name: {name}\non: push\njobs:\n  j:\n    {uses}"
            db.commit()
        _add_workflow(db, caller, "unrelated")
    finally:
        db.close()

    body = _ask(rwx, "shared", "shared-v2", files=["AM_RWX1_shared.yml"])[0].json()
    assert body["classification"] == "blocked"
    assert "uses:" in body["blocked_reason"]
    # Two referencing workflows, not one linking project — and named for the
    # caller workflow the user actually has to edit.
    assert len(body["consumers"]) == 2, body["consumers"]
    assert {c["workflow_name"] for c in body["consumers"]} == {"deploy", "release"}
    assert all(c["project_name"] == caller_name for c in body["consumers"])
    # The uses: line is rendered from the OWNING project's naming mode and repo.
    assert "AM_RWX1_shared.yml" in body["consumers"][0]["uses_line"]
    assert "2 caller workflow(s)" in body["blocked_reason"]


def test_undelivered_reusable_with_consumers_is_not_blocked():
    """Nothing on GitHub references it yet, so there is no broken uses: to cause."""
    db = TestingSessionLocal()
    try:
        rwx, repo_id = _make_project(db, code="RWX2", project_type="rwx")
        wf = _add_workflow(db, rwx, "shared", reusable=True, status="new")
        caller, _ = _make_project(db, code="CAL2")
        db.add(LinkedReusableWorkflow(
            standard_project_id=caller.id,
            rwx_project_id=rwx.id,
            workflow_id=wf.workflow_id,
        ))
        db.commit()
    finally:
        db.close()

    body = _ask(rwx, "shared", "shared-v2", files=[])[0].json()
    assert body["classification"] == "never_delivered"
    assert body["blocked_reason"] is None


def test_outage_does_not_release_the_reusable_consumer_block():
    """The failure this whole three-state design exists to prevent.

    A delivered reusable workflow with linked callers must stay blocked when
    GitHub cannot be reached. Folding unknown into "not delivered" turned an
    outage into an approved rename that 404s every consumer's `uses:` line.
    """
    db = TestingSessionLocal()
    try:
        rwx, repo_id = _make_project(db, code="RWX3", project_type="rwx")
        wf = _add_workflow(db, rwx, "shared", reusable=True)
        # No tree cache and no drift history: presence is genuinely unknown.
        caller, _ = _make_project(db, code="CAL3")
        db.add(LinkedReusableWorkflow(
            standard_project_id=caller.id,
            rwx_project_id=rwx.id,
            workflow_id=wf.workflow_id,
        ))
        db.commit()
        consumer = _add_workflow(db, caller, "deploy")
        consumer.workflow_yaml = (
            f"jobs:\n  j:\n    uses: {REPO}/.github/workflows/AM_RWX3_shared.yml@main"
        )
        db.commit()
    finally:
        db.close()

    with patch("workflows._resolve_drift_branches_for_repo", return_value=[BRANCH]), \
         patch("workflows.get_default_branch", return_value=BRANCH), \
         patch("workflows._fetch_tree_using_cache", side_effect=RuntimeError("502")):
        resp = client.post(
            "/api/workflows/rename-impact",
            json={"github_user": OWNER, "project_name": rwx.name,
                  "workflow_name": "shared", "new_name": "shared-v2"},
            headers={"X-GitHub-User": OWNER},
        )

    body = resp.json()
    assert body["classification"] == "blocked", body
    assert "uses:" in body["blocked_reason"]


def test_unresolvable_repo_is_unknown_not_absent():
    """A repo that yields no rows at all must not read as 'nothing is there'.

    Branch resolution failing used to return [] for that repository, so it
    vanished from the report entirely and the classifier saw an empty target
    list as 'never delivered'.
    """
    db = TestingSessionLocal()
    try:
        project, _repo_id = _make_project(db, code="NOBR")
        _add_workflow(db, project, "ci")
    finally:
        db.close()

    with patch("workflows._resolve_drift_branches_for_repo",
               side_effect=RuntimeError("branch listing failed")):
        resp = client.post(
            "/api/workflows/rename-impact",
            json={"github_user": OWNER, "project_name": project.name,
                  "workflow_name": "ci", "new_name": "build"},
            headers={"X-GitHub-User": OWNER},
        )

    body = resp.json()
    assert body["targets"] == []
    assert body["classification"] == "unknown", body
    assert any("Could not resolve branches" in w for w in body["warnings"])


def test_corrupt_tree_cache_is_unknown_not_a_500():
    """A truncated cache row replayed on a 304 is another unknown, not a crash."""
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="CORR")
        _add_workflow(db, project, "ci")
        db.add(WorkflowTreeCache(repo_id=repo_id, branch=BRANCH,
                                 etag='W/"x"', sha_map_json="{not json"))
        db.commit()
    finally:
        db.close()

    with patch("workflows._resolve_drift_branches_for_repo", return_value=[BRANCH]), \
         patch("workflows.fetch_workflow_tree", side_effect=NotModified("unchanged")):
        resp = client.post(
            "/api/workflows/rename-impact",
            json={"github_user": OWNER, "project_name": project.name,
                  "workflow_name": "ci", "new_name": "build"},
            headers={"X-GitHub-User": OWNER},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["targets"][0]["old_file_present"] is None
    assert body["classification"] == "unknown"


def test_rwx_project_with_no_repo_row_still_blocks_its_consumers():
    """The path that made the consumer refusal silently stop firing.

    Reusable workflows are delivered to _get_reusable_workflow_repo, not the
    project's ProjectRepo rows. Scanning ProjectRepo produced zero targets for
    an RWX project with no such row, and zero targets read as "not delivered",
    so a delivered reusable workflow with linked callers came back free to
    rename.
    """
    db = TestingSessionLocal()
    try:
        # Create the caller first so the OWNER account exists.
        caller, _ = _make_project(db, code="CAL4")
        owner = db.query(Account).filter(Account.github_user == OWNER).first()
        rwx = Project(project_name=f"norepo_{os.urandom(4).hex()}", project_code="NORP",
                      user_id=owner.user_id, branch_option="default",
                      project_type="rwx", use_prefix=True)
        db.add(rwx)
        db.commit()
        db.refresh(rwx)
        rwx_ns = SimpleNamespace(name=rwx.project_name, id=rwx.project_id,
                                 code=rwx.project_code, use_prefix=True)
        # Deliberately NO ProjectRepo row for this project.
        wf = _add_workflow(db, rwx_ns, "shared", reusable=True)

        db.add(LinkedReusableWorkflow(standard_project_id=caller.id,
                                      rwx_project_id=rwx_ns.id,
                                      workflow_id=wf.workflow_id))
        db.commit()
        consumer = _add_workflow(db, caller, "deploy")
        consumer.workflow_yaml = (
            "jobs:\n  j:\n    uses: "
            f"{OWNER}/am-reuseable-workflow/.github/workflows/AM_NORP_shared.yml@main"
        )
        db.commit()
    finally:
        db.close()

    # The fallback repo is what delivery would use, and the file is there.
    body = _ask(rwx_ns, "shared", "shared-v2",
                files=["AM_NORP_shared.yml"])[0].json()
    assert body["targets"], "the reusable repo was never scanned"
    assert body["classification"] == "blocked", body
    assert "uses:" in body["blocked_reason"]


def test_prefixed_old_name_resolves_instead_of_404():
    """The preview must accept the same input the write path accepts.

    create_or_update_workflow strips AM_{CODE}_ from original_name, so the
    displayed name renames fine; stripping only new_name made the preview 404 on
    exactly that input.
    """
    db = TestingSessionLocal()
    try:
        project, _repo_id = _make_project(db, code="PFX1")
        _add_workflow(db, project, "ci")
    finally:
        db.close()

    resp, _ = _ask(project, "AM_PFX1_ci", "build", files=["AM_PFX1_ci.yml"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["old_filename"] == "AM_PFX1_ci.yml"


# --- misc ------------------------------------------------------------------


def test_case_only_rename_is_blocked_because_it_cannot_be_performed():
    """create_or_update_workflow compares names case-insensitively.

    `original_name.lower() != new_name.lower()` is False for Build -> build, so
    it is not treated as a rename and the stored name never changes. Warning
    about the consequences of a rename that silently no-ops would be worse than
    saying no.
    """
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="CASE")
        _add_workflow(db, project, "Build")
    finally:
        db.close()

    body = _ask(project, "Build", "build", files=["AM_CASE_Build.yml"])[0].json()
    assert body["classification"] == "blocked"
    assert "capitalisation" in body["blocked_reason"]
    assert not any("capitalisation" in w for w in body["warnings"]), body["warnings"]


def test_unknown_workflow_is_404():
    db = TestingSessionLocal()
    try:
        project, _repo_id = _make_project(db, code="MISS")
    finally:
        db.close()

    resp, _ = _ask(project, "nope", "build")
    assert resp.status_code == 404


def test_report_writes_nothing():
    """It is a preview: the workflow must be untouched afterwards."""
    db = TestingSessionLocal()
    try:
        project, repo_id = _make_project(db, code="PURE")
        wf = _add_workflow(db, project, "ci")
        wf_id = wf.workflow_id
    finally:
        db.close()

    _ask(project, "ci", "build", files=["AM_PURE_ci.yml"])

    db = TestingSessionLocal()
    try:
        after = db.query(Workflow).filter_by(workflow_id=wf_id).first()
        assert after.workflow_name == "ci"
        assert after.workflow_status == "synced_with_github"
        assert after.pending_delete is False
    finally:
        db.close()


def test_rename_onto_a_tombstone_name_is_reported_as_blocked():
    """The report must refuse what the write path refuses.

    _rename_blocker_name_collision used to exclude pending_delete rows, so a
    rename onto a name a tombstone still owns came back with blocked_reason
    None — telling the user it was safe, while create_or_update_workflow
    answers the same request with a 409.
    """
    db = TestingSessionLocal()
    try:
        proj, _ = _make_project(db, code="TOMB")
        _add_workflow(db, proj, "ci", pending_delete=True)
        _add_workflow(db, proj, "other")
    finally:
        db.close()

    body = _ask(proj, "other", "ci", files=[])[0].json()
    assert body["classification"] == "blocked", body
    assert "queued for removal" in body["blocked_reason"]


def test_collision_check_is_scoped_to_the_same_kind():
    """A regular and a reusable workflow may share a name; renaming into that is legal.

    create_or_update_workflow scopes every name lookup by reusable_workflow, so
    an unscoped clash query refused a rename the write path performs without
    complaint — with a reason the user cannot act on.
    """
    db = TestingSessionLocal()
    try:
        proj, _ = _make_project(db, code="KIND")
        _add_workflow(db, proj, "deploy", reusable=True)
        _add_workflow(db, proj, "build")
    finally:
        db.close()

    body = _ask(proj, "build", "deploy", files=[], is_reusable=False)[0].json()
    assert body["blocked_reason"] is None, body
    assert body["classification"] != "blocked"


def test_is_reusable_selects_which_workflow_the_preview_answers_about():
    """With both kinds under one name, .first() must not decide which one.

    The two are delivered to different repositories and have different
    consumers, so answering about the wrong one is not a near miss. Given
    different statuses here, the blocker is the observable proof of which row
    was resolved.
    """
    db = TestingSessionLocal()
    try:
        proj, _ = _make_project(db, code="BOTH")
        _add_workflow(db, proj, "deploy", reusable=True, status="under_review")
        _add_workflow(db, proj, "deploy", status="synced_with_github")
    finally:
        db.close()

    reusable = _ask(proj, "deploy", "deploy-v2", files=[], is_reusable=True)[0].json()
    assert reusable["classification"] == "blocked"
    assert "under review" in reusable["blocked_reason"]

    regular = _ask(proj, "deploy", "deploy-v2", files=[], is_reusable=False)[0].json()
    assert regular["blocked_reason"] is None, regular

    # Omitted, the regular workflow wins deterministically rather than whichever
    # row the database happened to return first.
    unscoped = _ask(proj, "deploy", "deploy-v2", files=[])[0].json()
    assert unscoped["blocked_reason"] is None, unscoped


def test_save_workflows_declares_the_409_it_can_raise():
    """projects.py:57 makes this a rule: codes raised in shared helpers count.

    _assert_name_not_held_by_tombstone raises 409 through /api/save-workflows,
    so generated clients and the API docs have to know the status exists.
    """
    schema = client.get("/openapi.json").json()
    assert "409" in schema["paths"]["/api/save-workflows"]["post"]["responses"]
    assert "409" in schema["paths"]["/api/projects/"]["post"]["responses"]
    assert "409" in schema["paths"]["/api/projects/{project_id}/"]["put"]["responses"]


def test_confirmed_present_at_carries_an_explicit_utc_offset():
    """A naive stamp serialized bare reads as local time in the browser.

    Same defect #2040 fixed on the drift surfaces: the column stores naive UTC,
    so `.isoformat()` emits no designator and `new Date()` applies the viewer's
    zone, moving a delivery confirmation by hours. Routed through the shared
    ``_utc_iso`` so this report and the drift panel cannot disagree on format.
    """
    db = TestingSessionLocal()
    try:
        proj, repo_id = _make_project(db, code="UTC1")
        wf = _add_workflow(db, proj, "ci")
        _drift_state(db, proj, wf.workflow_id, repo_id,
                     confirmed_at=datetime(2026, 9, 16, 11, 30, 0))
    finally:
        db.close()

    body = _ask(proj, "ci", "ci-v2", files=["AM_UTC1_ci.yml"])[0].json()
    stamps = [t["confirmed_present_at"] for t in body["targets"]]
    assert stamps == ["2026-09-16T11:30:00+00:00"], stamps
