import json
import re
from typing import Any, Protocol

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, model_validator

from crossst.application.agents.diagnosis_state import DiagnosisState
from crossst.core.config import Settings, get_settings


class LLMDiagnosisOutput(BaseModel):
    root_cause: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_chain: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
    recommendations: list[str] = Field(default_factory=list)
    ruled_out_hypotheses: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_model(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        normalized["root_cause"] = _normalize_root_cause(normalized.get("root_cause"))
        for key in (
            "evidence_refs",
            "evidence_chain",
            "recommendations",
        ):
            normalized[key] = _as_str_list(normalized.get(key))
        normalized["ruled_out_hypotheses"] = _normalize_ruled_out_hypotheses(
            normalized.get("ruled_out_hypotheses")
        )
        return normalized


class DiagnosisLLMProvider(Protocol):
    def analyze_state(self, state: DiagnosisState) -> LLMDiagnosisOutput:
        ...


KNOWN_DIAGNOSIS_ROOT_CAUSES = {
    "mysql_or_database_dependency_unavailable",
    "login_service_database_dependency_error",
    "possible_credential_attack_or_bruteforce",
    "recent_deployment_or_config_change",
    "mysql_unavailable",
    "database_dependency_unavailable",
    "backend_dependency_failure_affecting_login",
    "credential_attack_or_bruteforce",
    "service_level_failure",
    "historical_similar_incident",
    "runbook_available",
    "unknown_operational_anomaly",
}


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _normalize_root_cause(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    for separator in ("：", ":"):
        if separator not in text:
            continue
        candidate = text.split(separator, 1)[0].strip(" `\"'")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{1,80}", candidate):
            return candidate
    return text


def _normalize_ruled_out_hypotheses(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [_normalize_ruled_out_hypothesis_item(item) for item in items]


def _normalize_ruled_out_hypothesis_item(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value)

    hypothesis = (
        value.get("hypothesis")
        or value.get("name")
        or value.get("id")
        or value.get("key")
        or value.get("title")
    )
    reason = (
        value.get("reason")
        or value.get("detail")
        or value.get("rationale")
        or value.get("explanation")
        or value.get("why")
    )
    if hypothesis and reason:
        return f"{hypothesis}: {reason}"
    if hypothesis:
        return str(hypothesis)
    return json.dumps(value, ensure_ascii=False, default=str)


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


def build_allowed_diagnosis_evidence_refs(state: DiagnosisState) -> list[str]:
    refs = [
        f"incident:{state['incident_id']}",
    ]
    current_hypothesis = state.get("current_hypothesis")
    if current_hypothesis:
        refs.append(f"hypothesis:{current_hypothesis}")

    for hypothesis in state.get("hypotheses", [])[:20]:
        refs.append(f"hypothesis:{hypothesis}")

    for tool_call in state.get("tool_call_summary", [])[:10]:
        tool_name = tool_call.get("tool")
        if tool_name:
            refs.append(f"tool:{tool_name}")

    for tool_call in state.get("pending_tool_calls", [])[:10]:
        tool_call_id = tool_call.get("tool_call_id")
        tool_name = tool_call.get("tool_name")
        if tool_call_id:
            refs.append(f"tool_call:{tool_call_id}")
        if tool_name:
            refs.append(f"tool:{tool_name}")

    return list(dict.fromkeys(refs))


def build_allowed_diagnosis_root_causes(state: DiagnosisState) -> list[str]:
    root_causes = list(KNOWN_DIAGNOSIS_ROOT_CAUSES)
    root_causes.extend(state.get("hypotheses", []))

    current_hypothesis = state.get("current_hypothesis")
    if current_hypothesis:
        root_causes.append(current_hypothesis)

    current_root_cause = state.get("root_cause")
    if current_root_cause:
        root_causes.append(current_root_cause)

    return list(dict.fromkeys(root_causes))


def validate_llm_diagnosis_output(
    output: LLMDiagnosisOutput,
    *,
    allowed_evidence_refs: set[str] | None = None,
    allowed_root_causes: set[str] | None = None,
) -> LLMDiagnosisOutput:
    filtered_refs = output.evidence_refs
    unsupported_refs: list[str] = []
    if allowed_evidence_refs is not None:
        filtered_refs = [
            reference
            for reference in output.evidence_refs
            if reference in allowed_evidence_refs
        ]
        unsupported_refs = [
            reference
            for reference in output.evidence_refs
            if reference not in allowed_evidence_refs
        ]

    if (
        allowed_root_causes is not None
        and output.root_cause
        and output.root_cause not in allowed_root_causes
    ):
        return output.model_copy(
            update={
                "root_cause": None,
                "evidence_refs": filtered_refs,
                "evidence_chain": [
                    "未授权根因 key 已移除，不能确认高置信诊断。"
                    f"未授权 root_cause：{output.root_cause}",
                    *output.evidence_chain,
                ],
                "confidence": min(output.confidence, 0.5),
                "needs_human_review": True,
            }
        )

    evidence_chain = output.evidence_chain
    if unsupported_refs:
        return output.model_copy(
            update={
                "evidence_refs": filtered_refs,
                "evidence_chain": [
                    "未授权证据引用已移除，不能确认高置信诊断。"
                    f"未授权引用：{unsupported_refs}",
                    *evidence_chain,
                ],
                "confidence": min(output.confidence, 0.5),
                "needs_human_review": True,
            }
        )

    if output.confidence >= 0.7 and not filtered_refs:
        return output.model_copy(
            update={
                "evidence_refs": filtered_refs,
                "evidence_chain": [
                    "缺少证据引用，不能确认高置信诊断。",
                    *evidence_chain,
                ],
                "confidence": min(output.confidence, 0.5),
                "needs_human_review": True,
            }
        )

    if filtered_refs != output.evidence_refs:
        return output.model_copy(update={"evidence_refs": filtered_refs})
    return output


def build_diagnosis_prompt_messages(state: DiagnosisState) -> list[BaseMessage]:
    allowed_refs = build_allowed_diagnosis_evidence_refs(state)
    allowed_root_causes = build_allowed_diagnosis_root_causes(state)
    compact_tool_results = [
        {
            "tool": result.get("tool"),
            "count": result.get("count", 0),
            "events": result.get("events", [])[:3],
            "alerts": result.get("alerts", [])[:3],
            "incidents": result.get("incidents", [])[:3],
            "dependencies": result.get("dependencies", [])[:3],
            "deployments": result.get("deployments", [])[:3],
            "runbooks": result.get("runbooks", [])[:3],
            "historical_incidents": result.get("historical_incidents", [])[:3],
        }
        for result in state.get("tool_results", [])[:10]
    ]

    system = SystemMessage(
        content=(
            "你是企业内部 AIOps L4 根因诊断推理器。"
            "你只能基于 Incident、当前假设和工具结果判断，不要编造日志或指标。"
            "如果证据不足，设置 needs_human_review=true。"
            "evidence_refs 只能使用用户消息中列出的可引用证据 ID。"
            "必须输出 JSON，不要输出 Markdown。JSON 字段固定为："
            "root_cause, confidence, evidence_refs, evidence_chain, "
            "needs_human_review, recommendations, ruled_out_hypotheses。"
            "所有自然语言字段必须使用简体中文，尤其是 evidence_chain、"
            "recommendations 和 ruled_out_hypotheses。"
            "root_cause 只能从用户消息列出的允许 root_cause key 中选择，不要写解释；"
            "解释必须写入 evidence_chain。"
            "ruled_out_hypotheses 请输出字符串数组，格式为 hypothesis: reason。"
        )
    )
    human = HumanMessage(
        content=(
            f"Incident：{_compact_json(state.get('incident', {}))}\n\n"
            f"触发摘要：{state.get('trigger_summary', '')}\n\n"
            f"候选假设：{_compact_json(state.get('hypotheses', []))}\n\n"
            f"当前假设：{state.get('current_hypothesis')}\n\n"
            f"已排除假设：{_compact_json(state.get('ruled_out_hypotheses', []))}\n\n"
            f"已有证据链：{_compact_json(state.get('evidence_chain', []))}\n\n"
            f"工具调用摘要：{_compact_json(state.get('tool_call_summary', []))}\n\n"
            f"工具结果样本：{_compact_json(compact_tool_results)}\n\n"
            f"可引用证据 ID：{_compact_json(allowed_refs)}\n\n"
            f"允许的 root_cause key：{_compact_json(allowed_root_causes)}"
        )
    )
    return [system, human]


class LangChainDiagnosisProvider:
    def __init__(self, chat_model: BaseChatModel) -> None:
        self.chat_model = chat_model

    def analyze_state(self, state: DiagnosisState) -> LLMDiagnosisOutput:
        messages = build_diagnosis_prompt_messages(state)
        response = self.chat_model.invoke(messages)
        parsed = _extract_json_object(str(response.content))
        raw_output = LLMDiagnosisOutput.model_validate(parsed)
        return validate_llm_diagnosis_output(
            raw_output,
            allowed_evidence_refs=set(build_allowed_diagnosis_evidence_refs(state)),
            allowed_root_causes=set(build_allowed_diagnosis_root_causes(state)),
        )


def build_langchain_diagnosis_provider(
    settings: Settings | None = None,
) -> LangChainDiagnosisProvider | None:
    settings = settings or get_settings()
    if (
        not settings.llm_enabled
        or not settings.diagnosis_llm_enabled
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
    return LangChainDiagnosisProvider(chat_model=chat_model)


def build_configured_langchain_diagnosis_provider(
    settings: Settings | None = None,
) -> tuple[LangChainDiagnosisProvider | None, str | None]:
    try:
        return build_langchain_diagnosis_provider(settings), None
    except Exception as exc:
        return None, type(exc).__name__

