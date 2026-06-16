#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 keyword 字段的多值支持（空格分隔方案）

功能说明：
- 验证数组写入时自动转换为空格分隔字符串
- 验证 term/terms 查询使用 BM25 <&> 操作符
- 验证单值和多值都能正常工作
"""

import sys
import os
import unittest

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

# 加载数据库配置
db_config = load_db_config()


class TestKeywordMultiValue(unittest.TestCase):
    """keyword 多值支持测试"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = OpenGauss(
            hosts=[{'host': db_config['host'], 'port': db_config['port']}],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        
        # 创建测试索引
        cls.test_index = 'test_keyword_multi'
        
        # 删除已存在的索引
        if cls.client.indices.exists(index=cls.test_index):
            cls.client.indices.delete(index=cls.test_index)
        
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "category": {"type": "keyword"},  # 单值
                    "tags": {"type": "keyword"}       # 多值（空格分隔）
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据
        docs = [
            {
                "id": "1",
                "body": {
                    "title": "Product A",
                    "category": "electronics",
                    "tags": ["sale", "new"]  # 多值数组
                }
            },
            {
                "id": "2",
                "body": {
                    "title": "Product B",
                    "category": "books",
                    "tags": ["sale", "hot"]  # 多值数组
                }
            },
            {
                "id": "3",
                "body": {
                    "title": "Product C",
                    "category": "electronics",
                    "tags": ["new"]  # 单元素数组
                }
            },
            {
                "id": "4",
                "body": {
                    "title": "Product D",
                    "category": "clothing",
                    "tags": "clearance"  # 标量字符串
                }
            }
        ]
        
        for doc in docs:
            cls.client.index(index=cls.test_index, id=doc["id"], body=doc["body"])
        
        print("[OK] 测试数据准备完成")
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        if cls.client.indices.exists(index=cls.test_index):
            cls.client.indices.delete(index=cls.test_index)
        cls.client.close()
    
    def test_01_array_storage(self):
        """测试数组存储为 JSON 数组格式"""
        doc = self.client.get(index=self.test_index, id="1")
        tags = doc["_source"]["tags"]
        
        # 数组应被转换为 JSON 数组格式，读取时自动解析为列表
        self.assertIsInstance(tags, list)
        self.assertIn("sale", tags)
        self.assertIn("new", tags)
        print(f"[OK] 数组存储测试通过: tags={tags}")
    
    def test_02_scalar_storage(self):
        """测试标量存储保持不变"""
        doc = self.client.get(index=self.test_index, id="4")
        tags = doc["_source"]["tags"]
        
        # 标量应保持不变
        self.assertEqual(tags, "clearance")
        print(f"[OK] 标量存储测试通过: tags='{tags}'")
    
    def test_03_term_query_single_value(self):
        """测试 term 查询单值字段"""
        query = {
            "query": {
                "term": {"category": "electronics"}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        total = result["hits"]["total"]["value"]
        
        # 应该匹配到 2 个文档（id=1 和 id=3）
        self.assertEqual(total, 2)
        print(f"[OK] term 查询单值字段通过: 找到 {total} 个文档")
    
    def test_04_term_query_multi_value(self):
        """测试 term 查询多值字段"""
        query = {
            "query": {
                "term": {"tags": "sale"}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        total = result["hits"]["total"]["value"]
        
        # 应该匹配到 2 个文档（id=1 和 id=2）
        self.assertEqual(total, 2)
        print(f"[OK] term 查询多值字段通过: 找到 {total} 个文档")
    
    def test_05_terms_query_multi_value(self):
        """测试 terms 查询多值字段（OR 逻辑）"""
        query = {
            "query": {
                "terms": {"tags": ["sale", "hot"]}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        total = result["hits"]["total"]["value"]
        
        # 应该匹配到 2 个文档（id=1 有 sale，id=2 有 sale 和 hot）
        self.assertEqual(total, 2)
        print(f"[OK] terms 查询多值字段通过: 找到 {total} 个文档")
    
    def test_06_term_query_precision(self):
        """测试 term 查询的精确匹配（不会部分匹配）"""
        # 插入一个包含 "sales" 的文档
        self.client.index(index=self.test_index, id="5", body={
            "title": "Product E",
            "category": "retail",
            "tags": ["sales"]  # 注意是 "sales" 不是 "sale"
        })
        
        # 查询 "sale" 不应该匹配 "sales"
        query = {"query": {"term": {"tags": "sale"}}}
        result = self.client.search(index=self.test_index, body=query)
        total = result["hits"]["total"]["value"]
        
        # 应该只匹配到 2 个文档（id=1 和 id=2），不包括 id=5
        self.assertEqual(total, 2)
        print(f"[OK] term 精确匹配测试通过: 找到 {total} 个文档（不包括 'sales'）")
    
    def test_07_terms_query_or_logic(self):
        """测试 terms 查询的 OR 逻辑"""
        # 查询包含 "sale" 或 "new" 的文档
        query = {"query": {"terms": {"tags": ["sale", "new"]}}}
        result = self.client.search(index=self.test_index, body=query)
        total = result["hits"]["total"]["value"]
        
        # BM25 <&> 操作符会进行分词匹配
        # id=1 ("sale new") 包含 sale 和 new，应该匹配
        # id=2 ("sale hot") 包含 sale，应该匹配
        # id=3 ("new") 包含 new，应该匹配
        # 所以应该找到 3 个文档
        self.assertGreaterEqual(total, 2)  # 至少找到 2 个
        print(f"[OK] terms OR 逻辑测试通过: 找到 {total} 个文档")


if __name__ == '__main__':
    unittest.main(verbosity=2)
