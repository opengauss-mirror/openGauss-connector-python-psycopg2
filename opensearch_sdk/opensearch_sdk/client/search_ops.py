from typing import Any, Dict, List, Optional, Tuple

from psycopg2 import sql
from psycopg2.retrievers import FullTextRetriever, VectorRetriever

from opensearch_sdk.client.constants import MAX_KNN_TOP_K, MIN_KNN_TOP_K
from opensearch_sdk.client.doc_utils.helpers import with_search_trace
import opensearch_sdk.client.search.convenience as search_convenience
from opensearch_sdk.client.search.knn_handler import parse_knn_config, merge_knn_and_bool_filters
import opensearch_sdk.client.search.query_builder_ext as search_query_builder
from opensearch_sdk.client.search.result_builder import (
    build_search_hits,
    format_search_response,
    build_knn_hits,
    build_retriever_hits,
)

from opensearch_sdk.client.utils import normalize_identifier
from opensearch_sdk.client.query_builder import QueryBuilder
from opensearch_sdk.client.indices import ENABLE_PYTHON_VALIDATION
from opensearch_sdk.client.post_validator import PostValidator


_NO_SEARCH_RESULT = object()


class SearchOpsMixin:
    """
    搜索操作 Mixin，提供全文搜索和向量搜索功能
    """
    
    def _get_table_columns(self, index: str) -> List[str]:
        """
        获取表的所有列名（从 information_schema）
        
        :param index: 索引/表名称
        :return: 列名列表
        """
        # 动态获取当前 schema
        current_schema = self.connection.get_current_schema()
        
        sql_query = sql.SQL("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND table_schema = %s
            ORDER BY ordinal_position;
        """)
        
        # [OK] 使用新的连接管理模式
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql_query, (index, current_schema))
                return [row[0] for row in cursor.fetchall()]
            finally:
                cursor.close()
    
    @staticmethod
    def _merge_knn_and_bool_filters(
        knn_filter: Optional[Dict[str, Any]],
        bool_query_filter: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """合并过滤器（代理方法）"""
        return merge_knn_and_bool_filters(knn_filter, bool_query_filter)

    def _record_search_trace(self, cursor, final_sql, params: List[Any], validated_index: str) -> None:
        """记录 search 查询的 SQL 追踪信息。"""
        if not (hasattr(self, 'sql_tracer') and self.sql_tracer and self.sql_tracer.enabled):
            return

        session = self.sql_tracer._get_current_session()
        if not session:
            return

        from opensearch_sdk.client.sql_tracer.record import SQLTraceRecord
        import time

        record = SQLTraceRecord(
            sql=str(final_sql),
            params=tuple(params) if params else None,
            start_time=time.time(),
            context=f"search_query_{validated_index}"
        )
        record.end_time = time.time()
        record.duration_ms = 0
        if hasattr(cursor, 'rowcount'):
            record.result_count = cursor.rowcount if cursor.rowcount >= 0 else 0
        session.add_record(record)

    def _execute_search_sql(
        self,
        final_sql,
        params: List[Any],
        validated_index: str,
        source_excludes_patterns: Optional[List[str]] = None,
        post_filter_marks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """执行 search SQL 并构建 hits。"""
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(final_sql, params)
                self._record_search_trace(cursor, final_sql, params, validated_index)

                rows = cursor.fetchall()
                column_names = [desc[0] for desc in cursor.description] if cursor.description else []
                hits = build_search_hits(rows, column_names, validated_index, source_excludes_patterns)
                if post_filter_marks:
                    hits = PostValidator.validate(hits, post_filter_marks)
                return hits
            finally:
                cursor.close()

    @staticmethod
    def _build_bm25_custom_sort_sql(
        body: Dict[str, Any],
        select_columns,
        validated_index: str,
        where_clause,
        bm25_field: str,
        params: List[Any]
    ) -> Tuple[Any, List[Any]]:
        """构建 BM25 筛选后再按用户排序的子查询。"""
        sql_parts = [sql.SQL("SELECT * FROM (")]
        inner_select, needs_bm25_param = search_query_builder.build_select_clause(
            select_columns,
            validated_index,
            bm25_field
        )
        sql_parts.append(inner_select)
        if needs_bm25_param and params:
            params.insert(0, params[0])

        sql_parts.append(where_clause)
        sql_parts.append(sql.SQL(" ORDER BY {} <&> %s::text DESC").format(sql.Identifier(bm25_field)))
        params.append(params[0])

        page_size = body.get("size", 10)
        sql_parts.append(sql.SQL(" LIMIT {}").format(sql.Literal(max(page_size * 10, 100))))
        sql_parts.append(sql.SQL(") AS subquery"))

        sort_clauses, params = search_query_builder.build_sort_clause(body, None, params)
        if sort_clauses:
            sql_parts.append(sql.SQL(" ORDER BY ") + sql.SQL(", ").join(sort_clauses))

        limit_clause = search_query_builder.build_limit_clause(body)
        if limit_clause:
            sql_parts.append(limit_clause)

        return sql.SQL("").join(sql_parts), params

    @staticmethod
    def _build_standard_filtered_sql(
        body: Dict[str, Any],
        select_columns,
        validated_index: str,
        where_clause,
        bm25_field: Optional[str],
        params: List[Any]
    ) -> Tuple[Any, List[Any]]:
        """构建普通带 WHERE 的 search SQL。"""
        sql_parts = [where_clause]
        if bm25_field:
            order_by_clause = sql.SQL(" ORDER BY {} <&> %s::text DESC").format(
                sql.Identifier(bm25_field)
            )
            sql_parts.append(order_by_clause)
            params.append(params[0])

        sort_clauses, params = search_query_builder.build_sort_clause(body, None, params)
        has_order_by = any('ORDER BY' in str(part).upper() for part in sql_parts)
        if sort_clauses and not has_order_by:
            sql_parts.append(sql.SQL(" ORDER BY ") + sql.SQL(", ").join(sort_clauses))

        limit_clause = search_query_builder.build_limit_clause(body)
        if limit_clause:
            sql_parts.append(limit_clause)

        select_sql, _ = search_query_builder.build_select_clause(select_columns, validated_index, bm25_field)
        sql_parts.insert(0, select_sql)
        if bm25_field:
            params.insert(0, params[0])

        return sql.SQL("").join(sql_parts), params

    def _execute_filtered_search(
        self,
        body: Dict[str, Any],
        select_columns,
        validated_index: str,
        where_conditions: List[Any],
        params: List[Any],
        post_filter_marks,
        source_excludes_patterns: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """执行带 WHERE 条件的 search 查询。"""
        from opensearch_sdk.client.doc_utils.query_executor import QueryExecutor

        where_clause = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_conditions)
        bm25_field = QueryExecutor.detect_bm25_field(where_conditions)
        if bm25_field and "sort" in body:
            final_sql, params = self._build_bm25_custom_sort_sql(
                body, select_columns, validated_index, where_clause, bm25_field, params
            )
            marks_to_apply = None
        else:
            final_sql, params = self._build_standard_filtered_sql(
                body, select_columns, validated_index, where_clause, bm25_field, params
            )
            marks_to_apply = post_filter_marks

        return self._execute_search_sql(
            final_sql,
            params,
            validated_index,
            source_excludes_patterns,
            marks_to_apply
        )

    def _execute_unfiltered_search(
        self,
        body: Dict[str, Any],
        select_columns,
        validated_index: str,
        params: List[Any],
        source_excludes_patterns: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """执行无 WHERE 条件的 search 查询。"""
        final_sql, _ = search_query_builder.build_select_clause(select_columns, validated_index, None)
        sql_parts = [final_sql]

        sort_clauses, params = search_query_builder.build_sort_clause(body, None, params)
        if sort_clauses:
            sql_parts.append(sql.SQL(" ORDER BY ") + sql.SQL(", ").join(sort_clauses))

        limit_clause = search_query_builder.build_limit_clause(body)
        if limit_clause:
            sql_parts.append(limit_clause)

        return self._execute_search_sql(
            sql.SQL("").join(sql_parts),
            params,
            validated_index,
            source_excludes_patterns
        )

    @staticmethod
    def _prepare_retriever_filter(
        filter_query: Optional[Dict[str, Any]]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """将 OpenSearch filter 转成 retriever 使用的条件和参数。"""
        if not filter_query:
            return None, None

        filter_condition, filter_params_list = QueryBuilder.process_filter_for_knn(filter_query)
        if not filter_condition:
            return filter_condition, None

        filter_params = {f"param_{i}": value for i, value in enumerate(filter_params_list)}
        return filter_condition, filter_params

    @staticmethod
    def _validate_knn_search_inputs(
        query_vector: List[float],
        k: int,
        similarity: str,
        ef_search: Optional[int]
    ) -> None:
        """校验 kNN 查询参数。"""
        if not isinstance(query_vector, list) or len(query_vector) == 0:
            raise ValueError("query_vector must be a non-empty list")

        if not isinstance(k, int) or k < MIN_KNN_TOP_K or k > MAX_KNN_TOP_K:
            raise ValueError(f"k must be a positive integer between {MIN_KNN_TOP_K} and {MAX_KNN_TOP_K}")

        if not ENABLE_PYTHON_VALIDATION:
            return

        valid_similarities = ['cosine', 'l2_norm', 'dot_product']
        if similarity not in valid_similarities:
            raise ValueError(
                f"Invalid similarity '{similarity}'. "
                f"Supported values: {', '.join(valid_similarities)}"
            )

        if ef_search is not None and (not isinstance(ef_search, int) or ef_search <= 0):
            raise ValueError("ef_search must be a positive integer")

    @staticmethod
    def _knn_operator(similarity: str) -> str:
        """根据 similarity 选择向量操作符。"""
        operator_map = {
            'cosine': '<=>',
            'l2_norm': '<->',
            'dot_product': '<#>'
        }
        operator = operator_map.get(similarity)
        if operator is None:
            raise ValueError(
                f"Invalid similarity '{similarity}'. "
                f"Supported values: {', '.join(operator_map.keys())}"
            )
        return operator

    def _build_knn_sql(
        self,
        validated_index: str,
        validated_field: str,
        query_vector: List[float],
        k: int,
        filter_query: Optional[Dict[str, Any]],
        similarity: str
    ) -> Tuple[Any, List[Any]]:
        """构建 kNN 查询 SQL 和参数。"""
        operator = self._knn_operator(similarity)
        vector_param = f"[{','.join(str(value) for value in query_vector)}]"
        sql_parts = [
            sql.SQL("SELECT *, {} {} %s::vector AS distance FROM {}").format(
                sql.Identifier(validated_field),
                sql.SQL(operator),
                sql.Identifier(validated_index)
            )
        ]
        params = [vector_param]

        if filter_query:
            where_clause_str, filter_params = QueryBuilder.process_filter_for_knn(filter_query)
            if where_clause_str:
                sql_parts.append(sql.SQL(" WHERE ") + sql.SQL(where_clause_str))
                params.extend(filter_params)

        order_by_clause = sql.SQL(" ORDER BY {} {} %s::vector ASC").format(
            sql.Identifier(validated_field),
            sql.SQL(operator)
        )
        sql_parts.append(order_by_clause)
        params.append(vector_param)
        sql_parts.append(sql.SQL(" LIMIT {}").format(sql.Literal(k)))
        return sql.SQL("").join(sql_parts), params

    def _execute_knn_sql(
        self,
        final_sql,
        params: List[Any],
        ef_search: Optional[int],
        validated_index: str,
        similarity: str,
        source_excludes_patterns: Optional[List[str]]
    ) -> Dict[str, Any]:
        """执行 kNN SQL 并返回 OpenSearch 格式响应。"""
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                if ef_search is not None:
                    set_sql = f"SET hnsw_ef_search = {ef_search}; "
                    cursor.execute(set_sql + final_sql.as_string(conn), params)
                else:
                    cursor.execute(final_sql, params)

                rows = cursor.fetchall()
                column_names = [desc[0] for desc in cursor.description] if cursor.description else []
                hits = build_knn_hits(rows, column_names, validated_index, similarity, source_excludes_patterns)
                return format_search_response(hits)
            finally:
                cursor.close()
    
    def _handle_knn_query(
        self,
        index: str,
        knn_config: Dict[str, Any],
        source_excludes_patterns: Optional[List[str]] = None,
        size: Optional[int] = None
    ) -> Any:
        """处理 kNN 查询（代理方法）
        
        :param index: 索引名称
        :param knn_config: kNN 配置
        :param source_excludes_patterns: 需要排除的字段模式
        :param size: 最终返回的结果数量（如果指定，会覆盖 k 值）
        """
        field, query_vector, k, num_candidates, filter_query, similarity = parse_knn_config(knn_config)
        
        # OpenSearch 兼容：如果指定了 size，使用 size 而不是 k
        # size <= k 时，返回 size 条结果
        # size > k 或未指定时，返回 k 条结果
        if size is not None and isinstance(size, int) and size > 0:
            effective_k = min(k, size)
        else:
            effective_k = k
        
        return self.knn_search(
            index=index,
            field=field,
            query_vector=query_vector,
            k=effective_k,
            num_candidates=num_candidates,
            filter_query=filter_query,
            similarity=similarity,
            source_excludes_patterns=source_excludes_patterns
        )

    @staticmethod
    def _extract_knn_filter(knn_config: Dict[str, Any]) -> Tuple[Optional[str], Any, Optional[Dict[str, Any]]]:
        """提取 kNN 字段配置和内置 filter。"""
        field_name = None
        field_config = None
        knn_filter = None

        if isinstance(knn_config, dict):
            field_name = list(knn_config.keys())[0]
            field_config = knn_config[field_name]
            if isinstance(field_config, dict):
                knn_filter = field_config.get("filter")

        return field_name, field_config, knn_filter

    @staticmethod
    def _extract_bool_query_filter(bool_filter: Dict[str, Any]):
        """提取 bool 查询中的 filter/must/should/must_not。"""
        if not isinstance(bool_filter, dict):
            return None
        if "filter" in bool_filter:
            return bool_filter["filter"]
        if "must" in bool_filter or "should" in bool_filter or "must_not" in bool_filter:
            return bool_filter
        return None

    def _handle_mixed_knn_bool_query(
        self,
        validated_index: str,
        body: Dict[str, Any],
        query: Dict[str, Any],
        source_excludes_patterns: Optional[List[str]]
    ) -> Any:
        """处理 query.knn + query.bool 混合格式。"""
        knn_config = query["knn"]
        field_name, field_config, knn_filter = self._extract_knn_filter(knn_config)
        bool_query_filter = self._extract_bool_query_filter(query["bool"])
        merged_filter = self._merge_knn_and_bool_filters(knn_filter, bool_query_filter)

        if field_name and field_config:
            new_field_config = field_config.copy() if isinstance(field_config, dict) else field_config
            if isinstance(new_field_config, dict):
                new_field_config["filter"] = merged_filter
            knn_config = {field_name: new_field_config}

        return self._handle_knn_query(
            validated_index,
            knn_config,
            source_excludes_patterns,
            body.get("size")
        )

    @staticmethod
    def _build_bool_must_knn_body(body: Dict[str, Any], query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将 bool.must 中的 kNN 条件转换为混合查询格式。"""
        if "bool" not in query or "knn" in query:
            return None

        bool_query = query["bool"]
        must_items = bool_query.get("must", [])
        if isinstance(must_items, dict):
            must_items = [must_items]

        knn_in_must = None
        other_conditions = []
        for item in must_items:
            if "knn" in item:
                knn_in_must = item["knn"]
            else:
                other_conditions.append(item)

        if not knn_in_must:
            return None

        new_query = {"knn": knn_in_must, "bool": {}}
        if other_conditions:
            new_query["bool"]["filter"] = other_conditions
        for key in ["should", "must_not", "filter"]:
            if key in bool_query:
                new_query["bool"][key] = bool_query[key]

        new_body = {"query": new_query}
        for key, value in body.items():
            if key != "query":
                new_body[key] = value
        return new_body

    def _handle_knn_search_variants(
        self,
        index: str,
        validated_index: str,
        body: Dict[str, Any],
        source_excludes_patterns: Optional[List[str]]
    ) -> Any:
        """尝试处理 search 请求中的各种 kNN 表达形式。"""
        if "knn" in body:
            return self._handle_knn_query(
                validated_index,
                body["knn"],
                source_excludes_patterns,
                body.get("size")
            )

        query = body.get("query")
        if not isinstance(query, dict):
            return _NO_SEARCH_RESULT

        if "knn" in query and "bool" in query:
            return self._handle_mixed_knn_bool_query(
                validated_index,
                body,
                query,
                source_excludes_patterns
            )
        if "knn" in query:
            return self._handle_knn_query(
                validated_index,
                query["knn"],
                source_excludes_patterns,
                body.get("size")
            )

        converted_body = self._build_bool_must_knn_body(body, query)
        if converted_body is not None:
            return self._search_impl(index, converted_body)
        return _NO_SEARCH_RESULT

    def _execute_query_body_search(
        self,
        body: Dict[str, Any],
        select_columns,
        validated_index: str,
        source_excludes_patterns: Optional[List[str]]
    ) -> Dict[str, Any]:
        """执行普通 query 搜索。"""
        from opensearch_sdk.client.doc_utils.query_executor import QueryExecutor

        query_part = body.get("query", {})
        where_conditions, params, post_filter_marks = QueryExecutor.build_where_clause(query_part)

        if where_conditions:
            hits = self._execute_filtered_search(
                body,
                select_columns,
                validated_index,
                where_conditions,
                params,
                post_filter_marks,
                source_excludes_patterns
            )
        else:
            hits = self._execute_unfiltered_search(
                body,
                select_columns,
                validated_index,
                params,
                source_excludes_patterns
            )

        return format_search_response(hits)
    
    def search(self, index: str, body: Dict[str, Any]) -> Any:
        """
        执行通用搜索查询（增强版 - 支持 knn 查询和混合格式）
        
        :param index: 索引名称
        :arg body: 搜索请求体，支持：
            - {"knn": {...}}  # kNN 向量搜索
            - {"query": {...}}  # 全文搜索
            - {"query": {"knn": {...}, "bool": {...}}}  # 混合格式
            - 两者组合  # 混合搜索
        :return: 搜索结果
        """
        return self._search_impl(index, body)
    
    @with_search_trace("search", query_body='body')
    def _search_impl(self, index: str, body: Dict[str, Any]) -> Any:
        """
        Search 方法的实际实现（原始逻辑）
        
        :param index: 索引名称
        :param body: 搜索请求体
        :return: 搜索结果
        """
        try:
            validated_index = normalize_identifier(index, "Index name")
            query_part = body.get("query", {})
            if "terms" in query_part and len(query_part) == 1:
                return self._handle_terms_with_union(validated_index, body, query_part["terms"])
            
            select_columns, source_excludes_patterns = search_query_builder.process_source_filter(
                body, validated_index, self._get_table_columns
            )

            knn_result = self._handle_knn_search_variants(
                index,
                validated_index,
                body,
                source_excludes_patterns
            )
            if knn_result is not _NO_SEARCH_RESULT:
                return knn_result

            if "query" in body:
                return self._execute_query_body_search(
                    body,
                    select_columns,
                    validated_index,
                    source_excludes_patterns
                )
                
        except Exception as e:
            raise Exception(f"##OS## - Search Error | index={index} | error: {str(e)}")
    
    @with_search_trace("knn_search", query_vector='query_vector', k='k', similarity='similarity')
    def knn_search(
        self,
        index: str,
        field: str,
        query_vector: List[float],
        k: int = 10,
        num_candidates: int = None,
        filter_query: Dict[str, Any] = None,
        similarity: str = 'cosine',
        ef_search: int = None,
        source_excludes_patterns: Optional[List[str]] = None
    ) -> Any:
        """
        执行 kNN 向量相似度搜索
        
        Opensearch 向量操作符说明：
        - <-> : L2 距离（欧氏距离），返回值越小越相似
        - <=> : 余弦相似度，返回值越小越相似 (0 表示完全相同)
        - <#> : 负内积（点积），返回值越大越相似（需要 DESC 排序）
        
        :param index: 索引名称
        :param field: 向量字段名
        :param query_vector: 查询向量（列表格式）
        :param k: 返回结果数量
        :param num_candidates: 候选集大小
        :param filter_query: 过滤条件
        :param similarity: 相似度算法，可选 'cosine', 'l2_norm', 'dot_product'
        :param ef_search: 查询时的搜索深度参数
        :param source_excludes_patterns: 需要排除的字段模式
        :return: 搜索结果
        """
        return self._knn_search_impl(
            index=index,
            field=field,
            query_vector=query_vector,
            k=k,
            num_candidates=num_candidates,
            filter_query=filter_query,
            similarity=similarity,
            ef_search=ef_search,
            source_excludes_patterns=source_excludes_patterns
        )
    
    def _knn_search_impl(
        self, index: str, field: str, query_vector: List[float], k: int = 10, *,
        num_candidates: Optional[int] = None,
        filter_query: Optional[Dict[str, Any]] = None,
        similarity: str = 'cosine',
        ef_search: Optional[int] = None,
        source_excludes_patterns: Optional[List[str]] = None
    ) -> Any:
        """
        knn_search 方法的实际实现（原始逻辑）
        
        :param index: 索引名称
        :param field: 向量字段名
        :param query_vector: 查询向量
        :param k: 返回结果数量
        :param num_candidates: 候选集大小
        :param filter_query: 过滤条件
        :param similarity: 相似度算法
        :param ef_search: 搜索深度参数
        :param source_excludes_patterns: 需要排除的字段模式
        :return: 搜索结果
        """
        try:
            validated_index = normalize_identifier(index, "Index name")
            validated_field = normalize_identifier(field, "Sort field")
            self._validate_knn_search_inputs(query_vector, k, similarity, ef_search)
            final_sql, params = self._build_knn_sql(
                validated_index,
                validated_field,
                query_vector,
                k,
                filter_query,
                similarity
            )
            return self._execute_knn_sql(
                final_sql,
                params,
                ef_search,
                validated_index,
                similarity,
                source_excludes_patterns
            )
            
        except Exception as e:
            raise Exception(f"##OS## - kNN Search Error | index={index}, field={field} | error: {str(e)}")

    def _run_retriever_search(
        self,
        retriever,
        validated_index: str,
        top_k: int,
        filter_query: Optional[Dict[str, Any]],
        output_columns: Optional[List[str]]
    ) -> Any:
        """执行 retriever 查询并统一格式化结果。"""
        filter_condition, filter_params = self._prepare_retriever_filter(filter_query)
        results = retriever.retrieve(
            client=self,
            table_name=validated_index,
            top_k=top_k,
            filter_condition=filter_condition,
            filter_params=filter_params,
            output_columns=output_columns
        )
        hits = build_retriever_hits(results, validated_index)
        return format_search_response(hits)
    
    def vector_search(
        self,
        index: str,
        query_vector: List[float],
        vector_column: str = "embedding",
        top_k: int = 10,
        metric: str = "cosine",
        filter_query: Dict[str, Any] = None,
        output_columns: List[str] = None,
        ef_search: int = None,
        probes: int = None,
        use_index: bool = True
    ) -> Any:
        """
        执行向量相似度搜索（高级 API，基于 VectorRetriever）
        
        :param index: 索引名称（表名）
        :param query_vector: 查询向量
        :param vector_column: 向量字段名
        :param top_k: 返回结果数量
        :param metric: 相似度算法
        :param filter_query: 过滤条件
        :param output_columns: 返回字段列表
        :param ef_search: HNSW 查询参数
        :param probes: IVFFlat 查询参数
        :param use_index: 是否使用索引
        :return: 搜索结果
        """
        try:
            validated_index = normalize_identifier(index, "Index name")
            # [OK] 标准化向量字段名
            validated_field = normalize_identifier(vector_column, "Vector column")
            
            if not isinstance(query_vector, list) or len(query_vector) == 0:
                raise ValueError("query_vector must be a non-empty list")
            
            if not isinstance(top_k, int) or top_k < MIN_KNN_TOP_K or top_k > MAX_KNN_TOP_K:
                raise ValueError(f"top_k must be a positive integer between {MIN_KNN_TOP_K} and {MAX_KNN_TOP_K}")
            
            retriever = VectorRetriever(
                query_vector=query_vector,
                vector_column=validated_field,
                metric=metric,
                id_column="id",
                top_k=top_k,
                filter_condition=None,
                filter_params=None,
                output_columns=output_columns,
                use_index=use_index,
                ef_search=ef_search,
                probes=probes
            )
            return self._run_retriever_search(retriever, validated_index,
                top_k, filter_query, output_columns)
            
        except Exception as e:
            raise Exception(
                f"##OS## - Vector Search Error | index={index}, "
                f"vector_column={vector_column} | error: {str(e)}"
            )
    
    def fulltext_search(
        self,
        index: str,
        query_text: str,
        text_column: str = "content",
        top_k: int = 10,
        filter_query: Dict[str, Any] = None,
        output_columns: List[str] = None,
        use_bm25_taat: bool = False,
        bm25_k1: float = None,
        bm25_b: float = None
    ) -> Any:
        """
        执行全文检索（高级 API，基于 FullTextRetriever）
        
        :param index: 索引名称
        :param query_text: 查询文本
        :param text_column: 文本字段名
        :param top_k: 返回结果数量
        :param filter_query: 过滤条件
        :param output_columns: 返回字段列表
        :param use_bm25_taat: 是否使用 TAAT 方法
        :param bm25_k1: BM25 k1 参数
        :param bm25_b: BM25 b 参数
        :return: 搜索结果
        """
        try:
            validated_index = normalize_identifier(index, "Index name")
            # [OK] 标准化文本字段名
            validated_field = normalize_identifier(text_column, "Text column")
            
            if not isinstance(query_text, str):
                raise ValueError("query_text must be a string")
            
            if not isinstance(top_k, int) or top_k < MIN_KNN_TOP_K or top_k > MAX_KNN_TOP_K:
                raise ValueError(f"top_k must be a positive integer between {MIN_KNN_TOP_K} and {MAX_KNN_TOP_K}")
            
            # 注意：BM25 参数已在索引创建时通过 SET 命令全局设置
            # 查询时直接使用用户传递的参数（如果有），否则使用数据库当前设置
            
            retriever = FullTextRetriever(
                query_text=query_text,
                text_column=validated_field,
                id_column="id",
                top_k=top_k,
                filter_condition=None,
                filter_params=None,
                output_columns=output_columns,
                use_bm25_taat=use_bm25_taat,
                bm25_k1=bm25_k1,
                bm25_b=bm25_b
            )
            return self._run_retriever_search(retriever, validated_index,
                top_k, filter_query, output_columns)
            
        except Exception as e:
            raise Exception(
                f"##OS## - Fulltext Search Error | index={index}, "
                f"text_column={text_column} | error: {str(e)}"
            )
    
    def search_by_category(self, index: str, category: str) -> Any:
        """按分类精确搜索"""
        search_body = search_convenience.create_search_by_category_body(category)
        return self.search(index, search_body)
    
    def search_by_multiple_fields(
        self, 
        index: str, 
        field_value_pairs: Dict[str, List[str]], 
        source_fields: Optional[List[str]] = None,
        size: int = 10
    ) -> Any:
        """根据多个字段值进行搜索"""
        search_body = search_convenience.create_search_by_multiple_fields_body(
            field_value_pairs,
            source_fields,
            size
        )
        return self.search(index, search_body)
    
    # 索引操作兼容层
    def create_index(self, index_name: str, mapping: Any) -> Any:
        """创建索引"""
        if self.indices.exists(index=index_name):
            return True
        
        try:
            response = self.indices.create(index=index_name, body=mapping)
            return True
        except Exception as e:
            raise Exception(f"##OS## - Create Index Error | index={str(index_name)} | error: {str(e)}")
    
    def delete_index(self, index_name: str) -> Any:
        """删除索引"""
        try:
            response = self.indices.delete(index=index_name)
            return response
        except Exception as e:
            raise Exception(f"##OS## - Delete Index Error | index={str(index_name)} | error: {str(e)}")
    
    def get_all_index_names(self) -> List[str]:
        """获取所有索引名称"""
        return self.indices.get_all_index_names()

    @staticmethod
    def _build_single_term_query(body: Dict[str, Any], field_name: str, value: Any) -> Dict[str, Any]:
        """为 terms 查询中的单个 value 构建 term 查询。"""
        single_query = {"query": {"term": {field_name: value}}}
        for key, config_value in body.items():
            if key != "query":
                single_query[key] = config_value
        return single_query

    @staticmethod
    def _append_unique_hits(all_hits: List[Dict[str, Any]], seen_ids: set, hits: List[Dict[str, Any]]) -> None:
        """追加未见过的 hits。"""
        for hit in hits:
            doc_id = hit.get("_id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                all_hits.append(hit)

    @staticmethod
    def _is_bm25_error(error: Exception) -> bool:
        error_msg = str(error)
        return "No BM25 index" in error_msg or "BM25" in error_msg

    @staticmethod
    def _format_terms_response(all_hits: List[Dict[str, Any]], body: Dict[str, Any]) -> Dict[str, Any]:
        total = len(all_hits)
        size = body.get("size", 10)
        if size is not None and size < total:
            all_hits = all_hits[:size]

        return {
            "took": 0,
            "timed_out": False,
            "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
            "hits": {
                "total": {"value": total, "relation": "eq"},
                "max_score": None,
                "hits": all_hits
            }
        }

    def _search_term_hits(self, validated_index: str, single_query: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = self._search_impl(validated_index, single_query)
        return result.get("hits", {}).get("hits", [])

    def _search_term_hits_without_bm25(
        self,
        validated_index: str,
        single_query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        from opensearch_sdk.client import query_builder

        original_build_term = query_builder.QueryBuilder.build_term_condition

        def build_term_no_bm25(field, val, use_bm25=True):
            return original_build_term(field, val, use_bm25=False)

        try:
            query_builder.QueryBuilder.build_term_condition = staticmethod(build_term_no_bm25)
            return self._search_term_hits(validated_index, single_query)
        finally:
            query_builder.QueryBuilder.build_term_condition = original_build_term

    def _collect_term_hits(
        self,
        validated_index: str,
        single_query: Dict[str, Any],
        value: Any
    ) -> List[Dict[str, Any]]:
        try:
            return self._search_term_hits(validated_index, single_query)
        except Exception as error:
            if not self._is_bm25_error(error):
                print(f"[WARNING] Term query for '{value}' failed: {error}")
                return []

        try:
            return self._search_term_hits_without_bm25(validated_index, single_query)
        except Exception as retry_error:
            print(f"[WARNING] Term query for '{value}' failed (retry): {retry_error}")
            return []
    
    def _handle_terms_with_union(self, validated_index: str, body: Dict[str, Any], terms_config: Dict[str, Any]) -> Any:
        """
        处理顶层 terms 查询，使用 UNION 方案（应用层合并）
        
        :param validated_index: 验证后的索引名
        :param body: 原始请求体
        :param terms_config: terms 配置，如 {"field": ["val1", "val2"]}
        :return: 合并后的搜索结果
        """
        field_name = list(terms_config.keys())[0]
        values = terms_config[field_name]

        if not values:
            return self._format_terms_response([], body)

        all_hits = []
        seen_ids = set()
        for value in values:
            single_query = self._build_single_term_query(body, field_name, value)
            hits = self._collect_term_hits(validated_index, single_query, value)
            self._append_unique_hits(all_hits, seen_ids, hits)

        return self._format_terms_response(all_hits, body)


__all__ = ['SearchOpsMixin']
