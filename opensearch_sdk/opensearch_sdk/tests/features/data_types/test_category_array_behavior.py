#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
其他功能测试 - 数组类别行为

功能说明：
- 验证数组类别字段的匹配行为
- 测试数组字段的查询逻辑

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.other_features.test_category_array_behavior -v
    python opensearch_sdk/tests/other_features/test_category_array_behavior.py
"""

import sys
import os
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

db_config = load_db_config()


class TestSearchByCategoryArray(unittest.TestCase):
    """类别字段数组匹配行为测试"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = OpenGauss(
            hosts=[{'host': db_config['host'], 'port': db_config['port']}],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        
        # 创建测试索引
        cls.test_index = 'test_category_array'
        
        # 先删除已存在的测试索引（如果有）
        if cls.client.indices.exists(index=cls.test_index):
            cls.client.indices.delete(index=cls.test_index)
            print(f"Deleted old test index: {cls.test_index}")
        
        mapping = {
            "mappings": {
                "properties": {
                    "categories": {"type": "text", "index": True},
                    "question": {"type": "text"}
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 为 categories 字段创建 BM25 索引
        try:
            from opensearch_sdk.retrieval import IndexConfig, IndexType
            index_config = IndexConfig(
                name="idx_categories_bm25",
                column="categories",
                index_type=IndexType.BM25,
                parallel_workers=4
            )
            pre_sql = index_config.get_pre_create_sql(cls.test_index)
            if pre_sql:
                cls.client.connection.execute(pre_sql)
            sql = index_config.to_sql(cls.test_index)
            cls.client.connection.execute(sql)
            cls.client.connection.commit()
        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg or "DuplicateTable" in error_msg:
                pass  # 索引已存在，忽略
            else:
                print(f"Warning: BM25 index creation failed: {e}")
            try:
                cls.client.connection.rollback()
            except:
                pass
        
        # 准备测试数据
        cls.prepare_test_data()
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        cls.client.close()
    
    def setUp(self):
        """每个测试前清理并重建 BM25 索引"""
        try:
            self.client.connection.rollback()
        except:
            pass
        
        # 删除并重建 BM25 索引（确保每个测试都在干净的环境中运行）
        try:
            drop_sql = "DROP INDEX IF EXISTS idx_categories_bm25"
            self.client.connection.execute(drop_sql)
            self.client.connection.commit()
        except:
            pass
        
        # 重新创建 BM25 索引
        try:
            from opensearch_sdk.retrieval import IndexConfig, IndexType
            index_config = IndexConfig(
                name="idx_categories_bm25",
                column="categories",
                index_type=IndexType.BM25,
                parallel_workers=4
            )
            pre_sql = index_config.get_pre_create_sql(self.test_index)
            if pre_sql:
                self.client.connection.execute(pre_sql)
            sql = index_config.to_sql(self.test_index)
            self.client.connection.execute(sql)
            self.client.connection.commit()
        except Exception as e:
            print(f"Warning: BM25 index recreation failed: {e}")
            try:
                self.client.connection.rollback()
            except:
                pass
    
    @classmethod
    def prepare_test_data(cls):
        """准备测试数据"""
        test_docs = [
            {
                "id": "doc1",
                "data": {
                    "categories": "one two",  # 使用空格分隔的文本，BM25 索引支持分词
                    "question": "问题 1"
                }
            },
            {
                "id": "doc2",
                "data": {
                    "categories": "two three",  # 使用空格分隔的文本
                    "question": "问题 2"
                }
            },
            {
                "id": "doc3",
                "data": {
                    "categories": "four",  # 单个词
                    "question": "问题 3"
                }
            }
        ]
        
        for doc in test_docs:
            cls.client.index(cls.test_index, doc["id"], doc["data"])
    
    def test_search_first_category(self):
        """搜索第一个类别（one）"""
        query = {
            "query": {
                "match_phrase": {
                    "categories": "one"
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回 doc1
        self.assertEqual(result["hits"]["total"]["value"], 1)
        self.assertEqual(result["hits"]["hits"][0]["_id"], "doc1")
    
    def test_search_second_category(self):
        """搜索第二个类别（two）"""
        query = {
            "query": {
                "match_phrase": {
                    "categories": "two"
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回 doc1 和 doc2（都包含 two）
        self.assertEqual(result["hits"]["total"]["value"], 2)
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc1", hit_ids)
        self.assertIn("doc2", hit_ids)
    
    def test_search_nonexistent_category(self):
        """搜索不存在的类别"""
        query = {
            "query": {
                "match_phrase": {
                    "categories": "nonexistent"
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回空结果
        self.assertEqual(result["hits"]["total"]["value"], 0)
    
    def test_search_partial_match(self):
        """测试部分匹配（全文检索的分词行为）"""
        query = {
            "query": {
                "match_phrase": {
                    "categories": "o"  # 只搜索字母 o
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 注意：全文检索基于分词匹配，不是 LIKE '%o%'
        # 单字母 "o" 不会匹配 "one"、"two"、"four" 等完整词
        # 因此应该返回空结果
        self.assertEqual(result["hits"]["total"]["value"], 0)
    


if __name__ == '__main__':
    unittest.main()
