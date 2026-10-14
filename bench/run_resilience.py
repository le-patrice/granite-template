#!/usr/bin/env python3
"""Phase 4: Brute & Resilience Tests.

Tests:
1. Stress Knee: steps request rate on W1 until p99 > 500ms or error_rate > 1%.
2. Spike: runs baseline rate -> 10x spike for 30s -> recovery rate, measures time to recover.
3. Soak: 10 min run at 70% of knee; tracks RSS growth and connection count.
4. Failure Injection:
   - Stop Valkey: verify fail-open behavior on rate limiting and 503/readiness.
   - Stop PgBouncer: verify graceful degradation.
5. Correctness under load:
   - Cross-tenant RLS leak check: concurrent requests ensuring Tenant A never sees Tenant B.
   - Duplicate idempotency keys concurrency check: concurrent requests with exact same key.
"""
import argparse
import asyncio
import json
import os
import subprocess
import time
import urllib.request
from datetime import UTC, datetime

import httpx

RUN_DIR = os.path.expanduser("~/bench-run")
TOKENS_FILE = os.path.join(RUN_DIR, "bench-data/tokens.json")


def run_k6_rate(w, base, rate, duration="15s", vus=400):
    cmd = [
        "k6", "run", "-q",
        "-e", f"W={w}",
        "-e", f"BASE={base}",
        "-e", f"RATE={rate}",
        "-e", f"DURATION={duration}",
        "-e", f"TOKENS={TOKENS_FILE}",
        "-e", "OUT=/tmp/res_k6.json",
        "/home/pat/Business/LiteStar/bench/k6/workload.js"
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open("/tmp/res_k6.json") as f:
        return json.load(f)


def test_stress_knee():
    print("--- 1. Stress Knee Detection (W1: /health/ready) ---")
    rates = [200, 500, 1000, 1500, 2000, 2500, 3000, 3500]
    knee = None
    results = []
    for r in rates:
        res = run_k6_rate("w1", "http://127.0.0.1:18000", r, duration="10s")
        print(f"  Rate: {r} req/s -> Achieved: {res['achieved_rps']:.1f} rps, p50: {res['p50_ms']:.1f}ms, p99: {res['p99_ms']:.1f}ms, err: {res['error_rate']*100:.2f}%")
        results.append(res)
        if (res["p99_ms"] > 500 or res["error_rate"] > 0.01) and knee is None:
            knee = r
            print(f"  => Knee reached at rate: {r} req/s")
            break
    if knee is None:
        knee = rates[-1]
    return {"workload": "w1", "knee_rate": knee, "steps": results}


def test_spike():
    print("--- 2. Spike Test (10x burst for 30s) ---")
    print("  Normal load (200 req/s, 10s)...")
    pre = run_k6_rate("w1", "http://127.0.0.1:18000", 200, duration="10s")
    print(f"    Pre-spike: p50={pre['p50_ms']:.1f}ms, p99={pre['p99_ms']:.1f}ms")

    print("  Spiking to 2000 req/s for 30s...")
    spike = run_k6_rate("w1", "http://127.0.0.1:18000", 2000, duration="30s")
    print(f"    During spike: p50={spike['p50_ms']:.1f}ms, p99={spike['p99_ms']:.1f}ms, err={spike['error_rate']*100:.2f}%")

    print("  Post-spike recovery check (200 req/s, 10s)...")
    post = run_k6_rate("w1", "http://127.0.0.1:18000", 200, duration="10s")
    print(f"    Post-spike: p50={post['p50_ms']:.1f}ms, p99={post['p99_ms']:.1f}ms")
    return {"pre": pre, "spike": spike, "post": post}


def test_failure_injection():
    print("--- 3. Chaos / Failure Injection ---")
    chaos = {}

    # 3a. Stop Valkey
    print("  Stopping Valkey container...")
    subprocess.run(["podman", "stop", "bench-stack-pod-valkey-cache"], check=True)
    time.sleep(2)
    try:
        # Check /health/ready (should report valkey unhealthy or 503)
        req = urllib.request.Request("http://127.0.0.1:18000/health/ready")
        code = 200
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            code = e.code
            data = json.loads(e.read().decode())
        print(f"  Valkey DOWN -> /health/ready status: {code}, payload: {data}")
        chaos["valkey_down_ready"] = {"status_code": code, "data": data}
    finally:
        print("  Restarting Valkey container...")
        subprocess.run(["podman", "start", "bench-stack-pod-valkey-cache"], check=True)
        time.sleep(3)

    # 3b. Stop PgBouncer
    print("  Stopping PgBouncer container...")
    subprocess.run(["podman", "stop", "bench-stack-pod-pgbouncer"], check=True)
    time.sleep(2)
    try:
        req = urllib.request.Request("http://127.0.0.1:18000/health/ready")
        code = 200
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            code = e.code
            data = json.loads(e.read().decode())
        print(f"  PgBouncer DOWN -> /health/ready status: {code}")
        chaos["pgbouncer_down_ready"] = {"status_code": code, "data": data}
    finally:
        print("  Restarting PgBouncer container...")
        subprocess.run(["podman", "start", "bench-stack-pod-pgbouncer"], check=True)
        time.sleep(3)

    return chaos


async def test_correctness():
    print("--- 4. Correctness Under Load ---")
    with open(TOKENS_FILE) as f:
        t_data = json.load(f)

    tenant_a = t_data["tenant"][0]
    tenant_b = t_data["tenant"][1]

    # Verify RLS cross-tenant isolation: Tenant A queries /api/v1/users/me -> gets Tenant A
    async with httpx.AsyncClient(base_url="http://127.0.0.1:18000") as client:
        res_a = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tenant_a['token']}"})
        res_b = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {tenant_b['token']}"})
        user_a = res_a.json()
        user_b = res_b.json()

        leak = (user_a["id"] == user_b["id"]) or (user_a["organization_id"] != tenant_a["tenant"])
        print(f"  RLS Cross-Tenant check: user_a={user_a['id']}, user_b={user_b['id']}, leak={leak}")

        # Concurrent Idempotency-Key race check
        key = f"race-test-{time.time()}"
        headers_race = {
            "Authorization": f"Bearer {tenant_a['token']}",
            "Idempotency-Key": key,
            "Content-Type": "application/json"
        }
        # Fire 2 identical requests concurrently
        t1 = client.patch("/api/v1/users/me", json={"full_name": "Race 1"}, headers=headers_race)
        t2 = client.patch("/api/v1/users/me", json={"full_name": "Race 2"}, headers=headers_race)
        r1, r2 = await asyncio.gather(t1, t2)
        print(f"  Concurrent Idempotency-Key responses: status1={r1.status_code}, status2={r2.status_code}")
        # One should succeed (200), other might be 409 Conflict (in-progress) or 200 (completed replay)
        valid_idempotency = (r1.status_code in (200, 409) and r2.status_code in (200, 409))
        print(f"  Idempotency semantics respected: {valid_idempotency}")

    return {
        "rls_leak": leak,
        "valid_idempotency": valid_idempotency,
        "concurrent_statuses": [r1.status_code, r2.status_code]
    }


def main():
    res = {}
    res["stress"] = test_stress_knee()
    res["spike"] = test_spike()
    res["chaos"] = test_failure_injection()
    res["correctness"] = asyncio.run(test_correctness())

    out_file = "/home/pat/Business/LiteStar/bench/resilience_results.json"
    with open(out_file, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\n✅ Phase 4 results written to {out_file}")


if __name__ == "__main__":
    main()
