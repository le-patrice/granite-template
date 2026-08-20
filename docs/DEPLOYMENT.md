# Production Deployment Guide (Rootless Podman Quadlets & Edge Ingress)

> **Classification:** Systems Reliability & DevOps Engineering  
> **Status:** Production Standard Baseline  
> **Standard:** Systemd Rootless Quadlets + Traefik v3 + Cloudflare Zero Trust

---

## 1. Production Architecture Overview

In production, the platform runs as a collection of declarative **Systemd Quadlet units** under a non-root service account (`appuser`, UID `10001`). External ingress is managed by **Cloudflare Zero Trust Tunnel** routing directly into **Traefik v3**, while **PgBouncer** pools connections to **TimescaleDB**.

```mermaid
flowchart TD
    subgraph Edge & Security
        CF[Cloudflare Edge Network] -->|Outbound Encrypted Tunnel| Tunnel[cloudflared Quadlet]
        Tunnel -->|HTTP :80| Traefik[Traefik v3 Quadlet :80]
    end

    subgraph Application & Worker
        Traefik -->|api.*, /api/*, /docs| App[Litestar / Granian Quadlet :8000]
        Traefik -->|app.*, /*| Frontend[Nginx Static SPA Quadlet :8080]
        Worker[SAQ Distributed Worker Quadlet]
    end

    subgraph Data & Caching
        App -->|Port 6432| PgBouncer[PgBouncer Quadlet :6432]
        Worker -->|Port 6432| PgBouncer
        PgBouncer -->|Port 5432| DB[(TimescaleDB HA Quadlet :5432)]
        App -->|Port 6379| VK[(Valkey 8 Quadlet :6379)]
        Worker -->|Port 6379| VK
    end
```

---

## 2. Cloudflare Zero Trust Tunnel Setup

Cloudflare Tunnels eliminate the need to open incoming firewall ports (80/443) on your production host.

### Step-by-Step Dashboard Configuration

1. **Create the Tunnel:**
   - In **Cloudflare Zero Trust Dashboard** $\rightarrow$ **Networks** $\rightarrow$ **Tunnels**, click **Create a Tunnel**.
   - Select **Cloudflared** and name it `granite-prod`.
   - Copy the generated **Tunnel Token**.
   - Configure in `/etc/platform/app.env` (or `.env`):
     ```ini
     CLOUDFLARED_TUNNEL_TOKEN=eyJhIjoiY2...
     ```

2. **Configure Public Hostnames (Edge Routing):**
   - On the tunnel's **Public Hostname** page, map your domain names to the local **Traefik** service:
     - **Main Frontend App:**
       - Subdomain: `app` (or root `@`) $\rightarrow$ Domain: `example.com`
       - Service: `HTTP` $\rightarrow$ URL: `traefik:80` (or `http://traefik:80`)
     - **API Service:**
       - Subdomain: `api` $\rightarrow$ Domain: `example.com`
       - Service: `HTTP` $\rightarrow$ URL: `traefik:80`
     - **Interactive Documentation:**
       - Subdomain: `docs` $\rightarrow$ Domain: `example.com`
       - Service: `HTTP` $\rightarrow$ URL: `traefik:80`

3. **Traefik Proxy Header Trust:**
   - Traefik is configured with `insecure: true` on entrypoint forwarded headers to trust Cloudflare proxy headers (`CF-Connecting-IP`, `X-Forwarded-Proto`, `CF-Ray`).

---

## 3. PgBouncer Connection Pooling

PgBouncer operates in **Transaction Pooling Mode** (`POOL_MODE=transaction`) to support thousands of concurrent client requests over a lean pool of 25–50 physical PostgreSQL connections.

### PgBouncer Configuration Parameters
- **Gateway Port:** `6432`
- **Max Client Connections:** `1000`
- **Default Pool Size:** `25`
- **Auth Type:** `scram-sha-256`
- **Connection URL:** `postgresql+asyncpg://app_user:password@pgbouncer:6432/app_db`

> [!NOTE]
> Database migrations (`make migrate`) and DDL scripts always connect directly to PostgreSQL on port `5432` to ensure full session-level DDL lock support.

---

## 4. Production Multi-Stage Frontend Build

In production, the frontend is built into static HTML/JS/CSS assets and served via an unprivileged Nginx container (`frontend/Containerfile`):

```dockerfile
# Stage 1: Build static bundle
FROM docker.io/library/node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve with unprivileged Nginx
FROM docker.io/nginxinc/nginx-unprivileged:alpine AS runner
USER nginx
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
```

---

## 5. Systemd Quadlets (Declarative Rootless Units)

Production containers are deployed as user systemd units under `~/.config/containers/systemd/`.

### Directory Layout
```
~/.config/containers/systemd/
├── platform-network.network
├── postgres-volume.volume
├── valkey-volume.volume
├── postgres.container
├── valkey.container
├── pgbouncer.container
├── app.container
├── worker.container
├── frontend.container
└── traefik.container
```

### Sample Unit: `app.container`
```ini
[Unit]
Description=LiteForge API Engine (Granian Rust ASGI)
After=network-online.target postgres.service valkey.service pgbouncer.service
Requires=platform-network-network.service

[Container]
Image=registry.example.com/granite/backend:latest
ContainerName=api_app
EnvironmentFile=/etc/platform/app.env
Network=platform-network.network
ExposeHostPort=8000:8000
AutoUpdate=registry

[Service]
Restart=always
RestartSec=5s
TimeoutStartSec=120s

[Install]
WantedBy=default.target
```

### Enabling and Starting Production Quadlets
```bash
# Reload systemd user daemon to recognize new Quadlet units
systemctl --user daemon-reload

# Enable and start the full production mesh
systemctl --user enable --now platform-network-network.service
systemctl --user enable --now postgres.service valkey.service pgbouncer.service
systemctl --user enable --now app.service worker.service frontend.service traefik.service

# Enable automated registry update timer
systemctl --user enable --now podman-auto-update.timer
```
