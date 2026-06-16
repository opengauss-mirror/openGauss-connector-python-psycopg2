#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量搜索测试 - 直接 kNN 查询

功能说明：
- 直接使用 knn_search API 测试过滤功能
- 验证 kNN 查询的基本功能

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.vector_search.test_knn_direct -v
    python opensearch_sdk/tests/vector_search/test_knn_direct.py
"""

import os
import sys
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config

# 直接导入 SDK，避免循环依赖
from opensearch_sdk import OpenGauss

# 加载配置
db_config = load_db_config()


class TestKnnDirect(unittest.TestCase):
    """测试直接 kNN 查询功能"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = OpenGauss(
            hosts=[{
                'host': db_config['host'],
                'port': db_config['port']
            }],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        cls.test_index = 'test_knn_direct'
        
        # 清理并创建索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except:
            pass
        
        mapping = {
            "mappings": {
                "properties": {
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
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据
        docs = [
            {"id": "1", "body": {"category": "tech", "publish_date": "2024-03-15", "embedding": [0.9, 0.1, 0.1, 0.1]}},
            {"id": "2", "body": {"category": "art", "publish_date": "2024-02-10", "embedding": [0.1, 0.9, 0.1, 0.1]}},
        ]
        
        for doc in docs:
            cls.client.index(index=cls.test_index, id=doc['id'], body=doc['body'])
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(index=cls.test_index)
        finally:
            cls.client.close()
    
    def test_knn_search_with_filter(self):
        """测试 knn_search API 带过滤功能"""
        # 使用 knn_search API（底层接口）带过滤
        filter_query = {
            "bool": {
                "filter": [
                    {"term": {"category": "tech"}}
                ]
            }
        }
        
        print("\nfilter_query:")
        import json
        print(json.dumps(filter_query, indent=2))
        print()
        
        result = self.client.knn_search(
            index=self.test_index,
            field='embedding',
            query_vector=[0.85, 0.15, 0.1, 0.1],
            k=10,
            filter_query=filter_query
        )
        
        # 验证结果
        total = result['hits']['total']['value']
        print(f"找到 {total} 个匹配:")
        for hit in result['hits']['hits']:
            print(f"  - {hit['_id']}: category={hit['_source']['category']}")
        
        # 应该至少找到 1 个结果
        self.assertGreaterEqual(total, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
