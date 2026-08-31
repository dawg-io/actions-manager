# Public HTTPS for a Self-Hosted Install via Cloudflare Tunnel

This guide puts your self-hosted ActionsManager behind a stable public HTTPS
hostname — for example `https://actions.example.com` — without opening an
inbound firewall port, forwarding anything on your router, or giving the host a
public IP. `cloudflared` makes an outbound connection to Cloudflare, and traffic
comes back down it.

It is one of the reverse-proxy options in
[SELF_HOSTED_INSTALL.md → Using HTTPS with Reverse Proxy](../SELF_HOSTED_INSTALL.md#using-https-with-reverse-proxy),
alongside Caddy, Traefik and Nginx. Pick this one when the host sits behind NAT
or a firewall you would rather not touch; pick Caddy when the host already has
port 443 reachable from the internet, since it is less moving parts.

Do not expose ActionsManager over plain HTTP beyond localhost. PATs and API
credentials would cross the network in the clear. Everything below exists to
get you off `ALLOW_INSECURE_HTTP`.

Two things this buys you beyond encryption:

- **GitHub OAuth login**, which needs a fixed callback URL GitHub can reach.
- **Webhook delivery**, so a merged pull request updates its status immediately
  instead of on the next poll. If that is *all* you want, you do not need this
  guide — expose the single `POST /webhooks/github` path instead, per
  [Exposing the Webhook Endpoint](WEBHOOK_ENDPOINT.md).

## What you are pointing the tunnel at

The self-hosted image is a single container serving the dashboard, the API and
the WebSocket on **one port, 8080**:

```bash
docker run -d \
  --name actions-manager \
  -p 8080:8080 \
  -v actions-manager-data:/app/data \
  -e INSTALLATION_MODE=self-hosted \
  -e SECRET_KEY=<your_generated_key> \
  ghcr.io/dawg-io/actions-manager:latest
```

or, with `docker-compose.self-hosted.yml`, the `app` service publishing
`${PORT:-8080}:8080`. (No `ALLOW_INSECURE_HTTP` above because nothing but
`localhost` reaches it yet — see
[INSTALLATION.md](../../INSTALLATION.md) for the full first-run command.)

One port means one hostname and one ingress rule — there is no separate API or
frontend origin to route.

## Prerequisites

- A working self-hosted install, reachable on the host at
  `http://localhost:8080`. Confirm with `curl -f http://localhost:8080/healthz`.
- A Cloudflare account with a zone you control (`example.com` below).
- `cloudflared` installed on the host, or Docker to run it as a container.

## One-time Cloudflare setup

```bash
# Authenticate and create a named tunnel
cloudflared tunnel login
cloudflared tunnel create actionsmanager

# Note the tunnel UUID and the credentials file it wrote, e.g.
# ~/.cloudflared/<tunnel-id>.json

# Point the hostname at it
cloudflared tunnel route dns actionsmanager actions.example.com
```

That last command creates the CNAME in your Cloudflare zone. Nothing is
reachable yet — the tunnel has to be running for it to resolve to anything.

## Tunnel configuration

`~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: actions.example.com
    service: http://localhost:8080
  # Anything else is refused rather than silently routed
  - service: http_status:404
```

WebSocket traffic needs no special configuration — Cloudflare Tunnel proxies
the `Upgrade` handshake as-is, so ActionsManager's `/ws` endpoint works over
the same hostname. That matters here: live workflow status, drift updates and
PR state all arrive over that socket, so a proxy that drops upgrades leaves the
UI looking frozen rather than broken.

## Run it

**On the host**, as a service that survives reboots. `cloudflared service
install` reads its configuration from `/etc/cloudflared/`, so put the file
there rather than under `~`:

```bash
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/config.yml /etc/cloudflared/config.yml
sudo cp ~/.cloudflared/<tunnel-id>.json /etc/cloudflared/
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

**Or as a container**, if you would rather not install anything on the host. On
a Linux host, `--network host` lets it reach the published port the same way
you just did with `curl`:

```bash
docker run -d \
  --name actions-manager-tunnel \
  --restart unless-stopped \
  --network host \
  -v ~/.cloudflared:/etc/cloudflared:ro \
  cloudflare/cloudflared:2025.11.1 \
  tunnel --config /etc/cloudflared/config.yml run
```

Avoid `--network container:actions-manager` here: it works, but it ties the
tunnel's network namespace to the app container, so recreating the app on an
upgrade leaves the tunnel with no network until it is recreated too.

With Compose instead, add `cloudflared` as a service on the same network and
target the app by service name — `service: http://app:8080` in `config.yml` —
rather than `localhost`. Keep it in a file of your own (an override, or a
separate project attached to the app's network) so a
`docker compose pull && docker compose up -d` upgrade of ActionsManager does
not disturb it.

## Point the app at its new URL

Set `APP_URL` to the public hostname. On the self-hosted image this one
variable is enough — `start.sh` derives the backend, frontend and WebSocket
URLs from it at container start, including `wss://` for an `https://` value, so
no rebuild is needed:

```bash
APP_URL=https://actions.example.com
```

Then **remove `ALLOW_INSECURE_HTTP`**. It exists only to permit plain HTTP on a
non-loopback address; the app is behind TLS now, and leaving it set keeps a
guard switched off for no reason.

Restart the container to pick both up. Keep `SECRET_KEY` exactly as it was —
changing it makes previously saved tokens unreadable.

If you use **GitHub OAuth login**, update the OAuth App's callback URL to match
the new `APP_URL` in the same pass, or the sign-in round trip fails with a
redirect-URI error.

Full semantics for these variables, including the auto-detection that makes
`APP_URL` optional for PAT-only installs, are in
[ENVIRONMENT_VARIABLES.md](../ENVIRONMENT_VARIABLES.md).

## Validate

```bash
# TLS terminates at Cloudflare and the app answers
curl -sSI https://actions.example.com/healthz | head -1

# The origin is no longer needed from outside
curl -sS http://localhost:8080/healthz
```

Then load `https://actions.example.com` in a browser and confirm live updates
arrive — open a project and watch a workflow status change without reloading.
That exercises the WebSocket, which a plain `curl` does not.

If you enabled webhooks, send a test delivery from the GitHub App or repository
settings and confirm a `200` at
`https://actions.example.com/webhooks/github`.

## Triage

```bash
docker logs --tail=100 actions-manager
docker logs --tail=100 actions-manager-tunnel   # or: journalctl -u cloudflared
cloudflared tunnel info actionsmanager
```

| Symptom | Likely cause |
|---|---|
| Cloudflare error 1033 | The tunnel is not running, or the DNS route was never created |
| Cloudflare 502 | `cloudflared` is running but cannot reach `http://localhost:8080` — check the ingress `service:` and, for the container form, that it shares the app's network |
| Container exits on start with a URL error | `APP_URL` is plain HTTP on a non-loopback address and `ALLOW_INSECURE_HTTP` is unset. Behind the tunnel `APP_URL` should be `https://` |
| Page loads, status never updates | The WebSocket is not connecting. Check `APP_URL` uses `https://` so the derived URL is `wss://`, not `ws://` |
| OAuth `redirect_uri` mismatch | The OAuth App's callback URL does not match `APP_URL` |
| Saved tokens stopped working | `SECRET_KEY` changed when the container was recreated |

## Optional hardening

Put Cloudflare Access in front of `actions.example.com` to require an identity
before the app is reachable at all. It is enforced at Cloudflare's edge, so
nothing in the container or the tunnel config changes.

If you also serve webhooks on this hostname, scope a bypass policy to
`/webhooks/github` — GitHub cannot satisfy an Access challenge, and deliveries
will fail if it has to. The endpoint rejects every request whose HMAC does not
verify, so a bypass there is not an open door.

## Tearing it down

```bash
# Container form
docker rm -f actions-manager-tunnel
# Host service form
sudo systemctl disable --now cloudflared

cloudflared tunnel delete actionsmanager
# Then remove the CNAME record from the Cloudflare dashboard
```

Point `APP_URL` back at the host address, restore `ALLOW_INSECURE_HTTP=true` if
you are going back to plain HTTP, revert the OAuth App callback, and restart.
Your data is on the `actions-manager-data` volume throughout and is untouched
by any of this.
