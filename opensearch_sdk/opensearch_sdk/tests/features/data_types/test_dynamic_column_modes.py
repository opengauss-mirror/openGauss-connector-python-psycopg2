#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
动态列功能测试

测试两种模式：
1. 严格模式（enable_dynamic_inference=False）：字段必须在 mapping 中定义，否则报错
2. 宽松模式（默认，enable_dynamic_inference=True）：允许从样本值推断类型
"""

import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.features.data_types.dynamic_column_common import (
    delete_index_safely as _delete_index_safely,
    fetch_columns as _fetch_columns,
    fetch_indexes as _fetch_indexes,
    recreate_base_index as _recreate_base_index,
    refresh_index_safely as _refresh_index_safely,
)
from opensearch_sdk.tests.utils.config_loader import load_db_config


class DynamicColumnTestMixin:
    """Assertions shared by dynamic column test cases."""

    def _index_doc(self, doc_id, body):
        result = self.client.index(index=self.index_name, id=doc_id, body=body)
        self.assertEqual(result['result'], 'created')
        return result

    def _index_docs(self, docs):
        for doc_id, body in docs:
            self._index_doc(doc_id, body)

    def _assert_columns_present(self, db_columns, expected_fields):
        column_names = [col[0] for col in db_columns]
        for field in expected_fields:
            self.assertIn(field, column_names, f"动态字段 '{field}' 应该被添加")
            print(f"[PASS] 动态字段 '{field}' 已成功添加")

    def _assert_index_name_contains(self, index_names, field_name, label=None, extra_marker=None):
        label = label or field_name
        markers = [field_name]
        if extra_marker:
            markers.append(extra_marker)
        self.assertTrue(
            any(all(marker in idx for marker in markers) for idx in index_names),
            f"{field_name} 应该有索引，实际索引: {index_names}"
        )
        print(f"[PASS] {label} 的索引已创建")

    def _search_hits(self, query):
        search_result = self.client.search(index=self.index_name, body={"query": query})
        return search_result.get('hits', {}).get('hits', [])

    def _assert_match_hits_contain(self, query_text, expected_text, label):
        hits = self._search_hits({"match": {"dynamic_string": query_text}})
        self.assertGreater(len(hits), 0, f"应该能找到包含'{expected_text}'的文档")
        matched_docs = [hit['_source']['dynamic_string'] for hit in hits]
        self.assertTrue(any(expected_text.lower() in text.lower() for text in matched_docs))
        print(f"[PASS] {label} BM25 查询成功，找到 {len(hits)} 条包含'{expected_text}'的文档")


class TestDynamicColumnStrictMode(DynamicColumnTestMixin, unittest.TestCase):
    """测试严格模式 - 字段必须在 mapping 中定义"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        cls.db_config = load_db_config()
        # [OK] 显式设置为严格模式
        cls.client = OpenGauss(**cls.db_config, enable_dynamic_inference=False)
        cls.index_name = "test_dynamic_strict"
        _recreate_base_index(cls.client, cls.index_name)
        print(f"\n[SETUP] 创建索引 '{cls.index_name}'")
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理"""
        _delete_index_safely(cls.client, cls.index_name)
        print(f"[TEARDOWN] 删除索引 '{cls.index_name}'")
        cls.client.close()
    
    def setUp(self):
        """每个测试前重建索引，确保数据隔离"""
        _recreate_base_index(self.client, self.index_name)
    
    def test_undefined_column_should_fail(self):
        """测试未定义的字段应该失败"""
        doc = {
            "title": "测试文档",
            "content": "内容",
            "undefined_field": "这个字段不在 mapping 中"
        }
        
        with self.assertRaises(Exception) as context:
            self.client.index(index=self.index_name, id="doc1", body=doc)
        
        # 验证错误信息
        error_msg = str(context.exception)
        self.assertIn("mapping", error_msg.lower(), f"错误消息应该包含 'mapping'，实际为: {error_msg}")
        print(f"[PASS] 严格模式正常工作：{error_msg}")


class TestDynamicColumnInferenceMode(DynamicColumnTestMixin, unittest.TestCase):
    """测试宽松模式 - 启用动态类型推断"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        cls.db_config = load_db_config()
        # 启用动态推断
        cls.client = OpenGauss(**cls.db_config, enable_dynamic_inference=True)
        cls.index_name = "test_dynamic_infer"
        _recreate_base_index(cls.client, cls.index_name)
        print(f"\n[SETUP] 创建索引 '{cls.index_name}' (动态推断已启用)")
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理"""
        _delete_index_safely(cls.client, cls.index_name)
        print(f"[TEARDOWN] 删除索引 '{cls.index_name}'")
        cls.client.close()
    
    def setUp(self):
        """每个测试前重建索引，确保数据隔离"""
        _recreate_base_index(self.client, self.index_name)
    
    def test_dynamic_column_inference(self):
        """测试动态列推断功能"""
        doc = {
            "title": "测试文档",
            "content": "内容",
            "dynamic_string": "字符串字段",      # 应推断为 TEXT
            "dynamic_number": 123,              # 应推断为 BIGINT
            "dynamic_bool": True,               # 应推断为 BOOLEAN
            "dynamic_float": 3.14,              # 应推断为 FLOAT4
        }
        
        result = self._index_doc("doc1", doc)
        print(f"[PASS] 文档插入成功：{result['result']}")
        
        # 验证列已添加
        db_columns = _fetch_columns(self.client, self.index_name)
        
        # 验证动态字段已添加
        self._assert_columns_present(db_columns,
            ['dynamic_string', 'dynamic_number', 'dynamic_bool', 'dynamic_float'])
        
        # 验证数据类型
        column_types = {col[0]: col[1] for col in db_columns}
        self.assertEqual(column_types.get('dynamic_string'), 'text')
        self.assertEqual(column_types.get('dynamic_number'), 'bigint')
        self.assertEqual(column_types.get('dynamic_bool'), 'boolean')
        self.assertIn(column_types.get('dynamic_float'), ['real', 'double precision'])
        print(f"[PASS] 数据类型推断正确")
        
        # [OK] 验证动态列的索引是否自动创建
        indexes = _fetch_indexes(self.client, self.index_name)
        
        index_names = [idx[0] for idx in indexes]
        print(f"\n创建的索引列表:")
        for idx_name, _ in indexes:
            print(f"  - {idx_name}")
        
        # 验证 TEXT 字段有 BM25 索引
        self._assert_index_name_contains(index_names, 'dynamic_string', extra_marker='bm25')
        
        # 验证数值字段有 B-tree 索引
        for field_name in ['dynamic_number', 'dynamic_bool', 'dynamic_float']:
            self._assert_index_name_contains(index_names, field_name)
    
    def test_dynamic_vector_column_and_index(self):
        """测试动态向量列和 HNSW 索引创建"""
        # 插入包含向量字段的文档（维度 >= 100）
        doc = {
            "title": "向量测试",
            "content": "内容",
            "embedding": [0.1] * 128,  # 128维向量，应该触发向量索引创建
        }
        
        self._index_doc("doc_vec", doc)
        print(f"[PASS] 向量文档插入成功")
        
        # 验证向量列已添加
        columns = _fetch_columns(self.client, self.index_name, column_name='embedding')
        col_info = columns[0] if columns else None
        
        self.assertIsNotNone(col_info, "embedding 列应该存在")
        self.assertTrue(
            col_info[1].upper().startswith('VECTOR'),
            f"embedding 应该是 VECTOR 类型，实际为: {col_info[1]}"
        )
        print(f"[PASS] 向量列 embedding 已创建，类型: {col_info[1]}")
        
        # 验证 HNSW 索引已创建
        hnsw_indexes = _fetch_indexes(self.client, self.index_name, index_like='%embedding%hnsw%')
        
        self.assertGreater(
            len(hnsw_indexes), 0,
            f"embedding 应该有 HNSW 索引，实际索引: {[idx[0] for idx in hnsw_indexes]}"
        )
        print(f"[PASS] embedding 的 HNSW 索引已创建: {hnsw_indexes[0][0]}")
        print(f"       索引定义: {hnsw_indexes[0][1][:200]}...")
    
    def test_dynamic_column_query_with_index(self):
        """测试动态列的索引是否能正常用于查询（包括中英文 BM25）"""
        # 先插入测试数据（包含中英文）
        docs = [
            ("doc1", {
                "title": "测试文档1",
                "content": "这是第一个测试文档",
                "dynamic_string": "苹果香蕉橙子 apple banana orange",
                "dynamic_number": 100,
                "dynamic_bool": True,
                "dynamic_float": 3.14
            }),
            ("doc2", {
                "title": "测试文档2",
                "content": "这是第二个测试文档",
                "dynamic_string": "葡萄西瓜草莓 grape watermelon strawberry",
                "dynamic_number": 200,
                "dynamic_bool": False,
                "dynamic_float": 2.71
            }),
            ("doc3", {
                "title": "测试文档3",
                "content": "这是第三个测试文档",
                "dynamic_string": "苹果葡萄桃子 apple grape peach",
                "dynamic_number": 150,
                "dynamic_bool": True,
                "dynamic_float": 1.41
            }),
        ]
        
        self._index_docs(docs)
        
        _refresh_index_safely(self.client, self.index_name)
        
        print(f"[PASS] 插入了 {len(docs)} 条测试数据")
        
        self._assert_match_hits_contain("苹果", "苹果", "中文")
        self._assert_match_hits_contain("apple", "apple", "英文")
        
        # 测试3: 数值范围查询（使用 dynamic_number）
        hits = self._search_hits({
            "range": {
                "dynamic_number": {
                    "gte": 100,
                    "lte": 150
                }
            }
        })
        self.assertEqual(len(hits), 2, f"应该找到 2 条记录（100和150），实际找到 {len(hits)} 条")
        
        numbers = [hit['_source']['dynamic_number'] for hit in hits]
        self.assertIn(100, numbers)
        self.assertIn(150, numbers)
        print(f"[PASS] B-tree 索引范围查询成功，找到 {len(hits)} 条记录")
        
        # 测试4: 布尔值查询（使用 dynamic_bool）
        hits = self._search_hits({"term": {"dynamic_bool": True}})
        self.assertEqual(len(hits), 2, f"应该找到 2 条 dynamic_bool=True 的记录")
        
        bools = [hit['_source']['dynamic_bool'] for hit in hits]
        self.assertTrue(all(b is True for b in bools))
        print(f"[PASS] B-tree 索引布尔查询成功，找到 {len(hits)} 条记录")


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
