CHAT_INTENTS = (
    "diagnosis_summary",
    "tool_call_summary",
    "recommendations",
    "incident_report",
    "knowledge_query",
    "investigation_request",
    "general_question",
)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def classify_chat_intent(question: str) -> str:
    if _contains_any(
        question,
        (
            "查了什么",
            "查了哪些",
            "实际查",
            "调用",
            "tool",
            "工具",
            "排查了哪些",
            "查过什么",
            "支持了什么假设",
            "排除了什么假设",
        ),
    ):
        return "tool_call_summary"

    if _contains_any(question, ("故障报告", "报告", "复盘", "postmortem", "report")):
        return "incident_report"

    if _contains_any(question, ("下一步", "建议", "怎么办", "处理", "处置", "recommend", "action")):
        return "recommendations"

    if _contains_any(question, ("以前", "历史", "runbook", "手册", "知识", "类似", "出现过", "曾经")):
        return "knowledge_query"

    if _contains_any(question, ("查一下", "查询", "查看", "看一下", "最近", "日志", "错误日志", "log", "logs")):
        return "investigation_request"

    if _contains_any(question, ("为什么", "原因", "根因", "触发", "导致", "why", "root cause")):
        return "diagnosis_summary"

    return "general_question"

