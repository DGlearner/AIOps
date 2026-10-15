from crossst.api.schemas import AnalyzeRequest
from crossst.services.normalization.regex import regex_normalize_log
from crossst.services.windowing.sliding import build_sliding_windows
from crossst.services.embedding.sbert import embed_windows


def run_batch_analysis(request: AnalyzeRequest) -> dict[str, object]:
    # 自行上传多条原始日志时测试用
    normalized_events = run_normalization(
        source_type=request.source_type,
        raw_logs=request.raw_logs,
    )

    windows = run_windowing(normalized_events)
    embedded_windows = run_embedding(windows)
    detect_result = run_detection(embedded_windows)

    return {
        "status": "ok",
        "received": len(request.raw_logs),
        "normalized_count": len(normalized_events),
        "window_count": len(windows),
        "embedding_count": len(embedded_windows),
        "detection_result": detect_result,
    }


def run_analysis_agent(source_type: str, raw_logs: list[str]) -> dict[str, object]:
    # 正式 analysis_agent 链路
    normalized_events = run_normalization(
        source_type=source_type,
        raw_logs=raw_logs,
    )

    window_event = {
        "normalized_logs": [
            event["normalized_log"]
            for event in normalized_events
        ],
        "raw_logs": [
            event["raw_log"]
            for event in normalized_events
        ]
    }


    embed_windows = run_embedding(window_event)
    detect_result = run_detection(embed_windows)



def run_normalization(source_type: str, raw_logs: list[str]) -> list[dict[str, object]]:
    return [
        regex_normalize_log(source_type, raw_log)
        for raw_log in raw_logs
    ]


def run_windowing(normalized_events: list[dict[str, object]]) -> list[dict[str, object]]:
    return build_sliding_windows(
        normalized_events=normalized_events,
        window_size=20,
        stride=10,
    )


def run_embedding(window_events: list[dict[str, object]]) -> list[dict[str, object]]:
    return embed_windows(window_events)



def run_detection(embed_window):
    return
