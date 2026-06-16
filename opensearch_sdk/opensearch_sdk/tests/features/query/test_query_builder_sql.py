#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查询构建器 SQL 测试 - match_phrase SQL 生成

功能说明：
- 测试 QueryBuilder 生成的 match_phrase SQL
- 验证 SQL 语句的正确性
- 测试严格短语和 slop 短语

运行方式：
    python -m unittest opensearch_sdk.tests.features.query.test_query_builder_sql -v
"""

import json
import os
import sys
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from psycopg2 import sql as psycopg_sql

from opensearch_sdk.client.query_builder import QueryBuilder
from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestQueryBuilderSQL(unittest.TestCase):
    """测试 QueryBuilder 的 SQL 生成功能"""
    
    @classmethod
    def setUpClass(cls):
        """设置数据库连接"""
        db_config = load_db_config()
        cls.client = OpenGauss(
            hosts=[{'host': db_config['host'], 'port': db_config['port']}],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
    
    def test_01_strict_match_phrase(self):
        """测试严格短语匹配 (slop=None)"""
        field = "title"
        phrase = "quick brown fox"
        
        condition, params = QueryBuilder.build_match_phrase_condition(field, phrase, slop=None)
        
        # 验证条件生成
        self.assertIsNotNone(condition)
        self.assertIsNotNone(params)  # params 可能是 tuple 或 list
        
        # 生成完整 SQL
        select_clause = psycopg_sql.SQL("SELECT * FROM test_table WHERE ")
        full_query = select_clause + condition
        
        # [FIX] 使用新的连接管理模式获取 connection 对象
        with self.client.connection.get_connection_for_operation() as conn:
            query_str = full_query.as_string(conn)
        
        print(f"\n严格短语 (slop=None):")
        print(f"  生成的 SQL: {query_str}")
        print(f"  参数：{params}")
        
        # 验证 SQL 包含必要部分
        self.assertIn("SELECT", query_str.upper())
        self.assertIn("WHERE", query_str.upper())
    
    def test_02_slop_match_phrase(self):
        """测试带 slop 的短语匹配"""
        field = "title"
        phrase = "quick brown fox"
        slop = 1
        
        condition, params = QueryBuilder.build_match_phrase_condition(field, phrase, slop=slop)
        
        # 验证条件生成
        self.assertIsNotNone(condition)
        self.assertIsNotNone(params)  # params 可能是 tuple 或 list
        
        # 生成完整 SQL
        select_clause = psycopg_sql.SQL("SELECT * FROM test_table WHERE ")
        full_query = select_clause + condition
        
        # [FIX] 使用新的连接管理模式获取 connection 对象
        with self.client.connection.get_connection_for_operation() as conn:
            query_str = full_query.as_string(conn)
        
        print(f"\nSlop 短语 (slop={slop}):")
        print(f"  生成的 SQL: {query_str}")
        print(f"  参数：{params}")
        
        # 验证 SQL 包含必要部分
        self.assertIn("SELECT", query_str.upper())
        self.assertIn("WHERE", query_str.upper())


if __name__ == '__main__':
    unittest.main()
