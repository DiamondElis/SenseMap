"""
Tests for conversation_candidate_dag: import, task IDs, dependencies, callables, metadata.
Requires: airflow on PYTHONPATH (e.g. run from venv or Airflow env).
"""
import pytest

pytest.importorskip("airflow")
import conversation_memory as mod


def test_dag_imports_cleanly():
    """DAG module imports without error and exposes a DAG."""
    assert mod.dag is not None
    assert mod.dag.dag_id == "conversation_candidate_dag"


def test_expected_task_ids_exist():
    """All expected task IDs are present in the DAG."""
    expected = [
        "start_pipeline_run",
        "ingest_transcript",
        "extract_candidate_claims",
        "validate_candidates",
        "auto_merge_safe_items",
        "create_review_tasks",
        "close_pipeline_run",
    ]
    task_ids = [t.task_id for t in mod.dag.tasks]
    for tid in expected:
        assert tid in task_ids, f"Missing task_id: {tid}"
    assert len(mod.dag.tasks) == len(expected)


def test_dag_dependencies_are_correct():
    """DAG edges form a single linear chain from start through close."""
    expected_order = [
        "start_pipeline_run",
        "ingest_transcript",
        "extract_candidate_claims",
        "validate_candidates",
        "auto_merge_safe_items",
        "create_review_tasks",
        "close_pipeline_run",
    ]
    downstream = {t.task_id: [d.task_id for d in t.downstream_list] for t in mod.dag.tasks}
    for i, tid in enumerate(expected_order):
        if i + 1 < len(expected_order):
            assert expected_order[i + 1] in downstream.get(tid, []), f"Expected {tid} >> {expected_order[i + 1]}"


def test_task_callables_resolve_to_service_layer():
    """Task callables are wrapped around the expected _task_* functions which call conversation_memory service layer."""
    start_op = mod.dag.get_task("start_pipeline_run")
    close_op = mod.dag.get_task("close_pipeline_run")
    assert start_op.python_callable is mod.task_start_pipeline_run
    assert close_op.python_callable is mod.task_close_pipeline_run

    content_tasks = [
        ("ingest_transcript", "_task_ingest_transcript"),
        ("extract_candidate_claims", "_task_extract_candidate_claims"),
        ("validate_candidates", "_task_validate_candidates"),
        ("auto_merge_safe_items", "_task_auto_merge_safe_items"),
        ("create_review_tasks", "_task_create_review_tasks"),
    ]
    for task_id, inner_name in content_tasks:
        op = mod.dag.get_task(task_id)
        fn = op.python_callable
        assert callable(fn)
        inner = getattr(mod, inner_name, None)
        assert inner is not None
        if hasattr(fn, "__closure__") and fn.__closure__:
            cells = [c.cell_contents for c in fn.__closure__]
            assert any(getattr(c, "__name__", None) == inner_name for c in cells if callable(c))


def test_metadata_helpers_invoked():
    """PipelineRun/TaskRun metadata: start and close callables exist; DAG has on_failure_callback."""
    assert hasattr(mod, "task_start_pipeline_run") and callable(mod.task_start_pipeline_run)
    assert hasattr(mod, "task_close_pipeline_run") and callable(mod.task_close_pipeline_run)
    assert mod.dag.default_args.get("on_failure_callback") is mod._on_failure_callback
    assert mod._task_run_id("run_1", "ingest_transcript") == "run_1_ingest_transcript"
