#!/usr/bin/env python3
"""Run workload(s) for a specific fix, aggregate results, and compare against baseline.

Usage:
    python3 bench/measure_fix.py --fix-id FIX-01-G01-G02 \
                                 --commit-hash abc1234 \
                                 --desc "JWT auth + body limits in Go ingest" \
                                 --base http://127.0.0.1:18001 \
                                 --run w4go:100:1 \
                                 --run w4go:50:100 \
                                 --run w4go:10:1000 \
                                 [--duration 15s] [--reps 3]
"""
import argparse
import csv
import json
import os
import pathlib
import subprocess
import sys

BASE_CSV = pathlib.Path(__file__).parent / "results_baseline.csv"
FIX_CSV = pathlib.Path(__file__).parent / "FIX_RESULTS.csv"
RESULTS_DIR = pathlib.Path(os.environ.get("BENCH_OUT", pathlib.Path.home() / "bench-run" / "results"))
RUN_WORKLOAD = pathlib.Path(__file__).parent / "run_workload.sh"
AGGREGATE = pathlib.Path(__file__).parent / "aggregate.py"


def load_csv(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as fh:
        r = csv.DictReader(fh)
        out = {}
        for row in r:
            key = (row["label"], row["workload"], row["target_rate"], row.get("batch", ""))
            out[key] = row
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix-id", required=True)
    ap.add_argument("--commit-hash", default="HEAD")
    ap.add_argument("--desc", required=True)
    ap.add_argument("--base", default="http://127.0.0.1:18000")
    ap.add_argument("--run", action="append", required=True,
                    help="FORMAT: workload:rate or workload:rate:batch (e.g. w4go:50:100 or w1:200)")
    ap.add_argument("--duration", default="15s")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    # Get git commit hash if HEAD
    commit = args.commit_hash
    if commit == "HEAD":
        res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        commit = res.stdout.strip()

    label = args.fix_id.lower().replace("-", "_")

    # Run workloads
    for spec in args.run:
        parts = spec.split(":")
        w = parts[0]
        rate = parts[1]
        batch = parts[2] if len(parts) > 2 else ("100" if w.startswith("w4") else "")

        print(f"\n>>> Running workload {w} for {args.fix_id} (rate={rate}, batch={batch}, base={args.base}, label={label})...")
        cmd = [
            str(RUN_WORKLOAD),
            label,
            w,
            args.base,
            str(rate),
            args.duration,
            str(batch if batch else "100"),
            str(args.reps),
        ]
        subprocess.run(cmd, check=True)

    # Aggregate all runs
    subprocess.run([sys.executable, str(AGGREGATE), str(RESULTS_DIR)], check=True)

    # Read aggregated results
    all_results = load_csv(RESULTS_DIR / "results.csv")
    baseline_results = load_csv(BASE_CSV)

    fix_rows = []
    headers = [
        "fix_id", "commit_hash", "description", "workload", "batch", "target_rate",
        "metric", "before", "after", "delta_pct", "verdict", "notes"
    ]

    for spec in args.run:
        parts = spec.split(":")
        w = parts[0]
        rate = parts[1]
        batch = parts[2] if len(parts) > 2 else ("100" if w.startswith("w4") else "")

        base_key = ("baseline", w, rate, batch)
        after_key = (label, w, rate, batch)

        if base_key not in baseline_results:
            print(f"Warning: {base_key} not found in baseline")
            continue
        if after_key not in all_results:
            print(f"Warning: {after_key} not found in aggregated results")
            continue

        b = baseline_results[base_key]
        a = all_results[after_key]

        metrics = [
            ("rps", "rps_med"),
            ("p50_ms", "p50_ms_med"),
            ("p95_ms", "p95_ms_med"),
            ("p99_ms", "p99_ms_med"),
            ("max_ms", "max_ms_med"),
            ("err_pct", "err_pct_med"),
        ]

        verdict = "ACCEPT"

        for m_name, col in metrics:
            val_b = float(b[col])
            val_a = float(a[col])
            delta = ((val_a - val_b) / val_b * 100.0) if val_b != 0 else 0.0
            fix_rows.append({
                "fix_id": args.fix_id,
                "commit_hash": commit,
                "description": args.desc,
                "workload": w,
                "batch": batch,
                "target_rate": rate,
                "metric": m_name,
                "before": f"{val_b:.3f}",
                "after": f"{val_a:.3f}",
                "delta_pct": f"{delta:+.2f}%",
                "verdict": verdict,
                "notes": args.notes,
            })

    # Write or append to FIX_CSV
    file_exists = FIX_CSV.exists()
    existing_rows = []
    if file_exists:
        with open(FIX_CSV) as fh:
            existing_rows = list(csv.DictReader(fh))

    # Replace any previous rows with same fix_id
    updated_rows = [r for r in existing_rows if r["fix_id"] != args.fix_id] + fix_rows

    with open(FIX_CSV, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerows(updated_rows)

    print(f"\n=== Summary of Measured Deltas for {args.fix_id} ===")
    for r in fix_rows:
        print(f"  [{r['workload']} b={r['batch']} @ {r['target_rate']} rps] {r['metric']}: {r['before']} -> {r['after']} ({r['delta_pct']})")
    print(f"\nWritten to {FIX_CSV}")


if __name__ == "__main__":
    main()
