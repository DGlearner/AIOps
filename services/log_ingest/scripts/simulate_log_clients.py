import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from websockets.asyncio.client import connect

from log_ingest.schemas import StreamSimulationConfig, stream_source_to_payload


def load_lines(path: Path) -> list[str]:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        raise ValueError(f"No log lines found in {path}")
    return lines


def batch_lines(lines: list[str], *, batch_size: int) -> list[list[str]]:
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    return [lines[index : index + batch_size] for index in range(0, len(lines), batch_size)]


def build_payload(source: dict[str, Any], logs: list[str]) -> dict[str, Any]:
    return stream_source_to_payload(source, logs)


def resolve_source_files(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    for source in config.get("sources") or []:
        file_value = source.get("file")
        if not file_value:
            continue
        file_path = Path(file_value)
        if not file_path.is_absolute():
            file_path = config_path.parent / file_path
        source["file"] = str(file_path.resolve())
    return config


def load_config(path: Path) -> dict[str, Any]:
    config_path = path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config = resolve_source_files(config, config_path)
    validated = StreamSimulationConfig.model_validate(config)
    config = validated.model_dump()
    config["sources"] = [
        source
        for source in config["sources"]
        if source.get("enabled", True)
    ]
    return config


async def run_source_client(
    *,
    endpoint: str,
    source: dict[str, Any],
    default_batch_size: int,
    default_rate_per_second: float,
    loop: bool,
    duration_seconds: float | None,
) -> dict[str, Any]:
    name = source.get("name") or source["source_type"]
    lines = load_lines(Path(source["file"]))
    batch_size = int(source.get("batch_size") or default_batch_size)
    rate_per_second = float(source.get("rate_per_second") or default_rate_per_second)
    delay_seconds = 0.0 if rate_per_second <= 0 else batch_size / rate_per_second

    accepted = 0
    batches_sent = 0
    started_at = time.monotonic()

    async with connect(endpoint) as websocket:
        while True:
            for logs in batch_lines(lines, batch_size=batch_size):
                if duration_seconds is not None and time.monotonic() - started_at >= duration_seconds:
                    return {
                        "name": name,
                        "status": "completed",
                        "batches_sent": batches_sent,
                        "accepted_logs": accepted,
                    }

                await websocket.send(json.dumps(build_payload(source, logs), ensure_ascii=False))
                ack = json.loads(await websocket.recv())
                if ack.get("status") != "accepted":
                    raise RuntimeError(f"{name} received non-accepted ack: {ack}")
                accepted += int(ack.get("accepted") or 0)
                batches_sent += 1
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)

            if not loop:
                return {
                    "name": name,
                    "status": "completed",
                    "batches_sent": batches_sent,
                    "accepted_logs": accepted,
                }


async def run_simulation(
    *,
    config_path: Path,
    endpoint: str,
    loop: bool,
    duration_seconds: float | None,
) -> dict[str, Any]:
    config = load_config(config_path)
    default_batch_size = int(config.get("batch_size") or 10)
    default_rate_per_second = float(config.get("rate_per_second") or 10)
    sources = config.get("sources") or []

    results = await asyncio.gather(
        *[
            run_source_client(
                endpoint=endpoint,
                source=source,
                default_batch_size=default_batch_size,
                default_rate_per_second=default_rate_per_second,
                loop=loop,
                duration_seconds=duration_seconds,
            )
            for source in sources
        ]
    )

    return {
        "status": "completed",
        "endpoint": endpoint,
        "source_count": len(sources),
        "accepted_logs": sum(result["accepted_logs"] for result in results),
        "sources": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate multiple log source clients over WebSocket."
    )
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--endpoint",
        default="ws://localhost:8100/ws/ingest/logs",
        help="WebSocket ingest endpoint.",
    )
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(
        run_simulation(
            config_path=args.config,
            endpoint=args.endpoint,
            loop=args.loop,
            duration_seconds=args.duration_seconds,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
