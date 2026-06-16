from typing import Any, Dict, List, Optional


def create_search_by_category_body(category: str, size: int = 10) -> Dict[str, Any]:
    """
    创建按分类搜索的请求体
    
    :param category: 分类名称
    :param size: 返回结果数量
    :return: 搜索请求体
    """
    return {
        "query": {
            "match_phrase": {
                "categories": category
            }
        },
        "size": size
    }


def create_search_by_multiple_fields_body(
    field_value_pairs: Dict[str, List[str]],
    source_fields: Optional[List[str]] = None,
    size: int = 10
) -> Dict[str, Any]:
    """
    创建多字段搜索的请求体
    
    :param field_value_pairs: 字段值对字典
    :param source_fields: 返回字段列表
    :param size: 返回结果数量
    :return: 搜索请求体
    """
    must_conditions = []
    for field, values in field_value_pairs.items():
        must_conditions.append({
            "terms": {
                field: values
            }
        })
    
    search_body = {
        "query": {
            "bool": {
                "must": must_conditions
            }
        },
        "size": size
    }
    
    if source_fields:
        search_body["_source"] = source_fields
    
    return search_body
