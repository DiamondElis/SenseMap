"""
Entity extraction pipeline coordinator: load glossary and schema, fetch unprocessed chunks,
run Pass A (entity) and Pass B (relation) extraction, resolve, write hybrid graph, mark processed.
Resumable: skips chunks that already have entity_processed_at set.
"""
import argparse
import sys
from pathlib import Path

from services.graph_builder.merge_utils import get_driver
from services.extraction.entities.schema import ENTITY_TYPES, RELATIONSHIP_TYPES
from services.extraction.entities.llm_extract import extract_entities
from services.extraction.relations.llm_extract import extract_relationships
from services.extraction.resolution.merge import resolve_entity, ResolutionResult
from services.graph_builder.entity_writer import write_entity_graph

# Default glossary path: repo root / shared / schemas / entity_glossary.yaml
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_GLOSSARY_PATH = _REPO_ROOT / "shared" / "schemas" / "entity_glossary.yaml"


def load_glossary(path: Path | str | None = None) -> dict:
    """Load glossary YAML; return dict with 'entities' list."""
    p = Path(path or _DEFAULT_GLOSSARY_PATH)
    if not p.exists():
        return {"entities": []}
    try:
        import yaml
        with open(p) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {"entities": []}
    except Exception:
        return {"entities": []}


def get_schema() -> dict:
    """Return schema dict for extraction (entity_types, relationship_types)."""
    return {
        "entity_types": list(ENTITY_TYPES),
        "relationship_types": set(RELATIONSHIP_TYPES),
    }


def fetch_existing_entities(driver) -> list[dict]:
    """Load canonical entities from Neo4j for resolution."""
    with driver.session() as session:
        r = session.run(
            "MATCH (e:Entity) RETURN e.id AS id, e.canonical_name AS canonical_name, e.type AS type"
        )
        rows = list(r)
    return [
        {"id": rec["id"], "canonical_name": rec.get("canonical_name") or "", "name": rec.get("canonical_name") or "", "type": rec.get("type") or ""}
        for rec in rows
        if rec.get("id") is not None
    ]


def fetch_unprocessed_chunks(driver, limit: int) -> list[dict]:
    """Fetch Chunk nodes that do not yet have entity_processed_at set."""
    with driver.session() as session:
        r = session.run(
            "MATCH (ch:Chunk) WHERE ch.entity_processed_at IS NULL AND ch.text IS NOT NULL "
            "RETURN ch.id AS id, ch.text AS text LIMIT $limit",
            limit=limit,
        )
        rows = list(r)
    return [{"id": rec["id"], "text": rec.get("text") or ""} for rec in rows if rec.get("id")]


def run_pipeline(
    *,
    limit: int = 20,
    glossary_path: Path | str | None = None,
    extractor_name: str = "pipeline",
) -> dict:
    """
    Run the entity extraction pipeline for up to `limit` unprocessed chunks.
    Returns summary: processed, skipped, errors.
    """
    glossary = load_glossary(glossary_path)
    schema = get_schema()
    driver = get_driver()
    try:
        existing_entities = fetch_existing_entities(driver)
        chunks = fetch_unprocessed_chunks(driver, limit)
    finally:
        driver.close()

    processed = 0
    errors = 0
    for chunk in chunks:
        chunk_id = chunk.get("id")
        text = (chunk.get("text") or "").strip()
        if not chunk_id or not text:
            continue
        try:
            # Pass A: entity extraction
            entities_result = extract_entities(text, glossary, schema)
            entities = entities_result.get("entities") or []
            if not entities:
                # No entities -> still mark processed so we don't retry
                write_entity_graph(
                    chunk_id,
                    [],
                    [],
                    [],
                    extractor_name,
                )
                processed += 1
                continue

            # Pass B: relation extraction
            rel_result = extract_relationships(text, entities, schema)
            relationships = rel_result.get("relationships") or []

            # Resolve each entity against existing
            resolution_results: list[ResolutionResult] = []
            for ent in entities:
                res = resolve_entity(ent, existing_entities, glossary)
                resolution_results.append(res)

            # Write hybrid graph (entities, mentions, RELATES_TO, claim, mark processed)
            write_entity_graph(
                chunk_id,
                entities,
                relationships,
                resolution_results,
                extractor_name,
            )

            # Append resolved entities to existing so next chunk can resolve to them
            from services.graph_builder.entity_writer import _resolve_entity_ids
            for eid, canonical, typ in _resolve_entity_ids(entities, resolution_results):
                existing_entities.append({
                    "id": eid,
                    "canonical_name": canonical,
                    "name": canonical,
                    "type": typ,
                })
            processed += 1
        except Exception:
            errors += 1
            continue

    return {"processed": processed, "skipped": max(0, len(chunks) - processed - errors), "errors": errors, "chunks_considered": len(chunks)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Entity extraction pipeline: Pass A + Pass B, resolve, write.")
    parser.add_argument("--limit", type=int, default=20, help="Max unprocessed chunks to process (default 20)")
    parser.add_argument("--glossary", type=str, default=None, help="Path to entity glossary YAML")
    parser.add_argument("--extractor", type=str, default="pipeline", help="Extractor name for provenance")
    args = parser.parse_args()
    summary = run_pipeline(limit=args.limit, glossary_path=args.glossary, extractor_name=args.extractor)
    print(f"Processed: {summary['processed']}, errors: {summary['errors']}, chunks considered: {summary['chunks_considered']}")
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
