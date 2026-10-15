import json
from typing import Any

from aiokafka import AIOKafkaProducer

from log_ingest.config import get_settings

settings = get_settings()


def json_serializer(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def key_serializer(value: str | None) -> bytes | None:
    if value is None:
        return None
    return value.encode("utf-8")


async def create_kafka_producer() -> AIOKafkaProducer:
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=json_serializer,
        key_serializer=key_serializer,
    )
    await producer.start()
    return producer


async def send_json_message(
    producer: AIOKafkaProducer,
    *,
    topic: str,
    value: dict[str, Any],
    key: str | None = None,
) -> None:
    await producer.send_and_wait(topic, value=value, key=key)


async def check_kafka() -> bool:
    producer = await create_kafka_producer()
    try:
        return True
    finally:
        await producer.stop()
