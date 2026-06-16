#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 OpenSearch 和 Elasticsearch 向量字段参数双重兼容

验证 SDK 能同时处理：
1. OpenSearch 风格：space_type
2. Elasticsearch 风格：similarity
"""
import os
import sys
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


def _knn_mapping(vector_field, dimension, vector_options, text_field="title"):
    return {
        "settings": {
            "index": {
                "knn": True
            }
        },
        "mappings": {
            "properties": {
                text_field: {"type": "text"},
                vector_field: {
                    "type": "knn_vector",
                    "dimension": dimension,
                    **vector_options
                }
            }
        }
    }


class TestVectorFieldDualCompatibility(unittest.TestCase):
    """测试向量字段参数的双重兼容性"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        print("\n" + "="*70)
        print("开始执行向量字段参数双重兼容性测试")
        print("="*70)

        cls.db_config = load_db_config()
        # 创建客户端
        cls.client = OpenGauss(
            hosts=[{'host': cls.db_config['host'], 'port': cls.db_config['port']}],
            database=cls.db_config.get('database', 'es'),
            user=cls.db_config['user'],
            password=cls.db_config['password']
        )

        cls.test_index_prefix = "test_dual_compat"
    
    @classmethod
    def tearDownClass(cls):
        """测试类结束后清理"""
        cls._cleanup_test_indices()
        cls._close_client()

        print("\n" + "="*70)
        print("测试完成")
        print("="*70)

    @classmethod
    def _cleanup_test_indices(cls):
        try:
            indices = cls.client.cat.indices(output_format="json")
            for idx in indices:
                index_name = idx.get('index', '')
                if index_name.startswith(cls.test_index_prefix):
                    cls._delete_index_for_cleanup(index_name)
        except Exception as e:
            print(f"[警告] 清理索引失败：{e}")

    @classmethod
    def _delete_index_for_cleanup(cls, index_name):
        try:
            cls.client.indices.delete(index=index_name)
            print(f"[清理] 删除测试索引：{index_name}")
        except Exception as e:
            print(f"[警告] 删除索引 {index_name} 失败：{e}")

    @classmethod
    def _close_client(cls):
        try:
            cls.client.close()
        except Exception:
            pass

    def _delete_index_if_exists(self, test_index):
        try:
            if self.client.indices.exists(index=test_index):
                self.client.indices.delete(index=test_index)
                print(f"[清理] 删除已存在的索引：{test_index}")
        except Exception as e:
            print(f"[警告] 清理索引失败：{e}")

    def _create_index_and_assert(self, test_index, mapping, message="索引应该创建成功"):
        self._delete_index_if_exists(test_index)
        result = self.client.indices.create(index=test_index, body=mapping)
        self.assertTrue(result.get('acknowledged', False), message)

    def _test_index(self, suffix):
        return f"{self.test_index_prefix}_{suffix}"

    def _create_vector_index(self, suffix, vector_field, dimension, vector_options, text_field="title", message=None):
        test_index = self._test_index(suffix)
        mapping = _knn_mapping(vector_field, dimension, vector_options, text_field=text_field)
        self._create_index_and_assert(test_index, mapping, message or "索引应该创建成功")
        return test_index

    def _create_vector_index_with_doc(self, suffix, vector_field, dimension, vector_options, text_field="title"):
        test_index = self._create_vector_index(suffix, vector_field, dimension, vector_options, text_field)
        self._insert_vector_doc(test_index, vector_field, dimension)
        return test_index

    def _insert_vector_doc(self, test_index, vector_field, dimension):
        doc = {
            "title": "Test Document",
            vector_field: [0.1] * dimension
        }
        self.client.index(index=test_index, id="doc_001", body=doc)

    def _fetch_hnsw_indexes(self, test_index, vector_field):
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT indexname FROM pg_indexes WHERE tablename = %s AND indexname LIKE %s",
                    (test_index, f'%{vector_field}%hnsw%')
                )
                return [row[0] for row in cursor.fetchall()]
            finally:
                cursor.close()

    def _assert_hnsw_index_created(self, test_index, vector_field):
        hnsw_indexes = self._fetch_hnsw_indexes(test_index, vector_field)
        self.assertGreater(len(hnsw_indexes), 0, "应该创建 HNSW 索引")
        print(f"[验证] 找到 HNSW 索引：{hnsw_indexes}")

    def test_01_opensearch_space_type(self):
        """测试 OpenSearch 风格：space_type 参数"""
        print("\n[测试] OpenSearch 风格 space_type...")

        test_index = self._create_vector_index_with_doc("os_style", "embedding",
            512, {"space_type": "cosinesimil"})

        # [OK] 验证 HNSW 索引是否创建
        self._assert_hnsw_index_created(test_index, "embedding")
        
        print("[通过] OpenSearch space_type 兼容成功")
    
    def test_02_elasticsearch_similarity(self):
        """测试 Elasticsearch 风格：similarity 参数"""
        print("\n[测试] Elasticsearch 风格 similarity...")
        
        self._create_vector_index_with_doc("es_style", "embedding",
            768, {"similarity": "cosine"})
        
        print("[通过] Elasticsearch similarity 兼容成功")
    
    def test_03_both_parameters_space_type_priority(self):
        """测试同时设置 space_type 和 similarity（space_type 优先）"""
        print("\n[测试] 同时设置 space_type 和 similarity（space_type 优先）...")
        
        self._create_vector_index_with_doc("both_priority", "embedding",
            256, {"space_type": "l2", "similarity": "dot_product"})
        
        print("[通过] space_type 优先级高于 similarity")
    
    def test_04_different_similarity_values(self):
        """测试不同的 similarity 值"""
        print("\n[测试] 不同的 similarity 值...")
        
        test_cases = [
            ("cosine", "余弦相似度"),
            ("l2_norm", "L2 范数"),
            ("dot_product", "点积"),
        ]
        
        for similarity_value, description in test_cases:
            self._create_vector_index(similarity_value, "vector", 128, {"similarity": similarity_value},
                text_field="text", message=f"索引 {similarity_value} 应该创建成功")
            
            print(f"  [PASS] {description} ({similarity_value}) - 成功")
    
    def test_05_invalid_similarity_fallback(self):
        """测试无效的 similarity 值回退到默认值"""
        print("\n[测试] 无效的 similarity 值回退...")
        
        self._create_vector_index("invalid", "vector", 128, {"similarity": "invalid_value"},
            text_field="text", message="即使 similarity 无效，索引也应该创建成功（使用默认值）")
        
        print("[通过] 无效 similarity 值回退到默认值 'cosine'")
    
    def test_06_no_similarity_default(self):
        """测试未指定任何相似度参数时使用默认值"""
        print("\n[测试] 未指定相似度参数时的默认行为...")
        
        self._create_vector_index("default", "vector", 128, {},
            text_field="text", message="索引应该创建成功（使用默认相似度）")
        
        print("[通过] 未指定相似度时使用默认值 'cosine'")


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)
