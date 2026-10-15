import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib import request


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
    return items


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with request.urlopen(http_request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8")
        return json.loads(response_body)


def send_dataset(
    *,
    dataset_path: Path,
    endpoint: str,
    delay_seconds: float,
    timeout: float,
) -> list[dict[str, Any]]:
    payloads = load_jsonl(dataset_path)
    responses: list[dict[str, Any]] = []

    for payload in payloads:
        responses.append(post_json(endpoint, payload, timeout))
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return responses


def main() -> None:
    parser = argparse.ArgumentParser(description="Send simulated logs to log-ingest-service.")
    parser.add_argument("dataset", type=Path, help="Path to a JSONL dataset.")
    parser.add_argument(
        "--endpoint",
        default="http://localhost:8100/ingest/logs",
        help="Log ingest HTTP endpoint URL.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Delay between requests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP request timeout.",
    )
    args = parser.parse_args()

    responses = send_dataset(
        dataset_path=args.dataset,
        endpoint=args.endpoint,
        delay_seconds=args.delay_seconds,
        timeout=args.timeout,
    )

    total_logs = sum(response.get("accepted", 0) for response in responses)
    print(
        json.dumps(
            {
                "status": "sent",
                "requests": len(responses),
                "accepted_logs": total_logs,
                "dataset": str(args.dataset),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
