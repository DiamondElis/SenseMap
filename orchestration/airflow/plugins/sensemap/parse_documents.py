"""Parse PDF files into documents with text and metadata."""
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore[misc, assignment]


def parse_pdf(path: Path) -> dict[str, Any]:
    """Extract text and metadata from a single PDF. Returns dict with id, source, text, etc."""
    if PdfReader is None:
        raise RuntimeError("pypdf is required; pip install pypdf")
    reader = PdfReader(str(path))
    text_parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text_parts.append(t)
    text = "\n\n".join(text_parts).strip()
    source = str(path)
    doc_id = f"doc_{path.name}_{hash(source) % 2**32:x}"
    return {
        "id": doc_id,
        "source": source,
        "text": text,
        "page_count": len(reader.pages),
    }


def parse_documents(paths: list[Path]) -> list[dict[str, Any]]:
    """Parse each path (PDF) into a document dict. Skips empty or unreadable files."""
    parsed: list[dict[str, Any]] = []
    for p in paths:
        try:
            doc = parse_pdf(p)
            if doc.get("text"):
                parsed.append(doc)
        except Exception:
            continue
    return parsed
