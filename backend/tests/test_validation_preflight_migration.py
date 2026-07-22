import os
import sys

from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from migrate_add_validation_preflight import run_migration  # noqa: E402


def test_validation_preflight_migration_upgrades_older_projects_schema(tmp_path):
    db_path = tmp_path / "older_schema.db"
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE projects (
                    project_id INTEGER PRIMARY KEY,
                    project_code VARCHAR(10),
                    project_name VARCHAR(255) NOT NULL,
                    user_id INTEGER NOT NULL,
                    branch_regex VARCHAR(255),
                    branch_option VARCHAR(50),
                    branch_max_age_days INTEGER,
                    reusable_workflows_enabled BOOLEAN NOT NULL DEFAULT 0,
                    use_prefix BOOLEAN NOT NULL DEFAULT 1,
                    pr_state VARCHAR(20) NOT NULL DEFAULT 'new',
                    project_type VARCHAR(20) NOT NULL DEFAULT 'standard',
                    repository_visibility_scope VARCHAR(10) NOT NULL DEFAULT 'public',
                    project_color VARCHAR(20),
                    drift_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
                    drift_count INTEGER NOT NULL DEFAULT 0,
                    last_drift_check_at DATETIME,
                    drift_error_summary VARCHAR(500),
                    created_at DATETIME,
                    updated_at DATETIME,
                    last_modified_by VARCHAR(255)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO projects (
                    project_id,
                    project_code,
                    project_name,
                    user_id,
                    reusable_workflows_enabled,
                    use_prefix,
                    pr_state,
                    project_type,
                    repository_visibility_scope,
                    drift_status,
                    drift_count
                ) VALUES (
                    1,
                    'OLD',
                    'Older Project',
                    1,
                    0,
                    1,
                    'new',
                    'standard',
                    'public',
                    'unknown',
                    0
                )
                """
            )
        )

    run_migration(database_url)
    run_migration(database_url)

    columns = {column["name"] for column in inspect(engine).get_columns("projects")}
    assert {
        "validation_repo_id",
        "preflight_required",
        "last_preflight_status",
        "last_preflight_run_at",
        "last_preflight_error",
        "last_preflight_pr_url",
        "last_preflight_content_hash",
    }.issubset(columns)

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT validation_repo_id, preflight_required, last_preflight_status
                FROM projects
                WHERE project_id = 1
                """
            )
        ).one()

    assert row.validation_repo_id is None
    assert row.preflight_required in (False, 0)
    assert row.last_preflight_status is None
