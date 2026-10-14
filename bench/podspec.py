#!/usr/bin/env python3
"""Derive a benchmark pod spec from a rendered config/platform-pod.yaml.

Applies ONLY what is needed to make runs reproducible and fair, and prints every change:
  * identical resource limits per container (see LIMITS)
  * drops granian --reload (dev-only; makes workers restart on file change)
  * sets RATE_LIMIT_ENABLED=false (otherwise 120 req/min/IP caps every test)
  * adds direct host ports (app 18000, go-ingest 18001) so Traefik can be bypassed
  * Traefik arm: removes the global-ratelimit middleware from a COPY of traefik-dev.yml
Per-fix overrides come from --set KEY=VALUE (app env) and --workers N, so each fix is one flag.

usage: podspec.py SRC.yaml OUT.yaml [--workers N] [--set K=V ...] [--app-image IMG]
"""
import argparse
import copy
import pathlib
import re

import yaml

LIMITS = {
    "app": ("2", "1Gi"),
    "telemetry-ingest": ("2", "1Gi"),
    "worker": ("1", "512Mi"),
    "postgres-db": ("2", "2Gi"),
    "pgbouncer": ("1", "128Mi"),
    "valkey-cache": ("1", "256Mi"),
    "traefik": ("1", "256Mi"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=2)  # calibrated to match 2-CPU container limit
    ap.add_argument("--set", action="append", default=[], help="app env K=V")
    ap.add_argument("--pg-arg", action="append", default=[], help="postgres -c arg, e.g. shared_buffers=512MB")
    ap.add_argument("--pgb", action="append", default=[], help="pgbouncer env K=V")
    ap.add_argument("--no-reload-only", action="store_true")
    args = ap.parse_args()

    docs = list(yaml.safe_load_all(pathlib.Path(args.src).read_text()))
    pod = docs[0]
    log = []
    for c in pod["spec"]["containers"]:
        name = c["name"]
        if name in LIMITS:
            cpu, mem = LIMITS[name]
            c["resources"] = {"limits": {"cpu": cpu, "memory": mem}}
            log.append(f"{name}: limits cpu={cpu} mem={mem}")
        if name == "app":
            cmd = [x for x in c["command"] if x != "--reload"]
            if "--workers" in cmd:
                i = cmd.index("--workers")
                cmd[i + 1] = str(args.workers)
            if "--runtime-threads" in cmd:
                i = cmd.index("--runtime-threads")
                cmd[i + 1] = "1"
            c["command"] = cmd
            c.setdefault("env", []).append({"name": "RATE_LIMIT_ENABLED", "value": "false"})
            for kv in args.set:
                k, v = kv.split("=", 1)
                c["env"] = [e for e in c["env"] if e["name"] != k] + [{"name": k, "value": v}]
            c["ports"] = [{"containerPort": 8000, "hostPort": 18000}]
            log.append(f"app: --reload removed, workers={args.workers}, RATE_LIMIT_ENABLED=false, set={args.set}")
        if name == "worker":
            c.setdefault("env", []).append({"name": "RATE_LIMIT_ENABLED", "value": "false"})
        if name == "telemetry-ingest":
            c["ports"] = [{"containerPort": 8001, "hostPort": 18001}]
            if not any(e["name"] == "SECRET_KEY" for e in c.get("env", [])):
                secret = "d4b701543ffa55b4423be1d7993a4e3f6efdf8eaaf406165eee1c37d59ad3974"
                c.setdefault("env", []).append({"name": "SECRET_KEY", "value": secret})
        if name == "postgres-db":
            pg_args = list(args.pg_arg)
            if not any(x.startswith("max_connections=") for x in pg_args):
                pg_args.append("max_connections=200")
            c["args"] = ["postgres"] + [x for kv in pg_args for x in ("-c", kv)]
            log.append(f"postgres args: {pg_args}")
        if name == "pgbouncer" and args.pgb:
            for kv in args.pgb:
                k, v = kv.split("=", 1)
                c["env"] = [e for e in c["env"] if e["name"] != k] + [{"name": k, "value": v}]
            log.append(f"pgbouncer env: {args.pgb}")

    # Traefik without the edge rate limit (copy lives next to OUT)
    out = pathlib.Path(args.out)
    t_src = pathlib.Path(args.src).parent / "traefik-dev.yml"
    t_dst = out.parent / "traefik-bench.yml"
    txt = t_src.read_text()
    txt = re.sub(r"\n\s+- global-ratelimit", "", txt)
    t_dst.write_text(txt)
    for v in pod["spec"]["volumes"]:
        if v["name"] == "traefik-config":
            v["hostPath"]["path"] = str(t_dst.resolve())
    log.append("traefik: global-ratelimit middleware removed (copy)")

    # absolute hostPaths so kube play works from any cwd
    root = pathlib.Path(args.src).resolve().parent.parent
    for v in pod["spec"]["volumes"]:
        hp = v.get("hostPath")
        if hp and hp["path"].startswith("./"):
            hp["path"] = str((root / hp["path"][2:]).resolve())

    out.write_text(yaml.safe_dump_all(docs, sort_keys=False))
    print("\n".join(log))


if __name__ == "__main__":
    main()
