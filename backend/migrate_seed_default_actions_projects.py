"""
Seed migration: pre-populate the shared Actions Projects catalog with a small
set of commonly used actions, so every install starts with the common list
already there instead of empty.

Actions Projects are a shared, workspace-wide catalog (not per-user) - see
backend/actions_projects.py. These seeded rows are owned by a reserved system
account rather than any real user. That account's existence is the
idempotency marker: once it exists, this migration is a no-op on every
future run, even if a user later deletes some or all of the rows - removal
is permanent, it should never silently reappear on restart. That also means
this migration alone never delivers an entry added to SEED_ACTIONS later:
migrate_seed_catalog_entries does that, once per entry, per install.
"""

import json
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from migration_utils import get_migration_database_url
from database import DATABASE_URL as APP_DATABASE_URL
from models import Account, ActionsProject, SEED_ACCOUNT_GITHUB_USER

SEED_ACCOUNT_EMAIL = "seed@actionsmanager.internal"

# The actions/* entries were ported from the frontend's original hand-curated
# catalog. ActionInput has no `type`/`options` field (matches how action.yml
# itself never declares a formal type) - only description/required/default
# carry over. branding_* is optional and only set for actions that declare it.
SEED_ACTIONS = [
    {
        "name": "Checkout Repository",
        "description": "Check out repository content",
        "owner": "actions", "repo": "checkout", "ref": "v7.0.1",
        "inputs": [
            {"name": "repository", "description": "Repository name with owner, e.g. actions/checkout", "required": False, "default": None},
            {"name": "ref", "description": "The branch, tag or SHA to checkout", "required": False, "default": None},
            {"name": "token", "description": "Personal access token used to fetch the repository", "required": False, "default": "${{ github.token }}"},
            {"name": "path", "description": "Relative path under $GITHUB_WORKSPACE to place the repository", "required": False, "default": None},
            {"name": "fetch-depth", "description": "Number of commits to fetch (0 = all history)", "required": False, "default": "1"},
            {"name": "fetch-tags", "description": "Whether to fetch tags even when fetch-depth > 0", "required": False, "default": "false"},
            {"name": "lfs", "description": "Whether to download Git-LFS files", "required": False, "default": "false"},
            {"name": "submodules", "description": "Whether to checkout submodules", "required": False, "default": "false"},
            {"name": "clean", "description": "Whether to run git clean before fetching", "required": False, "default": "true"},
            {"name": "persist-credentials", "description": "Whether to persist the checkout credentials for later git commands", "required": False, "default": "true"},
        ],
    },
    {
        "name": "Setup Node.js",
        "description": "Set up Node.js environment",
        "owner": "actions", "repo": "setup-node", "ref": "v7.0.0",
        "inputs": [
            {"name": "node-version", "description": "Version Spec of the version to use, e.g. 20, 20.x, >=18", "required": False, "default": None},
            {"name": "node-version-file", "description": "File containing the version spec, e.g. .nvmrc", "required": False, "default": None},
            {"name": "architecture", "description": "Target architecture, e.g. x86, x64, arm64", "required": False, "default": None},
            {"name": "cache", "description": "Package manager to cache dependencies for", "required": False, "default": None},
            {"name": "cache-dependency-path", "description": "Path to lockfile(s) used for caching", "required": False, "default": None},
            {"name": "registry-url", "description": "npm registry to configure for auth", "required": False, "default": None},
            {"name": "always-auth", "description": "Set always-auth in npmrc", "required": False, "default": "false"},
            {"name": "check-latest", "description": "Check for the latest available version", "required": False, "default": "false"},
        ],
    },
    {
        "name": "Setup Python",
        "description": "Set up Python environment",
        "owner": "actions", "repo": "setup-python", "ref": "v7.0.0",
        "inputs": [
            {"name": "python-version", "description": "Version range or exact version, e.g. 3.12, 3.x", "required": False, "default": None},
            {"name": "python-version-file", "description": "File containing the version spec, e.g. .python-version", "required": False, "default": None},
            {"name": "cache", "description": "Package manager to cache dependencies for", "required": False, "default": None},
            {"name": "architecture", "description": "Target architecture, e.g. x64, x86", "required": False, "default": None},
            {"name": "check-latest", "description": "Check for the latest available version", "required": False, "default": "false"},
            {"name": "allow-prereleases", "description": "Allow pre-release Python versions to be used", "required": False, "default": "false"},
        ],
    },
    {
        "name": "Setup Java",
        "description": "Set up Java environment",
        "owner": "actions", "repo": "setup-java", "ref": "v5.6.0",
        "inputs": [
            {"name": "distribution", "description": "Java distribution to install", "required": True, "default": None},
            {"name": "java-version", "description": "Version Spec of the version to use, e.g. 17, 21", "required": True, "default": None},
            {"name": "java-package", "description": "Java package type to install", "required": False, "default": "jdk"},
            {"name": "architecture", "description": "Target architecture, e.g. x64, x86, arm64", "required": False, "default": None},
            {"name": "cache", "description": "Build tool to cache dependencies for", "required": False, "default": None},
        ],
    },
    {
        "name": "Cache Dependencies",
        "description": "Cache dependencies and build outputs",
        "owner": "actions", "repo": "cache", "ref": "v6.1.0",
        "inputs": [
            {"name": "path", "description": "A list of files, directories, and wildcard patterns to cache", "required": True, "default": None},
            {"name": "key", "description": "An explicit key for restoring and saving the cache", "required": True, "default": None},
            {"name": "restore-keys", "description": "Ordered multiline list of prefix-matched keys to use when restoring a stale cache", "required": False, "default": None},
            {"name": "enableCrossOsArchive", "description": "Allow Windows runners to save/restore caches shared with other platforms", "required": False, "default": "false"},
        ],
    },
    {
        "name": "Upload Artifacts",
        "description": "Upload build artifacts",
        "owner": "actions", "repo": "upload-artifact", "ref": "v7.0.1",
        "inputs": [
            {"name": "name", "description": "Name of the artifact to upload", "required": False, "default": "artifact"},
            {"name": "path", "description": "A file, directory or wildcard pattern describing what to upload", "required": True, "default": None},
            {"name": "if-no-files-found", "description": "Behavior when no files are found using the provided path", "required": False, "default": "warn"},
            {"name": "retention-days", "description": "Days to retain the artifact before it expires (0 = repository default)", "required": False, "default": None},
            {"name": "overwrite", "description": "Whether to overwrite an existing artifact with the same name", "required": False, "default": "false"},
        ],
    },
    {
        "name": "Download Artifacts",
        "description": "Download build artifacts",
        "owner": "actions", "repo": "download-artifact", "ref": "v8.0.1",
        "inputs": [
            {"name": "name", "description": "Name of the artifact to download (omit to download all artifacts)", "required": False, "default": None},
            {"name": "path", "description": "Destination path to extract the artifact", "required": False, "default": None},
            {"name": "pattern", "description": "Glob pattern matching artifact names when downloading multiple artifacts", "required": False, "default": None},
            {"name": "merge-multiple", "description": "Merge multiple matched artifacts into a single directory", "required": False, "default": "false"},
        ],
    },
    {
        "name": "AM Build Vars",
        "description": "Share build variables across jobs, workflows and runs",
        "owner": "dawg-io", "repo": "am-build-vars", "ref": "v1.0.0",
        "branding_icon": "shield", "branding_color": "purple",
        "inputs": [
            {"name": "config-file", "description": "Explicit path to the build variables file (empty auto-discovers am-build-vars.yml)", "required": False, "default": ""},
            {"name": "defaults", "description": "Fleet-wide default values as a YAML mapping, overridden per key by the config file", "required": False, "default": ""},
            {"name": "export-env", "description": "Whether to write every resolved key into $GITHUB_ENV for later steps in the job", "required": False, "default": "true"},
            {"name": "fail-on-missing", "description": "Whether to fail the step when the config file does not exist", "required": False, "default": "false"},
            {"name": "share", "description": "Values to publish to the shared store, as a YAML mapping", "required": False, "default": ""},
            {"name": "share-env", "description": "Names of environment variables to capture and publish to the shared store", "required": False, "default": ""},
            {"name": "load-shared", "description": "Whether to read the shared store for this scope and apply it (needs actions: read)", "required": False, "default": "false"},
            {"name": "share-scope", "description": "Namespace for shared variables; steps sharing a scope see each other's values", "required": False, "default": "${{ github.ref_name }}"},
            {"name": "share-token", "description": "Token used to look the shared store artifact up through the REST API", "required": False, "default": "${{ github.token }}"},
            {"name": "share-retention-days", "description": "How long the shared store artifact is kept, in days (empty uses the repository default)", "required": False, "default": ""},
        ],
    },
]


def build_seed_row(action: dict, user_id: int) -> ActionsProject:
    """Build the ActionsProject row for one SEED_ACTIONS entry.

    Shared with migrate_seed_catalog_entries, which back-fills an entry added
    here after an install was already seeded - both must produce the same row.
    """
    return ActionsProject(
        user_id=user_id,
        name=action["name"],
        description=action["description"],
        source_url=f"https://github.com/{action['owner']}/{action['repo']}/blob/{action['ref']}/action.yml",
        owner=action["owner"],
        repo=action["repo"],
        ref=action["ref"],
        yaml_path="action.yml",
        inputs_json=json.dumps(action["inputs"]),
        branding_icon=action.get("branding_icon"),
        branding_color=action.get("branding_color"),
        last_modified_by=SEED_ACCOUNT_GITHUB_USER,
    )


def run_migration(database_url: str | None = None):
    """Seed the default Actions Projects into a fresh database, once, ever.

    An install that already has the seed account is finished here - a default
    added to SEED_ACTIONS later reaches it through migrate_seed_catalog_entries.
    """
    db_url = database_url or get_migration_database_url() or APP_DATABASE_URL
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        table_names = inspect(engine).get_table_names()
        if "accounts" not in table_names or "actions_projects" not in table_names:
            print("⚠️ accounts or actions_projects table does not exist yet, skipping seed")
            return

        existing = db.execute(
            text("SELECT user_id FROM accounts WHERE github_user = :github_user"),
            {"github_user": SEED_ACCOUNT_GITHUB_USER},
        ).fetchone()

        if existing:
            print("✅ Default Actions Projects already seeded, skipping")
            return

        print("🔧 Seeding default Actions Projects...")
        # Use the ORM model rather than hand-written INSERT SQL so every
        # NOT NULL column's Python-level default (e.g. Account.github_api_calls)
        # is applied automatically, regardless of how the schema evolves later.
        seed_account = Account(
            github_user=SEED_ACCOUNT_GITHUB_USER,
            github_email=SEED_ACCOUNT_EMAIL,
            account_type="system",
        )
        db.add(seed_account)
        db.flush()

        for action in SEED_ACTIONS:
            db.add(build_seed_row(action, seed_account.user_id))

        db.commit()
        print(f"✅ Seeded {len(SEED_ACTIONS)} default Actions Projects")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
