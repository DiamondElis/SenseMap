"""Parent-child chunking for lexical graph (child embeddings, parent retrieval)."""
from typing import Any


def _split_text(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Split text into overlapping chunks by character count."""
    if not text or chunk_size <= 0:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap if overlap < chunk_size else end
    return chunks


def split_into_parent_chunks(
    text: str,
    chunk_size: int = 2048,
    overlap: int = 256,
) -> list[dict[str, Any]]:
    """Split document text into parent chunks. Returns list of {id, text, position} (document_id set by caller)."""
    raw = _split_text(text, chunk_size, overlap)
    return [
        {"id": f"parent_{i}", "text": t, "position": i}
        for i, t in enumerate(raw)
    ]


def split_into_child_chunks(
    parent_chunks: list[dict[str, Any]],
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[dict[str, Any]]:
    """Split each parent into child chunks. Returns list of {id, parent_id, text, position}."""
    child_chunks: list[dict[str, Any]] = []
    for p in parent_chunks:
        parent_id = p["id"]
        raw = _split_text(p["text"], chunk_size, overlap)
        for i, t in enumerate(raw):
            child_chunks.append({
                "id": f"{parent_id}_child_{i}",
                "parent_id": parent_id,
                "text": t,
                "position": i,
            })
    return child_chunks


def create_parent_child_chunks(
    parsed_docs: list[dict[str, Any]],
    parent_chunk_size: int = 2048,
    parent_chunk_overlap: int = 256,
    child_chunk_size: int = 512,
    child_chunk_overlap: int = 64,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    From parsed documents, produce parent chunks and child chunks with stable ids.
    Parent chunks get document_id; child chunks get parent_id and document_id for edges.
    """
    parent_chunks: list[dict[str, Any]] = []
    child_chunks: list[dict[str, Any]] = []
    for doc in parsed_docs:
        doc_id = doc["id"]
        text = doc.get("text", "")
        parents = split_into_parent_chunks(text, parent_chunk_size, parent_chunk_overlap)
        for i, p in enumerate(parents):
            p["document_id"] = doc_id
            p["id"] = f"{doc_id}_p{i}"
        children = split_into_child_chunks(parents, child_chunk_size, child_chunk_overlap)
        for c in children:
            c["document_id"] = doc_id
            c["id"] = f"{c['parent_id']}_c{c['position']}"
        parent_chunks.extend(parents)
        child_chunks.extend(children)
    return parent_chunks, child_chunks
