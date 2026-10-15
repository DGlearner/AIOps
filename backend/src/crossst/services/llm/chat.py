import json
from typing import Any, Protocol

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from crossst.core.config import Settings, get_settings
from crossst.services.chat.intent import CHAT_INTENTS
from crossst.services.llm.schemas import LLMChatOutput, validate_llm_chat_output


class ChatReplyProvider(Protocol):
    async def generate_chat_reply(
        self,
        *,
        question: str,
        diagnosis: dict[str, Any] | None,
        tool_calls: list[dict[str, Any]],
        rag_context: dict[str, Any] | None,
        memory_context: dict[str, Any] | None = None,
        detected_intent: str | None = None,
        investigation_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


def _reference_id(reference: dict[str, Any]) -> str:
    return f"{reference.get('document_type')}:{reference.get('source_id')}"


def _append_ref(refs: list[str], value: Any, prefix: str) -> None:
    if value is not None:
        refs.append(f"{prefix}:{value}")


def build_allowed_evidence_refs(
    *,
    diagnosis: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
    rag_context: dict[str, Any] | None,
) -> list[str]:
    refs: list[str] = []
    if diagnosis:
        _append_ref(refs, diagnosis.get("diagnosis_id"), "diagnosis")
        _append_ref(refs, diagnosis.get("incident_id"), "incident")

    for tool_call in tool_calls[:10]:
        _append_ref(refs, tool_call.get("tool_call_id"), "tool_call")
        _append_ref(refs, tool_call.get("tool_name"), "tool")

    for reference in (rag_context or {}).get("references") or []:
        refs.append(_reference_id(reference))

    return list(dict.fromkeys(refs))


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain a JSON object.")
    return json.loads(stripped[start : end + 1])


def build_chat_prompt_messages(
    *,
    question: str,
    diagnosis: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
    rag_context: dict[str, Any] | None,
    memory_context: dict[str, Any] | None = None,
    detected_intent: str | None = None,
    investigation_result: dict[str, Any] | None = None,
) -> list[BaseMessage]:
    references = (rag_context or {}).get("references") or []
    documents = (rag_context or {}).get("documents") or []
    allowed_evidence_refs = build_allowed_evidence_refs(
        diagnosis=diagnosis,
        tool_calls=tool_calls,
        rag_context=rag_context,
    )
    compact_documents = [
        {
            "ref": _reference_id(document),
            "title": document.get("title"),
            "content": document.get("content"),
        }
        for document in documents[:8]
    ]
    recent_messages = (memory_context or {}).get("recent_messages") or []
    compact_recent_messages = [
        {
            "role": message.get("role"),
            "content": message.get("content"),
            "created_at": message.get("created_at"),
        }
        for message in recent_messages[-12:]
    ]

    system = SystemMessage(
        content=(
            "你是企业内部 AIOps 运维助手。你只能基于提供的诊断、工具调用和 RAG "
            "上下文回答。不要编造不存在的日志、指标或工具结果。"
            "如果证据不足，设置 needs_human_review=true。"
            "evidence_refs 只能使用用户消息中列出的可引用证据 ID。"
            "intent 必须使用系统识别意图，不要发明新的 intent。"
            "必须输出 JSON，不要输出 Markdown。JSON 字段固定为："
            "intent, answer, evidence_refs, confidence, needs_human_review, "
            "recommended_actions。"
        )
    )
    human = HumanMessage(
        content=(
            f"用户问题：{question}\n\n"
            f"系统识别意图：{detected_intent or 'general_question'}\n\n"
            f"允许的 intent：{_compact_json(list(CHAT_INTENTS))}\n\n"
            f"最新诊断：{_compact_json(diagnosis or {})}\n\n"
            f"最近对话窗口：{_compact_json(compact_recent_messages)}\n\n"
            f"工具调用摘要：{_compact_json(tool_calls[:10])}\n\n"
            f"本轮工具调查：{_compact_json(investigation_result or {})}\n\n"
            f"可引用证据 ID：{_compact_json(allowed_evidence_refs)}\n\n"
            f"可引用资料：{_compact_json([_reference_id(ref) for ref in references])}\n\n"
            f"RAG 文档：{_compact_json(compact_documents)}"
        )
    )
    return [system, human]


class LangChainChatProvider:
    def __init__(self, chat_model: BaseChatModel) -> None:
        self.chat_model = chat_model

    async def generate_chat_reply(
        self,
        *,
        question: str,
        diagnosis: dict[str, Any] | None,
        tool_calls: list[dict[str, Any]],
        rag_context: dict[str, Any] | None,
        memory_context: dict[str, Any] | None = None,
        detected_intent: str | None = None,
        investigation_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        messages = build_chat_prompt_messages(
            question=question,
            diagnosis=diagnosis,
            tool_calls=tool_calls,
            rag_context=rag_context,
            memory_context=memory_context,
            detected_intent=detected_intent,
            investigation_result=investigation_result,
        )
        response = await self.chat_model.ainvoke(messages)
        parsed = _extract_json_object(str(response.content))
        raw_output = LLMChatOutput.model_validate(parsed)
        output = validate_llm_chat_output(
            raw_output,
            allowed_evidence_refs=set(
                build_allowed_evidence_refs(
                    diagnosis=diagnosis,
                    tool_calls=tool_calls,
                    rag_context=rag_context,
                )
            ),
            detected_intent=detected_intent,
        )

        return {
            "intent": output.intent,
            "content": output.answer,
            "evidence_refs": output.evidence_refs,
            "confidence": output.confidence,
            "needs_human_review": output.needs_human_review,
            "recommended_actions": output.recommended_actions,
            "action_plan": output.action_plan,
            "metadata": {
                "provider": "langchain",
                "detected_intent": detected_intent,
                "llm_intent": raw_output.intent,
            },
        }


def build_langchain_chat_provider(
    settings: Settings | None = None,
) -> LangChainChatProvider | None:
    settings = settings or get_settings()
    if not settings.llm_enabled or not settings.llm_model:
        return None

    model_kwargs: dict[str, Any] = {
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
        "timeout": settings.llm_timeout_seconds,
    }
    if settings.llm_api_key:
        model_kwargs["api_key"] = settings.llm_api_key
    if settings.llm_base_url:
        model_kwargs["base_url"] = settings.llm_base_url

    chat_model = init_chat_model(
        settings.llm_model,
        model_provider=settings.llm_provider,
        **model_kwargs,
    )
    return LangChainChatProvider(chat_model=chat_model)


def build_configured_langchain_chat_provider(
    settings: Settings | None = None,
) -> tuple[LangChainChatProvider | None, str | None]:
    try:
        return build_langchain_chat_provider(settings), None
    except Exception as exc:
        return None, type(exc).__name__


async def build_llm_chat_reply(
    *,
    provider: ChatReplyProvider | None,
    question: str,
    diagnosis: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
    rag_context: dict[str, Any] | None,
    memory_context: dict[str, Any] | None = None,
    detected_intent: str | None = None,
    investigation_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if provider is None:
        return None
    return await provider.generate_chat_reply(
        question=question,
        diagnosis=diagnosis,
        tool_calls=tool_calls,
        rag_context=rag_context,
        memory_context=memory_context,
        detected_intent=detected_intent,
        investigation_result=investigation_result,
    )

