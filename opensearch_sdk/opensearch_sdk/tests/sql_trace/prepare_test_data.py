#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
准备测试数据
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
    password=db_config['password']
)

TEST_INDEX = 'test_sql_trace_search'

print("=" * 80)
print("准备测试数据")
print("=" * 80)

# 删除旧索引
try:
    client.indices.delete(TEST_INDEX)
    print(f"已删除旧索引：{TEST_INDEX}")
except Exception:
    pass

# 创建新索引
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "content": {"type": "text"},
            "category": {"type": "keyword"},
            "publish_date": {"type": "date"}
        }
    }
}
client.indices.create(TEST_INDEX, mapping)
print(f"已创建索引：{TEST_INDEX}")

# 插入测试数据
test_docs = [
    {
        "title": "Opensearch Introduction",
        "content": "Opensearch is a powerful vector database with full-text search support",
        "category": "technology",
        "publish_date": "2024-01-15"
    },
    {
        "title": "AI Applications",
        "content": "Artificial intelligence is transforming industries worldwide",
        "category": "technology",
        "publish_date": "2024-02-20"
    },
    {
        "title": "Travel Guide",
        "content": "Best places to visit in 2024",
        "category": "travel",
        "publish_date": "2024-03-10"
    }
]

doc_ids = ["doc1", "doc2", "doc3"]
for i, doc in enumerate(test_docs):
    client.create(TEST_INDEX, doc_ids[i], doc)
    print(f"已插入文档：{doc_ids[i]}")

print(f"\n完成！共插入 {len(test_docs)} 条文档")

# 验证数据
result = client.search(TEST_INDEX, {"query": {"match_all": {}}})
print(f"验证查询结果数：{result['hits']['total']['value']}")

client.close()
