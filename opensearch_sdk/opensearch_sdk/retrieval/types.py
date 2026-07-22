"""
Vector Database Type Definition Module - OpenSearch SDK Extensions

This module extends psycopg2.vector_types with additional types specific to OpenSearch SDK.
All common types are imported from psycopg2.vector_types to avoid code duplication.
"""

from typing import Any, Dict
from dataclasses import dataclass, field

# Import all common types from psycopg2 (lib directory)
from psycopg2.vector_types import (
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
    # Trusted SQL fragments
    TrustedSQL,
    trusted_sql,
    # Exceptions
    VectorDBException,
    TableNotFoundException,
    IndexNotFoundException,
    InvalidSchemaException,
    InvalidQueryException,
)


@dataclass
class RetrievalResult:
    """Retrieval result (unified format for vector and full-text)

    This class is specific to OpenSearch SDK and not available in psycopg2.vector_types
    """
    id: Any
    score: float
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""  # "vector" or "fulltext"


__all__ = [
    # Re-exported from psycopg2.vector_types
    "ColumnType",
    "IndexType",
    "VectorDataType",
    "DistanceMetric",
    "RabitQRefineType",
    "ColumnSchema",
    "TableSchema",
    "IndexConfig",
    "SearchResult",
    "TrustedSQL",
    "trusted_sql",
    "VectorDBException",
    "TableNotFoundException",
    "IndexNotFoundException",
    "InvalidSchemaException",
    "InvalidQueryException",
    # Defined in this module
    "RetrievalResult",
]
