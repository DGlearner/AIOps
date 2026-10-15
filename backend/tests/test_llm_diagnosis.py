import asyncio

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from crossst.application.agents.diagnosis_graph import build_initial_state, make_incident_context
from crossst.application.agents.diagnosis_reasoning import HybridDiagnosisReasoning
from crossst.services.llm.diagnosis import (
    LangChainDiagnosisProvider,
    LLMDiagnosisOutput,
    build_allowed_diagnosis_evidence_refs,
    build_allowed_diagnosis_root_causes,
    build_diagnosis_prompt_messages,
    validate_llm_diagnosis_output,
)


def test_build_allowed_diagnosis_evidence_refs_includes_incident_and_tools():
    state = build_initial_state(
        incident=make_incident_context(
            incident_id="incident-llm-diagnosis-refs",
            summary="Login failures and MySQL errors increased.",
            event_types=["login_failed", "mysql_connection_refused"],
        )
    )
    state["current_hypothesis"] = "mysql_unavailable"
    state["tool_call_summary"] = [
        {
            "tool": "query_events",
            "result_count": 2,
        }
    ]
    state["pending_tool_calls"] = [
        {
            "tool_call_id": "tool-call-001",
            "tool_name": "query_events",
        }
    ]

    refs = build_allowed_diagnosis_evidence_refs(state)

    assert "incident:incident-llm-diagnosis-refs" in refs
    assert "hypothesis:mysql_unavailable" in refs
    assert "tool:query_events" in refs
    assert "tool_call:tool-call-001" in refs


def test_build_allowed_diagnosis_root_causes_includes_hypotheses_and_known_keys():
    state = build_initial_state(
        incident=make_incident_context(
            incident_id="incident-llm-diagnosis-root-causes",
            summary="Login failures and MySQL errors increased.",
            event_types=["login_failed", "mysql_connection_refused"],
        )
    )
    state["hypotheses"] = [
        "credential_attack_or_bruteforce",
        "mysql_unavailable",
    ]
    state["root_cause"] = "mysql_or_database_dependency_unavailable"

    root_causes = build_allowed_diagnosis_root_causes(state)

    assert "credential_attack_or_bruteforce" in root_causes
    assert "mysql_unavailable" in root_causes
    assert "mysql_or_database_dependency_unavailable" in root_causes


def test_validate_llm_diagnosis_output_rejects_confident_answer_without_evidence():
    output = LLMDiagnosisOutput(
        root_cause="mysql_unavailable",
        confidence=0.91,
        evidence_refs=[],
        evidence_chain=["MySQL unavailable is the likely cause."],
        needs_human_review=False,
        recommendations=["Restart MySQL."],
    )

    validated = validate_llm_diagnosis_output(output)

    assert validated.needs_human_review is True
    assert validated.confidence <= 0.5
    assert "缺少证据引用" in validated.evidence_chain[0]


def test_validate_llm_diagnosis_output_filters_unsupported_evidence_refs():
    output = LLMDiagnosisOutput(
        root_cause="mysql_unavailable",
        confidence=0.86,
        evidence_refs=["tool:query_events", "event:hallucinated"],
        evidence_chain=["query_events found MySQL connection refused errors."],
        needs_human_review=False,
        recommendations=["Check MySQL process."],
    )

    validated = validate_llm_diagnosis_output(
        output,
        allowed_evidence_refs={"tool:query_events"},
    )

    assert validated.evidence_refs == ["tool:query_events"]
    assert validated.needs_human_review is True
    assert validated.confidence <= 0.5
    assert "未授权证据引用" in validated.evidence_chain[0]


def test_validate_llm_diagnosis_output_rejects_unknown_root_cause_key():
    output = LLMDiagnosisOutput(
        root_cause="totally_new_root_cause",
        confidence=0.86,
        evidence_refs=["tool:query_events"],
        evidence_chain=["query_events returned relevant records."],
        needs_human_review=False,
        recommendations=["Check the service."],
    )

    validated = validate_llm_diagnosis_output(
        output,
        allowed_evidence_refs={"tool:query_events"},
        allowed_root_causes={"mysql_unavailable"},
    )

    assert validated.root_cause is None
    assert validated.needs_human_review is True
    assert validated.confidence <= 0.5
    assert "未授权根因 key" in validated.evidence_chain[0]


def test_llm_diagnosis_output_normalizes_structured_ruled_out_hypotheses():
    output = LLMDiagnosisOutput.model_validate(
        {
            "root_cause": "mysql_unavailable",
            "confidence": 0.82,
            "evidence_refs": ["tool:query_events"],
            "evidence_chain": ["MySQL connection refused supports the hypothesis."],
            "needs_human_review": False,
            "recommendations": ["Check MySQL process status."],
            "ruled_out_hypotheses": [
                {
                    "hypothesis": "credential_attack_or_bruteforce",
                    "reason": "当前证据更支持数据库依赖故障，而不是凭证攻击。",
                },
                {
                    "name": "recent_deployment_or_config_change",
                    "detail": "当前工具结果未提供近期发布证据。",
                },
                "runbook_available",
            ],
        }
    )

    assert output.ruled_out_hypotheses == [
        "credential_attack_or_bruteforce: 当前证据更支持数据库依赖故障，而不是凭证攻击。",
        "recent_deployment_or_config_change: 当前工具结果未提供近期发布证据。",
        "runbook_available",
    ]


def test_llm_diagnosis_output_normalizes_root_cause_key_with_explanation():
    output = LLMDiagnosisOutput.model_validate(
        {
            "root_cause": "mysql_unavailable：db-prod-01 上 MySQL 拒绝连接，导致登录失败。",
            "confidence": 0.86,
            "evidence_refs": ["tool:query_events"],
            "evidence_chain": ["MySQL connection refused supports the hypothesis."],
            "needs_human_review": False,
            "recommendations": ["Check MySQL process status."],
            "ruled_out_hypotheses": [],
        }
    )

    assert output.root_cause == "mysql_unavailable"


def test_build_diagnosis_prompt_messages_includes_tool_evidence_and_allowed_refs():
    state = build_initial_state(
        incident=make_incident_context(
            incident_id="incident-llm-diagnosis-prompt",
            summary="Login service reports DB connection errors.",
            event_types=["app_db_connection_error"],
            affected_services=["login-service"],
        )
    )
    state["hypotheses"] = ["database_dependency_unavailable"]
    state["current_hypothesis"] = "database_dependency_unavailable"
    state["tool_call_summary"] = [
        {
            "tool": "query_events",
            "reason": "Check MySQL errors.",
            "result_count": 2,
        }
    ]

    messages = build_diagnosis_prompt_messages(state)
    rendered = "\n".join(message.content for message in messages)

    assert "Login service reports DB connection errors" in rendered
    assert "database_dependency_unavailable" in rendered
    assert "query_events" in rendered
    assert "tool:query_events" in rendered
    assert "允许的 root_cause key" in rendered
    assert "mysql_or_database_dependency_unavailable" in rendered
    assert "所有自然语言字段必须使用简体中文" in rendered
    assert "evidence_chain" in rendered
    assert "recommendations" in rendered
    assert "ruled_out_hypotheses" in rendered


def test_langchain_diagnosis_provider_returns_validated_json_output():
    model = FakeListChatModel(
        responses=[
            """
            {
              "root_cause": "mysql_or_database_dependency_unavailable",
              "confidence": 0.84,
              "evidence_refs": ["tool:query_events"],
              "evidence_chain": [
                "query_events returned MySQL connection refused records near the incident window."
              ],
              "needs_human_review": false,
              "recommendations": [
                "Check MySQL process status.",
                "Verify login-service DB connection recovery."
              ],
              "ruled_out_hypotheses": ["credential_attack_or_bruteforce"]
            }
            """
        ]
    )
    provider = LangChainDiagnosisProvider(chat_model=model)
    state = build_initial_state(
        incident=make_incident_context(
            incident_id="incident-llm-diagnosis-provider",
            summary="Login failures and DB errors increased.",
            event_types=["login_failed", "app_db_connection_error"],
        )
    )
    state["current_hypothesis"] = "database_dependency_unavailable"
    state["tool_call_summary"] = [
        {
            "tool": "query_events",
            "result_count": 2,
        }
    ]

    output = provider.analyze_state(state)

    assert output.root_cause == "mysql_or_database_dependency_unavailable"
    assert output.confidence == 0.84
    assert output.evidence_refs == ["tool:query_events"]
    assert output.needs_human_review is False
    assert output.recommendations == [
        "Check MySQL process status.",
        "Verify login-service DB connection recovery.",
    ]


def test_hybrid_diagnosis_reasoning_accepts_valid_llm_evidence_update():
    class FakeProvider:
        def analyze_state(self, state):
            return LLMDiagnosisOutput(
                root_cause="mysql_or_database_dependency_unavailable",
                confidence=0.84,
                evidence_refs=["tool:query_events"],
                evidence_chain=[
                    "LLM: query_events supports MySQL dependency failure."
                ],
                needs_human_review=False,
                recommendations=["Check MySQL process status."],
                ruled_out_hypotheses=["credential_attack_or_bruteforce"],
            )

    state = build_initial_state(
        incident=make_incident_context(
            incident_id="incident-hybrid-diagnosis",
            summary="Login failures and DB errors increased.",
            event_types=["login_failed", "app_db_connection_error"],
        )
    )
    state["current_hypothesis"] = "database_dependency_unavailable"
    state["tool_results"] = [
        {
            "tool": "query_events",
            "count": 2,
            "events": [],
        }
    ]
    state["tool_call_summary"] = [
        {
            "tool": "query_events",
            "result_count": 2,
        }
    ]

    reasoning = HybridDiagnosisReasoning(llm_provider=FakeProvider())
    state = reasoning.update_evidence(state)
    state = reasoning.generate_recommendations(state)

    assert state["root_cause"] == "mysql_or_database_dependency_unavailable"
    assert state["confidence"] == 0.84
    assert "LLM: query_events supports MySQL dependency failure." in state["evidence_chain"]
    assert "credential_attack_or_bruteforce" in state["ruled_out_hypotheses"]
    assert state["recommendations"] == ["Check MySQL process status."]


def test_hybrid_diagnosis_reasoning_falls_back_to_rules_when_llm_errors():
    class BrokenProvider:
        def analyze_state(self, state):
            raise ValueError("bad model output")

    state = build_initial_state(
        incident=make_incident_context(
            incident_id="incident-hybrid-fallback",
            summary="MySQL unavailable.",
            event_types=["mysql_connection_refused"],
        )
    )
    state["current_hypothesis"] = "mysql_unavailable"
    state["tool_results"] = [
        {
            "tool": "query_events",
            "count": 1,
            "events": [],
        }
    ]

    reasoning = HybridDiagnosisReasoning(llm_provider=BrokenProvider())
    state = reasoning.update_evidence(state)

    assert state["root_cause"] == "mysql_or_database_dependency_unavailable"
    assert state["confidence"] == 0.82
    assert any("LLM diagnosis fallback" in item for item in state["evidence_chain"])


def test_hybrid_diagnosis_reasoning_keeps_rule_result_when_llm_needs_review():
    class UntrustedProvider:
        def analyze_state(self, state):
            return LLMDiagnosisOutput(
                root_cause="hallucinated_root_cause",
                confidence=0.5,
                evidence_refs=[],
                evidence_chain=["缺少证据引用，不能确认高置信诊断。"],
                needs_human_review=True,
                recommendations=["Ask a human."],
            )

    state = build_initial_state(
        incident=make_incident_context(
            incident_id="incident-hybrid-untrusted-llm",
            summary="MySQL unavailable.",
            event_types=["mysql_connection_refused"],
        )
    )
    state["current_hypothesis"] = "mysql_unavailable"
    state["tool_results"] = [
        {
            "tool": "query_events",
            "count": 1,
            "events": [],
        }
    ]

    reasoning = HybridDiagnosisReasoning(llm_provider=UntrustedProvider())
    state = reasoning.update_evidence(state)
    state = reasoning.generate_recommendations(state)

    assert state["root_cause"] == "mysql_or_database_dependency_unavailable"
    assert state["confidence"] == 0.82
    assert state["recommendations"] == [
        "Check MySQL process status and recent restart/shutdown logs.",
        "Verify login-service database connection pool and credentials.",
        "Confirm whether MySQL recovery reduces login-service DB errors.",
    ]


def test_hybrid_diagnosis_reasoning_keeps_stronger_rule_result_when_llm_disagrees():
    class LowerConfidenceProvider:
        def analyze_state(self, state):
            return LLMDiagnosisOutput(
                root_cause="recent_deployment_or_config_change",
                confidence=0.74,
                evidence_refs=["tool:query_events"],
                evidence_chain=["LLM: deployment may be related."],
                needs_human_review=False,
                recommendations=["Review recent deployment."],
            )

    state = build_initial_state(
        incident=make_incident_context(
            incident_id="incident-hybrid-lower-confidence-llm",
            summary="MySQL unavailable.",
            event_types=["mysql_connection_refused"],
        )
    )
    state["current_hypothesis"] = "mysql_unavailable"
    state["tool_results"] = [
        {
            "tool": "query_events",
            "count": 1,
            "events": [],
        }
    ]
    state["tool_call_summary"] = [
        {
            "tool": "query_events",
            "result_count": 1,
        }
    ]

    reasoning = HybridDiagnosisReasoning(llm_provider=LowerConfidenceProvider())
    state = reasoning.update_evidence(state)
    state = reasoning.generate_recommendations(state)

    assert state["root_cause"] == "mysql_or_database_dependency_unavailable"
    assert state["confidence"] == 0.82
    assert state["recommendations"] == [
        "Check MySQL process status and recent restart/shutdown logs.",
        "Verify login-service database connection pool and credentials.",
        "Confirm whether MySQL recovery reduces login-service DB errors.",
    ]

