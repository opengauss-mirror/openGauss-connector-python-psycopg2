import copy
import json
import re
from typing import Any, Dict

import psycopg2
from psycopg2 import sql

from opensearch_sdk.client.doc_utils.type_inference import infer_column_type_from_value
from opensearch_sdk.client.doc_utils.helpers import (
    with_sql_trace,
    handle_document_exception,
    validate_index,
    validate_document_params,
    prepare_document,
    build_insert_sql,
    build_update_sql,
)
from opensearch_sdk.client.doc_utils.nested_handler import (
    _flatten_nested_document,
    _reconstruct_nested_structure,
)
from opensearch_sdk.client.utils import normalize_identifier


class DocumentOperationsMixin:
    """
    文档操作实现 Mixin

    提供所有文档操作的底层实现方法（_impl）
    这些方法被装饰器包装以支持 SQL 追踪和异常处理
    """

    @with_sql_trace("create")
    @handle_document_exception("Create Document")
    def _create_impl(self, index: str, doc_id: str, body: Dict[str, Any], refresh: bool = False, cursor=None) -> Any:
        """
        创建文档的实现

        :param index: 索引名称
        :param doc_id: 文档 ID
        :param body: 文档内容
        :param refresh: 是否刷新（Opensearch 中忽略）
        :param cursor: 可选的 cursor 对象，如果提供则复用（用于 bulk 操作）
        :return: 操作结果
        """
        # 参数验证（使用通用函数，避免重复检查）
        validated_index, doc_id, validated_body = validate_document_params(index, doc_id, body)
        # [OK] 统一处理文档预处理（nested扁平化 + 字段标准化 + 类型转换）
        processed_body = prepare_document(
            body=validated_body,
            index=index,
            get_mapping_func=self._get_mapping,
            has_nested_check_func=self._has_nested_fields,
            process_body_func=self._process_body_fields,
            flatten_nested_func=_flatten_nested_document
        )

        # [OK] 使用通用SQL构建函数
        sql_query, values = build_insert_sql(validated_index, doc_id, processed_body)

        # [OK] 如果传入了 cursor，则复用；否则使用新的连接
        if cursor is not None:
            # 复用传入的 cursor（用于事务化 bulk）
            cursor.execute(sql_query, values)
            # 不 commit，由调用者决定
        else:
            # 使用新的连接管理模式
            with self.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(sql_query, values)
                    conn.commit()
                finally:
                    cursor.close()

        return {
            "result": "created",
            "_id": doc_id,
            "_index": validated_index
        }

    @staticmethod
    def _updated_result(validated_index: str, doc_id: str) -> Dict[str, Any]:
        return {
            "result": "updated",
            "_id": doc_id,
            "_index": validated_index
        }

    @staticmethod
    def _not_found_result(validated_index: str, doc_id: str) -> Dict[str, Any]:
        return {
            "_index": validated_index,
            "_id": doc_id,
            "found": False
        }

    @staticmethod
    def _found_result(validated_index: str, doc_id: str, source: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "_index": validated_index,
            "_id": doc_id,
            "_source": source,
            "found": True
        }

    @staticmethod
    def _raise_document_not_found(doc_id: str) -> None:
        raise Exception(f"Document with id '{doc_id}' not found (404 Not Found)")

    def _execute_update_statement(self, update_sql, values, validated_index: str, doc_id: str, cursor=None) -> Any:
        if cursor is not None:
            cursor.execute(update_sql, values)
            if cursor.rowcount <= 0:
                DocumentOperationsMixin._raise_document_not_found(doc_id)
            return DocumentOperationsMixin._updated_result(validated_index, doc_id)

        return self._execute_update_statement_with_connection(update_sql, values, validated_index, doc_id)

    def _execute_update_statement_with_connection(
        self,
        update_sql,
        values,
        validated_index: str,
        doc_id: str
    ) -> Any:
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(update_sql, values)
                if cursor.rowcount <= 0:
                    conn.rollback()
                    DocumentOperationsMixin._raise_document_not_found(doc_id)
                conn.commit()
                return DocumentOperationsMixin._updated_result(validated_index, doc_id)
            finally:
                cursor.close()

    @staticmethod
    def _decode_document_value(value):
        if not isinstance(value, str):
            return value

        if value.startswith(('{', '[')):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        if ',' not in value or value.startswith(' '):
            return value

        parts = value.split(',')
        if len(parts) > 1 and all(part.strip() for part in parts):
            return parts
        return value

    @staticmethod
    def _decode_document_row(row, description) -> Dict[str, Any]:
        column_names = [desc[0] for desc in description]
        result = dict(zip(column_names, row))
        return {
            key: DocumentOperationsMixin._decode_document_value(value)
            for key, value in result.items()
        }

    @with_sql_trace("update")
    def _update_impl(self, index: str, doc_id: str, body: Dict[str, Any], refresh: bool = False, cursor=None) -> Any:
        """
        更新文档的实现

        :param index: 索引名称
        :param doc_id: 文档 ID
        :param body: 要更新的字段
        :param refresh: 是否刷新（Opensearch 中忽略）
        :param cursor: 可选的 cursor 对象，如果提供则复用（用于 bulk 操作）
        :return: 操作结果
        """
        # 参数验证
        validated_index, doc_id, validated_body = validate_document_params(index, doc_id, body)
        # [OK] 兼容 OpenSearch 的 {"doc": {...}} 格式
        update_fields = validated_body.get('doc', validated_body)

        # [OK] 统一处理文档预处理（nested扁平化 + 字段标准化 + 类型转换）
        processed_body = prepare_document(
            body=update_fields,
            index=index,
            get_mapping_func=self._get_mapping,
            has_nested_check_func=self._has_nested_fields,
            process_body_func=self._process_body_fields,
            flatten_nested_func=_flatten_nested_document
        )

        # [OK] 使用通用SQL构建函数
        update_sql, values = build_update_sql(validated_index, doc_id, processed_body)

        return self._execute_update_statement(update_sql, values, validated_index, doc_id, cursor)

    @with_sql_trace("get")
    def _get_impl(self, index: str, doc_id: str) -> Any:
        """
        获取文档的实现

        :param index: 索引名称
        :param doc_id: 文档 ID
        :return: 文档内容
        """
        # 参数验证（使用通用函数，自动转换 ID 类型）
        validated_index, doc_id, _ = validate_document_params(index, doc_id)
        sql_query = sql.SQL("SELECT * FROM {} WHERE id = %s").format(
            sql.Identifier(validated_index)
        )

        # [OK] 使用新的连接管理模式
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql_query, (doc_id,))
                row = cursor.fetchone()

                if row is None:
                    # OpenSearch 兼容：文档不存在时返回 found=False，而不是抛出异常
                    return DocumentOperationsMixin._not_found_result(validated_index, doc_id)

                result = DocumentOperationsMixin._decode_document_row(row, cursor.description)
                # [OK] 将扁平化的 nested 字段还原为嵌套结构
                result = _reconstruct_nested_structure(result)

                # OpenSearch 兼容：添加 found 字段
                return DocumentOperationsMixin._found_result(validated_index, doc_id, result)
            finally:
                cursor.close()

    @with_sql_trace("delete")
    @handle_document_exception("Delete Document")
    def _delete_impl(self, index: str, doc_id: str, refresh: bool = False) -> Any:
        """
        删除文档的实现

        :param index: 索引名称
        :param doc_id: 文档 ID
        :param refresh: 是否刷新（Opensearch 中忽略）
        :return: 操作结果
        """
        # 参数验证（使用通用函数，自动转换 ID 类型）
        validated_index, doc_id, _ = validate_document_params(index, doc_id)
        sql_query = sql.SQL("DELETE FROM {} WHERE id = %s").format(
            sql.Identifier(validated_index)
        )

        # [OK] 使用新的连接管理模式
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql_query, (doc_id,))
                # DML 操作需要提交
                conn.commit()

                if cursor.rowcount > 0:
                    return {
                        "result": "deleted",
                        "_id": doc_id,
                        "_index": validated_index
                    }
                else:
                    raise Exception(f"Document with id '{doc_id}' not found in index '{validated_index}'")
            finally:
                cursor.close()

    @staticmethod
    def _index_body_needs_flatten(body: Dict[str, Any]) -> bool:
        return any(isinstance(value, (dict, list)) for value in body.values())

    @staticmethod
    def _prepare_index_body(body: Dict[str, Any], validated_index: str, process_body_func) -> tuple:
        prepared_body = body
        if DocumentOperationsMixin._index_body_needs_flatten(body):
            prepared_body = _flatten_nested_document(copy.deepcopy(body), None)

        processed_body = process_body_func(copy.deepcopy(prepared_body), validated_index)
        return prepared_body, processed_body

    @staticmethod
    def _rollback_safely(conn) -> None:
        try:
            conn.rollback()
        except Exception:
            pass

    @staticmethod
    def _is_duplicate_insert_error(error: Exception) -> bool:
        error_msg = str(error).lower()
        return "duplicate" in error_msg or "unique" in error_msg or "already exists" in error_msg

    @staticmethod
    def _execute_update_after_duplicate(
        cursor,
        conn,
        validated_index: str,
        doc_id: str,
        processed_body: Dict[str, Any]
    ) -> Any:
        DocumentOperationsMixin._rollback_safely(conn)
        return DocumentOperationsMixin._execute_update_or_return(
            cursor,
            conn,
            validated_index,
            doc_id,
            processed_body
        )

    def _execute_insert_or_update_with_cursor(
        self,
        cursor,
        conn,
        validated_index: str,
        doc_id: str,
        processed_body: Dict[str, Any]
    ) -> Any:
        try:
            return self._execute_insert_with_cursor(cursor, conn, validated_index, doc_id, processed_body)
        except psycopg2.errors.UniqueViolation:
            return DocumentOperationsMixin._execute_update_after_duplicate(
                cursor,
                conn,
                validated_index,
                doc_id,
                processed_body
            )
        except Exception as insert_error:
            if DocumentOperationsMixin._is_duplicate_insert_error(insert_error):
                return DocumentOperationsMixin._execute_update_after_duplicate(
                    cursor,
                    conn,
                    validated_index,
                    doc_id,
                    processed_body
                )
            raise

    @staticmethod
    def _raise_index_error(message: str, index: str, doc_id: str, error: Exception) -> None:
        raise Exception(f"##OS## - {message} | index={index} | id={doc_id} | error: {str(error)}")

    def _execute_index_with_cursor(
        self,
        conn,
        cursor,
        index: str,
        validated_index: str,
        doc_id: str,
        body: Dict[str, Any],
        processed_body: Dict[str, Any]
    ) -> Any:
        try:
            return self._execute_insert_or_update_with_cursor(
                cursor,
                conn,
                validated_index,
                doc_id,
                processed_body
            )
        except psycopg2.errors.UndefinedColumn as e:
            DocumentOperationsMixin._rollback_safely(conn)
            return self._handle_all_undefined_columns_with_cursor(conn, index, doc_id, body, processed_body, e)
        except psycopg2.errors.UniqueViolation as e:
            DocumentOperationsMixin._rollback_safely(conn)
            DocumentOperationsMixin._raise_index_error("Document already exists", index, doc_id, e)
        except psycopg2.errors.SyntaxError as e:
            DocumentOperationsMixin._rollback_safely(conn)
            DocumentOperationsMixin._raise_index_error("SQL syntax error", index, doc_id, e)
        except psycopg2.errors.DataError as e:
            DocumentOperationsMixin._rollback_safely(conn)
            DocumentOperationsMixin._raise_index_error("Data type error", index, doc_id, e)
        except psycopg2.Error as e:
            DocumentOperationsMixin._rollback_safely(conn)
            DocumentOperationsMixin._raise_index_error("Database error", index, doc_id, e)
        except Exception as e:
            DocumentOperationsMixin._rollback_safely(conn)
            DocumentOperationsMixin._raise_index_error("Index Document Error", index, doc_id, e)

    def _index_impl(self, index: str, doc_id: str, body: Dict[str, Any], refresh: bool = False) -> Any:
        """
        插入或更新文档的实现（UPSERT 语义）

        :param index: 索引名称
        :param doc_id: 文档 ID
        :param body: 文档内容
        :param refresh: 是否刷新（Opensearch 中忽略）
        :return: 操作结果
        """
        # 参数验证（使用通用函数，自动转换 ID 类型）
        validated_index, doc_id, _ = validate_document_params(index, doc_id)
        body, processed_body = DocumentOperationsMixin._prepare_index_body(
            body,
            validated_index,
            self._process_body_fields
        )

        # [OK] 使用新的连接管理模式 - 为整个 index 操作获取一个连接
        with self.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                return self._execute_index_with_cursor(
                    conn,
                    cursor,
                    index,
                    validated_index,
                    doc_id,
                    body,
                    processed_body
                )
            finally:
                # 关闭 cursor（连接会在退出 with 块时自动归还）
                cursor.close()

    @staticmethod
    def _execute_insert_with_cursor(cursor, conn, validated_index: str, doc_id: str, processed_body: Dict[str, Any]) -> Any:
        """
        使用指定的 cursor 执行 INSERT 操作

        :param cursor: 已获取的 cursor（在整个业务操作中复用）
        :param conn: 数据库连接对象（用于提交事务）
        :param validated_index: 已验证的索引名
        :param doc_id: 文档 ID
        :param processed_body: 处理后的文档内容
        :return: 操作结果
        """
        sql_query, values = build_insert_sql(validated_index, doc_id, processed_body)

        # 使用传入的 cursor 执行 SQL
        cursor.execute(sql_query, values)

        # [FIX] 直接使用 conn.commit()，而不是 cursor.commit() 或 self.commit()
        conn.commit()

        return {
            "result": "created",
            "_id": doc_id,
            "_index": validated_index
        }

    @staticmethod
    def _execute_update_with_cursor(cursor, conn, validated_index: str, doc_id: str, processed_body: Dict[str, Any]) -> Any:
        """
        使用指定的 cursor 执行 UPDATE 操作

        :param cursor: 已获取的 cursor（在整个业务操作中复用）
        :param conn: 数据库连接对象（用于提交事务）
        :param validated_index: 已验证的索引名
        :param doc_id: 文档 ID
        :param processed_body: 处理后的文档内容
        :return: 操作结果
        """
        update_sql, values = build_update_sql(validated_index, doc_id, processed_body)

        # 使用传入的 cursor 执行 SQL
        cursor.execute(update_sql, values)

        # [FIX] 直接使用 conn.commit()
        conn.commit()

        return {
            "result": "updated",
            "_id": doc_id,
            "_index": validated_index
        }

    @staticmethod
    def _execute_update_or_return(cursor, conn, validated_index: str, doc_id: str, processed_body: Dict[str, Any]) -> Any:
        """
        执行 UPDATE 操作，如果 processed_body 为空则直接返回成功结果
        :param cursor: 数据库游标
        :param conn: 数据库连接
        :param validated_index: 已验证的索引名
        :param doc_id: 文档 ID
        :param processed_body: 处理后的文档内容
        :return: 操作结果
        """
        if not processed_body:
            return {
                "result": "updated",
                "_id": doc_id,
                "_index": validated_index
            }

        return DocumentOperationsMixin._execute_update_with_cursor(cursor, conn, validated_index, doc_id, processed_body)

    @staticmethod
    def _close_cursor_safely(cursor) -> None:
        try:
            cursor.close()
        except Exception:
            pass

    def _missing_columns_context(
        self,
        conn,
        index: str,
        doc_id: str,
        body: Dict[str, Any],
        processed_body: Dict[str, Any]
    ) -> tuple:
        mapping = self._get_mapping(index)
        validated_index = normalize_identifier(index, "Index name")
        existing_columns = DocumentOperationsMixin._get_existing_columns(validated_index, conn)
        missing_columns = self._find_missing_columns(
            processed_body,
            body,
            existing_columns,
            mapping,
            index,
            doc_id
        )
        return mapping, validated_index, missing_columns

    @staticmethod
    def _retry_insert_with_new_cursor(conn, validated_index: str, doc_id: str, processed_body: Dict[str, Any]) -> Any:
        new_cursor = conn.cursor()
        try:
            return DocumentOperationsMixin._execute_insert_with_cursor(
                new_cursor,
                conn,
                validated_index,
                doc_id,
                processed_body
            )
        finally:
            DocumentOperationsMixin._close_cursor_safely(new_cursor)

    def _infer_missing_column_type(
        self,
        field_name: str,
        body: Dict[str, Any],
        mapping: dict,
        index: str,
        doc_id: str
    ) -> str:
        column_type = self._infer_column_type(field_name, body, mapping)
        if column_type:
            return column_type

        raise Exception(
            f"##OS## - Missing Column in Mapping | index={index} | id={doc_id} | "
            f"column={field_name} | Please add the column to the mapping first."
        )

    def _add_missing_columns(
        self,
        conn,
        validated_index: str,
        missing_columns: list,
        body: Dict[str, Any],
        mapping: dict,
        index: str,
        doc_id: str
    ) -> dict:
        new_cursor = conn.cursor()
        column_types_cache = {}
        try:
            for field_name, validated_column in missing_columns:
                column_type = self._infer_missing_column_type(field_name, body, mapping, index, doc_id)
                column_types_cache[field_name] = column_type
                alter_sql = sql.SQL("ALTER TABLE {} ADD COLUMN {} {}").format(
                    sql.Identifier(validated_index),
                    sql.Identifier(validated_column),
                    sql.SQL(column_type)
                )
                new_cursor.execute(alter_sql)

            conn.commit()
            return column_types_cache
        finally:
            DocumentOperationsMixin._close_cursor_safely(new_cursor)

    def _create_indexes_for_missing_columns(
        self,
        conn,
        validated_index: str,
        missing_columns: list,
        column_types_cache: dict,
        body: Dict[str, Any]
    ) -> None:
        for field_name, _ in missing_columns:
            column_type = column_types_cache.get(field_name)
            if column_type:
                self._create_index_for_column(conn, validated_index, field_name, column_type, body)

    def _update_mapping_comment_safely(
        self,
        validated_index: str,
        missing_columns: list,
        column_types_cache: dict,
        body: Dict[str, Any]
    ) -> None:
        try:
            self._update_mapping_comment(validated_index, missing_columns, column_types_cache, body)
        except Exception as e:
            print(f"[WARN] 更新 mapping 注释失败: {e}")

    def _handle_all_undefined_columns_with_cursor(self, conn, index: str, doc_id: str, body: Dict[str, Any],
                                  processed_body: Dict[str, Any], error: Exception) -> Any:
        """
        处理所有 UndefinedColumn 错误，一次性添加所有缺失的列

        :param conn: 数据库连接对象（已 rollback，处于 READY 状态）
        :param index: 索引名称
        :param doc_id: 文档 ID
        :param body: 原始文档内容
        :param processed_body: 处理后的文档内容
        :param error: 异常对象
        :return: 操作结果
        """
        # [FIX] 关键优化：一次性检查并添加所有缺失的列
        # 而不是依赖 PostgreSQL 逐个报错
        try:
            mapping, validated_index, missing_columns = self._missing_columns_context(
                conn,
                index,
                doc_id,
                body,
                processed_body
            )
            if not missing_columns:
                return DocumentOperationsMixin._retry_insert_with_new_cursor(
                    conn,
                    validated_index,
                    doc_id,
                    processed_body
                )

            column_types_cache = self._add_missing_columns(
                conn,
                validated_index,
                missing_columns,
                body,
                mapping,
                index,
                doc_id
            )
            self._create_indexes_for_missing_columns(
                conn,
                validated_index,
                missing_columns,
                column_types_cache,
                body
            )
            self._update_mapping_comment_safely(validated_index, missing_columns, column_types_cache, body)
            return DocumentOperationsMixin._retry_insert_with_new_cursor(
                conn,
                validated_index,
                doc_id,
                processed_body
            )
        except Exception as e:
            DocumentOperationsMixin._rollback_safely(conn)
            raise Exception(f"##OS## - Failed to add columns | index={index} | error: {str(e)}")

    def _find_missing_columns(self, processed_body: Dict[str, Any], body: Dict[str, Any],
                              existing_columns: set, mapping: dict, index: str, doc_id: str) -> list:
        """
        找出所有真正缺失的列

        :return: [(field_name, validated_column), ...]
        """
        missing_columns = []
        for field_name in processed_body.keys():
            validated_column = normalize_identifier(field_name, "Column name")
            if validated_column not in existing_columns:
                if self._can_add_missing_column(mapping, field_name, body):
                    missing_columns.append((field_name, validated_column))
                else:
                    raise Exception(
                        f"##OS## - Missing Column in Mapping | index={index} | id={doc_id} | "
                        f"column={field_name} | Please add the column to the mapping first."
                    )

        return missing_columns

    def _can_add_missing_column(self, mapping: dict, field_name: str, body: Dict[str, Any]) -> bool:
        if not mapping or 'mappings' not in mapping:
            return True
        if self._infer_type_from_mapping(mapping, field_name):
            return True
        enable_dynamic_inference = getattr(self, 'enable_dynamic_inference', False)
        return enable_dynamic_inference and field_name in body

    def _infer_column_type(self, field_name: str, body: Dict[str, Any], mapping: dict) -> str:
        """
        推断列类型（优先从 mapping，其次动态推断）
        """
        column_type = None

        # 方案 A: 从 mapping 推断
        if mapping and 'mappings' in mapping:
            column_type = self._infer_type_from_mapping(mapping, field_name)

            # 智能数组识别
            if (field_name.endswith('list') or field_name.endswith('List')) and \
               field_name in body and isinstance(body[field_name], list):
                column_type = 'TEXT'
        # 方案 B: 动态推断
        if not column_type:
            enable_dynamic_inference = getattr(self, 'enable_dynamic_inference', False)
            if enable_dynamic_inference and field_name in body:
                sample_value = body[field_name]
                column_type = infer_column_type_from_value(sample_value, field_name)

        return column_type

    @staticmethod
    def _create_index_for_column(conn, validated_index: str, field_name: str,
                                 column_type: str, body: Dict[str, Any]):
        """
        为单个列创建索引
        """
        from opensearch_sdk.client.indices.sql_generator import generate_index_sql

        # 将数据库类型映射回 OpenSearch 类型
        es_type = DocumentOperationsMixin._reverse_map_db_type_to_es_type(column_type, field_name, body.get(field_name))

        if not es_type:
            return

        # 向量字段需要检查维度
        if es_type == 'dense_vector':
            sample_value = body.get(field_name)
            if not sample_value or not isinstance(sample_value, list) or len(sample_value) < 100:
                print(f"[WARN] 字段 '{field_name}' 维度不足，跳过向量索引创建")
                return

        # 生成并执行索引 SQL
        field_props = {'index': True}
        index_sql = generate_index_sql(validated_index, field_name, es_type, field_props)

        if index_sql:
            try:
                idx_cursor = conn.cursor()
                try:
                    idx_cursor.execute(index_sql)
                    conn.commit()
                    print(f"[OK] 为动态列 '{field_name}' ({column_type}) 创建索引成功")
                finally:
                    idx_cursor.close()
            except Exception as e:
                print(f"[WARN] 为动态列 '{field_name}' 创建索引失败: {e}")

    @staticmethod
    def _get_existing_columns(validated_index: str, conn) -> set:
        """
        获取表中已存在的列名集合

        :param validated_index: 已验证的索引名
        :param conn: 数据库连接
        :return: 列名集合
        """
        cursor = conn.cursor()
        try:
            # [FIX] 获取当前 schema，而不是硬编码 'public'
            cursor.execute("SELECT current_schema()")
            current_schema = cursor.fetchone()[0]

            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = %s
            """, (validated_index, current_schema))

            columns = {row[0] for row in cursor.fetchall()}
            return columns
        finally:
            cursor.close()

    @staticmethod
    def _infer_type_from_mapping(mapping: dict, column_name: str) -> str:
        """
        从 mapping 中推断列类型

        :param mapping: mapping 字典
        :param column_name: 列名（可能是扁平化的 nested 字段，如 documentList__name）
        :return: 数据库类型字符串
        """
        properties = mapping.get('mappings', {}).get('properties', {})
        nested_type = DocumentOperationsMixin._infer_nested_mapping_type(properties, column_name)
        if nested_type:
            return nested_type

        if column_name in properties:
            field_info = properties[column_name]
            return DocumentOperationsMixin._map_field_type(field_info)

        return DocumentOperationsMixin._infer_dynamic_template_type(mapping, column_name)

    @staticmethod
    def _infer_nested_mapping_type(properties: dict, column_name: str) -> str:
        from opensearch_sdk.client.constants import NESTED_FIELD_SEPARATOR

        if NESTED_FIELD_SEPARATOR not in column_name:
            return None

        parts = column_name.split(NESTED_FIELD_SEPARATOR)
        current_props = properties
        for i, part in enumerate(parts):
            if part not in current_props:
                return None
            field_info = current_props[part]
            if i == len(parts) - 1:
                return DocumentOperationsMixin._map_field_type(field_info)
            if field_info.get('type') != 'nested':
                return None
            current_props = field_info.get('properties', {})
        return None

    @staticmethod
    def _infer_dynamic_template_type(mapping: dict, column_name: str) -> str:
        for template_config in DocumentOperationsMixin._iter_dynamic_template_configs(mapping):
            column_type = DocumentOperationsMixin._match_dynamic_template_type(template_config, column_name)
            if column_type:
                return column_type
        return None

    @staticmethod
    def _iter_dynamic_template_configs(mapping: dict):
        dynamic_templates = mapping.get('mappings', {}).get('dynamic_templates', [])
        for template_item in dynamic_templates:
            for template_config in template_item.values():
                yield template_config

    @staticmethod
    def _match_dynamic_template_type(template_config: dict, column_name: str) -> str:
        match_pattern = template_config.get('match', '')
        if not match_pattern:
            return None

        regex_pattern = '^' + match_pattern.replace('*', '.*') + '$'
        if not re.match(regex_pattern, column_name):
            return None

        template_mapping = template_config.get('mapping', {})
        return DocumentOperationsMixin._map_field_type(template_mapping)

    @staticmethod
    def _map_field_type(field_info: dict) -> str:
        """
        将 Elasticsearch 字段类型映射到数据库类型

        :param field_info: 字段信息
        :return: 数据库类型字符串
        """
        field_type = field_info.get('type', 'text')

        type_mapping = {
            'text': 'TEXT',
            'keyword': 'VARCHAR',
            'long': 'BIGINT',
            'integer': 'INTEGER',
            'float': 'FLOAT4',
            'double': 'FLOAT8',
            'boolean': 'BOOLEAN',
            'date': 'TIMESTAMP',
            'dense_vector': 'VECTOR',
            'float_vector': 'VECTOR',
            'knn_vector': 'VECTOR'
        }

        column_type = type_mapping.get(field_type, 'TEXT')

        # 如果是 vector 类型，检查是否有 dims/dimension
        if 'vector' in field_type.lower():
            dims = field_info.get('dims', field_info.get('dimension'))
            if dims:
                column_type = f'VECTOR({dims})'

        return column_type

    @staticmethod
    def _reverse_map_db_type_to_es_type(db_type: str, field_name: str = None, sample_value=None) -> str:
        """
        将数据库类型反向映射为 OpenSearch 类型

        :param db_type: 数据库类型（如 BIGINT, TEXT, BOOLEAN）
        :param field_name: 字段名（用于判断数组类型）
        :param sample_value: 样本值（用于判断 vector）
        :return: OpenSearch 类型（如 long, text, boolean），如果无法映射返回 None
        """
        if not db_type:
            return None

        db_type_upper = db_type.upper()

        # 检查是否为向量类型
        if db_type_upper.startswith('VECTOR'):
            return 'dense_vector'

        # 检查是否为数组类型（以 list 结尾）
        if field_name and (field_name.endswith('list') or field_name.endswith('List')):
            return 'text'  # 数组字段存储为 TEXT（JSON序列化）

        # 标准类型映射
        type_map = {
            'BIGINT': 'long',
            'INTEGER': 'integer',
            'SHORTINT': 'short',
            'TINYINT': 'byte',
            'FLOAT4': 'float',
            'FLOAT8': 'double',
            'BOOLEAN': 'boolean',
            'TIMESTAMP': 'date',
            'TEXT': 'text',
            'VARCHAR': 'text',
            'CHARACTER VARYING': 'text',
            # JSONB 不创建索引，返回 None
            'JSONB': None,
        }

        return type_map.get(db_type_upper, 'text')

    def _update_mapping_comment(self, validated_index: str, missing_columns: list, column_types_cache: dict, body: dict):
        """
        更新 mapping 到 opensearch_mapping 表，将新列添加到 mapping

        :param validated_index: 表名
        :param missing_columns: 新添加的列列表 [(field_name, validated_column), ...]
        :param column_types_cache: 列类型缓存 {field_name: column_type}
        :param body: 文档数据
        """
        import json as json_module
        from opensearch_sdk.client.doc_utils.mapping_storage import load_mapping_from_table, save_mapping_to_table

        # 获取当前 schema
        current_schema = self.connection.get_current_schema()

        # 从独立表加载现有的 mapping
        existing_mapping = load_mapping_from_table(self.connection, validated_index, current_schema)

        if not existing_mapping:
            # 如果没有现有 mapping，创建一个新的
            existing_mapping = {'properties': {}}

        # 添加新列到 mapping
        for field_name, validated_column in missing_columns:
            column_type = column_types_cache.get(field_name, 'TEXT')

            # 将数据库类型映射回 OpenSearch 类型
            es_type = DocumentOperationsMixin._reverse_map_db_type_to_es_type(column_type, field_name, body.get(field_name))
            if es_type:
                field_props = {
                    'type': es_type,
                    'index': True  # 关键：设置 index: true
                }
                existing_mapping['properties'][field_name] = field_props

        # 保存到 opensearch_mapping 表
        save_mapping_to_table(self.connection, validated_index, current_schema, existing_mapping)
        print(f"[OK] 已更新 {len(missing_columns)} 个新列的 mapping")


    def _check_column_exists(self, index: str, column_name: str, connection=None) -> bool:
        """
        检查列是否存在

        :param index: 索引名称
        :param column_name: 列名
        :param connection: 可选的连接对象，如果提供则复用
        :return: 是否存在
        """
        try:
            check_sql = sql.SQL(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s"
            )

            if connection is not None:
                return self._check_column_with_connection(connection, check_sql, index, column_name)
            with self.connection.get_connection_for_operation() as conn:
                return self._check_column_with_connection(conn, check_sql, index, column_name)
        except Exception:
            return False

    @staticmethod
    def _check_column_with_connection(connection, check_sql, index: str, column_name: str) -> bool:
        cursor = connection.cursor()
        try:
            cursor.execute(check_sql, (index, column_name))
            return cursor.fetchone()[0] > 0
        finally:
            cursor.close()

    def _add_column(self, index: str, column_name: str, column_type: str, connection=None):
        """
        动态添加列

        :param index: 索引名称
        :param column_name: 列名
        :param column_type: 列类型
        :param connection: 可选的连接对象，如果提供则复用
        """
        add_column_sql = sql.SQL("ALTER TABLE {} ADD COLUMN {}").format(
            sql.Identifier(index),
            sql.SQL("{} {}").format(sql.Identifier(column_name), sql.SQL(column_type))
        )

        # [OK] 如果传入了 connection，则复用；否则使用新的连接
        if connection is not None:
            # 复用传入的连接
            cursor = connection.cursor()
            try:
                cursor.execute(add_column_sql)
                connection.commit()
            finally:
                cursor.close()
        else:
            # [OK] 使用新的连接管理模式
            with self.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(add_column_sql)
                    conn.commit()
                finally:
                    cursor.close()
        # 为 TEXT 类型的字段创建 BM25 索引（排除 vector 类型）
        if column_type.upper() in ['TEXT', 'VARCHAR', 'CHARACTER VARYING'] and not column_type.upper().startswith('VECTOR'):
            try:
                bm25_index_name = f"{index}_{column_name}_bm25_idx"
                # Opensearch/OpenGauss BM25 索引不支持 WITH 选项
                create_bm25_sql = sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {} ON {} USING bm25 ({})"
                ).format(
                    sql.Identifier(bm25_index_name),
                    sql.Identifier(index),
                    sql.Identifier(column_name)
                )
                idx_cursor = conn.execute(create_bm25_sql)

                # [FIX] 只有我们自己创建的 cursor 才需要 commit 和 close
                if connection is None:
                    conn.commit()  # 直接使用 conn.commit()
                    idx_cursor.close()

                # 注意：BM25 索引不需要 ANALYZE，倒排索引在 CREATE INDEX 时已构建完成
                # ANALYZE 仅用于收集表级别统计信息（优化常规 SQL 查询），与 BM25 功能无关
                # 如需优化其他查询性能，可手动执行: ANALYZE table_name;
            except Exception as e:
                print(f"[WARN] 创建 BM25 索引失败: {e}")

    def _execute_insert_with_normalized_fields(self, validated_index: str, doc_id: str,
                                                processed_body: Dict[str, Any]) -> Any:
        """
        使用标准化后的字段名执行 INSERT 操作

        :param validated_index: 已验证的索引名
        :param doc_id: 文档 ID
        :param processed_body: 已处理的文档内容（字段名已标准化）
        :return: 操作结果
        """
        return self._execute_insert(validated_index, doc_id, processed_body)
