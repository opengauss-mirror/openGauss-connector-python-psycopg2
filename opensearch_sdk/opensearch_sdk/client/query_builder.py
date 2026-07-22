import json
from typing import Any, Optional, Dict, List, Tuple
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal

from psycopg2 import sql
from psycopg2.vector_types import quote_identifier

from opensearch_sdk.client.utils import _validate_identifier, _validate_identifiers, normalize_identifier
from opensearch_sdk.client.post_filter_mark import PostFilterMark
from opensearch_sdk.client.constants import NESTED_FIELD_SEPARATOR


class QueryBuilder:
    """
    查询构建器，用于构建各种 SQL 查询条件
    提供与 OpenSearch 兼容的查询语法转换
    """

    @staticmethod
    def _normalize_field_path(field_path: str, context: str = "Query field") -> str:
        """
        标准化查询中的字段路径（支持嵌套路径）

        将 . 和 - 替换为 _，以适配openGauss数据库命名规范

        Args:
            field_path: 字段路径（如 "user.name", "nested-field.info"）
            context: 上下文（用于警告信息）

        Returns:
            标准化后的字段路径

        Examples:
            >>> QueryBuilder._normalize_field_path("user.name")
            'user_name'
            >>> QueryBuilder._normalize_field_path("nested-field.info")
            'nested_field_info'
        """
        from opensearch_sdk.client.utils import normalize_nested_path
        return normalize_nested_path(field_path, context=context)

    @staticmethod
    def build_match_condition(field: str, value: Any, use_bm25: bool = True) -> Tuple[sql.Composable, Any]:
        """
        构建 match 查询条件

        :param field: 字段名
        :param value: 查询值
        :param use_bm25: 是否使用 BM25 操作符（默认 True，支持中文）
        :return: (SQL 条件，参数)
        """
        validated_field = normalize_identifier(field, "Query field")
        phrase = str(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

        if use_bm25:
            # [OK] 使用 BM25 的 <&> 操作符进行全文检索（支持中文）
            condition = sql.SQL("({} <&> %s::text) > 0").format(sql.Identifier(validated_field))
        else:
            # 分割为单词
            words = phrase.split()

            if len(words) == 0:
                raise ValueError("match query cannot be empty")
            elif len(words) == 1:
                # 单个词使用标准全文检索语法
                condition = sql.SQL("to_tsvector('simple', {}) @@ to_tsquery('simple', %s::text)").format(
                    sql.Identifier(validated_field)
                )
            else:
                # 多个词：使用 plainto_tsquery 自动处理分词和 AND 连接
                condition = sql.SQL("to_tsvector('simple', {}) @@ plainto_tsquery('simple', %s::text)").format(
                    sql.Identifier(validated_field)
                )

        return condition, phrase

    @staticmethod
    def build_match_phrase_condition(
        field: str,
        value: Any,
        slop: Optional[int] = None,  # 改为 slop参数（OpenSearch 标准）
        negate: bool = False,
        use_bm25: bool = True
    ) -> Tuple[sql.Composable, Any]:
        """
        构建 match_phrase查询条件（支持 slop参数）

        使用 Opensearch 全文检索能力进行短语/多词匹配。
        采用 BM25 + LIKE 双重过滤策略：
        - BM25 初筛：快速筛选包含所有词的文档
        - LIKE 过滤：初步验证短语连续性（仅严格短语）
        - Python 验证：精确验证短语连续性

        :param field: 字段名
        :param value: 查询值
        :param slop: 允许的最大间隔词数（OpenSearch 标准，None 或 0 表示严格相邻）
        :param negate: 是否为否定查询（NOT 条件）
        :param use_bm25: 是否使用 BM25 操作符（默认 True，支持中文）
        :return: (SQL 条件，参数)
        """
        validated_field = normalize_identifier(field, "Query field")
        phrase = str(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

        # 分割短语为单词
        words = phrase.split()

        if len(words) == 0:
            raise ValueError("match_phrase query cannot be empty")
        elif len(words) == 1:
            # 单个词
            if use_bm25:
                # [OK] 使用 BM25 的 <&> 操作符（支持中文）
                condition = sql.SQL("({} <&> %s::text) > 0").format(sql.Identifier(validated_field))
            else:
                # 使用标准全文检索语法
                condition = sql.SQL("to_tsvector('simple', {}) @@ to_tsquery('simple', %s::text)").format(
                    sql.Identifier(validated_field)
                )
        else:
            # 多个词
            if use_bm25:
                # [OK] 使用 BM25 的 <&> 操作符进行初筛（支持中文）
                condition = sql.SQL("({} <&> %s::text) > 0").format(sql.Identifier(validated_field))
            else:
                # 使用 plainto_tsquery 进行初筛
                condition = sql.SQL("to_tsvector('simple', {}) @@ plainto_tsquery('simple', %s::text)").format(
                    sql.Identifier(validated_field)
                )

            # 如果是严格短语（slop=None 或 0），添加 LIKE 条件进行初步过滤
            if slop is None or slop == 0:
                like_condition = sql.SQL("{} ILIKE %s").format(sql.Identifier(validated_field))
                # 组合两个条件：BM25 AND LIKE
                condition = sql.SQL("({} AND {})").format(condition, like_condition)
                # 返回时需要包含 LIKE 的参数（在 search_ops 中处理）
                return condition, (phrase, f'%{phrase}%')

        # 如果是否定查询，使用 NOT 包装条件
        if negate:
            condition = sql.SQL("NOT ({})").format(condition)

        return condition, phrase

    @staticmethod
    def build_term_condition(field: str, value: Any, use_bm25: bool = True) -> Tuple[sql.Composable, List[Any]]:
        """
        构建 term 查询条件

        :param field: 字段名
        :param value: 查询值
        :param use_bm25: 是否使用 BM25 操作符（默认 True，但会对非文本类型自动禁用）
        :return: (SQL 条件，参数列表)
        """
        validated_field = normalize_identifier(field, "Query field")

        # [OK] 检测值类型，非文本类型不能使用 BM25
        is_text_type = isinstance(value, str)

        if use_bm25 and is_text_type:
            # [OK] 使用 BM25 的 <&> 操作符进行全文检索（仅用于文本字段）
            condition = sql.SQL("({} <&> %s::text) > 0").format(sql.Identifier(validated_field))
        else:
            # [OK] 使用 = 进行精确匹配（适用于所有类型，包括 boolean/integer/float）
            condition = sql.SQL("{} = %s").format(sql.Identifier(validated_field))

        params = [str(value)]
        return condition, params

    @staticmethod
    def build_terms_condition(field: str, values: List[Any]) -> Tuple[sql.Composable, List[Any]]:
        """
        构建 terms 查询条件（多个值的 OR 逻辑）

        注意：此方法只用于顶层 terms 查询，由 search_ops 层的 UNION 方案处理
        这里保留实现以兼容旧代码

        :param field: 字段名
        :param values: 值列表
        :return: (SQL 条件，参数列表)
        """
        return QueryBuilder._build_terms_condition_impl(field, values, use_bm25=True)

    @staticmethod
    def _build_terms_condition_impl(
        field: str,
        values: List[Any],
        use_bm25: bool
    ) -> Tuple[sql.Composable, List[Any]]:
        """构建 terms 查询条件，按上下文决定是否使用 BM25 粗筛。"""
        validated_field = normalize_identifier(field, "Query field")

        if not values:
            return sql.SQL("1 = 0"), []

        all_numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
        if all_numeric:
            condition, params = QueryBuilder._build_terms_in_condition(validated_field, values)
        else:
            condition, params = QueryBuilder._build_terms_text_condition(
                validated_field,
                values,
                use_bm25=use_bm25
            )

        return condition, params

    @staticmethod
    def _build_terms_in_condition(validated_field: str, values: List[Any]) -> Tuple[sql.Composable, List[Any]]:
        """构建数值 terms 的 IN 条件。"""
        placeholders = sql.SQL(", ").join([sql.SQL("%s")] * len(values))
        condition = sql.SQL("{} IN ({})").format(
            sql.Identifier(validated_field),
            placeholders
        )
        return condition, list(values)

    @staticmethod
    def _build_array_or_scalar_exact_condition(validated_field: str) -> sql.Composable:
        """构建兼容 JSON 数组字符串和普通标量的精确匹配条件。"""
        return sql.SQL(
            "CASE WHEN {} LIKE '[%%' THEN "
            "EXISTS (SELECT 1 FROM json_array_elements_text({}::json) AS elem WHERE elem = %s) "
            "ELSE {} = %s END"
        ).format(
            sql.Identifier(validated_field),
            sql.Identifier(validated_field),
            sql.Identifier(validated_field)
        )

    @staticmethod
    def _build_terms_text_condition(
        validated_field: str,
        values: List[Any],
        use_bm25: bool
    ) -> Tuple[sql.Composable, List[Any]]:
        """构建文本 terms 条件，按需包含 BM25 粗筛。"""
        term_conditions = []
        params = []
        for value in values:
            exact_cond = QueryBuilder._build_array_or_scalar_exact_condition(validated_field)
            if use_bm25:
                term_cond = sql.SQL("({} <&> %s::text) > 0 AND {}").format(
                    sql.Identifier(validated_field),
                    exact_cond
                )
                params.extend([str(value), value, value])
            else:
                term_cond = exact_cond
                params.extend([value, value])
            term_conditions.append(term_cond)

        if len(term_conditions) == 1:
            return term_conditions[0], params
        condition = sql.SQL(" OR ").join(term_conditions)
        if use_bm25:
            condition = sql.SQL("({})").format(condition)
        return condition, params

    @staticmethod
    def _build_terms_exact_match(field: str, values: List[Any]) -> Tuple[sql.Composable, List[Any]]:
        """
        构建 terms 查询的纯精确匹配条件（用于 bool 上下文）

        :param field: 字段名
        :param values: 值列表
        :return: (SQL 条件，参数列表)
        """
        return QueryBuilder._build_terms_condition_impl(field, values, use_bm25=False)

    @staticmethod
    def build_range_condition(field: str, range_params: Dict[str, Any]) -> Tuple[sql.Composable, List[Any]]:
        """
        构建 range查询条件（范围查询）

        :param field: 字段名
        :param range_params: 范围参数，支持 gt/gte/lt/lte
        :return: (SQL 条件，参数列表)
        """
        validated_field = normalize_identifier(field, "Query field")
        conditions = []
        params = []

        # 处理 gte (greater than or equal)
        if "gte" in range_params:
            conditions.append(sql.SQL("{} >= %s").format(sql.Identifier(validated_field)))
            params.append(range_params["gte"])

        # 处理 gt (greater than)
        if "gt" in range_params:
            conditions.append(sql.SQL("{} > %s").format(sql.Identifier(validated_field)))
            params.append(range_params["gt"])

        # 处理 lte (less than or equal)
        if "lte" in range_params:
            conditions.append(sql.SQL("{} <= %s").format(sql.Identifier(validated_field)))
            params.append(range_params["lte"])

        # 处理 lt (less than)
        if "lt" in range_params:
            conditions.append(sql.SQL("{} < %s").format(sql.Identifier(validated_field)))
            params.append(range_params["lt"])

        if not conditions:
            raise ValueError("range query must contain at least one of: gte, gt, lte, lt")

        # 使用 AND 连接所有条件
        return sql.SQL(" AND ").join(conditions), params

    @staticmethod
    def build_exists_condition(field: str) -> Tuple[sql.Composable, None]:
        """
        构建 exists 查询条件（字段存在性检查）

        :param field: 字段名
        :return: (SQL 条件，None)
        """
        validated_field = normalize_identifier(field, "Query field")
        # 检查字段是否存在且不为 NULL
        condition = sql.SQL("{} IS NOT NULL").format(sql.Identifier(validated_field))
        return condition, None

    @staticmethod
    def _as_bool_items(items) -> List[Dict[str, Any]]:
        return items if isinstance(items, list) else [items]

    @staticmethod
    def _extend_query_params(params: List[Any], param) -> None:
        if isinstance(param, list):
            params.extend(param)
        elif isinstance(param, tuple):
            params.extend(list(param))
        else:
            params.append(param)

    @staticmethod
    def _join_and_conditions(conditions: List[sql.Composable]) -> sql.Composable:
        return conditions[0] if len(conditions) == 1 else sql.SQL(" AND ").join(conditions)

    @staticmethod
    def _process_and_bool_items(items, params: List[Any], depth: int, bool_type: str):
        conditions = []
        marks = []
        for item in QueryBuilder._as_bool_items(items):
            if "bool" in item:
                nested_conds, nested_params, nested_marks = QueryBuilder.process_bool_clause(
                    item["bool"], depth + 1
                )
                conditions.extend(nested_conds)
                params.extend(nested_params)
                marks.extend(nested_marks)
            elif "nested" in item:
                cond, new_params, nested_marks = QueryBuilder.process_nested_query(item["nested"], params)
                if cond:
                    conditions.append(cond)
                    params[:] = new_params
                    marks.extend(nested_marks)
            else:
                cond, param, item_marks = QueryBuilder.process_query_item(item, bool_type=bool_type)
                if cond:
                    conditions.append(cond)
                    QueryBuilder._extend_query_params(params, param)
                    marks.extend(item_marks)
        return conditions, marks

    @staticmethod
    def _process_should_bool_items(items, params: List[Any], depth: int):
        should_clauses = []
        should_params = []
        should_marks = []
        for item in QueryBuilder._as_bool_items(items):
            if "bool" in item:
                nested_conds, nested_params, nested_marks = QueryBuilder.process_bool_clause(
                    item["bool"], depth + 1
                )
                should_clauses.append(QueryBuilder._join_and_conditions(nested_conds))
                params.extend(nested_params)
                should_marks.extend(nested_marks)
            elif "nested" in item:
                old_param_count = len(params)
                cond, new_params, nested_marks = QueryBuilder.process_nested_query(item["nested"], params)
                if cond:
                    should_clauses.append(cond)
                    should_params.extend(new_params[old_param_count:])
                    params[:] = new_params
                    should_marks.extend(nested_marks)
            else:
                cond, param, item_marks = QueryBuilder.process_query_item(item, bool_type="should")
                if cond:
                    should_clauses.append(cond)
                    QueryBuilder._extend_query_params(should_params, param)
                    should_marks.extend(item_marks)
        return should_clauses, should_params, should_marks

    @staticmethod
    def _process_must_not_bool_items(items, params: List[Any], depth: int):
        conditions = []
        for item in QueryBuilder._as_bool_items(items):
            if "bool" in item:
                nested_conds, nested_params, _ = QueryBuilder.process_bool_clause(
                    item["bool"], depth + 1
                )
                conditions.append(sql.SQL("NOT ({})").format(QueryBuilder._join_and_conditions(nested_conds)))
                params.extend(nested_params)
            elif "nested" in item:
                cond, new_params, _ = QueryBuilder.process_nested_query(item["nested"], params)
                if cond:
                    conditions.append(sql.SQL("NOT ({})").format(cond))
                    params[:] = new_params
            else:
                cond, param, _ = QueryBuilder.process_query_item(item, negate=True, bool_type="must_not")
                if cond:
                    conditions.append(cond)
                    QueryBuilder._extend_query_params(params, param)
        return conditions

    @staticmethod
    def process_bool_clause(
        bool_clause: Dict[str, Any],
        depth: int = 0
    ) -> Tuple[List[sql.Composable], List[Any], List[PostFilterMark]]:
        """
        递归处理 bool 查询的 must/should/must_not 子句

        :param bool_clause: bool 查询条件
        :param depth: 递归深度（用于嵌套 bool）
        :return: (条件列表，参数列表，后过滤标记列表)
        """
        where_conditions = []
        params = []
        post_filter_marks = []

        if "must" in bool_clause:
            conditions, marks = QueryBuilder._process_and_bool_items(
                bool_clause["must"], params, depth, "must"
            )
            where_conditions.extend(conditions)
            post_filter_marks.extend(marks)

        if "should" in bool_clause:
            should_clauses, should_params, should_marks = QueryBuilder._process_should_bool_items(
                bool_clause["should"], params, depth
            )
            if should_clauses:
                where_conditions.append(sql.SQL("({})").format(sql.SQL(" OR ").join(should_clauses)))
                params.extend(should_params)
                post_filter_marks.extend(should_marks)

        if "must_not" in bool_clause:
            where_conditions.extend(QueryBuilder._process_must_not_bool_items(
                bool_clause["must_not"], params, depth
            ))

        if "filter" in bool_clause:
            conditions, marks = QueryBuilder._process_and_bool_items(
                bool_clause["filter"], params, depth, "filter"
            )
            where_conditions.extend(conditions)
            post_filter_marks.extend(marks)

        return where_conditions, params, post_filter_marks

    @staticmethod
    def _process_match_query(query_item: Dict[str, Any], negate: bool, bool_type):
        field, value = next(iter(query_item["match"].items()))
        field = QueryBuilder._normalize_field_path(field, "Match query")
        use_bm25 = (bool_type is None)
        cond, param = QueryBuilder.build_match_condition(field, value, use_bm25=use_bm25)
        if negate:
            cond = sql.SQL("NOT ({})").format(cond)
        return cond, param, []

    @staticmethod
    def _process_match_phrase_query(query_item: Dict[str, Any], negate: bool, bool_type):
        field, value = next(iter(query_item["match_phrase"].items()))
        field = QueryBuilder._normalize_field_path(field, "Match phrase query")

        if isinstance(value, dict):
            phrase_query = value.get("query", "")
            slop = value.get("slop")
        else:
            phrase_query = value
            slop = None

        use_bm25 = (bool_type is None)
        cond, param = QueryBuilder.build_match_phrase_condition(
            field,
            phrase_query,
            slop=slop,
            negate=negate,
            use_bm25=use_bm25
        )

        marks = []
        if not negate and bool_type != "must_not":
            filter_type = "match_phrase_strict" if slop is None or slop == 0 else "match_phrase_slop"
            marks.append(PostFilterMark(
                filter_type=filter_type,
                field=field,
                phrase=phrase_query,
                slop=None if filter_type == "match_phrase_strict" else slop,
                bool_type=bool_type
            ))

        return cond, param, marks

    @staticmethod
    def _process_term_query(query_item: Dict[str, Any], negate: bool, bool_type):
        field, value = next(iter(query_item["term"].items()))
        if field.endswith('.keyword'):
            field = field[:-len('.keyword')]
        field = QueryBuilder._normalize_field_path(field, "Term query")
        use_bm25 = (bool_type is None)
        cond, params = QueryBuilder.build_term_condition(field, value, use_bm25=use_bm25)
        if negate:
            cond = sql.SQL("NOT ({})").format(cond)
        return cond, params, []

    @staticmethod
    def _process_terms_query(query_item: Dict[str, Any], bool_type):
        field, values = next(iter(query_item["terms"].items()))
        field = QueryBuilder._normalize_field_path(field, "Terms query")
        if bool_type is not None:
            cond, params = QueryBuilder._build_terms_exact_match(field, values)
        else:
            cond, params = QueryBuilder.build_terms_condition(field, values)
        return cond, params, []

    @staticmethod
    def _process_range_query(query_item: Dict[str, Any], negate: bool):
        field, range_params = next(iter(query_item["range"].items()))
        field = QueryBuilder._normalize_field_path(field, "Range query")
        cond, params = QueryBuilder.build_range_condition(field, range_params)
        if negate:
            cond = sql.SQL("NOT ({})").format(cond)
        return cond, params, []

    @staticmethod
    def _process_exists_query(query_item: Dict[str, Any], negate: bool):
        exists_config = query_item["exists"]
        field = exists_config.get("field") if isinstance(exists_config, dict) else exists_config
        field = QueryBuilder._normalize_field_path(field, "Exists query")
        cond = QueryBuilder.build_exists_condition(field)
        cond_composable = cond[0] if isinstance(cond, tuple) else cond
        if negate:
            cond_composable = sql.SQL("NOT ({})").format(cond_composable)
        return cond_composable, [], []

    @staticmethod
    def process_query_item(
        query_item: Dict[str, Any],
        negate: bool = False,
        bool_type: Optional[Literal["must", "should", "must_not", "filter"]] = None,
        use_bm25: bool = True
    ) -> Tuple[Optional[sql.Composable], Any, List[PostFilterMark]]:
        """
        处理单个查询项（match/match_phrase/term/terms/range/exists）

        :param query_item: 查询项
        :param negate: 是否取反
        :param bool_type: bool 子句类型（用于确定是否需要后过滤）
        :param use_bm25: 是否使用 BM25 操作符（默认 True）
        :return: (SQL 条件，参数，后过滤标记列表)
        """
        if "match" in query_item:
            return QueryBuilder._process_match_query(query_item, negate, bool_type)
        if "match_phrase" in query_item:
            return QueryBuilder._process_match_phrase_query(query_item, negate, bool_type)
        if "term" in query_item:
            return QueryBuilder._process_term_query(query_item, negate, bool_type)
        if "terms" in query_item:
            return QueryBuilder._process_terms_query(query_item, bool_type)
        if "range" in query_item:
            return QueryBuilder._process_range_query(query_item, negate)
        if "exists" in query_item:
            return QueryBuilder._process_exists_query(query_item, negate)
        return None, None, []

    @staticmethod
    def _knn_filter_field(field: str, context: str) -> str:
        field = QueryBuilder._normalize_field_path(field, context)
        return normalize_identifier(field, "Query field")

    @staticmethod
    def _build_knn_term_filter(term_query: Dict[str, Any]) -> Tuple[List[str], List[Any]]:
        conditions = []
        params = []
        for field, value in term_query.items():
            validated_field = QueryBuilder._knn_filter_field(field, "Filter term")
            conditions.append(f'{quote_identifier(validated_field)} = %s')
            params.append(value)
        return conditions, params

    @staticmethod
    def _build_knn_terms_filter(terms_query: Dict[str, List[Any]]) -> Tuple[List[str], List[Any]]:
        conditions = []
        params = []
        for field, values in terms_query.items():
            validated_field = QueryBuilder._knn_filter_field(field, "Filter terms")
            placeholders = ','.join(['%s'] * len(values))
            conditions.append(f'{quote_identifier(validated_field)} IN ({placeholders})')
            params.extend(values)
        return conditions, params

    @staticmethod
    def _build_knn_match_filter(match_query: Dict[str, Any]) -> Tuple[List[str], List[Any]]:
        conditions = []
        params = []
        for field, value in match_query.items():
            validated_field = QueryBuilder._knn_filter_field(field, "Filter match")
            conditions.append(f'{quote_identifier(validated_field)} LIKE %s::text')
            params.append(f"%{value}%")
        return conditions, params

    @staticmethod
    def _build_knn_range_filter(range_query: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[Any]]:
        operators = (("gte", ">="), ("lte", "<="), ("gt", ">"), ("lt", "<"))
        conditions = []
        params = []
        for field, range_params in range_query.items():
            if not isinstance(range_params, dict):
                continue
            validated_field = QueryBuilder._knn_filter_field(field, "Filter range")
            for key, operator in operators:
                if key in range_params:
                    conditions.append(f'{quote_identifier(validated_field)} {operator} %s')
                    params.append(range_params[key])
        return conditions, params

    @staticmethod
    def _as_filter_list(value) -> List[Any]:
        return value if isinstance(value, list) else [value]

    @staticmethod
    def _append_knn_filter_conditions(conditions, params, filter_list, wrapper):
        for condition in QueryBuilder._as_filter_list(filter_list):
            if not isinstance(condition, dict):
                continue
            cond, param = QueryBuilder.process_filter_for_knn(condition)
            if cond:
                conditions.append(wrapper(cond))
                params.extend(param)

    @staticmethod
    def _build_knn_bool_filter(bool_clause: Dict[str, Any]) -> Tuple[List[str], List[Any]]:
        where_conditions = []
        params = []

        for clause_name in ("must", "filter"):
            if clause_name in bool_clause:
                QueryBuilder._append_knn_filter_conditions(
                    where_conditions,
                    params,
                    bool_clause[clause_name],
                    lambda cond: f"({cond})"
                )

        if "should" in bool_clause:
            or_parts = []
            QueryBuilder._append_knn_filter_conditions(
                or_parts,
                params,
                bool_clause["should"],
                lambda cond: f"({cond})"
            )
            if or_parts:
                where_conditions.append("(" + " OR ".join(or_parts) + ")")

        if "must_not" in bool_clause:
            QueryBuilder._append_knn_filter_conditions(
                where_conditions,
                params,
                bool_clause["must_not"],
                lambda cond: f"NOT ({cond})"
            )

        return where_conditions, params

    @staticmethod
    def process_filter_for_knn(filter_query: Dict[str, Any]) -> tuple:
        """
        查询中的过滤条件处理 kNN（增强版 - 支持 bool 嵌套）

        :param filter_query: 过滤条件字典
        :return: (SQL 条件字符串，参数列表)
        """
        if "term" in filter_query:
            where_conditions, params = QueryBuilder._build_knn_term_filter(filter_query["term"])
        elif "terms" in filter_query:
            where_conditions, params = QueryBuilder._build_knn_terms_filter(filter_query["terms"])
        elif "match" in filter_query:
            where_conditions, params = QueryBuilder._build_knn_match_filter(filter_query["match"])
        elif "range" in filter_query:
            where_conditions, params = QueryBuilder._build_knn_range_filter(filter_query["range"])
        elif "bool" in filter_query:
            where_conditions, params = QueryBuilder._build_knn_bool_filter(filter_query["bool"])
        else:
            where_conditions, params = [], []

        if where_conditions:
            return " AND ".join(where_conditions), params
        return None, []

    # ========== Nested Query Support (首值策略) ==========

    @staticmethod
    def process_nested_query(
        nested_clause: Dict[str, Any],
        params: List[Any]
    ) -> Tuple[sql.Composable, List[Any], List[PostFilterMark]]:
        """
        处理 nested 查询子句（首值策略简化版）

        Args:
            nested_clause: {"path": "authors", "query": {...}}
            params: SQL 参数列表

        Returns:
            (where_condition, params, marks)

        Example:
            >>> nested = {
            ...     "path": "author",
            ...     "query": {
            ...         "term": {"name": "John Doe"}
            ...     }
            ... }
            >>> # 转换为：author_name = 'John Doe'
        """
        path = nested_clause.get('path')
        query = nested_clause.get('query', {})

        if not path:
            raise ValueError("Nested query must contain 'path'")

        # [OK] 标准化 nested 路径（将 . 和 - 替换为 _）
        path = QueryBuilder._normalize_field_path(path, "Nested query")

        # 将 nested 查询转换为扁平字段查询
        flattened_query = QueryBuilder._flatten_nested_query(query, path)

        # 递归处理扁平化后的查询
        # 注意：flattened_query 可能包含多个查询项，需要找到第一个非空查询
        for query_type in ['match', 'match_phrase', 'term', 'terms', 'range', 'bool']:
            if query_type in flattened_query:
                cond, new_params, marks = QueryBuilder.process_query_item(flattened_query, bool_type="must")
                params.extend(new_params if isinstance(new_params, list) else [new_params] if new_params else [])
                return cond, params, marks

        # 如果没有找到支持的查询类型，返回空条件
        return sql.SQL("1=0"), params, []

    @staticmethod
    def _flatten_nested_query(query: Dict[str, Any], path_prefix: str) -> Dict[str, Any]:
        """
        递归扁平化 nested 查询中的字段名

        Args:
            query: 原始查询
            path_prefix: nested 路径前缀

        Returns:
            扁平化后的查询

        Example:
            >>> query = {"match": {"name": "John"}}
            >>> path_prefix = "author"
            >>> # Returns: {"match": {"author_name": "John"}}
        """
        result = {}

        for key, value in query.items():
            if key in ['match', 'match_phrase', 'term', 'terms', 'range']:
                # 处理查询子句中的字段
                new_value = {}
                for field, condition in value.items():
                    # [OK] 检查 field 是否已经包含 path_prefix
                    # 例如：field="documentList.name", path_prefix="documentList"
                    # 应该转换为 "documentList_name" 而不是 "documentList__documentList_name"
                    normalized_field = QueryBuilder._normalize_nested_field(field, path_prefix)
                    new_value[normalized_field] = condition
                result[key] = new_value
            elif key == 'bool':
                # 递归处理 bool 查询
                result[key] = QueryBuilder._flatten_nested_bool(value, path_prefix)
            else:
                result[key] = value

        return result

    @staticmethod
    def _normalize_nested_field(field: str, path_prefix: str) -> str:
        """
        标准化 nested 字段名，避免重复添加 path 前缀

        Args:
            field: 原始字段名（可能已包含 path）
            path_prefix: nested 路径前缀

        Returns:
            标准化后的字段名

        Examples:
            >>> _normalize_nested_field("name", "author")
            'author__name'
            >>> _normalize_nested_field("author.name", "author")
            'author__name'
        """
        # 如果 field 以 path_prefix. 开头，去掉这个前缀
        if field.startswith(f"{path_prefix}."):
            field = field[len(path_prefix) + 1:]  # 去掉 "path." 部分

        # 将 . 替换为 __
        field_with_separator = field.replace('.', NESTED_FIELD_SEPARATOR)

        # 添加 path 前缀
        return f"{path_prefix}{NESTED_FIELD_SEPARATOR}{field_with_separator}"

    @staticmethod
    def _flatten_nested_bool_clause(clause: Any, path_prefix: str) -> Optional[Dict[str, Any]]:
        if not isinstance(clause, dict):
            return None

        if 'nested' in clause:
            nested_clause = clause['nested']
            nested_path = nested_clause['path']
            nested_query = nested_clause['query']
            full_path = f"{path_prefix}{NESTED_FIELD_SEPARATOR}{nested_path}"
            return QueryBuilder._flatten_nested_query(nested_query, full_path)

        return QueryBuilder._flatten_nested_query(clause, path_prefix)

    @staticmethod
    def _flatten_nested_bool(bool_clause: Dict[str, Any], path_prefix: str) -> Dict[str, Any]:
        """
        扁平化 bool 查询中的 nested 字段

        Args:
            bool_clause: bool 查询子句
            path_prefix: nested 路径前缀

        Returns:
            扁平化后的 bool 查询
        """
        result = {}

        for clause_type in ['must', 'should', 'must_not', 'filter']:
            if clause_type not in bool_clause:
                continue

            result[clause_type] = []
            for clause in QueryBuilder._as_bool_items(bool_clause[clause_type]):
                flattened = QueryBuilder._flatten_nested_bool_clause(clause, path_prefix)
                if flattened is not None:
                    result[clause_type].append(flattened)

        return result


# 导出便捷函数
__all__ = [
    '_validate_identifier',
    '_validate_identifiers',
    'QueryBuilder'
]
