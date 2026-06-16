"""
Unified Retriever Module

Forward module: re-exports from project's lib directory to maintain backward compatibility.
All implementations now come from lib/retrievers.py (psycopg2 package).

Provides vector and full-text retrieval with shared infrastructure:
- GUC parameter lifecycle management (SET before query, RESET after)
- Connection pool integration (get → use → return)
- Parameter resolution (call-time overrides preset defaults)

Ref: https://docs.opengauss.org/zh/docs/latest/database_reference/datavec_vector_engine_parameters.html
"""

# Import from project's lib directory using absolute import
from psycopg2.retrievers import (
    RetrievalResult,
    BaseRetriever,
    VectorRetriever,
    FullTextRetriever,
)

__all__ = [
    "RetrievalResult",
    "BaseRetriever",
    "VectorRetriever",
    "FullTextRetriever",
]
