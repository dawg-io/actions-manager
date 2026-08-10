# Staging Cloud Deployment via Cloudflare Tunnel

This guide explains how to expose the in-cluster Actions Manager deployment
(built by `.github/workflows/docker-build-and-test.yml` and rolled out by Flux) at a
stable public HTTPS URL — for example `https://staging.example.com` — without
opening any inbound ports on your firewall or assigning a public IP to the
cluster.

The goal: after every push to `develop` (or `main`), the freshly built image is
deployed by Flux and immediately reachable at the same staging URL, so the
cloud deployment can be smoke-tested end-to-end (including GitHub OAuth and
Marketplace webhooks) on every code change.

## Why Cloudflare Tunnel

- **Outbound only.** `cloudflared` runs as a pod in the cluster and dials out to
  Cloudflare's edge. Nothing needs to be exposed inbound.
- **Free.** A Cloudflare account and a domain you control are sufficient; no
  paid plan is required for a single tunnel.
- **Real HTTPS URL.** Cloudflare terminates TLS on a hostname you own, which is
  what GitHub OAuth callbacks and Marketplace webhooks need.
- **Reuses the existing pipeline.** No changes to the build/deploy pipeline are
  required; the tunnel just fronts whatever the cluster is currently serving.

## Prerequisites

- A Cloudflare account.
- A domain (or subdomain) managed in Cloudflare DNS — e.g. `example.com`, with
  `staging.example.com` available to point at the tunnel.
- `cloudflared` CLI installed locally for the one-time tunnel creation
  (<https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/>).
- `kubectl` access to the cluster that already runs the Actions Manager
  backend and frontend (the same cluster Flux deploys to).
- Knowledge of the in-cluster Service that fronts the application — typically
  the ingress controller Service, or directly the `frontend` and `backend`
  Services in the Actions Manager namespace.

## One-time Cloudflare setup

1. **Log in and create the tunnel.** From a workstation:

   ```bash
   cloudflared tunnel login
   cloudflared tunnel create actions-manager-staging
   ```

   The `create` command prints a tunnel UUID and writes a credentials JSON
   file (e.g. `~/.cloudflared/<UUID>.json`). Keep this file — it is the
   tunnel's secret and will be loaded into the cluster as a Kubernetes
   Secret.

2. **Create the DNS route.** Map the chosen hostname to the tunnel:

   ```bash
   cloudflared tunnel route dns actions-manager-staging staging.example.com
   ```

   Cloudflare will create a proxied CNAME record automatically.

3. **Decide what the tunnel should point at inside the cluster.** Two common
   options:

   - **Front the existing ingress controller** (recommended if you already use
     ingress for hostname/path routing). Point the tunnel at the ingress
     controller's `Service` (e.g. `ingress-nginx-controller.ingress-nginx`)
     and let your existing `Ingress` resources route `staging.example.com` to
     the right backend.
   - **Point directly at the app Services.** Skip ingress entirely and route
     `/` to the frontend Service and `/api` (and any other backend paths) to
     the backend Service. This is simpler for a pure staging setup.

## Deploy `cloudflared` to the cluster

The tunnel runs as a small Deployment in the same cluster as Actions Manager.
You will need:

- The tunnel UUID and credentials JSON from step 1 above.
- A `config.yaml` describing the ingress rules (what hostname maps to what
  in-cluster Service).

### 1. Store the tunnel credentials as a Secret

Create the Secret from the credentials JSON Cloudflare generated for you:

```bash
kubectl create namespace cloudflared

kubectl -n cloudflared create secret generic tunnel-credentials \
  --from-file=credentials.json=$HOME/.cloudflared/<TUNNEL_UUID>.json
```

### 2. Provide the tunnel config as a ConfigMap

The config tells `cloudflared` which tunnel to run and how to map hostnames to
in-cluster Services.

**Option A — front your existing ingress controller:**

```yaml
# cloudflared-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cloudflared-config
  namespace: cloudflared
data:
  config.yaml: |
    tunnel: <TUNNEL_UUID>
    credentials-file: /etc/cloudflared/creds/credentials.json
    no-autoupdate: true
    ingress:
      - hostname: staging.example.com
        service: http://ingress-nginx-controller.ingress-nginx.svc.cluster.local:80
      - service: http_status:404
```

**Option B — point directly at the app Services** (replace the namespace and
Service names with whatever your Flux deployment uses):

```yaml
# cloudflared-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cloudflared-config
  namespace: cloudflared
data:
  config.yaml: |
    tunnel: <TUNNEL_UUID>
    credentials-file: /etc/cloudflared/creds/credentials.json
    no-autoupdate: true
    ingress:
      - hostname: staging.example.com
        path: ^/(api|docs|openapi.json|ws)(/|$)
        service: http://backend.actions-manager.svc.cluster.local:8000
      - hostname: staging.example.com
        service: http://frontend.actions-manager.svc.cluster.local:80
      - service: http_status:404
```

Apply it:

```bash
kubectl apply -f cloudflared-config.yaml
```

### 3. Deploy `cloudflared`

```yaml
# cloudflared-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cloudflared
  namespace: cloudflared
spec:
  replicas: 2
  selector:
    matchLabels:
      app: cloudflared
  template:
    metadata:
      labels:
        app: cloudflared
    spec:
      containers:
        - name: cloudflared
          image: cloudflare/cloudflared:2025.11.1
          args:
            - tunnel
            - --config
            - /etc/cloudflared/config/config.yaml
            - run
          livenessProbe:
            httpGet:
              path: /ready
              port: 2000
            initialDelaySeconds: 10
            periodSeconds: 10
          volumeMounts:
            - name: config
              mountPath: /etc/cloudflared/config
              readOnly: true
            - name: creds
              mountPath: /etc/cloudflared/creds
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: cloudflared-config
        - name: creds
          secret:
            secretName: tunnel-credentials
```

Apply:

```bash
kubectl apply -f cloudflared-deployment.yaml
kubectl -n cloudflared rollout status deploy/cloudflared
kubectl -n cloudflared logs deploy/cloudflared --tail=50
```

You should see lines like `Registered tunnel connection` for each
edge connection. Within a minute, `https://staging.example.com` will resolve to
your tunnel and proxy to the in-cluster Service you configured.

## Wire the app to the staging URL

Update the cloud-mode environment so the app knows its public origin and so
GitHub recognises the callback. In your Flux/Helm values (or whatever you use
to populate the backend Deployment env), set:

```env
VITE_FRONTEND_URL=https://staging.example.com
VITE_BACKEND_URL=https://staging.example.com
GITHUB_OAUTH_CALLBACK_URL=https://staging.example.com/api/auth/callback
```

Then in the GitHub OAuth App / GitHub App settings used by this staging
deployment:

- Set the **Authorization callback URL** to
  `https://staging.example.com/api/auth/callback`.
- If using GitHub Marketplace, set the **Webhook URL** to
  `https://staging.example.com/api/marketplace/webhook` (or whichever path the
  backend exposes for Marketplace events).

See [`docs/ENVIRONMENT_VARIABLES.md`](../ENVIRONMENT_VARIABLES.md) and
[`docs/CLOUD_DEPLOYMENT.md`](../CLOUD_DEPLOYMENT.md) for the full set of
variables that may need a staging-specific value.

## Validate after every push

The existing `.github/workflows/docker-build-and-test.yml` already pushes new
`dev-backend:<TIMESTAMP>` and `dev-frontend:<TIMESTAMP>` images on every push
to `develop`/`main`/`copilot/*`, and Flux rolls those into the cluster. Once
the tunnel is in place, the per-change validation loop is:

1. Push a commit to `develop`.
2. Wait for the GitHub Actions run to complete (5–10 minutes).
3. Wait for Flux to pick up the new image tag and roll the Deployments
   (typically under a minute after the image is pushed).
4. Hit `https://staging.example.com` in a browser and exercise the change.
5. Optional smoke checks from anywhere on the internet:

   ```bash
   curl -fsS https://staging.example.com/ -o /dev/null && echo frontend OK
   curl -fsS https://staging.example.com/api/test/build-patterns | head -c 200
   ```

If either check fails, inspect:

```bash
kubectl -n cloudflared logs deploy/cloudflared --tail=100
kubectl -n actions-manager get pods
kubectl -n actions-manager logs deploy/backend --tail=200
```

## Optional hardening

For a staging environment that is reachable from the public internet, consider
turning on Cloudflare Access (Zero Trust) in front of the tunnel hostname so
only your team can reach it:

- In the Cloudflare dashboard, go to **Zero Trust → Access → Applications**
  and add a self-hosted application for `staging.example.com`.
- Add a policy that allows your email or identity provider group.

This requires no changes inside the cluster — Cloudflare enforces the policy
at the edge before traffic enters the tunnel.

## Tearing it down

```bash
kubectl delete namespace cloudflared
cloudflared tunnel delete actions-manager-staging
```

Then remove the DNS record for `staging.example.com` from the Cloudflare
dashboard (or it will be cleaned up automatically when the tunnel is deleted).
