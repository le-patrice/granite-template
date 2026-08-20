# ADR 0002: Rootless Podman and Systemd Quadlets for Container Orchestration

- **Status:** Accepted
- **Date:** 2026-08-20
- **Deciders:** Principal DevOps Architect, Infrastructure Team

---

## Context

Production deployments require secure, deterministic, and self-healing container execution. Traditional container orchestrators present specific operational trade-offs for edge and single-node cluster deployments:
1. **Docker Daemon Vulnerability:** Docker runs a privileged background daemon (`dockerd`) with root permissions, creating a single point of failure and potential privilege escalation vulnerability.
2. **Kubernetes Complexity:** Full Kubernetes clusters introduce excessive operational complexity, resource overhead, and control-plane maintenance for edge or dedicated compute deployments.
3. **Init System Integration:** Containers need first-class integration with standard Linux service managers (`systemd`) for automated restarts, dependency ordering, and logging.

---

## Decision

We chose **Rootless Podman** paired with **Systemd Quadlets** as the primary container orchestration engine for development and production environments.

### Key Architectural Drivers

1. **Daemonless Architecture:** Podman operates without a centralized background daemon; containers run as direct child processes of the systemd user session.
2. **Rootless Security Sandbox:** Application containers execute under non-privileged user namespaces (`UID 10001`), preventing host privilege escalation even in the event of a container breakout.
3. **Declarative Systemd Units (Quadlets):** Developers author simple declarative `.container`, `.network`, and `.volume` files that Systemd dynamically compiles into native services on boot.
4. **Native Auto-Update:** `AutoUpdate=registry` allows Systemd timers to automatically pull new OCI images, perform healthcheck validation, and roll back upon startup failure.

---

## Consequences

### Positive
- **Enhanced Security Posture:** Zero root daemon exposure and complete SELinux label isolation (`:z` and `:Z`).
- **Native OS Observability:** Standard systemd tooling (`journalctl`, `systemctl --user status`) manages container lifecycles directly without custom abstraction layers.
- **Automated Rollbacks:** Built-in resilience against corrupted OCI image deployments.

### Negative / Trade-offs
- **Rootless Port Binding:** Binding to privileged ports (< 1024) requires reverse proxy forwarding (via Traefik) or configuring `net.ipv4.ip_unprivileged_port_start`.
- **User Session Linger:** Requires enabling `loginctl enable-linger <user>` so user systemd services remain active when no interactive session is logged in.
