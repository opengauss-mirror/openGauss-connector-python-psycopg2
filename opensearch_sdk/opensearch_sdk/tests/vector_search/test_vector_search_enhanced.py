#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
向量搜索测试 - 增强功能

功能说明：
- 索引创建支持 similarity 和 index_options 参数
- search() 方法支持 knn 查询路由
- _score 基于真实向量距离计算

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.vector_search.test_vector_search_enhanced -v
    python opensearch_sdk/tests/vector_search/test_vector_search_enhanced.py
"""

import os
import sys
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


def _create_client():
    db_config = load_db_config()
    return OpenGauss(
        hosts=[{
            'host': db_config['host'],
            'port': db_config['port']
        }],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )


def _drop_table(client, table_name):
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.commit()
        finally:
            cursor.close()


def _delete_index_if_exists(client, index_name):
    try:
        if client.indices.exists(index=index_name):
            client.indices.delete(index=index_name)
            print(f"Deleted old test index: {index_name}")
    except Exception:
        pass


def _fetch_index_names(client, table_name):
    return _fetch_pg_index_column(client, table_name, "indexname")


def _fetch_index_defs(client, table_name):
    return _fetch_pg_index_column(client, table_name, "indexdef")


def _fetch_pg_index_column(client, table_name, column_name):
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT {column_name} FROM pg_indexes WHERE tablename = %s",
                (table_name,)
            )
            return cursor.fetchall()
        finally:
            cursor.close()


def _contains_index_def(index_defs, *fragments):
    return any(all(fragment in row[0] for fragment in fragments) for row in index_defs)


def _index_docs(client, index_name, docs):
    for doc in docs:
        body = {key: value for key, value in doc.items() if key != "id"}
        client.index(index=index_name, id=doc["id"], body=body)


def _mapping(properties):
    return {
        "mappings": {
            "properties": properties
        }
    }


class TestSimilarityParameter(unittest.TestCase):
    """测试 similarity 参数支持"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = _create_client()
        cls.test_index = "test_similarity_idx"
    
    @classmethod
    def tearDownClass(cls):
        """清理测试资源"""
        try:
            _drop_table(cls.client, cls.test_index)
            cls.client.close()
        except Exception as e:
            print(f"清理失败：{e}")
    
    def test_create_index_with_l2_similarity(self):
        """测试 L2 相似度参数生效"""
        mapping = _mapping({
            "embedding_l2": {
                "type": "dense_vector",
                "dims": 4,
                "similarity": "l2_norm"
            }
        })
        
        # 创建索引
        result = self.client.indices.create(index=self.test_index, body=mapping)
        self.assertTrue(result.get("acknowledged"))
        
        self.assertGreater(len(_fetch_index_names(self.client, self.test_index)), 0)
        self.assertTrue(
            _contains_index_def(_fetch_index_defs(self.client, self.test_index), 'vector_l2_ops'),
            "应该使用 vector_l2_ops 操作符"
        )
    
    def test_create_index_with_custom_options(self):
        """测试自定义索引参数生效"""
        test_index_custom = f"{self.test_index}_custom"
        
        mapping = _mapping({
            "embedding_custom": {
                "type": "dense_vector",
                "dims": 4,
                "similarity": "cosine",
                "index_options": {
                    "m": 32,
                    "ef_construction": 128
                }
            }
        })
        
        try:
            # 创建索引
            result = self.client.indices.create(index=test_index_custom, body=mapping)
            self.assertTrue(result.get("acknowledged"))
            
            index_defs = _fetch_index_defs(self.client, test_index_custom)
            self.assertTrue(
                _contains_index_def(index_defs, 'm=32', 'ef_construction=128'),
                "应该使用自定义的 m 和 ef_construction 参数"
            )
        finally:
            _drop_table(self.client, test_index_custom)


class TestKnnInSearch(unittest.TestCase):
    """测试 search() 中的 knn 查询"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = _create_client()
        cls.test_index = "test_knn_search"
        _delete_index_if_exists(cls.client, cls.test_index)
        
        # 创建测试表和索引
        mapping = _mapping({
            "embedding": {
                "type": "dense_vector",
                "dims": 4,
                "similarity": "cosine"
            },
            "title": {"type": "text"},
            "category": {"type": "keyword"}
        })
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据
        test_data = [
            {"id": "1", "embedding": [0.1, 0.2, 0.3, 0.4], "title": "Document 1", "category": "A"},
            {"id": "2", "embedding": [0.2, 0.3, 0.4, 0.5], "title": "Document 2", "category": "B"},
            {"id": "3", "embedding": [0.3, 0.4, 0.5, 0.6], "title": "Document 3", "category": "A"},
        ]
        
        _index_docs(cls.client, cls.test_index, test_data)
    
    @classmethod
    def tearDownClass(cls):
        """清理测试资源"""
        try:
            _drop_table(cls.client, cls.test_index)
            cls.client.close()
        except Exception as e:
            print(f"清理失败：{e}")
    
    def test_search_with_knn_body(self):
        """测试标准的 search(body={knn: ...}) 接口"""
        query_vector = [0.15, 0.25, 0.35, 0.45]
        
        # 使用 OpenSearch 标准格式
        result = self.client.search(
            index=self.test_index,
            body={
                "knn": {
                    "embedding": {  # 字段名作为键
                        "vector": query_vector,  # 使用 vector 而不是 query_vector
                        "k": 2
                    }
                }
            }
        )
        
        # 验证返回结构
        self.assertIn('hits', result)
        self.assertIn('hits', result['hits'])
        self.assertEqual(len(result['hits']['hits']), 2)
        
        # 验证 score 存在
        for hit in result['hits']['hits']:
            self.assertIn('_score', hit)
            self.assertIsInstance(hit['_score'], float)
    
    def test_search_with_knn_and_filter(self):
        """测试带过滤的 knn 查询"""
        query_vector = [0.15, 0.25, 0.35, 0.45]
        
        # 使用 OpenSearch 标准格式
        result = self.client.search(
            index=self.test_index,
            body={
                "knn": {
                    "embedding": {  # 字段名作为键
                        "vector": query_vector,  # 使用 vector 而不是 query_vector
                        "k": 10,
                        "filter": {
                            "term": {"category": "A"}
                        }
                    }
                }
            }
        )
        
        # 验证返回结果
        self.assertIn('hits', result)
        self.assertIn('hits', result['hits'])
        
        # 所有结果都应该属于 category A
        for hit in result['hits']['hits']:
            self.assertEqual(hit['_source']['category'], 'A')


class TestScoreCalculation(unittest.TestCase):
    """测试 _score 计算"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = _create_client()
        cls.test_index = "test_score_calc"
        _delete_index_if_exists(cls.client, cls.test_index)
        
        # 创建测试表（L2 距离）
        mapping = _mapping({
            "embedding": {
                "type": "dense_vector",
                "dims": 3,
                "similarity": "l2_norm"
            }
        })
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据 - 已知的向量
        test_data = [
            {"id": "1", "embedding": [1.0, 0.0, 0.0]},  # 单位向量
            {"id": "2", "embedding": [0.0, 1.0, 0.0]},  # 正交向量
            {"id": "3", "embedding": [1.0, 1.0, 0.0]},  # 对角向量
        ]
        
        _index_docs(cls.client, cls.test_index, test_data)
    
    @classmethod
    def tearDownClass(cls):
        """清理测试资源"""
        try:
            _drop_table(cls.client, cls.test_index)
            cls.client.close()
        except Exception as e:
            print(f"清理失败：{e}")
    
    def test_score_based_on_distance(self):
        """测试 score 基于真实距离而非索引位置"""
        query_vector = [1.0, 0.0, 0.0]  # 与第一个向量完全相同
        
        result = self.client.knn_search(
            index=self.test_index,
            field="embedding",
            query_vector=query_vector,
            k=3
        )
        
        # 验证返回了结果
        self.assertIn('hits', result)
        self.assertIn('hits', result['hits'])
        self.assertGreater(len(result['hits']['hits']), 0)
        
        # 第一个结果的 score 应该最高（因为向量相同，L2 距离为 0）
        hits = result['hits']['hits']
        if len(hits) > 1:
            first_score = hits[0]['_score']
            second_score = hits[1]['_score']
            
            # 第一个分数应该大于等于第二个（相似度排序）
            self.assertGreaterEqual(first_score, second_score)
            
            # 对于 L2 距离，score = 1/(1+distance)
            # 如果向量为 [1,0,0] 且查询也是 [1,0,0]，距离应为 0，score 应为 1.0
            # 允许一定的浮点误差
            self.assertAlmostEqual(first_score, 1.0, places=1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
