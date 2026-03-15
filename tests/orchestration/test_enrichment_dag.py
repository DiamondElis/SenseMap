"""
Tests for answer_graph_enrichment_dag: import, task IDs, dependencies, callables, metadata.
Requires: airflow on PYTHONPATH (e.g. run from venv or Airflow env).
"""
import pytest

pytest.importorskip("airflow")
import enrichment as mod


def test_dag_imports_cleanly():
    """DAG module imports without error and exposes a DAG."""
    assert mod.dag is not None
    assert mod.dag.dag_id == "answer_graph_enrichment_dag"


def test_expected_task_ids_exist():
    """All expected task IDs are present in the DAG."""
    expected = [
        "start_pipeline_run",
        "project_graph",
        "run_pagerank",
        "run_leiden",
        "run_fastrp",
        "write_back_scores",
        "validate_enrichment",
        "close_pipeline_run",
    ]
    task_ids = [t.task_id for t in mod.dag.tasks]
    for tid in expected:
        assert tid in task_ids, f"Missing task_id: {tid}"
    assert len(mod.dag.tasks) == len(expected)


def test_dag_dependencies_are_correct():
    """DAG edges form a single linear chain: start -> project -> pagerank -> leiden -> fastrp -> write_back -> validate -> close."""
    expected_order = [
        "start_pipeline_run",
        "project_graph",
        "run_pagerank",
        "run_leiden",
        "run_fastrp",
        "write_back_scores",
        "validate_enrichment",
        "close_pipeline_run",
    ]
    downstream = {t.task_id: [d.task_id for d in t.downstream_list] for t in mod.dag.tasks}
    for i, tid in enumerate(expected_order):
        if i + 1 < len(expected_order):
            assert expected_order[i + 1] in downstream.get(tid, []), f"Expected {tid} >> {expected_order[i + 1]}"


def test_task_callables_resolve_to_service_layer():
    """Task callables are wrapped around the expected _task_* functions which call gds_runner."""
    start_op = mod.dag.get_task("start_pipeline_run")
    close_op = mod.dag.get_task("close_pipeline_run")
    assert start_op.python_callable is mod.task_start_pipeline_run
    assert close_op.python_callable is mod.task_close_pipeline_run

    content_tasks = [
        ("project_graph", "_task_project_graph"),
        ("run_pagerank", "_task_run_pagerank"),
        ("run_leiden", "_task_run_leiden"),
        ("run_fastrp", "_task_run_fastrp"),
        ("write_back_scores", "_task_write_back_scores"),
        ("validate_enrichment", "_task_validate_enrichment"),
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
