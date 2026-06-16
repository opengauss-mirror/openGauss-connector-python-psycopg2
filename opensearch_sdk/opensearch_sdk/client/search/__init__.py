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
