"""
Seed migration: pre-populate the shared Actions Projects catalog with the 7
actions already hand-curated in frontend/src/utils/actionInputSchemas.ts, so
every install starts with the common list already there instead of empty.

Actions Projects are a shared, workspace-wide catalog (not per-user) - see
backend/actions_projects.py. These seeded rows are owned by a reserved system
account rather than any real user. That account's existence is the
idempotency marker: once it exists, this migration is a no-op on every
future run, even if a user later deletes some or all of the 7 rows - removal
is permanent, it should never silently reappear on restart.
"""

import json
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from migration_utils import get_migration_database_url
from database import DATABASE_URL as APP_DATABASE_URL
from models import Account, ActionsProject

SEED_ACCOUNT_GITHUB_USER = "__actionsmanager_seed__"
SEED_ACCOUNT_EMAIL = "seed@actionsmanager.internal"

# Ported from frontend/src/utils/actionInputSchemas.ts's ACTION_INPUT_CATALOG.
# ActionInput has no `type`/`options` field (matches how action.yml itself
# never declares a formal type) - only description/required/default carry over.
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
]


def run_migration(database_url: str | None = None):
    """Seed the 7 default Actions Projects exactly once, ever."""
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
            source_url = f"https://github.com/{action['owner']}/{action['repo']}/blob/{action['ref']}/action.yml"
            db.add(ActionsProject(
                user_id=seed_account.user_id,
                name=action["name"],
                description=action["description"],
                source_url=source_url,
                owner=action["owner"],
                repo=action["repo"],
                ref=action["ref"],
                yaml_path="action.yml",
                inputs_json=json.dumps(action["inputs"]),
                last_modified_by=SEED_ACCOUNT_GITHUB_USER,
            ))

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
