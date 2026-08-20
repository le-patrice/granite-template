# Production Deployment & Infrastructure Guide

This document outlines the production architecture, security hardening, and deployment procedures for the Enterprise Platform using **Systemd Quadlets** and **Rootless Podman**.

---

## 1. Production Architecture Overview

In production, container orchestration is offloaded from heavy container daemons (like Docker daemon) directly to Linux **Systemd** via Podman Quadlets.

```
                          +-----------------------------------+
                          |      Host Systemd (Init / PID 1)  |
                          +-----------------------------------+
                                            |
                         User-Session Systemd Manager (--user)
                                            |
         +----------------------------------+----------------------------------+
         |                                  |                                  |
         v                                  v                                  v
+-----------------------+        +-----------------------+        +-----------------------+
| app.service           |        | postgres.service      |        | valkey.service        |
| (Quadlet: app.container)      | (postgres.container)  |        | (valkey.container)    |
| - Litestar (Granian)  |        | - TimescaleDB HA      |        | - Valkey 8 Cache      |
| - Port: 8000          |        | - Port: 5432          |        | - Port: 6379          |
| - AutoUpdate=registry |        | - AutoUpdate=registry |        | - AutoUpdate=registry |
+-----------------------+        +-----------------------+        +-----------------------+
         |                                  |                                  |
         +----------------------------------+----------------------------------+
                                            |
                         platform.network (platform-network bridge)
                                            |
                         postgres.volume (postgres-data storage)
```

---

## 2. Systemd Quadlets Configuration

Quadlet definitions live in [`deployments/prod/quadlets/`](file:///home/pat/Business/LiteStar/deployments/prod/quadlets/). When copied to `~/.config/containers/systemd/`, Systemd automatically translates them into native `.service` files.

### A. Shared Network ([`platform.network`](file:///home/pat/Business/LiteStar/deployments/prod/quadlets/platform.network))
```ini
[Network]
NetworkName=platform-network
```

### B. Persistent Volume ([`postgres.volume`](file:///home/pat/Business/LiteStar/deployments/prod/quadlets/postgres.volume))
```ini
[Volume]
VolumeName=postgres-data
```

### C. PostgreSQL Container ([`postgres.container`](file:///home/pat/Business/LiteStar/deployments/prod/quadlets/postgres.container))
```ini
[Unit]
Description=TimescaleDB PostgreSQL Database
After=network-online.target local-fs.target

[Container]
ContainerName=postgres-db
Image=docker.io/timescale/timescaledb-ha:pg16
Network=platform.network
Volume=postgres.volume:/var/lib/postgresql/data:Z
Environment=POSTGRES_USER=app_user
Environment=POSTGRES_PASSWORD=secure_dev_password
Environment=POSTGRES_DB=app_db
PublishPort=5432:5432
AutoUpdate=registry

[Service]
Restart=always
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target default.target
```

### D. Valkey Container ([`valkey.container`](file:///home/pat/Business/LiteStar/deployments/prod/quadlets/valkey.container))
```ini
[Unit]
Description=Valkey High-Performance In-Memory Store
After=network-online.target local-fs.target

[Container]
ContainerName=valkey-cache
Image=docker.io/valkey/valkey:8-alpine
Network=platform.network
PublishPort=6379:6379
AutoUpdate=registry

[Service]
Restart=always
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target default.target
```

### E. Application Runtime ([`app.container`](file:///home/pat/Business/LiteStar/deployments/prod/quadlets/app.container))
```ini
[Unit]
Description=Litestar Enterprise API
After=postgres.service valkey.service

[Container]
ContainerName=api-backend
Image=localhost/enterprise-platform:latest
PublishPort=8000:8000
Network=platform.network
EnvironmentFile=/etc/platform/app.env
Exec=granian --interface asgi app:app --host 0.0.0.0 --port 8000 --workers 4 --http auto --backlog 1024
AutoUpdate=registry

[Service]
Restart=always
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target default.target
```

---

## 3. Deploying Quadlets to Production

### Step 1: Install Quadlet Definitions
```bash
# Ensure target systemd user directory exists
mkdir -p ~/.config/containers/systemd/

# Copy quadlet files
cp deployments/prod/quadlets/* ~/.config/containers/systemd/

# Tell systemd to compile quadlets into unit services
systemctl --user daemon-reload
```

### Step 2: Configure Secrets & Environment
```bash
sudo mkdir -p /etc/platform
sudo tee /etc/platform/app.env > /dev/null << 'EOF'
ENVIRONMENT=production
DEBUG=False
SECRET_KEY=<generate-64-character-hex-secret>
DATABASE_URL=postgresql+asyncpg://app_user:secure_prod_password@postgres-db:5432/app_db
VALKEY_HOST=valkey-cache
VALKEY_PORT=6379
EOF
sudo chmod 600 /etc/platform/app.env
```

### Step 3: Enable and Start Services
```bash
# Enable and start services across reboots
systemctl --user enable --now platform-network-network.service
systemctl --user enable --now postgres-volume-volume.service
systemctl --user enable --now postgres.service
systemctl --user enable --now valkey.service
systemctl --user enable --now app.service

# Verify status
systemctl --user status app.service
```

---

## 4. Automated Updates & Rollbacks

All container units configure `AutoUpdate=registry`.

### Automatic Update Cycle
Podman includes a native timer service for automated registry synchronization:
```bash
# Enable the standard Podman auto-update timer
systemctl --user enable --now podman-auto-update.timer

# Or trigger a manual update run:
podman auto-update
```

When an updated image tag is published to your OCI container registry, Podman pulls the new layers, gracefully shuts down the running systemd unit, starts the new image, and validates the health check. If the container fails to start, Podman triggers an automatic rollback to the previously working image.

---

## 5. Security & Isolation Hardening

1. **Non-Root Execution (UID 10001):** The [`Containerfile`](file:///home/pat/Business/LiteStar/config/Containerfile#L14-L30) drops privileges to `appuser` (UID `10001`). Even if the application runtime were compromised, an attacker has zero access to the host kernel or root privileges.
2. **SELinux Volume Relabeling:**
   - `:z` (Shared relabeling): Used for read-only mounts shared across multiple containers (e.g. source code volumes).
   - `:Z` (Private relabeling): Used for sensitive exclusive volumes (e.g. `pg_data`), ensuring only the database process can read or write raw database files.
3. **Traefik Edge Ingress:** Exposes only port 80/443 to the internet. Internal service ports (8000, 5432, 6379) remain bound only to the private bridge network.

---

## 6. Cloudflare Zero Trust Tunnel Edge Ingress

The platform includes first-class integration with **Cloudflare Zero Trust Tunnel** (`cloudflared`). In this architecture, no public firewall ports (80/443) need to be open on your host. Instead, an outbound encrypted tunnel connects your local Traefik instance directly to Cloudflare's global edge network.

### Architecture Topology

```mermaid
flowchart LR
    User[End User] -->|HTTPS| CFEdge[Cloudflare Global Edge]
    CFEdge -->|Encrypted Tunnel| Tunnel[cloudflared container]
    Tunnel -->|HTTP :80| Traefik[Traefik v3 Gateway]
    Traefik -->|api.*, /api/*, /docs| App[Litestar Backend :8000]
    Traefik -->|app.*, /*| Frontend[Frontend SPA :5173 / :80]
```

### Setup Guide: Cloudflare Zero Trust Dashboard

1. **Create the Tunnel:**
   - Log into the **Cloudflare Zero Trust Dashboard** $\rightarrow$ **Networks** $\rightarrow$ **Tunnels**.
   - Click **Add a Tunnel**, choose **Cloudflared**, and name it `granite-prod` (or your project name).
   - Under the install instructions, copy the **Tunnel Token** value.
   - Paste the token into your `.env` file:
     ```ini
     CLOUDFLARED_TUNNEL_TOKEN=eyJhIjoiY2...
     ```

2. **Configure Public Hostnames (Edge Routing):**
   - On the tunnel details page, navigate to the **Public Hostname** tab and click **Add a public hostname**.
   - Map your desired subdomains directly to the internal **Traefik** reverse proxy:
     - **Main Application:**
       - Subdomain / Domain: `app.example.com` (or root `example.com`)
       - Service Type: `HTTP`
       - URL: `traefik:80` (or `http://traefik:80`)
     - **API Service:**
       - Subdomain: `api.example.com`
       - Service Type: `HTTP`
       - URL: `traefik:80`
     - **Interactive API Documentation:**
       - Subdomain: `docs.example.com`
       - Service Type: `HTTP`
       - URL: `traefik:80`

3. **Traefik Fine-Grained Subdomain Routing:**
   - Traefik inspects the incoming `Host` and `CF-Connecting-IP` headers and routes:
     - `api.example.com` or `/api/*` $\rightarrow$ `app:8000`
     - `docs.example.com` or `/docs`, `/scalar`, `/swagger` $\rightarrow$ `app:8000`
     - `app.example.com` or `/*` $\rightarrow$ `frontend:5173` (or Nginx in production)

4. **Lifecycle & Status Management:**
   ```bash
   # Check tunnel connection status
   make tunnel-status

   # Tail live logs from cloudflared
   make tunnel-logs

   # Restart the tunnel container
   make tunnel-restart
   ```

