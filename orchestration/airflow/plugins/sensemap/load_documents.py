"""Load document paths from a source directory (e.g. PDFs)."""
from pathlib import Path


def load_documents(source_path: str) -> list[Path]:
    """Return list of file paths under source_path for ingestion (PDFs)."""
    root = Path(source_path)
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".pdf",):
            paths.append(p)
    return sorted(paths)
