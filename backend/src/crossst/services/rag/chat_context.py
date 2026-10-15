from typing import Any

from crossst.services.rag.vector_store import RAGDocument


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _join_values(values: list[Any]) -> str:
    return " ".join(str(value) for value in values if value)


def build_chat_rag_query(
    *,
    question: str,
    incident: Any | None = None,
    diagnosis: dict[str, Any] | None = None,
    conversation_summary: Any | None = None,
) -> str:
    parts = [question]

    if incident is not None:
        parts.extend(
            [
                _join_values(_as_list(_get_value(incident, "affected_services"))),
                _join_values(_as_list(_get_value(incident, "affected_hosts"))),
                _join_values(_as_list(_get_value(incident, "event_types"))),
                str(_get_value(incident, "summary", "")),
            ]
        )

    if diagnosis:
        parts.extend(
            [
                str(diagnosis.get("root_cause") or ""),
                _join_values(_as_list(diagnosis.get("hypotheses"))),
                _join_values(_as_list(diagnosis.get("evidence_chain"))),
            ]
        )

    if conversation_summary is not None:
        parts.extend(
            [
                str(_get_value(conversation_summary, "compressed_context", "")),
                _join_values(_as_list(_get_value(conversation_summary, "known_facts"))),
                _join_values(_as_list(_get_value(conversation_summary, "hypotheses"))),
                _join_values(_as_list(_get_value(conversation_summary, "pending_actions"))),
            ]
        )

    return " ".join(part for part in parts if part).strip()


def infer_chat_rag_filters(
    *,
    incident: Any | None = None,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    services = _as_list(_get_value(incident, "affected_services"))
    event_types = _as_list(_get_value(incident, "event_types"))
    root_cause = (diagnosis or {}).get("root_cause")

    searchable_text = " ".join(
        [
            _join_values(event_types),
            str(_get_value(incident, "summary", "")),
            str(root_cause or ""),
        ]
    ).lower()
    component = None
    for candidate in ["mysql", "redis", "ssh", "nginx", "docker"]:
        if candidate in searchable_text:
            component = candidate
            break

    return {
        "service": str(services[0]) if services else None,
        "component": component,
        "problem_type": str(event_types[0]) if event_types else None,
        "root_cause": root_cause,
    }


def build_documents_from_diagnosis(
    diagnosis: dict[str, Any] | None,
) -> list[RAGDocument]:
    if not diagnosis:
        return []

    diagnosis_id = str(diagnosis.get("diagnosis_id") or "latest_diagnosis")
    evidence_chain = _as_list(diagnosis.get("evidence_chain"))
    recommendations = _as_list(diagnosis.get("recommendations"))
    content = "\n".join(
        part
        for part in [
            f"root_cause: {diagnosis.get('root_cause') or 'unconfirmed'}",
            f"confidence: {diagnosis.get('confidence', 0)}",
            _join_values(evidence_chain),
            _join_values(recommendations),
        ]
        if part
    )

    return [
        RAGDocument(
            document_type="diagnosis",
            source_id=diagnosis_id,
            title=f"Diagnosis {diagnosis_id}",
            content=content,
            metadata={
                "incident_id": diagnosis.get("incident_id"),
                "status": diagnosis.get("status"),
                "root_cause": diagnosis.get("root_cause"),
            },
        )
    ]


def build_documents_from_tool_calls(
    tool_calls: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[RAGDocument]:
    documents: list[RAGDocument] = []
    for tool_call in tool_calls[:limit]:
        tool_call_id = str(tool_call.get("tool_call_id") or tool_call.get("tool_name"))
        content = (
            f"tool: {tool_call.get('tool_name')}\n"
            f"reason: {tool_call.get('reason')}\n"
            f"result_count: {tool_call.get('result_count', 0)}"
        )
        documents.append(
            RAGDocument(
                document_type="tool_call",
                source_id=tool_call_id,
                title=f"Tool call {tool_call.get('tool_name')}",
                content=content,
                metadata={
                    "incident_id": tool_call.get("incident_id"),
                    "diagnosis_id": tool_call.get("diagnosis_id"),
                    "tool_name": tool_call.get("tool_name"),
                },
            )
        )
    return documents


def build_documents_from_runbooks(runbooks: list[Any]) -> list[RAGDocument]:
    documents: list[RAGDocument] = []
    for runbook in runbooks:
        runbook_id = str(_get_value(runbook, "runbook_id"))
        documents.append(
            RAGDocument(
                document_type="runbook",
                source_id=runbook_id,
                title=str(_get_value(runbook, "title", "")),
                content=str(_get_value(runbook, "content", "")),
                metadata={
                    "service": _get_value(runbook, "service"),
                    "component": _get_value(runbook, "component"),
                    "problem_types": _get_value(runbook, "problem_types", []),
                    "steps": _get_value(runbook, "steps", []),
                    "tags": _get_value(runbook, "tags", []),
                    "updated_at": (
                        _get_value(runbook, "updated_at").isoformat()
                        if _get_value(runbook, "updated_at") is not None
                        else None
                    ),
                },
            )
        )
    return documents


def build_documents_from_historical_incidents(
    historical_incidents: list[Any],
) -> list[RAGDocument]:
    documents: list[RAGDocument] = []
    for historical_incident in historical_incidents:
        historical_incident_id = str(
            _get_value(historical_incident, "historical_incident_id")
        )
        content = "\n".join(
            part
            for part in [
                str(_get_value(historical_incident, "summary", "")),
                str(_get_value(historical_incident, "resolution", "")),
                _join_values(_as_list(_get_value(historical_incident, "evidence_chain"))),
            ]
            if part
        )
        documents.append(
            RAGDocument(
                document_type="historical_incident",
                source_id=historical_incident_id,
                title=str(_get_value(historical_incident, "title", "")),
                content=content,
                metadata={
                    "service": _get_value(historical_incident, "service"),
                    "component": _get_value(historical_incident, "component"),
                    "root_cause": _get_value(historical_incident, "root_cause"),
                    "tags": _get_value(historical_incident, "tags", []),
                    "occurred_at": (
                        _get_value(historical_incident, "occurred_at").isoformat()
                        if _get_value(historical_incident, "occurred_at") is not None
                        else None
                    ),
                },
            )
        )
    return documents


def build_chat_rag_context_payload(
    *,
    query: str,
    diagnosis: dict[str, Any] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    runbooks: list[Any] | None = None,
    historical_incidents: list[Any] | None = None,
    retrieval_mode: str = "postgres_text",
) -> dict[str, Any]:
    documents = [
        *build_documents_from_diagnosis(diagnosis),
        *build_documents_from_tool_calls(tool_calls or []),
        *build_documents_from_runbooks(runbooks or []),
        *build_documents_from_historical_incidents(historical_incidents or []),
    ]
    document_payloads = [document.to_payload() for document in documents]

    return {
        "query": query,
        "retrieval_mode": retrieval_mode,
        "document_count": len(documents),
        "documents": document_payloads,
        "references": [
            {
                "document_type": document.document_type,
                "source_id": document.source_id,
                "title": document.title,
                "score": document.score,
            }
            for document in documents
        ],
        "milvus_ready": True,
    }

