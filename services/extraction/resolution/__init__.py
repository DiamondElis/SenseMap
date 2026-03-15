"""Entity resolution: canonicalize, fuzzy match, embedding match, merge policy."""
from .canonicalize import canonicalize_name, glossary_canonical_name
from .fuzzy_match import fuzzy_match_entity
from .embedding_match import embedding_match_entity, EMBEDDING_STRONG, EMBEDDING_MARGINAL, SHORT_NAME_MAX_LENGTH
from .merge import ResolutionResult, resolve_entity

__all__ = [
    "canonicalize_name",
    "glossary_canonical_name",
    "fuzzy_match_entity",
    "embedding_match_entity",
    "EMBEDDING_STRONG",
    "EMBEDDING_MARGINAL",
    "SHORT_NAME_MAX_LENGTH",
    "ResolutionResult",
    "resolve_entity",
]
