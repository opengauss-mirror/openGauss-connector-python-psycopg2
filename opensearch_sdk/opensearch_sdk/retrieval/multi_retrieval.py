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
