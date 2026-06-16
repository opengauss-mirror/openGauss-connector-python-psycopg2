import json
from typing import Any, Dict, List, Tuple, Optional
from contextlib import contextmanager

import psycopg2.errors
from psycopg2 import sql

from opensearch_sdk.client.utils import normalize_identifier
from opensearch_sdk.client.query_builder import _validate_identifier
from opensearch_sdk.client.constants import MILLISECONDS_PER_SECOND, NESTED_FIELD_SEPARATOR

# [OK] 从子模块导入已提取的函数
from opensearch_sdk.client.doc_utils.nested_handler import (
    _reconstruct_nested_structure,
    _flatten_nested_value,
    _flatten_nested_document,
    has_nested_fields,
)
from opensearch_sdk.client.doc_utils.serialization import process_body_fields as _process_body_fields_impl
from opensearch_sdk.client.doc_utils.type_inference import infer_column_type_from_value
from opensearch_sdk.client.doc_utils.operations import (
    DocumentOperationsMixin as _DocumentOperationsMixin,
)
from opensearch_sdk.client.doc_utils.helpers import (
    validate_index,
    validate_document_params,
)


class DocumentOpsMixin(_DocumentOperationsMixin):
    """
    文档操作 Mixin，提供文档的创建、读取、更新、删除功能

    资源管理规范:
    - 使用事务确保操作的原子性
    - 异常时自动回滚
    - 支持上下文管理器进行资源管理
    """

    def _init_document_ops(self, **kwargs):
        """
        初始化 DocumentOpsMixin（手动调用，避免多重继承问题）

        :arg enable_dynamic_inference: 是否启用动态列类型推断（默认 False）
                                      True: 当字段不在 mapping 中时，从样本值推断类型
                                      False: 严格模式，字段必须在 mapping 中定义
        :arg bulk_batch_size: Bulk 批量操作大小（默认 100）
        """
        # 动态列推断开关（默认启用 - 宽松模式）
        self.enable_dynamic_inference = kwargs.get('enable_dynamic_inference', True)
        # Bulk 批量操作大小（使用常量默认值）
        from opensearch_sdk.client.constants import DEFAULT_BATCH_SIZE, MAX_BATCH_SIZE
        bulk_batch_size = kwargs.get('bulk_batch_size', DEFAULT_BATCH_SIZE)
        # 验证范围
        if not isinstance(bulk_batch_size, int) or bulk_batch_size < 1:
            bulk_batch_size = DEFAULT_BATCH_SIZE
        elif bulk_batch_size > MAX_BATCH_SIZE:
            bulk_batch_size = MAX_BATCH_SIZE
        self.bulk_batch_size = bulk_batch_size

    def _get_mapping(self, index: str) -> dict:
        """
        获取索引 mapping（用于识别 nested 字段）

        :param index: 索引名称
        :return: mapping 字典，如果获取失败返回空字典
        """
        try:
            if hasattr(self, 'indices') and hasattr(self.indices, 'get_mapping'):
                result = self.indices.get_mapping(index=index)
                # get_mapping 返回 {index_name: {'mappings': {...}}}
                # 需要提取内部的 mappings
                if isinstance(result, dict):
                    index_data = result.get(index, {})
                    mapping_data = index_data.get('mappings', {})
                    return {'mappings': mapping_data}
        except Exception as e:
            # 获取 mapping 失败时不抛出异常，返回空字典
            pass
        return {}

    def _has_nested_fields(self, mapping: dict) -> bool:
        """
        检查 mapping 是否包含 nested 字段

        :param mapping: 索引 mapping
        :return: True 如果包含 nested 字段，否则 False

        注意：由于 Opensearch 在创建索引时会将 nested 展开为普通列，
        因此无法从展开后的 mapping 中识别 nested。
        这个方法目前主要用于向前兼容，实际判断逻辑已移至_write时的智能检测。
        """
        return has_nested_fields(mapping)

    @contextmanager
    def transaction(self):
        """
        上下文管理器：自动管理事务提交/回滚

        [FIX] 在连接池模式下，必须在同一个连接上下文中执行所有操作

        使用示例::

            # 连接池模式（推荐）
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO table VALUES (1)")
                cursor.execute("UPDATE table SET x = 1")
            # 正常退出时自动在同一个连接上提交

        异常处理::

            try:
                with self.transaction() as conn:
                    cursor = conn.cursor()
                    cursor.execute(sql, params)
            except Exception:
                # 异常时自动在同一个连接上回滚
                raise
        """
        if self.connection.use_connection_pool:
            # 连接池模式：获取一个连接，在该连接上执行所有操作
            with self.connection.get_connection_for_operation() as conn:
                try:
                    yield conn  # 返回连接给调用者
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        else:
            # 单连接模式：保持原有逻辑
            try:
                yield self
                self.commit()
            except Exception:
                self.rollback()
                raise

    @staticmethod
    def _resolve_document_id(document_id: str = None, **kwargs) -> str:
        if document_id is None and 'id' in kwargs:
            document_id = kwargs.pop('id')
        if kwargs:
            unexpected = next(iter(kwargs))
            raise TypeError(f"unexpected keyword argument '{unexpected}'")
        return document_id

    def create(self, index: str, document_id: str = None, body: Dict[str, Any] = None,
               refresh: bool = False, **kwargs) -> Any:
        """
        创建新文档，仅当文档 ID 不存在时插入，否则返回 409 Conflict

        :param index: 索引名称（对应数据库表名）
        :param document_id: 文档 ID
        :param body: 文档内容
        :param refresh: 是否刷新（在 Opensearch 中此参数被忽略，仅为了兼容性保留）
        :return: 操作结果
        :raises ValueError: 当参数无效时抛出
        :raises Exception: 当创建失败时抛出
        """
        document_id = self._resolve_document_id(document_id, **kwargs)
        # [FIX] 如果启用 SQL 追踪，手动创建记录
        if hasattr(self, 'sql_tracer') and self.sql_tracer and self.sql_tracer.enabled:
            with self.sql_tracer.trace_session("create", index) as session:
                result = self._create_impl(index, document_id, body, refresh)

                # 手动创建 SQL 记录
                if session:
                    from opensearch_sdk.client.sql_tracer.record import SQLTraceRecord
                    import time

                    record = SQLTraceRecord(
                        sql=f"INSERT INTO {index} (模拟SQL)",
                        params=None,
                        start_time=time.time(),
                        context=f"create_{index}"
                    )
                    record.end_time = time.time()
                    record.duration_ms = 0
                    record.result_count = 1

                    # 设置 metadata
                    record.metadata['document_id'] = document_id
                    record.metadata['field_count'] = len(body) if isinstance(body, dict) else 0

                    session.add_record(record)

                return result
        else:
            return self._create_impl(index, document_id, body, refresh)

    def index(self, index: str, document_id: str = None, body: Dict[str, Any] = None,
              refresh: bool = False, **kwargs) -> Any:
        """
        插入或更新单个文档（UPSERT 语义）
        使用 INSERT + UPDATE 实现 UPSERT

        :param index: 索引名称（对应数据库表名）
        :param document_id: 文档 ID
        :param body: 文档内容
        :param refresh: 是否刷新（在 Opensearch 中此参数被忽略，仅为了兼容性保留）
        :return: 操作结果
        """
        document_id = self._resolve_document_id(document_id, **kwargs)
        return self._index_impl(index, document_id, body, refresh)

    def update(self, index: str, document_id: str = None, body: Dict[str, Any] = None,
               refresh: bool = False, **kwargs) -> Any:
        """
        部分更新文档

        :param index: 索引名称（对应数据库表名）
        :param document_id: 文档 ID
        :param body: 要更新的字段（只包含需要变更的字段）
        :param refresh: 是否刷新
        :return: 操作结果
        :raises Exception: 当文档不存在时抛出 404 错误
        """
        document_id = self._resolve_document_id(document_id, **kwargs)
        return self._update_impl(index, document_id, body, refresh)

    def get(self, index: str, document_id: str = None, **kwargs) -> Any:
        """
        根据文档 ID 获取文档

        :param index: 索引名称（对应数据库表名）
        :param document_id: 文档 ID
        :return: 文档内容
        """
        document_id = self._resolve_document_id(document_id, **kwargs)
        return self._get_impl(index, document_id)

    def get_id(self, index: str, document_id: str = None, **kwargs) -> Any:
        """
        根据文档ID获取文档 (与get方法功能相同，为了兼容性保留)

        :param index: 索引名称
        :param document_id: 文档ID
        :return: 文档内容
        """
        document_id = self._resolve_document_id(document_id, **kwargs)
        return self.get(index, document_id)

    def delete(self, index: str, document_id: str = None, refresh: bool = False, **kwargs) -> Any:
        """
        删除指定 ID 的文档

        :param index: 索引名称
        :param document_id: 文档 ID
        :param refresh: 是否刷新
        :return: 操作结果
        """
        document_id = self._resolve_document_id(document_id, **kwargs)
        return self._delete_impl(index, document_id, refresh)

    def delete_id(self, index: str, document_id: str = None, **kwargs) -> Any:
        """
        删除指定ID的文档 (与delete方法功能相同，为了兼容性保留)
        """
        document_id = self._resolve_document_id(document_id, **kwargs)
        return self.delete(index, document_id)

    def _execute_delete_ids(self, sql_query, ids: List[str], cursor=None) -> int:
        if cursor is not None:
            cursor.execute(sql_query, ids)
            return cursor.rowcount

        with self.connection.get_connection_for_operation() as conn:
            local_cursor = conn.cursor()
            try:
                local_cursor.execute(sql_query, ids)
                deleted_count = local_cursor.rowcount
                conn.commit()
                return deleted_count
            finally:
                local_cursor.close()

    def delete_ids(self, index: str, ids: List[str], cursor=None) -> Any:
        """
        批量删除多个文档

        :param index: 索引名称
        :param ids: 文档 ID 列表
        :param cursor: 可选的 cursor 对象，如果提供则复用，否则创建新的
        :return: 操作结果
        """
        try:
            validated_index = normalize_identifier(index, "Index name")

            if not ids or len(ids) == 0:
                return {"deleted": 0}

            placeholders = sql.SQL(", ").join([sql.Placeholder()] * len(ids))
            sql_query = sql.SQL("DELETE FROM {} WHERE id IN ({})").format(
                sql.Identifier(validated_index),
                placeholders
            )
            deleted_count = self._execute_delete_ids(sql_query, ids, cursor)
            return {"deleted": deleted_count}
        except Exception as e:
            raise Exception(f"##OS## - Bulk Delete Error | index={index} | error: {str(e)}")

    def delete_docs_by_field_values(self, index: str, field: str, values: List[str]) -> Any:
        """
        根据字段值删除文档

        :param index: 索引名称
        :param field: 字段名
        :param values: 字段值列表
        :return: 删除结果
        """
        try:
            validated_index = normalize_identifier(index, "Index name")
            validated_field = normalize_identifier(field, "Delete by field")

            placeholders = sql.SQL(", ").join([sql.Placeholder()] * len(values))
            sql_query = sql.SQL("DELETE FROM {} WHERE {} IN ({})").format(
                sql.Identifier(validated_index),
                sql.Identifier(validated_field),
                placeholders
            )

            # [FIX] 使用 get_connection_for_operation() 确保在同一连接上执行和提交
            with self.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(sql_query, values)
                    deleted_count = cursor.rowcount
                    conn.commit()  # 在同一个连接上提交

                    return {
                        "deleted": deleted_count
                    }
                finally:
                    cursor.close()
        except Exception as e:
            raise Exception(f"##OS## - Delete by Query Error | index={index} | field={field} | error: {str(e)}")

    def delete_by_query(
        self,
        index: str,
        body: Dict[str, Any],
        wait_for_completion: bool = True,
        refresh: bool = False
    ) -> Any:
        """
        根据查询条件删除文档

        :param index: 索引名称
        :param body: 查询条件
        :param wait_for_completion: 是否等待完成
        :param refresh: 是否刷新
        :return: 删除结果
        """
        try:
            from opensearch_sdk.client.doc_utils.query_executor import QueryExecutor

            validated_index = QueryExecutor.validate_and_normalize_index(index)

            # 检查是否包含 should + minimum_should_match 的 bool 查询（BM25 OR 条件）
            if QueryExecutor.check_problematic_or_query(body):
                return self._delete_by_query_python_filter(validated_index, body, refresh)

            # 构建 WHERE 子句
            query = body.get("query", {})
            where_conditions, params, _ = QueryExecutor.build_where_clause(query)

            # 构建并执行 DELETE SQL
            sql_query = QueryExecutor.build_delete_sql(validated_index, where_conditions)

            # [FIX] 使用 get_connection_for_operation() 确保在同一连接上执行和提交
            with self.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(sql_query, params)
                    deleted_count = cursor.rowcount
                    conn.commit()  # 在同一个连接上提交

                    return {
                        "deleted": deleted_count,
                        "failures": []
                    }
                finally:
                    cursor.close()
        except Exception as e:
            # [FIX] 上下文管理器已自动 rollback，无需手动调用
            raise Exception(f"##OS## - Delete By Query Error | index={index} | error: {str(e)}")

    def _fetch_all_docs_for_python_filter(self, index: str):
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    sql.SQL("SELECT * FROM {}").format(sql.Identifier(index))
                )
                rows = cursor.fetchall()
                column_names = [desc[0] for desc in cursor.description]
                return rows, column_names
            finally:
                cursor.close()

    def _matches_minimum_should(self, doc: Dict[str, Any], should_values, minimum_should_match: int) -> bool:
        matched_count = sum(
            1
            for clause in should_values
            if self._check_clause_match(clause, doc)
        )
        return matched_count >= minimum_should_match

    def _matching_doc_ids_for_should_query(self, rows, column_names, bool_query: Dict[str, Any]) -> List[str]:
        should_values = bool_query["should"]
        minimum_should_match = bool_query.get("minimum_should_match", 1)
        docs_to_delete = []

        for row in rows:
            doc = dict(zip(column_names, row))
            if self._matches_minimum_should(doc, should_values, minimum_should_match):
                docs_to_delete.append(doc.get('id'))

        return docs_to_delete

    def _delete_by_query_python_filter(self, index: str, body: Dict[str, Any], refresh: bool = False) -> Any:
        """
        Python 层过滤方案：用于处理 BM25 OR 条件的 bug

        :param index: 索引名称
        :param body: 查询条件
        :param refresh: 是否刷新
        :return: 删除结果
        """
        try:
            rows, column_names = self._fetch_all_docs_for_python_filter(index)
            bool_query = body["query"]["bool"]
            docs_to_delete = self._matching_doc_ids_for_should_query(rows, column_names, bool_query)
            deleted_count = self.delete_ids(index, docs_to_delete)["deleted"]
            return {
                "deleted": deleted_count,
                "failures": []
            }
        except Exception as e:
            # [FIX] 上下文管理器已自动 rollback，无需手动调用
            raise Exception(f"##OS## - Delete By Query Python Filter Error | index={index} | error: {str(e)}")

    def _check_clause_match(self, clause: Dict[str, Any], doc: Dict[str, Any]) -> bool:
        """
        检查单个 clause 是否匹配文档

        :param clause: 查询子句（如 {"term": {"field": "value"}}）
        :param doc: 文档字典
        :return: 是否匹配
        """
        if "match" in clause:
            field, value = next(iter(clause["match"].items()))
            field_value = doc.get(field, "")

            # 检查字段值是否包含查询词
            if isinstance(field_value, str):
                if str(value).lower() in field_value.lower():
                    return True
            elif isinstance(field_value, (list, dict)):
                # JSON 类型，转为字符串后检查
                field_value_str = json.dumps(field_value, ensure_ascii=False).lower()
                if str(value).lower() in field_value_str:
                    return True

        elif "term" in clause:
            field, value = next(iter(clause["term"].items()))
            field_value = doc.get(field)
            # term 是精确匹配
            if field_value == value:
                return True

        elif "terms" in clause:
            field, values = next(iter(clause["terms"].items()))
            field_value = doc.get(field)
            # terms 是多值匹配
            if field_value in values:
                return True

        elif "range" in clause:
            field, range_params = next(iter(clause["range"].items()))
            field_value = doc.get(field)
            # 检查范围条件
            return self._check_range_match(range_params, field_value)

        return False

    def _check_range_match(self, range_params: Dict[str, Any], field_value: Any) -> bool:
        """
        检查范围条件是否匹配

        :param range_params: 范围参数（gte/gt/lte/lt）
        :param field_value: 字段值
        :return: 是否匹配
        """
        if field_value is None:
            return False

        if "gte" in range_params and field_value < range_params["gte"]:
            return False
        if "gt" in range_params and field_value <= range_params["gt"]:
            return False
        if "lte" in range_params and field_value > range_params["lte"]:
            return False
        if "lt" in range_params and field_value >= range_params["lt"]:
            return False

        return True

    @staticmethod
    def _ensure_same_bulk_index(index_name: str, actual_index: str) -> str:
        if index_name is not None and actual_index != index_name:
            raise ValueError(f"Bulk operations must target same index: expected {index_name}, got {actual_index}")
        return actual_index

    @staticmethod
    def _parse_bulk_delete(op_meta: Dict[str, Any], index_name: str):
        delete_op = op_meta['delete']
        index_name = DocumentOpsMixin._ensure_same_bulk_index(index_name, delete_op['_index'])
        return index_name, {
            'id': delete_op['_id'],
            'operation': 'delete'
        }

    @staticmethod
    def _parse_bulk_write(op_meta: Dict[str, Any], doc_data: Dict[str, Any], index_name: str):
        if 'update' in op_meta:
            update_op = op_meta['update']
            index_name = DocumentOpsMixin._ensure_same_bulk_index(index_name, update_op['_index'])
            return index_name, {
                'id': update_op['_id'],
                'data': doc_data.get('doc', {}),
                'operation': 'update',
                'doc_as_upsert': doc_data.get('doc_as_upsert', False)
            }

        index_op = op_meta['index']
        index_name = DocumentOpsMixin._ensure_same_bulk_index(index_name, index_op['_index'])
        return index_name, {
            'id': index_op['_id'],
            'data': doc_data,
            'operation': 'index'
        }

    @staticmethod
    def _parse_bulk_body(body: str):
        if not isinstance(body, str):
            raise ValueError("Bulk body must be a NDJSON string")

        lines = body.strip().split('\n')
        parsed_actions = []
        index_name = None
        i = 0

        while i < len(lines):
            if not lines[i].strip():
                i += 1
                continue

            op_meta = json.loads(lines[i])
            i += 1

            if 'delete' in op_meta:
                index_name, action = DocumentOpsMixin._parse_bulk_delete(op_meta, index_name)
                parsed_actions.append(action)
            elif 'update' in op_meta or 'index' in op_meta:
                if i >= len(lines):
                    raise ValueError("Missing data line for update/index operation")
                doc_data = json.loads(lines[i])
                i += 1
                index_name, action = DocumentOpsMixin._parse_bulk_write(op_meta, doc_data, index_name)
                parsed_actions.append(action)
            else:
                raise ValueError(f"Unknown operation type in bulk request: {op_meta}")

        if index_name is None:
            raise ValueError("No index found in bulk request")
        return index_name, parsed_actions

    def _execute_bulk_transaction(self, index_name: str, parsed_actions: List[Dict[str, Any]]) -> Any:
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                result = self._process_bulk_actions_with_cursor(index_name, parsed_actions, cursor)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

    def bulk(self, body: str, *, refresh: bool = False) -> Any:
        """
        批量插入或更新文档（原子操作）

        :param body: NDJSON 字符串格式的批量操作数据
        :param refresh: 是否刷新
        :return: 操作结果
        """
        import time
        start_time = time.time()

        try:
            index_name, parsed_actions = self._parse_bulk_body(body)
            result = self._execute_bulk_transaction(index_name, parsed_actions)
            took_ms = int((time.time() - start_time) * MILLISECONDS_PER_SECOND)
            result['took'] = took_ms
            return result
        except Exception as e:
            # [FIX] 上下文管理器已自动 rollback，无需手动调用
            raise Exception(f"##OS## - Bulk Index Error | error: {str(e)}")

    def _process_bulk_actions(self, index: str, actions: List[Dict[str, Any]]) -> Any:
        """
        处理批量操作的内部方法（兼容旧接口，不支持事务）
        """
        return self._process_bulk_actions_impl(index, actions, cursor=None)

    def _process_bulk_actions_with_cursor(self, index: str, actions: List[Dict[str, Any]], cursor) -> Any:
        """
        处理批量操作的内部方法（支持传入 cursor，用于事务化 bulk）

        :param index: 索引名称
        :param actions: 操作列表
        :param cursor: 复用的 cursor 对象
        :return: 操作结果
        """
        return self._process_bulk_actions_impl(index, actions, cursor=cursor)

    @staticmethod
    def _stage_bulk_action(index: str, action: Dict[str, Any]):
        if action.get('operation') == 'delete':
            return 'delete', action['id'], None, {
                'delete': {
                    '_index': index,
                    '_id': action['id'],
                    'status': 200,
                    'result': 'deleted'
                }
            }

        doc_id = action['id']
        body = action.get('data', {})
        op_type = 'update' if action.get('operation') == 'update' else 'index'
        action['_original_operation'] = op_type
        return 'write', doc_id, (doc_id, body), {
            op_type: {
                '_index': index,
                '_id': doc_id,
                'status': None,
                'result': None
            }
        }

    @staticmethod
    def _stage_bulk_actions(index: str, actions: List[Dict[str, Any]]):
        delete_ids = []
        insert_docs = []
        results = []

        for action in actions:
            try:
                action_type, doc_id, insert_doc, result = DocumentOpsMixin._stage_bulk_action(index, action)
                if action_type == 'delete':
                    delete_ids.append(doc_id)
                else:
                    insert_docs.append(insert_doc)
                results.append(result)
            except Exception as e:
                results.append({
                    'error': {
                        '_index': index,
                        '_id': action.get('id', 'unknown'),
                        'status': 500,
                        'error': {'type': 'Exception', 'reason': str(e)}
                    }
                })
        return delete_ids, insert_docs, results

    @staticmethod
    def _mark_bulk_insert_success(results: List[Dict[str, Any]]) -> None:
        for result in results:
            for op_type in ['update', 'index']:
                if op_type in result and 'error' not in result:
                    result[op_type]['status'] = 201
                    result[op_type]['result'] = 'created'

    @staticmethod
    def _mark_bulk_write_error(results: List[Dict[str, Any]], insert_docs, error_msg: str) -> None:
        for i, result in enumerate(results):
            for op_type in ['update', 'index']:
                if op_type in result and result[op_type].get('status') is None:
                    result[op_type] = {
                        '_index': result[op_type].get('_index'),
                        '_id': insert_docs[i][0] if i < len(insert_docs) else 'unknown',
                        'status': 500,
                        'error': {'type': 'Exception', 'reason': error_msg}
                    }

    @staticmethod
    def _iter_pending_bulk_entries(results: List[Dict[str, Any]], doc_id: str):
        for result in results:
            for op_type in ['update', 'index']:
                entry = result.get(op_type)
                if entry and entry.get('_id') == doc_id and entry.get('status') is None:
                    yield entry

    @staticmethod
    def _bulk_success_payload(operation_type: str) -> tuple:
        if operation_type == 'created':
            return 201, 'created'
        return 200, 'updated'

    @staticmethod
    def _update_bulk_single_result(results: List[Dict[str, Any]], doc_id: str, operation_type: str) -> None:
        status, result_value = DocumentOpsMixin._bulk_success_payload(operation_type)
        for entry in DocumentOpsMixin._iter_pending_bulk_entries(results, doc_id):
            entry['status'] = status
            entry['result'] = result_value

    @staticmethod
    def _mark_bulk_single_error(results: List[Dict[str, Any]], index: str, doc_id: str, error: Exception) -> None:
        for result in results:
            for op_type in ['update', 'index']:
                if (op_type in result and
                    result[op_type].get('_id') == doc_id and
                    result[op_type].get('status') is None):
                    result[op_type] = {
                        '_index': index,
                        '_id': doc_id,
                        'status': 500,
                        'error': {'type': 'Exception', 'reason': str(error)}
                    }

    def _handle_bulk_conflicts(self, index: str, insert_docs, results: List[Dict[str, Any]]) -> None:
        for doc_id, body in insert_docs:
            try:
                single_result = self._index_impl(index, doc_id, body)
                operation_type = single_result.get('result', 'updated')
                self._update_bulk_single_result(results, doc_id, operation_type)
            except Exception as single_error:
                self._mark_bulk_single_error(results, index, doc_id, single_error)

    @staticmethod
    def _mark_bulk_delete_success(results: List[Dict[str, Any]]) -> None:
        for result in results:
            if 'delete' in result and 'error' not in result:
                result['delete']['status'] = 200
                result['delete']['result'] = 'deleted'

    @staticmethod
    def _mark_bulk_delete_error(
        results: List[Dict[str, Any]],
        delete_ids: List[str],
        error: Exception
    ) -> None:
        for i, result in enumerate(results):
            if 'delete' in result:
                result['delete'] = {
                    '_index': result['delete'].get('_index'),
                    '_id': delete_ids[i] if i < len(delete_ids) else 'unknown',
                    'status': 500,
                    'error': {'type': 'Exception', 'reason': str(error)}
                }

    def _handle_bulk_deletes(
        self,
        index: str,
        delete_ids: List[str],
        results: List[Dict[str, Any]],
        cursor=None
    ) -> None:
        if not delete_ids:
            return
        try:
            self.delete_ids(index, delete_ids, cursor=cursor)
            self._mark_bulk_delete_success(results)
        except Exception as error:
            self._mark_bulk_delete_error(results, delete_ids, error)

    @staticmethod
    def _is_bulk_conflict(error: Exception) -> bool:
        error_msg = str(error).lower()
        return (
            "duplicate" in error_msg or
            "unique" in error_msg or
            "already exists" in error_msg
        )

    def _handle_bulk_writes(
        self,
        index: str,
        insert_docs,
        results: List[Dict[str, Any]],
        cursor=None
    ) -> None:
        if not insert_docs:
            return
        try:
            self._bulk_insert_strict(index, insert_docs, cursor=cursor)
            self._mark_bulk_insert_success(results)
        except Exception as insert_error:
            if self._is_bulk_conflict(insert_error):
                self._handle_bulk_conflicts(index, insert_docs, results)
            else:
                self._mark_bulk_write_error(results, insert_docs, str(insert_error))

    def _process_bulk_actions_impl(self, index: str, actions: List[Dict[str, Any]], cursor=None) -> Any:
        """
        处理批量操作的内部实现

        :param index: 索引名称
        :param actions: 操作列表
        :param cursor: 可选的 cursor 对象，如果提供则复用，否则每个操作独立创建
        :return: 操作结果
        """
        # [OK] 注意：在事务化 bulk 中，我们跳过表检查和创建
        # 原因：indices.exists() 和 indices.create() 会获取独立的连接
        # 这会导致连接泄漏，并且破坏事务的原子性
        # 解决方案：假设表已存在，如果不存在让数据库报错
        if cursor is None:
            # 非事务模式：执行表检查
            if not self.indices.exists(index=index):
                self.indices.create(index=index)
        # 事务模式：跳过表检查，直接使用传入的 cursor

        delete_ids, insert_docs, results = self._stage_bulk_actions(index, actions)

        self._handle_bulk_deletes(index, delete_ids, results, cursor=cursor)
        self._handle_bulk_writes(index, insert_docs, results, cursor=cursor)

        has_errors = any('error' in str(result) for result in results)

        return {
            'took': 0,
            'errors': has_errors,
            'items': results
        }

    @staticmethod
    def _collect_bulk_field_samples(docs: List[Tuple[str, Dict[str, Any]]]) -> Dict[str, Any]:
        samples = {}
        for _doc_id, body in docs:
            for key, value in body.items():
                if key not in samples and value is not None:
                    samples[key] = value
        return samples

    def _ensure_bulk_dynamic_columns(
        self,
        validated_index: str,
        docs: List[Tuple[str, Dict[str, Any]]],
        cursor=None
    ) -> None:
        if not getattr(self, 'enable_dynamic_inference', False):
            return

        dynamic_conn = cursor.conn if cursor is not None and hasattr(cursor, 'conn') else None
        for field_name, sample_value in self._collect_bulk_field_samples(docs).items():
            validated_column = normalize_identifier(field_name, "Dynamic column")
            if self._check_column_exists(validated_index, validated_column, connection=dynamic_conn):
                continue
            column_type = infer_column_type_from_value(sample_value, field_name)
            self._add_column(validated_index, validated_column, column_type, connection=dynamic_conn)

    @staticmethod
    def _prepare_bulk_insert_values(docs: List[Tuple[str, Dict[str, Any]]]):
        all_fields = set()
        for _doc_id, body in docs:
            all_fields.update(body.keys())

        sorted_fields = sorted(all_fields)
        columns = ['id'] + sorted_fields
        values_list = []
        for doc_id, body in docs:
            row = [doc_id]
            for key in sorted_fields:
                row.append(body.get(key))
            values_list.append(tuple(row))
        return columns, values_list

    def _execute_bulk_insert_values(
        self,
        validated_index: str,
        columns: List[str],
        values_list,
        batch_size: int,
        cursor=None
    ) -> None:
        from psycopg2.extras import execute_values

        columns_sql = ', '.join([col for col in columns])
        insert_query = f'INSERT INTO "{validated_index}" ({columns_sql}) VALUES %s'
        if cursor is not None:
            execute_values(cursor, insert_query, values_list, page_size=batch_size)
            return

        with self.connection.get_connection_for_operation() as conn:
            local_cursor = conn.cursor()
            try:
                execute_values(local_cursor, insert_query, values_list, page_size=batch_size)
                conn.commit()
            finally:
                local_cursor.close()

    def _bulk_insert_strict(self, index: str, docs: List[Tuple[str, Dict[str, Any]]], cursor=None) -> None:
        """
        使用批量 INSERT 语句严格插入所有文档

        :param index: 索引名称（表名）
        :param docs: 文档列表 [(id, body), ...]
        :param cursor: 可选的 cursor 对象，如果提供则复用，否则创建新的
        """
        if not docs:
            return

        validated_index = normalize_identifier(index, "Index name")
        self._ensure_bulk_dynamic_columns(validated_index, docs, cursor=cursor)
        columns, values_list = self._prepare_bulk_insert_values(docs)
        batch_size = getattr(self, 'bulk_batch_size', 100)
        self._execute_bulk_insert_values(
            validated_index,
            columns,
            values_list,
            batch_size,
            cursor=cursor
        )

    def _process_body_fields(self, body: Dict[str, Any], index: str = None) -> Dict[str, Any]:
        """
        处理 body 中的字段，转换复杂类型为 JSON 字符串格式

        :param body: 原始文档内容
        :param index: 索引名称（用于获取 mapping 信息）
        :return: 处理后的文档内容（字段名已标准化）
        """
        # [OK] 委托给子模块中的实现
        return _process_body_fields_impl(body, index, self._get_mapping)


__all__ = ['DocumentOpsMixin']
