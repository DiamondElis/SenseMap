"""Parser tests: TXT (and optionally PDF) return expected text and shape."""
import pytest
from pathlib import Path

from services.ingestion.pdf_ingestion.parser import parse_txt, parse_document

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR.parent / "fixtures"
SAMPLE_TXT = FIXTURES_DIR / "sample.txt"


def test_parse_txt_returns_text():
    """Parser returns non-empty text for TXT input."""
    assert SAMPLE_TXT.exists(), "fixture sample.txt missing"
    result = parse_txt(SAMPLE_TXT)
    assert isinstance(result, dict)
    assert "text" in result
    assert "title" in result
    assert "author" in result
    assert "metadata" in result
    text = (result["text"] or "").strip()
    assert len(text) > 0, "parse_txt should return non-empty text for sample.txt"
    assert "SenseMap" in text or "paragraph" in text


def test_parse_txt_metadata_shape():
    """TXT parse result has extension and source_path in metadata."""
    result = parse_txt(SAMPLE_TXT)
    meta = result.get("metadata") or {}
    assert meta.get("extension") == ".txt"
    assert "source_path" in meta


def test_parse_document_dispatches_txt():
    """parse_document(path) dispatches to parse_txt for .txt and returns same shape."""
    result = parse_document(SAMPLE_TXT)
    assert "text" in result and "title" in result and "metadata" in result
    assert (result["text"] or "").strip()


def test_parse_txt_empty_file(tmp_path):
    """TXT with only whitespace returns empty text (caller may reject)."""
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n\n  ")
    result = parse_txt(empty)
    assert result["text"].strip() == ""
