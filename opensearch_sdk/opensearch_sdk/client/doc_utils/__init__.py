import sys
import os
import importlib.util

from opensearch_sdk.client.doc_utils.nested_handler import (
    _reconstruct_nested_structure,
    _flatten_nested_value,
    _flatten_nested_document,
    has_nested_fields,
)

from opensearch_sdk.client.doc_utils.serialization import (
    process_body_fields,
)

from opensearch_sdk.client.doc_utils.type_inference import (
    infer_column_type_from_value,
)

from opensearch_sdk.client.doc_utils.helpers import (
    with_sql_trace,
    handle_document_exception,
    validate_index,
    validate_document_params,
    prepare_document,
    build_insert_sql,
    build_update_sql,
    with_search_trace,
)

from opensearch_sdk.client.doc_utils.operations import (
    DocumentOperationsMixin,
)

from opensearch_sdk.client.doc_utils.query_executor import (
    QueryExecutor,
)
# 注意：这里需要从父目录的 document_ops.py 文件导入
# 临时添加父目录到路径以导入原文件
_parent_dir = os.path.dirname(os.path.dirname(__file__))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# 直接导入原文件中的类
spec = importlib.util.spec_from_file_location(
    "document_ops_original",
    os.path.join(_parent_dir, "document_ops.py")
)
document_ops_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(document_ops_module)
DocumentOpsMixin = document_ops_module.DocumentOpsMixin

# 清理路径
if _parent_dir in sys.path:
    sys.path.remove(_parent_dir)

__all__ = [
    'DocumentOpsMixin',
    'process_body_fields',
    '_reconstruct_nested_structure',
    '_flatten_nested_value',
    '_flatten_nested_document',
    'has_nested_fields',
    'infer_column_type_from_value',
    'with_sql_trace',
    'handle_document_exception',
    'validate_index',
    'validate_document_params',
    'prepare_document',
    'build_insert_sql',
    'build_update_sql',
    'QueryExecutor',
    'with_search_trace',
]
