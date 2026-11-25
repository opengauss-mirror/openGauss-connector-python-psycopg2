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

from opensearch_sdk.client.search.knn_handler import (
    parse_knn_config,
    merge_knn_and_bool_filters,
)

from opensearch_sdk.client.search.helpers import (
    reconstruct_nested_structure,
    verify_match_phrase,
    match_column_patterns,
    verify_match_phrase_with_gap,
    build_must_not_condition,
    matches_clause,
)

from opensearch_sdk.client.search.result_builder import (
    build_search_hits,
    format_search_response,
    build_knn_hits,
)

from opensearch_sdk.client.search.query_builder_ext import (
    process_source_filter,
    build_sort_clause,
    build_limit_clause,
    build_select_clause,
)

from opensearch_sdk.client.search.convenience import (
    create_search_by_category_body,
    create_search_by_multiple_fields_body,
)

__all__ = [
    'parse_knn_config',
    'merge_knn_and_bool_filters',
    'reconstruct_nested_structure',
    'verify_match_phrase',
    'match_column_patterns',
    'verify_match_phrase_with_gap',
    'build_must_not_condition',
    'matches_clause',
    'build_search_hits',
    'format_search_response',
    'build_knn_hits',
    'process_source_filter',
    'build_sort_clause',
    'build_limit_clause',
    'build_select_clause',
    'create_search_by_category_body',
    'create_search_by_multiple_fields_body',
]
