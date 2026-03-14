"""Staged file I/O for DAG task handoff (production-shaped: no large XCom)."""
import json
from pathlib import Path

STAGED_BASE = Path("/opt/airflow/data/staged")


def staged_dir(run_id: str) -> Path:
    return STAGED_BASE / run_id


def ensure_staged(run_id: str) -> Path:
    d = staged_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(run_id: str, name: str, data: list | dict) -> Path:
    p = ensure_staged(run_id) / f"{name}.json"
    p.write_text(json.dumps(data, indent=0), encoding="utf-8")
    return p


def read_json(run_id: str, name: str) -> list | dict:
    p = staged_dir(run_id) / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))
