# Copyright (c) 2026 Huawei Technologies Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
    # Trusted SQL fragments
    "TrustedSQL",
    "trusted_sql",
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
