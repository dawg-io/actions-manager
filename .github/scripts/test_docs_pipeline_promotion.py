"""
Regression tests for the public documentation publishing pipeline (#2081).

The documentation site for the public repository is built by a workflow that
never runs here: .github/public-workflows/docs-pages.yml is staged outside
.github/workflows/ and installed into the sanitized export by
promote-to-public.yml. Nothing in CI executes it before a release does, so these
tests assert its contract - and the promotion steps that place it - from the
YAML itself.

They also pin the Issue A split: docs/ is published wholesale, so anything that
must stay private belongs in internal-docs/, which the export deletes.
"""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent.absolute()
PUBLIC_WORKFLOW = REPO_ROOT / ".github" / "public-workflows" / "docs-pages.yml"
PROMOTE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "promote-to-public.yml"

PREVIEW_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docs-preview.yml"

# The release process refers to workflows by name.
PUBLIC_WORKFLOW_NAME = "Publish Public Documentation Site"
PREVIEW_WORKFLOW_NAME = "Deploy Docs Preview"

# Moved out of docs/ by Issue A. docs/ is public in full, so these must not
# reappear there.
INTERNAL_DOCS = [
    "pipeline",
    "CLOUD_DEPLOYMENT.md",
    "LICENSE_KEYS.md",
    "DOCUMENTATION_CLEANUP_SUMMARY.md",
]


def load(path):
    with open(path) as handle:
        return yaml.safe_load(handle)


def promote_step(name):
    """The run: body of a named step in the promotion job."""
    steps = load(PROMOTE_WORKFLOW)["jobs"]["promote"]["steps"]
    for step in steps:
        if step.get("name") == name:
            return step.get("run", "")
    pytest.fail(f"promote-to-public.yml has no step named {name!r}")


@pytest.fixture(scope="module")
def public_workflow():
    return load(PUBLIC_WORKFLOW)


@pytest.fixture(scope="module")
def build_job(public_workflow):
    return public_workflow["jobs"]["build"]


class TestInternalDocsSplit:
    """docs/ is published in full, so internal material lives elsewhere."""

    @pytest.mark.parametrize("name", INTERNAL_DOCS)
    def test_internal_doc_is_not_under_docs(self, name):
        assert not (REPO_ROOT / "docs" / name).exists(), (
            f"docs/{name} is published verbatim to the public site. "
            f"Internal documentation belongs in internal-docs/."
        )

    @pytest.mark.parametrize("name", INTERNAL_DOCS)
    def test_internal_doc_is_under_internal_docs(self, name):
        assert (REPO_ROOT / "internal-docs" / name).exists()

    def test_internal_docs_directory_is_documented(self):
        readme = REPO_ROOT / "internal-docs" / "README.md"
        assert readme.exists(), "internal-docs/ needs a README explaining the split"

    def test_internal_docs_summary_is_tracked(self):
        """.gitignore ignores **/*_SUMMARY.md - the negation must follow the move."""
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "-v",
             "internal-docs/DOCUMENTATION_CLEANUP_SUMMARY.md"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        # check-ignore reports the last matching pattern; a leading "!" is the
        # negation that keeps the file tracked.
        assert "!internal-docs/DOCUMENTATION_CLEANUP_SUMMARY.md" in result.stdout, (
            "the .gitignore negation still points at docs/ - the moved file is "
            f"silently ignored. check-ignore said: {result.stdout.strip()!r}"
        )

    def test_no_jekyll_build_files_remain(self):
        """The Starlight cutover (#2077) retired Jekyll: no Ruby in the docs build."""
        for name in ("Gemfile", "Gemfile.lock", "_config.yml", "_includes", "_sass"):
            assert not (REPO_ROOT / "docs" / name).exists(), f"docs/{name} is a dead Jekyll file"
        for workflow in (PUBLIC_WORKFLOW, PREVIEW_WORKFLOW):
            text = workflow.read_text()
            assert "setup-ruby" not in text and "jekyll" not in text.lower(), workflow.name


class TestPromotionCarriesDocs:
    """What the sanitized export keeps, drops, and installs."""

    def test_export_drops_internal_docs_wholesale(self):
        run = promote_step("Remove private/internal files")
        assert "rm -rf internal-docs/" in run

    @pytest.mark.parametrize("name", INTERNAL_DOCS)
    def test_export_has_no_per_file_docs_exclusions(self, name):
        """docs/ carries in full - internal-docs/ is the only exclusion."""
        run = promote_step("Remove private/internal files")
        assert f"docs/{name}" not in run, (
            f"docs/{name} is excluded per-file; it should be covered by "
            f"internal-docs/ instead"
        )

    def test_export_strips_the_custom_domain(self):
        """A CNAME in the public tree would claim the production domain."""
        run = promote_step("Remove private/internal files")
        assert "rm -f docs/CNAME" in run

    def test_no_committed_cname(self):
        """The domain is set in the public repository's Pages settings."""
        assert not (REPO_ROOT / "docs" / "CNAME").exists()

    def test_old_production_deploy_is_gone(self):
        """The public repository serves actionsmanager.io now."""
        assert not (REPO_ROOT / ".github" / "workflows" / "pages.yml").exists()

    def test_export_installs_the_public_workflow(self):
        run = promote_step("Install public repository workflows")
        assert "mv .github/public-workflows/*.yml .github/workflows/" in run
        assert "rm -rf .github/public-workflows" in run, (
            "the staging directory must not survive into the public repository"
        )

    def test_public_workflow_is_staged_outside_the_live_directory(self):
        """Staged here it never runs in this repo, where it would publish a
        second Pages site from the same docs."""
        assert PUBLIC_WORKFLOW.exists()
        assert not (REPO_ROOT / ".github" / "workflows" / "docs-pages.yml").exists()


class TestPublicDocsWorkflow:
    """The contract of the workflow that runs in the public repository."""

    def test_name_is_what_the_release_process_expects(self, public_workflow):
        assert public_workflow["name"] == PUBLIC_WORKFLOW_NAME

    def test_all_three_triggers_are_present(self, public_workflow):
        # PyYAML reads a bare `on:` key as the boolean True.
        triggers = public_workflow.get("on", public_workflow.get(True))
        assert triggers["release"]["types"] == ["published"]
        assert "workflow_dispatch" in triggers
        assert triggers["push"]["branches"] == ["main"]
        assert "docs/**" in triggers["push"]["paths"], (
            "a docs-only fix must ship without waiting for a release"
        )

    def test_permissions_are_least_privilege(self, public_workflow):
        permissions = public_workflow["permissions"]
        assert permissions["pages"] == "write"
        assert permissions["id-token"] == "write"
        assert permissions.get("contents") == "read", (
            "the deploy needs to read the tree, never to write it"
        )

    def test_a_release_deploy_is_never_cancelled(self, public_workflow):
        concurrency = public_workflow["concurrency"]
        assert concurrency["cancel-in-progress"] is False

    def test_release_builds_the_tag_not_main(self, build_job):
        """promote-to-public.yml publishes the release without waiting for the
        promotion PR to merge, so main can still be the previous release."""
        checkout = next(
            s for s in build_job["steps"] if s.get("uses", "").startswith("actions/checkout")
        )
        ref = checkout["with"]["ref"]
        assert "github.event_name == 'release'" in ref
        assert "github.event.release.tag_name" in ref

    def test_runs_on_a_github_hosted_runner(self, public_workflow):
        """The public repository has none of this repository's self-hosted runners."""
        for job in public_workflow["jobs"].values():
            assert job["runs-on"] == "ubuntu-latest"

    def test_base_path_is_resolved_at_build_time(self, build_job):
        """Not a committed constant: moving to a domain must not need an edit
        here or in docs/astro.config.mjs."""
        steps = {s.get("name"): s for s in build_job["steps"]}
        assert steps["Setup GitHub Pages"]["uses"].startswith("actions/configure-pages")
        env = steps["Build with Astro"]["env"]
        assert env["PAGES_BASE_PATH"] == "${{ steps.pages.outputs.base_path }}"
        assert env["PAGES_BASE_URL"] == "${{ steps.pages.outputs.base_url }}"
        assert "BASE_URL" not in env, "Vite reads BASE_URL as the site base"

    def test_absolute_urls_are_overridden_too(self, build_job):
        """astro.config.mjs defaults to the production domain at the root; left
        alone on a project site the sitemap and canonicals resolve nowhere."""
        run = next(
            s for s in build_job["steps"] if s.get("name") == "Build with Astro"
        )["run"]
        assert "DOCS_SITE=" in run and "DOCS_BASE=" in run
        config = (REPO_ROOT / "docs" / "astro.config.mjs").read_text()
        assert "process.env.DOCS_SITE" in config and "process.env.DOCS_BASE" in config

    def test_builds_with_the_pinned_node_and_lockfile(self, build_job):
        steps = {s.get("name"): s for s in build_job["steps"]}
        node = steps["Setup Node.js"]["with"]
        assert node["node-version-file"] == "docs/.nvmrc"
        assert node["cache-dependency-path"] == "docs/package-lock.json"
        assert steps["Install dependencies"]["run"] == "npm ci"

    def test_build_failure_is_not_published(self, build_job):
        run = next(
            s for s in build_job["steps"] if s.get("name") == "Verify generated site"
        )["run"]
        assert "test -s dist/index.html" in run
        assert "dist/pagefind" in run, "search is part of the site's contract"
        assert "url-parity.txt" in run, "a published URL must never silently 404"

    def test_does_not_name_the_private_repository(self):
        """The export rewrites dawg-io -> dawg-io in every text file, so a
        private reference here would be silently rewritten, not caught."""
        assert "dawg-io" not in PUBLIC_WORKFLOW.read_text()


class TestDocsPreviewWorkflow:
    """The dev preview this repository publishes at its github.io address."""

    @pytest.fixture(scope="class")
    def preview(self):
        return load(PREVIEW_WORKFLOW)

    def test_name_is_distinct_from_production(self, preview, public_workflow):
        assert preview["name"] == PREVIEW_WORKFLOW_NAME
        assert preview["name"] != public_workflow["name"]

    def test_absolute_urls_point_at_the_preview(self, preview):
        """Left alone, canonicals and the sitemap name actionsmanager.io."""
        run = next(
            s for s in preview["jobs"]["build"]["steps"]
            if s.get("name") == "Build with Astro"
        )["run"]
        assert "DOCS_SITE=" in run and "DOCS_BASE=" in run
        assert "Disallow: /" in run, "the preview must stay out of search results"

    def test_astro_config_reads_the_preview_overrides(self):
        config = (REPO_ROOT / "docs" / "astro.config.mjs").read_text()
        assert "process.env.DOCS_SITE" in config
        assert "process.env.DOCS_BASE" in config

    def test_a_cname_fails_the_build(self, preview):
        """A domain here would take actionsmanager.io from the public repository."""
        run = next(
            s for s in preview["jobs"]["build"]["steps"]
            if s.get("name") == "Verify generated site"
        )["run"]
        assert "dist/CNAME" in run
        assert "exit 1" in run

    def test_pull_requests_into_develop_deploy_the_preview(self, preview):
        """Docs changes are seen on the preview before they merge."""
        triggers = preview.get("on", preview.get(True))
        for event in ("pull_request", "push"):
            assert triggers[event]["branches"] == ["develop"]
            assert "docs/**" in triggers[event]["paths"]
        assert "if" not in preview["jobs"]["deploy"]

    def test_it_is_the_only_docs_check(self, preview):
        """One docs workflow: it also runs what the standalone checks did."""
        assert {"docs-pipeline-contract", "build"} <= set(preview["jobs"])
        assert "test-docs" not in preview["jobs"], "the Jekyll build is retired"
        workflows = REPO_ROOT / ".github" / "workflows"
        assert not (workflows / "test-docs-local.yml").exists()
        assert not (workflows / "docs-next-build.yml").exists()

    def test_build_env_does_not_shadow_vites_base_url(self, preview):
        """BASE_URL in the build environment becomes Vite's base, and Starlight
        then marks no page current: no sidebar highlight, no prev/next."""
        step = next(
            s for s in preview["jobs"]["build"]["steps"]
            if s.get("name") == "Build with Astro"
        )
        assert "BASE_URL" not in step["env"] and "BASE_PATH" not in step["env"]

    def test_url_parity_is_checked(self, preview):
        run = next(
            s for s in preview["jobs"]["build"]["steps"]
            if s.get("name") == "Verify generated site"
        )["run"]
        assert "url-parity.txt" in run
        assert (REPO_ROOT / "docs" / "url-parity.txt").exists()

    def test_another_run_never_cancels_this_ones_checks(self, preview):
        """Only deploys share the one Pages site, and a running one finishes."""
        assert "concurrency" not in preview
        assert preview["jobs"]["deploy"]["concurrency"] == {
            "group": "pages",
            "cancel-in-progress": False,
        }


class TestPublicDocsOwnershipNote:
    """docs/ in the public repository is generated and gets overwritten."""

    def test_docs_readme_warns_that_edits_are_overwritten(self):
        text = (REPO_ROOT / "docs" / "README.md").read_text()
        assert "dawg-io/actions-manager" in text
        assert "overwritten" in text.lower()

    def test_note_survives_the_reference_rewrite(self):
        """Naming the private repo would be rewritten into the public one,
        inverting what the note says."""
        assert "dawg-io" not in (REPO_ROOT / "docs" / "README.md").read_text()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
