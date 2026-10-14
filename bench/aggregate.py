#!/usr/bin/env python3
"""Aggregate raw k6 JSON + podman stats into results.csv (median and min-max spread per cell).

usage: aggregate.py RESULTS_DIR   -> RESULTS_DIR/results.csv
Memory is the max RSS seen per container (sampled every 2 s); CPU is the mean of samples (percent of one core).
"""
import csv
import json
import pathlib
import re
import statistics as st
import sys
from collections import defaultdict

root = pathlib.Path(sys.argv[1])
cells = defaultdict(list)
for f in sorted((root / "raw").glob("*.json")):
    parts = f.stem.split("__")
    label, w, rate = parts[0], parts[1], parts[2]
    batch = next((p[1:] for p in parts[3:] if p.startswith("b")), "")
    d = json.loads(f.read_text())
    cpu, mem = defaultdict(list), defaultdict(float)
    sf = f.with_suffix("").with_suffix(".stats.csv")
    if sf.exists():
        for line in sf.read_text().splitlines():
            m = re.match(r"\d+,([^,]+),([\d.]+)%,([\d.]+)(\w+) /", line)
            if not m:
                continue
            name = m.group(1).replace("bench-stack-pod-", "")
            unit = {"B": 1, "kB": 1e3, "KB": 1e3, "MB": 1e6, "MiB": 2**20, "GB": 1e9, "GiB": 2**30}.get(m.group(4), 1)
            cpu[name].append(float(m.group(2)))
            mem[name] = max(mem[name], float(m.group(3)) * unit)
    d["_cpu"] = {k: st.mean(v) for k, v in cpu.items()}
    d["_mem"] = dict(mem)
    cells[(label, w, rate, batch)].append(d)


def med(xs):
    return st.median(xs) if xs else float("nan")


rows = []
for (label, w, rate, batch), runs in cells.items():
    g = lambda k: [r[k] for r in runs]
    row = {
        "label": label, "workload": w, "target_rate": rate, "batch": batch, "reps": len(runs),
        "rps_med": med(g("achieved_rps")), "rps_min": min(g("achieved_rps")), "rps_max": max(g("achieved_rps")),
        "p50_ms_med": med(g("p50_ms")), "p95_ms_med": med(g("p95_ms")),
        "p99_ms_med": med(g("p99_ms")), "p99_ms_min": min(g("p99_ms")), "p99_ms_max": max(g("p99_ms")),
        "max_ms_med": med(g("max_ms")), "err_pct_med": 100 * med(g("error_rate")),
        "dropped_med": med(g("dropped_iterations")),
    }
    for c in ("app", "telemetry-ingest", "postgres-db", "pgbouncer", "valkey-cache", "worker", "traefik", "go-baseline"):
        row[f"cpu_{c}"] = round(med([r["_cpu"].get(c, float("nan")) for r in runs]), 1)
        row[f"rss_mb_{c}"] = round(med([r["_mem"].get(c, 0) / 1e6 for r in runs]), 1)
    rows.append(row)

rows.sort(key=lambda r: (r["label"], r["workload"], float(r["target_rate"])))
if rows:
    with open(root / "results.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
print(f"{len(rows)} cells -> {root / 'results.csv'}")
