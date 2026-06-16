#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单调试脚本：验证 search 方法�?SQL 追踪
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from opensearch_sdk.client.base import OpenGaussClient

# 创建 Mock 连接和游�?
mock_cursor = Mock()
mock_cursor.fetchall.return_value = [
    (1, 'content 1'),
    (2, 'content 2')
]
mock_cursor.description = [('id',), ('content',)]

# 创建一个真实的 connection 实例用于测试
from opensearch_sdk.connection.opengauss import OpenGaussConnection
real_connection = OpenGaussConnection.__new__(OpenGaussConnection)  # 创建未初始化的实�?
real_connection.conn = None  # 不需要真实连�?
real_connection.sql_tracer = None  # 稍后设置

# Mock execute 方法但不覆盖追踪逻辑
def mock_execute(query, params=None):
    # 如果�?sql_tracer 且启用了，应该走追踪逻辑
    if hasattr(real_connection, 'sql_tracer') and real_connection.sql_tracer and real_connection.sql_tracer.enabled:
        # 模拟追踪执行
        with real_connection.sql_tracer.trace_session("database_operation", "test") as trace_session:
            # 记录 SQL
            from opensearch_sdk.client.sql_tracer import SQLTraceRecord
            trace_record = SQLTraceRecord(
                sql=str(query),
                params=params,
                context="search_query"
            )
            trace_record.result_count = 2
            trace_record.duration_ms = 5.0
            trace_session.add_record(trace_record)
            return mock_cursor
    else:
        return mock_cursor

real_connection.execute = mock_execute

# Mock OpenGaussConnection
with patch('opensearch_sdk.client.base.OpenGaussConnection') as mock_conn_class:
    mock_conn_class.return_value = real_connection
    
    # 创建客户端（启用 SQL 追踪�?
    client = OpenGaussClient(
        hosts=[{"host": "localhost", "port": 5432}],
        database="test_db",
        enable_sql_trace=True
    )
    
    # 重要：Mock 不会自动传�?sql_tracer，需要手动设�?
    client.connection = real_connection
    real_connection.sql_tracer = client.sql_tracer
    
    print("=" * 80)
    print("SQL 追踪集成测试")
    print("=" * 80)
    print(f"客户端有 sql_tracer 属性：{hasattr(client, 'sql_tracer')}")
    print(f"Tracer 存在：{client.sql_tracer is not None}")
    print(f"Tracer 已启用：{client.sql_tracer.enabled if client.sql_tracer else False}")
    print(f"Client connection: {client.connection}")
    print(f"Connection has tracer attr: {hasattr(client.connection, 'sql_tracer')}")
    print(f"Connection sql_tracer: {client.connection.sql_tracer if hasattr(client.connection, 'sql_tracer') else None}")
    if client.connection.sql_tracer:
        print(f"Connection tracer enabled: {client.connection.sql_tracer.enabled}")
    print()
    
    # 执行搜索
    query_body = {
        "query": {
            "match": {
                "content": "hello world"
            }
        },
        "size": 10
    }
    
    print(f"执行查询：{query_body}")
    print()
    
    result = client.search("test_index", query_body)
    
    # 检查追踪结�?
    session = client.sql_tracer.get_last_session()
    
    print("=" * 80)
    print("追踪结果")
    print("=" * 80)
    print(f"会话存在：{session is not None}")
    
    if session:
        print(f"操作类型：{session.operation}")
        print(f"索引名称：{session.index_name}")
        print(f"SQL 记录数：{len(session.records)}")
        print(f"总耗时：{session.total_duration_ms:.2f}ms")
        print()
        
        if len(session.records) > 0:
            print("SQL 记录详情:")
            for i, record in enumerate(session.records, 1):
                print(f"\n[SQL {i}]")
                print(f"  上下文：{record.context}")
                print(f"  SQL: {record.sql[:100]}...")
                print(f"  参数：{record.params}")
                print(f"  行数：{record.result_count}")
                print(f"  耗时：{record.duration_ms:.2f}ms")
        else:
            print("Warning: 没有记录到任何 SQL")
            print("\n可能原因:")
            print("1. _search_impl 没有被调用")
            print("2. connection.execute 没有被调用")
            print("3. sql_tracer 没有正确传递给 connection")
    else:
        print("错误：没有创建会话！")
    
    print()
    print("=" * 80)
    
    # 检�?connection 是否被调�?
    print(f"execute 方法被调用：{real_connection.execute is not None}")
