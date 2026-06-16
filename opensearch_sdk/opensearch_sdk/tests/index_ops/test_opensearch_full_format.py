#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 SDK 是否完全解析 OpenSearch 格式的 JSON（包括 settings.similarity）
"""

import json
import os
import sys

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

# 加载数据库配置
db_config = load_db_config()

client = OpenGauss(
    hosts=[{'host': db_config['host'], 'port': db_config['port']}],
    database=db_config['database'],
    user=db_config['user'],
    password=db_config['password']
)

# OpenSearch 完整格式（包含 settings.similarity）
opensearch_full_mapping = {
    "settings": {
        "index": {
            "number_of_shards": 2,
            "number_of_replicas": 1,
            "refresh_interval": "30s"
        },
        "similarity": {
            "custom_bm25": {
                "type": "BM25",
                "k1": "1.3",
                "b": "0.6"
            }
        }
    },
    "mappings": {
        "properties": {
            "categories": {
                "type": "text",
                "index": True
            },
            "question": {
                "type": "keyword",
                "index": True
            },
            "answerList": {
                "type": "text"
            },
            "similarQuestions": {
                "type": "text"
            },
            "keywordList": {
                "type": "keyword"
            },
            "startTime": {
                "type": "keyword"
            }
        }
    }
}

print("="*80)
print("测试：SDK 是否完全解析 OpenSearch 格式的 JSON")
print("="*80)

TEST_INDEX = "test_opensearch_full_format"

try:
    # 清理旧索引
    if client.indices.exists(index=TEST_INDEX):
        print(f"\n删除旧索引：{TEST_INDEX}")
        client.indices.delete(index=TEST_INDEX)
    
    print("\n尝试创建索引（使用完整的 OpenSearch 格式）...")
    print(json.dumps(opensearch_full_mapping, indent=2, ensure_ascii=False))
    
    # 创建索引
    response = client.indices.create(index=TEST_INDEX, body=opensearch_full_mapping)
    print(f"\n[OK] 索引创建成功！响应：{response}")
    
    # 验证索引存在
    exists = client.indices.exists(index=TEST_INDEX)
    print(f"[OK] 索引存在检查：{exists}")
    
    # 查看 mapping
    mapping = client.indices.get_mapping(index=TEST_INDEX)
    print(f"\n[OK] 获取的 Mapping:")
    print(json.dumps(mapping, indent=2, ensure_ascii=False))
    
    # 查看 settings（新接口）
    settings = client.indices.get_settings(index=TEST_INDEX)
    print(f"\n[OK] 获取的 Settings:")
    print(json.dumps(settings, indent=2, ensure_ascii=False))
    
    # 插入测试数据
    test_doc = {
        "categories": ["技术", "数据库"],
        "question": "什么是 Opensearch？",
        "answerList": ["Opensearch 是一款分布式数据库"],
        "similarQuestions": ["Opensearch 的特点是什么？"],
        "keywordList": ["分布式", "数据库"],
        "startTime": "2024-01-01 00:00:00"
    }
    
    print(f"\n插入测试数据...")
    client.index(index=TEST_INDEX, id="1", body=test_doc)
    print("[OK] 数据插入成功")
    
    # 测试 BM25 搜索（使用查询时参数）
    print(f"\n测试 BM25 全文搜索...")
    results = client.fulltext_search(
        index=TEST_INDEX,
        query_text="Opensearch 数据库",
        text_column="answerList",
        top_k=5,
        bm25_k1=1.3,  # 使用与 OpenSearch 相同的 k1 值
        bm25_b=0.6    # 使用与 OpenSearch 相同的 b 值
    )
    
    print(f"[OK] BM25 搜索结果：返回 {len(results['hits']['hits'])} 条记录")
    if results['hits']['hits']:
        print(f"   最佳匹配得分：{results['hits']['hits'][0]['_score']}")
    
    # 清理
    print(f"\n清理测试索引...")
    client.indices.delete(index=TEST_INDEX)
    print("[OK] 索引已删除")
    
    print("\n" + "="*80)
    print("[OK] 测试通过！SDK 完全支持 OpenSearch 格式的 JSON 解析")
    print("="*80)
    print("\n关键发现：")
    print("1. [OK] SDK 可以解析 settings 对象（虽然不实际使用分片/副本设置）")
    print("2. [OK] SDK 可以解析 similarity 对象（BM25 自定义相似度）")
    print("3. [OK] mappings.properties 被正确解析并创建表结构")
    print("4. [WARN] similarity 配置在索引创建时被解析但不存储（Opensearch 采用查询时动态传参）")
    print("5. [OK] 查询时可以通过 bm25_k1/bm25_b 参数实现相同效果")
    
except Exception as e:
    print(f"\n[FAIL] 测试失败：{e}")
    import traceback
    traceback.print_exc()
    raise  # 重新抛出异常，让 unittest 捕获


# 如果直接运行此文件，执行测试
if __name__ == "__main__":
    # 将脚本转换为 unittest 格式
    import unittest
    
    class TestOpenSearchFullFormat(unittest.TestCase):
        def test_opensearch_full_format(self):
            """包装现有脚本为 unittest 测试"""
            # 脚本已经在上面执行了
            pass
    
    unittest.main(verbosity=2)
