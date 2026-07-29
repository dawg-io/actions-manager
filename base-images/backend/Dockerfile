# Shared base image for backend/Dockerfile and Dockerfile.self-hosted's
# final Python+nginx stage. Rebuilt weekly by
# .github/workflows/base-images.yml so OS-package security patches land on
# a predictable cadence instead of only whenever Docker Hub happens to
# rebuild python:3.12-slim.
FROM python:3.12-slim

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
