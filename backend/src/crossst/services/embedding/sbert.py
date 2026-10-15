from pathlib import Path
from sentence_transformers import SentenceTransformer


_MODEL: SentenceTransformer | None = None


def embed_windows(
    windows: list[dict[str, object]],
) -> list[dict[str, object]]:
    model = get_sbert_model()

    embedded_windows = []

    for window in windows:
        normalized_logs = window["normalized_logs"]

        embeddings = model.encode(
            normalized_logs,
            convert_to_numpy=False,
            normalize_embeddings=False,
        )

        embedded_windows.append(
            {
                **window,
                "embedding": [
                    embedding.tolist()
                    for embedding in embeddings
                ],
                "embedding_dim": len(embeddings[0]) if len(embeddings) > 0 else 0,
            }
        )

    return embedded_windows
    

def get_sbert_model() -> SentenceTransformer:
    global _MODEL

    if _MODEL is None:
        model_path = (
            Path(__file__).resolve().parent
            / "embed_model"
            / "all-MiniLM-L6-v2"
        )
        _MODEL = SentenceTransformer(str(model_path))

    return _MODEL
