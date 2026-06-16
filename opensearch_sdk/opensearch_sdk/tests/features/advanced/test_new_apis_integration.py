#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
其他功能测试 - 新 API 集成

功能说明：
- vector_search 和 fulltext_search API 的集成测试
- 基于 unittest 框架的测试
- 验证新 API 的正确性

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.other_features.test_new_apis_integration -v
    python opensearch_sdk/tests/other_features/test_new_apis_integration.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from opensearch_sdk import OpenGauss
from opensearch_sdk.retrieval import DistanceMetric, IndexConfig, IndexType
from opensearch_sdk.tests.utils.config_loader import load_db_config


TEST_VECTOR_INDEX = 'test_vector_search'
TEST_FULLTEXT_INDEX = 'test_fulltext_search'


class TestNewAPIsIntegration(unittest.TestCase):
    """vector_search 和 fulltext_search API 集成测试"""

    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        # 加载数据库配置
        cls.db_config = load_db_config()
        # 初始化客户端
        cls.client = OpenGauss(
            hosts=[{
                "host": cls.db_config['host'],
                "port": cls.db_config['port']
            }],
            database=cls.db_config['database'],
            user=cls.db_config['user'],
            password=cls.db_config['password']
        )

        # 清理可能存在的旧测试索引
        cls._cleanup_test_indices()

    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        cls._cleanup_test_indices()
        cls.client.close()

    def setUp(self):
        """每个测试前清理，确保环境干净"""
        self._rollback_connection()
        self._cleanup_test_indices()

    def tearDown(self):
        """每个测试后清理，确保事务正常"""
        self._rollback_connection()
        self._cleanup_test_indices()

    def _rollback_connection(self):
        try:
            self.client.connection.rollback()
        except Exception:
            pass

    @classmethod
    def _cleanup_test_indices(cls):
        """清理测试索引"""
        test_indices = [TEST_VECTOR_INDEX, TEST_FULLTEXT_INDEX]
        for index_name in test_indices:
            try:
                if cls.client.indices.exists(index=index_name):
                    cls.client.indices.delete(index=index_name)
            except Exception:
                pass

    @staticmethod
    def _vector_mapping():
        return {
            "mappings": {
                "properties": {
                    "title": {"type": "keyword"},
                    "embedding": {"type": "float_vector", "dims": 3},
                    "category": {"type": "keyword"}
                }
            }
        }

    @staticmethod
    def _vector_docs(limit=None):
        docs = [
            {"title": "openGauss 教程", "embedding": [0.1, 0.2, 0.3], "category": "tech"},
            {"title": "Python 编程", "embedding": [0.2, 0.3, 0.4], "category": "tech"},
            {"title": "机器学习入门", "embedding": [0.3, 0.4, 0.5], "category": "ai"},
            {"title": "深度学习详解", "embedding": [0.4, 0.5, 0.6], "category": "ai"},
            {"title": "数据库原理", "embedding": [0.5, 0.6, 0.7], "category": "tech"}
        ]
        return docs[:limit] if limit else docs

    @staticmethod
    def _fulltext_mapping():
        return {
            "mappings": {
                "properties": {
                    "title": {"type": "keyword"},
                    "content": {"type": "text"},
                    "category": {"type": "keyword"}
                }
            }
        }

    @staticmethod
    def _fulltext_docs(limit=None):
        docs = [
            {"title": "openGauss 数据库教程", "content": "openGauss 是一款开源的关系型数据库管理系统，支持 SQL 查询和事务处理", "category": "tech"},
            {"title": "Python 编程指南", "content": "Python 是一门高级编程语言，简洁易学，广泛应用于 Web 开发、数据科学和人工智能领域", "category": "tech"},
            {"title": "机器学习基础", "content": "机器学习是人工智能的核心技术，通过训练模型让计算机具备学习和预测能力", "category": "ai"},
            {"title": "深度学习详解", "content": "深度学习使用神经网络模拟人脑，在图像识别、自然语言处理等领域取得突破性进展", "category": "ai"},
            {"title": "数据库优化技巧", "content": "数据库性能优化包括索引设计、查询优化、缓存策略等多个方面", "category": "tech"}
        ]
        return docs[:limit] if limit else docs

    def _insert_docs(self, table_name, docs):
        for i, doc in enumerate(docs, 1):
            self.client.create(index=table_name, id=str(i), body=doc)

    def _create_index_safely(self, table_name, index_config, use_pre_sql=False):
        try:
            pre_sql = index_config.get_pre_create_sql(table_name) if use_pre_sql else None
            if pre_sql:
                self.client.connection.execute(pre_sql)
            self.client.connection.execute(index_config.to_sql(table_name))
            self.client.connection.commit()
        except Exception as e:
            error_msg = str(e)
            if "already exists" not in error_msg and "DuplicateTable" not in error_msg:
                print(f"Warning: 索引创建失败：{e}")
            try:
                self.client.connection.rollback()
            except Exception:
                pass

    def _create_vector_table(self, table_name, doc_limit=None):
        self.client.indices.create(index=table_name, body=self._vector_mapping())
        self._insert_docs(table_name, self._vector_docs(doc_limit))
        index_config = IndexConfig(
            name="idx_embedding_hnsw",
            column="embedding",
            index_type=IndexType.HNSW,
            metric=DistanceMetric.COSINE,
            m=16,
            ef_construction=64
        )
        self._create_index_safely(table_name, index_config)

    def _create_fulltext_table(self, table_name, doc_limit=None):
        self.client.indices.create(index=table_name, body=self._fulltext_mapping())
        self._insert_docs(table_name, self._fulltext_docs(doc_limit))
        index_config = IndexConfig(
            name="idx_content_bm25",
            column="content",
            index_type=IndexType.BM25,
            parallel_workers=4
        )
        self._create_index_safely(table_name, index_config, use_pre_sql=True)

    def _vector_search(self, table_name, top_k=3, metric="cosine", **kwargs):
        return self.client.vector_search(
            index=table_name,
            query_vector=[0.15, 0.25, 0.35],
            vector_column="embedding",
            top_k=top_k,
            metric=metric,
            **kwargs
        )

    def _fulltext_search(self, table_name, query_text, top_k=3, **kwargs):
        return self.client.fulltext_search(
            index=table_name,
            query_text=query_text,
            text_column="content",
            top_k=top_k,
            **kwargs
        )

    def _assert_hits_category(self, results, category):
        for hit in results['hits']['hits']:
            self.assertEqual(hit['_source']['category'], category)

    def _assert_source_fields(self, results, excluded_field, included_fields):
        for hit in results['hits']['hits']:
            self.assertNotIn(excluded_field, hit['_source'], f"{excluded_field} should not be in _source")
            for field in included_fields:
                self.assertIn(field, hit['_source'])

    def test_01_vector_search_basic(self):
        """测试 1: 基础向量搜索"""
        table_name = TEST_VECTOR_INDEX
        self._create_vector_table(table_name)
        results = self._vector_search(table_name)

        # 验证结果
        self.assertEqual(results['hits']['total']['value'], 3, "Should return 3 results")
        self.assertEqual(len(results['hits']['hits']), 3)

    def test_02_vector_search_with_filter(self):
        """测试 2: 带过滤条件的向量搜索"""
        table_name = TEST_VECTOR_INDEX
        self._create_vector_table(table_name)
        results = self._vector_search(
            table_name,
            top_k=5,
            filter_query={"term": {"category": "ai"}}
        )

        # 验证结果
        self.assertLessEqual(results['hits']['total']['value'], 2, "Should return at most 2 AI results")
        self._assert_hits_category(results, 'ai')

    def test_03_vector_search_output_columns(self):
        """测试 3: 向量搜索的输出列控制"""
        table_name = TEST_VECTOR_INDEX
        self._create_vector_table(table_name, doc_limit=3)
        results = self._vector_search(
            table_name,
            metric="l2_norm",
            output_columns=["title", "category"]
        )
        self._assert_source_fields(results, 'embedding', ['title', 'category'])

    def test_04_fulltext_search_basic(self):
        """测试 4: 基础全文搜索"""
        table_name = TEST_FULLTEXT_INDEX
        self._create_fulltext_table(table_name)
        results = self._fulltext_search(table_name, "数据库")

        # 验证结果
        self.assertGreaterEqual(results['hits']['total']['value'], 1, "Should find at least 1 result")

    def test_05_fulltext_search_with_filter(self):
        """测试 5: 带过滤条件的全文搜索"""
        table_name = TEST_FULLTEXT_INDEX
        self._create_fulltext_table(table_name)
        results = self._fulltext_search(
            table_name,
            "学习",
            top_k=5,
            filter_query={"term": {"category": "ai"}}
        )
        self._assert_hits_category(results, 'ai')

    def test_06_fulltext_search_output_columns(self):
        """测试 6: 全文搜索的输出列控制"""
        table_name = TEST_FULLTEXT_INDEX
        self._create_fulltext_table(table_name, doc_limit=3)
        results = self._fulltext_search(
            table_name,
            "人工智能",
            output_columns=["title", "category"]
        )
        self._assert_source_fields(results, 'content', ['title', 'category'])

    def test_07_fulltext_search_custom_bm25_params(self):
        """测试 7: 自定义 BM25 参数"""
        table_name = TEST_FULLTEXT_INDEX
        self._create_fulltext_table(table_name, doc_limit=3)
        results = self._fulltext_search(
            table_name,
            "Python 编程",
            bm25_k1=1.5,
            bm25_b=0.75
        )

        # 验证返回结果
        self.assertGreaterEqual(results['hits']['total']['value'], 1, "Should find at least 1 result")


if __name__ == "__main__":
    unittest.main()
