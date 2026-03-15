"""Unit tests for merge_utils: run_write_query, run_batched_write, get_driver."""
import pytest
from unittest.mock import MagicMock

from services.graph_builder.merge_utils import (
    run_write_query,
    run_batched_write,
    get_driver,
)


def test_run_write_query_calls_session_run_with_params():
    """run_write_query passes query and params to session.run."""
    session = MagicMock()
    run_write_query(session, "MERGE (n:Node {id: $id})", {"id": "x"})
    session.run.assert_called_once_with("MERGE (n:Node {id: $id})", {"id": "x"})


def test_run_write_query_uses_empty_dict_when_params_none():
    """run_write_query uses empty dict when params is None."""
    session = MagicMock()
    run_write_query(session, "RETURN 1", None)
    session.run.assert_called_once_with("RETURN 1", {})


def test_run_batched_write_empty_rows_no_op():
    """run_batched_write with empty rows does not call session.run."""
    session = MagicMock()
    run_batched_write(session, "UNWIND $rows AS row RETURN row", [])
    session.run.assert_not_called()


def test_run_batched_write_single_batch():
    """run_batched_write with rows <= batch_size runs once."""
    session = MagicMock()
    rows = [{"id": "a"}, {"id": "b"}]
    run_batched_write(session, "UNWIND $rows AS row RETURN row", rows, batch_size=500)
    session.run.assert_called_once()
    call_args = session.run.call_args
    assert call_args[0][1]["rows"] == rows


def test_run_batched_write_splits_into_batches():
    """run_batched_write with more rows than batch_size runs multiple times."""
    session = MagicMock()
    rows = [{"i": i} for i in range(5)]
    run_batched_write(session, "UNWIND $rows AS row RETURN row", rows, batch_size=2)
    assert session.run.call_count == 3  # 2+2+1
    calls = session.run.call_args_list
    assert len(calls[0][0][1]["rows"]) == 2
    assert len(calls[1][0][1]["rows"]) == 2
    assert len(calls[2][0][1]["rows"]) == 1


def test_run_batched_write_custom_rows_param():
    """run_batched_write uses custom rows_param key when given."""
    session = MagicMock()
    rows = [{"id": "x"}]
    run_batched_write(session, "UNWIND $batch AS row RETURN row", rows, rows_param="batch")
    session.run.assert_called_once()
    assert "batch" in session.run.call_args[0][1]
    assert session.run.call_args[0][1]["batch"] == rows


def test_get_driver_returns_driver():
    """get_driver returns a Neo4j Driver instance (requires config/env)."""
    driver = get_driver()
    assert driver is not None
    try:
        driver.close()
    except Exception:
        pass
