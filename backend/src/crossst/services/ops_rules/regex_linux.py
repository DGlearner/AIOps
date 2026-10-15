import re


SYSLOG_LINE = re.compile(
    r"^(?P<month>[A-Z][a-z]{2})\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<process>[^\s:]+)(?:\[(?P<pid>\d+)\])?:\s*"
    r"(?P<message>.*)$"
)

PAM_PROCESS = re.compile(
    r"^(?P<service>\w+)\(pam_unix\)(?:\[(?P<pid>\d+)\])?$"
)

SSH_AUTH_FAILURE = re.compile(
    r"authentication failure;.*rhost=(?P<rhost>\S+)?(?:\s+user=(?P<user>\S+))?",
    re.IGNORECASE,
)

SSH_USER_UNKNOWN = re.compile(
    r"check pass; user unknown",
    re.IGNORECASE,
)

RPC_GETHOSTBYNAME_ERROR = re.compile(
    r"gethostbyname error for (?P<payload>.+)",
    re.IGNORECASE,
)

BIND_FAILED = re.compile(
    r"bind failed \((?P<reason>.+?)\)\. service = (?P<service>\S+)",
    re.IGNORECASE,
)

SERVICE_FAILED_TO_START = re.compile(
    r"Service (?P<service>\S+) failed to start and is deactivated",
    re.IGNORECASE,
)

GENERIC_FAILED = re.compile(
    r"\bfailed\b|\bfailure\b",
    re.IGNORECASE,
)

CDROM_OPEN_FAILED = re.compile(
    r"cdrom: open failed",
    re.IGNORECASE,
)


def match_linux_rules(raw_log: str) -> list[dict[str, object]]:
    event = parse_linux_log(raw_log)
    message = str(event["message"])
    process = str(event["process"])

    matches = []

    pam = PAM_PROCESS.match(process)
    service = pam.group("service") if pam else process

    ssh_auth_failure = SSH_AUTH_FAILURE.search(message)
    if service == "sshd" and ssh_auth_failure:
        matches.append(
            build_match(
                event_type="ssh_auth_failure",
                base_severity="low",
                event=event,
                entities=clean_entities(
                    {
                        "service": service,
                        "rhost": ssh_auth_failure.group("rhost"),
                        "user": ssh_auth_failure.group("user"),
                    }
                ),
            )
        )

    if service == "sshd" and SSH_USER_UNKNOWN.search(message):
        matches.append(
            build_match(
                event_type="ssh_user_unknown",
                base_severity="medium",
                event=event,
                entities={"service": service},
            )
        )

    rpc_error = RPC_GETHOSTBYNAME_ERROR.search(message)
    if process.startswith("rpc.statd") and rpc_error:
        payload = rpc_error.group("payload")
        matches.append(
            build_match(
                event_type="rpc_statd_gethostbyname_error",
                base_severity="high" if looks_like_exploit_payload(payload) else "medium",
                event=event,
                entities={
                    "service": "rpc.statd",
                    "payload_excerpt": payload[:160],
                    "exploit_like": looks_like_exploit_payload(payload),
                },
            )
        )

    bind_failed = BIND_FAILED.search(message)
    if bind_failed:
        matches.append(
            build_match(
                event_type="service_bind_failed",
                base_severity="medium",
                event=event,
                entities=bind_failed.groupdict(),
            )
        )

    service_failed = SERVICE_FAILED_TO_START.search(message)
    if service_failed:
        matches.append(
            build_match(
                event_type="service_start_failed",
                base_severity="medium",
                event=event,
                entities=service_failed.groupdict(),
            )
        )

    if CDROM_OPEN_FAILED.search(message):
        matches.append(
            build_match(
                event_type="cdrom_open_failed",
                base_severity="low",
                event=event,
                entities={"device": "cdrom"},
            )
        )

    if not matches and GENERIC_FAILED.search(message):
        matches.append(
            build_match(
                event_type="generic_failure",
                base_severity="low",
                event=event,
                entities={"process": process},
            )
        )

    return matches


def parse_linux_log(raw_log: str) -> dict[str, object]:
    match = SYSLOG_LINE.match(raw_log)

    if not match:
        return {
            "timestamp": None,
            "host": None,
            "process": "unknown",
            "pid": None,
            "message": raw_log,
            "raw_log": raw_log,
        }

    data = match.groupdict()

    return {
        "timestamp": f"{data['month']} {data['day']} {data['time']}",
        "host": data["host"],
        "process": data["process"],
        "pid": data["pid"],
        "message": data["message"],
        "raw_log": raw_log,
    }


def build_match(
    event_type: str,
    base_severity: str,
    event: dict[str, object],
    entities: dict[str, object],
) -> dict[str, object]:
    return {
        "source_type": "linux",
        "event_type": event_type,
        "base_severity": base_severity,
        "timestamp": event["timestamp"],
        "host": event["host"],
        "process": event["process"],
        "pid": event["pid"],
        "message": event["message"],
        "entities": clean_entities(entities),
        "raw_log": event["raw_log"],
    }


def clean_entities(entities: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in entities.items()
        if value not in {None, ""}
    }


def looks_like_exploit_payload(payload: str) -> bool:
    indicators = [
        "%x",
        "%hn",
        "\\220",
        "\x90",
        "AAAA",
    ]

    lowered = payload.lower()

    return any(indicator.lower() in lowered for indicator in indicators)
