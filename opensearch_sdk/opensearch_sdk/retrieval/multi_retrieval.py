"""
Multi-path Retrieval and Fusion Module

Forward module: re-exports from project's lib directory to maintain backward compatibility.
All implementations now come from lib/multi_retrieval.py (psycopg2 package).
"""

# Import from project's lib directory using absolute import
from psycopg2.multi_retrieval import (
    # Normalization methods
    NormMethod,
    # Fusion strategies
    FusionStrategy,
    RRFFusion,
    WeightedFusion,
    ModelRerankFusion,
    MultiRetrievalEngine,
)

__all__ = [
    "NormMethod",
    "FusionStrategy",
    "RRFFusion",
    "WeightedFusion",
    "ModelRerankFusion",
    "MultiRetrievalEngine",
]
