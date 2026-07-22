#!/bin/bash

# Actions Manager - Container Rebuild Script
# This script stops, removes old containers and images, and rebuilds/starts the application

set -e  # Exit on error
git pull
echo "🧹 Cleaning up old containers and images..."

# Stop and remove containers
echo "⏹️  Stopping containers..."
podman-compose -f docker-compose.self-hosted.yml down -v

podman system prune -a -f

BUILD_DATE=$(date +%s)
podman-compose -f docker-compose.self-hosted.yml build --no-cache

podman-compose -f docker-compose.self-hosted.yml up

echo "✅ Done! Application is running."
echo ""
echo "📝 View logs with: podman-compose logs -f"
echo "🛑 Stop with: podman-compose down"
