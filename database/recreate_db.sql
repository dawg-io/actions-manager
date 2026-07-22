-- =============================================================================
-- ActionsManager PostgreSQL Drop & Recreate Database Script
-- =============================================================================
--
-- PURPOSE:
--   Drops the existing 'actions_manager' database and creates a fresh one.
--   Use this to reset the database to a clean state.
--
-- WARNING:
--   This will PERMANENTLY DELETE all data in the 'actions_manager' database.
--   Make sure you have a backup before running this script.
--
-- HOW TABLES ARE CREATED (read this first)
-- -----------------------------------------
-- This script only creates an empty database shell — it does NOT create any
-- tables itself.  Tables are created in two stages after the database exists:
--
--   Stage 1 — Application startup (automatic)
--     When the FastAPI backend starts, backend/database.py calls:
--
--       Base.metadata.create_all(engine)
--
--     SQLAlchemy inspects every model defined in backend/models.py and issues
--     a CREATE TABLE IF NOT EXISTS statement for each one.  All core tables
--     (accounts, projects, repos, workflows, rulesets, project_repos,
--     project_workflows, project_rulesets, etc.) are created this way.
--     Simply starting the application is enough to build the initial schema.
--
--   Stage 2 — Migrations (manual, run once after startup)
--     Over time, new columns and tables have been added to the schema that
--     are not yet reflected in Base.metadata.create_all (because SQLAlchemy
--     only adds missing tables, not missing columns).  The migration scripts
--     in backend/ add those extra columns safely:
--
--       cd backend && python run_migrations.py
--
--     This is safe to run multiple times — each script checks whether its
--     column/table already exists before altering anything.
--
-- FULL SEQUENCE AFTER RUNNING THIS SCRIPT
-- ----------------------------------------
--   1. Run this script (drops and recreates the empty database).
--   2. Start the backend — SQLAlchemy auto-creates all tables on startup.
--   3. Run migrations to apply any additional schema changes:
--
--        cd backend && python run_migrations.py
--
-- HOW TO RUN THIS SCRIPT
-- -----------------------
--   You must be connected to a DIFFERENT database (e.g. 'postgres') — not to
--   'actions_manager' itself — because PostgreSQL does not allow dropping a
--   database that has active connections, including your own.
--
--   Option 1 — Run from the command line (recommended):
--
--     psql -U postgres -d postgres -f recreate_db.sql
--
--   Option 2 — Run interactively inside psql:
--
--     psql -U postgres
--     \i /path/to/recreate_db.sql
--
-- =============================================================================

-- Step 1: Terminate all active connections to the target database so the DROP
--         does not fail with "other users are connected to the database".
SELECT pg_terminate_backend(pid)
FROM   pg_stat_activity
WHERE  datname = 'actions_manager'
  AND  pid <> pg_backend_pid();

-- Step 2: Drop the existing database (safe — does nothing if it does not exist).
DROP DATABASE IF EXISTS actions_manager;

-- Step 3: Create a fresh, empty database with UTF-8 encoding.
CREATE DATABASE actions_manager
    WITH
    ENCODING    = 'UTF8'
    TEMPLATE    = template0;
