"""API config: re-export shared settings and API-specific defaults."""
from shared.python.config import settings

NEO4J_URI = settings.NEO4J_URI
NEO4J_USER = settings.NEO4J_USER
NEO4J_PASSWORD = settings.NEO4J_PASSWORD
OPENAI_API_KEY = settings.OPENAI_API_KEY
EMBEDDING_MODEL = settings.OPENAI_EMBEDDING_MODEL
VECTOR_INDEX_NAME = "chunk_embedding"
