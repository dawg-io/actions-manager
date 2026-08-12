# Database Migrations

This directory contains database migration scripts for ActionsManager. These migrations ensure your database schema stays in sync with the application models.

## Quick Start

### Run All Migrations

The easiest way to ensure your database is up to date is to run the master migration script:

```bash
cd backend
python run_migrations.py
```

This script will automatically:
- Detect your database type (SQLite or PostgreSQL)
- Run all necessary migrations in the correct order
- Report success/failure for each migration

## When to Run Migrations

You should run migrations:
- **After upgrading** the application to a new version
- **When you see database errors** like "no such column" or "value too long"
- **After fresh installation** if using an existing database

## Common Issues and Solutions

### Issue 1: "no such column: projects.pr_state"

**Error:**
```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such column: projects.pr_state
```

**Solution:**
Run the PR tracking migration:
```bash
cd backend
python migrate_add_pr_tracking.py
```

Or run all migrations:
```bash
cd backend
python run_migrations.py
```

### Issue 2: "value too long for type character varying(4)"

**Error:**
```
sqlalchemy.exc.DataError: (psycopg2.errors.StringDataRightTruncation) value too long for type character varying(4)
```

**Solution:**
Run the project_code length fix migration:
```bash
cd backend
python migrate_fix_project_code_length.py
```

Or run all migrations:
```bash
cd backend
python run_migrations.py
```

## Available Migrations

### Critical Migrations (Required)

1. **migrate_add_pr_tracking.py**
   - Adds `pr_state` column to `projects` table
   - Creates `project_pull_requests` table
   - Required for project creation to work

2. **migrate_fix_project_code_length.py**
   - Changes `project_code` column from VARCHAR(4) to VARCHAR(10)
   - Required for PostgreSQL deployments
   - Allows project keys up to 10 characters

### Optional Migrations

3. **migrate_add_reusable_workflows_enabled.py**
   - Adds reusable workflows feature flag to projects

4. **migrate_add_marketplace_webhooks.py**
   - Adds marketplace webhook support (cloud deployments only)

5. **migrate_add_webhook_security.py**
   - Adds webhook security features

6. **migrate_add_admin_columns.py**
   - Adds admin-related columns to accounts table

7. **migrate_add_admin_override.py**
   - Adds admin override functionality

8. **migrate_add_api_calls_column.py**
   - Adds API call tracking columns

9. **migrate_fix_workflow_constraints.py**
   - Fixes workflow table constraints

10. **migrate_normalize_professional_tier.py**
    - Normalizes tier naming conventions

## Running Individual Migrations

To run a specific migration:

```bash
cd backend
python migrate_<name>.py
```

Example:
```bash
cd backend
python migrate_add_pr_tracking.py
```

## Database Support

All migrations support both:
- **SQLite** (for self-hosted installations)
- **PostgreSQL** (for cloud deployments)

The migrations automatically detect which database you're using based on the `DATABASE_URL` environment variable.

## For Docker Deployments

If you're running ActionsManager in Docker, you can run migrations inside the container:

```bash
# Docker Compose
docker compose exec app python /app/backend/run_migrations.py

# Or run a specific migration
docker compose exec app python /app/backend/migrate_add_pr_tracking.py
```

## Troubleshooting

### Migration fails with "database is locked"

This can happen with SQLite if the application is running. Stop the application first:

```bash
# Stop the application
docker compose down

# Run migrations
python run_migrations.py

# Start the application
docker compose up -d
```

### Migration reports "already exists"

This is normal! Migrations check if changes have already been applied and skip them if they have.

### Need to reset the database?

If you want to start fresh (⚠️ **this will delete all data**):

**SQLite:**
```bash
cd backend
rm -f actionsmanager.db
python run_migrations.py
```

**PostgreSQL:**
Drop the database and recreate it, then run migrations.

## Need Help?

If you encounter issues with migrations:

1. Check the error message - it usually indicates which column or constraint is causing the problem
2. Make sure you're running the latest version of the application
3. Try running migrations with verbose output: `python run_migrations.py`
4. Open an issue on GitHub with the error message and database type
