from typing import Any, Dict, List, Optional, Tuple
from psycopg2 import sql
from opensearch_sdk.client.utils import normalize_identifier
from opensearch_sdk.client.search.helpers import match_column_patterns
from opensearch_sdk.client.constants import MAX_QUERY_LIMIT, MIN_QUERY_LIMIT


def process_source_filter(
    body: Dict[str, Any],
    validated_index: str,
    get_table_columns_func
) -> Tuple[Optional[List[str]], List[str]]:
    """
    处理 _source 过滤配置
    
    :param body: 搜索请求体
    :param validated_index: 索引名称
    :param get_table_columns_func: 获取表列名的函数
    :return: (select_columns, source_excludes_patterns)
        - select_columns: None表示SELECT *，否则是指定列列表
        - source_excludes_patterns: Python层排除的模式列表
    """
    select_columns = None  # None 表示 SELECT *
    source_excludes_patterns = []  # Python 层排除的模式
    
    if "_source" not in body:
        return select_columns, source_excludes_patterns
    
    source_config = body["_source"]
    
    if isinstance(source_config, dict):
        includes = source_config.get("includes", [])
        excludes = source_config.get("excludes", [])
        
        if includes:
            # includes 模式：生成优化的 SQL SELECT
            all_columns = get_table_columns_func(validated_index)
            selected = set()
            for pattern in includes:
                matched = match_column_patterns(all_columns, pattern)
                selected.update(matched)
            select_columns = list(selected)
        elif excludes:
            # excludes 模式：使用 Python 层后过滤（低效但快速实现）
            # 仍然 SELECT *，然后在 Python 层删除不需要的字段
            source_excludes_patterns = excludes
    
    elif source_config is False:
        # _source: false - 只返回 id
        select_columns = ['id']
    
    return select_columns, source_excludes_patterns


def _append_bm25_sort(sort_clauses: List[sql.Composable], bm25_field: Optional[str], params: List[Any]) -> None:
    if not bm25_field or not params:
        return

    order_by_clause = sql.SQL(" ORDER BY {} <&> %s::text DESC").format(
        sql.Identifier(bm25_field)
    )
    sort_clauses.append(order_by_clause)
    params.append(params[0])


def _sort_direction(order_spec: Any) -> str:
    if isinstance(order_spec, str):
        direction = order_spec.upper()
    elif isinstance(order_spec, dict):
        direction = order_spec.get("order", "asc").upper()
    else:
        direction = "ASC"

    return "ASC" if direction in ["ASC", "ASCENDING"] else "DESC"


def _sort_clauses_from_dict(sort_item: Dict[str, Any]) -> List[sql.Composable]:
    sort_clauses = []
    for field, order_spec in sort_item.items():
        validated_field = normalize_identifier(field, "Sort field")
        sort_clauses.append(sql.SQL("{} {}").format(
            sql.Identifier(validated_field),
            sql.SQL(_sort_direction(order_spec))
        ))
    return sort_clauses


def _sort_clauses_from_item(sort_item: Any) -> List[sql.Composable]:
    if isinstance(sort_item, str):
        validated_field = normalize_identifier(sort_item, "Sort field")
        return [sql.SQL("{} ASC").format(sql.Identifier(validated_field))]
    if isinstance(sort_item, dict):
        return _sort_clauses_from_dict(sort_item)
    return []


def build_sort_clause(
    body: Dict[str, Any],
    bm25_field: Optional[str],
    params: List[Any]
) -> Tuple[List[sql.Composable], List[Any]]:
    """
    构建 ORDER BY 子句
    
    :param body: 搜索请求体
    :param bm25_field: BM25字段名（如果有）
    :param params: 当前参数列表
    :return: (sort_clauses, updated_params)
    """
    sort_clauses = []
    
    if "sort" not in body:
        # 如果使用了 BM25 且没有自定义排序，添加 BM25 排序
        _append_bm25_sort(sort_clauses, bm25_field, params)
        return sort_clauses, params
    
    # 处理自定义排序
    for sort_item in body["sort"]:
        sort_clauses.extend(_sort_clauses_from_item(sort_item))
    
    return sort_clauses, params


def build_limit_clause(body: Dict[str, Any]) -> Optional[sql.Composable]:
    """
    构建 LIMIT/OFFSET 子句
    
    :param body: 搜索请求体
    :return: limit 子句或 None
    """
    if "size" not in body and "from" not in body:
        return None
    
    offset = body.get("from", 0)
    limit = body.get("size", 10)
    
    if not isinstance(limit, int) or limit < MIN_QUERY_LIMIT or limit > MAX_QUERY_LIMIT:
        limit = 10
    if not isinstance(offset, int) or offset < 0:
        offset = 0
    
    return sql.SQL(" LIMIT {} OFFSET {}").format(
        sql.Literal(limit), 
        sql.Literal(offset)
    )


def build_select_clause(
    select_columns: Optional[List[str]],
    validated_index: str,
    bm25_field: Optional[str]
) -> Tuple[sql.Composable, bool]:
    """
    构建 SELECT 子句
    
    :param select_columns: 选择的列（None表示SELECT *）
    :param validated_index: 索引名称
    :param bm25_field: BM25字段名（如果有）
    :return: (SELECT 子句, needs_bm25_param) 元组
             - SELECT 子句: SQL 查询片段
             - needs_bm25_param: 是否需要添加 BM25 参数（True/False）
    """
    if select_columns is None or select_columns == []:
        # SELECT *
        if bm25_field:
            # 当有 BM25 字段时，需要添加 BM25 评分列
            return sql.SQL("SELECT *, ({} <&> %s::text) AS _bm25_score FROM {}").format(
                sql.Identifier(bm25_field),
                sql.Identifier(validated_index)
            ), True
        else:
            return sql.SQL("SELECT * FROM {}").format(sql.Identifier(validated_index)), False
    else:
        # SELECT col1, col2, col3 FROM ...
        # 确保 id 字段存在（用于构建文档 ID）
        if 'id' not in select_columns:
            select_columns.append('id')
        
        # 如果有 BM25 字段，添加 BM25 评分列
        if bm25_field:
            columns_sql = sql.SQL(", ").join(sql.Identifier(col) for col in select_columns)
            bm25_score_sql = sql.SQL("({} <&> %s::text) AS _bm25_score").format(
                sql.Identifier(bm25_field)
            )
            final_columns = sql.SQL(", ").join([columns_sql, bm25_score_sql])
            return sql.SQL("SELECT {} FROM {}").format(
                final_columns,
                sql.Identifier(validated_index)
            ), True
        else:
            return sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(", ").join(sql.Identifier(col) for col in select_columns),
                sql.Identifier(validated_index)
            ), False
