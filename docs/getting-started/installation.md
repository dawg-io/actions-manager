---
layout: default
title: Installation
parent: Getting Started
nav_order: 2
---

# Installation
{: .no_toc }

Detailed installation guide for ActionsManager Self-Hosted Beta.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

> **Beta notice:** ActionsManager Self-Hosted is currently a free beta preview for testing, evaluation, and feedback. No paid plans are currently available. Provided as-is, without warranty or production-readiness guarantee.

## Prerequisites

- Docker Engine 20.10+ with Docker Compose plugin (or Podman 3.0+)
- A GitHub account
- Free port `8080` on your host
- 4 GB RAM (8 GB recommended), 10 GB disk

## Installation Methods

ActionsManager can be installed using either `docker run` or Docker Compose. Both use the same prebuilt image:

```
ghcr.io/dawg-io/actions-manager:latest
```

SQLite is the default database. PostgreSQL is available for larger deployments.

## Option 1: Docker Run (Fastest)

For PAT-based login (no OAuth App required):

```bash
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e SECRET_KEY=<your_generated_key> \
  ghcr.io/dawg-io/actions-manager:latest
```

For GitHub OAuth login, add your OAuth App credentials:

```bash
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e SECRET_KEY=<your_generated_key> \
  -e APP_URL=http://localhost:8080 \
  -e GITHUB_CLIENT_ID=your_client_id \
  -e GITHUB_CLIENT_SECRET=your_client_secret \
  ghcr.io/dawg-io/actions-manager:latest
```

Generate `<your_generated_key>` once with `openssl rand -hex 32` and use the same value every time you restart or update the container.

> **Note:** The self-hosted image now forces `INSTALLATION_MODE=self-hosted` in `start.sh`, so you can omit that variable. `VITE_APP_URL` still works as a deprecated alias for `APP_URL`.

## Option 2: Docker Compose

Create a `docker-compose.yml` file:

```yaml
version: "3.8"
services:
  actions-manager:
    image: ghcr.io/dawg-io/actions-manager:latest
    ports:
      - "8080:8080"
    volumes:
      - actions-manager-data:/app/data
    environment:
      - SECRET_KEY=${SECRET_KEY}
      # Optional OAuth (set APP_URL to match your deployment URL when using OAuth;
      # VITE_APP_URL remains supported as a deprecated alias):
      # - APP_URL=http://localhost:8080
      # - GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}
      # - GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}
    restart: unless-stopped

volumes:
  actions-manager-data:
```

Then start with:

```bash
docker compose up -d
```

Make sure `SECRET_KEY` is set in your `.env` file (generate once with `openssl rand -hex 32` and reuse on every restart).

## Authentication Setup

### Personal Access Token (Recommended for Quick Start)

No additional configuration required. After starting the container:

1. Open `http://localhost:8080`
2. Click **Sign in with Personal Access Token**
3. Paste your GitHub PAT and submit

See [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %}) for token creation instructions.

### GitHub OAuth

1. Create a GitHub OAuth App (see [GitHub OAuth Setup]({% link getting-started/github-oauth-setup.md %}))
2. Add `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` to your container environment
3. Use the **Sign in with GitHub** button

## Post-Installation

After startup:

1. Open `http://localhost:8080`
2. Sign in using your preferred authentication method
3. Create your first project
4. Add repositories to manage

## Upgrading

Pull the latest image and restart:

```bash
docker pull ghcr.io/dawg-io/actions-manager:latest
docker stop actions-manager
docker rm actions-manager
# Re-run the docker run command with the same volume mount
```

{: .warning }
Back up your data volume before upgrading. The SQLite database is stored in the mounted `actions-manager-data` volume.

## Accessing Logs

```bash
# Docker run
docker logs actions-manager --tail=100 -f

# Docker Compose
docker compose logs --tail=100 -f
```

## Uninstalling

```bash
docker stop actions-manager
docker rm actions-manager
# To also remove data:
docker volume rm actions-manager-data
```

## Next Steps

- [GitHub PAT Setup]({% link getting-started/github-pat-setup.md %})
- [GitHub OAuth Setup]({% link getting-started/github-oauth-setup.md %})
- [Troubleshooting]({% link troubleshooting/common-errors.md %})
