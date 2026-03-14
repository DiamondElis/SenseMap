"""Pipeline config from environment."""
import os

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Chunking (tunable)
PARENT_CHUNK_SIZE = int(os.getenv("PARENT_CHUNK_SIZE", "2048"))
PARENT_CHUNK_OVERLAP = int(os.getenv("PARENT_CHUNK_OVERLAP", "256"))
CHILD_CHUNK_SIZE = int(os.getenv("CHILD_CHUNK_SIZE", "512"))
CHILD_CHUNK_OVERLAP = int(os.getenv("CHILD_CHUNK_OVERLAP", "64"))

# Embedding model (1536 to match schema)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
