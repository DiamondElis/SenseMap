"""
Transcript ingestion for Step 5: read JSON conversation, create Conversation and Message nodes.
Preserves raw text and order; no extraction. Writes (Conversation)-[:HAS_MESSAGE]->(Message) only.

CLI: python -m services.conversation_memory.ingest --input conversation.json
Runs full pipeline: ingest -> extract -> validate -> auto-merge safe -> create review tasks -> summary.

Review queue: python -m services.conversation_memory.ingest --review-queue
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.python.models.conversation import (
    CandidateClaimRecord,
    CandidateRelationRecord,
    ConversationRecord,
    MessageRecord,
    ValidationTaskRecord,
)
from services.extraction.pipeline import fetch_existing_entities
from services.graph_builder.merge_utils import get_driver, run_batched_write, run_write_query

from services.conversation_memory.extract_claims import extract_claims_from_conversation
from services.conversation_memory.merge import (
    AcceptedRelation,
    execute_merge,
    merge_decision,
    MergeResult,
)
from services.conversation_memory.validate import validate_candidate_claim


class MessageInput(BaseModel):
    """One message in the transcript input."""

    role: str = "user"
    text: str = ""


class TranscriptInput(BaseModel):
    """Input shape for a single conversation transcript (JSON)."""

    conversation_id: str
    messages: list[MessageInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptInput":
        """Build from JSON-like dict."""
        raw_messages = data.get("messages") or []
        messages = [MessageInput(role=m.get("role", "user"), text=m.get("text", "")) for m in raw_messages]
        return cls(
            conversation_id=str(data["conversation_id"]),
            messages=messages,
            metadata=dict(data.get("metadata") or {}),
        )


def _message_id(conversation_id: str, position: int) -> str:
    return f"{conversation_id}_msg_{position}"


def _parse_transcript(raw: dict[str, Any] | TranscriptInput) -> tuple[ConversationRecord, list[MessageRecord]]:
    """Parse input into ConversationRecord and ordered MessageRecords. Preserve raw text and order."""
    if isinstance(raw, TranscriptInput):
        inp = raw
    else:
        inp = TranscriptInput.from_dict(raw)

    conv_id = inp.conversation_id
    meta = dict(inp.metadata or {})
    source = meta.get("source", "ingest")

    conversation = ConversationRecord(
        id=conv_id,
        source=source,
        started_at=datetime.now(timezone.utc),
        metadata=meta,
    )

    messages: list[MessageRecord] = []
    for i, m in enumerate(inp.messages):
        role = (m.role or "user").strip() or "user"
        text = m.text if m.text is not None else ""
        messages.append(
            MessageRecord(
                id=_message_id(conv_id, i),
                conversation_id=conv_id,
                role=role,
                text=text,
                position=i,
                timestamp=None,
                metadata={},
            )
        )

    return conversation, messages


def fetch_accepted_relations(driver: Any) -> list[AcceptedRelation]:
    """Load accepted Entity-RELATES_TO->Entity triples from the canonical graph for contradiction checks."""
    with driver.session() as session:
        r = session.run(
            """
            MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)
            RETURN a.id AS source_id, COALESCE(r.type, 'RELATES_TO') AS relation_type, b.id AS target_id
            """
        )
        rows = list(r)
    return [
        AcceptedRelation(source_id=rec["source_id"], relation_type=rec["relation_type"], target_id=rec["target_id"])
        for rec in rows
        if rec.get("source_id") and rec.get("target_id")
    ]


def write_candidate_claims_to_graph(
    session: Any,
    conversation_id: str,
    claims: list[CandidateClaimRecord],
    relations: list[CandidateRelationRecord],
) -> None:
    """Persist CandidateClaim nodes and link to Message; optionally persist CandidateRelation. Idempotent MERGE."""
    if not claims:
        return
    claim_rows = [
        {
            "claim_id": c.id,
            "message_id": c.message_id,
            "text": (c.text or "")[:2000],
            "claim_type": c.claim_type,
            "confidence": c.confidence,
            "status": "pending",
        }
        for c in claims
    ]
    run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MERGE (cc:CandidateClaim {id: row.claim_id})
        SET cc.message_id = row.message_id, cc.text = row.text, cc.claim_type = row.claim_type,
            cc.confidence = row.confidence, cc.status = row.status
        WITH cc, row
        MATCH (m:Message {id: row.message_id})
        MERGE (cc)-[:FROM_MESSAGE]->(m)
        """,
        claim_rows,
    )
    rel_by_claim: dict[str, list[CandidateRelationRecord]] = {}
    for r in relations:
        rel_by_claim.setdefault(r.claim_id, []).append(r)
    rel_rows = []
    for c in claims:
        for rel in rel_by_claim.get(c.id, []):
            rel_rows.append({
                "relation_id": rel.id,
                "claim_id": rel.claim_id,
                "source_entity_name": rel.source_entity_name or "",
                "target_entity_name": rel.target_entity_name or "",
                "relation_type": rel.relation_type or "RELATES_TO",
                "confidence": rel.confidence,
            })
    if rel_rows:
        run_batched_write(
            session,
            """
            UNWIND $rows AS row
            MERGE (cr:CandidateRelation {id: row.relation_id})
            SET cr.claim_id = row.claim_id, cr.source_entity_name = row.source_entity_name,
                cr.target_entity_name = row.target_entity_name, cr.relation_type = row.relation_type,
                cr.confidence = row.confidence
            WITH cr, row
            MATCH (cc:CandidateClaim {id: row.claim_id})
            MERGE (cc)-[:HAS_RELATION]->(cr)
            """,
            rel_rows,
        )


def write_validation_tasks_to_graph(
    session: Any,
    claims: list[CandidateClaimRecord],
    validation_tasks: list[ValidationTaskRecord],
) -> None:
    """Persist ValidationTask nodes and (CandidateClaim)-[:HAS_STATUS]->(ValidationTask). Idempotent MERGE."""
    if len(validation_tasks) != len(claims):
        return
    for claim, vt in zip(claims, validation_tasks):
        run_write_query(
            session,
            """
            MERGE (vt:ValidationTask {id: $vt_id})
            SET vt.status = $status, vt.reason = $reason, vt.claim_id = $claim_id
            WITH vt
            MATCH (cc:CandidateClaim {id: $claim_id})
            MERGE (cc)-[:HAS_STATUS]->(vt)
            """,
            {
                "vt_id": vt.id,
                "status": vt.status,
                "reason": vt.reason or "",
                "claim_id": claim.id,
            },
        )


REVIEW_QUEUE_QUERY = """
MATCH (c:CandidateClaim)-[:HAS_STATUS]->(v:ValidationTask)
WHERE v.status = 'needs-review'
RETURN c.id AS id, c.text AS text, v.reason AS reason
ORDER BY c.id;
"""


def run_review_queue(driver: Any) -> list[dict[str, Any]]:
    """Return list of pending review items: id, text, reason."""
    with driver.session() as session:
        r = session.run(REVIEW_QUEUE_QUERY.strip())
        return [dict(rec) for rec in r]


def run_full_pipeline(
    input_path: Path | str,
    *,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> dict[str, Any]:
    """
    Run full Step 5 pipeline: ingest transcript -> extract claims -> validate -> auto-merge safe -> review tasks.
    Returns summary with counts: messages, candidate_claims, auto_approved, needs_review, rejected, merged, review_queue_items.
    """
    path = Path(input_path)
    raw = json.loads(path.read_text())
    conversation, messages = _parse_transcript(raw)

    driver = get_driver(uri=uri, user=user, password=password)
    try:
        # 1. Ingest transcript
        ingest_transcript(raw, uri=uri, user=user, password=password)
        # 2. Extract claims and relations
        claims, relations = extract_claims_from_conversation(messages)
        if not claims:
            return {
                "conversation_id": conversation.id,
                "messages_stored": len(messages),
                "candidate_claims": 0,
                "auto_approved": 0,
                "needs_review": 0,
                "rejected": 0,
                "merged": 0,
                "review_queue_items": 0,
            }

        with driver.session() as session:
            write_candidate_claims_to_graph(session, conversation.id, claims, relations)

        existing_entities = fetch_existing_entities(driver)
        accepted_relations = fetch_accepted_relations(driver)
        glossary: dict[str, Any] = {}

        validation_tasks: list[ValidationTaskRecord] = []
        merge_results: list[MergeResult] = []
        merged_count = 0

        for claim in claims:
            rels_for_claim = [r for r in relations if r.claim_id == claim.id]
            vt = validate_candidate_claim(claim, rels_for_claim, existing_entities, glossary=glossary)
            validation_tasks.append(vt)
            mr = merge_decision(
                claim, rels_for_claim, vt, existing_entities, accepted_relations, glossary=glossary
            )
            merge_results.append(mr)
            if mr.decision == "auto_merge":
                ex = execute_merge(
                    claim,
                    rels_for_claim,
                    vt,
                    mr,
                    existing_entities,
                    conversation.id,
                    glossary=glossary,
                    uri=uri,
                    user=user,
                    password=password,
                )
                if ex.relations_written > 0 or ex.candidate_status_updated:
                    merged_count += 1

        with driver.session() as session:
            write_validation_tasks_to_graph(session, claims, validation_tasks)

        auto_approved = sum(1 for vt in validation_tasks if vt.status == "auto-approved")
        needs_review = sum(1 for vt in validation_tasks if vt.status == "needs-review")
        rejected = sum(1 for vt in validation_tasks if vt.status == "rejected")
        review_queue_items = needs_review
    finally:
        driver.close()

    return {
        "conversation_id": conversation.id,
        "messages_stored": len(messages),
        "candidate_claims": len(claims),
        "auto_approved": auto_approved,
        "needs_review": needs_review,
        "rejected": rejected,
        "merged": merged_count,
        "review_queue_items": review_queue_items,
    }


def ingest_transcript(
    raw: dict[str, Any] | TranscriptInput,
    *,
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> tuple[ConversationRecord, list[MessageRecord]]:
    """
    Read input JSON transcript, create Conversation and ordered Message nodes in Neo4j.
    Relationship: (Conversation)-[:HAS_MESSAGE]->(Message). Message has role, position, text.
    No extraction; raw text preserved exactly.
    """
    conversation, messages = _parse_transcript(raw)
    if not messages:
        return conversation, messages

    driver = get_driver(uri=uri, user=user, password=password)
    try:
        with driver.session() as session:
            run_write_query(
                session,
                """
                MERGE (c:Conversation {id: $id})
                SET c.source = $source, c.started_at = $started_at, c.metadata = $metadata
                """,
                {
                    "id": conversation.id,
                    "source": conversation.source,
                    "started_at": conversation.started_at.isoformat() if conversation.started_at else None,
                    "metadata": conversation.metadata,
                },
            )
            rows = [
                {
                    "message_id": m.id,
                    "conversation_id": m.conversation_id,
                    "role": m.role,
                    "position": m.position,
                    "text": m.text,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    "metadata": m.metadata,
                }
                for m in messages
            ]
            run_batched_write(
                session,
                """
                UNWIND $rows AS row
                MERGE (m:Message {id: row.message_id})
                SET m.conversation_id = row.conversation_id, m.role = row.role,
                    m.position = row.position, m.text = row.text,
                    m.timestamp = row.timestamp, m.metadata = row.metadata
                WITH m, row
                MATCH (c:Conversation {id: row.conversation_id})
                MERGE (c)-[:HAS_MESSAGE]->(m)
                """,
                rows,
            )
    finally:
        driver.close()

    return conversation, messages


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 5 conversation memory: ingest transcript, extract claims, validate, auto-merge, review queue."
    )
    parser.add_argument("--input", type=str, help="Path to conversation JSON file (runs full pipeline)")
    parser.add_argument("--review-queue", action="store_true", help="List pending items needing review and exit")
    parser.add_argument("--uri", type=str, default=None, help="Neo4j URI")
    parser.add_argument("--user", type=str, default=None, help="Neo4j user")
    parser.add_argument("--password", type=str, default=None, help="Neo4j password")
    args = parser.parse_args()

    if args.review_queue:
        driver = get_driver(uri=args.uri, user=args.user, password=args.password)
        try:
            items = run_review_queue(driver)
            print("Review queue (needs-review):")
            for rec in items:
                text_preview = (rec.get("text") or "")[:60]
                if len(str(rec.get("text") or "")) > 60:
                    text_preview += "..."
                print(f"  {rec.get('id', '')}: {text_preview} | reason: {rec.get('reason', '')}")
            if not items:
                print("  (none)")
        finally:
            driver.close()
        print("\nReview queue query:")
        print(REVIEW_QUEUE_QUERY.strip())
        return

    if not args.input:
        parser.error("Either --input <file> or --review-queue is required")
    summary = run_full_pipeline(args.input, uri=args.uri, user=args.user, password=args.password)
    print("Conversation ingested:", summary["conversation_id"])
    print("Messages stored:", summary["messages_stored"])
    print("Candidate claims:", summary["candidate_claims"])
    print("Auto-approved:", summary["auto_approved"])
    print("Needs review:", summary["needs_review"])
    print("Rejected:", summary["rejected"])
    print("Merged:", summary["merged"])
    print("Review queue items:", summary["review_queue_items"])
    print("\nReview queue query:")
    print(REVIEW_QUEUE_QUERY.strip())


if __name__ == "__main__":
    _main()
