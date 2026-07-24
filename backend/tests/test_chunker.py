"""MarkdownChunker: no document text is ever dropped (see H1)."""
import _path  # noqa: F401
from app.services.docling_service import MarkdownChunker

CK = MarkdownChunker(max_tokens=512, min_content_length=120)


def _joined(md):
    return "\n".join(c.content for c in CK.chunk(md))


def test_short_section_not_dropped():
    md = ("## Q1 Revenue\n$1.2M in Q1\n\n"
          "## Details\n" + "A sufficiently long paragraph of detail text. " * 5)
    out = _joined(md)
    assert "$1.2M in Q1" in out and "Q1 Revenue" in out


def test_wholly_short_document_kept():
    chunks = CK.chunk("## Note\nShort but important fact: code is 4271.")
    assert chunks and "4271" in chunks[0].content


def test_many_tiny_sections_all_survive():
    md = "".join(f"## S{i}\nfact-{i}\n\n" for i in range(10))
    out = _joined(md)
    assert all(f"fact-{i}" in out for i in range(10))


def test_short_heading_absorbed_above_table():
    chunks = CK.chunk("## Financials\n| A | B |\n|---|---|\n| 1 | 2 |\n")
    tables = [c for c in chunks if c.chunk_type == "table"]
    assert tables and "| 1 | 2 |" in tables[0].content and "Financials" in tables[0].content


def test_oversized_multiline_section_splits():
    big = "\n".join(f"This is line number {n} with filler text." for n in range(200))
    chunks = CK.chunk(f"## Big\n{big}")
    joined = "\n".join(c.content for c in chunks)
    assert len(chunks) > 1
    assert all(f"line number {n} " in joined for n in range(200))  # no middle-line loss
    assert max(len(c.content) for c in chunks) <= CK.max_chars + CK.min_content_length


def test_long_sections_not_over_merged():
    para = "A long paragraph sentence that comfortably exceeds the threshold here. " * 2
    chunks = CK.chunk(f"## Alpha\n{para}\n\n## Beta\n{para}")
    assert len(chunks) >= 2
    assert not any("Alpha" in c.content and "Beta" in c.content for c in chunks)


def test_trailing_table_kept():
    assert "| 9 | 8 |" in _joined("## T\n| x | y |\n|---|---|\n| 9 | 8 |")


def test_small_table_stays_single_chunk():
    chunks = CK.chunk("| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n")
    tables = [c for c in chunks if c.chunk_type == "table"]
    assert len(tables) == 1 and "| 3 | 4 |" in tables[0].content


def test_oversized_table_splits_repeating_header():
    header = "| id | description |\n|----|-------------|"
    rows = [f"| {n} | row value number {n} with padding text |" for n in range(200)]
    chunks = CK.chunk(header + "\n" + "\n".join(rows))
    tables = [c for c in chunks if c.chunk_type == "table"]
    assert len(tables) > 1                                   # actually split
    for t in tables:
        assert t.content.splitlines()[0] == "| id | description |"   # header repeated
        assert len(t.content) <= CK.max_chars + CK.min_content_length
    joined = "\n".join(t.content for t in tables)
    assert all(f"| {n} |" in joined for n in range(200))     # no row lost


def test_single_wide_row_kept_whole():
    header = "| a | b |\n|---|---|"
    wide = "| x | " + "y" * (CK.max_chars * 2) + " |"
    tables = [c for c in CK.chunk(header + "\n" + wide) if c.chunk_type == "table"]
    assert any(wide in t.content for t in tables)            # row never split


def test_empty_input():
    assert CK.chunk("") == [] and CK.chunk("\n\n   \n") == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("chunker: all passed")
