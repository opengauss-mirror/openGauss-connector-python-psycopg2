import json
from typing import Any, Dict, Optional, Callable

from opensearch_sdk.client.utils import normalize_identifier
from opensearch_sdk.client.query_builder import _validate_identifier


def _load_field_types(index: str, get_mapping_func: Optional[Callable]) -> Dict[str, str]:
    if not index or not get_mapping_func:
        return {}
    try:
        mapping = get_mapping_func(index)
    except Exception:
        return {}
    if not mapping or 'mappings' not in mapping:
        return {}
    properties = mapping['mappings'].get('properties', {})
    return {
        field_name: field_info['type']
        for field_name, field_info in properties.items()
        if isinstance(field_info, dict) and 'type' in field_info
    }


def _serialize_field_value(normalized_key: str, value: Any, field_types: Dict[str, str]) -> Any:
    if isinstance(value, list):
        field_type = field_types.get(normalized_key)
        is_list_field = normalized_key.endswith('list') or normalized_key.endswith('List')
        if is_list_field or (field_type and field_type.endswith('[]')):
            return json.dumps(value, ensure_ascii=False)
        if len(value) > 0 and all(isinstance(v, (int, float)) for v in value):
            return json.dumps(value, ensure_ascii=False)
        return json.dumps([str(v) for v in value], ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def process_body_fields(
    body: Dict[str, Any], 
    index: str = None,
    get_mapping_func: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    处理 body 中的字段，转换复杂类型为 JSON 字符串格式
    
    Args:
        body: 原始文档内容
        index: 索引名称（用于获取 mapping 信息）
        get_mapping_func: 获取mapping的函数（可选），签名为 func(index) -> dict
        
    Returns:
        处理后的文档内容（字段名已标准化）
    """
    processed_body = {}
    
    field_types = _load_field_types(index, get_mapping_func)
    
    for key, value in body.items():
        # [OK] 先标准化字段名
        normalized_key = normalize_identifier(key, "Document field")
        _validate_identifier(normalized_key)
        
        processed_body[normalized_key] = _serialize_field_value(normalized_key, value, field_types)
    
    return processed_body
