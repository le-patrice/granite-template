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
        Tunnel -->|HTTP :80| Traefik[Traefik v3 Ingress Quadlet :80]
    end

    subgraph Native_Podman_Pod ["Native Podman Pod (platform.pod Loopback)"]
        Traefik -->|POST /api/v1/telemetry/ingest| GoIngest[Go Telemetry Ingest Quadlet :8001]
        Traefik -->|api.*, /api/*, /docs, /health| App[Litestar / Granian + uvloop Quadlet :8000]
        Traefik -->|app.*, /*| Frontend[Nginx Static SPA Quadlet :8080]
        Worker[SAQ Distributed Worker Quadlet]
        OutboxRelay[PostgreSQL LISTEN/NOTIFY Outbox Relay Daemon]

        App -->|Port 6432| PgBouncer[PgBouncer Quadlet :6432]
        Worker -->|Port 6432| PgBouncer
        PgBouncer -->|Port 5432| DB[(TimescaleDB HA Quadlet :5432)]
        GoIngest -->|Direct Port 5432| DB
        OutboxRelay -->|Dedicated Direct Port 5432| DB
        OutboxRelay -->|Sub-2ms Pub/Sub| VK[(Valkey 8 Quadlet :6379)]
        App -->|Port 6379| VK
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

## 3. Database Connection Architecture & Collision Prevention

To reconcile high-concurrency throughput with stateful database operations and prevent collisions with existing host databases, the platform enforces strict connection tiering and network namespace isolation:

### 3.1 Dual-Connection Strategy (Transaction Pooling vs Direct)
- **Standard Transaction Queries (`DATABASE_URL` on port `6432`):**
  All standard Litestar HTTP requests and transactional CRUD endpoints connect via **PgBouncer** in transaction pooling mode. PgBouncer multiplexes thousands of incoming client requests over a lean pool of 20–25 server connections, preventing PostgreSQL backend process exhaustion.
  ```ini
  DATABASE_URL=postgresql+asyncpg://app_user:secure_dev_password@127.0.0.1:6432/app_db
  ```
- **Stateful Direct Connection (`DIRECT_DATABASE_URL` on port `5432`):**
  Operations that require persistent, session-level database locks or state bypass PgBouncer and connect directly to TimescaleDB:
  1. **PostgreSQL LISTEN/NOTIFY Outbox Relay:** PgBouncer in transaction mode rips connections away upon transaction commit, which silently breaks `LISTEN` channels. The outbox relay daemon connects directly to port `5432` to maintain an unbroken TCP stream.
  2. **Alembic DDL Migrations (`make migrate`):** DDL statements, table alters, advisory locks, and migration transactions execute directly on port `5432`.
  3. **High-Throughput Go Telemetry Ingest:** The Go ingest microservice connects directly to port `5432` for microsecond COPY/batch inserts.
  ```ini
  DIRECT_DATABASE_URL=postgresql+asyncpg://app_user:secure_dev_password@127.0.0.1:5432/app_db
  ```

### 3.2 Production Database Collision Prevention
When deploying to a production host that already runs an existing native PostgreSQL cluster or multiple projects:
- **Network Isolation:** In both development (`config/platform-pod.yaml`) and production Quadlet pods, internal services bind to `127.0.0.1` inside the pod namespace. Internal ports (`5432`, `6432`, `6379`) are completely isolated and never conflict with host PostgreSQL or Redis instances. Direct host access can be mapped if desired via `.env` parameterization.

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

## 5. Systemd Quadlets (Native Podman Pod & Orchestration)

Production containers are deployed as declarative **Systemd Quadlet units** under `~/.config/containers/systemd/` (or `/etc/containers/systemd/` for system-wide services).

### Directory Layout
```
~/.config/containers/systemd/
├── platform.pod                        # Native Pod definition (shared network & cgroups)
├── platform-network.network             # User bridge network with DNS
├── postgres.volume                     # Persistent volume for TimescaleDB data
├── valkey.volume                       # Persistent volume for Valkey data
├── postgres.container                  # TimescaleDB 16 + pgvector container
├── pgbouncer.container                 # PgBouncer transaction pooling gateway
├── valkey.container                    # Valkey 8 in-memory store & Pub/Sub
├── traefik.container                   # Traefik v3 ingress reverse proxy
├── app.container                       # Litestar + Granian (Rust) + uvloop API
├── worker.container                    # SAQ background task worker & outbox sweeper
└── telemetry-ingest.container          # Compiled Go bypass ingest microservice
```

### Sample Native Pod Unit: `platform.pod`
```ini
[Unit]
Description=Enterprise Platform Native Podman Pod
After=network-online.target
Wants=network-online.target

[Pod]
PodName=enterprise-platform
PublishPort=80:80
PublishPort=443:443
PublishPort=8080:8080
Network=platform.network

[Install]
WantedBy=default.target multi-user.target
```

### Sample Container Unit: `app.container`
```ini
[Unit]
Description=Enterprise Platform API Engine (Litestar + Granian + uvloop)
After=platform-pod.service postgres.service valkey.service pgbouncer.service
Wants=platform-pod.service

[Container]
ContainerName=backend
Pod=platform.pod
Image=docker.io/library/enterprise-backend:latest
EnvironmentFile=/etc/platform/app.env
Exec=granian --interface asgi app.main:app --host 127.0.0.1 --port 8000 --loop uvloop
AutoUpdate=registry

[Service]
Restart=always
RestartSec=5s
TimeoutStartSec=120s

[Install]
WantedBy=default.target multi-user.target
```

### Enabling and Starting Production Quadlets
```bash
# 1. Generate and inspect systemd units from Quadlets
systemctl --user daemon-reload

# 2. Verify generated service units
systemctl --user status platform-pod.service

# 3. Enable and start the entire pod mesh
systemctl --user enable --now platform-pod.service
systemctl --user enable --now postgres.service valkey.service pgbouncer.service
systemctl --user enable --now app.service worker.service telemetry-ingest.service traefik.service

# 4. View unified journal logs
journalctl --user -u app.service -f
```
