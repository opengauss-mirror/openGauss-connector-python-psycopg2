#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
向量搜索测试 - kNN 搜索

功能说明：
- 基本 kNN 查询功能
- 不同相似度算法的查询
- 带过滤条件的 kNN 查询
- 边界条件验证

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.vector_search.test_knn_search -v
    python opensearch_sdk/tests/vector_search/test_knn_search.py
"""

import os
import sys
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


TEST_INDEX = 'test_knn_index'
COSINE_QUERY_VECTOR = [0.85, 0.15, 0.1, 0.1]
MIXED_QUERY_VECTOR = [0.5, 0.5, 0.3, 0.3]
DOC_ONE_TITLE = 'Product One'


def _vector_field(space_type):
    return {
        "type": "knn_vector",
        "dimension": 4,
        "space_type": space_type,
        "method": {
            "name": "hnsw"
        }
    }


def _test_mapping():
    return {
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "category": {"type": "keyword"},
                "price": {"type": "float"},
                "embedding_cosine": _vector_field("cosinesimil"),
                "embedding_l2": _vector_field("l2"),
                "embedding_dotprod": _vector_field("innerproduct")
            }
        }
    }


def _test_documents():
    return [
        {
            "title": "Product One",
            "category": "electronics",
            "price": 99.99,
            "embedding_cosine": [0.9, 0.1, 0.1, 0.1],
            "embedding_l2": [1.0, 0.0, 0.0, 0.0],
            "embedding_dotprod": [1.0, 0.0, 0.0, 0.0]
        },
        {
            "title": "Product Two",
            "category": "electronics",
            "price": 149.99,
            "embedding_cosine": [0.8, 0.2, 0.1, 0.1],
            "embedding_l2": [0.8, 0.2, 0.0, 0.0],
            "embedding_dotprod": [0.8, 0.2, 0.0, 0.0]
        },
        {
            "title": "Product Three",
            "category": "books",
            "price": 29.99,
            "embedding_cosine": [0.1, 0.9, 0.1, 0.1],
            "embedding_l2": [0.0, 1.0, 0.0, 0.0],
            "embedding_dotprod": [0.0, 1.0, 0.0, 0.0]
        },
        {
            "title": "Product Four",
            "category": "books",
            "price": 39.99,
            "embedding_cosine": [0.1, 0.8, 0.2, 0.1],
            "embedding_l2": [0.0, 0.8, 0.2, 0.0],
            "embedding_dotprod": [0.0, 0.8, 0.2, 0.0]
        },
        {
            "title": "Product Five",
            "category": "clothing",
            "price": 59.99,
            "embedding_cosine": [0.1, 0.1, 0.9, 0.1],
            "embedding_l2": [0.0, 0.0, 1.0, 0.0],
            "embedding_dotprod": [0.0, 0.0, 1.0, 0.0]
        }
    ]


class TestKNNSearch(unittest.TestCase):
    """测试 kNN 向量搜索功能（真实数据库）"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备：创建测试索引和数据"""
        cls.db_config = load_db_config()
        try:
            cls.client = cls._create_client()
            cls._drop_test_table()
            cls.client.indices.create(index=TEST_INDEX, body=_test_mapping())
            cls._insert_test_documents()
            print("\n[OK] 测试环境准备完成")
        except Exception as e:
            print(f"\n[FAIL] 测试环境准备失败：{e}")
            raise

    @classmethod
    def _create_client(cls):
        return OpenGauss(
            hosts=[{'host': cls.db_config['host'], 'port': cls.db_config['port']}],
            database=cls.db_config['database'],
            user=cls.db_config['user'],
            password=cls.db_config['password'],
            use_connection_pool=True,
            pool_min_conn=3,
            pool_max_conn=10
        )

    @classmethod
    def _drop_test_table(cls):
        try:
            with cls.client.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {TEST_INDEX}")
                    conn.commit()
                finally:
                    cursor.close()
            print(f"[INFO] Dropped existing {TEST_INDEX} table")
        except Exception as e:
            print(f"[WARN] Failed to drop table: {e}")

    @classmethod
    def _insert_test_documents(cls):
        for i, doc in enumerate(_test_documents(), 1):
            cls.client.index(index=TEST_INDEX, id=f"doc{i}", body=doc)
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理"""
        try:
            cls.client.delete_index(TEST_INDEX)
            print("[OK] 测试环境清理完成")
        except Exception as e:
            print(f"[FAIL] 测试环境清理失败：{e}")
        finally:
            # [OK] 关键修复：确保关闭客户端连接
            try:
                cls.client.close()
                print("[OK] Client connection closed")
            except Exception as e:
                print(f"[WARN] Failed to close client: {e}")

    def _knn_search(self, field='embedding_cosine', query_vector=None, k=3, similarity='cosine', **kwargs):
        return self.client.knn_search(
            index=TEST_INDEX,
            field=field,
            query_vector=COSINE_QUERY_VECTOR if query_vector is None else query_vector,
            k=k,
            similarity=similarity,
            **kwargs
        )

    def _search_body(self, body):
        return self.client.search(index=TEST_INDEX, body=body)

    def _hits(self, result):
        return result['hits']['hits']

    def _assert_result_structure(self, result):
        self.assertIn('hits', result)
        self.assertIn('total', result['hits'])
        self.assertIn('hits', result['hits'])

    def _assert_hit_count(self, result, count):
        self.assertEqual(len(self._hits(result)), count)

    def _assert_top_title(self, result, title=DOC_ONE_TITLE):
        top_hit = self._hits(result)[0]
        self.assertEqual(top_hit['_source']['title'], title)

    def _assert_invalid_knn_search(self, expected_text, **overrides):
        params = {
            "field": "embedding_cosine",
            "query_vector": MIXED_QUERY_VECTOR,
            "k": 3,
            "similarity": "cosine"
        }
        params.update(overrides)
        with self.assertRaises(Exception) as context:
            self._knn_search(**params)
        self.assertIn(expected_text, str(context.exception))
    
    def test_basic_knn_search_cosine(self):
        """测试基本的 kNN 搜索（余弦相似度）"""
        result = self._knn_search()
        
        # 验证返回结构
        self._assert_result_structure(result)
        
        # 验证返回数量
        self._assert_hit_count(result, 3)
        
        # 验证最相似的是 doc1
        self._assert_top_title(result)
        
        print("[OK] 余弦相似度 kNN 搜索测试通过")
    
    def test_knn_search_l2_distance(self):
        """测试 L2 距离的 kNN 搜索"""
        result = self._knn_search(
            field='embedding_l2',
            query_vector=[1.0, 0.0, 0.0, 0.0],
            similarity='l2_norm'
        )
        
        # 验证返回结构
        self._assert_hit_count(result, 3)
        
        # 验证最相似的是 doc1（L2 距离最小）
        self._assert_top_title(result)
        
        print("[OK] L2 距离 kNN 搜索测试通过")
    
    def test_knn_search_dot_product(self):
        """测试内积（点积）的 kNN 搜索"""
        result = self._knn_search(
            field='embedding_dotprod',
            query_vector=[0.95, 0.05, 0.0, 0.0],
            similarity='dot_product'
        )
        
        # 验证返回结构
        self._assert_hit_count(result, 3)
        
        # 验证最相似的是 doc1（内积最大）
        top_hit = self._hits(result)[0]
        print(f"Top hit: {top_hit['_source']['title']}")
        self._assert_top_title(result)
        
        print("[OK] 内积（点积）kNN 搜索测试通过")
    
    def test_knn_search_with_ef_search(self):
        """测试带 ef_search 参数的 kNN 搜索"""
        # 使用较大的 ef_search 值进行查询
        result = self._knn_search(
            ef_search=100  # 设置较高的搜索精度
        )
        
        # 验证返回结构
        self._assert_hit_count(result, 3)
        
        # 验证最相似的是 doc1
        self._assert_top_title(result)
        
        print("[OK] 带 ef_search 参数的 kNN 搜索测试通过")
    
    def test_knn_search_with_filter_term(self):
        """测试带 term 过滤的 kNN 搜索"""
        result = self._knn_search(
            filter_query={"term": {"category": "electronics"}}
        )
        
        # 验证返回结构
        self._assert_hit_count(result, 2)  # 只有 2 个 electronics
        
        # 验证所有结果都满足过滤条件
        for hit in self._hits(result):
            self.assertEqual(hit['_source']['category'], 'electronics')
        
        print("[OK] 带 term 过滤的 kNN 搜索测试通过")
    
    def test_opensearch_standard_format(self):
        """测试 OpenSearch 标准 kNN 查询格式（重要兼容性测试）"""
        # OpenSearch 标准格式：字段名作为键，使用 "vector" 而不是 "query_vector"
        query = {
            "knn": {
                "embedding_cosine": {  # ← 字段名作为键
                    "vector": [0.85, 0.15, 0.1, 0.1],  # ← 使用 "vector"
                    "k": 3
                }
            }
        }
        
        # 使用 search() 方法执行 OpenSearch 标准格式的 kNN 查询
        result = self._search_body(query)
        
        # 验证返回结构
        self._assert_result_structure(result)
        
        # 验证返回数量
        self._assert_hit_count(result, 3)
        
        # 验证最相似的是 doc1
        self._assert_top_title(result)
        
        print("[OK] OpenSearch 标准 kNN 查询格式测试通过")
    
    def test_opensearch_format_with_num_candidates(self):
        """测试 OpenSearch 标准格式带 num_candidates 参数"""
        query = {
            "knn": {
                "embedding_l2": {
                    "vector": [1.0, 0.0, 0.0, 0.0],
                    "k": 3,
                    "num_candidates": 100  # 候选集大小
                }
            }
        }
        
        result = self._search_body(query)
        
        # 验证返回结构
        self._assert_hit_count(result, 3)
        
        # 验证最相似的是 doc1
        self._assert_top_title(result)
        
        print("[OK] OpenSearch 标准格式带 num_candidates 测试通过")
    
    def test_knn_search_with_filter_terms(self):
        """测试带 terms 过滤的 kNN 搜索"""
        result = self._knn_search(
            query_vector=MIXED_QUERY_VECTOR,
            k=5,
            filter_query={
                "terms": {
                    "category": ["electronics", "books"]
                }
            }
        )
        
        # 验证只返回指定类别
        for hit in self._hits(result):
            self.assertIn(hit['_source']['category'], ['electronics', 'books'])
        
        print("[OK] 带 terms 过滤的 kNN 搜索测试通过")
    
    def test_knn_search_with_bool_filter(self):
        """测试带 bool 过滤的 kNN 搜索"""
        result = self._knn_search(
            query_vector=MIXED_QUERY_VECTOR,
            k=5,
            filter_query={
                "bool": {
                    "filter": [
                        {"terms": {"category": ["electronics", "books"]}},
                        {"term": {"price": 29.99}}
                    ]
                }
            }
        )
        
        # 验证只返回 books 且价格为 29.99 的文档
        for hit in self._hits(result):
            self.assertEqual(hit['_source']['category'], 'books')
            self.assertEqual(hit['_source']['price'], 29.99)
        
        print("[OK] 带 bool 过滤的 kNN 搜索测试通过")
    
    def test_knn_search_different_k_values(self):
        """测试不同 k 值的影响"""
        for k_value in (1, 3, 5):
            result = self._knn_search(query_vector=MIXED_QUERY_VECTOR, k=k_value)
            self._assert_hit_count(result, k_value)
        
        print("[OK] 不同 k 值测试通过")
    
    def test_invalid_similarity_value(self):
        """测试无效的 similarity 值"""
        self._assert_invalid_knn_search("Invalid similarity", similarity='invalid_similarity')
        print("[OK] 无效 similarity 值检测通过")
    
    def test_invalid_query_vector(self):
        """测试无效的查询向量"""
        # 空列表
        self._assert_invalid_knn_search("non-empty list", query_vector=[])
        print("[OK] 空查询向量检测通过")
    
    def test_invalid_k_value(self):
        """测试无效的 k 值"""
        for k_value in (0, -5):
            self._assert_invalid_knn_search("positive integer", k=k_value)
        print("[OK] 无效 k 值检测通过")
    
    def test_score_ordering(self):
        """测试分数排序的正确性"""
        result = self._knn_search(
            query_vector=[1.0, 0.0, 0.0, 0.0],
            k=5,
        )
        
        # 验证分数递减（最相似的在前面）
        scores = [hit['_score'] for hit in self._hits(result)]
        for i in range(len(scores) - 1):
            self.assertGreaterEqual(scores[i], scores[i + 1])
        
        print("[OK] 分数排序测试通过")


def run_tests():
    """运行所有测试"""
    print("=" * 70)
    print("开始测试 kNN 向量搜索功能")
    print("=" * 70)
    
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestKNNSearch)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("[PASS] 所有测试通过！")
    else:
        print("[FAIL] 部分测试失败")
        print("\n失败的测试:")
        for test, traceback in result.failures + result.errors:
            print(f"  - {test}")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
