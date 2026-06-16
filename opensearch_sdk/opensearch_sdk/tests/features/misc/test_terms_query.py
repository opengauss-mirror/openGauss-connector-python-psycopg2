#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Terms 查询测试 - 多值匹配功能

功能说明：
- terms 查询功能全面测试
- 验证 OpenSearch API 标准的 terms 查询
- 测试多值匹配的 OR 逻辑

运行方式：
    python -m unittest opensearch_sdk.tests.features.misc.test_terms_query -v
"""

import sys
import os
import json
import unittest
from pathlib import Path
from opensearch_sdk.tests.utils.config_loader import load_db_config

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opensearch_sdk.client.base import OpenGaussClient
from opensearch_sdk.retrieval import IndexConfig, IndexType



class TestTermsQuery(unittest.TestCase):
    """测试 Terms 查询功能"""
    
    @classmethod
    def _execute_sql(cls, sql):
        """在单独连接中执行 SQL"""
        try:
            with cls.client.connection.get_connection_for_operation() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
        except Exception:
            pass

    @classmethod
    def _create_bm25_index(cls, field):
        """为字段创建 BM25 索引"""
        try:
            index_config = IndexConfig(
                name=f"idx_{field}_bm25",
                column=field,
                index_type=IndexType.BM25,
                parallel_workers=4
            )
            pre_sql = index_config.get_pre_create_sql(cls.test_index)
            if pre_sql:
                cls._execute_sql(pre_sql)
            sql = index_config.to_sql(cls.test_index)
            cls._execute_sql(sql)
        except Exception:
            pass

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
        
        cls.test_index = 'test_terms_query'
        
        # 清理旧索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except:
            pass
        
        # 创建索引
        mapping = {
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                }
            },
            "mappings": {
                "properties": {
                    "title": {"type": "text", "analyzer": "simple"},
                    "category": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    "price": {"type": "integer"}
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 创建 BM25 索引
        for field in ['category', 'tags']:
            cls._create_bm25_index(field)
        
        # 插入测试数据
        cls.docs = [
            {"id": "doc1", "body": {"title": "Product A", "category": "electronics", "tags": ["sale", "new"], "price": 100}},
            {"id": "doc2", "body": {"title": "Product B", "category": "books", "tags": ["sale"], "price": 50}},
            {"id": "doc3", "body": {"title": "Product C", "category": "electronics", "tags": ["new", "hot"], "price": 200}},
            {"id": "doc4", "body": {"title": "Product D", "category": "clothing", "tags": ["sale", "hot"], "price": 80}},
            {"id": "doc5", "body": {"title": "Product E", "category": "books", "tags": ["new"], "price": 30}},
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
        finally:
            # [FIX] 确保关闭客户端连接
            try:
                cls.client.close()
            except:
                pass
    
    def test_01_basic_terms_query(self):
        """测试基础 terms 查询 - category IN ['electronics', 'books']"""
        query = {
            "query": {
                "terms": {
                    "category": ["electronics", "books"]
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        expected = {'doc1', 'doc2', 'doc3', 'doc5'}
        actual = {hit['_id'] for hit in hits}
        
        self.assertEqual(actual, expected, f"期望 {expected}, 实际 {actual}")
        print(f"\n[PASS] 基础 terms 查询通过，找到 {len(hits)} 个匹配")
    
    def test_02_terms_array_field(self):
        """测试 terms 查询数组字段 - tags IN ['sale', 'hot']"""
        query = {
            "query": {
                "terms": {
                    "tags": ["sale", "hot"]
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        expected = {'doc1', 'doc2', 'doc3', 'doc4'}
        actual = {hit['_id'] for hit in hits}
        
        self.assertEqual(actual, expected, f"期望 {expected}, 实际 {actual}")
        print(f"\n[PASS] 数组字段 terms 查询通过，找到 {len(hits)} 个匹配")
    
    def test_03_terms_numeric_field(self):
        """测试 terms 查询数值字段 - price IN [50, 100]"""
        query = {
            "query": {
                "terms": {
                    "price": [50, 100]
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        expected = {'doc1', 'doc2'}
        actual = {hit['_id'] for hit in hits}
        
        self.assertEqual(actual, expected, f"期望 {expected}, 实际 {actual}")
        print(f"\n[PASS] 数值字段 terms 查询通过，找到 {len(hits)} 个匹配")
    
    def test_04_terms_in_bool_must(self):
        """测试 bool.must 中的 terms 查询"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "terms": {
                                "category": ["electronics", "clothing"]
                            }
                        }
                    ]
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        expected = {'doc1', 'doc3', 'doc4'}
        actual = {hit['_id'] for hit in hits}
        
        self.assertEqual(actual, expected, f"期望 {expected}, 实际 {actual}")
        print(f"\n[PASS] bool.must 中的 terms 查询通过，找到 {len(hits)} 个匹配")
    
    def test_05_terms_in_bool_filter(self):
        """测试 bool.filter 中的 terms 查询"""
        query = {
            "query": {
                "bool": {
                    "filter": [
                        {
                            "terms": {
                                "category": ["electronics", "books"]
                            }
                        }
                    ]
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        expected = {'doc1', 'doc2', 'doc3', 'doc5'}
        actual = {hit['_id'] for hit in hits}
        
        self.assertEqual(actual, expected, f"期望 {expected}, 实际 {actual}")
        print(f"\n[PASS] bool.filter 中的 terms 查询通过，找到 {len(hits)} 个匹配")
    
    def test_06_single_value_terms(self):
        """测试单个值的 terms 查询"""
        query = {
            "query": {
                "terms": {
                    "category": ["electronics"]
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        expected = {'doc1', 'doc3'}
        actual = {hit['_id'] for hit in hits}
        
        self.assertEqual(actual, expected, f"期望 {expected}, 实际 {actual}")
        print(f"\n[PASS] 单值 terms 查询通过，找到 {len(hits)} 个匹配")


if __name__ == '__main__':
    unittest.main()
