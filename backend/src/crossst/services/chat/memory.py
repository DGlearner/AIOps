from typing import Any

from crossst.domain.schemas.conversations import ConversationSummaryRecord


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _serialize_message(message: Any) -> dict[str, Any]:
    created_at = _get_value(message, "created_at")
    return {
        "message_id": _get_value(message, "message_id"),
        "session_id": _get_value(message, "session_id"),
        "incident_id": _get_value(message, "incident_id"),
        "role": _get_value(message, "role"),
        "content": _get_value(message, "content", ""),
        "metadata": _get_value(message, "extra", {})
        or _get_value(message, "metadata", {}),
        "created_at": created_at.isoformat() if created_at is not None else None,
    }


def _serialize_summary(summary: Any | None) -> dict[str, Any]:
    if summary is None:
        return {
            "known_facts": [],
            "checked_tools": [],
            "hypotheses": [],
            "pending_actions": [],
            "compressed_context": "",
            "message_count": 0,
        }
    return {
        "known_facts": _as_list(_get_value(summary, "known_facts")),
        "checked_tools": _as_list(_get_value(summary, "checked_tools")),
        "hypotheses": _as_list(_get_value(summary, "hypotheses")),
        "pending_actions": _as_list(_get_value(summary, "pending_actions")),
        "compressed_context": str(_get_value(summary, "compressed_context", "")),
        "message_count": int(_get_value(summary, "message_count", 0) or 0),
    }


def _sort_messages(messages: list[Any]) -> list[Any]:
    return sorted(messages, key=lambda message: _get_value(message, "created_at"))


def build_chat_memory_context(
    *,
    messages: list[Any],
    summary: Any | None,
    window_size: int,
) -> dict[str, Any]:
    ordered_messages = _sort_messages(messages)
    recent_messages = ordered_messages[-window_size:] if window_size > 0 else []

    return {
        "window_size": window_size,
        "summary": _serialize_summary(None),
        "recent_messages": [
            _serialize_message(message) for message in recent_messages
        ],
        "older_messages": [],
    }


def _message_summary_line(message: Any) -> str:
    role = _get_value(message, "role", "unknown")
    content = str(_get_value(message, "content", "")).replace("\n", " ").strip()
    if len(content) > 500:
        content = f"{content[:500]}..."
    return f"{role}: {content}"


def _trim_summary(text: str, max_summary_chars: int) -> str:
    if len(text) <= max_summary_chars:
        return text
    return text[-max_summary_chars:].lstrip()


def build_updated_conversation_summary(
    *,
    existing_summary: Any,
    all_messages: list[Any],
    window_size: int,
    max_summary_chars: int,
) -> ConversationSummaryRecord:
    ordered_messages = _sort_messages(all_messages)
    older_messages = ordered_messages[: max(len(ordered_messages) - window_size, 0)]
    compressed_context = "\n".join(
        _message_summary_line(message) for message in older_messages
    )

    payload = {
        "session_id": _get_value(existing_summary, "session_id"),
        "current_incident_id": _get_value(existing_summary, "current_incident_id"),
        "known_facts": _as_list(_get_value(existing_summary, "known_facts")),
        "checked_tools": _as_list(_get_value(existing_summary, "checked_tools")),
        "hypotheses": _as_list(_get_value(existing_summary, "hypotheses")),
        "pending_actions": _as_list(_get_value(existing_summary, "pending_actions")),
        "compressed_context": _trim_summary(compressed_context, max_summary_chars),
        "message_count": len(ordered_messages),
    }
    summary_id = _get_value(existing_summary, "summary_id")
    if summary_id is not None:
        payload["summary_id"] = summary_id

    return ConversationSummaryRecord(**payload)

