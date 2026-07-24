from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import chat, ingest
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AppError,
    DocumentNotFoundError,
    EmbeddingError,
    IndexingError,
    LLMError,
    StorageError,
)
from app.core.logging import get_logger
from app.jobs.queue import BackgroundJobQueue
from app.services.docling_service import DoclingService
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService
from app.services.llm_service import LLMService
from app.services.qdrant_service import QdrantService
from app.services.rag_service import RAGService
from app.services.state import StateStore

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Ensure the upload scratch directory exists before any route handler runs.
    temp_dir = Path(settings.TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    for f in temp_dir.iterdir():
        if f.is_file():
            f.unlink(missing_ok=True)

    state_store = StateStore(settings.DB_PATH)
    await state_store.open()
    stale = await state_store.fail_stale_processing()
    if stale:
        logger.info("stale_processing_reconciled", extra={"count": stale})

    qdrant_service = QdrantService()
    embedding_service = EmbeddingService()
    llm_service = LLMService()
    docling_service = DoclingService()
    job_queue = BackgroundJobQueue()
    ingestion_service = IngestionService(
        docling=docling_service,
        embedding=embedding_service,
        qdrant=qdrant_service,
        llm=llm_service,
    )
    rag_service = RAGService(
        embedding=embedding_service,
        qdrant=qdrant_service,
        llm=llm_service,
    )

    app.state.state_store = state_store
    app.state.qdrant_service = qdrant_service
    app.state.embedding_service = embedding_service
    app.state.llm_service = llm_service
    app.state.docling_service = docling_service
    app.state.job_queue = job_queue
    app.state.ingestion_service = ingestion_service
    app.state.rag_service = rag_service

    await job_queue.start()
    await qdrant_service.validate_collection_schema(vector_size=settings.EMBEDDING_DIMENSIONS)

    await _check_ollama(settings)

    yield

    await job_queue.stop()
    await embedding_service.close()
    await llm_service.close()
    await qdrant_service.close()
    await state_store.close()


async def _check_ollama(settings: Settings) -> None:
    """Log a warning if Ollama is unreachable or required models are missing.

    This is intentionally a soft check — the app can still start and serve
    documents, but ingestion and chat will fail until Ollama is ready.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            available = {
                m.get("name", "")
                for m in resp.json().get("models", [])
            }
            required = {settings.LLM_MODEL, settings.EMBEDDING_MODEL}
            missing = sorted(required - available)
            if missing:
                logger.warning(
                    "ollama_models_missing",
                    extra={
                        "missing_models": missing,
                        "pull_commands": [f"ollama pull {m}" for m in missing],
                    },
                )
            else:
                logger.info("ollama_ready", extra={"models": sorted(required)})
    except httpx.HTTPError as exc:
        logger.warning(
            "ollama_unreachable",
            extra={
                "url": settings.OLLAMA_BASE_URL,
                "error": str(exc),
                "hint": (
                    "Ensure Ollama is installed and running: "
                    "https://ollama.com/download  |  ollama serve"
                ),
            },
        )


app = FastAPI(title="Local RAG Document Assistant", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(ingest.router, prefix="/api/documents")
app.include_router(chat.router, prefix="/api/chat")


def error_response(exc: AppError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": str(exc), "detail": exc.detail},
    )


def log_app_error(request: Request, exc: AppError) -> None:
    logger.error(
        "application_error",
        extra={
            "path": request.url.path,
            "error": exc.__class__.__name__,
            "detail": exc.detail,
        },
    )


@app.exception_handler(DocumentNotFoundError)
async def document_not_found_handler(
    request: Request,
    exc: DocumentNotFoundError,
) -> JSONResponse:
    log_app_error(request, exc)
    return error_response(exc, status.HTTP_404_NOT_FOUND)


@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError) -> JSONResponse:
    log_app_error(request, exc)
    return error_response(exc, status.HTTP_422_UNPROCESSABLE_ENTITY)


@app.exception_handler(IndexingError)
async def indexing_error_handler(request: Request, exc: IndexingError) -> JSONResponse:
    log_app_error(request, exc)
    return error_response(exc, status.HTTP_500_INTERNAL_SERVER_ERROR)


@app.exception_handler(EmbeddingError)
async def embedding_error_handler(
    request: Request,
    exc: EmbeddingError,
) -> JSONResponse:
    log_app_error(request, exc)
    return error_response(exc, status.HTTP_502_BAD_GATEWAY)


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    log_app_error(request, exc)
    return error_response(exc, status.HTTP_502_BAD_GATEWAY)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    log_app_error(request, exc)
    return error_response(exc, status.HTTP_400_BAD_REQUEST)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    logger.error(
        "request_validation_error",
        extra={"path": request.url.path, "errors": exc.errors()},
    )
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": errors}),
    )
