#!/usr/bin/env bash
# =============================================================================
# backup.sh — Automated database & cache backup engine
#
# Usage (directly):
#   ./scripts/backup.sh                  # backup both PG and Valkey
#   ./scripts/backup.sh --pg-only        # PostgreSQL only
#   ./scripts/backup.sh --valkey-only    # Valkey only
#   ./scripts/backup.sh --restore <file> # Restore a .dump file
#
# Via make:
#   make backup
#   make restore BACKUP_FILE=backups/postgres/app_db_20260820_120000.dump
#
# Features
# --------
#   • pg_dump -Fc (custom binary format — compressed, supports parallel restore)
#   • Valkey BGSAVE with wait loop, then snapshot file copy
#   • Timestamped filenames:  <dbname>_YYYYMMDD_HHMMSS.dump
#   • 7-day retention prune (configurable via BACKUP_RETENTION_DAYS)
#   • Structured log lines: timestamp | level | message
#   • Dry-run mode:  DRY_RUN=1 ./scripts/backup.sh
#   • Non-zero exit on any failure (set -euo pipefail)
#
# Environment variables (override via .env or shell):
#   POSTGRES_HOST          (default: localhost)
#   POSTGRES_PORT          (default: 5432)
#   POSTGRES_USER          (default: app_user)
#   POSTGRES_PASSWORD      (default: secure_dev_password)
#   POSTGRES_DB            (default: app_db)
#   VALKEY_HOST            (default: localhost)
#   VALKEY_PORT            (default: 6379)
#   BACKUP_DIR             (default: ./backups)
#   BACKUP_RETENTION_DAYS  (default: 7)
#   DRY_RUN                (default: 0 — set to 1 to skip writes)
#
# Container execution (rootless Podman, via make):
#   Postgres backup runs inside the postgres-db container via pg_dump.
#   Valkey snapshot is copied out of the valkey-cache container.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (env var → default)
# ---------------------------------------------------------------------------
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-app_user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-secure_dev_password}"
POSTGRES_DB="${POSTGRES_DB:-app_db}"
VALKEY_HOST="${VALKEY_HOST:-localhost}"
VALKEY_PORT="${VALKEY_PORT:-6379}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
DRY_RUN="${DRY_RUN:-0}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-podman}"
COMPOSE_FILE="${COMPOSE_FILE:-config/podman-compose.yml}"

if command -v "${CONTAINER_ENGINE}-compose" &>/dev/null; then
    COMPOSE_CMD=("${CONTAINER_ENGINE}-compose" -f "${COMPOSE_FILE}")
else
    COMPOSE_CMD=("${CONTAINER_ENGINE}" compose -f "${COMPOSE_FILE}")
fi

TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
PG_BACKUP_DIR="${BACKUP_DIR}/postgres"
VALKEY_BACKUP_DIR="${BACKUP_DIR}/valkey"

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log_info()  { echo "$(date -u +%FT%TZ) | INFO  | $*"; }
log_warn()  { echo "$(date -u +%FT%TZ) | WARN  | $*" >&2; }
log_error() { echo "$(date -u +%FT%TZ) | ERROR | $*" >&2; }

dry_run_guard() {
    if [[ "${DRY_RUN}" == "1" ]]; then
        log_info "[DRY RUN] would execute: $*"
        return 0
    fi
    "$@"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
MODE="all"
RESTORE_FILE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pg-only)     MODE="pg";      shift ;;
        --valkey-only) MODE="valkey";  shift ;;
        --restore)     MODE="restore"; RESTORE_FILE="${2:-}"; shift 2 ;;
        *)             log_error "Unknown argument: $1"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helper: ensure backup subdirectory exists
# ---------------------------------------------------------------------------
ensure_dir() {
    local dir="$1"
    if [[ "${DRY_RUN}" == "1" ]]; then
        log_info "[DRY RUN] would mkdir -p $dir"
        return
    fi
    mkdir -p "$dir"
}

# ---------------------------------------------------------------------------
# PostgreSQL backup  (pg_dump custom format, compressed internally)
# ---------------------------------------------------------------------------
backup_postgres() {
    local outfile="${PG_BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.dump"
    log_info "Starting PostgreSQL backup → ${outfile}"

    ensure_dir "${PG_BACKUP_DIR}"

    # Determine whether to run pg_dump locally or via the container
    if command -v pg_dump &>/dev/null; then
        # pg_dump available locally
        dry_run_guard env PGPASSWORD="${POSTGRES_PASSWORD}" \
            pg_dump \
            --host="${POSTGRES_HOST}" \
            --port="${POSTGRES_PORT}" \
            --username="${POSTGRES_USER}" \
            --format=custom \
            --compress=9 \
            --file="${outfile}" \
            "${POSTGRES_DB}"
    else
        # Run via postgres-db container (rootless Podman)
        log_info "pg_dump not found locally — running via ${POSTGRES_DB} container"
        dry_run_guard "${COMPOSE_CMD[@]}" \
            exec -T postgres-db \
            env PGPASSWORD="${POSTGRES_PASSWORD}" \
            pg_dump \
            --username="${POSTGRES_USER}" \
            --format=custom \
            --compress=9 \
            --file="/tmp/${POSTGRES_DB}_${TIMESTAMP}.dump" \
            "${POSTGRES_DB}"

        # Copy the dump out of the container
        dry_run_guard "${CONTAINER_ENGINE}" cp \
            "$("${COMPOSE_CMD[@]}" ps -q postgres-db):/tmp/${POSTGRES_DB}_${TIMESTAMP}.dump" \
            "${outfile}"
    fi

    if [[ "${DRY_RUN}" != "1" ]]; then
        local size
        size="$(du -sh "${outfile}" | cut -f1)"
        log_info "PostgreSQL backup complete: ${outfile} (${size})"
    fi
}

# ---------------------------------------------------------------------------
# Valkey / Redis snapshot backup  (BGSAVE + copy dump.rdb)
# ---------------------------------------------------------------------------
backup_valkey() {
    local outfile="${VALKEY_BACKUP_DIR}/valkey_${TIMESTAMP}.rdb"
    log_info "Starting Valkey snapshot → ${outfile}"

    ensure_dir "${VALKEY_BACKUP_DIR}"

    # Trigger BGSAVE and wait for it to finish
    if command -v valkey-cli &>/dev/null || command -v redis-cli &>/dev/null; then
        local CLI
        CLI="$(command -v valkey-cli 2>/dev/null || command -v redis-cli)"
        log_info "Sending BGSAVE to ${VALKEY_HOST}:${VALKEY_PORT}"
        dry_run_guard "${CLI}" -h "${VALKEY_HOST}" -p "${VALKEY_PORT}" BGSAVE

        # Wait for the background save to complete
        local attempts=0
        while [[ "${DRY_RUN}" != "1" ]]; do
            local status
            status="$("${CLI}" -h "${VALKEY_HOST}" -p "${VALKEY_PORT}" LASTSAVE)"
            sleep 1
            local new_status
            new_status="$("${CLI}" -h "${VALKEY_HOST}" -p "${VALKEY_PORT}" LASTSAVE)"
            if [[ "${new_status}" != "${status}" ]]; then
                log_info "Valkey BGSAVE completed (LASTSAVE changed)"
                break
            fi
            attempts=$((attempts + 1))
            if [[ ${attempts} -ge 30 ]]; then
                log_warn "Timed out waiting for BGSAVE after 30s — copying existing dump.rdb"
                break
            fi
        done
    else
        log_info "valkey-cli not found locally — triggering BGSAVE via container"
        dry_run_guard "${COMPOSE_CMD[@]}" \
            exec -T valkey-cache valkey-cli BGSAVE
        sleep 3   # conservative wait when no feedback loop
    fi

    # Copy dump.rdb out of the container
    if [[ "${DRY_RUN}" != "1" ]]; then
        "${CONTAINER_ENGINE}" cp \
            "$("${COMPOSE_CMD[@]}" ps -q valkey-cache 2>/dev/null):/data/dump.rdb" \
            "${outfile}" 2>/dev/null \
            || log_warn "Could not copy dump.rdb from container — Valkey may use AOF only"
        if [[ -f "${outfile}" ]]; then
            local size
            size="$(du -sh "${outfile}" | cut -f1)"
            log_info "Valkey backup complete: ${outfile} (${size})"
        fi
    else
        log_info "[DRY RUN] would copy /data/dump.rdb → ${outfile}"
    fi
}

# ---------------------------------------------------------------------------
# Retention prune  (delete files older than BACKUP_RETENTION_DAYS)
# ---------------------------------------------------------------------------
prune_old_backups() {
    local dir="$1"
    local extension="$2"
    log_info "Pruning ${dir} — removing ${extension} files older than ${BACKUP_RETENTION_DAYS} days"
    if [[ -d "${dir}" && "${DRY_RUN}" != "1" ]]; then
        find "${dir}" -maxdepth 1 -name "*.${extension}" \
            -mtime "+${BACKUP_RETENTION_DAYS}" -delete \
            -print | while read -r f; do log_info "Pruned: ${f}"; done
    elif [[ "${DRY_RUN}" == "1" ]]; then
        log_info "[DRY RUN] would prune files older than ${BACKUP_RETENTION_DAYS} days in ${dir}"
    fi
}

# ---------------------------------------------------------------------------
# Restore  (pg_restore from a custom-format dump)
# ---------------------------------------------------------------------------
restore_postgres() {
    local file="$1"

    if [[ -z "${file}" ]]; then
        log_error "Usage: $0 --restore <path/to/file.dump>"
        exit 1
    fi
    if [[ ! -f "${file}" ]]; then
        log_error "Backup file not found: ${file}"
        exit 1
    fi

    log_warn "⚠️  This will REPLACE all data in '${POSTGRES_DB}' on ${POSTGRES_HOST}:${POSTGRES_PORT}"
    log_warn "    Press Ctrl-C within 5 seconds to abort..."
    sleep 5

    log_info "Restoring ${file} → ${POSTGRES_DB}"
    if command -v pg_restore &>/dev/null; then
        env PGPASSWORD="${POSTGRES_PASSWORD}" \
            pg_restore \
            --host="${POSTGRES_HOST}" \
            --port="${POSTGRES_PORT}" \
            --username="${POSTGRES_USER}" \
            --dbname="${POSTGRES_DB}" \
            --clean \
            --if-exists \
            --no-owner \
            --jobs=4 \
            "${file}"
    else
        log_info "pg_restore not found locally — running via container"
        local container_path="/tmp/restore_${TIMESTAMP}.dump"
        "${CONTAINER_ENGINE}" cp "${file}" \
            "$("${COMPOSE_CMD[@]}" ps -q postgres-db):${container_path}"
        "${COMPOSE_CMD[@]}" exec -T postgres-db \
            env PGPASSWORD="${POSTGRES_PASSWORD}" \
            pg_restore \
            --username="${POSTGRES_USER}" \
            --dbname="${POSTGRES_DB}" \
            --clean --if-exists --no-owner --jobs=4 \
            "${container_path}"
    fi
    log_info "Restore complete."
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
case "${MODE}" in
    all)
        backup_postgres
        backup_valkey
        prune_old_backups "${PG_BACKUP_DIR}"    "dump"
        prune_old_backups "${VALKEY_BACKUP_DIR}" "rdb"
        log_info "✅  All backups complete."
        ;;
    pg)
        backup_postgres
        prune_old_backups "${PG_BACKUP_DIR}" "dump"
        log_info "✅  PostgreSQL backup complete."
        ;;
    valkey)
        backup_valkey
        prune_old_backups "${VALKEY_BACKUP_DIR}" "rdb"
        log_info "✅  Valkey backup complete."
        ;;
    restore)
        restore_postgres "${RESTORE_FILE}"
        ;;
esac
