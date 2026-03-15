"""Integration test: run pipeline on sample document with mocked embeddings (no Neo4j)."""
import pytest
from pathlib import Path
from unittest.mock import patch

from services.ingestion.pdf_ingestion.pipeline import run_pipeline

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR.parent / "fixtures"
SAMPLE_TXT = FIXTURES_DIR / "sample.txt"


class MockEmbedder:
    """Deterministic embedder for tests: returns fixed-dim vectors, no API calls."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dim for _ in texts]


@pytest.fixture
def mock_embedder():
    return MockEmbedder(dim=64)


def test_pipeline_runs_on_sample_txt_with_mocked_embeddings(mock_embedder):
    """Run pipeline on sample.txt with get_embedder mocked; confirm models and counts."""
    assert SAMPLE_TXT.exists(), "fixture tests/fixtures/sample.txt required"
    with patch("services.ingestion.pdf_ingestion.pipeline.get_embedder", return_value=mock_embedder):
        summary = run_pipeline(
            input_path=str(SAMPLE_TXT),
            embedding_backend="openai",
            write_neo4j=False,
        )
    assert summary["document_title"]
    assert summary["parents"] >= 1
    assert summary["children"] >= 1
    assert summary["embedded_children"] == summary["children"]
    assert summary["neo4j_write"] == "skipped"
    assert summary["run_id"].startswith("ingest_")


def test_pipeline_fails_clearly_on_empty_parsed_text(tmp_path):
    """Pipeline raises ValueError when parsing returns empty text."""
    empty = tmp_path / "empty.txt"
    empty.write_text("   ")
    with patch("services.ingestion.pdf_ingestion.pipeline.get_embedder", return_value=MockEmbedder()):
        with pytest.raises(ValueError) as exc:
            run_pipeline(str(empty), write_neo4j=False)
        assert "empty text" in str(exc.value).lower()


def test_pipeline_fails_clearly_on_missing_file(mock_embedder):
    """Pipeline raises FileNotFoundError for missing input path."""
    with patch("services.ingestion.pdf_ingestion.pipeline.get_embedder", return_value=mock_embedder):
        with pytest.raises(FileNotFoundError):
            run_pipeline("/nonexistent/file.txt", write_neo4j=False)
