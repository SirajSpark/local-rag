import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.deps import get_rag_service
from app.models.chat import ChatRequest, ChatStreamEvent
from app.services.citation_service import filter_cited_sources
from app.services.rag_service import RAGService

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)


@router.post("/query")
async def query_chat(
    request: Request,
    chat_request: ChatRequest,
    rag_service: Annotated[RAGService, Depends(get_rag_service)],
) -> StreamingResponse:
    settings = get_settings()

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            citation_results, raw_chunks = await rag_service.get_citations(
                chat_request.question
            )

            answer_parts: list[str] = []
            async with asyncio.timeout(settings.LLM_TIMEOUT):
                async for token in rag_service.query(chat_request.question, raw_chunks):
                    if await request.is_disconnected():
                        return
                    answer_parts.append(token)
                    yield _sse(ChatStreamEvent.TOKEN, token)

            unique_citations = [
                citation.model_dump(mode="json")
                for citation in filter_cited_sources(
                    "".join(answer_parts),
                    citation_results,
                )
            ]

            yield _sse(ChatStreamEvent.CITATIONS, unique_citations)
            yield _sse(ChatStreamEvent.DONE, "")
        except TimeoutError:
            logger.warning(
                "chat_query_timeout",
                extra={"question": chat_request.question},
            )
            yield _sse(
                ChatStreamEvent.ERROR,
                "Request timed out. The model may be overloaded.",
            )
        except Exception as exc:
            logger.exception("chat_query_failed")
            yield _sse(ChatStreamEvent.ERROR, "An error occurred while processing your request.")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: ChatStreamEvent, data: Any) -> str:
    return f"data: {json.dumps({'event': event.value, 'data': data})}\n\n"
