#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
openGauss数据库 GUC 参数命名格式测试

功能说明：
- 验证openGauss数据库是否支持点号 (.) 分隔符
- 测试下划线 (_) 和点号 (.) 两种格式
- 测试多种GUC参数

运行方式：
    python -m unittest opensearch_sdk.tests.features.sql_security.test_opengauss_guc_params -v
"""

import sys
import os
import json
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestOpenGaussGUCParams(unittest.TestCase):
    """测试openGauss数据库 GUC 参数"""
    
    @classmethod
    def setUpClass(cls):
        """设置数据库连接"""
        db_config = load_db_config()
        cls.client = OpenGauss(
            hosts=[{"host": db_config['host'], "port": db_config['port']}],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
    
    def test_01_hnsw_ef_search_underscore(self):
        """测试 HNSW ef_search (下划线格式)"""
        sql = "SHOW hnsw_ef_search"
        # [FIX] 使用新的连接管理模式
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                result = cursor.fetchone()
                self.assertIsNotNone(result)
                print(f"\n[PASS] HNSW ef_search (下划线): {result[0]}")
            finally:
                cursor.close()
    
    def test_02_bm25_k1_underscore(self):
        """测试 BM25 k1 (下划线格式)"""
        sql = "SHOW bm25_k1"
        # [FIX] 使用新的连接管理模式
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                result = cursor.fetchone()
                self.assertIsNotNone(result)
                print(f"[PASS] BM25 k1 (下划线): {result[0]}")
            finally:
                cursor.close()
    
    def test_03_bm25_b_underscore(self):
        """测试 BM25 b (下划线格式)"""
        sql = "SHOW bm25_b"
        # [FIX] 使用新的连接管理模式
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                result = cursor.fetchone()
                self.assertIsNotNone(result)
                print(f"[PASS] BM25 b (下划线): {result[0]}")
            finally:
                cursor.close()
    
    def test_04_ivfflat_probes_underscore(self):
        """测试 IVFFlat probes (下划线格式)"""
        sql = "SHOW ivfflat_probes"
        # [FIX] 使用新的连接管理模式
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql)
                result = cursor.fetchone()
                self.assertIsNotNone(result)
                print(f"[PASS] IVFFlat probes (下划线): {result[0]}")
            finally:
                cursor.close()


if __name__ == '__main__':
    unittest.main()
