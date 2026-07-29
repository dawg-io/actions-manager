# Base stage: Setup dependencies
# Shared, weekly-patched base image (base-images/backend/Dockerfile +
# .github/workflows/base-images.yml) instead of building the OS layer fresh
# from python:3.12-slim on every CI run - see that Dockerfile for what it
# contains.
FROM ghcr.io/dawg-io/actions-manager/base-backend:latest AS base

# Set the working directory
WORKDIR /app

# Copy and install required dependencies
COPY requirements.txt .
RUN pip install psycopg2-binary websockets wsproto
RUN pip install --no-cache-dir -r requirements.txt

# Install stage: Copy application code and finalize setup
FROM base AS install

# Copy the application code
COPY . .

# Ensure local development `.env` defaults are not baked into the image.
RUN rm -f /app/.env

# Make the startup script executable
RUN chmod +x /app/start.sh

# Create a non-root user for running the application
# Using UID 1001 to avoid conflicts with common system users
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

# Set ownership of the application directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose FastAPI port
EXPOSE 8000

# Run migrations then start the application
CMD ["/app/start.sh"]
