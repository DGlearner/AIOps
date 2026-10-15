from collections import defaultdict


_BUFFERS: dict[str, list[str]] = defaultdict(list)


def append_logs_memory(source_type: str, raw_logs: list[str]) -> list[list[str]]:
    buffer = _BUFFERS[source_type]
    buffer.extend(raw_logs)

    ready_windows = []

    while len(buffer) >= 20:
        window_logs = buffer[:20]
        ready_windows.append(window_logs)

        del buffer[:10]

    return ready_windows


def get_buffer_size(source_type: str) -> int:
    return len(_BUFFERS[source_type])
