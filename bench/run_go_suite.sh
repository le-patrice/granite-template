#!/usr/bin/env bash
set -euo pipefail

BASE="http://127.0.0.1:18002"
LABEL="go_baseline"
DURATION="30s"
REPS=3

echo "=== Running Go Baseline Benchmark Suite ==="

echo "--- W1 (Readiness) @ 200 rps ---"
bench/run_workload.sh "$LABEL" w1 "$BASE" 200 "$DURATION" 100 "$REPS"

echo "--- W2 (Users List Paginated + RLS) @ 50 rps ---"
bench/run_workload.sh "$LABEL" w2 "$BASE" 50 "$DURATION" 100 "$REPS"

echo "--- W4 (Telemetry Ingest) b1 @ 100 rps ---"
bench/run_workload.sh "$LABEL" w4 "$BASE" 100 "$DURATION" 1 "$REPS"

echo "--- W4 (Telemetry Ingest) b100 @ 50 rps ---"
bench/run_workload.sh "$LABEL" w4 "$BASE" 50 "$DURATION" 100 "$REPS"

echo "--- W4 (Telemetry Ingest) b1000 @ 10 rps ---"
bench/run_workload.sh "$LABEL" w4 "$BASE" 10 "$DURATION" 1000 "$REPS"

echo "--- W4 (Telemetry Ingest) Python Parity Rates ---"
echo "--- W4 b1 @ 50 rps ---"
bench/run_workload.sh "$LABEL" w4 "$BASE" 50 "$DURATION" 1 "$REPS"

echo "--- W4 b100 @ 20 rps ---"
bench/run_workload.sh "$LABEL" w4 "$BASE" 20 "$DURATION" 100 "$REPS"

echo "--- W4 b1000 @ 5 rps ---"
bench/run_workload.sh "$LABEL" w4 "$BASE" 5 "$DURATION" 1000 "$REPS"

echo "=== All Go Baseline Workloads Completed ==="
