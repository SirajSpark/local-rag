import asyncio
from pathlib import Path

import aiosqlite

from app.models.common import StatusEnum
from app.models.ingest import DocumentResponse


class StateStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    def _require_conn(self) -> aiosqlite.Connection:
        """Return the active connection or raise if ``open()`` was never called."""
        if self._conn is None:
            raise RuntimeError(
                "StateStore.open() must be awaited before any database operation."
            )
        return self._conn

    async def open(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.execute(
            "CREATE TABLE IF NOT EXISTS documents ("
            "  id TEXT PRIMARY KEY,"
            "  filename TEXT NOT NULL DEFAULT '',"
            "  data TEXT NOT NULL,"
            "  created_at TEXT NOT NULL"
            ")"
        )
        # Migration: add the filename column to databases created before this
        # version.  ALTER TABLE ADD COLUMN errors if the column already exists,
        # so we catch that specific case and re-raise any other database error.
        try:
            await self._conn.execute(
                "ALTER TABLE documents ADD COLUMN filename TEXT NOT NULL DEFAULT ''"
            )
        except aiosqlite.Error as exc:
            if "duplicate column" not in str(exc).lower():
                raise
        # Backfill the column from the JSON blob for pre-migration rows.
        await self._conn.execute(
            "UPDATE documents "
            "SET filename = json_extract(data, '$.filename') "
            "WHERE filename = '' AND json_extract(data, '$.filename') IS NOT NULL"
        )
        # Efficient lookup index used by find_document_by_filename.
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_filename "
            "ON documents(filename COLLATE NOCASE)"
        )
        # Generation counter for monotonic IDs across app restarts.
        await self._conn.execute(
            "CREATE TABLE IF NOT EXISTS generation_counter ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  created_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def fail_stale_processing(self) -> int:
        """Mark every ``processing`` document as ``failed``; return the count.

        Call once at startup: jobs live only in memory, so any document still
        ``processing`` after a restart is orphaned and can never complete.
        """
        conn = self._require_conn()
        async with self._write_lock:
            cursor = await conn.execute(
                "UPDATE documents SET data = json_set(data, '$.status', ?) "
                "WHERE json_extract(data, '$.status') = ?",
                (StatusEnum.FAILED.value, StatusEnum.PROCESSING.value),
            )
            await conn.commit()
            return cursor.rowcount

    async def get_next_generation(self) -> int:
        """Return a monotonically increasing generation ID.
        Uses SQLite AUTOINCREMENT so the counter survives app restarts.
        """
        conn = self._require_conn()
        async with self._write_lock:
            await conn.execute(
                "INSERT INTO generation_counter (created_at) VALUES (datetime('now'))"
            )
            await conn.commit()
            cursor = await conn.execute(
                "SELECT last_insert_rowid() AS generation_id"
            )
            row = await cursor.fetchone()
            return row["generation_id"]

    async def set_document(self, doc_id: str, document: DocumentResponse) -> None:
        conn = self._require_conn()
        async with self._write_lock:
            await conn.execute(
                "INSERT OR REPLACE INTO documents (id, filename, data, created_at) VALUES (?, ?, ?, ?)",
                (
                    doc_id,
                    document.filename,
                    document.model_dump_json(),
                    document.created_at.isoformat(),
                ),
            )
            await conn.commit()

    async def get_document(self, doc_id: str) -> DocumentResponse | None:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT data FROM documents WHERE id = ?", (doc_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return DocumentResponse.model_validate_json(row["data"])

    async def list_documents(self) -> list[DocumentResponse]:
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT data FROM documents ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [DocumentResponse.model_validate_json(row["data"]) for row in rows]

    async def update_document_status(self, doc_id: str, status: StatusEnum) -> None:
        conn = self._require_conn()
        async with self._write_lock:
            await conn.execute(
                "UPDATE documents SET data = json_set(data, '$.status', ?) WHERE id = ?",
                (status.value, doc_id),
            )
            await conn.commit()

    async def update_document_summary(self, doc_id: str, summary: str | None) -> None:
        conn = self._require_conn()
        async with self._write_lock:
            await conn.execute(
                "UPDATE documents SET data = json_set(data, '$.summary', ?) WHERE id = ?",
                (summary, doc_id),
            )
            await conn.commit()

    async def delete_document(self, doc_id: str) -> None:
        conn = self._require_conn()
        async with self._write_lock:
            await conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            await conn.commit()

    async def find_document_by_filename(self, filename: str) -> DocumentResponse | None:
        """O(log n) lookup via the idx_documents_filename index."""
        conn = self._require_conn()
        cursor = await conn.execute(
            "SELECT data FROM documents WHERE filename = ? COLLATE NOCASE",
            (filename,),
        )
        row = await cursor.fetchone()
        return DocumentResponse.model_validate_json(row["data"]) if row else None
