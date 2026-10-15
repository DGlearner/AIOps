def build_sliding_windows(
    normalized_events: list[dict[str, object]],
    window_size: int = 20,
    stride: int = 10,
) -> list[dict[str, object]]:
    windows = []

    start = 0

    while start < len(normalized_events):
        window_events = normalized_events[start : start + window_size]

        if not window_events:
            break

        windows.append(
            {
                "start_index": start,
                "end_index": start + len(window_events) - 1,
                "event_count": len(window_events),
                "normalized_logs": [
                    event["normalized_log"]
                    for event in window_events
                ],
                "raw_logs": [
                    event["raw_log"]
                    for event in window_events
                ],
            }
        )

        next_start = start + stride
        if next_start >= len(normalized_events):
            break

        start = next_start

    return windows
