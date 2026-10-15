from pathlib import Path

import torch


_CHECKPOINT: dict[str, object] | None = None


REQUIRED_CHECKPOINT_FIELDS = {
    "model_state",
    "in_dim",
    "threshold",
}


def detect_windows(embedded_windows: list[dict[str, object]]) -> dict[str, object]:
    checkpoint = get_checkpoint()
    threshold = float(checkpoint["threshold"])

    scores = infer_with_checkpoint(
        checkpoint=checkpoint,
        embedded_windows=embedded_windows,
    )

    window_scores = [
        {
            "window_index": index,
            "score": score,
            "is_anomaly": score > threshold,
        }
        for index, score in enumerate(scores)
    ]

    return {
        "is_anomaly": any(item["is_anomaly"] for item in window_scores),
        "anomaly_score": max(scores, default=0.0),
        "threshold": threshold,
        "window_scores": window_scores,
    }


def get_checkpoint() -> dict[str, object]:
    global _CHECKPOINT

    if _CHECKPOINT is None:
        checkpoint_path = (
            Path(__file__).resolve().parent
            / "checkpoints"
            / "source_hdfs.pt"
        )

        checkpoint = torch.load(checkpoint_path, map_location="cpu")

        if not isinstance(checkpoint, dict):
            raise ValueError("checkpoint must be a dict")

        missing_fields = REQUIRED_CHECKPOINT_FIELDS - set(checkpoint)
        if missing_fields:
            raise ValueError(f"checkpoint missing fields: {sorted(missing_fields)}")

        _CHECKPOINT = checkpoint

    return _CHECKPOINT


def infer_with_checkpoint(
    checkpoint: dict[str, object],
    embedded_windows: list[dict[str, object]],
) -> list[float]:
    raise NotImplementedError(
        "checkpoint inference requires the training model code and adapter"
    )
