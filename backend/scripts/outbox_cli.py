"""
CLI tool for Outbox event relay sweeps and Dead Letter Queue (DLQ) replay.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from app.adapters.outbox.relay import OutboxRelay, PostgresOutboxRepository
from app.core.database import db_config


async def run_action(action: str) -> None:
    session_maker = db_config.create_session_maker()
    async with session_maker() as session:
        repo = PostgresOutboxRepository(session)
        relay = OutboxRelay(repo)

        if action == "sweep":
            count = await relay.process_sweep()
            print(f"✅ Outbox sweep complete. Relayed {count} pending events.")
        elif action == "replay":
            dead_letters = await repo.get_dead_letters(limit=100)
            replayed = 0
            for dl in dead_letters:
                await repo.replay_dead_letter(dl.id)
                replayed += 1
            print(f"✅ DLQ replay complete. Replayed {replayed} quarantined events.")
        elif action == "status":
            pending = await repo.get_pending_events()
            dead = await repo.get_dead_letters()
            print(f"📊 Outbox Status — Pending: {len(pending)}, Dead Letters (DLQ): {len(dead)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Transactional Outbox & DLQ CLI")
    parser.add_argument("action", choices=["sweep", "replay", "status"], default="sweep", nargs="?")
    args = parser.parse_args()
    asyncio.run(run_action(args.action))


if __name__ == "__main__":
    main()
