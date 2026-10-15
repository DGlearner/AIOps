from typing import Any

from crossst.services.chat.rules import build_rule_based_chat_reply
from crossst.services.llm.chat import ChatReplyProvider, build_llm_chat_reply


async def build_chat_reply(
    *,
    question: str,
    diagnosis: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
    rag_context: dict[str, Any] | None,
    memory_context: dict[str, Any] | None = None,
    detected_intent: str | None = None,
    investigation_result: dict[str, Any] | None = None,
    llm_provider: ChatReplyProvider | None,
    llm_fallback_reason: str | None = None,
) -> dict[str, Any]:
    try:
        llm_reply = await build_llm_chat_reply(
            provider=llm_provider,
            question=question,
            diagnosis=diagnosis,
            tool_calls=tool_calls,
            rag_context=rag_context,
            memory_context=memory_context,
            detected_intent=detected_intent,
            investigation_result=investigation_result,
        )
    except Exception as exc:
        fallback = build_rule_based_chat_reply(
            question=question,
            diagnosis=diagnosis,
            tool_calls=tool_calls,
            rag_context=rag_context,
            investigation_result=investigation_result,
        )
        fallback["metadata"] = {
            **fallback.get("metadata", {}),
            "provider": "rules",
            "llm_fallback_reason": type(exc).__name__,
            "detected_intent": detected_intent,
        }
        if detected_intent is not None:
            fallback["intent"] = detected_intent
        return fallback

    if llm_reply is not None:
        return llm_reply

    fallback = build_rule_based_chat_reply(
        question=question,
        diagnosis=diagnosis,
        tool_calls=tool_calls,
        rag_context=rag_context,
        investigation_result=investigation_result,
    )
    fallback["metadata"] = {
        **fallback.get("metadata", {}),
        "provider": "rules",
        "detected_intent": detected_intent,
    }
    if llm_fallback_reason is not None:
        fallback["metadata"]["llm_fallback_reason"] = llm_fallback_reason
    if detected_intent is not None:
        fallback["intent"] = detected_intent
    return fallback

