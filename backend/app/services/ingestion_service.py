from pathlib import Path

from app.core.exceptions import IndexingError
from app.core.logging import get_logger
from app.services.docling_service import DoclingService
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.qdrant_service import QdrantService

logger = get_logger(__name__)


class IngestionService:
    def __init__(
        self,
        docling: DoclingService,
        embedding: EmbeddingService,
        qdrant: QdrantService,
        llm: LLMService,
    ) -> None:
        self.docling = docling
        self.embedding = embedding
        self.qdrant = qdrant
        self.llm = llm

    async def ingest(
        self, document_id: str, filename: str, file_path: Path, generation: int = 0
    ) -> list[dict]:
        try:
            chunks = await self.docling.parse(file_path)
            contents = [chunk.get("content", "") for chunk in chunks]
            embeddings = await self.embedding.embed_batch(contents)
            await self.qdrant.upsert_chunks(chunks, embeddings, document_id, filename, generation=generation)
            return chunks
        except Exception as exc:
            logger.exception(
                "document_ingestion_failed",
                extra={"document_id": document_id},
            )
            raise IndexingError(
                "Failed to index document",
                detail={"document_id": document_id, "error": str(exc)},
            ) from exc

    async def generate_summary(self, chunks: list[dict]) -> str | None:
        return await self.llm.generate_summary(chunks)
