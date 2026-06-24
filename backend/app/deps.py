from fastapi import Request

from app.jobs.queue import BackgroundJobQueue
from app.services.docling_service import DoclingService
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService
from app.services.llm_service import LLMService
from app.services.qdrant_service import QdrantService
from app.services.rag_service import RAGService
from app.services.state import StateStore


def get_state_store(request: Request) -> StateStore:
    return request.app.state.state_store


def get_job_queue(request: Request) -> BackgroundJobQueue:
    return request.app.state.job_queue


def get_qdrant_service(request: Request) -> QdrantService:
    return request.app.state.qdrant_service


def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service


def get_llm_service(request: Request) -> LLMService:
    return request.app.state.llm_service


def get_docling_service(request: Request) -> DoclingService:
    return request.app.state.docling_service


def get_ingestion_service(request: Request) -> IngestionService:
    return request.app.state.ingestion_service


def get_rag_service(request: Request) -> RAGService:
    return request.app.state.rag_service
