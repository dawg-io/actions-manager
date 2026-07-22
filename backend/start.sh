#!/bin/bash
# Backend startup script: runs database migrations then starts the application.
# This ensures schema changes are applied before the API begins handling requests.

set -e

echo "🔄 Running database migrations..."
python /app/run_migrations.py

# ---------------------------------------------------------------------------
# Startup diagnostics: validate the backend entrypoint before launching
# Uvicorn.  This surfaces the real Python traceback instead of the generic
# "Could not import module 'main'" Uvicorn error, making it far easier to
# diagnose missing files, bad volume mounts, or broken imports.
# ---------------------------------------------------------------------------
echo "Validating backend entrypoint..."

if [ ! -f /app/main.py ]; then
  echo "ERROR: /app/main.py is missing."
  echo "This usually means a Docker volume mount is overriding /app (the backend workdir)."
  ls -la /app || true
  exit 1
fi

cd /app
python -c "import main; print('Backend import validation passed')" || {
  echo "ERROR: Failed to import backend main.py."
  echo "Review the Python traceback above for the root cause."
  exit 1
}

echo "🚀 Starting ActionsManager backend..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
