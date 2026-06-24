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
        """Split markdown into semantic chunks."""
        lines = markdown_text.splitlines()
        chunks: list[MarkdownChunk] = []
        current_heading_path: list[str] = []
        current_lines: list[str] = []
        current_length = 0

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Detect headings and update heading path
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading_match:
                # Save current chunk before switching headings
                if current_lines:
                    content = '\n'.join(current_lines).strip()
                    if content and len(content) >= self.min_content_length:
                        chunks.append(MarkdownChunk(
                            content=content,
                            heading_path=current_heading_path.copy(),
                            chunk_type=self._detect_type(current_lines),
                        ))
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

            # Detect tables (keep them atomic)
            if stripped.startswith('|') and i + 1 < len(lines) and lines[i + 1].strip().startswith('|'):
                # Save current chunk if it has content
                if current_lines and current_length > 0:
                    content = '\n'.join(current_lines).strip()
                    if content and len(content) >= self.min_content_length:
                        chunks.append(MarkdownChunk(
                            content=content,
                            heading_path=current_heading_path.copy(),
                            chunk_type=self._detect_type(current_lines),
                        ))
                    current_lines = []
                    current_length = 0

                # Extract full table
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    table_lines.append(lines[i])
                    i += 1

                table_text = '\n'.join(table_lines)

                # Add table as a single chunk
                if table_text:
                    chunks.append(MarkdownChunk(
                        content=table_text,
                        heading_path=current_heading_path.copy(),
                        chunk_type="table",
                    ))
                continue

            # Add regular line to current chunk
            if current_lines:
                line_length = len(line) + 1  # +1 for newline
                if current_length + line_length > self.max_chars:
                    # Split at current boundary
                    content = '\n'.join(current_lines).strip()
                    if content and len(content) >= self.min_content_length:
                        chunks.append(MarkdownChunk(
                            content=content,
                            heading_path=current_heading_path.copy(),
                            chunk_type=self._detect_type(current_lines),
                        ))
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
            content = '\n'.join(current_lines).strip()
            if content and len(content) >= self.min_content_length:
                chunks.append(MarkdownChunk(
                    content=content,
                    heading_path=current_heading_path.copy(),
                    chunk_type=self._detect_type(current_lines),
                ))

        return chunks

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
                markdown_text = self._doc_to_markdown(dl_doc)
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

    @staticmethod
    def _doc_to_markdown(dl_doc: DoclingDocument) -> str:
        """Convert a DoclingDocument to markdown text."""
        return dl_doc.export_to_markdown()

    async def _parse_text_file(self, file_path: Path) -> DoclingDocument:
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        dl_doc = DoclingDocument(name=file_path.stem)
        dl_doc.add_text(label=DocItemLabel.TEXT, text=content)
        return dl_doc
