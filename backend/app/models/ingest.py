from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, UUID4

from app.models.common import StatusEnum


class DocumentBase(BaseModel):
    id: UUID4
    filename: str
    status: StatusEnum
    created_at: datetime
    summary: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(DocumentBase):
    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]

    model_config = ConfigDict(from_attributes=True)


class ConflictDetail(BaseModel):
    existing_document_id: str
    filename: str
    processing: bool

    model_config = ConfigDict(from_attributes=True)


class ConflictResponse(BaseModel):
    detail: ConflictDetail

    model_config = ConfigDict(from_attributes=True)


class UploadResponse(BaseModel):
    document_id: UUID
    status: StatusEnum

    model_config = ConfigDict(from_attributes=True)
