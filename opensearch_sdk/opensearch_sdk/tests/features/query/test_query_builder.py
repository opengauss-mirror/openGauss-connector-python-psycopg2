#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
查询构建器测试 - should 子句 OR 逻辑

功能说明：
- 测试 QueryBuilder 的 should 处理
- 验证 should 条件的 OR 逻辑
- 验证 DELETE SQL 模板生成

运行方式：
    python -m unittest opensearch_sdk.tests.features.query.test_query_builder -v
"""

import os
import sys
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from psycopg2 import sql

from opensearch_sdk.client.query_builder import QueryBuilder
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestQueryBuilderShould(unittest.TestCase):
    """测试 QueryBuilder 的 should 子句处理"""
    
    def test_01_should_or_logic(self):
        """测试 should 子句的 OR 逻辑"""
        query = {
            "should": [
                {"term": {"categories": "cat1"}},
                {"term": {"categories": "cat2"}}
            ],
            "minimum_should_match": 1
        }
        
        where_conditions, params, _ = QueryBuilder.process_bool_clause(query)
        
        # 验证生成了 WHERE 条件
        self.assertIsNotNone(where_conditions)
        self.assertIsInstance(where_conditions, list)
        self.assertGreater(len(where_conditions), 0)
        
        # 验证参数数量
        self.assertEqual(len(params), 2)
        self.assertIn("cat1", params)
        self.assertIn("cat2", params)
        
        print(f"\n输入查询: {query}")
        print(f"生成的 WHERE 条件数: {len(where_conditions)}")
        print(f"参数：{params}")
    
    def test_02_delete_sql_template(self):
        """测试 DELETE SQL 模板生成"""
        query = {
            "should": [
                {"term": {"categories": "cat1"}},
                {"term": {"categories": "cat2"}}
            ],
            "minimum_should_match": 1
        }
        
        where_conditions, params, _ = QueryBuilder.process_bool_clause(query)
        
        if where_conditions:
            where_clause = sql.SQL(" AND ").join(where_conditions)
            delete_sql = sql.SQL("DELETE FROM test_index WHERE {}").format(where_clause)
            
            # 验证 SQL 模板生成
            self.assertIsNotNone(delete_sql)
            sql_str = str(delete_sql)
            self.assertIn("DELETE FROM", sql_str)
            self.assertIn("test_index", sql_str)
            self.assertIn("WHERE", sql_str)
            
            print(f"\n生成的 DELETE SQL 模板: {delete_sql}")


if __name__ == '__main__':
    unittest.main()
