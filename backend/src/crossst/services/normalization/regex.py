import re


def regex_normalize_log(source_type: str, raw_log: str) -> dict[str, object]:
    if source_type == "hdfs":
        return normalize_hdfs_log(raw_log)

    return normalize_generic_log(source_type, raw_log)


def normalize_hdfs_log(raw_log: str) -> dict[str, object]:
    header_pattern = re.compile(
        r"^(?P<date>\d{6})\s+(?P<time>\d{6})\s+(?P<pid>\d+)\s+"
        r"(?P<level>[A-Z]+)\s+(?P<component>[^:]+):\s+(?P<message>.*)$"
    )

    match = header_pattern.match(raw_log)
    if not match:
        return normalize_generic_log("hdfs", raw_log)

    message = match.group("message")

    return {
        "source_type": "hdfs",
        "raw_log": raw_log,
        "timestamp": f"{match.group('date')} {match.group('time')}",
        "level": match.group("level"),
        "component": match.group("component"),
        "normalized_log": normalize_template(message),
    }


def normalize_generic_log(source_type: str, raw_log: str) -> dict[str, object]:
    return {
        "source_type": source_type,
        "raw_log": raw_log,
        "timestamp": None,
        "level": None,
        "component": None,
        "normalized_log": normalize_template(raw_log),
    }


def normalize_template(text: str) -> str:
    text = re.sub(r"blk_-?\d+", "<BLOCK_ID>", text)
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<IP>", text)
    text = re.sub(r":\d+\b", ":<PORT>", text)
    text = re.sub(r"\b\d+\b", "<NUM>", text)
    return text
