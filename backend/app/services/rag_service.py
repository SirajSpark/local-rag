from collections.abc import AsyncGenerator

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.chat import ChunkResult
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.qdrant_service import QdrantService

logger = get_logger(__name__)


class RAGService:
    def __init__(
        self,
        embedding: EmbeddingService,
        qdrant: QdrantService,
        llm: LLMService,
    ) -> None:
        self.embedding = embedding
        self.qdrant = qdrant
        self.llm = llm
        self.settings = get_settings()

    async def retrieve(self, question: str) -> tuple[list[float], list[dict]]:
        """Embed *question* and retrieve the top context chunks.

        Returns the query vector alongside the chunks so callers can reuse
        both without a second embedding round-trip.
        """
        query_vector = await self.embedding.embed(question)
        context_chunks = await self.qdrant.search(query_vector, self.settings.TOP_K)

        logger.info(
            "qdrant_results",
            extra={
                "question": question,
                "total": len(context_chunks),
                "chunks": [
                    {
                        "rank": i + 1,
                        "score": round(c["score"], 4),
                        "filename": c.get("filename", ""),
                        "chunk_id": c.get("chunk_id", "")[:8],
                        "preview": c.get("content", "")[:300],
                    }
                    for i, c in enumerate(context_chunks)
                ],
            },
        )

        return query_vector, context_chunks

    async def query(
        self,
        question: str,
        context_chunks: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream answer tokens for *question*.

        If *context_chunks* are supplied (e.g. already fetched by the caller)
        they are reused directly, avoiding a redundant embedding + search.
        """
        if context_chunks is None:
            _, context_chunks = await self.retrieve(question)

        async for token in self.llm.stream_answer(question, context_chunks):
            yield token

    async def get_citations(self, question: str) -> tuple[list[ChunkResult], list[dict]]:
        """Return citation objects and the raw chunk dicts for *question*.

        Returning the raw dicts lets the chat route pass them straight into
        ``query()`` without triggering another embed/search cycle.
        """
        _, raw_chunks = await self.retrieve(question)
        citations = [ChunkResult(**chunk) for chunk in raw_chunks]
        return citations, raw_chunks