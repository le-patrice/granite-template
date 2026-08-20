# Operational Runbook & Disaster Recovery Procedures

> **Classification:** Site Reliability Engineering (SRE) & Operational Manual  
> **Status:** Production Standard Baseline

---

## 1. Automated Database Backup & Disaster Recovery

### 1.1 Creating Backups
The platform control plane creates timestamped, compressed (`gzip -9`) PostgreSQL backups:

```bash
# Generate database backup in backups/ directory
make db-backup
```
Output: `backups/db_backup_20260820_143000.sql.gz`

### 1.2 Verifying Backup Archives
```bash
# Verify integrity of all backup archives without extracting to disk
make db-backup-verify
```

### 1.3 Disaster Recovery / Database Restoration
To restore a backup into a database:

```bash
# Step 1: Restore into an isolated validation database first
make db-restore FILE=backups/db_backup_20260820_143000.sql.gz DB=app_db_restore

# Step 2: Direct restore over live database (requires explicit confirmation flag)
make db-restore FILE=backups/db_backup_20260820_143000.sql.gz DB=app_db CONFIRM_LIVE_RESTORE=YES
```

---

## 2. Incident Management & Troubleshooting Recipes

### Recipe 1: Rootless Podman Network Namespace Lockup
**Symptom:** `make down` or container teardown hangs with `resource temporarily unavailable` or `slirp4netns` zombie errors.

**Remediation:**
```bash
# 1. Kill orphaned rootless network namespace processes
podman unshare -- killall -9 slirp4netns pasta 2>/dev/null || true

# 2. Force remove stuck container instances
podman rm -f postgres_db backend worker_app valkey_cache traefik 2>/dev/null || true

# 3. Clean teardown and restart
make down
make up
```

---

### Recipe 2: PgBouncer Connection Pool Exhaustion
**Symptom:** API requests log `psycopg2.OperationalError: server_login_retry: connection limit reached` or elevated latency percentiles on `http_request_duration_seconds`.

**Remediation:**
```bash
# 1. Inspect active PgBouncer pools and client connections
podman exec -u 1000 -it pgbouncer_pool psql -p 6432 -U app_user -d pgbouncer -c "SHOW POOLS;"

# 2. Inspect active client connection counts
podman exec -u 1000 -it pgbouncer_pool psql -p 6432 -U app_user -d pgbouncer -c "SHOW CLIENTS;"

# 3. Temporarily increase pool size in config/podman-compose.yml:
#    DEFAULT_POOL_SIZE=50
#    MAX_CLIENT_CONN=2000
make restart SERVICE=pgbouncer
```

---

### Recipe 3: Dead Letter Queue (DLQ) Quarantined Event Replay
**Symptom:** `make outbox-status` reports `Dead Letters (DLQ) > 0` due to transient upstream network failures.

**Remediation:**
```bash
# 1. Check current outbox status and DLQ count
make outbox-status

# 2. Replay all quarantined events back into PENDING state
make dlq-replay

# 3. Sweep pending events to dispatch to Valkey Pub/Sub
make outbox-relay

# 4. Verify DLQ count has returned to 0
make outbox-status
```

---

### Recipe 4: Resolving Alembic Revision Branch Conflicts
**Symptom:** `make migrate` fails with `Multiple head revisions are present`.

**Remediation:**
```bash
# 1. Inspect migration history inside the container
podman exec -u 10001 -it backend alembic history --verbose

# 2. Merge divergent heads into a single revision
podman exec -u 10001 -it backend alembic merge heads -m "merge_divergent_heads"

# 3. Apply the merged revision
make migrate
```

---

### Recipe 5: Live Log Streaming & Service Debugging
```bash
# Stream API engine logs
make logs SERVICE=app

# Stream SAQ background worker logs
make worker-logs

# Stream Cloudflare Zero Trust Tunnel logs
make tunnel-logs

# Stream database logs
make logs SERVICE=postgres-db
```
