"""
Retrieval Module

Provides unified vector and full-text retrieval capabilities for openGauss.
Reuses psycopg2 (lib) implementation to avoid code duplication.
"""

from psycopg2.retrievers import (
    BaseRetriever,
    VectorRetriever,
    FullTextRetriever,
)
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

# Import models from psycopg2 (only available classes)
from psycopg2.models import (
    DashScopeModel,
)

# Import from local types module (which re-exports from psycopg2.vector_types)
from opensearch_sdk.retrieval.types import (
    # Enumerations
    ColumnType,
    IndexType,
    VectorDataType,
    DistanceMetric,
    RabitQRefineType,
    # Data classes
    ColumnSchema,
    TableSchema,
    IndexConfig,
    SearchResult,
    RetrievalResult,  # Defined locally in types.py
    # Exceptions
    VectorDBException,
    TableNotFoundException,
    IndexNotFoundException,
    InvalidSchemaException,
    InvalidQueryException,
)

__all__ = [
    # Enumerations
    "ColumnType",
    "IndexType",
    "VectorDataType",
    "DistanceMetric",
    "RabitQRefineType",
    # Data classes
    "ColumnSchema",
    "TableSchema",
    "IndexConfig",
    "RetrievalResult",
    "SearchResult",
    # Retriever classes
    "BaseRetriever",
    "VectorRetriever",
    "FullTextRetriever",
    # Normalization methods
    "NormMethod",
    # Fusion strategies
    "FusionStrategy",
    "RRFFusion",
    "WeightedFusion",
    "ModelRerankFusion",
    "MultiRetrievalEngine",
    # Rerank models
    "DashScopeModel",
    # Exceptions
    "VectorDBException",
    "TableNotFoundException",
    "IndexNotFoundException",
    "InvalidSchemaException",
    "InvalidQueryException",
]
