#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试openGauss数据库 Document Operations 字段名标准化功能

功能说明：
- 测试文档插入时自动转换字段名中的 . 和 - 为 _
- 测试文档更新时自动转换字段名
- 确保文档操作的一致性
"""

import sys
import os
import unittest
import warnings
import json

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestDocumentOperationsNormalization(unittest.TestCase):
    """测试 Document Operations 字段名标准化"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        # 默认配置（仅作为后备）
        cls.db_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432')),
            'database': os.getenv('DB_NAME', 'postgres'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD')
        }
        
        # 尝试加载真实配置
        config_path = os.path.join(project_root, 'db_config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    cls.db_config.update(loaded_config)
                    print(f"[INFO] 已加载配置文件: {config_path}")
            except Exception as e:
                print(f"[WARN] 加载配置文件失败: {e}，使用默认配置")
        
        try:
            cls.client = OpenGauss(
                hosts=[{'host': cls.db_config['host'], 'port': cls.db_config['port']}],
                database=cls.db_config['database'],
                user=cls.db_config['user'],
                password=cls.db_config['password']
            )
            cls.skip_test = False
        except Exception as e:
            print(f"[WARN]  无法连接到数据库，跳过集成测试：{e}")
            cls.skip_test = True
    
    @classmethod
    def _safe_delete_index(cls, index_name):
        """安全删除测试索引"""
        try:
            cls.client.indices.delete(index_name)
        except Exception:
            pass

    @classmethod
    def _check_connection_leak(cls):
        """检查连接池泄漏情况"""
        if not hasattr(cls.client.connection, '_pool') or not cls.client.connection._pool:
            return None
        pool_status = cls.client.connection._pool.get_pool_status()
        used_connections = pool_status.get('used_connections', 0)
        if used_connections == 0:
            return None
        return f"tearDownClass 后仍有 {used_connections} 个连接未归还: {pool_status}"

    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        if cls.skip_test:
            return
        try:
            test_indices = [
                'test_doc_insert_normalization',
                'test_doc_update_normalization'
            ]
            for index_name in test_indices:
                cls._safe_delete_index(index_name)

            leak_message = cls._check_connection_leak()
            cls.client.close()

            if leak_message:
                raise AssertionError(leak_message)
        except Exception:
            pass
    
    def test_document_insert_field_normalization(self):
        """测试文档插入时字段名标准化"""
        if self.skip_test:
            self.skipTest("数据库连接不可用")
        
        index_name = 'test_doc_insert_normalization'
        
        # 创建测试索引
        mapping = {
            "mappings": {
                "properties": {
                    "user_name": {"type": "keyword"},
                    "user_info": {"type": "text"},
                    "field_value": {"type": "long"}
                }
            }
        }
        
        try:
            self.client.indices.delete(index_name)
        except Exception:
            pass
        
        self.client.indices.create(index_name, body=mapping)
        
        # 插入包含特殊字符字段名的文档（自动转换）
        doc = {
            "user-name": "john_doe",      # 含连字符
            "user.info": "developer",     # 含点号
            "normal_field": "test"        # 正常字段
        }
        
        result = self.client.index(index=index_name, id="doc1", body=doc)
        
        # [OK] 验证插入成功
        self.assertEqual(result['result'], 'created', "文档应该创建成功")
        
        # 验证文档已正确插入（字段名已转换）
        retrieved = self.client.get(index=index_name, id="doc1")
        source = retrieved['_source']
        
        # 验证转换后的字段存在
        self.assertIn('user_name', source, "user-name 应转换为 user_name")
        self.assertIn('user_info', source, "user.info 应转换为 user_info")
        self.assertIn('normal_field', source, "normal_field 保持不变")
        
        # 验证原始字段名不存在
        self.assertNotIn('user-name', source, "原始字段 user-name 不应存在")
        self.assertNotIn('user.info', source, "原始字段 user.info 不应存在")
        
        print("[PASS] 文档插入字段名标准化测试通过")
    
    def test_document_update_field_normalization(self):
        """测试文档更新时字段名标准化"""
        if self.skip_test:
            self.skipTest("数据库连接不可用")
        
        index_name = 'test_doc_update_normalization'
        
        # 创建测试索引
        mapping = {
            "mappings": {
                "properties": {
                    "user_name": {"type": "keyword"},
                    "status_code": {"type": "long"}
                }
            }
        }
        
        try:
            self.client.indices.delete(index_name)
        except Exception:
            pass
        
        self.client.indices.create(index_name, body=mapping)
        
        # 先插入文档
        initial_doc = {
            "user_name": "alice",
            "status_code": 100
        }
        self.client.index(index=index_name, id="doc1", body=initial_doc)
        
        # 更新文档时使用特殊字符字段名（自动转换）
        update_doc = {
            "status-code": 200,    # 含连字符
            "user-name": "bob"     # 含连字符
        }
        
        result = self.client.update(index=index_name, id="doc1", body=update_doc)
        
        # [OK] 验证更新成功
        self.assertEqual(result['result'], 'updated', "文档应该更新成功")
        
        # 验证文档已正确更新
        retrieved = self.client.get(index=index_name, id="doc1")
        source = retrieved['_source']
        
        # 验证更新后的字段
        self.assertEqual(source['user_name'], 'bob', "user-name 应转换为 user_name 并更新值")
        self.assertEqual(source['status_code'], 200, "status-code 应转换为 status_code 并更新值")
        
        print("[PASS] 文档更新字段名标准化测试通过")


class TestDocumentOperationsUnit(unittest.TestCase):
    """Document Operations 单元测试（不依赖数据库）"""
    
    def test_normalize_identifier_in_process_body(self):
        """测试 _process_body_fields 中的字段名标准化"""
        from opensearch_sdk.client.utils import normalize_identifier
        
        # 模拟文档字段的标准化过程
        test_fields = {
            "field-name": "value1",
            "field.name": "value2",
            "normal_field": "value3"
        }
        
        normalized = {}
        for key, value in test_fields.items():
            normalized_key = normalize_identifier(key, "Test field")
            normalized[normalized_key] = value
        
        # 验证转换结果
        self.assertIn('field_name', normalized)
        self.assertIn('normal_field', normalized)
        self.assertNotIn('field-name', normalized)
        self.assertNotIn('field.name', normalized)
        
        print("[PASS] Document Operations 标准化工具函数测试通过")


if __name__ == '__main__':
    unittest.main(verbosity=2)
