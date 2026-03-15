"""Token estimation and chunk metadata. Simple heuristic; upgrade tokenizer later if needed."""
from typing import Any


def estimate_tokens(text: str) -> int:
    """
    Estimate token count with a simple robust heuristic.
    ~4 chars per token for English is a common approximation; use word count + 1.3 as fallback for very short text.
    """
    if not text or not text.strip():
        return 0
    text = text.strip()
    char_count = len(text)
    word_count = len(text.split())
    return max(
        char_count // 4,
        int(word_count * 1.3),
        1 if word_count > 0 else 0,
    )


def build_chunk_metadata(
    *,
    overlap_ratio: float | None = None,
    target_tokens: int | None = None,
    start_unit_index: int | None = None,
    end_unit_index: int | None = None,
    unit_count: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a metadata dict for a chunk. Pass overlap_ratio, target_tokens, unit indices, etc."""
    out: dict[str, Any] = dict(extra)
    if overlap_ratio is not None:
        out["overlap_ratio"] = overlap_ratio
    if target_tokens is not None:
        out["target_tokens"] = target_tokens
    if start_unit_index is not None:
        out["start_unit_index"] = start_unit_index
    if end_unit_index is not None:
        out["end_unit_index"] = end_unit_index
    if unit_count is not None:
        out["unit_count"] = unit_count
    return out
