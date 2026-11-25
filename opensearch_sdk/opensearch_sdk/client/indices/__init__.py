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

from opensearch_sdk.client.indices.helpers import (
    ENABLE_PYTHON_VALIDATION,
    set_validation_enabled,
    get_validation_enabled,
    validate_mapping_schema,
    expand_nested_fields,
)

from opensearch_sdk.client.indices.sql_generator import (
    generate_create_table_sql,
    generate_index_sql,
    generate_bm25_set_sql,
    generate_mapping_comment_sql,
)

from opensearch_sdk.client.indices.operations import (
    execute_delete,
    execute_exists,
    execute_get_mapping_from_comment,
    build_mapping_from_columns,
    build_mapping_from_comment,
    execute_refresh,
    execute_analyze,
    execute_get_all_index_names,
    execute_rebuild_index,
)

__all__ = [
    # Helpers
    'ENABLE_PYTHON_VALIDATION',
    'set_validation_enabled',
    'get_validation_enabled',
    'validate_mapping_schema',
    'expand_nested_fields',
    # SQL Generator
    'generate_create_table_sql',
    'generate_index_sql',
    'generate_bm25_set_sql',
    'generate_mapping_comment_sql',
    # Operations
    'execute_delete',
    'execute_exists',
    'execute_get_mapping_from_comment',
    'build_mapping_from_columns',
    'build_mapping_from_comment',
    'execute_refresh',
    'execute_analyze',
    'execute_get_all_index_names',
    'execute_rebuild_index',
]
