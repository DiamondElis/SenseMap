"""
Tests for lexical_ingestion_dag: import, task IDs, dependencies, callables, metadata.
Requires: airflow on PYTHONPATH (e.g. run from venv or Airflow env).
"""
import pytest

pytest.importorskip("airflow")
import lexical_ingestion as mod


def test_dag_imports_cleanly():
    """DAG module imports without error and exposes a DAG."""
    assert mod.dag is not None
    assert mod.dag.dag_id == "lexical_ingestion_dag"


def test_expected_task_ids_exist():
    """All expected task IDs are present in the DAG."""
    expected = [
        "start_pipeline_run",
        "load_document",
        "parse_document",
        "chunk_document",
        "embed_child_chunks",
        "write_lexical_graph",
        "validate_lexical_graph",
        "close_pipeline_run",
    ]
    task_ids = [t.task_id for t in mod.dag.tasks]
    for tid in expected:
        assert tid in task_ids, f"Missing task_id: {tid}"
    assert len(mod.dag.tasks) == len(expected)


def test_dag_dependencies_are_correct():
    """DAG edges form a single linear chain: start -> load -> parse -> chunk -> embed -> write -> validate -> close."""
    expected_order = [
        "start_pipeline_run",
        "load_document",
        "parse_document",
        "chunk_document",
        "embed_child_chunks",
        "write_lexical_graph",
        "validate_lexical_graph",
        "close_pipeline_run",
    ]
    downstream = {t.task_id: [d.task_id for d in t.downstream_list] for t in mod.dag.tasks}
    for i, tid in enumerate(expected_order):
        if i + 1 < len(expected_order):
            assert expected_order[i + 1] in downstream.get(tid, []), f"Expected {tid} >> {expected_order[i + 1]}"
    assert "close_pipeline_run" in downstream.get("validate_lexical_graph", [])


def test_task_callables_resolve_to_service_layer():
    """Task callables are wrapped around the expected _task_* functions which call sensemap/service layer."""
    # start and close are plain callables
    start_op = mod.dag.get_task("start_pipeline_run")
    close_op = mod.dag.get_task("close_pipeline_run")
    assert start_op.python_callable is mod.task_start_pipeline_run
    assert close_op.python_callable is mod.task_close_pipeline_run

    # Content tasks are _with_metadata(task_id, _task_*); closure holds the inner _task_*
    content_tasks = [
        ("load_document", "_task_load_document"),
        ("parse_document", "_task_parse_document"),
        ("chunk_document", "_task_chunk_document"),
        ("embed_child_chunks", "_task_embed_child_chunks"),
        ("write_lexical_graph", "_task_write_lexical_graph"),
        ("validate_lexical_graph", "_task_validate_lexical_graph"),
    ]
    for task_id, inner_name in content_tasks:
        op = mod.dag.get_task(task_id)
        fn = op.python_callable
        assert callable(fn)
        # Wrapper is a closure; the content function is in the closure
        inner = getattr(mod, inner_name, None)
        assert inner is not None
        # Wrapper was built as _with_metadata(task_id, inner); closure has inner
        if hasattr(fn, "__closure__") and fn.__closure__:
            cells = [c.cell_contents for c in fn.__closure__]
            assert any(getattr(c, "__name__", None) == inner_name for c in cells if callable(c))


def test_metadata_helpers_invoked():
    """PipelineRun/TaskRun metadata: start and close callables exist; DAG has on_failure_callback."""
    assert hasattr(mod, "task_start_pipeline_run") and callable(mod.task_start_pipeline_run)
    assert hasattr(mod, "task_close_pipeline_run") and callable(mod.task_close_pipeline_run)
    assert mod.dag.default_args.get("on_failure_callback") is mod._on_failure_callback
    assert mod._task_run_id("run_1", "load_document") == "run_1_load_document"
