from typing import Dict, Any, Optional
from opensearch_sdk.client.utils import normalize_identifier


def parse_knn_config(knn_config: Dict[str, Any]) -> tuple:
    """
    解析 OpenSearch 标准格式的 kNN 配置
    
    OpenSearch 标准格式:
    {
        "field_name": {
            "vector": [...],
            "k": 10,
            "num_candidates": 100,
            "filter": {...},
            "similarity": "cosine"
        }
    }
    
    :param knn_config: kNN 配置字典
    :return: (field, query_vector, k, num_candidates, filter_query, similarity)
    :raises ValueError: 当配置格式不正确时
    """
    # OpenSearch 标准格式：knn_config 只有一个键值对，键是字段名
    if not knn_config or len(knn_config) != 1:
        raise ValueError(
            "Invalid kNN query format. Expected OpenSearch standard format: "
            "{\"field_name\": {\"vector\": [...], \"k\": 10}}"
        )
    
    # [OK] 标准化字段名（将 . 和 - 替换为 _）
    original_field = list(knn_config.keys())[0]
    field = normalize_identifier(original_field, "kNN field")
    config = knn_config[original_field]
    
    # 提取参数（使用 OpenSearch 标准键名）
    query_vector = config.get("vector")  # [OK] OpenSearch 使用 "vector"
    if query_vector is None:
        raise ValueError("Missing required parameter 'vector' in kNN query")
    
    k = config.get("k", 10)
    num_candidates = config.get("num_candidates")
    filter_query = config.get("filter")
    similarity = config.get("similarity", "cosine")
    
    return field, query_vector, k, num_candidates, filter_query, similarity


def _as_bool_filter(filter_value):
    if isinstance(filter_value, list):
        return {"bool": {"filter": filter_value}}
    return filter_value


def _is_standalone_bool_query(filter_value) -> bool:
    if not isinstance(filter_value, dict):
        return False
    return any(key in filter_value for key in ("must", "should", "must_not"))


def _extend_filter_list(target: list, filter_value) -> None:
    if not filter_value:
        return
    if isinstance(filter_value, list):
        target.extend(filter_value)
    elif isinstance(filter_value, dict) and "bool" in filter_value and "filter" in filter_value["bool"]:
        target.extend(filter_value["bool"]["filter"])
    else:
        target.append(filter_value)


def merge_knn_and_bool_filters(
    knn_filter: Optional[Dict[str, Any]], 
    bool_query_filter: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    合并 knn.filter 和 bool.query.filter 两个过滤条件
    
    :param knn_filter: knn 配置中的 filter
    :param bool_query_filter: bool 查询中的 filter（可能是数组或 dict）
    :return: 合并后的 filter（dict 格式，适合传递给 knn_search）
    """
    # 如果只有一个 filter，直接返回
    if not knn_filter and not bool_query_filter:
        return {}
    if not knn_filter:
        return _as_bool_filter(bool_query_filter)
    if not bool_query_filter:
        return knn_filter
    if _is_standalone_bool_query(bool_query_filter):
        return bool_query_filter
    
    # 两个 filter 都存在，使用 bool.filter 连接（AND 逻辑）
    merged = {
        "bool": {
            "filter": []
        }
    }
    
    _extend_filter_list(merged["bool"]["filter"], knn_filter)
    _extend_filter_list(merged["bool"]["filter"], bool_query_filter)
    
    return merged
