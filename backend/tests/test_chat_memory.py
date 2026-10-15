from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from crossst.services.chat.memory import build_chat_memory_context
from crossst.services.llm.chat import build_chat_prompt_messages


def _message(index: int, role: str = "user"):
    return SimpleNamespace(
        message_id=f"msg-{index}",
        session_id="session-001",
        incident_id="incident-001",
        role=role,
        content=f"message {index}",
        extra={},
        created_at=datetime(2026, 6, 5, 10, index, tzinfo=timezone.utc),
    )


def test_build_chat_memory_context_keeps_recent_window_and_ignores_summary_for_mvp():
    messages = [_message(index) for index in range(6)]
    summary = SimpleNamespace(
        known_facts=["mysql error existed"],
        checked_tools=["query_events"],
        hypotheses=["mysql unavailable"],
        pending_actions=["check mysql process"],
        compressed_context="Earlier context summary.",
        message_count=2,
    )

    context = build_chat_memory_context(
        messages=messages,
        summary=summary,
        window_size=3,
    )

    assert [item["message_id"] for item in context["recent_messages"]] == [
        "msg-3",
        "msg-4",
        "msg-5",
    ]
    assert context["older_messages"] == []
    assert context["summary"]["compressed_context"] == ""
    assert context["summary"]["message_count"] == 0
    assert context["window_size"] == 3


def test_build_chat_prompt_messages_includes_recent_window_without_summary_context():
    memory_context = {
        "summary": {
            "compressed_context": "Earlier compressed context.",
            "known_facts": ["mysql error existed"],
            "checked_tools": [],
            "hypotheses": [],
            "pending_actions": [],
        },
        "recent_messages": [
            {
                "role": "user",
                "content": "刚刚查到 MySQL 连接失败",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }

    messages = build_chat_prompt_messages(
        question="继续分析",
        diagnosis=None,
        tool_calls=[],
        rag_context=None,
        memory_context=memory_context,
    )

    rendered = "\n".join(message.content for message in messages)

    assert "历史压缩上下文" not in rendered
    assert "Earlier compressed context." not in rendered
    assert "刚刚查到 MySQL 连接失败" in rendered

