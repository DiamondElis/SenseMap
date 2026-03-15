"""Shared Neo4j and embedding helpers for retrievers."""
from typing import Optional

from neo4j import GraphDatabase

from shared.python.config import settings

VECTOR_INDEX_NAME = "chunk_embedding"


def get_driver(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
):
    """Neo4j driver using shared config when args not provided."""
    u = uri or settings.NEO4J_URI
    usr = user or settings.NEO4J_USER
    pwd = password or settings.NEO4J_PASSWORD
    return GraphDatabase.driver(u, auth=(usr, pwd))
