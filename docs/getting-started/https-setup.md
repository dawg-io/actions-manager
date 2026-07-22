---
layout: default
title: HTTPS Configuration
parent: Getting Started
nav_order: 6
---

# HTTPS Configuration
{: .no_toc }

How to put ActionsManager Self-Hosted behind HTTPS for any non-localhost deployment.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

{: .warning }
**Do not expose ActionsManager over plain HTTP on a network or to the internet.** Personal Access Tokens (PATs) and API credentials are transmitted in plaintext over HTTP and can be intercepted. Always use HTTPS for any deployment reachable from outside `localhost`.

## Why this is enforced

ActionsManager **refuses to start** if `APP_URL` is set to a non-loopback `http://` address without `ALLOW_INSECURE_HTTP=true`, and it separately blocks PAT login over non-local HTTP as defense-in-depth. `localhost`/`127.0.0.1`/`::1` are always exempt — this only applies once you're serving the app on a real network address or domain.

If you're intentionally testing without HTTPS (not recommended for production), set:

```bash
ALLOW_INSECURE_HTTP=true
```

For anything else, put a reverse proxy in front of ActionsManager that terminates TLS. Pick whichever of the three below fits your infrastructure.

## Option 1: Caddy (easiest — automatic HTTPS)

Caddy automatically obtains and renews TLS certificates from Let's Encrypt with zero extra configuration.

**Caddyfile:**
```caddy
# /etc/caddy/Caddyfile

actionsmanager.example.com {
    reverse_proxy localhost:8080

    encode gzip zstd

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

**Install and run:**
```bash
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

sudo systemctl enable caddy
sudo systemctl start caddy
```

## Option 2: Traefik (Docker-native)

Traefik integrates directly with Docker Compose via labels and automatic service discovery.

```yaml
# docker-compose.traefik.yml
services:
  traefik:
    image: traefik:v2.10
    command:
      - "--api.insecure=false"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=admin@example.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
      - "--entrypoints.web.http.redirections.entryPoint.to=websecure"
      - "--entrypoints.web.http.redirections.entryPoint.scheme=https"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "./letsencrypt:/letsencrypt"
    networks:
      - web

  actionsmanager:
    image: ghcr.io/dawg-io/actions-manager:latest
    env_file:
      - .env.self-hosted
    environment:
      - APP_URL=https://actionsmanager.example.com
    volumes:
      - ./data:/app/data
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.actionsmanager.rule=Host(`actionsmanager.example.com`)"
      - "traefik.http.routers.actionsmanager.entrypoints=websecure"
      - "traefik.http.routers.actionsmanager.tls.certresolver=letsencrypt"
      - "traefik.http.services.actionsmanager.loadbalancer.server.port=8080"
    networks:
      - web

networks:
  web:
    driver: bridge
```

```bash
mkdir -p letsencrypt && chmod 600 letsencrypt
docker compose -f docker-compose.traefik.yml up -d
```

## Option 3: Nginx (manual configuration)

Maximum control, manual TLS certificate setup via Certbot.

```nginx
# /etc/nginx/sites-available/actions-manager

upstream backend {
    server localhost:8080;
}

server {
    listen 80;
    listen [::]:80;
    server_name actions-manager.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name actions-manager.example.com;

    ssl_certificate /etc/letsencrypt/live/actions-manager.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/actions-manager.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        # WebSocket connections need long timeouts
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/actions-manager /etc/nginx/sites-enabled/actions-manager
sudo nginx -t
sudo systemctl restart nginx

sudo apt-get install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d actions-manager.example.com
sudo certbot renew --dry-run
```

## Point ActionsManager at the new HTTPS URL

Whichever proxy you chose, update `.env.self-hosted` (or your `docker run -e` flags) and restart:

```bash
APP_URL=https://actionsmanager.example.com

docker compose -f docker-compose.self-hosted.yml restart
```

`APP_URL` derives the frontend URL, backend URL, OAuth callback, and WebSocket URL (`wss://` for an `https://` `APP_URL`) automatically — you don't need to set them individually. See [Installation]({% link getting-started/installation.md %}) for the full environment variable reference.
