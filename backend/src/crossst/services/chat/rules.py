from typing import Any


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword.lower() in text.lower() for keyword in keywords)


def build_rule_based_chat_reply(
    *,
    question: str,
    diagnosis: dict[str, Any] | None,
    tool_calls: list[dict[str, Any]],
    rag_context: dict[str, Any] | None = None,
    investigation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if investigation_result:
        checked_tool_lines = []
        for tool_call in (investigation_result.get("tool_calls") or [])[:10]:
            checked_tool_lines.append(
                f"{tool_call.get('tool_name')}: {tool_call.get('reason')} "
                f"(result_count={tool_call.get('result_count', 0)}, "
                f"duration_ms={tool_call.get('duration_ms', 0)})"
            )
        if not checked_tool_lines:
            for tool_call in (
                (investigation_result.get("fallback_report") or {}).get(
                    "checked_tools"
                )
                or []
            )[:10]:
                checked_tool_lines.append(
                    f"{tool_call.get('tool_name')}: {tool_call.get('reason')} "
                    f"(result_count={tool_call.get('result_count', 0)})"
                )

        evidence_chain = investigation_result.get("evidence_chain") or []
        recommendations = investigation_result.get("recommendations") or []
        fallback_report = investigation_result.get("fallback_report") or {}
        remaining_uncertainty = fallback_report.get("remaining_uncertainty") or []
        human_next_steps = fallback_report.get("recommended_human_next_steps") or []
        content_parts = [
            f"调查状态：{investigation_result.get('status')}",
            (
                "当前判断根因："
                f"{investigation_result.get('root_cause') or '未确认'}，"
                f"置信度：{investigation_result.get('confidence', 0)}。"
            ),
        ]
        if fallback_report.get("initial_anomaly"):
            content_parts.append(f"触发点：{fallback_report.get('initial_anomaly')}")
        if evidence_chain:
            content_parts.append("主要证据：" + "；".join(evidence_chain[:5]))
        if checked_tool_lines:
            content_parts.append("已查询工具：\n" + "\n".join(checked_tool_lines))
        if remaining_uncertainty:
            content_parts.append(
                "仍不确定：" + "；".join(remaining_uncertainty[:3])
            )
        if recommendations:
            content_parts.append(
                "建议动作：\n" + "\n".join(f"- {item}" for item in recommendations[:5])
            )
        if human_next_steps:
            content_parts.append(
                "人工排查建议：\n"
                + "\n".join(f"- {item}" for item in human_next_steps[:5])
            )

        return {
            "intent": "investigation_request",
            "content": "\n".join(content_parts),
            "evidence_refs": [],
            "confidence": investigation_result.get("confidence", 0.0),
            "needs_human_review": investigation_result.get(
                "needs_human_review",
                True,
            ),
            "recommended_actions": recommendations or human_next_steps,
            "metadata": {
                "investigation_status": investigation_result.get("status"),
                "investigation_stop_reason": investigation_result.get("stop_reason"),
            },
        }

    if _contains_any(question, ["为什么", "原因", "根因", "触发", "why", "root cause"]):
        if diagnosis is None:
            return {
                "intent": "diagnosis_summary",
                "content": "当前会话还没有可用的诊断报告。",
            }
        root_cause = diagnosis.get("root_cause") or "未确认"
        confidence = diagnosis.get("confidence", 0)
        trigger_summary = diagnosis.get("trigger_summary", "")
        evidence_chain = diagnosis.get("evidence_chain") or []
        evidence_text = "；".join(evidence_chain[:3]) if evidence_chain else "暂无证据链。"
        return {
            "intent": "diagnosis_summary",
            "content": (
                f"触发点：{trigger_summary}\n"
                f"当前判断根因：{root_cause}，置信度：{confidence}。\n"
                f"主要证据：{evidence_text}"
            ),
        }

    if _contains_any(question, ["查了什么", "调用", "tool", "工具", "排查了哪些"]):
        if not tool_calls:
            return {
                "intent": "tool_call_summary",
                "content": "当前会话还没有工具调用记录。",
            }
        lines = []
        for tool_call in tool_calls[:10]:
            lines.append(
                f"{tool_call.get('tool_name')}: {tool_call.get('reason')} "
                f"(result_count={tool_call.get('result_count', 0)}, "
                f"duration_ms={tool_call.get('duration_ms', 0)})"
            )
        return {
            "intent": "tool_call_summary",
            "content": "\n".join(lines),
        }

    if _contains_any(question, ["下一步", "建议", "怎么办", "处理", "recommend"]):
        recommendations = (diagnosis or {}).get("recommendations") or []
        if not recommendations:
            return {
                "intent": "recommendations",
                "content": "当前诊断报告还没有明确建议。",
            }
        return {
            "intent": "recommendations",
            "content": "\n".join(f"- {item}" for item in recommendations),
        }

    if rag_context and rag_context.get("document_count", 0) > 0:
        references = rag_context.get("references") or []
        lines = [
            f"{reference.get('document_type')}:{reference.get('source_id')} "
            f"{reference.get('title')}"
            for reference in references[:5]
        ]
        return {
            "intent": "rag_context_ready",
            "content": (
                f"当前 MVP 尚未接入 LLM，但已检索到 "
                f"{rag_context.get('document_count', 0)} 条可用于分析的上下文：\n"
                + "\n".join(lines)
            ),
            "rag_context": rag_context,
        }

    return {
        "intent": "llm_not_configured",
        "content": "当前 MVP 尚未接入 LLM，但已经保存了你的问题上下文。",
        "rag_context": rag_context,
    }

