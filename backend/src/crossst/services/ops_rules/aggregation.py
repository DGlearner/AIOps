def aggregate_matches(
    rule_matches: list[dict[str, object]],
) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}

    for match in rule_matches:
        group_key = build_group_key(match)

        if group_key not in groups:
            groups[group_key] = {
                "group_key": group_key,
                "event_type": match["event_type"],
                "base_severity": match["base_severity"],
                "count": 0,
                "entities": match.get("entities", {}),
                "raw_logs": [],
            }

        group = groups[group_key]
        group["count"] += 1
        group["raw_logs"].append(match["raw_log"])

        group["base_severity"] = max_severity(
            str(group["base_severity"]),
            str(match["base_severity"]),
        )

    return list(groups.values())


def build_group_key(match: dict[str, object]) -> str:
    event_type = str(match["event_type"])
    entities = match.get("entities", {})

    if not isinstance(entities, dict):
        return event_type

    source_ip = entities.get("source_ip")
    user = entities.get("user")
    resource = entities.get("resource")
    process = entities.get("process")
    service = entities.get("service") or entities.get("service_name")

    if source_ip:
        return f"{event_type}:source_ip:{source_ip}"

    if user:
        return f"{event_type}:user:{user}"

    if resource:
        return f"{event_type}:resource:{resource}"

    if process:
        return f"{event_type}:process:{process}"

    if service:
        return f"{event_type}:service:{service}"

    return event_type


def max_severity(left: str, right: str) -> str:
    order = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }

    if order.get(right, 0) > order.get(left, 0):
        return right

    return left
