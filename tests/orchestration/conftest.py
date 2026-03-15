"""
Orchestration tests: ensure Airflow DAG and plugin paths are on sys.path
so DAG modules (lexical_ingestion, entity_graph, enrichment, conversation_memory) and sensemap plugins load.
"""
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
_dags = _repo_root / "orchestration" / "airflow" / "dags"
_plugins = _repo_root / "orchestration" / "airflow" / "plugins"
for _p in (_plugins, _dags):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
