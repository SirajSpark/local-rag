import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.config import get_settings
from app.core.exceptions import DocumentNotFoundError, StorageError
from app.core.logging import get_logger
from app.deps import (
    get_ingestion_service,
    get_job_queue,
    get_qdrant_service,
    get_state_store,
)
from app.jobs.queue import BackgroundJobQueue
from app.models.common import StatusEnum
from app.models.ingest import (
    ConflictDetail,
    ConflictResponse,
    DocumentListResponse,
    DocumentResponse,
    UploadResponse,
)
from app.services.ingestion_service import IngestionService
from app.services.qdrant_service import QdrantService
from app.services.state import StateStore

logger = get_logger(__name__)

router = APIRouter(tags=["documents"])

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".bmp",
    ".gif",
}


def sanitize_filename(filename: str | None) -> str:
    """Return a safe basename, rejecting path-traversal and dangerous characters.

    Steps:
    1. ``Path.name`` strips any directory component (``../../etc/passwd.pdf``
       becomes ``passwd.pdf``).
    2. Null bytes and other control characters are removed.
    3. The stem is reduced to alphanumerics, hyphens, underscores and dots
       via a regex allowlist — everything else becomes ``_``.
    4. Extension must be in ALLOWED_EXTENSIONS.
    """
    if not filename:
        raise StorageError("Invalid filename")

    # 1. Strip directory components.
    name = Path(filename).name
    # 2. Remove null bytes / control characters.
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)

    suffix = Path(name).suffix.lower()
    if not suffix or suffix not in ALLOWED_EXTENSIONS:
        raise StorageError(
            "Unsupported file type",
            detail={"extension": suffix, "allowed": sorted(ALLOWED_EXTENSIONS)},
        )

    # 3. Sanitize stem: keep alphanumerics, hyphens, underscores, and dots.
    stem = re.sub(r"[^\w.\-]", "_", Path(name).stem)
    stem = stem.strip("._")  # no leading/trailing dots or underscores
    if not stem:
        raise StorageError("Invalid filename")

    return f"{stem}{suffix}"


async def _stream_to_file(file: UploadFile, dest: Path, max_bytes: int) -> None:
    """Write *file* to *dest* in 64 KB chunks, enforcing *max_bytes* as we go.

    Raises ``StorageError`` the moment the cumulative byte count exceeds the
    cap, so the full content is never buffered in memory.
    """
    _CHUNK = 64 * 1024  # 64 KB
    received = 0
    with dest.open("wb") as fh:
        while True:
            chunk = await file.read(_CHUNK)
            if not chunk:
                break
            received += len(chunk)
            if received > max_bytes:
                raise StorageError(
                    "File too large",
                    detail={
                        "max_mb": max_bytes // (1024 * 1024),
                        "received_bytes": received,
                    },
                )
            fh.write(chunk)


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={409: {"model": ConflictResponse, "description": "File already exists"}},
)
async def upload_document(
    file: Annotated[UploadFile, File()],
    job_queue: Annotated[BackgroundJobQueue, Depends(get_job_queue)],
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
    state_store: Annotated[StateStore, Depends(get_state_store)],
) -> UploadResponse:
    filename = sanitize_filename(file.filename)

    existing = await state_store.find_document_by_filename(filename)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=ConflictDetail(
                existing_document_id=str(existing.id),
                filename=existing.filename,
                processing=existing.status == StatusEnum.PROCESSING,
            ).model_dump(),
        )

    settings = get_settings()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise StorageError(
            "File too large",
            detail={
                "max_mb": settings.MAX_FILE_SIZE_MB,
                "received_bytes": file.size,
            },
        )

    suffix = Path(filename).suffix
    tmp_path = Path(settings.TEMP_DIR) / f"{uuid4()}{suffix}"

    try:
        await _stream_to_file(file, tmp_path, max_bytes)

        document_id = uuid4()
        document_id_str = str(document_id)

        document = DocumentResponse(
            id=document_id,
            filename=filename,
            status=StatusEnum.PROCESSING,
            created_at=datetime.now(timezone.utc),
        )
        await state_store.set_document(document_id_str, document)

        async def _ingest_and_update() -> None:
            try:
                chunks = await ingestion_service.ingest(
                    document_id_str, filename, tmp_path
                )
                await state_store.update_document_status(
                    document_id_str, StatusEnum.COMPLETED
                )

                async def _summarize() -> None:
                    try:
                        logger.info(
                            "summary_generation_started",
                            extra={
                                "document_id": document_id_str,
                                "chunk_count": len(chunks),
                            },
                        )
                        summary = await ingestion_service.generate_summary(chunks)
                        if summary:
                            await state_store.update_document_summary(
                                document_id_str, summary
                            )
                            logger.info(
                                "summary_generation_completed",
                                extra={"document_id": document_id_str},
                            )
                    except Exception:
                        logger.exception(
                            "summary_generation_failed",
                            extra={"document_id": document_id_str},
                        )

                asyncio.create_task(_summarize(), name=f"summarize-{document_id_str}")
            except Exception:
                await state_store.update_document_status(
                    document_id_str, StatusEnum.FAILED
                )
                raise
            finally:
                tmp_path.unlink(missing_ok=True)

        await job_queue.enqueue(document_id_str, _ingest_and_update())

        return UploadResponse(document_id=document_id, status=StatusEnum.PROCESSING)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@router.put(
    "/{document_id}/reingest",
    response_model=UploadResponse,
)
async def reingest_document(
    document_id: str,
    file: Annotated[UploadFile, File()],
    job_queue: Annotated[BackgroundJobQueue, Depends(get_job_queue)],
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)],
    state_store: Annotated[StateStore, Depends(get_state_store)],
    qdrant_service: Annotated[QdrantService, Depends(get_qdrant_service)],
) -> UploadResponse:
    document = await state_store.get_document(document_id)
    if document is None:
        raise DocumentNotFoundError(
            "Document not found",
            detail={"document_id": document_id},
        )

    filename = sanitize_filename(file.filename)

    settings = get_settings()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise StorageError(
            "File too large",
            detail={
                "max_mb": settings.MAX_FILE_SIZE_MB,
                "received_bytes": file.size,
            },
        )

    suffix = Path(filename).suffix
    tmp_path = Path(settings.TEMP_DIR) / f"{uuid4()}{suffix}"

    try:
        await _stream_to_file(file, tmp_path, max_bytes)

        document.filename = filename
        document.status = StatusEnum.PROCESSING
        await state_store.set_document(document_id, document)

        async def _ingest_and_update() -> None:
            new_generation = await state_store.get_next_generation()
            try:
                chunks = await ingestion_service.ingest(
                    document_id, filename, tmp_path, generation=new_generation
                )
                await qdrant_service.delete_old_chunks(document_id, new_generation)
                await state_store.update_document_status(
                    document_id, StatusEnum.COMPLETED
                )

                async def _summarize() -> None:
                    try:
                        logger.info(
                            "summary_generation_started",
                            extra={
                                "document_id": document_id,
                                "chunk_count": len(chunks),
                            },
                        )
                        summary = await ingestion_service.generate_summary(chunks)
                        if summary:
                            await state_store.update_document_summary(
                                document_id, summary
                            )
                            logger.info(
                                "summary_generation_completed",
                                extra={"document_id": document_id},
                            )
                    except Exception:
                        logger.exception(
                            "summary_generation_failed",
                            extra={"document_id": document_id},
                        )

                asyncio.create_task(_summarize(), name=f"summarize-{document_id}")
            except Exception:
                await state_store.update_document_status(
                    document_id, StatusEnum.FAILED
                )
                raise
            finally:
                tmp_path.unlink(missing_ok=True)

        await job_queue.enqueue(document_id, _ingest_and_update())

        return UploadResponse(document_id=document_id, status=StatusEnum.PROCESSING)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    state_store: Annotated[StateStore, Depends(get_state_store)],
) -> DocumentListResponse:
    documents = await state_store.list_documents()
    return DocumentListResponse(documents=documents)


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    state_store: Annotated[StateStore, Depends(get_state_store)],
    qdrant_service: Annotated[QdrantService, Depends(get_qdrant_service)],
) -> dict[str, str]:
    document = await state_store.get_document(document_id)
    if document is None:
        raise DocumentNotFoundError(
            "Document not found",
            detail={"document_id": document_id},
        )

    await state_store.delete_document(document_id)
    try:
        await qdrant_service.delete_by_document_id(document_id)
    except Exception:
        logger.warning("qdrant_cleanup_failed", extra={"document_id": document_id})

    return {"message": "Document deleted successfully", "document_id": document_id}


@router.get("/{document_id}/status")
async def get_document_status(
    document_id: str,
    state_store: Annotated[StateStore, Depends(get_state_store)],
) -> dict[str, str | StatusEnum]:
    document = await state_store.get_document(document_id)
    if document is None:
        raise DocumentNotFoundError(
            "Document not found",
            detail={"document_id": document_id},
        )
    return {"document_id": document_id, "status": document.status}
