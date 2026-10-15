from crossst.application.agents.diagnosis_graph import build_initial_state, make_incident_context
from crossst.application.agents.diagnosis_reasoning import RuleBasedDiagnosisReasoning


def test_rule_based_reasoning_generates_login_hypotheses():
    incident = make_incident_context(
        incident_id="incident-reasoning-login",
        summary="Login failures increased.",
        event_types=["login_failed"],
    )
    state = build_initial_state(incident=incident)

    state = RuleBasedDiagnosisReasoning().generate_hypotheses(state)

    assert state["hypotheses"] == [
        "credential_attack_or_bruteforce",
        "backend_dependency_failure_affecting_login",
    ]
    assert state["current_hypothesis"] == "credential_attack_or_bruteforce"


def test_rule_based_reasoning_updates_mysql_evidence():
    incident = make_incident_context(
        incident_id="incident-reasoning-mysql",
        summary="MySQL unavailable.",
        event_types=["mysql_connection_refused"],
    )
    state = build_initial_state(incident=incident)
    state["current_hypothesis"] = "mysql_unavailable"
    state["tool_results"] = [
        {
            "tool": "query_events",
            "count": 2,
            "items": [],
        }
    ]

    state = RuleBasedDiagnosisReasoning().update_evidence(state)

    assert state["confidence"] == 0.82
    assert state["root_cause"] == "mysql_or_database_dependency_unavailable"
    assert state["evidence_chain"] == [
        "mysql_unavailable: query_events returned 2 related record(s)."
    ]


def test_rule_based_reasoning_generates_human_review_recommendations():
    incident = make_incident_context(
        incident_id="incident-reasoning-unknown",
        summary="Unknown anomaly.",
        event_types=["unknown"],
    )
    state = build_initial_state(incident=incident)

    state = RuleBasedDiagnosisReasoning().generate_recommendations(state)

    assert state["recommendations"] == [
        "Review the trigger alert and raw log samples.",
        "Check related service dependencies and recent deployments.",
        "Escalate to the responsible service owner with this investigation summary.",
    ]

