#!/usr/bin/env python
# -*-coding:utf-8 -*-
"""
Mapping 存储管理模块
使用独立的 opensearch_mapping 表存储所有索引的 mapping 信息
"""

import json
from contextlib import contextmanager
from typing import Dict, Optional

from opensearch_sdk.client.constants import MAPPING_STORAGE_TABLE


@contextmanager
def _cursor_scope(connection):
    from opensearch_sdk.connection.opengauss import OpenGaussConnection

    if isinstance(connection, OpenGaussConnection):
        with connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                yield cursor, conn
            finally:
                cursor.close()
    else:
        cursor = connection.cursor()
        try:
            yield cursor, connection
        finally:
            cursor.close()


def _execute_and_commit(connection, callback):
    with _cursor_scope(connection) as (cursor, conn):
        result = callback(cursor)
        conn.commit()
        return result


def ensure_mapping_table_exists(connection) -> None:
    """
    确保 opensearch_mapping 表存在（如果不存在则创建）
    
    :param connection: 数据库连接对象（OpenGaussConnection 或 psycopg2 connection）
    """
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {MAPPING_STORAGE_TABLE} (
        index_name VARCHAR(255) NOT NULL,
        schema_name VARCHAR(255) NOT NULL,
        mapping_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (schema_name, index_name)
    )
    """
    
    try:
        _execute_and_commit(connection, lambda cursor: cursor.execute(create_table_sql))
    except Exception as e:
        # 表创建失败不影响主流程
        print(f"[WARN] 创建 opensearch_mapping 表失败: {e}")


def _upsert_mapping(cursor, index_name: str, schema_name: str, mapping_json: str) -> None:
    update_sql = f"""
    UPDATE {MAPPING_STORAGE_TABLE}
    SET mapping_json = %s, updated_at = CURRENT_TIMESTAMP
    WHERE index_name = %s AND schema_name = %s
    """
    cursor.execute(update_sql, (mapping_json, index_name, schema_name))

    if cursor.rowcount == 0:
        insert_sql = f"""
        INSERT INTO {MAPPING_STORAGE_TABLE} (index_name, schema_name, mapping_json)
        VALUES (%s, %s, %s)
        """
        cursor.execute(insert_sql, (index_name, schema_name, mapping_json))


def save_mapping_to_table(connection, index_name: str, schema_name: str, mapping_data: Dict) -> None:
    """
    保存 mapping 到 opensearch_mapping 表
    
    :param connection: 数据库连接对象（OpenGaussConnection 或 psycopg2 connection）
    :param index_name: 索引名称
    :param schema_name: Schema 名称
    :param mapping_data: Mapping 数据字典
    """
    try:
        # 确保表存在
        ensure_mapping_table_exists(connection)
        
        mapping_json = json.dumps(mapping_data, ensure_ascii=False)
        
        _execute_and_commit(
            connection,
            lambda cursor: _upsert_mapping(cursor, index_name, schema_name, mapping_json)
        )
    except Exception as e:
        print(f"[WARN] 保存 mapping 到表失败: {e}")


def load_mapping_from_table(connection, index_name: str, schema_name: str) -> Optional[Dict]:
    """
    从 opensearch_mapping 表加载 mapping
    
    :param connection: 数据库连接对象
    :param index_name: 索引名称
    :param schema_name: Schema 名称
    :return: Mapping 数据字典，如果不存在返回 None
    """
    try:
        query_sql = f"""
        SELECT mapping_json FROM {MAPPING_STORAGE_TABLE}
        WHERE index_name = %s AND schema_name = %s
        """
        
        with _cursor_scope(connection) as (cursor, _):
            cursor.execute(query_sql, (index_name, schema_name))
            result = cursor.fetchone()
            if result and result[0]:
                return json.loads(result[0])
            return None
    except Exception as e:
        # 查询失败返回 None，不影响主流程
        return None
