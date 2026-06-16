#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
词序颠倒匹配测试 - match_phrase gap 参数

功能说明：
- 测试词序颠倒的 match_phrase 查询
- 验证 gap 参数对词序的容忍度
- 测试反向词序匹配

运行方式：
    python -m unittest opensearch_sdk.tests.features.advanced.test_reversed_order -v
"""

import sys
import os
import json
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opensearch_sdk.client.base import OpenGaussClient
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestReversedOrder(unittest.TestCase):
    """测试词序颠倒匹配"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        db_config = load_db_config()
        cls.client = OpenGaussClient(
            hosts=[{
                'host': db_config['host'],
                'port': db_config['port']
            }],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        
        cls.test_index = 'test_reversed_order'
        
        # 清理旧索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except:
            pass
        
        # 创建索引
        mapping = {
            "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
            "mappings": {
                "properties": {
                    "title": {"type": "text", "analyzer": "simple"}
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据
        cls.docs = [
            {"id": "doc1", "body": {"title": "the fox is quick and brown"}},  # fox ... quick (间隔 2 词)
            {"id": "doc2", "body": {"title": "quick brown fox"}},  # quick ... fox (顺序)
            {"id": "doc3", "body": {"title": "the quick brown fox"}},  # quick ... fox (顺序)
        ]
        
        for doc in cls.docs:
            cls.client.index(index=cls.test_index, id=doc['id'], body=doc['body'])
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(index=cls.test_index)
        except:
            pass
    
    def test_01_reversed_order_with_gap(self):
        """测试词序颠倒查询 'fox quick' (slop=2)"""
        query = {
            "query": {
                "match_phrase": {
                    "title": {
                        "query": "fox quick",
                        "slop": 2
                    }
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        print(f"\n找到 {len(hits)} 个匹配:")
        for hit in hits:
            print(f"  - {hit['_id']}: {hit['_source']['title']}")
        
        # 期望只匹配 doc1 (fox 在 quick 前面，间隔 2 个词)
        self.assertEqual(len(hits), 1, f"期望 1 个结果，实际 {len(hits)}")
        self.assertEqual(hits[0]['_id'], 'doc1', "应该匹配 doc1")
        
        print(f"\n[PASS] 正确匹配 doc1 (fox 在 quick 前面，间隔 2 个词)")


if __name__ == '__main__':
    unittest.main()
