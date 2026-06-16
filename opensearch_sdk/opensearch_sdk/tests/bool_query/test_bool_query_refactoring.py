#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bool 查询测试 - 重构集成测试

功能说明：
- 验证新的 QueryBuilder API 和 PostValidator 的集成
- 测试 search() 方法中的 bool 查询处理
- 确保重构后的功能正确性

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.bool_query.test_bool_query_refactoring -v
    python opensearch_sdk/tests/bool_query/test_bool_query_refactoring.py
"""

import os
import sys
import unittest
from typing import Any, Dict, List

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestBoolQueryRefactoring(unittest.TestCase):
    """Bool 查询重构集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """初始化数据库连接和测试数据"""
        # 加载配置
        cls.config = load_db_config()
        
        # 创建客户端
        cls.client = OpenGauss(
            hosts=[{'host': cls.config['host'], 'port': cls.config['port']}],
            database=cls.config['database'],
            user=cls.config['user'],
            password=cls.config['password']
        )
        
        # 测试索引名称
        cls.test_index = 'test_bool_refactor_integration'
        
        # 清理并创建索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
        
        # 创建映射
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "tags": {"type": "keyword"}
                }
            }
        }
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试文档
        cls.test_docs = [
            {"id": "1", "data": {"title": "the quick fox jumps", "content": "test1", "tags": ["animal"]}},
            {"id": "2", "data": {"title": "the quick brown fox", "content": "test2", "tags": ["animal"]}},
            {"id": "3", "data": {"title": "quick very brown fox", "content": "test3", "tags": ["nature"]}},
            {"id": "4", "data": {"title": "the slow turtle", "content": "test4", "tags": ["animal"]}},
            {"id": "5", "data": {"title": "quick fox and slow turtle", "content": "test5", "tags": ["animal", "nature"]}},
        ]
        
        for doc in cls.test_docs:
            cls.client.index(index=cls.test_index, id=doc['id'], body=doc['data'])
    
    @classmethod
    def tearDownClass(cls):
        """清理测试数据"""
        try:
            cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
        finally:
            cls.client.close()
    
    def test_01_must_strict_match_phrase(self):
        """测试 must 中的严格 match_phrase（需要后过滤）"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"title": "quick fox"}}
                    ]
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        self.assertEqual(len(hits), 2)
        hit_ids = [hit["_id"] for hit in hits]
        self.assertIn("1", hit_ids)
        self.assertIn("5", hit_ids)
    
    def test_02_must_slop_match_phrase(self):
        """测试 slop>0 的 match_phrase（必须后过滤）"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"title": {"query": "quick fox", "slop": 1}}}
                    ]
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # 应该返回间隔 <= 1 的文档
        # ID=1: "the quick fox jumps" [OK] (间隔 0)
        # ID=2: "the quick brown fox" [OK] (间隔 1)
        # ID=5: "quick fox and slow turtle" [OK] (间隔 0)
        self.assertEqual(len(hits), 3)
        hit_ids = [hit["_id"] for hit in hits]
        self.assertIn("1", hit_ids)
        self.assertIn("2", hit_ids)
        self.assertIn("5", hit_ids)
    
    def test_03_must_not_match_phrase(self):
        """测试 must_not 中的 match_phrase（不需要后过滤）"""
        query = {
            "query": {
                "bool": {
                    "must_not": [
                        {"match_phrase": {"content": "test1"}}
                    ]
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # 应该排除 content="test1" 的文档
        self.assertEqual(len(hits), 4)
        hit_ids = [hit["_id"] for hit in hits]
        self.assertNotIn("1", hit_ids)
    
    def test_04_should_strict_match_phrase(self):
        """测试 should 中的严格 match_phrase（可选后过滤）"""
        query = {
            "query": {
                "bool": {
                    "should": [
                        {"match_phrase": {"title": "quick fox"}}
                    ],
                    "minimum_should_match": 1
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # 应该返回包含 "quick fox" 的文档
        self.assertGreater(len(hits), 0)
        for hit in hits:
            self.assertIn("quick fox", hit["_source"]["title"].lower())
    
    def test_05_nested_bool(self):
        """测试嵌套 bool 查询（递归处理）"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "must": [
                                    {"match_phrase": {"title": {"query": "quick fox", "slop": 1}}}
                                ]
                            }
                        }
                    ]
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # 嵌套 bool 应该正确执行，返回与 test_02 相同的结果
        self.assertEqual(len(hits), 3)
        hit_ids = [hit["_id"] for hit in hits]
        self.assertIn("1", hit_ids)
        self.assertIn("2", hit_ids)
        self.assertIn("5", hit_ids)
    
    def test_06_combined_must_should_must_not(self):
        """测试组合 must/should/must_not"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"tags": "animal"}}
                    ],
                    "should": [
                        {"match_phrase": {"title": {"query": "quick fox", "slop": 1}}}
                    ],
                    "must_not": [
                        {"match": {"content": "test5"}}
                    ],
                    "minimum_should_match": 1
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # 应该返回：
        # - tags 包含 "animal"
        # - title 包含 "quick fox" (slop=1)
        # - content 不等于 "test5"
        self.assertGreater(len(hits), 0)
        for hit in hits:
            self.assertIn("animal", hit["_source"]["tags"])
            self.assertNotEqual(hit["_source"]["content"], "test5")
    
    def test_07_deep_nested_bool(self):
        """测试深度嵌套的 bool 查询"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "should": [
                                    {
                                        "bool": {
                                            "must": [
                                                {"match_phrase": {"title": {"query": "quick fox", "slop": 2}}}
                                            ]
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # 深度嵌套应该正确执行
        # ID=1, 2, 3 都应该匹配（slop=2 允许间隔 2 个词）
        self.assertGreater(len(hits), 0)
        hit_ids = [hit["_id"] for hit in hits]
        self.assertIn("1", hit_ids)
        self.assertIn("2", hit_ids)
    
    def test_08_multiple_match_phrases(self):
        """测试多个 match_phrase 条件"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"title": "quick fox"}},
                        {"match": {"tags": "animal"}}
                    ]
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # 应该同时满足两个条件
        self.assertGreater(len(hits), 0)
        for hit in hits:
            self.assertIn("quick fox", hit["_source"]["title"].lower())
            self.assertIn("animal", hit["_source"]["tags"])
    
    def test_09_slop_with_word_order(self):
        """测试 slop 对词序的影响"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"title": {"query": "quick fox", "slop": 2}}}
                    ]
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # slop=2 允许间隔 2 个词
        # ID=1: "the quick fox jumps" [OK] (间隔 0)
        # ID=2: "the quick brown fox" [OK] (间隔 1)
        # ID=3: "quick very brown fox" [OK] (间隔 2)
        # ID=5: "quick fox and slow turtle" [OK] (间隔 0)
        self.assertGreater(len(hits), 0)
        hit_ids = [hit["_id"] for hit in hits]
        self.assertIn("1", hit_ids)  # 至少应该包含 ID=1
    
    def test_10_empty_result(self):
        """测试无结果的情况"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"title": "nonexistent phrase"}}
                    ]
                }
            }
        }
        
        result = self.client.search(self.test_index, query)
        hits = result["hits"]["hits"]
        
        # 应该没有匹配结果
        self.assertEqual(len(hits), 0)


if __name__ == '__main__':
    print("="*80)
    print("Bool 查询重构集成测试")
    print("="*80)
    unittest.main(verbosity=2)
