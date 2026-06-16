#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
其他功能测试 - 过滤器构建器

功能说明：
- 测试 process_filter_for_knn 方法
- 验证 bool.filter 数组格式的处理

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.other_features.test_filter_builder -v
    python opensearch_sdk/tests/other_features/test_filter_builder.py
"""

import json
import os
import sys
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from opensearch_sdk.client.query_builder import QueryBuilder
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestFilterBuilder(unittest.TestCase):
    """测试过滤器构建器功能"""
    
    def test_01_bool_filter_array_format(self):
        """测试 bool.filter 数组格式的处理"""
        filter_query = {
            "bool": {
                "filter": [
                    {"term": {"category": "tech"}},
                    {"range": {"publish_date": {"gte": "2024-01-01"}}}
                ]
            }
        }
        
        sql, params = QueryBuilder.process_filter_for_knn(filter_query)
        
        # 验证 SQL 生成
        self.assertIsNotNone(sql)
        self.assertIsInstance(params, list)
        
        # 验证包含两个过滤条件
        self.assertIn("category", sql)
        self.assertIn("publish_date", sql)
        
        print(f"\n输入 filter:")
        print(json.dumps(filter_query, indent=2))
        print(f"\n生成的 SQL: {sql}")
        print(f"参数：{params}")
    
    def test_02_single_term_filter(self):
        """测试单个 term 过滤"""
        filter_query = {
            "term": {"status": "published"}
        }
        
        sql, params = QueryBuilder.process_filter_for_knn(filter_query)
        
        self.assertIsNotNone(sql)
        self.assertIn("status", sql)
        print(f"\n单 term 过滤 SQL: {sql}")
        print(f"参数：{params}")
    
    def test_03_empty_filter(self):
        """测试空过滤"""
        filter_query = {}
        
        sql, params = QueryBuilder.process_filter_for_knn(filter_query)
        
        # 空过滤应该返回 None 或空字符串
        self.assertTrue(sql is None or sql == "")
        print(f"\n空过滤 SQL: {sql}")


if __name__ == '__main__':
    unittest.main()
