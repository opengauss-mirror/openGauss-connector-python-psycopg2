#!/usr/bin/env python
# -*-coding:utf-8 -*-
"""
测试 _source.includes/excludes 功能

测试场景：
1. includes - 只包含指定字段（SQL 层优化）
2. excludes - 排除指定字段（Python 层后过滤）
3. _source: false - 只返回 id
4. 通配符模式匹配
"""

import unittest
import json
from pathlib import Path
from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestSourceFiltering(unittest.TestCase):
    """测试 _source 过滤功能"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        cls.db_config = load_db_config()
        cls.client = OpenGauss(**cls.db_config)
        cls.test_index = "test_source_filter"
        
        # 清理旧索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
        
        # 创建测试索引
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "category": {"type": "keyword"},
                    "author": {"type": "keyword"},
                    "publish_date": {"type": "date"},
                    "view_count": {"type": "integer"},
                    "vector_field": {"type": "knn_vector", "dims": 4}
                }
            }
        }
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据
        test_docs = [
            {
                "id": "doc1",
                "body": {
                    "title": "测试文档 1",
                    "content": "这是第一个测试文档的内容",
                    "category": "技术",
                    "author": "张三",
                    "publish_date": "2024-01-01",
                    "view_count": 100,
                    "vector_field": [0.1, 0.2, 0.3, 0.4]
                }
            },
            {
                "id": "doc2",
                "body": {
                    "title": "测试文档 2",
                    "content": "这是第二个测试文档",
                    "category": "科学",
                    "author": "李四",
                    "publish_date": "2024-02-01",
                    "view_count": 200,
                    "vector_field": [0.5, 0.6, 0.7, 0.8]
                }
            },
            {
                "id": "doc3",
                "body": {
                    "title": "测试文档 3",
                    "content": "第三个文档",
                    "category": "技术",
                    "author": "王五",
                    "publish_date": "2024-03-01",
                    "view_count": 300,
                    "vector_field": [0.9, 1.0, 0.1, 0.2]
                }
            }
        ]
        
        for doc in test_docs:
            cls.client.index(
                index=cls.test_index,
                id=doc["id"],
                body=doc["body"]
            )
        
        print(f"\n[SETUP] 创建测试索引 '{cls.test_index}' 并插入 {len(test_docs)} 条数据")
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理"""
        try:
            cls.client.indices.delete(index=cls.test_index)
            print(f"[TEARDOWN] 删除测试索引 '{cls.test_index}'")
        except Exception:
            pass
        cls.client.close()
    
    def test_01_includes_basic(self):
        """测试 includes - 只包含指定字段"""
        query = {
            "_source": {
                "includes": ["title", "content"]
            },
            "query": {
                "match_all": {}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        self.assertEqual(len(hits), 3)
        
        # 验证只返回了 title 和 content（以及自动添加的 id）
        for hit in hits:
            source = hit['_source']
            self.assertIn('title', source)
            self.assertIn('content', source)
            # 其他字段不应该存在
            self.assertNotIn('category', source)
            self.assertNotIn('author', source)
            self.assertNotIn('vector_field', source)
        
        print("[PASS] includes 基础测试通过")
    
    def test_02_excludes_basic(self):
        """测试 excludes - 排除指定字段（Python 层过滤）"""
        query = {
            "_source": {
                "excludes": ["vector_field"]
            },
            "query": {
                "match_all": {}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        self.assertEqual(len(hits), 3)
        
        # 验证 vector_field 被排除
        for hit in hits:
            source = hit['_source']
            self.assertNotIn('vector_field', source)
            # 其他字段应该存在
            self.assertIn('title', source)
            self.assertIn('content', source)
            self.assertIn('category', source)
        
        print("[PASS] excludes 基础测试通过")
    
    def test_03_excludes_multiple_fields(self):
        """测试 excludes - 排除多个字段"""
        query = {
            "_source": {
                "excludes": ["vector_field", "view_count", "publish_date"]
            },
            "query": {
                "match_all": {}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        for hit in hits:
            source = hit['_source']
            self.assertNotIn('vector_field', source)
            self.assertNotIn('view_count', source)
            self.assertNotIn('publish_date', source)
            # 基本字段应该存在
            self.assertIn('title', source)
            self.assertIn('content', source)
        
        print("[PASS] excludes 多个字段测试通过")
    
    def test_04_source_false(self):
        """测试 _source: false - 只返回 id"""
        query = {
            "_source": False,
            "query": {
                "match_all": {}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        self.assertEqual(len(hits), 3)
        
        # 验证只返回了 id，没有 _source
        for hit in hits:
            # _source 应该是空字典或者不存在任何字段
            source = hit.get('_source', {})
            self.assertEqual(len(source), 0)
        
        print("[PASS] _source: false 测试通过")
    
    def test_05_wildcard_pattern(self):
        """测试通配符模式匹配"""
        query = {
            "_source": {
                "includes": ["*_date", "*_count"]  # 匹配 publish_date 和 view_count
            },
            "query": {
                "match_all": {}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        for hit in hits:
            source = hit['_source']
            # 应该包含匹配的字段
            self.assertIn('publish_date', source)
            self.assertIn('view_count', source)
            # 不应该包含其他字段
            self.assertNotIn('title', source)
            self.assertNotIn('content', source)
        
        print("[PASS] 通配符模式测试通过")
    
    def test_06_combined_includes_excludes(self):
        """测试 includes 和 excludes 组合（includes 优先）"""
        # 根据 OpenSearch 规范，当同时指定 includes 和 excludes 时
        # includes 优先生效
        query = {
            "_source": {
                "includes": ["title", "content", "category"],
                "excludes": ["category"]  # 这个会被忽略
            },
            "query": {
                "match_all": {}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        for hit in hits:
            source = hit['_source']
            # includes 优先，所以 category 应该存在
            self.assertIn('title', source)
            self.assertIn('content', source)
            self.assertIn('category', source)
        
        print("[PASS] includes+excludes 组合测试通过")
    
    def test_07_with_bool_query(self):
        """测试与 bool 查询组合使用"""
        query = {
            "_source": {
                "excludes": ["vector_field"]
            },
            "query": {
                "bool": {
                    "must": [
                        {"term": {"category": "技术"}}
                    ]
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        # 应该只返回 category=技术 的文档
        self.assertEqual(len(hits), 2)
        
        for hit in hits:
            source = hit['_source']
            self.assertEqual(source['category'], '技术')
            self.assertNotIn('vector_field', source)
        
        print("[PASS] 与 bool 查询组合测试通过")
    
    def test_08_performance_comparison(self):
        """性能对比测试（可选，展示优化效果）"""
        import time
        
        # 不使用 includes - 返回所有字段
        start = time.time()
        query_all = {
            "query": {"match_all": {}}
        }
        result_all = self.client.search(index=self.test_index, body=query_all)
        time_all = time.time() - start
        
        # 使用 includes - 只返回部分字段
        start = time.time()
        query_filtered = {
            "_source": {
                "includes": ["title", "content"]
            },
            "query": {"match_all": {}}
        }
        result_filtered = self.client.search(index=self.test_index, body=query_filtered)
        time_filtered = time.time() - start
        
        print(f"\n[PERF] 全量查询耗时：{time_all*1000:.2f}ms")
        print(f"[PERF] 过滤查询耗时：{time_filtered*1000:.2f}ms")
        print(f"[INFO] 性能提升：{((time_all - time_filtered) / time_all * 100):.1f}%")
        
        # 验证结果正确性
        self.assertEqual(len(result_all['hits']['hits']), 3)
        self.assertEqual(len(result_filtered['hits']['hits']), 3)
        
        print("[PASS] 性能对比测试完成")


if __name__ == '__main__':
    unittest.main()
