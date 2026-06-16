#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CRUD 操作 SQL 追踪集成验证
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

client = OpenGauss(
    hosts=[{'host': db_config['host'], 'port': db_config['port']}],
    database=db_config['database'],
    user=db_config['user'],
    password=db_config['password'],
    enable_sql_trace=True
)

TEST_INDEX = 'test_crud_trace'

print("=" * 80)
print("CRUD 操作 SQL 追踪验证")
print("=" * 80)

# 清理旧索引
try:
    client.indices.delete(TEST_INDEX)
    print(f"已删除旧索引：{TEST_INDEX}")
except Exception:
    pass

# 创建索引
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "content": {"type": "text"},
            "tags": {"type": "keyword"}
        }
    }
}
client.indices.create(TEST_INDEX, mapping)
print(f"已创建索引：{TEST_INDEX}\n")

# ========== CREATE ==========
print("[1] CREATE - 创建文档")
doc_data = {
    "title": "Test Document",
    "content": "This is a test document for SQL tracing",
    "tags": ["test", "sql-trace"]
}
result = client.create(TEST_INDEX, "doc1", doc_data)
print(f"创建结果：{result['result']}")

session = client.sql_tracer.get_last_session()
print(f"Session operation: {session.operation}")
print(f"SQL 记录数：{len(session.records)}")
if session.records:
    print(f"Context: {session.records[-1].context}")
    if hasattr(session.records[-1], 'metadata'):
        print(f"Metadata: {session.records[-1].metadata}")
print()

# ========== READ ==========
print("[2] READ - 获取文档")
result = client.get(TEST_INDEX, "doc1")
print(f"获取文档：{result['_id']}")

session = client.sql_tracer.get_last_session()
print(f"Session operation: {session.operation}")
print(f"SQL 记录数：{len(session.records)}")
print()

# ========== UPDATE ==========
print("[3] UPDATE - 更新文档")
update_data = {
    "title": "Updated Document",
    "content": "This content has been updated"
}
result = client.update(TEST_INDEX, "doc1", update_data)
print(f"更新结果：{result['result']}")

session = client.sql_tracer.get_last_session()
print(f"Session operation: {session.operation}")
print(f"SQL 记录数：{len(session.records)}")
if session.records:
    print(f"Context: {session.records[-1].context}")
    if hasattr(session.records[-1], 'metadata'):
        print(f"Metadata: {session.records[-1].metadata}")
print()

# ========== DELETE ==========
print("[4] DELETE - 删除文档")
result = client.delete(TEST_INDEX, "doc1")
print(f"删除结果：{result['result']}")

session = client.sql_tracer.get_last_session()
print(f"Session operation: {session.operation}")
print(f"SQL 记录数：{len(session.records)}")
if session.records:
    print(f"Context: {session.records[-1].context}")
    if hasattr(session.records[-1], 'metadata'):
        print(f"Metadata: {session.records[-1].metadata}")
print()

# ========== 导出报告 ==========
print("[5] 导出追踪报告")
filepath = client.sql_tracer.export_to_file(export_format="markdown")
print(f"已导出到：{filepath}")

# 查看导出的内容
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
    print(f"\n报告预览（前 500 字符）:")
    print("-" * 80)
    print(content[:500])

# 清理
try:
    client.indices.delete(TEST_INDEX)
    print(f"\n已删除测试索引：{TEST_INDEX}")
except Exception:
    pass

client.close()
print("\n完成！")
