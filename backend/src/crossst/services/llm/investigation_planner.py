import json
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from crossst.core.config import Settings, get_settings


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
        raise ValueError("Planner response did not contain a JSON object.")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Planner response JSON must be an object.")
    return parsed


def build_investigation_planner_prompt_messages(
    *,
    question: str,
    incident: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
    evidence_chain: list[str],
    remaining_tool_calls: int,
    allowed_tools: list[str],
) -> list[BaseMessage]:
    system = SystemMessage(
        content=(
            "你是企业内部 AIOps 调查规划器，只负责选择下一次只读工具查询。"
            "不要输出解释性 Markdown，不要请求执行重启、删除、修改配置等操作。"
            "只输出 JSON，字段固定为 tool, reason, kwargs。"
            "tool 必须来自 allowed_tools。kwargs 只放查询过滤条件。"
        )
    )
    human = HumanMessage(
        content=(
            f"question: {question}\n\n"
            f"incident: {_compact_json(incident or {})}\n\n"
            f"diagnosis: {_compact_json(diagnosis or {})}\n\n"
            f"tool_calls: {_compact_json(tool_calls[-8:])}\n\n"
            f"evidence_chain: {_compact_json(evidence_chain[-8:])}\n\n"
            f"remaining_tool_calls: {remaining_tool_calls}\n\n"
            f"allowed_tools: {_compact_json(allowed_tools)}\n\n"
            "返回示例："
            '{"tool":"query_events","reason":"Check MySQL errors.",'
            '"kwargs":{"source_type":"mysql","event_type":"mysql_connection_refused","limit":20}}'
        )
    )
    return [system, human]


class LangChainInvestigationPlannerProvider:
    def __init__(self, chat_model: BaseChatModel) -> None:
        self.chat_model = chat_model

    async def propose_next_step(
        self,
        *,
        question: str,
        incident: dict[str, Any] | None,
        diagnosis: dict[str, Any] | None,
        tool_calls: list[dict[str, Any]],
        evidence_chain: list[str],
        remaining_tool_calls: int,
        allowed_tools: list[str],
    ) -> dict[str, Any] | None:
        messages = build_investigation_planner_prompt_messages(
            question=question,
            incident=incident,
            diagnosis=diagnosis,
            tool_calls=tool_calls,
            evidence_chain=evidence_chain,
            remaining_tool_calls=remaining_tool_calls,
            allowed_tools=allowed_tools,
        )
        response = await self.chat_model.ainvoke(messages)
        try:
            return _extract_json_object(str(response.content))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None


def build_langchain_investigation_planner_provider(
    settings: Settings | None = None,
) -> LangChainInvestigationPlannerProvider | None:
    settings = settings or get_settings()
    if (
        not settings.llm_enabled
        or not settings.chat_investigation_llm_planner_enabled
        or not settings.llm_model
    ):
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
    return LangChainInvestigationPlannerProvider(chat_model=chat_model)


def build_configured_langchain_investigation_planner_provider(
    settings: Settings | None = None,
) -> tuple[LangChainInvestigationPlannerProvider | None, str | None]:
    try:
        return build_langchain_investigation_planner_provider(settings), None
    except Exception as exc:
        return None, type(exc).__name__

