from aiokafka import AIOKafkaProducer
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from log_ingest.config import get_settings
from log_ingest.kafka import send_json_message
from log_ingest.schemas import IngestLogsRequest, IngestLogsResponse, RawLogMessage

router = APIRouter(tags=["ingest"])
settings = get_settings()


def build_raw_log_messages(request: IngestLogsRequest) -> list[RawLogMessage]:
    return [
        RawLogMessage(
            source_type=request.source_type,
            message=message,
            host=request.host,
            service=request.service,
            source_name=request.source_name,
        )
        for message in request.logs
    ]


async def publish_raw_logs(
    producer: AIOKafkaProducer,
    ingest_request: IngestLogsRequest,
) -> IngestLogsResponse:
    raw_logs = build_raw_log_messages(ingest_request)

    for raw_log in raw_logs:
        await send_json_message(
            producer,
            topic=settings.kafka_raw_logs_topic,
            key=raw_log.log_id,
            value=raw_log.model_dump(mode="json"),
        )

    return IngestLogsResponse(
        status="accepted",
        topic=settings.kafka_raw_logs_topic,
        accepted=len(raw_logs),
        log_ids=[raw_log.log_id for raw_log in raw_logs],
    )


@router.post("/ingest/logs", response_model=IngestLogsResponse)
async def ingest_logs_to_kafka(
    ingest_request: IngestLogsRequest,
    request: Request,
) -> IngestLogsResponse:
    producer: AIOKafkaProducer = request.app.state.kafka_producer
    return await publish_raw_logs(producer, ingest_request)


@router.websocket("/ws/ingest/logs")
async def ingest_logs_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    producer: AIOKafkaProducer = websocket.app.state.kafka_producer

    try:
        while True:
            payload = await websocket.receive_json()
            try:
                ingest_request = IngestLogsRequest.model_validate(payload)
                response = await publish_raw_logs(producer, ingest_request)
                await websocket.send_json(response.model_dump(mode="json"))
            except (ValueError, TypeError, KeyError) as exc:
                await websocket.send_json(
                    {
                        "status": "error",
                        "detail": str(exc),
                    }
                )
    except WebSocketDisconnect:
        return
