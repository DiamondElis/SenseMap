"""Split text into sentence-like units; preserve paragraph boundaries when possible."""
import re


def split_into_units(text: str) -> list[str]:
    """
    Split text into units: paragraphs first (double newline), then sentence boundaries if needed.
    Returns list of non-empty strings. Single newlines preserved inside units.
    """
    if not text or not text.strip():
        return []
    text = text.strip()
    # 1) Split on paragraph boundaries (double newline or more)
    paragraphs = re.split(r"\n\s*\n", text)
    units: list[str] = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        # 2) If paragraph is short enough, keep as one unit; else split on sentence boundaries
        if _is_single_unit(p):
            units.append(p)
        else:
            for s in _split_sentences(p):
                if s.strip():
                    units.append(s.strip())
    return units


def _is_single_unit(paragraph: str) -> bool:
    """Treat as one unit if it's one sentence or very short."""
    if len(paragraph.split()) <= 15:
        return True
    if paragraph.count(". ") + paragraph.count("! ") + paragraph.count("? ") < 2:
        return True
    return False


def _split_sentences(paragraph: str) -> list[str]:
    """Split on sentence boundaries (. ! ?) while keeping the delimiter with the sentence."""
    # Match . ! ? followed by space or end
    parts = re.split(r"(?<=[.!?])\s+", paragraph)
    return [p.strip() for p in parts if p.strip()]
