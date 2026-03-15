"""
End-to-end local ingestion: load -> parse -> normalize -> chunk -> embed -> write lexical graph.
Run: python -m services.ingestion.pdf_ingestion.pipeline --input ./data/raw/book.pdf [options]
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from shared.python.models.chunks import ChildChunk

from .loader import load_input, get_extension
from .parser import parse_document
from .normalize import normalize_document
from services.chunking import create_parent_chunks, create_child_chunks
from services.embeddings import get_embedder
from services.graph_builder import build_ingestion_run, write_lexical_graph
from services.graph_builder.validators import ValidationError


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Ingest a local document (PDF, DOCX, TXT) into the lexical graph.",
    )
    p.add_argument(
        "--input",
        required=True,
        help="Path to the document (.pdf, .docx, or .txt)",
    )
    p.add_argument(
        "--embedding-backend",
        default="openai",
        choices=("openai", "local_bge"),
        help="Embedding backend (default: openai). Overrides SENSEMAP_EMBEDDING_BACKEND.",
    )
    p.add_argument(
        "--write-neo4j",
        default="true",
        choices=("true", "false"),
        help="Whether to write to Neo4j (default: true).",
    )
    return p.parse_args()


def _run_id() -> str:
    return f"ingest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


def run_pipeline(
    input_path: str,
    embedding_backend: str = "openai",
    write_neo4j: bool = True,
) -> dict:
    """
    Run the full pipeline. Returns a summary dict.
    Decomposed for testing; CLI calls this.
    """
    path = load_input(input_path)
    parsed = parse_document(path)
    text = (parsed.get("text") or "").strip()
    if not text:
        raise ValueError(
            f"Parsing returned empty text for {path}. Check file format and content."
        )

    document = normalize_document(path, parsed)
    source_type = get_extension(path).lstrip(".") or "unknown"
    ingestion_run = build_ingestion_run(
        source_type=source_type,
        input_path=str(path),
        run_id=_run_id(),
        status="running",
    )

    parent_chunks = create_parent_chunks(document)
    child_chunks = create_child_chunks(document, parent_chunks)

    embedder = get_embedder(backend=embedding_backend)
    texts = [c.text for c in child_chunks]
    vectors = embedder.embed_texts(texts)
    child_chunks_with_embeddings = [
        ChildChunk(
            **{**c.model_dump(), "embedding": vec},
        )
        for c, vec in zip(child_chunks, vectors, strict=True)
    ]

    neo4j_status = "skipped"
    if write_neo4j:
        try:
            write_lexical_graph(
                document,
                parent_chunks,
                child_chunks_with_embeddings,
                ingestion_run,
            )
            neo4j_status = "success"
        except Exception as e:
            neo4j_status = f"failed: {e}"

    return {
        "document_title": document.title,
        "parents": len(parent_chunks),
        "children": len(child_chunks),
        "embedded_children": len(vectors),
        "neo4j_write": neo4j_status,
        "run_id": ingestion_run.id,
    }


def main() -> None:
    args = _parse_args()
    write_neo4j = args.write_neo4j.lower() == "true"

    try:
        summary = run_pipeline(
            input_path=args.input,
            embedding_backend=args.embedding_backend,
            write_neo4j=write_neo4j,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("Ingestion complete")
    print(f"Document: {summary['document_title']}")
    print(f"Parents: {summary['parents']}")
    print(f"Children: {summary['children']}")
    print(f"Embedded children: {summary['embedded_children']}")
    print(f"Neo4j write: {summary['neo4j_write']}")
    print(f"Run ID: {summary['run_id']}")

    if summary["neo4j_write"] != "success" and write_neo4j:
        sys.exit(1)


if __name__ == "__main__":
    main()
