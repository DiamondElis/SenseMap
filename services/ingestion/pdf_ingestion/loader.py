"""Validate local path and supported extension; return resolved Path."""
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def load_input(path: str) -> Path:
    """
    Validate path: must exist, be a file, and have a supported extension (.pdf, .docx, .txt).
    Returns the resolved Path. Raises FileNotFoundError or ValueError if invalid.
    """
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {p}")
    if not p.is_file():
        raise ValueError(f"Path is not a file: {p}")
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    return p


def get_extension(path: str | Path) -> str:
    """Return lowercased extension for the path."""
    return Path(path).suffix.lower()
