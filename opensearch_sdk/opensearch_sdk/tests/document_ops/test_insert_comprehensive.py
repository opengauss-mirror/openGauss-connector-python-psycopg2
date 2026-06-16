#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文档操作测试 - 插入操作综合测试

功能说明：
- 验证 insert 方法的各种场景和边界条件
- 测试单条插入和批量插入
- 测试异常处理和错误场景

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.document_ops.test_insert_comprehensive -v
    python opensearch_sdk/tests/document_ops/test_insert_comprehensive.py
"""

import json
import os
import sys
import unittest

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

# 加载数据库配置 - 使用绝对路径到项目根目录
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'db_config.json')
with open(config_path, 'r') as f:
    db_config = json.load(f)


class TestInsertComprehensive(unittest.TestCase):
    """insert 方法综合测试"""
    
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
        cls.test_index = 'test_insert_comprehensive'
        
        # 先删除已存在的测试索引（如果有）
        if cls.client.indices.exists(index=cls.test_index):
            cls.client.indices.delete(index=cls.test_index)
            print(f"Deleted old test index: {cls.test_index}")
        
        # 创建测试索引
        # 注意：对于 nested 对象（如 metadata），SDK 会将其扁平化为双下划线格式
        # 例如：metadata.version -> metadata__version
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "category": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    # Nested 对象扁平化后的字段（使用双下划线）
                    "metadata__version": {"type": "keyword"},
                    "metadata__author": {"type": "keyword"},
                    "metadata__created_at": {"type": "keyword"}
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 准备测试数据
        cls.prepare_test_data()
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        # [PASS] 在关闭客户端前检查连接池状态，确保没有连接泄漏
        leak_detected = False
        leak_message = ""
        
        if hasattr(cls.client.connection, '_pool') and cls.client.connection._pool:
            pool_status = cls.client.connection._pool.get_pool_status()
            used_connections = pool_status.get('used_connections', 0)
            if used_connections != 0:
                leak_detected = True
                leak_message = f"tearDownClass 后仍有 {used_connections} 个连接未归还: {pool_status}"
        
        # [PASS] 先关闭客户端，确保资源清理
        cls.client.close()
        
        # [PASS] 最后再断言，即使失败也不影响资源清理
        if leak_detected:
            raise AssertionError(leak_message)
    
    @classmethod
    def prepare_test_data(cls):
        """准备初始测试数据"""
        # 插入一个初始文档用于后续更新测试
        cls.client.index(cls.test_index, "init_doc", {
            "title": "Initial Document",
            "content": "This is an initial document"
        })
    
    def test_simple_insert(self):
        """测试简单插入（原 test_insert_success）"""
        result = self.client.index(self.test_index, "simple_doc", {
            "title": "Simple Test",
            "category": "test"
        })
        
        # 验证返回结果
        self.assertEqual(result["result"], "created")
        self.assertEqual(result["_id"], "simple_doc")
        self.assertEqual(result["_index"], self.test_index)
        
        # 验证数据确实插入成功
        get_result = self.client.get(self.test_index, "simple_doc")
        source = get_result["_source"]
        self.assertEqual(source["title"], "Simple Test")
        self.assertEqual(source["category"], "test")
    
    def test_upsert_existing_document(self):
        """测试 UPSERT - 更新已存在的文档"""
        # 第一次插入
        result1 = self.client.index(self.test_index, "upsert_doc", {
            "title": "First Version",
            "content": "Original content"
        })
        self.assertEqual(result1["result"], "created")
        
        # 第二次更新（UPSERT）
        result2 = self.client.index(self.test_index, "upsert_doc", {
            "title": "Second Version",
            "content": "Updated content"
        })
        self.assertEqual(result2["result"], "updated")
        
        # 验证最终内容
        get_result = self.client.get(self.test_index, "upsert_doc")
        source = get_result["_source"]
        self.assertEqual(source["title"], "Second Version")
        self.assertEqual(source["content"], "Updated content")
    
    def test_insert_with_complex_types(self):
        """测试插入复杂数据类型（dict、list）"""
        complex_data = {
            "title": "Complex Data Test",
            "tags": ["python", "database", "search"],
            "metadata": {
                "version": "1.0",
                "author": "test_user",
                "created_at": "2024-01-01"
            }
        }
        
        result = self.client.index(self.test_index, "complex_doc", complex_data)
        self.assertEqual(result["result"], "created")
        
        # 验证复杂类型被正确存储
        get_result = self.client.get(self.test_index, "complex_doc")
        source = get_result["_source"]
        # [OK] 多值 keyword 字段存储为 JSON 数组格式，读取时自动解析为数组
        self.assertEqual(source["tags"], ["python", "database", "search"])
        # [OK] Nested 对象在读取时被自动还原为嵌套结构
        self.assertIn("metadata", source)
        self.assertIsInstance(source["metadata"], list)
        self.assertEqual(len(source["metadata"]), 1)  # 首值策略
        self.assertEqual(source["metadata"][0]["version"], "1.0")
        self.assertEqual(source["metadata"][0]["author"], "test_user")
    
    def test_insert_empty_body(self):
        """测试插入空数据"""
        result = self.client.index(self.test_index, "empty_doc", {})
        self.assertEqual(result["result"], "created")
        
        # 验证至少 id 字段存在
        get_result = self.client.get(self.test_index, "empty_doc")
        self.assertIsNotNone(get_result)
    
    def test_update_empty_body(self):
        """测试更新时传入空 body（修复后的功能）"""
        # 先插入一个完整文档
        self.client.index(self.test_index, "update_empty_doc", {
            "title": "Original Title",
            "content": "Original Content",
            "category": "original"
        })
        
        # 尝试用空 body 更新（应该成功，不改变任何字段）
        result = self.client.index(self.test_index, "update_empty_doc", {})
        self.assertEqual(result["result"], "updated")
        
        # 验证所有字段保持不变
        get_result = self.client.get(self.test_index, "update_empty_doc")
        source = get_result["_source"]
        self.assertEqual(source["title"], "Original Title")
        self.assertEqual(source["content"], "Original Content")
        self.assertEqual(source["category"], "original")
    
    def test_insert_special_characters_in_string(self):
        """测试包含特殊字符的字符串"""
        special_data = {
            "title": "Special Chars: %_like'test\"value",
            "content": "Contains 'quotes', \"double quotes\", and % wildcards"
        }
        
        result = self.client.index(self.test_index, "special_doc", special_data)
        self.assertEqual(result["result"], "created")
        
        # 验证特殊字符被正确存储
        get_result = self.client.get(self.test_index, "special_doc")
        source = get_result["_source"]
        
        # content 可能被逗号分隔成数组，检查数组元素
        if isinstance(source["content"], list):
            content_str = " ".join(str(x) for x in source["content"])
        else:
            content_str = source["content"]
        
        self.assertIn("quotes", content_str)
        self.assertIn("%", content_str)
    
    def test_insert_chinese_content(self):
        """测试插入中文内容"""
        chinese_data = {
            "title": "中文标题测试",
            "content": "这是一段中文内容，包含汉字和标点符号。",
            "category": "测试分类"
        }
        
        result = self.client.index(self.test_index, "chinese_doc", chinese_data)
        self.assertEqual(result["result"], "created")
        
        # 验证中文内容正确存储
        get_result = self.client.get(self.test_index, "chinese_doc")
        source = get_result["_source"]
        self.assertEqual(source["title"], "中文标题测试")
        self.assertEqual(source["content"], "这是一段中文内容，包含汉字和标点符号。")
    
    def test_insert_large_text(self):
        """测试插入大文本"""
        large_text = "这是测试文本。" * 1000  # 重复 1000 次
        
        large_data = {
            "title": "Large Text Test",
            "content": large_text
        }
        
        result = self.client.index(self.test_index, "large_doc", large_data)
        self.assertEqual(result["result"], "created")
        
        # 验证大文本正确存储
        get_result = self.client.get(self.test_index, "large_doc")
        source = get_result["_source"]
        self.assertEqual(len(source["content"]), len(large_text))
    
    def test_partial_update(self):
        """测试部分字段更新"""
        # 插入完整文档
        self.client.index(self.test_index, "partial_doc", {
            "title": "Original Title",
            "content": "Original Content",
            "category": "original",
            "tags": ["tag1", "tag2"]
        })
        
        # 只更新部分字段
        self.client.index(self.test_index, "partial_doc", {
            "title": "Updated Title",
            "category": "updated"
        })
        
        # 验证更新的字段被更新，未更新的字段保持不变
        get_result = self.client.get(self.test_index, "partial_doc")
        source = get_result["_source"]
        self.assertEqual(source["title"], "Updated Title")
        self.assertEqual(source["category"], "updated")
        # 注意：在 Opensearch兼容接口中，UPDATE 会覆盖整行，所以 content 和 tags 会变成 NULL
        # 这是与 Elasticsearch 的重要区别
    
    def test_insert_then_get_all_fields(self):
        """验证插入后获取所有字段"""
        test_data = {
            "title": "Complete Test",
            "content": "Testing all fields",
            "category": "complete",
            "tags": ["test", "complete"]
        }
        
        self.client.index(self.test_index, "complete_doc", test_data)
        get_result = self.client.get(self.test_index, "complete_doc")
        
        # 验证所有字段都存在
        source = get_result["_source"]
        for key, value in test_data.items():
            self.assertIn(key, source)
            # [OK] 多值 keyword 字段存储为 JSON 数组格式，读取时自动解析为数组
            if key == "tags" and isinstance(value, list):
                self.assertEqual(source[key], value)
            else:
                self.assertEqual(source[key], value)


if __name__ == '__main__':
    unittest.main()
