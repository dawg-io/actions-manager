#!/usr/bin/env python3
"""
Master migration script for ActionsManager database schema updates.

This script runs all necessary database migrations to ensure the database schema
is up to date with the application models.

Usage:
    python run_migrations.py

The script will automatically detect the database type (SQLite or PostgreSQL)
and run the appropriate migrations.
"""

import sys
import subprocess
from pathlib import Path
from migration_utils import get_database_type

# List of migration scripts to run in order
# These are the critical migrations needed for the application to work
MIGRATION_SCRIPTS = [
    "migrate_add_pr_tracking.py",                    # Adds pr_state column
    "migrate_fix_project_code_length.py",            # Fixes project_code VARCHAR length
    "migrate_add_linked_reusable_workflows.py",      # Adds linked_reusable_workflows table
    "migrate_add_workflow_status.py",                # Adds workflow_status column to workflows
    "migrate_add_workflow_versions.py",              # Adds workflow_versions table
    "migrate_add_pr_history_fields.py",              # Adds PR history fields (title, author, body, merged_at, closed_at, workflow_names)
    "migrate_add_workspace_members.py",             # Adds workspace_members table for multi-user support
    "migrate_co_admin_to_admin.py",                # Normalizes legacy co_admin workspace role to admin
    "migrate_add_last_modified_by.py",              # Adds last_modified_by audit column to workflows and projects
    "add_permission_tracking_fields.py",            # Adds GitHub permission tracking fields (github_permission_status, github_permission_checked_at)
    "migrate_add_codeowners.py",                    # Adds codeowners table for CODEOWNERS file management
    "migrate_add_repo_workflow_overrides.py",       # Adds repo_workflow_overrides table for per-repo workflow overrides
    "migrate_add_repository_visibility_scope.py",   # Adds repository_visibility_scope column to projects (public/private)
    "migrate_add_project_color.py",                # Adds project_color column to projects (identity accent key)
    "migrate_add_project_drift_summary.py",        # Adds cached project-level drift summary columns
    "migrate_add_validation_preflight.py",         # Adds validation repository preflight columns to projects
    "migrate_add_preflight_content_hash.py",       # Adds last_preflight_content_hash column to projects
    "migrate_add_github_pat_fields.py",            # Adds encrypted PAT fields to accounts
    "migrate_add_auth_sessions.py",                # Adds hashed server-side auth sessions
    "migrate_add_pr_campaigns.py",                 # Adds project_pr_campaigns table and campaign_id column on project_pull_requests
    "migrate_add_custom_files.py",                 # Adds custom_files table for project-level managed text files
    "migrate_add_pr_file_names.py",                # Adds file_names column to project_pull_requests for per-PR custom file + CODEOWNERS tracking
    "migrate_add_actions_projects.py",             # Adds actions_projects table for custom GitHub Actions (issue #1687)
    "migrate_seed_default_actions_projects.py",    # Seeds the shared Actions Projects catalog with 7 common actions
    "migrate_add_action_branding.py",              # Adds branding_icon/branding_color columns to actions_projects
    "migrate_add_action_groups.py",                # Adds action_groups and action_group_memberships tables
    "migrate_add_notifications_schema.py",         # Adds notification_events/deliveries/subscriptions/settings tables (issue #1790)
    "migrate_add_workflow_drift_states.py",        # Adds workflow_drift_states table for drift transition detection (issue #1793)
    "migrate_add_campaign_last_known_status.py",   # Adds last_known_status column to project_pr_campaigns (issue #1794)
    "migrate_add_project_display_order.py",        # Adds project_display_order table for per-user grid ordering (issue #1804)
    # After the drift-states table exists, since it rebuilds that table.
    "migrate_add_drift_state_branch.py",           # Keys drift state by branch as well as repo (drift hardening PR 5)
    "migrate_add_workflow_tree_cache.py",          # Caches tree listings + ETags so unchanged branches cost no rate limit
    "migrate_add_drift_state_display_fields.py",   # Lets the drift panel render from stored state without calling GitHub
    "migrate_add_drift_check_failure_count.py",    # Adds a consecutive-failure counter to projects, for sweep backoff
    "migrate_add_workflow_runs.py",                # Stores GitHub Actions runs for build metrics (issue #689)
    "migrate_add_drift_configuration.py",          # Moves drift sweep config out of env vars: global settings + per-project interval
    # After the seed account exists, so it repairs the same boot that creates it.
    "migrate_revoke_seed_workspace_membership.py", # Takes workspace admin off the seed account and restores it to the installer
    "migrate_add_campaign_snapshot.py",            # Adds target_repos/base_commits/policy_version snapshot columns to project_pr_campaigns
    "migrate_add_campaign_rollback.py",            # Adds rollback_of_campaign_id/rollback_am_action to project_pr_campaigns
    # Must stay last: purges rows orphaned while SQLite foreign keys were
    # disabled, so every table it cleans has to exist by the time it runs.
    "migrate_add_project_workflow_unique.py",      # Enforces one project per workflow (drift hardening PR 4)
    "migrate_purge_orphaned_rows.py",              # Removes pre-existing orphaned rows (issue #1811)
]


def run_migration_script(script_path):
    """Run a migration script and return success/failure."""
    script_name = script_path.name
    print(f"\n{'='*60}")
    print(f"Running: {script_name}")
    print('='*60)
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Print output
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        if result.returncode == 0:
            print(f"✅ {script_name} completed successfully")
            return True
        else:
            print(f"❌ {script_name} failed with exit code {result.returncode}")
            return False
            
    except Exception as e:
        print(f"❌ Error running {script_name}: {e}")
        return False

def main():
    """Run all necessary database migrations in order."""
    print("="*60)
    print("ActionsManager Database Migration Tool")
    print("="*60)
    
    db_type = get_database_type()
    print(f"\n📊 Detected database type: {db_type.upper()}")
    
    # Get the backend directory
    backend_dir = Path(__file__).parent
    
    migration_scripts = MIGRATION_SCRIPTS
    
    # Check which migrations exist
    existing_migrations = []
    missing_migrations = []
    
    for script_name in migration_scripts:
        script_path = backend_dir / script_name
        if script_path.exists():
            existing_migrations.append(script_path)
        else:
            missing_migrations.append(script_name)
    
    if missing_migrations:
        print("\n⚠️  Warning: Some migration scripts are missing:")
        for script in missing_migrations:
            print(f"   - {script}")
    
    if not existing_migrations:
        print("\n❌ No migration scripts found to run")
        return 1
    
    print(f"\n📋 Found {len(existing_migrations)} migration(s) to run:")
    for script_path in existing_migrations:
        print(f"   - {script_path.name}")
    
    # Run migrations
    success_count = 0
    failure_count = 0
    
    for script_path in existing_migrations:
        if run_migration_script(script_path):
            success_count += 1
        else:
            failure_count += 1
            # Continue with other migrations even if one fails
    
    # Summary
    print("\n" + "="*60)
    print("Migration Summary")
    print("="*60)
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {failure_count}")
    
    if failure_count == 0:
        print("\n🎉 All migrations completed successfully!")
        return 0
    else:
        print(f"\n⚠️  {failure_count} migration(s) failed. Please check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
