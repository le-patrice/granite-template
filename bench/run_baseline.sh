#!/usr/bin/env bash
# bench/run_baseline.sh [LABEL=baseline] [DURATION=15s] [REPS=3]
set -euo pipefail

LABEL=${1:-baseline}
DURATION=${2:-15s}
REPS=${3:-3}

HERE=$(cd "$(dirname "$0")" && pwd)
RUN_DIR=$HOME/bench-run
OUT_DIR=$RUN_DIR/results
TOKENS=$RUN_DIR/bench-data/tokens.json

export BENCH_OUT=$OUT_DIR
export TOKENS=$TOKENS
export POD=bench-stack-pod

mkdir -p "$OUT_DIR/raw"

echo "=== Starting Benchmark Suite: $LABEL (duration: $DURATION, reps: $REPS) ==="

# 1. W1: GET /health/ready
echo "--- Running W1: /health/ready (direct app :18000) ---"
"$HERE/run_workload.sh" "$LABEL" w1 "http://127.0.0.1:18000" 200 "$DURATION" 100 "$REPS"

echo "--- Running W1 through Traefik (:8000) for proxy overhead check ---"
"$HERE/run_workload.sh" "${LABEL}_traefik" w1 "http://127.0.0.1:8000" 200 "$DURATION" 100 "$REPS"

# 2. W2: GET /users (paginated, admin superuser RLS path)
echo "--- Running W2: GET /users paginated ---"
"$HERE/run_workload.sh" "$LABEL" w2 "http://127.0.0.1:18000" 50 "$DURATION" 100 "$REPS"

# 3. W2t: GET /users/me (tenant user, tenant-scoped RLS path)
echo "--- Running W2t: GET /users/me ---"
"$HERE/run_workload.sh" "$LABEL" w2t "http://127.0.0.1:18000" 50 "$DURATION" 100 "$REPS"

# 4. W3: PATCH /users/me with unique Idempotency-Key
echo "--- Running W3: PATCH /users/me (unique key) ---"
"$HERE/run_workload.sh" "$LABEL" w3 "http://127.0.0.1:18000" 20 "$DURATION" 100 "$REPS"

# 5. W3dup: PATCH /users/me (duplicate key replay)
echo "--- Running W3dup: PATCH /users/me (replay cache hit) ---"
"$HERE/run_workload.sh" "$LABEL" w3dup "http://127.0.0.1:18000" 50 "$DURATION" 100 "$REPS"

# 6. W4 Python: POST /telemetry/ingest (batch 1, 100, 1000)
echo "--- Running W4 Python: batch 1 ---"
"$HERE/run_workload.sh" "$LABEL" w4 "http://127.0.0.1:18000" 50 "$DURATION" 1 "$REPS"

echo "--- Running W4 Python: batch 100 ---"
"$HERE/run_workload.sh" "$LABEL" w4 "http://127.0.0.1:18000" 20 "$DURATION" 100 "$REPS"

echo "--- Running W4 Python: batch 1000 ---"
"$HERE/run_workload.sh" "$LABEL" w4 "http://127.0.0.1:18000" 5 "$DURATION" 1000 "$REPS"

# 7. W4 Go Ingest: POST /telemetry/ingest (batch 1, 100, 1000)
echo "--- Running W4 Go Ingest: batch 1 ---"
"$HERE/run_workload.sh" "$LABEL" w4go "http://127.0.0.1:18001" 100 "$DURATION" 1 "$REPS"

echo "--- Running W4 Go Ingest: batch 100 ---"
"$HERE/run_workload.sh" "$LABEL" w4go "http://127.0.0.1:18001" 50 "$DURATION" 100 "$REPS"

echo "--- Running W4 Go Ingest: batch 1000 ---"
"$HERE/run_workload.sh" "$LABEL" w4go "http://127.0.0.1:18001" 10 "$DURATION" 1000 "$REPS"

# 8. W5: POST /auth/login (Argon2id CPU bound)
echo "--- Running W5: POST /auth/login (Argon2id) ---"
"$HERE/run_workload.sh" "$LABEL" w5 "http://127.0.0.1:18000" 2 "$DURATION" 100 "$REPS"

echo "=== Aggregating results into $OUT_DIR/results.csv ==="
python3 "$HERE/aggregate.py" "$OUT_DIR"

echo "=== Baseline benchmark complete ==="
