from typing import Protocol

from crossst.application.agents.diagnosis_state import DiagnosisState
from crossst.services.llm.diagnosis import (
    DiagnosisLLMProvider,
    LLMDiagnosisOutput,
    build_configured_langchain_diagnosis_provider,
)


class DiagnosisReasoning(Protocol):
    def generate_hypotheses(self, state: DiagnosisState) -> DiagnosisState:
        ...

    def update_evidence(self, state: DiagnosisState) -> DiagnosisState:
        ...

    def generate_recommendations(self, state: DiagnosisState) -> DiagnosisState:
        ...


class RuleBasedDiagnosisReasoning:
    def generate_hypotheses(self, state: DiagnosisState) -> DiagnosisState:
        incident = state["incident"]
        event_types = set(incident.get("event_types", []))
        aggregate_key = incident.get("aggregate_key", "")
        hypotheses: list[str] = []

        if "login_failed" in event_types:
            hypotheses.extend(
                [
                    "credential_attack_or_bruteforce",
                    "backend_dependency_failure_affecting_login",
                ]
            )
        if "app_db_connection_error" in event_types:
            hypotheses.append("database_dependency_unavailable")
        if "mysql_connection_refused" in event_types:
            hypotheses.append("mysql_unavailable")
            hypotheses.append("historical_similar_incident")
            hypotheses.append("runbook_available")
        if aggregate_key.startswith("service:"):
            hypotheses.append("service_level_failure")
            hypotheses.append("recent_deployment_or_config_change")
            hypotheses.append("historical_similar_incident")
            hypotheses.append("runbook_available")

        if not hypotheses:
            hypotheses.append("unknown_operational_anomaly")

        state["hypotheses"] = list(dict.fromkeys(hypotheses))
        state["current_hypothesis"] = state["hypotheses"][0]
        return state

    def update_evidence(self, state: DiagnosisState) -> DiagnosisState:
        latest = state["tool_results"][-1]
        current = state.get("current_hypothesis")
        count = int(latest.get("count", 0))

        if count > 0:
            state.setdefault("evidence_chain", []).append(
                f"{current}: {latest['tool']} returned {count} related record(s)."
            )
            if current in {"mysql_unavailable", "database_dependency_unavailable"}:
                state["confidence"] = max(state.get("confidence", 0.0), 0.82)
                state["root_cause"] = "mysql_or_database_dependency_unavailable"
            elif current == "backend_dependency_failure_affecting_login":
                state["confidence"] = max(state.get("confidence", 0.0), 0.72)
                state["root_cause"] = "login_service_database_dependency_error"
            elif current == "credential_attack_or_bruteforce":
                state["confidence"] = max(state.get("confidence", 0.0), 0.68)
                state["root_cause"] = "possible_credential_attack_or_bruteforce"
            elif current == "service_level_failure":
                state["confidence"] = max(state.get("confidence", 0.0), 0.55)
            elif current == "recent_deployment_or_config_change":
                state["confidence"] = max(state.get("confidence", 0.0), 0.74)
                state["root_cause"] = "recent_deployment_or_config_change"
            elif current == "historical_similar_incident":
                state["confidence"] = max(state.get("confidence", 0.0), 0.69)
            elif current == "runbook_available":
                state["confidence"] = max(state.get("confidence", 0.0), 0.5)
        else:
            state.setdefault("ruled_out_hypotheses", []).append(str(current))

        return state

    def generate_recommendations(self, state: DiagnosisState) -> DiagnosisState:
        root_cause = state.get("root_cause")
        if root_cause == "mysql_or_database_dependency_unavailable":
            state["recommendations"] = [
                "Check MySQL process status and recent restart/shutdown logs.",
                "Verify login-service database connection pool and credentials.",
                "Confirm whether MySQL recovery reduces login-service DB errors.",
            ]
        elif root_cause == "login_service_database_dependency_error":
            state["recommendations"] = [
                "Check login-service DB connection configuration.",
                "Query MySQL availability and connection limits.",
                "Review recent login-service deployment changes.",
            ]
        elif root_cause == "possible_credential_attack_or_bruteforce":
            state["recommendations"] = [
                "Review source IP distribution and target accounts.",
                "Check whether any successful login followed repeated failures.",
                "Consider temporary rate limiting or blocking suspicious IPs.",
            ]
        elif root_cause == "recent_deployment_or_config_change":
            state["recommendations"] = [
                "Review the recent deployment diff and configuration changes.",
                "Check whether rollback reduces the current error rate.",
                "Compare affected instances with the deployment rollout scope.",
            ]
        else:
            state["recommendations"] = [
                "Review the trigger alert and raw log samples.",
                "Check related service dependencies and recent deployments.",
                "Escalate to the responsible service owner with this investigation summary.",
            ]
        return state


DEFAULT_REASONING = RuleBasedDiagnosisReasoning()


class HybridDiagnosisReasoning:
    def __init__(
        self,
        *,
        rule_reasoning: DiagnosisReasoning | None = None,
        llm_provider: DiagnosisLLMProvider | None = None,
        llm_fallback_reason: str | None = None,
    ) -> None:
        self.rule_reasoning = rule_reasoning or DEFAULT_REASONING
        self.llm_provider = llm_provider
        self.llm_fallback_reason = llm_fallback_reason
        self._latest_llm_output: LLMDiagnosisOutput | None = None

    def generate_hypotheses(self, state: DiagnosisState) -> DiagnosisState:
        return self.rule_reasoning.generate_hypotheses(state)

    def update_evidence(self, state: DiagnosisState) -> DiagnosisState:
        state = self.rule_reasoning.update_evidence(state)
        if self.llm_provider is None:
            if self.llm_fallback_reason:
                state.setdefault("evidence_chain", []).append(
                    f"LLM diagnosis fallback: provider unavailable ({self.llm_fallback_reason})."
                )
            return state

        try:
            output = self.llm_provider.analyze_state(state)
        except Exception as exc:
            state.setdefault("evidence_chain", []).append(
                f"LLM diagnosis fallback: {type(exc).__name__}."
            )
            return state

        current_confidence = state.get("confidence", 0.0)
        if output.evidence_chain:
            state.setdefault("evidence_chain", []).extend(output.evidence_chain)
        if output.needs_human_review or output.confidence < current_confidence:
            return state

        self._latest_llm_output = output
        if output.ruled_out_hypotheses:
            existing = state.setdefault("ruled_out_hypotheses", [])
            existing.extend(
                item for item in output.ruled_out_hypotheses if item not in existing
            )
        if output.root_cause:
            state["root_cause"] = output.root_cause
        state["confidence"] = max(state.get("confidence", 0.0), output.confidence)
        if output.needs_human_review:
            state["confidence"] = min(state.get("confidence", 0.0), output.confidence)
        return state

    def generate_recommendations(self, state: DiagnosisState) -> DiagnosisState:
        if self._latest_llm_output and self._latest_llm_output.recommendations:
            state["recommendations"] = self._latest_llm_output.recommendations
            return state
        return self.rule_reasoning.generate_recommendations(state)


def build_configured_diagnosis_reasoning() -> DiagnosisReasoning:
    provider, fallback_reason = build_configured_langchain_diagnosis_provider()
    if provider is None and fallback_reason is None:
        return DEFAULT_REASONING
    return HybridDiagnosisReasoning(
        llm_provider=provider,
        llm_fallback_reason=fallback_reason,
    )

