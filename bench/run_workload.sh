#!/usr/bin/env bash
# bench/run_workload.sh LABEL W BASE RATE [DURATION=30s] [BATCH=100] [REPS=3]
# Warm-up (10 s, same rate) then REPS measured runs. Writes raw JSON + container stats under
#   $BENCH_OUT/raw/<LABEL>__<W>__<RATE>[__b<BATCH>]__<rep>.{json,stats.csv}
set -euo pipefail
LABEL=$1; W=$2; BASE=$3; RATE=$4; DURATION=${5:-30s}; BATCH=${6:-100}; REPS=${7:-3}
OUT=${BENCH_OUT:-$HOME/bench-run/results}
TOK=${TOKENS:-$HOME/bench-run/bench-data/tokens.json}
HERE=$(cd "$(dirname "$0")" && pwd)
POD=${POD:-bench-stack-pod}
mkdir -p "$OUT/raw"
suffix=""; [ "$W" = w4 ] && suffix="__b${BATCH}"

sample() { # background container stats sampler -> csv (ts,name,cpu%,mem_bytes)
  while true; do
    podman stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' 2>/dev/null |
      grep "^$POD" | sed "s/^/$(date +%s),/" >> "$1" || true
    sleep 2
  done
}

k6 run -q -e W="$W" -e BASE="$BASE" -e RATE="$RATE" -e DURATION=10s -e BATCH="$BATCH" \
  -e TOKENS="$TOK" -e RUNID=warm -e OUT=/dev/null "$HERE/k6/workload.js" >/dev/null 2>&1 || true
sleep 3
for rep in $(seq 1 "$REPS"); do
  base="$OUT/raw/${LABEL}__${W}__${RATE}${suffix}__${rep}"
  : > "$base.stats.csv"
  sample "$base.stats.csv" & SP=$!
  k6 run -q -e W="$W" -e BASE="$BASE" -e RATE="$RATE" -e DURATION="$DURATION" -e BATCH="$BATCH" \
    -e TOKENS="$TOK" -e RUNID="r$rep" -e OUT="$base.json" "$HERE/k6/workload.js" 2>&1 | tail -1
  kill $SP 2>/dev/null || true; wait $SP 2>/dev/null || true
  sleep 3
done
