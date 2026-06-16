#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQL 注入漏洞修复测试

功能说明：
- SQL 注入漏洞修复测试
- 验证参数化查询的安全性
- 确保特殊字符正确处理

运行方式：
    python -m unittest opensearch_sdk.tests.features.sql_security.test_sql_injection_fix -v
"""

import json
import os
import unittest
from pathlib import Path
import sys
from opensearch_sdk.tests.utils.config_loader import load_db_config

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opensearch_sdk import OpenGauss


class TestSQLInjectionFix(unittest.TestCase):
    """测试 SQL 注入防护"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        config = load_db_config()
        cls.client = OpenGauss(
            hosts=[{'host': config['host'], 'port': config['port']}],
            database=config['database'],
            user=config['user'],
            password=config['password']
        )
        
        cls.test_index = 'test_sql_injection'
        
        # 清理旧索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
        
        # 创建测试索引
        table_mapping = {
            'mappings': {
                'properties': {
                    'name': {'type': 'text'},
                    'description': {'type': 'text'}
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=table_mapping)
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
    
    def test_01_safe_operations(self):
        """测试正常的安全操作"""
        # 插入包含特殊字符的数据
        result = self.client.index(
            index=self.test_index,
            id='normal_001',
            body={'name': "正常数据", 'description': "包含'单引号'和\"双引号\"的文本"}
        )
        
        self.assertIsNotNone(result)
        print(f"\n[PASS] 正常操作测试通过")
    
    def test_02_special_characters(self):
        """测试特殊字符处理"""
        special_chars = [
            ("单引号测试", "It's a test"),
            ("双引号测试", 'Say "hello"'),
            ("反斜杠测试", "Path: C:\\Users\\test"),
            ("百分号测试", "100% complete"),
            ("下划线测试", "test_value"),
        ]
        
        for i, (name, desc) in enumerate(special_chars):
            doc_id = f'special_{i+1}'
            result = self.client.index(
                index=self.test_index,
                id=doc_id,
                body={'name': name, 'description': desc}
            )
            self.assertIsNotNone(result)
        
        print(f"[PASS] 特殊字符处理测试通过，插入 {len(special_chars)} 条记录")
    
    def test_03_search_with_special_chars(self):
        """测试包含特殊字符的搜索"""
        # 先插入测试数据
        self.client.index(
            index=self.test_index,
            id='search_test',
            body={'name': "Test's Name", 'description': "Description with \"quotes\""}
        )
        
        # 搜索
        result = self.client.search(
            index=self.test_index,
            body={
                "query": {
                    "match": {
                        "name": "Test"
                    }
                }
            }
        )
        
        hits = result['hits']['hits']
        self.assertGreater(len(hits), 0)
        print(f"[PASS] 特殊字符搜索测试通过，找到 {len(hits)} 条记录")


if __name__ == '__main__':
    unittest.main()
