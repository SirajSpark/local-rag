from typing import Any


class AppError(Exception):
    def __init__(self, message: str, detail: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class DocumentNotFoundError(AppError):
    pass


class IndexingError(AppError):
    pass


class EmbeddingError(AppError):
    pass


class LLMError(AppError):
    pass


class StorageError(AppError):
    pass
