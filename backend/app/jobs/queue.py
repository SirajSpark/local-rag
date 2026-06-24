import asyncio
from collections.abc import Coroutine
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class BackgroundJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, Coroutine[Any, Any, Any]]] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker(), name="bg-job-worker")

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        finally:
            self._worker_task = None

    async def enqueue(self, job_id: str, coro: Coroutine[Any, Any, Any]) -> None:
        await self._queue.put((job_id, coro))

    async def _worker(self) -> None:
        while True:
            job_id, coro = await self._queue.get()

            # Use create_task (preferred over the deprecated ensure_future).
            heartbeat = asyncio.create_task(
                self._heartbeat(job_id),
                name=f"heartbeat-{job_id}",
            )
            try:
                await coro
            except asyncio.CancelledError:
                coro.close()
                raise
            except Exception:
                logger.exception("background_job_failed", extra={"job_id": job_id})
            finally:
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
                self._queue.task_done()

    @staticmethod
    async def _heartbeat(job_id: str) -> None:
        """Log a keep-alive message every 30 seconds while a job runs."""
        while True:
            await asyncio.sleep(30)
            logger.info("background_job_running", extra={"job_id": job_id})