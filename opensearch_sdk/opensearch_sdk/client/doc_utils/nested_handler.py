from typing import Any, Dict


def _reconstruct_nested_structure(source: dict) -> dict:
    """
    将扁平化的 nested 字段还原为嵌套结构
    
    Args:
        source: 扁平化的文档（如 {'author__name': 'John', 'author__age': 30}）
        
    Returns:
        还原后的文档（如 {'author': [{'name': 'John', 'age': 30}]})
        
    Note:
        由于 Opensearch 使用首值策略，nested 数组只存储第一个元素，
        所以还原后返回单元素列表以符合 OpenSearch 格式。
    """
    from opensearch_sdk.client.constants import NESTED_FIELD_SEPARATOR
    
    result = {}
    nested_groups = {}  # {prefix: {subkey: value}}
    
    for key, value in source.items():
        if NESTED_FIELD_SEPARATOR in key:
            # 这是一个扁平化的 nested 字段
            parts = key.split(NESTED_FIELD_SEPARATOR, 1)
            prefix = parts[0]
            subkey = parts[1]
            
            if prefix not in nested_groups:
                nested_groups[prefix] = {}
            nested_groups[prefix][subkey] = value
        else:
            # 普通字段，直接复制
            result[key] = value
    
    # 将分组后的 nested 字段添加到结果中（包装为单元素列表）
    for prefix, fields in nested_groups.items():
        result[prefix] = [fields]  # [OK] 包装为列表，符合 OpenSearch 格式
    
    return result


def _flatten_nested_value(value: Any) -> Any:
    """
    处理 nested 字段的值，支持数组和字典两种格式（首值策略）
    
    Args:
        value: 原始值（可能是数组或字典）
        
    Returns:
        扁平化后的值
        
    Examples:
        >>> _flatten_nested_value([{"name": "John"}])
        {"name": "John"}
        >>> _flatten_nested_value({"name": "John"})
        {"name": "John"}
        >>> _flatten_nested_value(None)
        None
    """
    if value is None:
        return None
    
    if isinstance(value, list):
        # 数组格式：取第一个元素
        if len(value) == 0:
            return None
        elif len(value) == 1:
            return value[0]
        else:
            # [WARN] Known Issue: 多值情况只取第一个
            # TODO: 如果业务需要支持多值，需要重新设计存储方案
            return value[0]
    elif isinstance(value, dict):
        # 字典格式：直接返回
        return value
    else:
        # 其他类型：直接返回（可能是标量）
        return value


def _flatten_without_mapping(doc: dict) -> dict:
    flat_doc = {}
    for key, value in doc.items():
        _flatten_field(flat_doc, key, value)
    return flat_doc


def _flatten_field(flat_doc: dict, key: str, value: Any) -> None:
    from opensearch_sdk.client.constants import NESTED_FIELD_SEPARATOR

    if isinstance(value, dict):
        for sub_key, sub_value in value.items():
            flat_key = f"{key}{NESTED_FIELD_SEPARATOR}{sub_key}"
            flat_doc[flat_key] = sub_value
    elif isinstance(value, list):
        if len(value) == 0:
            return
        first_item = value[0]
        if isinstance(first_item, dict):
            for sub_key, sub_value in first_item.items():
                flat_key = f"{key}{NESTED_FIELD_SEPARATOR}{sub_key}"
                flat_doc[flat_key] = sub_value
        else:
            flat_doc[key] = value
    else:
        flat_doc[key] = value


def _flatten_nested_document(doc: dict, mapping: dict = None) -> dict:
    """
    将包含 nested 对象的文档展开为扁平字典（首值策略）
    
    Args:
        doc: 原始文档
        mapping: 索引 mapping（用于识别 nested 字段），如果为 None 则展开所有嵌套对象
               
        注意：mapping 可能是两种格式：
        1. {'mappings': {...}} （直接 mappings）
        2. {'index_name': {'mappings': {...}}} （带索引名的嵌套）
        
    Returns:
        扁平化后的文档
    """
    # [OK] 如果没有 mapping 或 mapping 中没有 properties，直接展开所有嵌套对象
    if not mapping or (isinstance(mapping, dict) and 'mappings' not in mapping and len(mapping) == 0):
        return _flatten_without_mapping(doc)
    
    # 处理映射格式差异：提取实际的 mappings
    if 'mappings' in mapping:
        # 格式 1：直接包含 mappings
        actual_mapping = mapping
    else:
        # 格式 2：索引名在外层，取第一个索引的 mapping
        index_name = list(mapping.keys())[0]
        actual_mapping = mapping[index_name]
    
    if 'mappings' not in actual_mapping:
        return _flatten_without_mapping(doc)
    
    properties = actual_mapping['mappings'].get('properties', {})
    flat_doc = {}
    
    for key, value in doc.items():
        _flatten_field(flat_doc, key, value)
    
    return flat_doc


def has_nested_fields(mapping: dict) -> bool:
    """
    检查 mapping 是否包含 nested 字段
    
    Args:
        mapping: 索引 mapping
        
    Returns:
        True 如果包含 nested 字段，否则 False
        
    Note:
        由于 Opensearch 在创建索引时会将 nested 展开为普通列，
        因此无法从展开后的 mapping 中识别 nested。
        这个方法目前主要用于向前兼容，实际判断逻辑已移至_write时的智能检测。
    """
    if not mapping or 'mappings' not in mapping:
        return False
    
    # 处理映射格式差异
    if 'mappings' in mapping:
        actual_mapping = mapping
    else:
        index_name = list(mapping.keys())[0]
        actual_mapping = mapping[index_name]
    
    if 'mappings' not in actual_mapping:
        return False
    
    properties = actual_mapping['mappings'].get('properties', {})
    return any(
        props.get('type') == 'nested' 
        for props in properties.values()
    )
