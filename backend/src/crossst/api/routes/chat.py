from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from crossst.application.agents.chat_investigation import run_chat_investigation
from crossst.application.agents.chat_router import run_chat_router
from crossst.application.agents.incident_context import build_incident_context_from_record
from crossst.api.routes.diagnosis import serialize_diagnosis_record
from crossst.api.routes.ops import serialize_tool_call
from crossst.core.config import get_settings
from crossst.domain.schemas.conversations import (
    ConversationMessageCreate,
    ConversationMessageRecord,
    ConversationSessionCreate,
    ConversationSessionRecord,
    ConversationSessionUpdate,
)
from crossst.services.chat.memory import build_chat_memory_context
from crossst.services.chat.intent import classify_chat_intent
from crossst.services.chat.reply import build_chat_reply
from crossst.services.llm.chat import build_configured_langchain_chat_provider
from crossst.services.llm.investigation_planner import (
    build_configured_langchain_investigation_planner_provider,
)
from crossst.services.rag.chat_context import (
    build_chat_rag_context_payload,
    build_chat_rag_query,
    infer_chat_rag_filters,
)
from crossst.infrastructure.storage.conversations import (
    get_conversation_session,
    get_conversation_team_id,
    get_latest_conversation_summary,
    query_conversation_messages,
    query_conversation_sessions,
    save_conversation_message,
    save_conversation_session,
    update_conversation_session,
)
from crossst.infrastructure.storage.diagnoses import get_latest_diagnosis_for_incident
from crossst.infrastructure.storage.incidents import get_incident_by_id
from crossst.infrastructure.storage.knowledge import query_historical_incidents, query_runbooks
from crossst.infrastructure.storage.postgres import AsyncSessionLocal
from crossst.infrastructure.storage.tool_calls import query_tool_calls

router = APIRouter(prefix="/chat", tags=["chat"])


def serialize_conversation_session(record) -> dict[str, Any]:
    return {
        "session_id": record.session_id,
        "user_id": record.user_id,
        "team_id": get_conversation_team_id(record),
        "current_incident_id": record.current_incident_id,
        "title": record.title,
        "status": record.status,
        "metadata": record.extra,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def ensure_conversation_access(
    record,
    *,
    user_id: str | None = None,
    team_id: str | None = None,
) -> None:
    if user_id is not None and record.user_id != user_id:
        raise HTTPException(status_code=403, detail="Conversation session access denied")
    if team_id is not None and get_conversation_team_id(record) != team_id:
        raise HTTPException(status_code=403, detail="Conversation session access denied")


def serialize_conversation_message(record) -> dict[str, Any]:
    return {
        "message_id": record.message_id,
        "session_id": record.session_id,
        "incident_id": record.incident_id,
        "role": record.role,
        "content": record.content,
        "metadata": record.extra,
        "created_at": record.created_at.isoformat(),
    }


def serialize_conversation_summary(record) -> dict[str, Any]:
    return {
        "summary_id": record.summary_id,
        "session_id": record.session_id,
        "current_incident_id": record.current_incident_id,
        "known_facts": record.known_facts,
        "checked_tools": record.checked_tools,
        "hypotheses": record.hypotheses,
        "pending_actions": record.pending_actions,
        "compressed_context": record.compressed_context,
        "message_count": record.message_count,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def build_default_session_title(payload: ConversationSessionCreate) -> str:
    if payload.title:
        return payload.title
    if payload.current_incident_id:
        return f"Incident {payload.current_incident_id}"
    return "Ops Chat Session"


def build_user_message_metadata(
    *,
    payload_metadata: dict[str, Any],
    detected_intent: str,
) -> dict[str, Any]:
    return {
        **payload_metadata,
        "detected_intent": detected_intent,
    }


def build_assistant_message_metadata(
    *,
    reply: dict[str, Any],
    detected_intent: str,
    rag_context: dict[str, Any] | None,
    route_result: dict[str, Any] | None = None,
    investigation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reply_metadata = reply.get("metadata", {}) or {}
    route_result = route_result or {}
    investigation_result = investigation_result or {}
    investigation_tool_calls = investigation_result.get("tool_calls") or []
    return {
        "intent": reply.get("intent"),
        "detected_intent": detected_intent,
        "chat_route": route_result.get("chat_route"),
        "route_reason": route_result.get("route_reason"),
        "requires_tool_investigation": route_result.get(
            "requires_tool_investigation",
            False,
        ),
        "llm_intent": reply_metadata.get("llm_intent"),
        "provider": reply_metadata.get("provider", "unknown"),
        "llm_fallback_reason": reply_metadata.get("llm_fallback_reason"),
        "evidence_refs": reply.get("evidence_refs", []),
        "confidence": reply.get("confidence"),
        "needs_human_review": reply.get("needs_human_review"),
        "recommended_actions": reply.get("recommended_actions", []),
        "action_plan": reply.get("action_plan", []),
        "rag_reference_count": len((rag_context or {}).get("references", [])),
        "investigation_status": investigation_result.get("status"),
        "investigation_stop_reason": investigation_result.get("stop_reason"),
        "investigation_planner_provider": investigation_result.get(
            "planner_provider"
        ),
        "investigation_planner_fallback_reason": investigation_result.get(
            "planner_fallback_reason"
        ),
        "investigation_confidence": investigation_result.get("confidence"),
        "investigation_root_cause": investigation_result.get("root_cause"),
        "investigation_needs_human_review": investigation_result.get(
            "needs_human_review"
        ),
        "investigation_tool_call_count": investigation_result.get(
            "tool_call_count",
            0,
        ),
        "investigation_checked_tools": [
            {
                "tool_name": tool_call.get("tool_name"),
                "reason": tool_call.get("reason"),
                "result_count": tool_call.get("result_count", 0),
            }
            for tool_call in investigation_tool_calls
        ],
        "investigation_fallback_report": investigation_result.get("fallback_report"),
    }


def serialize_runbook(record) -> dict[str, Any]:
    return {
        "runbook_id": record.runbook_id,
        "title": record.title,
        "service": record.service,
        "component": record.component,
        "problem_types": record.problem_types,
        "content": record.content,
        "steps": record.steps,
        "tags": record.tags,
        "metadata": record.extra,
        "is_active": record.is_active,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def serialize_historical_incident(record) -> dict[str, Any]:
    return {
        "historical_incident_id": record.historical_incident_id,
        "title": record.title,
        "service": record.service,
        "component": record.component,
        "root_cause": record.root_cause,
        "summary": record.summary,
        "resolution": record.resolution,
        "evidence_chain": record.evidence_chain,
        "tags": record.tags,
        "metadata": record.extra,
        "occurred_at": record.occurred_at.isoformat(),
        "created_at": record.created_at.isoformat(),
    }


async def build_session_rag_context(
    session,
    *,
    conversation,
    question: str,
    diagnosis_payload: dict[str, Any] | None = None,
    tool_calls_payload: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    incident = None
    if conversation.current_incident_id:
        incident = await get_incident_by_id(session, conversation.current_incident_id)

    query = build_chat_rag_query(
        question=question,
        incident=incident,
        diagnosis=diagnosis_payload,
        conversation_summary=None,
    )
    filters = infer_chat_rag_filters(
        incident=incident,
        diagnosis=diagnosis_payload,
    )
    runbooks = await query_runbooks(
        session,
        query=query or None,
        service=filters["service"],
        component=filters["component"],
        active_only=True,
        limit=5,
    )
    if not runbooks and filters["service"]:
        runbooks = await query_runbooks(
            session,
            service=filters["service"],
            component=filters["component"],
            active_only=True,
            limit=5,
        )

    historical_incidents = await query_historical_incidents(
        session,
        query=query or None,
        service=filters["service"],
        component=filters["component"],
        root_cause=filters["root_cause"],
        limit=5,
    )
    if not historical_incidents and filters["service"]:
        historical_incidents = await query_historical_incidents(
            session,
            service=filters["service"],
            component=filters["component"],
            root_cause=filters["root_cause"],
            limit=5,
        )

    payload = build_chat_rag_context_payload(
        query=query,
        diagnosis=diagnosis_payload,
        tool_calls=tool_calls_payload or [],
        runbooks=runbooks,
        historical_incidents=historical_incidents,
    )
    payload["filters"] = filters
    payload["runbooks"] = [serialize_runbook(runbook) for runbook in runbooks]
    payload["historical_incidents"] = [
        serialize_historical_incident(historical_incident)
        for historical_incident in historical_incidents
    ]
    return payload


@router.post("/sessions")
async def create_chat_session(payload: ConversationSessionCreate) -> dict[str, Any]:
    conversation = ConversationSessionRecord(
        user_id=payload.user_id,
        team_id=payload.team_id,
        current_incident_id=payload.current_incident_id,
        title=build_default_session_title(payload),
        metadata=payload.metadata,
    )

    async with AsyncSessionLocal() as session:
        await save_conversation_session(session, conversation)

    return conversation.model_dump(mode="json")


@router.get("/sessions")
async def list_chat_sessions(
    user_id: str | None = None,
    team_id: str | None = None,
    incident_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        sessions = await query_conversation_sessions(
            session,
            user_id=user_id,
            team_id=team_id,
            incident_id=incident_id,
            status=status,
            limit=limit,
        )

    return {
        "count": len(sessions),
        "sessions": [serialize_conversation_session(record) for record in sessions],
    }


@router.patch("/sessions/{session_id}")
async def update_chat_session(
    session_id: str,
    payload: ConversationSessionUpdate,
    user_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    title = payload.title.strip() if payload.title is not None else None
    if title == "":
        raise HTTPException(status_code=422, detail="Conversation session title cannot be empty")

    async with AsyncSessionLocal() as session:
        conversation = await get_conversation_session(session, session_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation session not found")
        ensure_conversation_access(conversation, user_id=user_id, team_id=team_id)
        await update_conversation_session(
            session,
            conversation,
            title=title,
            status=payload.status,
            updated_at=datetime.now(timezone.utc),
        )

    return serialize_conversation_session(conversation)


@router.get("/sessions/{session_id}/messages")
async def list_chat_messages(
    session_id: str,
    before_created_at: datetime | None = None,
    newest_first: bool = True,
    user_id: str | None = None,
    team_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        conversation = await get_conversation_session(session, session_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation session not found")
        ensure_conversation_access(conversation, user_id=user_id, team_id=team_id)
        messages = await query_conversation_messages(
            session,
            session_id=session_id,
            before_created_at=before_created_at,
            newest_first=newest_first,
            limit=limit,
        )

    return {
        "session_id": session_id,
        "count": len(messages),
        "limit": limit,
        "newest_first": newest_first,
        "next_before_created_at": (
            messages[-1].created_at.isoformat() if messages else None
        ),
        "messages": [serialize_conversation_message(message) for message in messages],
    }


@router.post("/sessions/{session_id}/messages")
async def create_chat_message(
    session_id: str,
    payload: ConversationMessageCreate,
    user_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        conversation = await get_conversation_session(session, session_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation session not found")
        ensure_conversation_access(conversation, user_id=user_id, team_id=team_id)

        incident_id = payload.incident_id or conversation.current_incident_id
        detected_intent = classify_chat_intent(payload.content)
        route_result = await run_chat_router(
            question=payload.content,
            detected_intent=detected_intent,
        )
        user_message = ConversationMessageRecord(
            session_id=session_id,
            incident_id=incident_id,
            role=payload.role,
            content=payload.content,
            metadata=build_user_message_metadata(
                payload_metadata=payload.metadata,
                detected_intent=detected_intent,
            ),
        )
        await save_conversation_message(session, user_message)
        messages_before_reply = await query_conversation_messages(
            session,
            session_id=session_id,
            newest_first=False,
            limit=settings.chat_memory_query_limit,
        )
        memory_context = build_chat_memory_context(
            messages=messages_before_reply,
            summary=None,
            window_size=settings.chat_memory_window_size,
        )

        latest_diagnosis = None
        incident_record = None
        tool_call_records = []
        if incident_id:
            incident_record = await get_incident_by_id(session, incident_id)
            latest_diagnosis = await get_latest_diagnosis_for_incident(session, incident_id)
            tool_call_records = await query_tool_calls(
                session,
                incident_id=incident_id,
                limit=20,
            )

        diagnosis_payload = (
            serialize_diagnosis_record(latest_diagnosis) if latest_diagnosis else None
        )
        tool_calls_payload = [
            serialize_tool_call(tool_call) for tool_call in tool_call_records
        ]
        incident_context = (
            build_incident_context_from_record(incident_record)
            if incident_record is not None
            else None
        )
        investigation_result = None
        if route_result.get("chat_route") == "investigate_with_tools":
            planner_provider, planner_fallback_reason = (
                build_configured_langchain_investigation_planner_provider()
            )
            investigation_result = await run_chat_investigation(
                question=payload.content,
                incident=incident_context,
                diagnosis=diagnosis_payload,
                max_tool_calls=5,
                planner_provider=planner_provider,
            )
            investigation_result["planner_provider"] = (
                "langchain" if planner_provider is not None else "deterministic"
            )
            investigation_result["planner_fallback_reason"] = planner_fallback_reason
        investigation_tool_calls = (
            (investigation_result or {}).get("tool_calls") or []
        )
        combined_tool_calls_payload = [
            *tool_calls_payload,
            *investigation_tool_calls,
        ]
        rag_context = await build_session_rag_context(
            session,
            conversation=conversation,
            question=payload.content,
            diagnosis_payload=diagnosis_payload,
            tool_calls_payload=combined_tool_calls_payload,
        )
        llm_provider, llm_fallback_reason = build_configured_langchain_chat_provider()
        reply = await build_chat_reply(
            question=payload.content,
            diagnosis=diagnosis_payload,
            tool_calls=combined_tool_calls_payload,
            rag_context=rag_context,
            memory_context=memory_context,
            detected_intent=detected_intent,
            investigation_result=investigation_result,
            llm_provider=llm_provider,
            llm_fallback_reason=llm_fallback_reason,
        )

        assistant_message = ConversationMessageRecord(
            session_id=session_id,
            incident_id=incident_id,
            role="assistant",
            content=reply["content"],
            metadata=build_assistant_message_metadata(
                reply=reply,
                detected_intent=detected_intent,
                rag_context=rag_context,
                route_result=route_result,
                investigation_result=investigation_result,
            ),
        )
        await save_conversation_message(session, assistant_message)

    return {
        "session_id": session_id,
        "user_message": user_message.model_dump(mode="json"),
        "assistant_message": assistant_message.model_dump(mode="json"),
        "reply": reply,
        "chat_route": route_result.get("chat_route"),
        "route_result": route_result,
        "investigation_result": investigation_result,
        "memory_context": memory_context,
    }


@router.get("/sessions/{session_id}/context")
async def get_chat_context(
    session_id: str,
    user_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        conversation = await get_conversation_session(session, session_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation session not found")
        ensure_conversation_access(conversation, user_id=user_id, team_id=team_id)

        messages = await query_conversation_messages(
            session,
            session_id=session_id,
            limit=settings.chat_memory_query_limit,
        )
        summary = await get_latest_conversation_summary(session, session_id)
        memory_context = build_chat_memory_context(
            messages=messages,
            summary=None,
            window_size=settings.chat_memory_window_size,
        )

        latest_diagnosis = None
        tool_call_records = []
        if conversation.current_incident_id:
            latest_diagnosis = await get_latest_diagnosis_for_incident(
                session,
                conversation.current_incident_id,
            )
            tool_call_records = await query_tool_calls(
                session,
                incident_id=conversation.current_incident_id,
                limit=50,
            )

        diagnosis_payload = (
            serialize_diagnosis_record(latest_diagnosis) if latest_diagnosis else None
        )
        tool_calls_payload = [
            serialize_tool_call(tool_call) for tool_call in tool_call_records
        ]
        rag_context = await build_session_rag_context(
            session,
            conversation=conversation,
            question="",
            diagnosis_payload=diagnosis_payload,
            tool_calls_payload=tool_calls_payload,
        )

    return {
        "session": serialize_conversation_session(conversation),
        "summary": serialize_conversation_summary(summary) if summary else None,
        "messages": [serialize_conversation_message(message) for message in messages],
        "latest_diagnosis": diagnosis_payload,
        "tool_calls": tool_calls_payload,
        "rag_context": rag_context,
        "memory_context": memory_context,
    }


@router.get("/sessions/{session_id}/rag-context")
async def get_chat_rag_context(
    session_id: str,
    question: str = "",
    user_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        conversation = await get_conversation_session(session, session_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation session not found")
        ensure_conversation_access(conversation, user_id=user_id, team_id=team_id)

        latest_diagnosis = None
        tool_call_records = []
        if conversation.current_incident_id:
            latest_diagnosis = await get_latest_diagnosis_for_incident(
                session,
                conversation.current_incident_id,
            )
            tool_call_records = await query_tool_calls(
                session,
                incident_id=conversation.current_incident_id,
                limit=20,
            )

        diagnosis_payload = (
            serialize_diagnosis_record(latest_diagnosis) if latest_diagnosis else None
        )
        tool_calls_payload = [
            serialize_tool_call(tool_call) for tool_call in tool_call_records
        ]
        rag_context = await build_session_rag_context(
            session,
            conversation=conversation,
            question=question,
            diagnosis_payload=diagnosis_payload,
            tool_calls_payload=tool_calls_payload,
        )

    return {
        "session_id": session_id,
        "rag_context": rag_context,
    }

