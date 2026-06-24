from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)

    model_config = ConfigDict(from_attributes=True)


class CitationSource(BaseModel):
    filename: str

    model_config = ConfigDict(from_attributes=True)


class ChunkResult(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float
    filename: str

    model_config = ConfigDict(from_attributes=True)


class ChatStreamEvent(StrEnum):
    TOKEN = "token"
    CITATIONS = "citations"
    ERROR = "error"
    DONE = "done"


class CitationsPayload(BaseModel):
    citations: list[CitationSource]

    model_config = ConfigDict(from_attributes=True)


class StreamResponse(BaseModel):
    event: ChatStreamEvent
    data: str

    model_config = ConfigDict(from_attributes=True)
