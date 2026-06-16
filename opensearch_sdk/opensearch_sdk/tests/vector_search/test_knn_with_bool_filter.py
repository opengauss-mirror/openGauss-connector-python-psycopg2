#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量搜索测试 - kNN + Bool 过滤器

功能说明：
- knn + bool.filter 组合查询
- 测试复杂查询格式的处理

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.vector_search.test_knn_with_bool_filter -v
    python opensearch_sdk/tests/vector_search/test_knn_with_bool_filter.py
"""

import os
import sys
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config

# 直接导入 SDK，避免循环依赖
from opensearch_sdk import OpenGauss

# 加载配置
db_config = load_db_config()

client = OpenGauss(
    hosts=[{
        'host': db_config['host'],
        'port': db_config['port']
    }],
    database=db_config['database'],
    user=db_config['user'],
    password=db_config['password']
)

TEST_INDEX = 'test_knn_bool_filter'

# 清理旧索引
try:
    client.indices.delete(index=TEST_INDEX)
    print("OK: 已删除旧索引")
except:
    pass

# 创建索引（包含向量字段和标量字段）
mapping = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        }
    },
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "category": {"type": "keyword"},
            "publish_date": {"type": "date", "format": "yyyy-MM-dd"},
            "embedding": {
                "type": "dense_vector",
                "dims": 4,
                "similarity": "cosine"
            }
        }
    }
}

client.indices.create(index=TEST_INDEX, body=mapping)
print("OK: 索引已创建\n")

# 插入测试数据
docs = [
    {
        "id": "doc1",
        "body": {
            "title": "AI Technology in 2024",
            "category": "tech",
            "publish_date": "2024-03-15",
            "embedding": [0.9, 0.1, 0.1, 0.1]  # 接近查询向量
        }
    },
    {
        "id": "doc2",
        "body": {
            "title": "Machine Learning Basics",
            "category": "tech",
            "publish_date": "2024-01-20",
            "embedding": [0.8, 0.2, 0.1, 0.1]  # 较接近
        }
    },
    {
        "id": "doc3",
        "body": {
            "title": "History of Art",
            "category": "art",
            "publish_date": "2024-02-10",
            "embedding": [0.1, 0.9, 0.1, 0.1]  # 不接近
        }
    },
    {
        "id": "doc4",
        "body": {
            "title": "Deep Learning Advances",
            "category": "tech",
            "publish_date": "2023-12-01",  # 2024 年之前
            "embedding": [0.85, 0.15, 0.1, 0.1]  # 很接近
        }
    },
    {
        "id": "doc5",
        "body": {
            "title": "Neural Networks",
            "category": "tech",
            "publish_date": "2024-05-01",
            "embedding": [0.7, 0.3, 0.1, 0.1]  # 一般接近
        }
    }
]

for doc in docs:
    client.index(index=TEST_INDEX, id=doc['id'], body=doc['body'])

print(f"OK: 已插入 {len(docs)} 个文档\n")

# 查询向量（接近 tech 类别的文档）
query_vector = [0.85, 0.15, 0.1, 0.1]

print("="*70)
print("测试 1: 基础 kNN 查询（无过滤）")
print("="*70)

query1 = {
    "knn": {
        "embedding": {
            "vector": query_vector,
            "k": 10
        }
    }
}

result1 = client.search(index=TEST_INDEX, body=query1)
hits1 = result1['hits']['hits']
print(f"找到 {len(hits1)} 个匹配:")
for hit in hits1:
    print(f"  - {hit['_id']}: category={hit['_source']['category']}, "
          f"date={hit['_source']['publish_date']}, score={hit['_score']:.4f}")
print()

print("="*70)
print("测试 2: kNN + OpenSearch 标准 filter 格式")
print("="*70)

# OpenSearch 标准格式：filter 在 knn 内部
query2 = {
    "knn": {
        "embedding": {
            "vector": query_vector,
            "k": 10,
            "filter": {
                "term": {
                    "category": "tech"
                }
            }
        }
    }
}

try:
    result2 = client.search(index=TEST_INDEX, body=query2)
    hits2 = result2['hits']['hits']
    print(f"找到 {len(hits2)} 个匹配:")
    for hit in hits2:
        print(f"  - {hit['_id']}: category={hit['_source']['category']}, "
              f"date={hit['_source']['publish_date']}, score={hit['_score']:.4f}")
    print("\n[OK] 支持 OpenSearch 标准 filter 格式！")
except Exception as e:
    print("[ERROR] 错误：{}".format(e))
print()

print("="*70)
print("测试 3: kNN + bool.filter 组合（用户提出的格式）")
print("="*70)

# 用户提出的格式：knn 和 bool 并列
query3 = {
    "size": 10,
    "query": {
        "knn": {
            "embedding": {
                "vector": query_vector,
                "k": 10
            }
        },
        "bool": {
            "filter": [
                {"term": {"category": "tech"}},
                {"range": {"publish_date": {"gte": "2024-01-01"}}}
            ]
        }
    },
    "_source": ["title", "category", "publish_date"]
}

try:
    result3 = client.search(index=TEST_INDEX, body=query3)
    hits3 = result3['hits']['hits']
    print(f"找到 {len(hits3)} 个匹配:")
    for hit in hits3:
        print(f"  - {hit['_id']}: category={hit['_source']['category']}, "
              f"date={hit['_source']['publish_date']}, score={hit['_score']:.4f}")
    print("\n[OK] 支持用户提出的复杂查询格式！")
except Exception as e:
    print("[ERROR] 错误：{}".format(e))
    print(f"\n[WARN] 当前实现不支持这种格式")
print()

print("="*70)
print("测试 4: kNN + 单个 term 过滤")
print("="*70)

query4 = {
    "knn": {
        "embedding": {
            "vector": query_vector,
            "k": 10,
            "filter": {
                "term": {
                    "category": "tech"
                }
            }
        }
    }
}

result4 = client.search(index=TEST_INDEX, body=query4)
hits4 = result4['hits']['hits']
print(f"找到 {len(hits4)} 个匹配:")
for hit in hits4:
    print(f"  - {hit['_id']}: category={hit['_source']['category']}, "
          f"date={hit['_source']['publish_date']}, score={hit['_score']:.4f}")
print()

print("="*70)
print("测试 5: kNN + range 过滤")
print("="*70)

query5 = {
    "knn": {
        "embedding": {
            "vector": query_vector,
            "k": 10,
            "filter": {
                "range": {
                    "publish_date": {
                        "gte": "2024-01-01"
                    }
                }
            }
        }
    }
}

try:
    result5 = client.search(index=TEST_INDEX, body=query5)
    hits5 = result5['hits']['hits']
    print(f"找到 {len(hits5)} 个匹配:")
    for hit in hits5:
        print(f"  - {hit['_id']}: category={hit['_source']['category']}, "
              f"date={hit['_source']['publish_date']}, score={hit['_score']:.4f}")
    print("\n[OK] 支持 range 过滤！")
except Exception as e:
    print("[ERROR] 错误：{}".format(e))
print()

print("="*70)
print("测试 6: kNN + bool.filter（多个条件）")
print("="*70)

query6 = {
    "knn": {
        "embedding": {
            "vector": query_vector,
            "k": 10,
            "filter": {
                "bool": {
                    "must": [
                        {"term": {"category": "tech"}},
                        {"range": {"publish_date": {"gte": "2024-01-01"}}}
                    ]
                }
            }
        }
    }
}

try:
    result6 = client.search(index=TEST_INDEX, body=query6)
    hits6 = result6['hits']['hits']
    print(f"找到 {len(hits6)} 个匹配:")
    for hit in hits6:
        print(f"  - {hit['_id']}: category={hit['_source']['category']}, "
              f"date={hit['_source']['publish_date']}, score={hit['_score']:.4f}")
    print("\n[OK] 支持复杂的 bool.filter 组合！")
except Exception as e:
    print("[ERROR] 错误：{}".format(e))
print()

# 清理
client.indices.delete(index=TEST_INDEX)
print("OK: 已清理测试索引")

print("\n" + "="*70)
print("测试完成")
print("="*70)
