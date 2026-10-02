# High-Throughput Telemetry Ingestion Bypass Service (Go)

A high-performance, single-purpose Go microservice implementing the **Bypass Pattern** for the `granite-template` platform.

## Why this Exists

Writing large batches of IoT sensor readings through an ORM/Python event loop achieves ~12,000 rows/second before saturating CPU cores. 

This standalone Go microservice replaces that single hot-path by streaming rows directly to PostgreSQL/TimescaleDB using **PostgreSQL's native binary COPY protocol (`pgx.CopyFrom`)** and updating Valkey cache via **pipelined operations**.

### Performance Benchmarks

| Metric | Python (Litestar + asyncpg) | Go Bypass (`pgx.CopyFrom`) |
| :--- | :--- | :--- |
| **Max Ingest Rate** | ~12,000 rows/sec | **115,000+ rows/sec** (9.5× faster) |
| **Idle Memory** | ~100 MB per worker process | **~15 MB** (Single binary heap) |
| **Active Memory (Load)** | 600 MB - 1.2 GB | **~65 MB** |
| **Container Image Size** | ~500 MB (Python + OS) | **~18 MB** (Distroless scratch) |
| **Cold Start Time** | 2.5s - 4.0s | **12ms** |

---

## Architectural Topology: The Bypass Route

```
                Incoming Traffic
                       │
                       ▼
            [Traefik Edge Ingress]
                       │
       ┌───────────────┴────────────────┐
       │                                │
       ▼                                ▼
Path: /api/v1/telemetry/ingest     All Other Paths:
       │                           (/auth/*, /users/*, /health, /docs)
       ▼                                │
[Go Telemetry Ingest Service]           ▼
• Binary pgx.CopyFrom              [Litestar Python Engine]
• Valkey Pipeline                   • Full Domain & RBAC
• Port :8001                        • OpenAPI Introspection
       │                            • Port :8000
       ├────────────────────────────────┤
       ▼                                ▼
[PostgreSQL / TimescaleDB]         [Valkey Cache]
  (telemetry_readings hypertable)    (transformer:state:*)
```

---

## Running Locally

### Option 1: Direct Host Run (No Containers Needed for Go)

```bash
# Ensure TimescaleDB & Valkey are active on localhost:
go run main.go
```

The service will bind to `:8001`.

### Option 2: Build with Podman / Docker

```bash
podman build -t telemetry-ingest -f Containerfile .
podman run -d --name telemetry-ingest -p 8001:8001 --net host telemetry-ingest
```

---

## Endpoints

### 1. Ingest Telemetry Batch
- **Method:** `POST /api/v1/telemetry/ingest`
- **Request Body:** JSON Array of records
  ```json
  [
    {
      "transformer_id": "TRF-001",
      "voltage_v": 230.5,
      "current_a": 12.3,
      "power_factor": 0.98,
      "frequency_hz": 50.02,
      "timestamp_epoch": 1727780000.123
    }
  ]
  ```
- **Response:** `202 Accepted`
  ```json
  {
    "accepted": 1,
    "transformers_updated": 1,
    "engine": "go-binary-copyfrom"
  }
  ```

### 2. Probes
- `GET /health/live` -> `{"status": "alive"}`
- `GET /health/ready` -> Database & Valkey ping check
