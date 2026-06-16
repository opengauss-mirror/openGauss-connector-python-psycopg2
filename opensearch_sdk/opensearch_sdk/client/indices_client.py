# SPDX-License-Identifier: Apache-2.0
#
# This file contains code derived from opensearch-py.
# Original source: https://github.com/opensearch-project/opensearch-py
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
#
# Modifications Copyright OpenSearch Contributors. See
# GitHub history for details.
#
# Modifications Copyright 2026 openGauss Contributors
#
#  Licensed to Elasticsearch B.V. under one or more contributor
#  license agreements. See the NOTICE file distributed with
#  this work for additional information regarding copyright
#  ownership. Elasticsearch B.V. licenses this file to you under
#  the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
# 	http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an
#  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  KIND, either express or implied.  See the License for the
#  specific language governing permissions and limitations
#  under the License.

from typing import Any

from psycopg2 import sql

from opensearch_sdk.client.utils import (
    SKIP_IN_PATH,
    NamespacedClient,
    _make_path,
    query_params,
    normalize_identifier,
)
from opensearch_sdk.client.constants import (
    DEFAULT_DISTRIBUTED,
    DEFAULT_DISTRIBUTION_COLUMN,
    DEFAULT_SHARD_COUNT
)
import opensearch_sdk.client.indices.operations as index_operations
import opensearch_sdk.client.indices.sql_generator as index_sql_generator


class IndicesClient(NamespacedClient):
    @staticmethod
    def _build_stats_bucket(row_count: int, total_size_bytes: int) -> dict:
        return {
            "docs": {
                "count": row_count,
                "deleted": 0
            },
            "store": {
                "size_in_bytes": total_size_bytes
            }
        }

    @staticmethod
    def _create_options(distributed: bool, distribution_column: str, shard_count: int) -> dict:
        return {
            "distributed": distributed,
            "distribution_column": distribution_column,
            "shard_count": shard_count,
        }

    @query_params("error_trace", "filter_path", "human", "pretty", "source")
    def create(
        self,
        index: Any = None,
        body: Any = None,
        params: Any = None,
        headers: Any = None,
        distributed: bool = DEFAULT_DISTRIBUTED,
        distribution_column: str = DEFAULT_DISTRIBUTION_COLUMN,
        shard_count: int = DEFAULT_SHARD_COUNT,
        **kwargs: Any
    ) -> Any:
        """
        Creates a vector index with optional settings.
        
        OpenGauss 索引策略说明：
        - text 类型：BM25 全文索引，支持关键词搜索
        - keyword 类型：B-tree 索引，支持精确匹配和范围查询
        - long/integer 类型：B-tree 索引，支持数值范围查询
        - float 类型：B-tree 索引，支持浮点数范围查询
        - date 类型：B-tree 索引，支持时间范围查询
        - boolean 类型：B-tree 索引，支持布尔值查询
        - float_vector/dense_vector 类型：HNSW 索引，支持高维向量相似度搜索

        :arg index: Name of the index to create.
        :arg body: The configuration for the index (settings and mappings)
        :arg distributed: Whether to create as distributed table (default: False)
        :arg distribution_column: Distribution column for hash partitioning (default: 'id')
        :arg shard_count: Number of shards for distributed table (default: 6)
        :arg error_trace: Whether to include the stack trace of returned
            errors. Default is false.
        :arg filter_path: Used to reduce the response. This parameter
            takes a comma-separated list of filters. It supports using wildcards to
            match any field or part of a field's name. You can also exclude fields
            with "-".
        :arg human: Whether to return human readable values for
            statistics. Default is True.
        :arg pretty: Whether to pretty format the returned JSON
            response. Default is false.
        :arg source: The URL-encoded request definition. Useful for
            libraries that do not accept a request body for non-POST requests.
        """
        # 使用 SQL 追踪上下文包装（如果启用了追踪）
        create_options = self._create_options(distributed, distribution_column, shard_count)
        if hasattr(self.client, 'sql_tracer') and self.client.sql_tracer and self.client.sql_tracer.enabled:
            return self._create_with_trace(
                index, body, params, headers,
                create_options=create_options,
                **kwargs
            )
        return self._create_impl(
            index, body, params, headers,
            create_options=create_options,
            **kwargs
        )
    
    def _create_with_trace(
        self, index: Any = None, body: Any = None, params: Any = None,
        headers: Any = None, create_options: Any = None,
        **kwargs: Any
    ) -> Any:
        """
        带 SQL 追踪的 indices.create 实现
        
        :param index: 索引名称
        :param body: 索引配置
        :param distributed: 是否创建分布式表
        :param distribution_column: 分布列
        :param shard_count: 分片数
        :param params: 查询参数
        :param headers: 请求头
        :return: 操作结果
        """
        create_options = create_options or self._create_options(
            DEFAULT_DISTRIBUTED,
            DEFAULT_DISTRIBUTION_COLUMN,
            DEFAULT_SHARD_COUNT
        )
        with self.client.sql_tracer.trace_session("indices_create", index) as session:
            result = self._create_impl(
                index, body, params, headers,
                create_options=create_options,
                **kwargs
            )
            
            # [FIX] 手动创建 SQL 记录（因为 _create_impl 中有多个 SQL 执行）
            if session:
                from opensearch_sdk.client.sql_tracer.record import SQLTraceRecord
                import time
                
                # 创建一个简化的 SQL 记录
                record = SQLTraceRecord(
                    sql=f"CREATE TABLE {index} (模拟SQL)",
                    params=None,
                    start_time=time.time(),
                    context=f"indices_create_{index}"
                )
                record.end_time = time.time()
                record.duration_ms = 0
                record.result_count = 1
                
                # 设置 metadata
                record.metadata['index_name'] = index
                record.metadata['distributed'] = create_options["distributed"]
                if body:
                    record.metadata['field_count'] = len(body.get('mappings', {}).get('properties', {}))
                
                session.add_record(record)
            
            return result

    @staticmethod
    def _execute_and_commit(conn, statement) -> None:
        cursor = conn.cursor()
        try:
            cursor.execute(statement)
            conn.commit()
        finally:
            cursor.close()

    def _rollback_created_index(self, validated_index: str) -> None:
        try:
            self.delete(index=validated_index)
        except Exception as delete_error:
            print(f"[WARN] 回滚删除表失败：{delete_error}")

    def _convert_created_table_if_needed(
        self,
        validated_index: str,
        distributed: bool,
        distribution_column: str,
        shard_count: int
    ) -> None:
        if not distributed:
            return

        try:
            self._convert_to_distributed(validated_index, distribution_column, shard_count)
        except Exception as dist_error:
            self._rollback_created_index(validated_index)
            raise Exception(f"创建分布式表失败，已回滚: {dist_error}") from dist_error

    def _execute_create_table(
        self,
        conn,
        sql_query,
        validated_index: str,
        distributed: bool,
        distribution_column: str,
        shard_count: int
    ) -> None:
        self._execute_and_commit(conn, sql_query)
        self._convert_created_table_if_needed(
            validated_index,
            distributed,
            distribution_column,
            shard_count
        )

    def _create_field_indexes(self, conn, validated_index: str, fields_to_index) -> None:
        for field_name, field_type, field_props in fields_to_index:
            index_sql = index_sql_generator.generate_index_sql(
                validated_index,
                field_name,
                field_type,
                field_props
            )
            if index_sql:
                self._execute_and_commit(conn, index_sql)

    def _apply_bm25_config(self, conn, bm25_config) -> None:
        if not bm25_config:
            return

        try:
            for set_sql in index_sql_generator.generate_bm25_set_sql(bm25_config):
                self._execute_and_commit(conn, set_sql)
        except Exception as error:
            print(f"[WARN] Failed to apply BM25 config: {error}")

    def _save_mapping_metadata(self, conn, validated_index: str, body: Any) -> None:
        try:
            from opensearch_sdk.client.doc_utils.mapping_storage import save_mapping_to_table

            mappings = body.get('mappings', {})
            mapping_data = {
                'properties': mappings.get('properties', {}),
                'dynamic_templates': mappings.get('dynamic_templates', [])
            }
            if hasattr(conn, 'get_current_schema'):
                current_schema = conn.get_current_schema()
            else:
                current_schema = self.client.connection.get_current_schema()
            save_mapping_to_table(self.client.connection, validated_index, current_schema, mapping_data)
        except Exception as error:
            print(f"[WARN] 存储 mapping 到表失败：{error}")

    @staticmethod
    def _raise_create_error(validated_index: str, error: Exception, default_index: bool = False) -> None:
        error_msg_lower = str(error).lower()
        if "already exists" in error_msg_lower or "duplicate" in error_msg_lower:
            raise Exception(
                f"resource_already_exists_exception: "
                f"index [{validated_index}] already exists"
            ) from error

        if default_index:
            message = f"Failed to create default index '{validated_index}': {str(error)}"
        else:
            message = f"Failed to create index '{validated_index}': {str(error)}"
        raise Exception(message) from error

    def _create_from_body(
        self,
        validated_index: str,
        body: Any,
        distributed: bool,
        distribution_column: str,
        shard_count: int
    ) -> Any:
        sql_query, fields_to_index, bm25_config = index_sql_generator.generate_create_table_sql(
            validated_index,
            body
        )
        try:
            with self.client.connection.get_connection_for_operation() as conn:
                self._execute_create_table(conn, sql_query, validated_index,
                    distributed, distribution_column, shard_count)
                self._create_field_indexes(conn, validated_index, fields_to_index)
                self._apply_bm25_config(conn, bm25_config)
                self._save_mapping_metadata(conn, validated_index, body)
                return {"acknowledged": True}
        except Exception as error:
            self._raise_create_error(validated_index, error)

    def _create_default_index(
        self,
        validated_index: str,
        distributed: bool,
        distribution_column: str,
        shard_count: int
    ) -> Any:
        sql_query = sql.SQL("CREATE TABLE {} (id VARCHAR PRIMARY KEY)").format(
            sql.Identifier(validated_index)
        )
        try:
            with self.client.connection.get_connection_for_operation() as conn:
                self._execute_create_table(conn, sql_query, validated_index,
                    distributed, distribution_column, shard_count)
            return {"acknowledged": True}
        except Exception as error:
            self._raise_create_error(validated_index, error, default_index=True)
    
    def _create_impl(
        self,
        index: Any = None,
        body: Any = None,
        params: Any = None,
        headers: Any = None,
        create_options: Any = None,
        **kwargs: Any
    ) -> Any:
        if index in SKIP_IN_PATH:
            raise ValueError("Empty value passed for a required argument 'index'.")

        create_options = create_options or self._create_options(
            DEFAULT_DISTRIBUTED,
            DEFAULT_DISTRIBUTION_COLUMN,
            DEFAULT_SHARD_COUNT
        )
        validated_index = normalize_identifier(index, "Index name")
        if body:
            return self._create_from_body(
                validated_index,
                body,
                create_options["distributed"],
                create_options["distribution_column"],
                create_options["shard_count"]
            )
        return self._create_default_index(
            validated_index,
            create_options["distributed"],
            create_options["distribution_column"],
            create_options["shard_count"]
        )
    
    def _convert_to_distributed(
        self,
        index: str,
        distribution_column: str,
        shard_count: int
    ) -> None:
        """
        将普通表转换为分布式表
        
        :param index: 表名
        :param distribution_column: 分布列名称
        :param shard_count: 分片数量
        :raises Exception: 如果转换失败
        """
        # 构建 SQL
        sql_template = "SELECT create_distributed_table(%s, %s"
        params = [index, distribution_column]
        
        if shard_count is not None:
            sql_template += ", shard_count:=%s)"
            params.append(shard_count)
        else:
            sql_template += ")"
        
        # 执行转换
        try:
            with self.client.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                cursor.execute(sql_template, tuple(params))
                conn.commit()
                cursor.close()
        except Exception as e:
            # [FIX] 上下文管理器已自动 rollback，无需手动调用
            raise Exception(f"转换为分布式表失败: {e}") from e

    @query_params(
        "error_trace",
        "filter_path",
        "human",
        "pretty",
        "source",
    )
    def delete(
        self,
        index: Any = None,
        *,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        Deletes an index.


        :arg index: A comma-separated list of index names to delete.
        :arg error_trace: Whether to include the stack trace of returned
            errors. Default is false.
        :arg filter_path: Used to reduce the response. This parameter
            takes a comma-separated list of filters. It supports using wildcards to
            match any field or part of a field's name. You can also exclude fields
            with "-".
        :arg human: Whether to return human readable values for
            statistics. Default is True.
        :arg pretty: Whether to pretty format the returned JSON
            response. Default is false.
        :arg source: The URL-encoded request definition. Useful for
            libraries that do not accept a request body for non-POST requests.
        """
        # 使用 SQL 追踪上下文包装（如果启用了追踪）
        has_tracer = hasattr(self.client, 'sql_tracer')
        tracer_enabled = has_tracer and self.client.sql_tracer and self.client.sql_tracer.enabled
        
        if tracer_enabled:
            return self._delete_with_trace(index=index, params=params, headers=headers)
        else:
            # 未启用追踪，直接执行原有逻辑
            return self._delete_impl(index=index, params=params, headers=headers)
    
    def _delete_with_trace(
        self,
        index: Any = None,
        *,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        带 SQL 追踪的 indices.delete 实现
        
        :param index: 索引名称
        :param params: 查询参数
        :param headers: 请求头
        :return: 操作结果
        """
        with self.client.sql_tracer.trace_session("indices_delete", index) as session:
            result = self._delete_impl(index=index, params=params, headers=headers)
            
            # 记录操作信息
            if session and len(session.records) > 0:
                last_record = session.records[-1]
                last_record.metadata['index_name'] = index
                last_record.context = f"indices_delete_{index}"
            
            return result
    
    def _delete_impl(
        self,
        index: Any = None,
        *,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        return index_operations.execute_delete(self.client, index)

    def rebuild_index(
        self,
        index_name: str = None,
        table_name: str = None,
        column_name: str = None,
        index_type: str = "btree",
        auto_detect: bool = True,
        **kwargs
    ) -> dict:
        """
        重建数据库索引（先删除后重建）
        
        :arg index_name: 索引名称
        :arg table_name: 表名
        :arg column_name: 索引列名
        :arg index_type: 索引类型 (btree, gin, gist, hnsw, etc.)，默认 btree
        :arg auto_detect: 是否自动检测原索引类型（默认 True），如果检测到则使用原类型
        :arg kwargs: 其他参数
        :return: 重建结果字典
        """
        return index_operations.execute_rebuild_index(
            self.client, 
            index_name, 
            table_name, 
            column_name, 
            index_type,
            auto_detect,
            **kwargs
        )

    @query_params(
        "error_trace",
        "filter_path",
        "human",
        "pretty",
        "source",
    )
    def exists(
        self,
        index: Any = None,
        *,
        params: Any = None,
        headers: Any = None,
        connection: Any = None,
    ) -> bool:
        """
        Returns information about whether a particular index exists.


        :arg index: A comma-separated list of index names to check.
        :arg connection: Optional connection object to reuse (for transactional bulk)
        :arg error_trace: Whether to include the stack trace of returned
            errors. Default is false.
        :arg filter_path: Used to reduce the response. This parameter
            takes a comma-separated list of filters. It supports using wildcards to
            match any field or part of a field's name. You can also exclude fields
            with "-".
        :arg human: Whether to return human readable values for
            statistics. Default is True.
        :arg pretty: Whether to pretty format the returned JSON
            response. Default is false.
        :arg source: The URL-encoded request definition. Useful for
            libraries that do not accept a request body for non-POST requests.
        """
        if index in SKIP_IN_PATH:
            raise ValueError("Empty value passed for a required argument 'index'.")

        return index_operations.execute_exists(self.client, index, connection=connection)

    @query_params(
        "error_trace",
        "filter_path",
        "human",
        "pretty",
        "source",
    )
    def get(
        self,
        *,
        index: Any,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        Returns information about one or more indices.


        :arg index: A comma-separated list of index names.
        :arg error_trace: Whether to include the stack trace of returned
            errors. Default is false.
        :arg filter_path: Used to reduce the response. This parameter
            takes a comma-separated list of filters. It supports using wildcards to
            match any field or part of a field's name. You can also exclude fields
            with "-".
        :arg human: Whether to return human readable values for
            statistics. Default is True.
        :arg pretty: Whether to pretty format the returned JSON
            response. Default is false.
        :arg source: The URL-encoded request definition. Useful for
            libraries that do not accept a request body for non-POST requests.
        """
        if index in SKIP_IN_PATH:
            raise ValueError("Empty value passed for a required argument 'index'.")

        # Get table information from Opensearch
        # 动态获取当前 schema
        current_schema = self.client.connection.get_current_schema()
        
        sql_query = sql.SQL("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = %s AND table_schema = %s;
        """)
        validated_index = normalize_identifier(index, "Index name")
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql_query, (validated_index, current_schema))
                columns = cursor.fetchall()
            finally:
                cursor.close()

            if not columns:
                raise Exception(f"Index {validated_index} not found")

            mapping_from_comment = index_operations.execute_get_mapping_from_comment(
                self.client,
                validated_index
            )
            mappings = {"mappings": {"properties": {}}}
            if mapping_from_comment and 'properties' in mapping_from_comment:
                mappings = index_operations.build_mapping_from_comment(mapping_from_comment)
            else:
                mappings = index_operations.build_mapping_from_columns(columns)

            return {validated_index: mappings}

    @query_params(
        "error_trace",
        "filter_path",
        "human",
        "pretty",
        "source",
    )
    def put_mapping(
        self,
        *,
        index: Any,
        body: Any,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        Updates the index mappings.


        :arg index: A comma-separated list of index names. the mapping
            will be updated for each of them.
        :arg body: The mapping definition
        :arg error_trace: Whether to include the stack trace of returned
            errors. Default is false.
        :arg filter_path: Used to reduce the response. This parameter
            takes a comma-separated list of filters. It supports using wildcards to
            match any field or part of a field's name. You can also exclude fields
            with "-".
        :arg human: Whether to return human readable values for
            statistics. Default is True.
        :arg pretty: Whether to pretty format the returned JSON
            response. Default is false.
        :arg source: The URL-encoded request definition. Useful for
            libraries that do not accept a request body for non-POST requests.
        """
        for param in (index, body):
            if param in SKIP_IN_PATH:
                raise ValueError("Empty value passed for a required argument.")

        # In Opensearch, we would need to use ALTER TABLE to modify columns
        # This is a simplified implementation
        if body and 'properties' in body:
            # Normally you would ALTER TABLE to add/modify columns
            # For now, we'll just acknowledge the request
            return {"acknowledged": True}
        else:
            raise ValueError("Invalid mapping definition")

    @query_params(
        "error_trace",
        "filter_path",
        "human",
        "pretty",
        "source",
    )
    def get_mapping(
        self,
        *,
        index: Any = None,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        Returns mappings for one or more indices.


        :arg index: A comma-separated list of index names. Use `_all` or
            `*` to get mappings for all indices.
        :arg error_trace: Whether to include the stack trace of returned
            errors. Default is false.
        :arg filter_path: Used to reduce the response. This parameter
            takes a comma-separated list of filters. It supports using wildcards to
            match any field or part of a field's name. You can also exclude fields
            with "-".
        :arg human: Whether to return human readable values for
            statistics. Default is True.
        :arg pretty: Whether to pretty format the returned JSON
            response. Default is false.
        :arg source: The URL-encoded request definition. Useful for
            libraries that do not accept a request body for non-POST requests.
        """
        # Delegate to get method for single index
        if index and index not in SKIP_IN_PATH:
            return self.get(index=index, params=params, headers=headers)
        else:
            # For multiple indices or all indices, we would need more complex logic
            raise NotImplementedError("Getting mappings for multiple indices not implemented")

    @query_params(
        "error_trace",
        "filter_path",
        "human",
        "pretty",
        "source",
    )
    def refresh(
        self,
        *,
        index: Any = None,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        Performs the refresh operation in one or more indices.


        :arg index: A comma-separated list of index names. Use `_all` or
            `*` to perform the operation on all indices.
        :arg error_trace: Whether to include the stack trace of returned
            errors. Default is false.
        :arg filter_path: Used to reduce the response. This parameter
            takes a comma-separated list of filters. It supports using wildcards to
            match any field or part of a field's name. You can also exclude fields
            with "-".
        :arg human: Whether to return human readable values for
            statistics. Default is True.
        :arg pretty: Whether to pretty format the returned JSON
            response. Default is false.
        :arg source: The URL-encoded request definition. Useful for
            libraries that do not accept a request body for non-POST requests.
        """
        # In Opensearch, there's no direct equivalent to Elasticsearch refresh
        # We'll just acknowledge the request
        return index_operations.execute_refresh()

    @query_params(
        "error_trace",
        "filter_path",
        "human",
        "pretty",
        "source",
    )
    def analyze(
        self,
        *,
        body: Any = None,
        index: Any = None,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        Performs the analysis process on a text and return the tokens breakdown of the
        text.


        :arg body: Define analyzer/tokenizer parameters and the text on
            which the analysis should be performed
        :arg index: The name of the index to scope the operation.
        :arg error_trace: Whether to include the stack trace of returned
            errors. Default is false.
        :arg filter_path: Used to reduce the response. This parameter
            takes a comma-separated list of filters. It supports using wildcards to
            match any field or part of a field's name. You can also exclude fields
            with "-".
        :arg human: Whether to return human readable values for
            statistics. Default is True.
        :arg pretty: Whether to pretty format the returned JSON
            response. Default is false.
        :arg source: The URL-encoded request definition. Useful for
            libraries that do not accept a request body for non-POST requests.
        """
        # In Opensearch, we don't have text analysis like Elasticsearch
        # We'll return a basic response
        return index_operations.execute_analyze()

    @query_params(
        "error_trace",
        "filter_path",
        "human",
        "pretty",
        "source",
    )
    def get_all_index_names(self) -> Any:
        """
        Returns all index names in the database.
        
        :return: List of index names
        """
        sql_query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """
        return index_operations.execute_get_all_index_names(self.client)
    
    def get_settings(
        self,
        *,
        index: Any = None,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        Returns settings for one or more indices.
        
        OpenSearch 兼容接口：获取索引设置
        
        :arg index: A comma-separated list of index names. Use `_all` or
            `*` to get settings for all indices.
        :return: Index settings in OpenSearch-compatible format
        """
        if index in SKIP_IN_PATH:
            raise ValueError("Empty value passed for a required argument 'index'.")
        
        validated_index = normalize_identifier(index, "Index name")
        
        # 查询表信息（包括创建时间等）
        sql_query = """
        SELECT 
            tablename,
            tableowner,
            schemaname
        FROM pg_tables 
        WHERE tablename = %s AND schemaname = 'public';
        """
        
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql_query, (validated_index,))
                result = cursor.fetchone()
            finally:
                cursor.close()

            if not result:
                raise Exception(f"Index '{validated_index}' not found")

            settings_response = {
                validated_index: {
                    "settings": {
                        "index": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                            "creation_date": "0",
                            "uuid": "_na_",
                            "provided_name": validated_index,
                            "version": {
                                "created": "14000001"
                            }
                        }
                    },
                    "mappings": self.get(index=index).get(validated_index, {}).get("mappings", {})
                }
            }

            return settings_response
    
    def stats(
        self,
        *,
        index: Any = None,
        params: Any = None,
        headers: Any = None,
    ) -> Any:
        """
        Returns statistical information about one or more indices.
        
        OpenSearch 兼容接口：获取索引统计信息
        
        :arg index: A comma-separated list of index names. Use `_all` or
            `*` to get statistics for all indices.
        :return: Index statistics in OpenSearch-compatible format
        """
        if index in SKIP_IN_PATH:
            raise ValueError("Empty value passed for a required argument 'index'.")
        
        validated_index = normalize_identifier(index, "Index name")
        
        # [FIX] 使用一个连接完成所有操作，避免多次获取连接
        with self.client.connection.get_connection_for_operation() as conn:
            # 检查索引是否存在（复用连接）
            if not self.exists(index=validated_index, connection=conn):
                raise Exception(f"Index '{validated_index}' not found")
            
            # [OK] 使用 SELECT COUNT(*) 获取准确的行数
            count_query = f'SELECT COUNT(*) FROM "{validated_index}"'
            cursor = conn.cursor()
            try:
                cursor.execute(count_query)
                row_result = cursor.fetchone()
                row_count = int(row_result[0]) if row_result else 0
            finally:
                cursor.close()
            
            # 查询表大小（复用同一个连接）
            size_query = """
            SELECT pg_size_pretty(pg_total_relation_size(%s::regclass)) AS total_size,
                   pg_total_relation_size(%s::regclass) AS total_size_bytes
            """
            cursor = conn.cursor()
            try:
                cursor.execute(size_query, (validated_index, validated_index))
                size_result = cursor.fetchone()
                total_size_pretty = size_result[0] if size_result else "0B"
                total_size_bytes = size_result[1] if size_result else 0
            finally:
                cursor.close()
            
            # 查询字段数量（复用同一个连接）
            current_schema = self.client.connection.get_current_schema()
            
            field_count_query = """
            SELECT COUNT(*) as field_count
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = %s;
            """
            cursor = conn.cursor()
            try:
                cursor.execute(field_count_query, (validated_index, current_schema))
                field_result = cursor.fetchone()
                field_count = field_result[0] if field_result else 0
            finally:
                cursor.close()
        
        # 构建 OpenSearch 兼容的统计响应
        stats_response = {
            "_shards": {
                "total": 1,
                "successful": 1,
                "failed": 0
            },
            "_all": {
                "primaries": self._build_stats_bucket(row_count, total_size_bytes),
                "total": self._build_stats_bucket(row_count, total_size_bytes)
            },
            "indices": {
                validated_index: {
                    "uuid": "_na_",
                    "primaries": self._build_stats_bucket(row_count, total_size_bytes),
                    "total": self._build_stats_bucket(row_count, total_size_bytes)
                }
            }
        }
        
        return stats_response
