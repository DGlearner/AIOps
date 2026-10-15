from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    source_type: str
    raw_logs: list[str]
