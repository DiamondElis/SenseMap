"""Parent-child chunking: create ParentChunk and ChildChunk from NormalizedDocument with stable IDs."""
import hashlib
from typing import Any

from shared.python.models.ingestion import NormalizedDocument
from shared.python.models.chunks import ParentChunk, ChildChunk

from .metadata import estimate_tokens, build_chunk_metadata
from .sentence_window import split_into_units


def _chunk_id_prefix(text: str, max_len: int = 8) -> str:
    """Deterministic content hash prefix for stable chunk IDs."""
    return hashlib.sha256(text.encode()).hexdigest()[:max_len]


def _sliding_window_chunks(
    units: list[str],
    target_tokens: int,
    overlap_ratio: float,
) -> list[tuple[str, int, int, int]]:
    """
    Sliding window over units by estimated tokens. Returns list of (chunk_text, start_idx, end_idx, token_count).
    Overlap: step = (1 - overlap_ratio) * chunk_size in units, so chunks overlap by overlap_ratio.
    """
    if not units:
        return []
    token_counts = [estimate_tokens(u) for u in units]
    n = len(units)
    result: list[tuple[str, int, int, int]] = []
    start = 0
    while start < n:
        end = start
        total = 0
        while end < n and total + token_counts[end] <= target_tokens * 1.15:
            total += token_counts[end]
            end += 1
        if end == start:
            end = start + 1
        chunk_units = units[start:end]
        chunk_text = "\n\n".join(chunk_units).strip()
        if not chunk_text:
            start += 1
            continue
        total_tokens = estimate_tokens(chunk_text)
        result.append((chunk_text, start, end, total_tokens))
        step = max(1, int((1 - overlap_ratio) * (end - start)))
        start = start + step
    return result


def create_parent_chunks(
    document: NormalizedDocument,
    target_tokens: int = 1200,
    overlap_ratio: float = 0.15,
) -> list[ParentChunk]:
    """
    Create parent chunks from document text. Target ~800–1500 tokens (default 1200), overlap 10–20% (default 15%).
    Short docs yield one parent. Positions and IDs are stable and ordered.
    """
    doc_id = document.id
    text = document.text.strip()
    if not text:
        return []

    units = split_into_units(text)
    if not units:
        one_chunk = text
        pid = f"{doc_id}_p0_{_chunk_id_prefix(one_chunk)}"
        return [
            ParentChunk(
                id=pid,
                document_id=doc_id,
                text=one_chunk,
                position=0,
                token_count=estimate_tokens(one_chunk),
                metadata=build_chunk_metadata(
                    overlap_ratio=overlap_ratio,
                    target_tokens=target_tokens,
                    start_unit_index=0,
                    end_unit_index=0,
                    unit_count=1,
                ),
            )
        ]

    windows = _sliding_window_chunks(units, target_tokens, overlap_ratio)
    if not windows:
        one_chunk = "\n\n".join(units).strip()
        pid = f"{doc_id}_p0_{_chunk_id_prefix(one_chunk)}"
        return [
            ParentChunk(
                id=pid,
                document_id=doc_id,
                text=one_chunk,
                position=0,
                token_count=estimate_tokens(one_chunk),
                metadata=build_chunk_metadata(
                    overlap_ratio=overlap_ratio,
                    target_tokens=target_tokens,
                    start_unit_index=0,
                    end_unit_index=len(units) - 1,
                    unit_count=len(units),
                ),
            )
        ]

    parents: list[ParentChunk] = []
    for pos, (chunk_text, start_idx, end_idx, token_count) in enumerate(windows):
        if not chunk_text.strip():
            continue
        pid = f"{doc_id}_p{pos}_{_chunk_id_prefix(chunk_text)}"
        parents.append(
            ParentChunk(
                id=pid,
                document_id=doc_id,
                text=chunk_text,
                position=pos,
                token_count=token_count,
                metadata=build_chunk_metadata(
                    overlap_ratio=overlap_ratio,
                    target_tokens=target_tokens,
                    start_unit_index=start_idx,
                    end_unit_index=end_idx - 1,
                    unit_count=end_idx - start_idx,
                ),
            )
        )
    return parents


def create_child_chunks(
    document: NormalizedDocument,
    parents: list[ParentChunk],
    target_tokens: int = 250,
    overlap_ratio: float = 0.15,
) -> list[ChildChunk]:
    """
    Create child chunks inside each parent. Target ~150–350 tokens (default 250), overlap 15%.
    Each child has valid parent_id; positions stable within parent.
    """
    doc_id = document.id
    children: list[ChildChunk] = []
    for parent in parents:
        text = parent.text.strip()
        if not text:
            continue
        units = split_into_units(text)
        if not units:
            one_text = parent.text.strip()
            if not one_text:
                continue
            cid = f"{parent.id}_c0_{_chunk_id_prefix(one_text)}"
            children.append(
                ChildChunk(
                    id=cid,
                    parent_id=parent.id,
                    document_id=doc_id,
                    text=one_text,
                    position=0,
                    token_count=estimate_tokens(one_text),
                    metadata=build_chunk_metadata(
                        overlap_ratio=overlap_ratio,
                        target_tokens=target_tokens,
                        start_unit_index=0,
                        end_unit_index=0,
                        unit_count=1,
                    ),
                )
            )
            continue

        windows = _sliding_window_chunks(units, target_tokens, overlap_ratio)
        if not windows:
            one_text = "\n\n".join(units).strip()
            cid = f"{parent.id}_c0_{_chunk_id_prefix(one_text)}"
            children.append(
                ChildChunk(
                    id=cid,
                    parent_id=parent.id,
                    document_id=doc_id,
                    text=one_text,
                    position=0,
                    token_count=estimate_tokens(one_text),
                    metadata=build_chunk_metadata(
                        overlap_ratio=overlap_ratio,
                        target_tokens=target_tokens,
                        start_unit_index=0,
                        end_unit_index=len(units) - 1,
                        unit_count=len(units),
                    ),
                )
            )
            continue

        for pos, (chunk_text, start_idx, end_idx, token_count) in enumerate(windows):
            if not chunk_text.strip():
                continue
            cid = f"{parent.id}_c{pos}_{_chunk_id_prefix(chunk_text)}"
            children.append(
                ChildChunk(
                    id=cid,
                    parent_id=parent.id,
                    document_id=doc_id,
                    text=chunk_text,
                    position=pos,
                    token_count=token_count,
                    metadata=build_chunk_metadata(
                        overlap_ratio=overlap_ratio,
                        target_tokens=target_tokens,
                        start_unit_index=start_idx,
                        end_unit_index=end_idx - 1,
                        unit_count=end_idx - start_idx,
                    ),
                )
            )
    return children
