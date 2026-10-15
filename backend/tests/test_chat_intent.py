import pytest

from crossst.services.chat.intent import CHAT_INTENTS, classify_chat_intent


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("这个告警为什么触发，根因是什么？", "diagnosis_summary"),
        ("Agent 刚刚查了什么工具？", "tool_call_summary"),
        ("刚刚 Agent 实际查了哪些东西？这些结果支持了什么假设？", "tool_call_summary"),
        ("下一步应该怎么处理？", "recommendations"),
        ("帮我生成一份故障报告", "incident_report"),
        ("这个问题以前出现过吗，有没有 runbook？", "knowledge_query"),
        ("查一下最近 5 分钟 mysql 的错误日志", "investigation_request"),
        ("继续分析一下", "general_question"),
    ],
)
def test_classify_chat_intent_returns_stable_intent(question, expected):
    assert classify_chat_intent(question) == expected
    assert expected in CHAT_INTENTS

