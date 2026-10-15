from pydantic import BaseModel, Field

from crossst.domain.schemas.logs import RawLogMessage, SourceType


class IngestLogsRequest(BaseModel):
    source_type: SourceType
    logs: list[str] = Field(min_length=1)
    host: str | None = None
    service: str | None = None
    source_name: str | None = None


def build_raw_log_messages(request: IngestLogsRequest) -> list[RawLogMessage]:
    return [
        RawLogMessage(
            source_type=request.source_type,
            message=message,
            host=request.host,
            service=request.service,
            source_name=request.source_name,
        )
        for message in request.logs
    ]
