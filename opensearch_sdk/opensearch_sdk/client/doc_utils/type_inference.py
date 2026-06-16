from typing import Any
import re


def infer_column_type_from_value(value: Any, field_name: str = None) -> str:
    """
    根据样本值推断列类型（降级方案）
    
    Args:
        value: 样本值
        field_name: 字段名（可选，用于智能识别数组类型）
        
    Returns:
        SQL 类型名称
        
    Examples:
        >>> infer_column_type_from_value(123)
        'BIGINT'
        >>> infer_column_type_from_value(12.5)
        'FLOAT4'
        >>> infer_column_type_from_value("text")
        'TEXT'
        >>> infer_column_type_from_value(True)
        'BOOLEAN'
        >>> infer_column_type_from_value([0.1] * 128)
        'VECTOR(128)'
        >>> infer_column_type_from_value([1, 2, 3], "scores_list")
        'INTEGER[]'
    """
    if value is None:
        return 'TEXT'  # 默认
    
    if isinstance(value, bool):
        return 'BOOLEAN'
    elif isinstance(value, int):
        return 'BIGINT'
    elif isinstance(value, float):
        return 'FLOAT4'
    elif isinstance(value, str):
        # 简单的日期格式检测（避免依赖 dateutil）
        # ISO 8601 日期格式：YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS
        if re.match(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$', value):
            return 'TIMESTAMP'
        return 'TEXT'
    elif isinstance(value, list):
        # [OK] 智能数组识别：如果字段名以 list/List 结尾，强制使用 TEXT 类型（JSON序列化存储）
        if field_name and (field_name.endswith('list') or field_name.endswith('List')):
            return 'TEXT'
        
        # 检查是否为数值数组（向量）
        if _is_numeric_vector(value):
            dimension = len(value)
            return f'VECTOR({dimension})'
        # 其他列表类型存储为 JSONB
        return 'JSONB'
    elif isinstance(value, dict):
        return 'JSONB'
    else:
        return 'TEXT'


def _is_numeric_vector(value: list, min_dimension: int = 100) -> bool:
    """
    检查列表是否为数值向量
    
    Args:
        value: 待检查的列表
        min_dimension: 最小维度阈值，默认100
        
    Returns:
        True 如果是数值向量，否则 False
    """
    # 长度检查：必须达到最小维度
    if len(value) < min_dimension:
        return False
    
    # 元素类型检查：所有元素必须是数值类型（int 或 float）
    for item in value:
        if not isinstance(item, (int, float)):
            return False
        # 排除布尔值（bool 是 int 的子类）
        if isinstance(item, bool):
            return False
    
    return True


