"""
Diagnosis Worker

职责：
- 持续消费 Kafka topic: agent_tasks。
- 针对中高危、跨组件或原因不明确的 Incident 启动诊断流程。
- 通过 LangGraph 编排多个诊断节点和工具调用。
- 查询事件、告警、服务依赖、历史故障、Runbook 等上下文。
- 生成 DiagnosisReport，并写入 PostgreSQL。

边界：
- 只处理需要智能分析的 Incident。
- 不参与 L0-L3 的实时规则检测链路。
- 工具调用需要有次数上限和审计记录，避免无限循环。
"""


import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from crossst.application.agents.langgraph_diagnosis import run_langgraph_diagnosis
from crossst.core.config import get_settings
from crossst.domain.schemas.incidents import IncidentMessage
from crossst.infrastructure.storage.kafka import create_kafka_consumer

logger = logging.getLogger(__name__)
settings = get_settings()


def build_incident_context_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    incident = IncidentMessage.model_validate(payload)
    return {
        "incident_id": incident.incident_id,
        "summary": incident.summary,
        "event_types": incident.event_types,
        "affected_hosts": incident.affected_hosts,
        "affected_services": incident.affected_services,
        "aggregate_key": incident.aggregate_key,
        "time_window_start": incident.time_window_start.isoformat(),
        "time_window_end": incident.time_window_end.isoformat(),
    }


async def diagnose_incident_payload(payload: dict[str, Any]):
    incident_context = build_incident_context_from_payload(payload)
    return await run_langgraph_diagnosis(
        incident=incident_context,
        max_tool_calls=5,
        persist=True,
    )


async def run_diagnosis_worker() -> None:
    consumer = await create_kafka_consumer(
        topic=settings.kafka_incidents_topic,
        group_id="diagnosis-worker",
    )

    logger.info("Diagnosis worker started: %s -> incident_diagnoses", settings.kafka_incidents_topic)

    try:
        async for message in consumer:
            try:
                report = await diagnose_incident_payload(message.value)
                logger.info(
                    "Diagnosis completed diagnosis_id=%s incident_id=%s status=%s confidence=%s",
                    report.diagnosis_id,
                    report.incident_id,
                    report.status,
                    report.confidence,
                )
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.warning("Skip invalid incident payload: %s", exc)
    finally:
        await consumer.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_diagnosis_worker())


if __name__ == "__main__":
    main()

