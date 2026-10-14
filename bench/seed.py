#!/usr/bin/env python3
"""Deterministic seed (random.seed(42)). Connects as DB owner on the DIRECT port (never PgBouncer).

  python seed.py --users 10000 --orgs 10 --telemetry 1000000 --dsn postgresql://app_user:PW@127.0.0.1:5432/app_db

Writes bench-data/tokens.json with ready-to-use JWTs (signed with SECRET_KEY) so load tests never
hit the Argon2 login path (W5 measures that separately).
Local disposable database only.
"""
import argparse
import asyncio
import json
import pathlib
import random
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--secret", required=True)
    ap.add_argument("--users", type=int, default=10_000)
    ap.add_argument("--orgs", type=int, default=10)
    ap.add_argument("--telemetry", type=int, default=1_000_000)
    ap.add_argument("--transformers", type=int, default=500)
    ap.add_argument("--out", default="bench-data/tokens.json")
    a = ap.parse_args()

    rnd = random.Random(42)
    ns = uuid.UUID("11111111-1111-1111-1111-111111111111")
    pw_hash = PasswordHash((Argon2Hasher(),)).hash("BenchPass123!")
    conn = await asyncpg.connect(a.dsn)
    await conn.execute("TRUNCATE telemetry_readings")
    await conn.execute("DELETE FROM platform_users WHERE email LIKE 'bench-%'")
    await conn.execute("DELETE FROM organizations WHERE slug LIKE 'bench-org-%'")

    orgs = [uuid.uuid5(ns, f"org-{i}") for i in range(a.orgs)]
    await conn.executemany(
        "INSERT INTO organizations (id,name,slug) VALUES ($1,$2,$3)",
        [(o, f"Bench Org {i}", f"bench-org-{i}") for i, o in enumerate(orgs)],
    )
    now = datetime.now(UTC)
    users = []
    for i in range(a.users):
        uid = uuid.uuid5(ns, f"user-{i}")
        users.append(
            (uid, f"bench-{i}@example.test", pw_hash, f"Bench User {i}", True, i == 0,
             orgs[i % a.orgs], "superadmin" if i == 0 else "member", now, now)
        )
    await conn.copy_records_to_table(
        "platform_users",
        records=users,
        columns=["id", "email", "hashed_password", "full_name", "is_active", "is_superuser",
                 "organization_id", "role", "created_at", "updated_at"],
    )
    print(f"users={a.users} orgs={a.orgs}")

    tids = [f"TRF-{i:04d}" for i in range(a.transformers)]
    batch, total = [], 0
    base = now - timedelta(days=3)
    for _ in range(a.telemetry):
        batch.append((uuid.UUID(int=rnd.getrandbits(128), version=4), rnd.choice(tids),
                      rnd.gauss(230, 4), rnd.gauss(40, 8), rnd.uniform(0.85, 1.0),
                      rnd.gauss(50, 0.05), base + timedelta(seconds=rnd.random() * 259200), now))
        if len(batch) == 100_000:
            await conn.copy_records_to_table(
                "telemetry_readings", records=batch,
                columns=["id", "transformer_id", "voltage_v", "current_a", "power_factor",
                         "frequency_hz", "recorded_at", "ingested_at"])
            total += len(batch)
            batch = []
    if batch:
        await conn.copy_records_to_table(
            "telemetry_readings", records=batch,
            columns=["id", "transformer_id", "voltage_v", "current_a", "power_factor",
                     "frequency_hz", "recorded_at", "ingested_at"])
        total += len(batch)
    print(f"telemetry={total}")
    # VACUUM cannot be batched in one simple-query (implicit transaction) -> run separately
    await conn.execute("VACUUM (ANALYZE) platform_users")
    await conn.execute("VACUUM (ANALYZE) telemetry_readings")
    await conn.close()

    def tok(sub: uuid.UUID, org: uuid.UUID | None, role: str, su: bool) -> str:
        return jwt.encode(
            {"sub": str(sub), "exp": now + timedelta(hours=12), "iat": now, "jti": str(uuid.uuid4()),
             "is_superuser": su, "tenant_id": str(org) if org else "",
             "organization_id": str(org) if org else "", "role": role},
            a.secret, algorithm="HS256")

    out = {
        "super": tok(users[0][0], None, "superadmin", True),
        "tenant": [{"sub": str(users[i][0]), "tenant": str(orgs[i % a.orgs]),
                    "token": tok(users[i][0], orgs[i % a.orgs], "member", False)}
                   for i in range(1, min(a.users, 200))],
        "emails": [u[1] for u in users[1:51]],
    }
    p = pathlib.Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out))
    print("wrote", p)


asyncio.run(main())
