#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenSearch 格式 PQ 和 RabitQ 压缩支持测试
测试 SDK 对 OpenSearch 标准 encoder 格式的解析和支持

依赖：
- db_config.json (位于 tests 目录)

运行方式：
    python -m unittest opensearch_sdk.tests.index_ops.test_opensearch_compression -v
    python opensearch_sdk/tests/index_ops/test_opensearch_compression.py
"""

import json
import os
import random
import sys
import traceback
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


VECTOR_DIMENSION = 768
TEST_DOC_COUNT = 10


def _compression_mapping(space_type, encoder=None):
    """Build an OpenSearch kNN vector mapping with optional compression encoder."""
    parameters = {
        "nlist": 100,
        "nprobes": 50
    }
    if encoder is not None:
        parameters["encoder"] = encoder

    return {
        "mappings": {
            "properties": {
                "title": {"type": "keyword"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": VECTOR_DIMENSION,
                    "space_type": space_type,
                    "method": {
                        "name": "ivf",
                        "engine": "faiss",
                        "parameters": parameters
                    }
                }
            }
        }
    }


def _random_docs(count=TEST_DOC_COUNT, dimension=VECTOR_DIMENSION):
    return [
        {
            "id": f"doc_{i}",
            "title": f"测试文档{i}",
            "embedding": [random.random() for _ in range(dimension)]
        }
        for i in range(count)
    ]


def _bulk_body(index_name, docs):
    bulk_lines = []
    for doc in docs:
        action = {"index": {"_index": index_name, "_id": doc["id"]}}
        bulk_lines.append(json.dumps(action, ensure_ascii=False))
        bulk_lines.append(json.dumps(doc, ensure_ascii=False))
    return '\n'.join(bulk_lines) + '\n'


def _is_compression_library_error(error):
    error_msg = str(error)
    upper_msg = error_msg.upper()
    return (
        "loaded the pq dynamic library" in error_msg
        or "PQ" in upper_msg
        or "RABITQ" in upper_msg
    )


class TestOpenSearchCompression(unittest.TestCase):
    """测试 OpenSearch 压缩格式"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        cls.db_config = load_db_config()
        cls.client = OpenGauss(
            hosts=[{'host': cls.db_config['host'], 'port': cls.db_config['port']}],
            database=cls.db_config['database'],
            user=cls.db_config['user'],
            password=cls.db_config['password']
        )
        cls.test_indices = []  # 记录创建的索引，用于清理
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理"""
        for index_name in cls.test_indices:
            try:
                if cls.client.indices.exists(index=index_name):
                    cls.client.indices.delete(index=index_name)
                    print(f"[OK] Cleaned up test index: {index_name}")
            except Exception as e:
                print(f"[WARN] Failed to clean index {index_name}: {e}")
        
        # [FIX] 确保客户端关闭
        try:
            cls.client.close()
        except Exception:
            pass

    def _delete_index_if_exists(self, index_name):
        try:
            if self.client.indices.exists(index=index_name):
                self.client.indices.delete(index=index_name)
        except Exception:
            pass

    def _create_index_and_verify(self, index_name, mapping):
        print(f"\n创建索引：{index_name}")
        self.client.indices.create(index=index_name, body=mapping)
        print("[OK] 索引创建成功！")

        self.test_indices.append(index_name)
        self.assertTrue(self.client.indices.exists(index=index_name), "索引应该存在")
        print("[OK] 索引存在性验证通过")

    def _bulk_insert_docs(self, index_name, docs):
        print(f"\n插入 {len(docs)} 条测试数据...")
        self.client.bulk(_bulk_body(index_name, docs))
        print("[OK] 数据插入成功！")

    def _run_knn_search(self, index_name):
        print("\n执行 kNN 搜索...")
        results = self.client.knn_search(
            index=index_name,
            field="embedding",
            query_vector=[random.random() for _ in range(VECTOR_DIMENSION)],
            k=3
        )
        hits = results['hits']['hits']
        print(f"[OK] kNN 搜索成功！返回 {len(hits)} 条结果")
        if hits:
            print(f"   Top result score: {hits[0]['_score']:.4f}")

    def _run_vector_case(self, index_name, mapping, skip_compression_errors=False):
        try:
            self._delete_index_if_exists(index_name)
            self._create_index_and_verify(index_name, mapping)
            self._bulk_insert_docs(index_name, _random_docs())
            self._run_knn_search(index_name)
        except Exception as e:
            if skip_compression_errors and _is_compression_library_error(e):
                print("[SKIP] RabitQ compression requires database to load PQ dynamic library")
                print(f"     Error message: {e}")
                self.skipTest("Database has not loaded PQ dynamic library (RabitQ dependency)")

            print(f"[FAIL] 测试失败：{e}")
            traceback.print_exc()
            raise
    
    def test_opensearch_pq_format(self):
        """Test 1: OpenSearch PQ format"""
        print("\n" + "="*70)
        print("Test 1: OpenSearch PQ Format")
        print("="*70)
        
        test_index = "test_os_pq_format"
        
        mapping = _compression_mapping(
            "cosinesimil",
            {
                "name": "pq",
                "parameters": {
                    "m": 64,
                    "code_size": 8
                }
            }
        )
        self._run_vector_case(test_index, mapping, skip_compression_errors=True)
    
    def test_opensearch_rabitq_format(self):
        """Test 2: OpenSearch RabitQ format"""
        print("\n" + "="*70)
        print("Test 2: OpenSearch RabitQ Format")
        print("="*70)
        
        test_index = "test_os_rabitq_format"
        
        mapping = _compression_mapping(
            "l2",
            {
                "name": "rabitq",
                "parameters": {
                    "refine_type": "SQ8",
                    "fht": True
                }
            }
        )
        self._run_vector_case(test_index, mapping, skip_compression_errors=True)
    
    def test_without_compression(self):
        """Test 3: No compression control"""
        print("\n" + "="*70)
        print("Test 3: No Compression Control")
        print("="*70)
        
        test_index = "test_no_compression"
        
        mapping = _compression_mapping("cosinesimil")
        self._run_vector_case(test_index, mapping)


if __name__ == "__main__":
    unittest.main(verbosity=2)
