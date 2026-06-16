from typing import Any, Dict, List, Optional, Tuple
from psycopg2 import sql

from opensearch_sdk.client.utils import normalize_identifier
from opensearch_sdk.client.query_builder import QueryBuilder


class QueryExecutor:
    """
    通用查询执行器
    
    提供查询条件构建、SQL生成等共用功能
    被 search 和 delete_by_query 等方法复用
    """

    @staticmethod
    def _extend_params(params: List, param) -> None:
        if isinstance(param, list):
            params.extend(param)
        elif isinstance(param, tuple):
            params.extend(list(param))
        else:
            params.append(param)

    @staticmethod
    def _append_simple_query(query: Dict[str, Any], where_conditions: List, params: List):
        for query_type in ["match", "match_phrase", "term", "terms", "range", "exists"]:
            if query_type not in query:
                continue
            cond, param, marks = QueryBuilder.process_query_item({query_type: query[query_type]})
            if not cond:
                return None
            where_conditions.append(cond)
            QueryExecutor._extend_params(params, param)
            return marks
        return None
    
    @staticmethod
    def build_where_clause(query: Dict[str, Any]) -> Tuple[List, List, Optional[Dict]]:
        """
        根据查询体构建 WHERE 子句
        
        :param query: 查询条件（body中的query部分）
        :return: (where_conditions, params, post_filter_marks) 元组
                 - where_conditions: WHERE 条件列表
                 - params: SQL 参数列表
                 - post_filter_marks: 后过滤标记（用于 match_phrase 等）
        """
        where_conditions = []
        params = []
        post_filter_marks = None
        
        if not query:
            return where_conditions, params, post_filter_marks
        
        if "bool" in query:
            bool_query = query["bool"]
            where_conds, params, post_filter_marks = QueryBuilder.process_bool_clause(bool_query, depth=0)
            where_conditions.extend(where_conds)
        else:
            marks = QueryExecutor._append_simple_query(query, where_conditions, params)
            if marks:
                post_filter_marks = []
                post_filter_marks.extend(marks)
        
        return where_conditions, params, post_filter_marks
    
    @staticmethod
    def detect_bm25_field(where_conditions: List) -> Optional[str]:
        """
        检测 WHERE 条件中是否使用了 BM25 (<&>) 操作符
        
        :param where_conditions: WHERE 条件列表
        :return: BM25 字段名，如果未检测到返回 None
        """
        import re
        
        for cond in where_conditions:
            try:
                cond_str = str(cond)
                if '<&>' not in cond_str:
                    continue
                match = re.search(r'Identifier\([\'"](\w+)[\'"]', cond_str)
                if match:
                    return match.group(1)
            except Exception:
                pass
        
        return None
    
    @staticmethod
    def check_problematic_or_query(body: Dict[str, Any]) -> bool:
        """
        检查是否需要使用 Python 层过滤
        
        只有当 should 中包含 match/match_phrase 等全文检索操作符时才需要
        term/terms/range 等操作符可以直接通过 SQL 执行
        
        特殊情况：minimum_should_match > 1 时，SQL 的 OR 语义无法满足要求，必须用 Python 过滤
        
        :param body: 完整的查询体
        :return: 是否存在问题查询
        """
        if "query" not in body or "bool" not in body["query"]:
            return False
        
        bool_query = body["query"]["bool"]
        
        if "should" not in bool_query or "minimum_should_match" not in bool_query:
            return False
        
        minimum_should_match = bool_query.get("minimum_should_match", 1)
        
        # 如果 minimum_should_match > 1，SQL 的 OR 语义无法满足，必须用 Python 过滤
        if minimum_should_match > 1:
            return True
        
        # minimum_should_match = 1 时，检查 should 中是否包含需要 Python 过滤的操作符
        should_clauses = bool_query["should"]
        for clause in should_clauses:
            # match/match_phrase 需要 Python 过滤（BM25 全文检索）
            if "match" in clause or "match_phrase" in clause:
                return True
            # term/terms/range/exists 等可以直接用 SQL
            if any(op in clause for op in ["term", "terms", "range", "exists"]):
                continue
        
        # 如果所有 should 都是 term/terms 等，且 minimum_should_match = 1，可以走 SQL
        return False
    
    @staticmethod
    def validate_and_normalize_index(index: str) -> str:
        """
        验证并标准化索引名称
        
        :param index: 原始索引名称
        :return: 标准化后的索引名称
        """
        return normalize_identifier(index, "Index name")
    
    @staticmethod
    def build_delete_sql(index: str, where_conditions: List) -> sql.Composable:
        """
        构建 DELETE SQL 语句
        
        :param index: 索引名称（已验证）
        :param where_conditions: WHERE 条件列表
        :return: SQL 语句对象
        """
        if not where_conditions:
            raise Exception("No valid delete conditions found")
        
        where_clause = sql.SQL(" AND ").join(where_conditions)
        return sql.SQL("DELETE FROM {} WHERE {}").format(
            sql.Identifier(index),
            where_clause
        )
    
    @staticmethod
    def build_select_sql(index: str, where_conditions: List, 
                         select_columns: Optional[List[str]] = None,
                         order_by: Optional[str] = None,
                         limit: Optional[int] = None) -> sql.Composable:
        """
        构建 SELECT SQL 语句
        
        :param index: 索引名称（已验证）
        :param where_conditions: WHERE 条件列表
        :param select_columns: 选择的列（None 表示 SELECT *）
        :param order_by: ORDER BY 子句
        :param limit: LIMIT 数量
        :return: SQL 语句对象
        """
        # SELECT 子句
        if select_columns:
            columns = sql.SQL(", ").join([sql.Identifier(col) for col in select_columns])
            select_clause = sql.SQL("SELECT {}").format(columns)
        else:
            select_clause = sql.SQL("SELECT *")
        
        # FROM 子句
        from_clause = sql.SQL(" FROM {}").format(sql.Identifier(index))
        
        # 组合基础 SQL
        sql_parts = [select_clause, from_clause]
        
        # WHERE 子句
        if where_conditions:
            where_clause = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_conditions)
            sql_parts.append(where_clause)
        
        # ORDER BY 子句
        if order_by:
            sql_parts.append(sql.SQL(" ORDER BY {}").format(sql.SQL(order_by)))
        
        # LIMIT 子句
        if limit is not None:
            sql_parts.append(sql.SQL(" LIMIT %s"))
        
        return sql.SQL("").join(sql_parts)
