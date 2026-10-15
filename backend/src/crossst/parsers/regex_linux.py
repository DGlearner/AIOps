import re

from crossst.parsers.event_builder import build_event
from crossst.domain.schemas.logs import NormalizedEvent, RawLogMessage


FAILED_PASSWORD_RE = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+sshd\[\d+\]:\s+"
    r"Failed password for (?:invalid user )?(?P<user>\S+) "
    r"from (?P<src_ip>\d+\.\d+\.\d+\.\d+) port (?P<port>\d+) ssh2"
)

ACCEPTED_PUBLICKEY_RE = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+sshd\[\d+\]:\s+"
    r"Accepted publickey for (?P<user>\S+) "
    r"from (?P<src_ip>\d+\.\d+\.\d+\.\d+) port (?P<port>\d+) ssh2"
)

CRON_JOB_RE = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+cron\[(?P<pid>\d+)\]:\s+(?P<body>.*)$"
)

SYSTEMD_RE = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+systemd\[1\]:\s+(?P<body>.*)$"
)

KERNEL_RE = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+kernel:\s+(?P<body>.*)$"
)


def parse_linux_log(raw: RawLogMessage) -> NormalizedEvent | None:
    match = FAILED_PASSWORD_RE.search(raw.message)
    if match:
        data = match.groupdict()
        return build_event(
            raw,
            component="ssh",
            event_type="login_failed",
            severity_hint="low",
            host=data["host"],
            fields={
                "user": data["user"],
                "src_ip": data["src_ip"],
                "port": int(data["port"]),
                "log_time": f"{data['month']} {data['day']} {data['time']}",
            },
            tags=["linux", "auth", "ssh", "security"],
        )

    match = ACCEPTED_PUBLICKEY_RE.search(raw.message)
    if match:
        data = match.groupdict()
        return build_event(
            raw,
            component="ssh",
            event_type="login_success",
            severity_hint="info",
            host=data["host"],
            fields={
                "user": data["user"],
                "src_ip": data["src_ip"],
                "port": int(data["port"]),
                "method": "publickey",
                "log_time": f"{data['month']} {data['day']} {data['time']}",
            },
            tags=["linux", "auth", "ssh", "login"],
        )

    match = CRON_JOB_RE.search(raw.message)
    if match:
        data = match.groupdict()
        return build_event(
            raw,
            component="cron",
            event_type="linux_cron_job",
            severity_hint="info",
            host=data["host"],
            fields={
                "pid": int(data["pid"]),
                "body": data["body"],
                "log_time": f"{data['month']} {data['day']} {data['time']}",
            },
            tags=["linux", "cron", "system"],
        )

    match = SYSTEMD_RE.search(raw.message)
    if match:
        data = match.groupdict()
        return build_event(
            raw,
            component="systemd",
            event_type="linux_systemd_event",
            severity_hint="info",
            host=data["host"],
            fields={
                "body": data["body"],
                "log_time": f"{data['month']} {data['day']} {data['time']}",
            },
            tags=["linux", "systemd", "system"],
        )

    match = KERNEL_RE.search(raw.message)
    if match:
        data = match.groupdict()
        return build_event(
            raw,
            component="kernel",
            event_type="linux_kernel_event",
            severity_hint="info",
            host=data["host"],
            fields={
                "body": data["body"],
                "log_time": f"{data['month']} {data['day']} {data['time']}",
            },
            tags=["linux", "kernel", "system"],
        )

    return None
