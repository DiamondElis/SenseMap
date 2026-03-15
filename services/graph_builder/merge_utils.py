"""
Reusable Neo4j write utilities: driver, single writes, batched UNWIND writes.
Connection info from shared config; driver/session handling isolated from business logic.
"""
from typing import Any, Optional

from neo4j import Driver, GraphDatabase

from shared.python.config import settings


def get_driver(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> Driver:
    """
    Return a Neo4j driver. Connection info from shared config when not passed.
    Caller is responsible for closing the driver when done (e.g. driver.close()).
    """
    u = uri or settings.NEO4J_URI
    usr = user or settings.NEO4J_USER
    pwd = password or settings.NEO4J_PASSWORD
    return GraphDatabase.driver(u, auth=(usr, pwd))


def run_write_query(
    session: Any,
    query: str,
    params: Optional[dict[str, Any]] = None,
) -> None:
    """
    Run a single write query in the given session. No result consumed.
    Use for MERGE/SET/CREATE statements. Params default to empty dict.
    """
    session.run(query, params or {})


def run_batched_write(
    session: Any,
    query: str,
    rows: list[dict[str, Any]],
    batch_size: int = 500,
    rows_param: str = "rows",
) -> None:
    """
    Run a parameterized write query repeatedly over chunks of rows (UNWIND-style).
    The query must accept the given parameter (default $rows) and use UNWIND $rows AS row.
    Each batch is executed in its own transaction. Empty rows list is a no-op.
    """
    if not rows:
        return
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        session.run(query, {rows_param: batch})
