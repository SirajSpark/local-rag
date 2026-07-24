"""filter_cited_sources: only retrieved sources actually cited get through."""
import _path  # noqa: F401
from app.models.chat import ChunkResult
from app.services.citation_service import filter_cited_sources


def _chunk(filename):
    return ChunkResult(chunk_id="c", document_id="d", content="x", score=0.9, filename=filename)


def _names(answer, chunks):
    return [c.filename for c in filter_cited_sources(answer, chunks)]


def test_cited_retrieved_source_returned():
    assert _names("The figure is 5 (a.pdf).", [_chunk("a.pdf")]) == ["a.pdf"]


def test_hallucinated_filename_rejected():
    # Model cites a file that was never retrieved -> must not appear.
    assert _names("See (ghost.pdf).", [_chunk("a.pdf")]) == []


def test_insufficient_info_returns_none():
    assert _names("I do not have enough information (a.pdf).", [_chunk("a.pdf")]) == []


def test_semicolon_separated_multiple():
    out = _names("Both agree (a.pdf; b.pdf).", [_chunk("a.pdf"), _chunk("b.pdf")])
    assert set(out) == {"a.pdf", "b.pdf"}


def test_dedupes_repeated_filename():
    out = _names("Cited (a.pdf).", [_chunk("a.pdf"), _chunk("a.pdf")])
    assert out == ["a.pdf"]


def test_no_citation_no_sources():
    assert _names("A plain answer with no parentheses.", [_chunk("a.pdf")]) == []


def test_no_chunks():
    assert _names("Whatever (a.pdf).", []) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("citations: all passed")
