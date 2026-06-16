from functools import partial, wraps
from typing import Any, Callable, Dict, Optional


_MISSING = object()


def _trace_enabled(client) -> bool:
    return bool(hasattr(client, 'sql_tracer') and client.sql_tracer and client.sql_tracer.enabled)


def _trace_index(args, kwargs) -> str:
    return args[0] if args else kwargs.get('index', 'unknown')


def _last_trace_record(session):
    if session and len(session.records) > 0:
        return session.records[-1]
    return None


def _apply_document_trace_metadata(record, operation_name: str, args) -> None:
    if operation_name == "create" and len(args) >= 3:
        record.metadata['document_id'] = args[1]
        record.metadata['field_count'] = len(args[2]) if isinstance(args[2], dict) else 0
    elif operation_name == "update" and len(args) >= 3:
        record.metadata['document_id'] = args[1]
        record.metadata['updated_fields'] = list(args[2].keys()) if isinstance(args[2], dict) else []
    elif operation_name in ("get", "delete") and len(args) >= 2:
        record.metadata['document_id'] = args[1]


def _apply_document_trace(record, operation_name: str, index: str, args, kwargs) -> None:
    _apply_document_trace_metadata(record, operation_name, args)
    record.context = f"{operation_name}_{index}"


def _search_metadata_value(param_name: str, args, kwargs):
    positional_indexes = {
        'body': 1,
        'query_vector': 2,
        'k': 3,
    }
    arg_index = positional_indexes.get(param_name)
    if arg_index is not None and len(args) > arg_index:
        return args[arg_index]
    if param_name in kwargs:
        return kwargs[param_name]
    return _MISSING


def _search_trace_context(operation_name: str, index: str) -> str:
    if operation_name == "search":
        return f"search_query_{index}"
    return f"{operation_name}_{index}"


def _apply_search_trace(record, operation_name: str, index: str, args, kwargs, metadata_kwargs) -> None:
    for metadata_key, param_name in metadata_kwargs.items():
        value = _search_metadata_value(param_name, args, kwargs)
        if value is not _MISSING:
            record.metadata[metadata_key] = value
    record.context = _search_trace_context(operation_name, index)


def _run_traced_operation(client, operation_name: str, func: Callable, args, kwargs, trace_updater: Callable):
    if not _trace_enabled(client):
        return func(client, *args, **kwargs)

    index = _trace_index(args, kwargs)
    with client.sql_tracer.trace_session(operation_name, index) as session:
        result = func(client, *args, **kwargs)
        last_record = _last_trace_record(session)
        if last_record:
            trace_updater(last_record, operation_name, index, args, kwargs)
        return result


def with_sql_trace(operation_name: str):
    """
    SQL 追踪装饰器：自动包装带有 SQL 追踪的操作
    
    Args:
        operation_name: 操作名称（如 "create", "update", "get", "delete"）
        
    Returns:
        装饰器函数
        
    Example:
        @with_sql_trace("create")
        def _create_impl(self, index, id, body, refresh=False):
            # 实现逻辑
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            return _run_traced_operation(self, operation_name, func, args, kwargs, _apply_document_trace)
        return wrapper
    return decorator


def handle_document_exception(operation_name: str):
    """
    文档操作异常处理装饰器：统一处理回滚和错误消息
    
    Args:
        operation_name: 操作名称（用于错误消息）
        
    Returns:
        装饰器函数
        
    Example:
        @handle_document_exception("Create Document")
        def _create_impl(self, index, id, body, refresh=False):
            # 实现逻辑，异常会自动回滚并格式化错误消息
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                # [FIX] 在连接池模式下，不应该在这里调用 rollback
                # 因为 self.rollback() 会获取新连接，无法回滚实际执行 SQL 的连接
                # 应该让调用者通过上下文管理器自行处理事务
                if hasattr(self, 'connection') and self.connection.use_connection_pool:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"{operation_name} failed. In pool mode, automatic rollback() "
                        "is not effective because it would execute on a different connection. "
                        "Use transaction() context manager for proper transaction management."
                    )
                
                # 提取关键参数用于错误消息
                index = args[0] if args else kwargs.get('index', 'unknown')
                doc_id = args[1] if len(args) > 1 else kwargs.get('id', 'unknown')
                
                # 格式化错误消息
                error_msg = f"##OS## - {operation_name} Error | index={index} | id={doc_id} | error: {str(e)}"
                raise Exception(error_msg)
        return wrapper
    return decorator


def validate_index(index: str) -> str:
    """
    验证并标准化索引名称
    
    Args:
        index: 原始索引名称
        
    Returns:
        标准化后的索引名称
        
    Raises:
        ValueError: 如果索引名称无效
    """
    from opensearch_sdk.client.utils import normalize_identifier
    
    if not index or not isinstance(index, str):
        raise ValueError("Index name must be a non-empty string")
    
    return normalize_identifier(index, "Index name")


def validate_document_params(index: str, doc_id, body: Optional[Dict[str, Any]] = None) -> tuple:
    """
    验证文档操作的基本参数
    
    Args:
        index: 索引名称
        doc_id: 文档 ID（支持字符串、整数等可转换类型；如果为 None 或空字符串，将自动生成 UUID）
        body: 文档内容（可选）
        
    Returns:
        (validated_index, validated_id, validated_body) 元组
        
    Raises:
        ValueError: 如果参数无效
    """
    import uuid
    
    validated_index = validate_index(index)
    
    # [OK] 如果未提供 ID 或为空字符串，自动生成 UUID（类似 OpenSearch 行为）
    if doc_id is None or doc_id == '':
        doc_id = str(uuid.uuid4())
    
    # 自动将非字符串 ID 转换为字符串（提高兼容性）
    if not isinstance(doc_id, str):
        try:
            doc_id = str(doc_id)
        except Exception:
            raise ValueError(f"Document ID cannot be converted to string: {type(doc_id).__name__}")
    
    # 最终验证（理论上不会触发，因为上面已经处理了 None 和空字符串）
    if not doc_id:
        raise ValueError("Document ID must be a non-empty string")
    
    validated_body = None
    if body is not None:
        if not isinstance(body, dict):
            raise ValueError("Document body must be a dictionary")
        validated_body = body
    
    return validated_index, doc_id, validated_body


def prepare_document(
    body: Dict[str, Any],
    index: str,
    get_mapping_func,
    has_nested_check_func,
    process_body_func,
    flatten_nested_func
) -> Dict[str, Any]:
    """
    统一处理文档预处理流程
    
    Args:
        body: 原始文档内容
        index: 索引名称
        get_mapping_func: 获取mapping的函数
        has_nested_check_func: 检查是否有nested字段的函数
        process_body_func: 处理body字段的函数
        flatten_nested_func: 扁平化nested的函数
        
    Returns:
        处理后的文档内容
    """
    from opensearch_sdk.client.utils import normalize_identifier
    
    # [OK] 处理 nested 字段扁平化（首值策略）
    # 智能检测：如果 body 中包含 dict 或 list 类型的值，尝试扁平化
    needs_flatten = any(
        isinstance(value, (dict, list)) 
        for value in body.values()
    )
    
    if needs_flatten:
        mapping = get_mapping_func(index)
        if mapping and has_nested_check_func(mapping):
            body = flatten_nested_func(body, mapping)
    
    # [OK] 标准化文档字段名（将 . 和 - 替换为 _）
    normalized_body = {}
    for key, value in body.items():
        normalized_key = normalize_identifier(key, "Document field")
        normalized_body[normalized_key] = value
    
    # 处理 body 中的字段，转换复杂类型为 JSON 字符串
    processed_body = process_body_func(normalized_body, index)
    
    return processed_body


def build_insert_sql(index: str, doc_id: str, processed_body: Dict[str, Any]):
    """
    构建 INSERT SQL 语句
    
    Args:
        index: 索引名称（已验证）
        doc_id: 文档 ID
        processed_body: 处理后的文档内容
        
    Returns:
        (sql_query, values) 元组
    """
    from psycopg2 import sql
    
    columns = ['id'] + list(processed_body.keys())
    values = [doc_id] + list(processed_body.values())
    column_identifiers = [sql.Identifier(col) for col in columns]
    columns_clause = sql.SQL(", ").join(column_identifiers)
    placeholders = sql.SQL(", ").join([sql.Placeholder()] * len(values))
    
    sql_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(index),
        columns_clause,
        placeholders
    )
    
    return sql_query, values


def build_update_sql(index: str, doc_id: str, processed_body: Dict[str, Any]):
    """
    构建 UPDATE SQL 语句
    
    Args:
        index: 索引名称（已验证）
        doc_id: 文档 ID
        processed_body: 处理后的文档内容
        
    Returns:
        (sql_query, values) 元组
    """
    from psycopg2 import sql
    
    set_parts = []
    values = []
    for key, value in processed_body.items():
        set_parts.append(sql.SQL("{} = %s").format(sql.Identifier(key)))
        values.append(value)
    
    values.append(doc_id)
    set_clause = sql.SQL(", ").join(set_parts)
    
    sql_query = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
        sql.Identifier(index),
        set_clause
    )
    
    return sql_query, values


def with_search_trace(operation_name: str, **metadata_kwargs):
    """
    搜索操作 SQL 追踪装饰器
    
    Args:
        operation_name: 操作名称（如 "search", "knn_search"）
        **metadata_kwargs: 要记录的元数据键值对
        
    Returns:
        装饰器函数
        
    Example:
        @with_search_trace("search", query_body='body')
        def _search_impl(self, index, body):
            pass
            
        @with_search_trace("knn_search", query_vector='query_vector', k='k')
        def _knn_search_impl(self, index, field, query_vector, k=10):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            trace_updater = partial(_apply_search_trace, metadata_kwargs=metadata_kwargs)
            return _run_traced_operation(self, operation_name, func, args, kwargs, trace_updater)
        return wrapper
    return decorator
