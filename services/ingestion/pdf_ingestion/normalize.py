"""Convert parser output into NormalizedDocument with stable source_id and cleaned text."""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.python.models.ingestion import NormalizedDocument


def _clean_whitespace(text: str) -> str:
    """Strip excessive whitespace and collapse blank lines to at most one."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _stable_source_id(path: str | Path, parsed: dict[str, Any]) -> str:
    """Generate stable source_id from absolute path and file size (or content hash)."""
    path = Path(path).resolve()
    raw = f"{path}{path.stat().st_size}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _source_type_from_extension(path: str | Path) -> str:
    """Map extension to source_type string."""
    ext = Path(path).suffix.lower()
    return ext.lstrip(".") or "unknown"


def normalize_document(path: str | Path, parsed: dict[str, Any]) -> NormalizedDocument:
    """
    Convert parser output into NormalizedDocument.
    - Stable source_id from sha256(absolute_path + file_size)
    - Cleaned text (strip, collapse spaces and blank lines)
    - source_type from extension; uri = file URI or path string
    - Preserve original path and parser metadata (extension, page_count, etc.) in metadata.
    """
    path = Path(path).resolve()
    source_id = _stable_source_id(path, parsed)
    source_type = _source_type_from_extension(path)
    title = (parsed.get("title") or path.name).strip()
    author = parsed.get("author")
    if author is not None:
        author = str(author).strip() or None
    text = _clean_whitespace(parsed.get("text") or "")
    uri = str(path)

    metadata: dict[str, Any] = dict(parsed.get("metadata") or {})
    metadata.setdefault("extension", path.suffix.lower())
    metadata.setdefault("source_path", str(path))

    return NormalizedDocument(
        id=source_id,
        source_id=source_id,
        source_type=source_type,
        title=title,
        author=author,
        uri=uri,
        created_at=datetime.now(tz=timezone.utc),
        text=text,
        metadata=metadata,
    )
