# Operational Runbook & Disaster Recovery

This runbook provides actionable procedures, disaster recovery workflows, and troubleshooting recipes for operators managing the Enterprise Platform.

---

## 1. Automated Backup Procedures

The automated backup engine ([`scripts/backup.sh`](file:///home/pat/Business/LiteStar/scripts/backup.sh)) generates timestamped, compressed dumps with a configurable retention policy.

### Taking Backups

```bash
# Backup both PostgreSQL database and Valkey cache
make backup

# Backup PostgreSQL database only
make backup-pg

# Preview commands without executing (Dry run)
make backup-dry
```

### Backup Artifact Locations
- **PostgreSQL Dumps:** `backups/postgres/app_db_YYYYMMDD_HHMMSS.dump`
  - Created using `pg_dump -Fc --compress=9` (custom binary format supporting parallel restores and table-level filtering).
- **Valkey Memory Snapshots:** `backups/valkey/valkey_YYYYMMDD_HHMMSS.rdb`
  - Created using atomic `BGSAVE` with completion verification via `LASTSAVE`.

### Automated Retention Pruning
Every execution of `backup.sh` automatically scans `backups/` and deletes files older than `BACKUP_RETENTION_DAYS` (default: 7 days).

---

## 2. Disaster Recovery & Restore Procedures

### Restoring PostgreSQL Database from Dump

> [!CAUTION]
> Restoring a database replaces existing schema and table state. Always ensure active application traffic is paused before initiating a full restore.

```bash
# 1. Identify the target dump file
ls -lt backups/postgres/

# 2. Run restore command
make restore BACKUP_FILE=backups/postgres/app_db_20260820_120000.dump
```

The restore script executes `pg_restore --clean --if-exists --no-owner --jobs=4` to rebuild tables, constraints, and indexes in parallel.

### Restoring Valkey Cache State

```bash
# 1. Stop the valkey service
podman-compose -f config/podman-compose.yml stop valkey-cache

# 2. Copy the snapshot RDB file into the volume
podman cp backups/valkey/valkey_20260820_120000.rdb $(podman ps -aqf "name=valkey_cache"):/data/dump.rdb

# 3. Restart Valkey
podman-compose -f config/podman-compose.yml start valkey-cache
```

---

## 3. Incident Troubleshooting Recipes

### Incident 1: Database Connection Pool Exhaustion

#### Symptoms
- API returns `HTTP 500` or logs `TimeoutError: QueuePool limit of size 20 overflow 10 reached`.
- High request latency on endpoints performing database transactions.

#### Diagnosis
Execute a diagnostic query inside the database container to inspect connection states:

```bash
podman-compose -f config/podman-compose.yml exec postgres-db psql -U app_user -d app_db -c "
SELECT count(*), state, wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = 'app_db'
GROUP BY state, wait_event_type, wait_event;
"
```

To list queries holding locks longer than 30 seconds:
```bash
podman-compose -f config/podman-compose.yml exec postgres-db psql -U app_user -d app_db -c "
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state != 'idle' AND (now() - query_start) > interval '30 seconds';
"
```

#### Mitigation & Resolution
1. **Terminate Blocked Queries:**
   ```bash
   podman-compose -f config/podman-compose.yml exec postgres-db psql -U app_user -d app_db -c "SELECT pg_terminate_backend(<pid>);"
   ```
2. **Tune Pool Settings in Environment:**
   Adjust `.env` parameters:
   ```ini
   DB_POOL_SIZE=30
   DB_MAX_OVERFLOW=15
   ```
3. **Verify PgBouncer Compatibility:** Ensure [`database.py`](file:///home/pat/Business/LiteStar/backend/src/app/core/database.py#L40-L51) maintains `pool_pre_ping=True`, `pool_recycle=1800`, and `statement_cache_size=0`.

---

### Incident 2: Valkey Memory Pressure & Cache Eviction

#### Symptoms
- `OOM command not allowed when used memory > 'maxmemory'` in backend logs.
- Unexpected user session logouts due to evicted revocation keys.

#### Diagnosis
Inspect live Valkey memory usage and fragmentation:

```bash
podman-compose -f config/podman-compose.yml exec valkey-cache valkey-cli info memory
```

Check key count and average TTL across namespaces:
```bash
podman-compose -f config/podman-compose.yml exec valkey-cache valkey-cli info keyspace
```

#### Mitigation & Resolution
1. **Set Max Memory and Eviction Policy:**
   ```bash
   podman-compose -f config/podman-compose.yml exec valkey-cache valkey-cli config set maxmemory 2gb
   podman-compose -f config/podman-compose.yml exec valkey-cache valkey-cli config set maxmemory-policy volatile-lru
   ```
2. **Purge Stale Keys if Necessary:**
   ```bash
   podman-compose -f config/podman-compose.yml exec valkey-cache valkey-cli scan 0 match "transformer:state:*" count 1000
   ```

---

### Incident 3: Alembic Migration Drift

#### Symptoms
- Application startup fails with `alembic.util.exc.CommandError: Can't locate revision identified by 'xxxx'`.
- Duplicate table or constraint errors during `make migrate`.

#### Diagnosis
Inspect the current migration status in the database vs. codebase versions:

```bash
# Check database version
make migrate-show

# Check code version history
make migrate-history
```

#### Resolution
1. If the database is ahead or pointed to an untracked revision, manually stamp the current revision:
   ```bash
   podman-compose -f config/podman-compose.yml exec app alembic -c alembic.ini stamp head
   ```
2. If migrations branched accidentally, create a merge revision:
   ```bash
   podman-compose -f config/podman-compose.yml exec app alembic -c alembic.ini merge heads -m "merge_drift"
   make migrate
   ```
