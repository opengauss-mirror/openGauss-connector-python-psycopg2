from typing import Any
from psycopg2 import sql
from opensearch_sdk.client.utils import SKIP_IN_PATH, normalize_identifier


def _with_cursor(conn, callback):
    cursor = conn.cursor()
    try:
        return callback(cursor)
    finally:
        cursor.close()


def execute_delete(client, index: str) -> dict:
    """执行删除索引操作"""
    if index in SKIP_IN_PATH:
        raise ValueError("Empty value passed for a required argument 'index'.")

    validated_index = normalize_identifier(index, "Index name")
    drop_sql = sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(validated_index))

    # [OK] 使用新的连接管理模式
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(drop_sql)
            conn.commit()
        finally:
            cursor.close()

        # [OK] 同步删除 opensearch_mapping 表中的记录
        try:
            from opensearch_sdk.client.constants import MAPPING_STORAGE_TABLE
            delete_mapping_sql = f"""
                DELETE FROM {MAPPING_STORAGE_TABLE}
                WHERE index_name = %s;
            """
            mapping_cursor = conn.cursor()
            try:
                mapping_cursor.execute(delete_mapping_sql, (validated_index,))
                conn.commit()
            finally:
                mapping_cursor.close()
        except Exception as e:
            print(f"[WARN] 删除 mapping 表中的记录失败: {e}")
            # 不影响主流程

    return {"acknowledged": True}


def execute_exists(client, index: str, connection=None) -> bool:
    """
    检查索引是否存在

    :param client: Opensearch 客户端
    :param index: 索引名称
    :param connection: 可选的连接对象，如果提供则复用，否则使用 client.connection
    :return: True 如果索引存在，否则 False
    """
    if index in SKIP_IN_PATH:
        raise ValueError("Empty value passed for a required argument 'index'.")

    validated_index = normalize_identifier(index, "Index name")

    # 动态获取当前 schema
    current_schema = client.connection.get_current_schema()

    exists_sql = sql.SQL("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = %s AND table_schema = %s
        );
    """)

    # 如果提供了 connection，复用它；否则使用 client.connection
    if connection is not None:
        # 复用传入的连接
        cursor = connection.cursor()
        try:
            cursor.execute(exists_sql, (validated_index, current_schema))
            result = cursor.fetchone()
            return result[0] if result else False
        finally:
            cursor.close()
    else:
        # [FIX] 使用新的连接管理模式
        with client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(exists_sql, (validated_index, current_schema))
                result = cursor.fetchone()
                return result[0] if result else False
            finally:
                cursor.close()


def execute_get_mapping_from_comment(client, validated_index: str) -> dict:
    """从 opensearch_mapping 表读取 mapping 配置"""
    try:
        from opensearch_sdk.client.doc_utils.mapping_storage import load_mapping_from_table

        # 获取当前 schema
        current_schema = client.connection.get_current_schema()

        # 从独立表加载
        mapping_data = load_mapping_from_table(client.connection, validated_index, current_schema)

        if mapping_data:
            return mapping_data
    except Exception as e:
        # 读取失败返回 None，不影响主流程
        pass

    return None


def build_mapping_from_columns(columns: list) -> dict:
    """从数据库列构建 mapping（降级方案）"""
    import re

    mappings = {
        "mappings": {
            "properties": {}
        }
    }

    for column_name, data_type in columns:
        # 验证列名
        validated_column = normalize_identifier(column_name, "Column name from DB") if re.match(r'^[a-zA-Z_][a-zA-Z0-9_.\-]*$', column_name) else 'unknown'

        # 映射 Opensearch 类型到 OpenSearch 类型
        type_map = {
            'character varying': 'keyword',
            'text': 'text',
            'bigint': 'long',
            'integer': 'long',
            'smallint': 'long',
            'real': 'float',
            'double precision': 'float',
            'boolean': 'boolean',
            'timestamp without time zone': 'date',
        }

        field_type = type_map.get(data_type, 'text')
        if data_type.startswith('vector'):
            field_type = 'dense_vector'

        mappings["mappings"]["properties"][validated_column] = {"type": field_type}

    return mappings


def build_mapping_from_comment(mapping_from_comment: dict) -> dict:
    """从 pg_description 的 mapping 构建响应"""
    import re

    mappings = {
        "mappings": {
            "properties": {}
        }
    }

    for field_name, field_info in mapping_from_comment['properties'].items():
        validated_column = normalize_identifier(field_name, "Mapping field from comment") if re.match(r'^[a-zA-Z_][a-zA-Z0-9_.\-]*$', field_name) else 'unknown'

        field_type_stored = field_info.get('type', 'text')

        # OpenSearch 兼容性：将 integer/smallint 统一转换为 long
        if field_type_stored in ['integer', 'smallint']:
            field_type_stored = 'long'

        # 处理 vector 类型
        if field_type_stored in ['float_vector', 'dense_vector', 'knn_vector']:
            dims = field_info.get('dims') or field_info.get('dimension')
            if dims:
                mappings["mappings"]["properties"][validated_column] = {
                    "type": field_type_stored,
                    "dimension": dims  # OpenSearch 标准字段名
                }
            else:
                mappings["mappings"]["properties"][validated_column] = {"type": field_type_stored}
        else:
            mappings["mappings"]["properties"][validated_column] = {"type": field_type_stored}

    # 添加 dynamic_templates
    if 'dynamic_templates' in mapping_from_comment:
        mappings["mappings"]["dynamic_templates"] = mapping_from_comment['dynamic_templates']

    return mappings


def execute_refresh() -> dict:
    """执行 refresh 操作（Opensearch 无直接对应）"""
    return {"_shards": {"total": 1, "successful": 1, "failed": 0}}


def execute_analyze() -> dict:
    """执行 analyze 操作（返回基本响应）"""
    return {
        "tokens": [
            {
                "token": "analyzed",
                "start_offset": 0,
                "end_offset": 8,
                "type": "word",
                "position": 0
            }
        ]
    }


def execute_get_all_index_names(client) -> list:
    """获取所有索引名称"""
    from opensearch_sdk.client.constants import MAPPING_STORAGE_TABLE

    mapping_query = f"""
        SELECT DISTINCT index_name
        FROM {MAPPING_STORAGE_TABLE}
        ORDER BY index_name;
    """

    try:
        return _execute_index_name_query(client, mapping_query)
    except Exception as e:
        # 如果 opensearch_mapping 表不存在或查询失败，回退到查询 information_schema
        print(f"[WARN] 从 {MAPPING_STORAGE_TABLE} 表查询索引失败: {e}，回退到 information_schema")
        return _execute_index_name_query(client, """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)


def _is_valid_index_name(name: str) -> bool:
    import re
    if not isinstance(name, str):
        return False
    return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name))


def _filter_index_rows(rows) -> list:
    return [row[0] for row in rows if row and _is_valid_index_name(row[0])]


def _execute_index_name_query(client, query) -> list:
    with client.connection.get_connection_for_operation() as conn:
        def fetch_names(cursor):
            cursor.execute(query)
            return _filter_index_rows(cursor.fetchall())
        return _with_cursor(conn, fetch_names)


def _detect_original_index(cursor, validated_index: str, index_type: str):
    detect_sql = sql.SQL("""
        SELECT
            am.amname as index_type,
            pg_get_indexdef(i.indexrelid) as index_definition
        FROM pg_index i
        JOIN pg_class c ON i.indexrelid = c.oid
        JOIN pg_am am ON c.relam = am.oid
        WHERE c.relname = %s
    """)
    cursor.execute(detect_sql, (validated_index,))
    result = cursor.fetchone()
    if not result:
        return None, None, index_type

    detected_type = result[0]
    original_index_def = result[1]
    print(f"[INFO] Detected original index type: {detected_type}")
    print(f"[INFO] Original definition: {original_index_def}")

    if index_type == "btree":
        index_type = detected_type
        print(f"[INFO] Using detected type for rebuild: {index_type}")
    return original_index_def, detected_type, index_type


def _build_rebuild_create_sql(validated_index: str, validated_table: str,
                              validated_column: str, index_type: str,
                              original_index_def: str, detected_type: str):
    if original_index_def and detected_type != 'btree':
        print(f"[INFO] Rebuilding with original definition")
        return original_index_def
    return sql.SQL("CREATE INDEX {} ON {} USING {} ({})").format(
        sql.Identifier(validated_index),
        sql.Identifier(validated_table),
        sql.SQL(index_type.lower()),
        sql.Identifier(validated_column)
    )


def _rebuild_result(validated_index: str, validated_table: str, validated_column: str,
                    index_type: str, original_index_def: str, detected_type: str,
                    auto_detect: bool) -> dict:
    return {
        "acknowledged": True,
        "index": validated_index,
        "table": validated_table,
        "column": validated_column,
        "type": index_type,
        "original_type": detected_type,
        "auto_detected": auto_detect and detected_type is not None,
        "original_definition": original_index_def,
        "message": f"Index '{validated_index}' rebuilt successfully"
    }


def execute_rebuild_index(client, index_name: str, table_name: str,
                         column_name: str, index_type: str = "btree",
                         auto_detect: bool = True,
                         **kwargs) -> dict:
    """
    重建数据库索引（先删除后重建）

    :param client: Opensearch 客户端
    :param index_name: 索引名称
    :param table_name: 表名
    :param column_name: 索引列名
    :param index_type: 索引类型 (btree, gin, gist, hnsw, etc.)
    :param auto_detect: 是否自动检测原索引类型（默认 True）
    :return: 重建结果
    """
    # 验证参数
    if not all([index_name, table_name, column_name]):
        raise ValueError("index_name, table_name, and column_name are required")

    validated_index = normalize_identifier(index_name, "Index name")
    validated_table = normalize_identifier(table_name, "Table name")
    validated_column = normalize_identifier(column_name, "Column name")

    # [OK] 使用新的连接管理模式
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            original_index_def = None
            detected_type = None
            if auto_detect:
                original_index_def, detected_type, index_type = _detect_original_index(
                    cursor, validated_index, index_type
                )

            drop_sql = sql.SQL("DROP INDEX IF EXISTS {}").format(
                sql.Identifier(validated_index)
            )
            cursor.execute(drop_sql)

            create_sql = _build_rebuild_create_sql(
                validated_index, validated_table, validated_column,
                index_type, original_index_def, detected_type
            )
            cursor.execute(create_sql)
            conn.commit()

            return _rebuild_result(
                validated_index, validated_table, validated_column,
                index_type, original_index_def, detected_type, auto_detect
            )

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to rebuild index '{validated_index}': {e}")
        finally:
            cursor.close()
