# Exposing the Webhook Endpoint

How to let GitHub deliver events to a self-hosted ActionsManager, including instances with no
public IP.

## Do I need this?

**Only if you want GitHub to notify ActionsManager of events.** Everything else — creating and
delivering workflows, drift detection, pull request campaigns — works with no inbound access at
all, because ActionsManager calls *out* to GitHub.

| Feature | Needs an inbound URL? |
|---|---|
| Workflow delivery (PR or direct) | No |
| Drift detection | No |
| Resolving drift | No |
| Instant PR-merge status updates | **Yes** |

Without a reachable endpoint, ActionsManager learns about merged pull requests the next time it
polls rather than the moment they merge. Nothing breaks; it is a latency difference.

> **Note:** If your instance has no public URL — common for internal or development deployments — you can skip
this guide entirely and revisit it later. There is no degraded mode to opt into.

## What has to be reachable

GitHub delivers to a single path:

```
POST https://<your-instance>/webhooks/github
```

**Only that path needs to be reachable from the internet.** You do not need to expose the UI, the
API, or anything else. Every option below can be scoped to just this path, and doing so is the
recommended setup — it keeps your dashboard private while still receiving events.

Requirements:

- **HTTPS.** GitHub will deliver over plain HTTP, but the payload includes repository names and
  branch names; use TLS.
- **Reachable from GitHub's senders**, not from you. A URL that works in your browser on the office
  VPN is not necessarily reachable by GitHub.
- **A shared secret** — see [Securing the endpoint](#securing-the-endpoint). ActionsManager
  **rejects every webhook** when `GITHUB_PR_WEBHOOK_SECRET` is unset, so an exposed endpoint with
  no secret configured is inert rather than dangerous.

## Option 1: Cloudflare Tunnel

Good when you want a stable hostname on a domain you already control, and no inbound firewall
rules. `cloudflared` makes an outbound connection to Cloudflare, so nothing needs to be forwarded.

For a full production walkthrough (Kubernetes, credentials as Secrets, config as a ConfigMap), see
[Staging Cloud Deployment via Cloudflare Tunnel](STAGING_TUNNEL.md). The short
version for a Docker or bare-metal install:

```bash
# One-time: authenticate and create a named tunnel
cloudflared tunnel login
cloudflared tunnel create actionsmanager

# Point a hostname at it
cloudflared tunnel route dns actionsmanager actions.example.com
```

Then restrict the tunnel to the webhook path only, so the rest of the app stays private:

```yaml
# ~/.cloudflared/config.yml
tunnel: actionsmanager
credentials-file: /root/.cloudflared/<tunnel-id>.json

ingress:
  # Only the webhook path reaches the app
  - hostname: actions.example.com
    path: ^/webhooks/github$
    service: http://localhost:8080
  # Everything else is refused
  - service: http_status:404
```

```bash
cloudflared tunnel run actionsmanager
```

Your webhook URL is `https://actions.example.com/webhooks/github`.

> **Warning:** `cloudflared tunnel --url http://localhost:8080` gives you an instant `*.trycloudflare.com`
hostname with no account. It is useful for a one-off test, but the hostname changes every restart
and it exposes **all** paths — do not use it for anything lasting.

## Option 2: Tailscale Funnel

Good if you already run Tailscale. Note the distinction that catches people out:

- `tailscale serve` publishes to **your tailnet only** — GitHub cannot reach it.
- `tailscale funnel` publishes to the **public internet** — this is the one you need.

Funnel must be enabled for the node in your tailnet policy file, and HTTPS certificates must be
enabled for the tailnet. Then:

```bash
# Expose the local app publicly over HTTPS
tailscale funnel --bg 8080

# Confirm what is published
tailscale funnel status
```

Your URL is `https://<machine>.<tailnet>.ts.net`, so the webhook URL is
`https://<machine>.<tailnet>.ts.net/webhooks/github`.

To publish only the webhook path rather than the whole app, map that single path:

```bash
tailscale funnel --bg --set-path /webhooks/github http://localhost:8080/webhooks/github
```

> **Note:** Funnel listens on 443, 8443 or 10000 only, and exact flags vary between Tailscale versions — check
`tailscale funnel --help` against your installed version. Traffic is proxied through Tailscale's
infrastructure.

## Option 3: Reverse proxy or port forward

If you already terminate TLS at nginx, Caddy, Traefik or a cloud load balancer, forward just the
webhook path:

```nginx
location = /webhooks/github {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

The exact-match `location =` matters: it publishes only this path and nothing else on the instance.

## Configuring GitHub

Per repository (**Settings → Webhooks → Add webhook**), or once at organisation level to cover
every repository:

| Field | Value |
|---|---|
| Payload URL | `https://<your-instance>/webhooks/github` |
| Content type | `application/json` |
| Secret | The same value as `GITHUB_PR_WEBHOOK_SECRET` |
| Events | **Pull requests** |

## Securing the endpoint

Set a strong secret and give GitHub the same value:

```bash
openssl rand -hex 32
```

```bash
# .env.self-hosted
GITHUB_PR_WEBHOOK_SECRET=<the generated value>
```

Every request is verified with HMAC-SHA256 against `X-Hub-Signature-256`. Requests with a missing,
malformed or incorrect signature are rejected with 401, and — importantly — **if the secret is not
configured at all, every webhook is rejected**. ActionsManager will not accept unauthenticated
state changes.

Optionally, restrict who can reach the endpoint at the network layer. GitHub publishes its sender
ranges:

```bash
curl -s https://api.github.com/meta | jq -r '.hooks[]'
```

These change occasionally, so if you allowlist them, re-check periodically rather than setting and
forgetting.

## Checking your configuration

ActionsManager can tell you whether it is set up to receive webhooks, and what is missing:

```bash
curl -s http://localhost:8080/api/webhooks/readiness | jq
```

On an instance with no public URL — the normal case for internal deployments — you will see:

```json
{
  "ready": false,
  "public_url_configured": false,
  "secret_configured": false,
  "app_url": "http://localhost:8080",
  "webhook_url": null,
  "blockers": [
    "APP_URL is http://localhost:8080, which only resolves on the machine running ActionsManager. GitHub cannot deliver to it.",
    "GITHUB_PR_WEBHOOK_SECRET is not set. Until it is, every inbound webhook is rejected — nothing is exposed, the feature is simply off."
  ],
  "docs_url": "https://actionsmanager.io/guides/WEBHOOK_ENDPOINT.html"
}
```

Once a tunnel is running and the secret is set, `webhook_url` is the exact value to paste into
GitHub's **Payload URL** field:

```json
{
  "ready": true,
  "public_url_configured": true,
  "secret_configured": true,
  "webhook_url": "https://actions.example.com/webhooks/github",
  "blockers": []
}
```

This checks your **configuration**, not live reachability. It cannot ask GitHub to try, and a
self-request would succeed from inside your own network even when the instance is unreachable from
outside — which is the very situation it is meant to catch. A private or loopback `APP_URL` is
reported as unreachable; a public hostname is treated as plausible and confirmed by GitHub's
delivery log below.

## Verifying it works

1. In GitHub, open the webhook and check **Recent Deliveries**. A green tick means it reached you.
2. Use **Redeliver** on any delivery to retry without creating new activity.
3. Check the ActionsManager container logs for `📥 GitHub PR webhook:`.

Common failures:

| Symptom in GitHub | Cause |
|---|---|
| Timeout / couldn't connect | The URL is not reachable from the internet — a tunnel is not running, or DNS points somewhere else |
| `401 Invalid webhook signature` | The secret in GitHub does not match `GITHUB_PR_WEBHOOK_SECRET`, or the variable is unset |
| `404` | Wrong path — it must end in `/webhooks/github` |
| Green tick, nothing happens | The pull request is not one ActionsManager created, so it is ignored by design |

## Related topics

- [Staging Cloud Deployment via Cloudflare Tunnel](STAGING_TUNNEL.md)
- [Environment Variables](../ENVIRONMENT_VARIABLES.md)
- [Self-Hosted Installation](../SELF_HOSTED_INSTALL.md)
