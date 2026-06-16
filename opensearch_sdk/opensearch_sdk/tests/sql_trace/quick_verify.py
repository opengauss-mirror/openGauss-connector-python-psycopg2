#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速验证 SQL 追踪功能
"""

import sys
import os
import json

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

# 加载配置
db_config = load_db_config()

# 创建客户端（启用 SQL 追踪）
client = OpenGauss(
    hosts=[{'host': db_config['host'], 'port': db_config['port']}],
    database=db_config['database'],
    user=db_config['user'],
    password=db_config['password'],
    enable_sql_trace=True
)

TEST_INDEX = 'test_sql_trace_search'

print("=" * 80)
print("SQL 追踪功能快速验证")
print("=" * 80)

# 测试 1: 直接执行 SQL 查询
print("\n[测试 1] 直接 SQL 查询")
cursor = client.connection.execute(f'SELECT * FROM "{TEST_INDEX}" LIMIT 5')
rows = cursor.fetchall()
print(f"查询结果数：{len(rows)}")
if rows:
    print(f"第一条：{rows[0]}")

# 获取 session
session = client.sql_tracer.get_last_session()
if session:
    print(f"\nSQL 记录:")
    for record in session.records:
        print(f"  - {record.context}: {record.sql[:60]}...")

# 测试 2: 使用 search 方法
print("\n[测试 2] 使用 search 方法")
result = client.search(TEST_INDEX, {"query": {"match_all": {}}})
print(f"Search 结果数：{result['hits']['total']['value']}")

session = client.sql_tracer.get_last_session()
print(f"Session operation: {session.operation}")
print(f"SQL 记录数：{len(session.records)}")
if session.records:
    print(f"最后一条 SQL: {session.records[-1].sql[:80]}...")

# 导出报告
print("\n[测试 3] 导出报告")
filepath = client.sql_tracer.export_to_file(export_format="markdown")
print(f"已导出到：{filepath}")

client.close()
print("\n完成！")
