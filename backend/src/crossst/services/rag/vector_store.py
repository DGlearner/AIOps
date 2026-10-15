from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class RAGDocument:
    document_type: str
    source_id: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "source_id": self.source_id,
            "title": self.title,
            "content": self.content,
            "metadata": self.metadata,
            "score": self.score,
        }


class VectorStore(Protocol):
    async def upsert_documents(self, documents: list[RAGDocument]) -> None:
        ...

    async def search_similar(
        self,
        *,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[RAGDocument]:
        ...

