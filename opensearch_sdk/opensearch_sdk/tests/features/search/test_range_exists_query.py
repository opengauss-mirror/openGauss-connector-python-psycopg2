#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Range 和 Exists 查询测试

功能说明：
- 测试范围查询功能 (range)
- 测试存在性查询功能 (exists)
- 验证各种范围操作符

运行方式：
    python -m unittest opensearch_sdk.tests.features.search.test_range_exists_query -v
"""

import json
import os
import unittest
from pathlib import Path
import sys
from opensearch_sdk.tests.utils.config_loader import load_db_config

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opensearch_sdk import OpenGauss


class TestRangeExistsQuery(unittest.TestCase):
    """测试 Range 和 Exists 查询"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        db_config = load_db_config()
        cls.client = OpenGauss(
            hosts=[{
                'host': db_config.get('host', os.getenv('DB_HOST', 'localhost')),
                'port': db_config.get('port', int(os.getenv('DB_PORT', '5432'))),
            }],
            database=db_config.get('database', os.getenv('DB_NAME', 'postgres')),
            user=db_config.get('user', os.getenv('DB_USER', 'postgres')),
            password=db_config.get('password', os.getenv('DB_PASSWORD'))
        )
        cls.test_index = "test_range_exists"
        
        # 删除旧索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
        
        # 创建索引
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "price": {"type": "float"},
                    "quantity": {"type": "integer"},
                    "category": {"type": "keyword"}
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据
        cls.test_docs = [
            {"id": "doc1", "body": {"title": "商品 A", "price": 50.0, "quantity": 10, "category": "electronics"}},
            {"id": "doc2", "body": {"title": "商品 B", "price": 100.0, "quantity": 20}},
            {"id": "doc3", "body": {"title": "商品 C", "price": 150.0, "quantity": 30, "category": "books"}},
            {"id": "doc4", "body": {"title": "商品 D", "price": 200.0, "quantity": 40}},
            {"id": "doc5", "body": {"title": "商品 E", "price": 250.0, "quantity": 50, "category": "electronics"}},
        ]
        
        for doc in cls.test_docs:
            cls.client.create(index=cls.test_index, id=doc["id"], body=doc["body"])
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
    
    def test_01_range_gte_lte(self):
        """测试 range gte 和 lte (>= and <=)"""
        response = self.client.search(
            index=self.test_index,
            body={
                "query": {
                    "range": {
                        "price": {
                            "gte": 100,
                            "lte": 200
                        }
                    }
                }
            }
        )
        
        hits = response['hits']['hits']
        self.assertEqual(len(hits), 3, f"预期 3 个结果，实际 {len(hits)} 个")
        self.assertTrue(all(100 <= h['_source']['price'] <= 200 for h in hits))
        print(f"\n[PASS] range gte/lte 测试通过，找到 {len(hits)} 个匹配")
    
    def test_02_range_gt_lt(self):
        """测试 range gt 和 lt (> and <)"""
        response = self.client.search(
            index=self.test_index,
            body={
                "query": {
                    "range": {
                        "price": {
                            "gt": 100,
                            "lt": 250
                        }
                    }
                }
            }
        )
        
        hits = response['hits']['hits']
        self.assertEqual(len(hits), 2, f"预期 2 个结果，实际 {len(hits)} 个")
        self.assertTrue(all(100 < h['_source']['price'] < 250 for h in hits))
        print(f"\n[PASS] range gt/lt 测试通过，找到 {len(hits)} 个匹配")
    
    def test_03_exists_query(self):
        """测试 exists 查询"""
        response = self.client.search(
            index=self.test_index,
            body={
                "query": {
                    "exists": {
                        "field": "category"
                    }
                }
            }
        )
        
        hits = response['hits']['hits']
        # 只有 doc1, doc3, doc5 有 category 字段
        self.assertEqual(len(hits), 3, f"预期 3 个结果，实际 {len(hits)} 个")
        self.assertTrue(all('category' in h['_source'] for h in hits))
        print(f"\n[PASS] exists 查询测试通过，找到 {len(hits)} 个匹配")
    
    def test_04_range_with_integer(self):
        """测试整数范围的 range 查询"""
        response = self.client.search(
            index=self.test_index,
            body={
                "query": {
                    "range": {
                        "quantity": {
                            "gte": 20,
                            "lte": 40
                        }
                    }
                }
            }
        )
        
        hits = response['hits']['hits']
        self.assertEqual(len(hits), 3, f"预期 3 个结果，实际 {len(hits)} 个")
        self.assertTrue(all(20 <= h['_source']['quantity'] <= 40 for h in hits))
        print(f"\n[PASS] 整数 range 查询测试通过，找到 {len(hits)} 个匹配")


if __name__ == '__main__':
    unittest.main()
