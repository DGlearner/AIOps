from typing import Any

from pydantic import BaseModel, Field, model_validator


def _stringify_action(value: Any) -> str:
    if isinstance(value, str):
        return value
    return str(value)


def _extract_actions(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_stringify_action(item) for item in value]
    return [_stringify_action(value)]


def _normalize_recommended_actions(value: Any) -> tuple[list[str], list[dict[str, Any]]]:
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [_stringify_action(value)], []

    flat_actions: list[str] = []
    action_plan: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            flat_actions.append(item)
            continue
        if not isinstance(item, dict):
            flat_actions.append(_stringify_action(item))
            continue

        phase = str(
            item.get("phase")
            or item.get("title")
            or item.get("name")
            or "action"
        )
        actions = _extract_actions(
            item.get("actions")
            or item.get("steps")
            or item.get("items")
            or item.get("action")
        )
        if not actions:
            actions = [_stringify_action(item)]
        action_plan.append({"phase": phase, "actions": actions})
        flat_actions.extend(f"{phase}: {action}" for action in actions)

    return flat_actions, action_plan


class LLMChatOutput(BaseModel):
    intent: str
    answer: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_human_review: bool = False
    recommended_actions: list[str] = Field(default_factory=list)
    action_plan: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_model(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        actions, action_plan = _normalize_recommended_actions(
            normalized.get("recommended_actions")
        )
        normalized["recommended_actions"] = actions
        if action_plan and not normalized.get("action_plan"):
            normalized["action_plan"] = action_plan
        return normalized


def validate_llm_chat_output(
    output: LLMChatOutput,
    *,
    allowed_evidence_refs: set[str] | None = None,
    detected_intent: str | None = None,
) -> LLMChatOutput:
    if detected_intent and output.intent != detected_intent:
        output = output.model_copy(update={"intent": detected_intent})

    unsupported_refs: list[str] = []
    filtered_refs = output.evidence_refs
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

    if unsupported_refs:
        return output.model_copy(
            update={
                "answer": (
                    "未授权证据引用已移除，不能确认高置信结论。"
                    f"未授权引用：{unsupported_refs}\n{output.answer}"
                ),
                "evidence_refs": filtered_refs,
                "confidence": min(output.confidence, 0.5),
                "needs_human_review": True,
            }
        )

    if output.confidence >= 0.7 and not filtered_refs:
        return output.model_copy(
            update={
                "answer": f"缺少证据引用，不能确认高置信结论。\n{output.answer}",
                "evidence_refs": filtered_refs,
                "confidence": min(output.confidence, 0.5),
                "needs_human_review": True,
            }
        )
    if filtered_refs != output.evidence_refs:
        return output.model_copy(update={"evidence_refs": filtered_refs})
    return output

