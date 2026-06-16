#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
knn_search SQL 追踪集成验证
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

TEST_INDEX = 'test_knn_trace'

print("=" * 80)
print("knn_search SQL 追踪验证")
print("=" * 80)

# 删除旧索引
try:
    client.indices.delete(TEST_INDEX)
    print(f"已删除旧索引：{TEST_INDEX}")
except Exception:
    pass

# 创建带向量字段的索引
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "embedding": {
                "type": "dense_vector",  # 或 knn_vector
                "dims": 3  # 使用 dims 而不是 dimension
            }
        }
    }
}
client.indices.create(TEST_INDEX, mapping)
print(f"已创建索引：{TEST_INDEX}")

# 插入测试数据（包含向量）
test_docs = [
    {
        "title": "Document 1",
        "embedding": [0.1, 0.2, 0.3]
    },
    {
        "title": "Document 2",
        "embedding": [0.4, 0.5, 0.6]
    },
    {
        "title": "Document 3",
        "embedding": [0.7, 0.8, 0.9]
    }
]

for i, doc in enumerate(test_docs, 1):
    client.create(TEST_INDEX, f"doc{i}", doc)
    print(f"已插入文档：doc{i}")

print()

# 执行 knn_search
print("[测试] 执行 knn_search")
query_vector = [0.2, 0.3, 0.4]
result = client.knn_search(
    index=TEST_INDEX,
    field="embedding",
    query_vector=query_vector,
    k=2,
    similarity='cosine'
)

print(f"返回结果数：{result['hits']['total']['value']}")

# 查看追踪信息
session = client.sql_tracer.get_last_session()
print(f"\nSession operation: {session.operation}")
print(f"Index: {session.index_name}")
print(f"SQL 记录数：{len(session.records)}")

if session.records:
    print(f"\nSQL 详情:")
    for record in session.records:
        print(f"  Context: {record.context}")
        print(f"  SQL: {str(record.sql)[:80]}...")
        print(f"  Duration: {record.duration_ms:.2f}ms")
        
        # 查看 metadata
        if hasattr(record, 'metadata') and record.metadata:
            print(f"  Metadata:")
            for key, value in record.metadata.items():
                print(f"    {key}: {value}")

# 导出报告
print("\n[导出] 生成报告")
filepath = client.sql_tracer.export_to_file(export_format="markdown")
print(f"已导出到：{filepath}")

# 清理
try:
    client.indices.delete(TEST_INDEX)
    print(f"\n已删除测试索引：{TEST_INDEX}")
except Exception:
    pass

client.close()
print("\n完成！")
