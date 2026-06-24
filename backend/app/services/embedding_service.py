import asyncio

import httpx

from app.core.config import get_settings
from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger

logger = get_logger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 2.0  # seconds; doubles each attempt


class EmbeddingService:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.EMBEDDING_MODEL
        self.client = httpx.AsyncClient(timeout=settings.EMBEDDING_TIMEOUT)

    async def embed(self, text: str) -> list[float]:
        logger.debug("embedding_requested", extra={"input_length": len(text)})
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        logger.info("embedding_batch_requested", extra={"batch_size": len(texts)})

        sub_batch_size = 50
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), sub_batch_size):
            batch = texts[i : i + sub_batch_size]
            last_exc = None

            for attempt in range(1, _RETRY_ATTEMPTS + 1):
                try:
                    response = await self.client.post(
                        f"{self.base_url}/api/embed",
                        json={"model": self.model, "input": batch},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    embeddings = [
                        [float(val) for val in emb] for emb in payload["embeddings"]
                    ]
                    all_embeddings.extend(embeddings)
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500:
                        raise EmbeddingError(
                            "Ollama embedding request failed",
                            detail={
                                "status_code": exc.response.status_code,
                                "response": exc.response.text,
                            },
                        ) from exc
                    last_exc = exc
                except httpx.HTTPError as exc:
                    last_exc = exc
                except (KeyError, TypeError) as exc:
                    raise EmbeddingError(
                        "Invalid embedding response from Ollama",
                        detail=str(exc),
                    ) from exc

                if attempt < _RETRY_ATTEMPTS:
                    wait = _RETRY_BACKOFF ** attempt
                    logger.warning(
                        "embedding_retry",
                        extra={
                            "attempt": attempt,
                            "wait_seconds": wait,
                            "error": str(last_exc),
                        },
                    )
                    await asyncio.sleep(wait)
            else:
                raise EmbeddingError(
                    "Failed to connect to Ollama after retries",
                    detail=str(last_exc),
                ) from last_exc

        return all_embeddings

    async def close(self) -> None:
        await self.client.aclose()