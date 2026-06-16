#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试openGauss数据库 Query Builder 字段名标准化功能

功能说明：
- 测试查询条件中自动转换字段名中的 . 和 - 为 _
- 验证 nested 查询路径的标准化
- 确保过滤条件的字段名标准化
"""

import sys
import os
import unittest
import warnings

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from opensearch_sdk.client.query_builder import QueryBuilder


class TestQueryBuilderNormalization(unittest.TestCase):
    """测试 Query Builder 字段名标准化"""
    
    def test_normalize_field_path_basic(self):
        """测试基本的字段路径标准化"""
        # 测试点号
        result = QueryBuilder._normalize_field_path("user.name")
        self.assertEqual(result, "user_name")
        
        # 测试连字符
        result = QueryBuilder._normalize_field_path("user-name")
        self.assertEqual(result, "user_name")
        
        # 测试混合
        result = QueryBuilder._normalize_field_path("user-name.info")
        self.assertEqual(result, "user_name_info")
        
        # 测试正常字段（无需转换）
        result = QueryBuilder._normalize_field_path("normal_field")
        self.assertEqual(result, "normal_field")
    
    def test_process_query_item_normalization(self):
        """测试 process_query_item 自动标准化字段名（已移除警告）"""
        
        # 测试 match 查询
        query_item = {"match": {"user-name": "test"}}
        cond, param, marks = QueryBuilder.process_query_item(query_item)
        
        # 测试 term 查询
        query_item = {"term": {"user.info": "value"}}
        cond, param, marks = QueryBuilder.process_query_item(query_item)
        
        # 测试 range 查询
        query_item = {"range": {"field-name": {"gte": 10}}}
        cond, param, marks = QueryBuilder.process_query_item(query_item)
        
        # 测试 exists 查询
        query_item = {"exists": {"field": "test-field"}}
        cond, param, marks = QueryBuilder.process_query_item(query_item)
    
    def test_process_nested_query_normalization(self):
        """测试 nested 查询路径标准化（已移除警告）"""
        
        # 测试 nested 路径包含特殊字符
        nested_clause = {
            "path": "user-info",  # 含连字符
            "query": {
                "term": {"name": "John"}
            }
        }
        
        # 注意：process_nested_query 需要 params 参数
        cond, params, marks = QueryBuilder.process_nested_query(nested_clause, [])
    
    def test_process_filter_for_knn_normalization(self):
        """测试 kNN 过滤条件字段名标准化（已移除警告）"""
        
        # 测试 term 过滤
        filter_query = {
            "term": {
                "category-name": "electronics"  # 含连字符
            }
        }
        cond_str, params = QueryBuilder.process_filter_for_knn(filter_query)
        
        # 测试 terms 过滤
        filter_query = {
            "terms": {
                "user.info": ["val1", "val2"]  # 含点号
            }
        }
        cond_str, params = QueryBuilder.process_filter_for_knn(filter_query)
        
        # 测试 range 过滤
        filter_query = {
            "range": {
                "price-range": {"gte": 100, "lte": 500}  # 含连字符
            }
        }
        cond_str, params = QueryBuilder.process_filter_for_knn(filter_query)
    
    def test_no_warning_for_normal_fields(self):
        """测试正常字段名不触发警告（已移除警告机制）"""
        
        # 测试正常字段名的各种查询
        test_cases = [
            {"match": {"user_name": "test"}},
            {"term": {"category_type": "value"}},
            {"range": {"price_range": {"gte": 10}}},
            {"exists": {"field": "normal_field"}},
        ]
        
        for query_item in test_cases:
            cond, param, marks = QueryBuilder.process_query_item(query_item)


if __name__ == '__main__':
    unittest.main(verbosity=2)
