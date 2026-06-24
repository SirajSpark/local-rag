import asyncio
from uuid import uuid4

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.http.models import Distance, FieldCondition, Filter, FilterSelector, MatchValue, PointStruct, Range, VectorParams

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class QdrantService:
    def __init__(self) -> None:
        settings = get_settings()
        self.collection_name = settings.QDRANT_COLLECTION
        self.client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
        # Cache whether the collection has been confirmed to exist so we avoid
        # an extra round-trip on every search / upsert after startup.
        self._collection_ready: bool = False

    async def _wait_for_qdrant(self, retries: int = 10, delay: float = 2.0) -> None:
        for attempt in range(1, retries + 1):
            try:
                await self.client.get_collections()
                return
            except (ResponseHandlingException, UnexpectedResponse) as e:
                if attempt < retries:
                    logger.info(
                        "qdrant_not_ready",
                        extra={"attempt": attempt, "error": str(e)},
                    )
                    await asyncio.sleep(delay * attempt)
                else:
                    raise

    async def validate_collection_schema(self, vector_size: int) -> None:
        """Validate existing collection schema or create a new one.

        Hard-fails with a clear error message if the dimensions do not match.
        Call this once at startup before accepting any requests.
        """
        await self._wait_for_qdrant()

        collection_exists = await self.client.collection_exists(
            collection_name=self.collection_name
        )

        if not collection_exists:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info(
                "qdrant_collection_created",
                extra={"collection": self.collection_name, "vector_size": vector_size},
            )
            self._collection_ready = True
            return

        # Collection exists — validate dimensions
        info = await self.client.get_collection(self.collection_name)
        existing_size = info.config.params.vectors.size

        if existing_size != vector_size:
            raise ValueError(
                f"Vector dimension mismatch for collection '{self.collection_name}':\n"
                f"  Collection has: {existing_size}\n"
                f"  EMBEDDING_DIMENSIONS is set to: {vector_size}\n"
                f"  This usually means the embedding model was changed.\n"
                f"  Fix: update EMBEDDING_DIMENSIONS in .env to {existing_size},\n"
                f"  or delete the Qdrant collection (e.g. docker volume rm qdrant_data)."
            )

        self._collection_ready = True

    async def init_collection(self, vector_size: int = 4096) -> None:
        """Create the collection if it does not exist.

        After the first successful call the result is cached so subsequent
        calls (e.g. on every search or upsert) are essentially free.
        """
        if self._collection_ready:
            return

        await self._wait_for_qdrant()
        if not await self.client.collection_exists(collection_name=self.collection_name):
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.info(
                "qdrant_collection_created",
                extra={"collection": self.collection_name, "vector_size": vector_size},
            )
        else:
            # Validate dimensions if collection already exists
            info = await self.client.get_collection(self.collection_name)
            existing_size = info.config.params.vectors.size
            if existing_size != vector_size:
                raise ValueError(
                    f"Vector dimension mismatch for collection '{self.collection_name}':\n"
                    f"  Collection has: {existing_size}\n"
                    f"  Requested vector_size: {vector_size}\n"
                    f"  This usually means the embedding model was changed.\n"
                    f"  Fix: update EMBEDDING_DIMENSIONS in .env to {existing_size},\n"
                    f"  or delete the Qdrant collection (e.g. docker volume rm qdrant_data)."
                )

        self._collection_ready = True

    async def upsert_chunks(
        self,
        chunks: list[dict],
        embeddings: list[list[float]],
        document_id: str,
        filename: str,
        generation: int = 0,
    ) -> None:
        if not embeddings:
            return

        expected_dim = get_settings().EMBEDDING_DIMENSIONS
        actual_dim = len(embeddings[0])
        if actual_dim != expected_dim:
            raise ValueError(
                f"Embedding dimension mismatch: expected {expected_dim}, got {actual_dim}"
            )

        await self.init_collection(vector_size=actual_dim)

        points = [
            PointStruct(
                id=str(uuid4()),
                vector=embedding,
                payload={
                    "document_id": document_id,
                    "filename": filename,
                    "content": chunk.get("content", ""),
                    "generation": generation,
                },
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]

        for batch_start in range(0, len(points), 100):
            batch = points[batch_start : batch_start + 100]
            await self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )

    async def search(self, query_vector: list[float], top_k: int) -> list[dict]:
        settings = get_settings()

        await self.init_collection(vector_size=len(query_vector))
        response = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            score_threshold=settings.MIN_SCORE,
        )

        return [
            {
                "chunk_id": str(result.id),
                "document_id": result.payload.get("document_id"),
                "filename": result.payload.get("filename"),
                "content": result.payload.get("content"),
                "score": result.score,
            }
            for result in response.points
            if result.payload is not None
        ]

    async def delete_by_document_id(self, document_id: str) -> None:
        """Delete all chunks belonging to a document."""
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )

    async def delete_old_chunks(self, document_id: str, current_generation: int) -> None:
        """Delete chunks for a document with generation strictly less than current_generation.

        Also deletes chunks that lack a ``generation`` field entirely (i.e.
        documents ingested before generation tracking was introduced).
        """
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        ),
                    ],
                    should=[
                        FieldCondition(
                            key="generation",
                            range=Range(lt=current_generation),
                        ),
                        FieldCondition(
                            key="generation",
                            is_null=True,
                        ),
                    ],
                )
            ),
        )

    async def close(self) -> None:
        await self.client.close()
