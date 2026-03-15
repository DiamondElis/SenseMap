"""Parse PDF, DOCX, and TXT into a common dict shape: title, author, text, metadata."""
from pathlib import Path
from typing import Any

# PDF
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore[misc, assignment]

# DOCX
try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None  # type: ignore[misc, assignment]


def parse_pdf(path: str | Path) -> dict[str, Any]:
    """Parse a PDF file. Returns dict with title, author, text, metadata (page_count, extension, ...)."""
    if PdfReader is None:
        raise RuntimeError("pypdf is required; pip install pypdf")
    path = Path(path)
    reader = PdfReader(str(path))
    text_parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            text_parts.append(t)
    text = "\n\n".join(text_parts).strip()
    meta = reader.metadata
    title = None
    author = None
    if meta:
        title = (meta.get("/Title") or meta.get("Title") or "").strip() or None
        author = (meta.get("/Author") or meta.get("Author") or "").strip() or None
    if not title and path.stem:
        title = path.stem
    return {
        "title": title or path.name,
        "author": author,
        "text": text,
        "metadata": {
            "page_count": len(reader.pages),
            "extension": path.suffix.lower(),
            "source_path": str(path.resolve()),
        },
    }


def parse_docx(path: str | Path) -> dict[str, Any]:
    """Parse a DOCX file. Returns dict with title, author, text, metadata."""
    if DocxDocument is None:
        raise RuntimeError("python-docx is required; pip install python-docx")
    path = Path(path)
    doc = DocxDocument(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs).strip()
    core = doc.core_properties
    title = (getattr(core, "title", None) or "").strip() or None
    author = (getattr(core, "author", None) or "").strip() or None
    if not title and path.stem:
        title = path.stem
    return {
        "title": title or path.name,
        "author": author,
        "text": text,
        "metadata": {
            "extension": path.suffix.lower(),
            "source_path": str(path.resolve()),
        },
    }


def parse_txt(path: str | Path) -> dict[str, Any]:
    """Parse a plain text file. Returns dict with title, author, text, metadata."""
    path = Path(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read().strip()
    return {
        "title": path.stem or path.name,
        "author": None,
        "text": text,
        "metadata": {
            "extension": path.suffix.lower(),
            "source_path": str(path.resolve()),
        },
    }


def parse_document(path: str | Path) -> dict[str, Any]:
    """
    Detect extension and dispatch to parse_pdf, parse_docx, or parse_txt.
    Returns dict with title, author, text, metadata.
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return parse_pdf(path)
    if ext == ".docx":
        return parse_docx(path)
    if ext == ".txt":
        return parse_txt(path)
    raise ValueError(f"Unsupported extension: {ext}. Use .pdf, .docx, or .txt.")
