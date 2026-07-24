import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path

from docling.datamodel.document import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel

from app.core.config import get_settings
from app.core.exceptions import IndexingError
from app.core.logging import get_logger

logger = get_logger(__name__)


def _make_converter():
    """
    Build a DocumentConverter that uses Apple MPS (Metal) when available,
    and falls back to CPU for broader compatibility.
    """
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat

    pipeline_options = PdfPipelineOptions()

    # ------------------------------------------------------------------ #
    # Device detection (MPS > CPU)                                        #
    # ------------------------------------------------------------------ #
    import torch  # noqa: I001

    supporter_mps = torch.backends.mps.is_available() and torch.backends.mps.is_built()

    if supporter_mps:
        os.environ["DOCLING_DEVICE"] = "mps"
        logger.info("docling_mps_enabled")
        try:
            from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice
            pipeline_options.accelerator_options = AcceleratorOptions(
                num_threads=4,
                device=AcceleratorDevice.MPS,
            )
        except ImportError:
            pass
    else:
        os.environ.setdefault("DOCLING_DEVICE", "cpu")
        try:
            from docling.datamodel.pipeline_options import AcceleratorOptions, AcceleratorDevice
            pipeline_options.accelerator_options = AcceleratorOptions(
                num_threads=4,
                device=AcceleratorDevice.CPU,
            )
        except ImportError:
            pass

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


@dataclass
class MarkdownChunk:
    """Represents a chunk of markdown text with its metadata."""
    content: str
    heading_path: list[str]
    chunk_type: str  # "table", "text", "heading"


class MarkdownChunker:
    """
    Chunk markdown text by:
    - Keeping markdown tables atomic (never split inside a table)
    - Splitting by headings (##, ###) when possible
    - Attaching heading context to each chunk
    """

    def __init__(self, max_tokens: int = 512, min_content_length: int = 120):
        self.max_chars = max_tokens * 4  # Approximate: 1 token ≈ 4 chars
        self.min_content_length = min_content_length

    def chunk(self, markdown_text: str) -> list[MarkdownChunk]:
        """Split markdown into semantic chunks.

        ``min_content_length`` controls where we are willing to cut, not what
        we keep: content below the threshold is carried forward and merged into
        the next chunk rather than discarded, so no document text is ever lost.
        """
        lines = markdown_text.splitlines()
        chunks: list[MarkdownChunk] = []
        current_heading_path: list[str] = []
        current_lines: list[str] = []
        current_length = 0
        # Lines from a sub-threshold flush awaiting merge into the next chunk.
        carryover_lines: list[str] = []

        def flush(lines_to_flush: list[str]) -> None:
            """Emit a chunk from ``lines_to_flush`` plus any pending carryover.

            If the combined content is still below ``min_content_length`` it is
            retained in ``carryover_lines`` (prepended to the next chunk) instead
            of being dropped.
            """
            nonlocal carryover_lines
            combined = carryover_lines + lines_to_flush
            content = '\n'.join(combined).strip()
            if not content:
                return
            if len(content) >= self.min_content_length:
                chunks.append(MarkdownChunk(
                    content=content,
                    heading_path=current_heading_path.copy(),
                    chunk_type=self._detect_type(combined),
                ))
                carryover_lines = []
            else:
                carryover_lines = combined

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Detect headings and update heading path
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading_match:
                # Save current chunk before switching headings
                if current_lines:
                    flush(current_lines)
                    current_lines = []
                    current_length = 0

                level = len(heading_match.group(1))
                heading_text = heading_match.group(2).strip()

                # Update heading path based on heading level
                current_heading_path = current_heading_path[:level-1]
                current_heading_path.append(heading_text)

                # Start a new chunk with this heading
                current_lines = [line]
                current_length = len(line)
                i += 1
                continue

            # Detect tables (kept whole, or split only on row boundaries)
            if stripped.startswith('|') and i + 1 < len(lines) and lines[i + 1].strip().startswith('|'):
                # Save current chunk if it has content
                if current_lines and current_length > 0:
                    flush(current_lines)
                    current_lines = []
                    current_length = 0

                # Extract full table
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    table_lines.append(lines[i])
                    i += 1

                # Emit the table, splitting oversized tables on row boundaries
                # (repeating the header so each piece is self-describing) so a
                # large table is not truncated by the embedder. Any carried-over
                # content (e.g. a short preceding heading) rides on the first
                # piece so it stays contiguous with the table it introduces.
                for idx, group in enumerate(self._split_table(table_lines)):
                    body = (carryover_lines + group) if idx == 0 else group
                    chunks.append(MarkdownChunk(
                        content='\n'.join(body),
                        heading_path=current_heading_path.copy(),
                        chunk_type="table",
                    ))
                carryover_lines = []
                continue

            # Add regular line to current chunk
            if current_lines:
                line_length = len(line) + 1  # +1 for newline
                if current_length + line_length > self.max_chars:
                    # Split at current boundary
                    flush(current_lines)
                    current_lines = [line]
                    current_length = len(line)
                else:
                    current_lines.append(line)
                    current_length += line_length
            else:
                current_lines = [line]
                current_length = len(line)

            i += 1

        # Don't forget the last chunk
        if current_lines:
            flush(current_lines)

        # Emit any trailing carryover so short tail content is never lost, even
        # when there is no following chunk to merge it into.
        if carryover_lines:
            content = '\n'.join(carryover_lines).strip()
            if content:
                chunks.append(MarkdownChunk(
                    content=content,
                    heading_path=current_heading_path.copy(),
                    chunk_type=self._detect_type(carryover_lines),
                ))

        return chunks

    def _split_table(self, table_lines: list[str]) -> list[list[str]]:
        """Split a markdown table into row-groups that each fit ``max_chars``.

        The header row (and its separator, if present) is repeated at the top of
        every group so each piece is a valid, self-describing table. Rows are
        never split; a single row wider than ``max_chars`` is kept whole.
        Tables that already fit are returned unchanged as a single group.
        """
        header = table_lines[:1]
        rows = table_lines[1:]
        if rows and self._is_separator_row(rows[0]):
            header = table_lines[:2]
            rows = table_lines[2:]

        header_len = sum(len(line) + 1 for line in header)
        groups: list[list[str]] = []
        current: list[str] = []
        current_len = header_len
        for row in rows:
            row_len = len(row) + 1
            if current and current_len + row_len > self.max_chars:
                groups.append(header + current)
                current = [row]
                current_len = header_len + row_len
            else:
                current.append(row)
                current_len += row_len
        if current:
            groups.append(header + current)
        # A header-only table (no data rows) still gets emitted.
        return groups or [list(table_lines)]

    @staticmethod
    def _is_separator_row(line: str) -> bool:
        """True for a markdown header separator like ``|---|:--:|``."""
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        return bool(cells) and all(c and set(c) <= set(':- ') and '-' in c for c in cells)

    @staticmethod
    def _detect_type(lines: list[str]) -> str:
        """Detect if a chunk is primarily a table."""
        table_lines = sum(1 for line in lines if line.strip().startswith('|'))
        if table_lines > len(lines) * 0.5:
            return "table"
        return "text"

    @staticmethod
    def contextualize(chunk: MarkdownChunk) -> str:
        """Add heading context to a chunk's content."""
        if chunk.heading_path:
            path = " > ".join(chunk.heading_path)
            return f"# {path}\n\n{chunk.content}"
        return chunk.content


class DoclingService:
    def __init__(self) -> None:
        self.converter = _make_converter()
        settings = get_settings()
        self.chunker = MarkdownChunker(
            max_tokens=settings.CHUNK_MAX_TOKENS,
            min_content_length=settings.CHUNK_MIN_CONTENT_LENGTH,
        )

    async def parse(self, file_path: Path) -> list[dict]:
        logger.info("docling_parse_started", extra={"file_path": str(file_path)})

        try:
            if file_path.suffix.lower() == ".txt":
                dl_doc = await self._parse_text_file(file_path)
                markdown_text = dl_doc.export_to_markdown()
            else:
                result = await asyncio.to_thread(self.converter.convert, file_path)
                dl_doc = result.document
                markdown_text = dl_doc.export_to_markdown()

            chunks = self._extract_chunks_from_markdown(markdown_text)
        except Exception as exc:
            raise IndexingError(
                "Failed to parse document",
                detail={"file_path": str(file_path), "error": str(exc)},
            ) from exc

        logger.info(
            "docling_parse_completed",
            extra={"file_path": str(file_path), "chunks": len(chunks)},
        )
        return chunks

    def _extract_chunks_from_markdown(self, markdown_text: str) -> list[dict]:
        """Extract chunks using the markdown-aware chunker."""
        chunks = []
        for chunk in self.chunker.chunk(markdown_text):
            if not chunk.content:
                continue

            chunks.append({
                "content": MarkdownChunker.contextualize(chunk),
            })
        return chunks

    async def _parse_text_file(self, file_path: Path) -> DoclingDocument:
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        dl_doc = DoclingDocument(name=file_path.stem)
        dl_doc.add_text(label=DocItemLabel.TEXT, text=content)
        return dl_doc
