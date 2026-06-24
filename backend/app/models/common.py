from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class StatusEnum(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int

    model_config = ConfigDict(from_attributes=True)
