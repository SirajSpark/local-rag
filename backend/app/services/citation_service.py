import re
from collections.abc import Iterable

from app.models.chat import ChunkResult, CitationSource

_PARENTHETICAL_RE = re.compile(r"\(([^()]*)\)")
_INSUFFICIENT_INFO_RE = re.compile(
    r"\b(?:do not|don't|does not|doesn't|cannot|can't)\s+"
    r"(?:have|contain|provide)\s+enough\s+information\b|"
    r"\bnot\s+enough\s+information\b",
    re.IGNORECASE,
)


def filter_cited_sources(
    answer: str,
    retrieved_chunks: Iterable[ChunkResult],
) -> list[CitationSource]:
    """Return only retrieved sources explicitly cited in *answer*."""
    chunks = list(retrieved_chunks)
    if not chunks or _INSUFFICIENT_INFO_RE.search(answer):
        return []

    cited_filenames = _extract_cited_filenames(answer)
    if not cited_filenames:
        return []

    cited_sources: list[CitationSource] = []
    seen: set[str] = set()

    for chunk in chunks:
        if chunk.filename in seen:
            continue

        if chunk.filename in cited_filenames:
            seen.add(chunk.filename)
            cited_sources.append(CitationSource(filename=chunk.filename))

    return cited_sources


def _extract_cited_filenames(answer: str) -> set[str]:
    filenames: set[str] = set()
    for parenthetical in _PARENTHETICAL_RE.findall(answer):
        for part in parenthetical.split(";"):
            text = part.strip()
            if text:
                filenames.add(text)
    return filenames
