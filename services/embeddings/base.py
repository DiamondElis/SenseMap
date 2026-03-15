"""Pluggable embedding backends: protocol and return shape."""
from typing import Protocol


class Embedder(Protocol):
    """Backend interface: embed a list of texts and return vectors (one per text)."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed each text. Returns list of vectors (list[float]) in same order as input.
        Length of each vector is backend-defined (e.g. 1536 for OpenAI, 768 for BGE).
        """
        ...
