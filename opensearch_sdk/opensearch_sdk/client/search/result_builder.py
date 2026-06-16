import json
from typing import Any, Dict, List, Optional
from opensearch_sdk.client.search.helpers import reconstruct_nested_structure, match_column_patterns


def build_search_hits(
    rows: List[tuple],
    column_names: List[str],
    validated_index: str,
    source_excludes_patterns: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    从数据库查询结果构建搜索 hits

    :param rows: 数据库查询结果行
    :param column_names: 列名列表
    :param validated_index: 索引名称
    :param source_excludes_patterns: 需要排除的字段模式
    :return: hits 列表
    """
    hits = []

    for row in rows:
        source = dict(zip(column_names, row))

        # 提取 BM25 分数（如果存在）
        bm25_score = source.pop('_bm25_score', None)

        # 解析 JSON 字段
        _parse_json_fields(source)

        # 还原 nested 结构
        source = reconstruct_nested_structure(source)

        # 提取文档 ID
        doc_id = source.get('id', 'unknown')
        if 'id' in source:
            del source['id']

        # 处理 excludes（Python 层过滤）
        if source_excludes_patterns:
            _apply_source_excludes(source, source_excludes_patterns)

        # 使用实际的 BM25 分数，如果没有则默认为 1.0
        score = float(bm25_score) if bm25_score is not None else 1.0

        hits.append({
            "_index": validated_index,
            "_id": doc_id,
            "_score": score,
            "_source": source
        })

    return hits


def _parse_json_fields(source: Dict[str, Any]) -> None:
    """
    尝试解析 JSON 字符串字段

    :param source: 源数据字典（原地修改）
    """
    for key, value in source.items():
        if isinstance(value, str) and value.startswith(('{', '[')):
            try:
                source[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass


def _apply_source_excludes(source: Dict[str, Any], exclude_patterns: List[str]) -> None:
    """
    应用 source excludes 过滤

    :param source: 源数据字典（原地修改）
    :param exclude_patterns: 排除模式列表
    """
    all_columns_to_exclude = set()
    for pattern in exclude_patterns:
        matched = match_column_patterns(list(source.keys()), pattern)
        all_columns_to_exclude.update(matched)

    # 从 source 中删除匹配的列
    for col in all_columns_to_exclude:
        if col in source:
            del source[col]


def format_search_response(hits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    格式化搜索响应为 OpenSearch 兼容格式

    :param hits: hits 列表
    :return: OpenSearch 格式的响应
    """
    return {
        "hits": {
            "total": {
                "value": len(hits),
                "relation": "eq"
            },
            "hits": hits
        }
    }


def build_retriever_hits(results: List[Any], validated_index: str) -> List[Dict[str, Any]]:
    """
    将 retriever 结果转换为 OpenSearch hits 格式

    :param results: retriever 返回的结果列表
    :param validated_index: 索引名称
    :return: hits 列表
    """
    hits = []
    for result in results:
        source = reconstruct_nested_structure(dict(result.data))
        doc_id = source.pop('id', 'unknown')
        hits.append({
            "_index": validated_index,
            "_id": str(doc_id),
            "_score": result.score,
            "_source": source
        })
    return hits


def build_knn_hits(
    rows: List[tuple],
    column_names: List[str],
    validated_index: str,
    similarity: str,
    source_excludes_patterns: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    从 kNN 查询结果构建 hits（带 score 计算）

    :param rows: 数据库查询结果行
    :param column_names: 列名列表
    :param validated_index: 索引名称
    :param similarity: 相似度算法
    :param source_excludes_patterns: 需要排除的字段模式
    :return: hits 列表
    """
    hits = []
    num_columns = len(column_names)

    for idx, row in enumerate(rows):
        source = dict(zip(column_names, row))

        # 解析 JSON 字段
        _parse_json_fields(source)

        # 还原 nested 结构
        source = reconstruct_nested_structure(source)

        # 提取文档 ID
        doc_id = source.get('id', 'unknown')
        if 'id' in source:
            del source['id']

        # 处理 excludes（Python 层过滤）
        if source_excludes_patterns:
            _apply_source_excludes(source, source_excludes_patterns)

        # 计算 score
        distance = _extract_distance(row, source, num_columns, idx)
        score = _calculate_score(distance, similarity)

        hits.append({
            "_index": validated_index,
            "_id": doc_id,
            "_score": score,
            "_source": source
        })

    return hits


def _extract_distance(row: tuple, source: Dict[str, Any], num_columns: int, idx: int) -> float:
    """
    从查询结果中提取 distance 值

    :param row: 数据行
    :param source: 源数据字典
    :param num_columns: 列数
    :param idx: 行索引
    :return: distance 值
    """
    if len(row) > num_columns:
        return float(row[num_columns])  # distance 列的值
    elif 'distance' in source and source['distance'] is not None:
        return float(source['distance'])
    else:
        return idx * 0.1  # fallback


def _calculate_score(distance: float, similarity: str) -> float:
    """
    根据相似度算法计算 score

    :param distance: 距离值
    :param similarity: 相似度算法
    :return: score 值
    """
    if similarity == 'cosine':
        return 1.0 - distance  # cosine 距离转相似度 (0-1 范围)
    elif similarity == 'l2_norm':
        return 1.0 / (1.0 + distance)  # L2 距离转相似度
    elif similarity == 'dot_product':
        return 1.0 / (1.0 - distance) if distance < 1 else 1.0 / (1.0 + abs(distance))
    else:
        return 1.0 / (1.0 + distance)  # 默认 fallback
