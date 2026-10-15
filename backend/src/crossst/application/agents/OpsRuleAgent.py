from crossst.services.ops_rules.aggregation import aggregate_matches
from crossst.services.ops_rules.decision import decide_findings
from crossst.services.ops_rules.regex_linux import match_linux_rules


def run_ops_rule_agent(
    source_type: str,
    raw_logs: list[str],
) -> dict[str, object]:
    if source_type != "linux":
        raise ValueError(f"unsupported source_type for OpsRuleAgent: {source_type}")

    rule_matches = []

    for raw_log in raw_logs:
        matches = match_linux_rules(raw_log)
        rule_matches.extend(matches)

    aggregated = aggregate_matches(rule_matches)
    findings = decide_findings(aggregated)

    return {
        "agent": "ops_rule_agent",
        "source_type": source_type,
        "rule_matches": rule_matches,
        "aggregated": aggregated,
        "findings": findings,
    }
