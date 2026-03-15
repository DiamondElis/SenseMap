from .loader import load_input, get_extension
from .parser import parse_document, parse_pdf, parse_docx, parse_txt
from .normalize import normalize_document

__all__ = [
    "load_input",
    "get_extension",
    "parse_document",
    "parse_pdf",
    "parse_docx",
    "parse_txt",
    "normalize_document",
]
