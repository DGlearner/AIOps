import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from crossst.core.config import get_settings
from crossst.domain.schemas.alerts import AlertMessage
from crossst.domain.schemas.incidents import IncidentMessage
from crossst.services.correlation.rules import (
    build_aggregate_key,
    build_incident_cache_key,
    build_incident_from_alerts,
)
from crossst.infrastructure.storage.incidents import (
    get_incident_by_id,
    save_new_incident,
    update_existing_incident,
)
from crossst.infrastructure.storage.kafka import (
    create_kafka_consumer,
    create_kafka_producer,
    send_json_message,
)
from crossst.infrastructure.storage.postgres import AsyncSessionLocal
from crossst.infrastructure.storage.redis import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()


async def load_incident_alerts_from_cache(
    cache_key: str,
) -> tuple[str, list[AlertMessage]]:
    redis = await get_redis()
    incident_id_key = f"{cache_key}:id"
    alerts_key = f"{cache_key}:alerts"

    incident_id = await redis.get(incident_id_key)
    if incident_id is None:
        incident_id = str(uuid4())
        await redis.set(incident_id_key, incident_id, ex=600)

    raw_alerts = await redis.lrange(alerts_key, 0, -1)
    alerts = [
        AlertMessage.model_validate(json.loads(raw_alert))
        for raw_alert in raw_alerts
    ]
    return incident_id, alerts


async def append_alert_to_cache(
    cache_key: str,
    alert: AlertMessage,
) -> tuple[str, list[AlertMessage]]:
    redis = await get_redis()
    incident_id_key = f"{cache_key}:id"
    alerts_key = f"{cache_key}:alerts"

    incident_id = await redis.get(incident_id_key)
    if incident_id is None:
        incident_id = str(uuid4())
        await redis.set(incident_id_key, incident_id, ex=600)

    await redis.rpush(alerts_key, alert.model_dump_json())
    await redis.expire(alerts_key, 600)

    return await load_incident_alerts_from_cache(cache_key)


async def persist_and_publish_incident(
    incident: IncidentMessage,
    producer,
) -> None:
    async with AsyncSessionLocal() as session:
        existing = await get_incident_by_id(session, incident.incident_id)
        if existing is None:
            await save_new_incident(session, incident)
        else:
            await update_existing_incident(session, existing, incident)

    await send_json_message(
        producer,
        topic=settings.kafka_incidents_topic,
        key=incident.incident_id,
        value=incident.model_dump(mode="json"),
    )


async def correlate_alert_payload(payload: dict[str, Any]) -> IncidentMessage:
    alert = AlertMessage.model_validate(payload)

    cache_key = build_incident_cache_key(alert)
    incident_id, alerts = await append_alert_to_cache(cache_key, alert)

    aggregate_key = build_aggregate_key(alert)
    return build_incident_from_alerts(
        incident_id=incident_id,
        aggregate_key=aggregate_key,
        alerts=alerts,
    )


async def run_correlation_worker() -> None:
    consumer = await create_kafka_consumer(
        topic=settings.kafka_alerts_topic,
        group_id="correlation-worker",
    )
    producer = await create_kafka_producer()

    logger.info(
        "Correlation worker started: %s -> %s",
        settings.kafka_alerts_topic,
        settings.kafka_incidents_topic,
    )

    try:
        async for message in consumer:
            try:
                incident = await correlate_alert_payload(message.value)
                await persist_and_publish_incident(incident, producer)
                logger.info(
                    "Incident emitted incident_id=%s severity=%s "
                    "alert_count=%s aggregate_key=%s",
                    incident.incident_id,
                    incident.severity,
                    incident.alert_count,
                    incident.aggregate_key,
                )
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.warning("Skip invalid alert payload: %s", exc)
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_correlation_worker())


if __name__ == "__main__":
    main()

