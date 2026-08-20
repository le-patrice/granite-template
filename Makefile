# ==============================================================================
# LiteForge / Enterprise Platform - Unified Control Plane
# ==============================================================================

SHELL := /bin/bash
export PODMAN_COMPOSE_WARNING_LOGS := 0
.DEFAULT_GOAL := help

# ------------------------------------------------------------------------------
# Terminal Styling
# ------------------------------------------------------------------------------
BLUE   := \033[0;34m
GREEN  := \033[0;32m
YELLOW := \033[1;33m
RED    := \033[0;31m
NC     := \033[0m # No Color

# ------------------------------------------------------------------------------
# Configurable Runtime Variables (Weak Assignments)
# ------------------------------------------------------------------------------
CONTAINER_ENGINE ?= podman
COMPOSE_FILE     ?= -f config/podman-compose.yml
ENV_FILE         ?= --env-file .env

# Socket context for rootless Podman execution
export CONTAINER_HOST ?= unix:///run/user/$(shell id -u)/podman/podman.sock

# Execution wrappers
COMPOSE_BASE := $(CONTAINER_ENGINE) compose $(COMPOSE_FILE)
EXEC_APP     := $(COMPOSE_BASE) exec -T app 2>/dev/null || $(CONTAINER_ENGINE) exec -u 10001 -i backend
EXEC_DB      := $(COMPOSE_BASE) exec -T postgres-db 2>/dev/null || $(CONTAINER_ENGINE) exec -u 1000 -i postgres_db

# Command argument overrides
SERVICE ?= app
TEST    ?= tests
MSG     ?=
FILE    ?=
DB      ?=
CONFIRM_LIVE_RESTORE ?= NO

# ------------------------------------------------------------------------------
# Help & Documentation
# ------------------------------------------------------------------------------
.PHONY: help
help: ## Show this interactive help banner
	@echo -e ""
	@echo -e "$(BLUE)╔══════════════════════════════════════════════════════════════════╗$(NC)"
	@echo -e "$(BLUE)║   LiteForge Control Plane — Podman/Docker Automation Engine      ║$(NC)"
	@echo -e "$(BLUE)╚══════════════════════════════════════════════════════════════════╝$(NC)"
	@echo -e ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-24s$(NC) %s\n", $$1, $$2}'
	@echo -e ""
	@echo -e "$(YELLOW)Common Workflows:$(NC)"
	@echo -e "  make up                           # Boot full container mesh in background (Podman default)"
	@echo -e "  make up-dev                       # Boot container mesh with forced image rebuild"
	@echo -e "  make logs SERVICE=app             # Tail live logs for a specific service"
	@echo -e "  make worker                       # Start or ensure SAQ background worker is running"
	@echo -e "  make worker-logs                  # Tail live logs from SAQ background worker"
	@echo -e "  make metrics                      # Inspect Prometheus scrapable metrics endpoint"
	@echo -e "  make outbox-relay                 # Trigger a sweep of pending transactional outbox events"
	@echo -e "  make dlq-replay                   # Replay quarantined Dead Letter Queue events"
	@echo -e "  make tunnel-status                # Check Cloudflare Zero Trust Tunnel container status"
	@echo -e "  make tunnel-logs                  # Tail live logs from Cloudflare Tunnel container"
	@echo -e "  make migrate                      # Run Alembic migrations inside app container"
	@echo -e "  make seed                         # Seed initial superuser into database"
	@echo -e "  make test                         # Run isolated pytest suite inside container"
	@echo -e "  make db-backup                    # Dump timestamped compressed PostgreSQL backup"
	@echo -e "  CONTAINER_ENGINE=docker make up   # Override runtime engine to Docker on demand"
	@echo -e ""

# ------------------------------------------------------------------------------
# Stack Lifecycle Management
# ------------------------------------------------------------------------------
.PHONY: up
up: ## Start all core mesh services (App, Worker, PostgreSQL, Valkey, Traefik) in background
	@echo -e "$(BLUE)Starting services with $(CONTAINER_ENGINE)...$(NC)"
	@$(COMPOSE_BASE) up -d
	@echo -e "$(GREEN)✅ Stack running. API available at http://localhost:8000$(NC)"

.PHONY: up-dev
up-dev: ## Rebuild and start container mesh in background with live volume mounts
	@echo -e "$(BLUE)Building and starting development stack...$(NC)"
	@$(COMPOSE_BASE) up -d --build
	@echo -e "$(GREEN)✅ Development stack started$(NC)"

.PHONY: worker
worker: ## Start or ensure background task worker container is running
	@echo -e "$(BLUE)Starting SAQ background worker container...$(NC)"
	@$(COMPOSE_BASE) up -d worker
	@echo -e "$(GREEN)✅ SAQ worker container is active$(NC)"

.PHONY: worker-logs
worker-logs: ## Tail live logs from SAQ distributed background task worker
	@echo -e "$(BLUE)Tailing SAQ background worker logs...$(NC)"
	@$(COMPOSE_BASE) logs -f --tail=200 worker

.PHONY: down
down: ## Stop and remove stack containers (preserves database volumes)
	@echo -e "$(YELLOW)Stopping stack containers...$(NC)"
	@$(COMPOSE_BASE) stop -t 5 2>/dev/null || true
	@$(COMPOSE_BASE) down
	@echo -e "$(GREEN)✅ Containers stopped cleanly (Database volumes preserved)$(NC)"

.PHONY: down-volumes
down-volumes: ## Stop stack and PERMANENTLY DESTROY all database data volumes
	@echo -e "$(RED)⚠️  WARNING: Deleting all persistent database and cache volumes!$(NC)"
	@$(COMPOSE_BASE) down -v
	@echo -e "$(GREEN)✅ Containers and persistent volumes wiped clean$(NC)"

.PHONY: down-check
down-check: ## Stop project and verify no lingering containers remain on host
	@$(COMPOSE_BASE) down
	@echo -e "$(YELLOW)Checking for remaining project containers...$(NC)"
	@$(CONTAINER_ENGINE) ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | grep -E 'app|worker|postgres|valkey|traefik|pgbouncer' || echo -e "$(GREEN)✅ No matching project containers running$(NC)"

.PHONY: stop
stop: ## Stop all services or a specific target (e.g., make stop SERVICE=app)
	@$(COMPOSE_BASE) stop $(SERVICE)

.PHONY: start
start: ## Start stopped services (e.g., make start SERVICE=app)
	@$(COMPOSE_BASE) start $(SERVICE)

.PHONY: restart
restart: ## Restart services (e.g., make restart SERVICE=app)
	@echo -e "$(YELLOW)Restarting service: $(SERVICE)...$(NC)"
	@$(COMPOSE_BASE) restart $(SERVICE)
	@echo -e "$(GREEN)✅ Restart complete$(NC)"

# ------------------------------------------------------------------------------
# Inspection & Observability
# ------------------------------------------------------------------------------
.PHONY: ps
ps: ## List status of all mesh containers
	@$(COMPOSE_BASE) ps

.PHONY: logs
logs: ## Tail container logs (e.g., make logs SERVICE=app)
	@$(COMPOSE_BASE) logs -f --tail=200 $(SERVICE)

.PHONY: health
health: ## Perform HTTP health check against local Litestar instance
	@echo -e "$(YELLOW)Checking backend health...$(NC)"
	@curl -fsS http://localhost:8000/health/ready >/dev/null && echo -e "$(GREEN)✅ Backend is healthy & ready$(NC)" || echo -e "$(RED)❌ Backend not ready$(NC)"

.PHONY: metrics
metrics: ## Fetch Prometheus metrics from /metrics endpoint
	@curl -s http://localhost:8000/metrics

.PHONY: stats
stats: ## Stream real-time resource utilization (CPU, Memory, I/O)
	@$(CONTAINER_ENGINE) stats --no-stream

.PHONY: shell
shell: ## Open an interactive bash shell inside container (e.g., make shell SERVICE=app)
	@$(COMPOSE_BASE) exec $(SERVICE) bash

# ------------------------------------------------------------------------------
# Container Image Builds
# ------------------------------------------------------------------------------
.PHONY: build
build: ## Build standard container images defined in Compose
	@echo -e "$(BLUE)Building images with $(CONTAINER_ENGINE)...$(NC)"
	@$(COMPOSE_BASE) build

.PHONY: build-backend
build-backend: ## Build only the backend container image from root context
	@echo -e "$(BLUE)Building backend image (config/Containerfile)...$(NC)"
	@$(CONTAINER_ENGINE) build -t api-backend -f config/Containerfile .
	@echo -e "$(GREEN)✅ Backend build finished$(NC)"

.PHONY: build-backend-clean
build-backend-clean: ## Build backend container with no cache
	@$(CONTAINER_ENGINE) build --no-cache -t api-backend -f config/Containerfile .

.PHONY: pull
pull: ## Pull latest base images (TimescaleDB, Valkey) from registries
	@$(COMPOSE_BASE) pull

# ------------------------------------------------------------------------------
# Database & Migration Operations
# ------------------------------------------------------------------------------
.PHONY: migrate
migrate: ## Apply all pending Alembic migrations inside container
	@echo -e "$(YELLOW)Applying database migrations...$(NC)"
	@$(EXEC_APP) alembic upgrade head
	@echo -e "$(GREEN)✅ Migrations up to date$(NC)"

.PHONY: migrate-down
migrate-down: ## Rollback one Alembic migration revision (-1)
	@echo -e "$(YELLOW)Rolling back one migration...$(NC)"
	@$(EXEC_APP) alembic downgrade -1
	@echo -e "$(GREEN)✅ Migration rollback complete$(NC)"

.PHONY: migration-create
migration-create: ## Generate new autodetected migration (e.g., make migration-create MSG="add_asset_table")
	@if [ -z "$(MSG)" ]; then \
		echo -e "$(RED)❌ MSG parameter required.$(NC) Usage: make migration-create MSG=\"description\""; \
		exit 1; \
	fi
	@$(EXEC_APP) alembic revision --autogenerate -m "$(MSG)"
	@echo -e "$(GREEN)✅ Migration script created in backend/alembic/versions/$(NC)"

.PHONY: migrate-history
migrate-history: ## Display full Alembic migration timeline and revision heads
	@$(EXEC_APP) alembic history --verbose

.PHONY: seed
seed: ## Seed initial platform superuser from environment settings
	@echo -e "$(YELLOW)Seeding superuser account...$(NC)"
	@$(EXEC_APP) python scripts/seed_initial_data.py
	@echo -e "$(GREEN)✅ Seeding script finished$(NC)"

.PHONY: db-shell
db-shell: ## Open direct interactive psql console on running PostgreSQL container
	@$(EXEC_DB) psql -U $$(grep POSTGRES_USER .env | cut -d= -f2) -d $$(grep POSTGRES_DB .env | cut -d= -f2)

# ------------------------------------------------------------------------------
# Transactional Outbox & DLQ Operations
# ------------------------------------------------------------------------------
.PHONY: outbox-relay
outbox-relay: ## Perform a manual sweep to relay pending outbox events to message broker
	@echo -e "$(BLUE)Sweeping pending outbox events...$(NC)"
	@$(EXEC_APP) python scripts/outbox_cli.py sweep

.PHONY: dlq-replay
dlq-replay: ## Replay quarantined events from Dead Letter Queue back to Outbox
	@echo -e "$(YELLOW)Replaying Dead Letter Queue (DLQ) events...$(NC)"
	@$(EXEC_APP) python scripts/outbox_cli.py replay

.PHONY: outbox-status
outbox-status: ## Check counts of pending outbox and dead letter events
	@$(EXEC_APP) python scripts/outbox_cli.py status

# ------------------------------------------------------------------------------
# Database Backup & Disaster Recovery
# ------------------------------------------------------------------------------
.PHONY: db-backup
db-backup: ## Dump compressed PostgreSQL custom-format archive into backups/
	@mkdir -p backups
	@echo -e "$(YELLOW)Extracting compressed PostgreSQL backup...$(NC)"
	@$(EXEC_DB) pg_dump -U $$(grep POSTGRES_USER .env | cut -d= -f2) $$(grep POSTGRES_DB .env | cut -d= -f2) | gzip -9 > backups/db_backup_$$(date +%Y%m%d_%H%M%S).sql.gz
	@echo -e "$(GREEN)✅ Backup saved to backups/$(NC)"

.PHONY: db-backup-verify
db-backup-verify: ## Test integrity of a compressed backup file (e.g., make db-backup-verify FILE=backups/db_xxx.sql.gz)
	@if [ -z "$(FILE)" ]; then \
		echo -e "$(RED)❌ FILE is required.$(NC) Usage: make db-backup-verify FILE=backups/your_backup.sql.gz"; \
		exit 1; \
	fi
	@gzip -t "$(FILE)" && echo -e "$(GREEN)✅ Gzip stream valid$(NC)"
	@gzip -dc "$(FILE)" | head -n 15

.PHONY: db-restore
db-restore: ## Restore backup into target DB (e.g., make db-restore FILE=backups/db.sql.gz DB=app_db)
	@if [ -z "$(FILE)" ] || [ ! -f "$(FILE)" ]; then \
		echo -e "$(RED)❌ Valid FILE path required.$(NC) Usage: make db-restore FILE=backups/db.sql.gz DB=target_db"; \
		exit 1; \
	fi
	@if [ -z "$(DB)" ]; then \
		echo -e "$(RED)❌ DB is required.$(NC) Specify target database (e.g., DB=app_restore or DB=app_db)"; \
		exit 1; \
	fi
	@if [ "$(DB)" = "$$(grep POSTGRES_DB .env | cut -d= -f2)" ] && [ "$(CONFIRM_LIVE_RESTORE)" != "YES" ]; then \
		echo -e "$(RED)❌ Refusing direct restore over live database without explicit confirmation.$(NC)"; \
		echo -e "$(YELLOW)Pass CONFIRM_LIVE_RESTORE=YES or restore to an alternate database first.$(NC)"; \
		exit 1; \
	fi
	@echo -e "$(YELLOW)Restoring $(FILE) into $(DB)...$(NC)"
	@gzip -dc "$(FILE)" | $(EXEC_DB) psql -U $$(grep POSTGRES_USER .env | cut -d= -f2) -d "$(DB)"
	@echo -e "$(GREEN)✅ Database restored$(NC)"

# ------------------------------------------------------------------------------
# Schema Sync & TypeScript Frontend Client Generation
# ------------------------------------------------------------------------------
.PHONY: export-schema
export-schema: ## Export Litestar OpenAPI 3.1 schema to frontend/openapi.json
	@echo -e "$(YELLOW)Extracting OpenAPI schema...$(NC)"
	@$(EXEC_APP) python scripts/export_schemas.py
	@echo -e "$(GREEN)✅ Exported to frontend/openapi.json$(NC)"

.PHONY: frontend-sync
frontend-sync: export-schema ## Compile TypeScript fetch client from exported OpenAPI schema
	@if [ -d "frontend" ]; then \
		echo -e "$(BLUE)Generating frontend TypeScript client via @hey-api/openapi-ts...$(NC)"; \
		cd frontend && npm run generate-client; \
		echo -e "$(GREEN)✅ Frontend API bindings updated in frontend/src/client/$(NC)"; \
	else \
		echo -e "$(YELLOW)Frontend directory not present. Skipping TypeScript generation.$(NC)"; \
	fi

# ------------------------------------------------------------------------------
# Cloudflare Tunnel
# ------------------------------------------------------------------------------
.PHONY: tunnel-status
tunnel-status: ## Check Cloudflare Tunnel container health and status
	@echo -e "$(YELLOW)Checking Cloudflare Tunnel status...$(NC)"
	@$(COMPOSE_BASE) ps cloudflared

.PHONY: tunnel-logs
tunnel-logs: ## Tail live logs from the Cloudflare Tunnel container
	@$(COMPOSE_BASE) logs -f --tail=200 cloudflared

.PHONY: tunnel-restart
tunnel-restart: ## Restart the Cloudflare Tunnel container
	@$(COMPOSE_BASE) restart cloudflared

# ------------------------------------------------------------------------------
# Automated Testing
# ------------------------------------------------------------------------------
.PHONY: test
test: ## Run test suite inside app container using isolated database subtransactions
	@echo -e "$(BLUE)Executing pytest suite inside container...$(NC)"
	@$(EXEC_APP) pytest $(TEST) -v

# ------------------------------------------------------------------------------
# Host Maintenance & System Cleanup
# ------------------------------------------------------------------------------
.PHONY: prune
prune: ## Prune stopped containers, dangling images, and build caches
	@echo -e "$(YELLOW)Pruning unused $(CONTAINER_ENGINE) system resources...$(NC)"
	@$(CONTAINER_ENGINE) system prune -f
	@echo -e "$(GREEN)✅ System pruned$(NC)"
