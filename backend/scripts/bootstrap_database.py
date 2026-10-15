import argparse
import asyncio
import json
from typing import Any

from crossst.infrastructure.storage.init_db import init_db
from scripts.seed_context_data import seed_context_data
from scripts.seed_knowledge_data import seed_knowledge_data


def build_bootstrap_report(
    *,
    init_status: str,
    knowledge: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "ok" if init_status == "ok" else "degraded",
        "database_initialized": init_status == "ok",
        "knowledge": knowledge,
        "context": context,
    }


async def bootstrap_database() -> dict[str, Any]:
    await init_db()
    knowledge = await seed_knowledge_data()
    context = await seed_context_data()
    return build_bootstrap_report(
        init_status="ok",
        knowledge=knowledge,
        context=context,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize PostgreSQL tables and seed MVP context data."
    )
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(bootstrap_database())
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()

