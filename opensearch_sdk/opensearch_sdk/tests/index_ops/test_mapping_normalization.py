#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试openGauss数据库 Mapping 字段名标准化功能

功能说明：
- 测试创建索引时自动转换字段名中的 . 和 - 为 _
- 验证 nested 字段的标准化
- 确保转换后索引正常工作
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


class TestMappingNormalization(unittest.TestCase):
    """测试 Mapping 字段名标准化"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        # 默认配置（仅作为后备）
        cls.db_config = {
            'host': '172.17.9.26',
            'port': 5432,
            'database': 'es',
            'user': 'jzc',
            'password': os.getenv('DB_PASSWORD', '123qweASDz')  # 从环境变量获取，提供默认值用于开发环境
        }
        
        # 尝试加载真实配置
        config_path = os.path.join(project_root, 'db_config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 只更新存在的键，保留默认值作为后备
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
    def tearDownClass(cls):
        """清理测试环境"""
        if cls.skip_test:
            return
        try:
            test_indices = [
                'test_mapping_dot_dash',
                'test_mapping_nested_normalization'
            ]
            for index_name in test_indices:
                cls._safe_delete_index(index_name)
            cls.client.close()
        except Exception:
            pass
    
    def test_mapping_with_dot_and_dash(self):
        """测试包含点号和连字符的字段名自动转换"""
        if self.skip_test:
            self.skipTest("数据库连接不可用")
        
        index_name = 'test_mapping_dot_dash'
        
        # 确保索引不存在
        try:
            self.client.indices.delete(index_name)
        except Exception:
            pass
        
        # 定义包含特殊字符的 mapping
        mapping = {
            "mappings": {
                "properties": {
                    "user-name": {"type": "keyword"},      # 含 -
                    "user.info": {"type": "text"},         # 含 .
                    "normal_field": {"type": "keyword"},   # 正常
                    "field-with-dash": {"type": "long"}    # 多个 -
                }
            }
        }
        
        # 创建索引（自动转换字段名）
        result = self.client.indices.create(index_name, body=mapping)
        
        # [OK] 验证创建成功
        self.assertTrue(result.get('acknowledged', False), "索引应该创建成功")
        
        # 获取创建的 mapping 验证字段名已转换
        mapping_result = self.client.indices.get(index=index_name)
        properties = mapping_result[index_name]['mappings']['properties']
        
        # 验证转换后的字段名
        self.assertIn('user_name', properties, "user-name 应转换为 user_name")
        self.assertIn('user_info', properties, "user.info 应转换为 user_info")
        self.assertIn('normal_field', properties, "normal_field 保持不变")
        self.assertIn('field_with_dash', properties, "field-with-dash 应转换为 field_with_dash")
        
        # 验证原始字段名不存在
        self.assertNotIn('user-name', properties, "原始字段 user-name 不应存在")
        self.assertNotIn('user.info', properties, "原始字段 user.info 不应存在")
        self.assertNotIn('field-with-dash', properties, "原始字段 field-with-dash 不应存在")
        
        print("[PASS] Mapping 字段名标准化测试通过")
    
    def test_nested_field_normalization(self):
        """测试 nested 字段内部属性名标准化"""
        if self.skip_test:
            self.skipTest("数据库连接不可用")
        
        index_name = 'test_mapping_nested_normalization'
        
        # 确保索引不存在
        try:
            self.client.indices.delete(index=index_name)
        except Exception:
            pass
        
        # 定义包含特殊字符的 nested mapping
        mapping = {
            "mappings": {
                "properties": {
                    "author": {
                        "type": "nested",
                        "properties": {
                            "first-name": {"type": "text"},    # 含 -
                            "last.name": {"type": "text"},     # 含 .
                            "age": {"type": "integer"}         # 正常
                        }
                    },
                    "title": {"type": "text"}
                }
            }
        }
        
        # 创建索引（自动转换 nested 字段名）
        result = self.client.indices.create(index=index_name, body=mapping)
        
        # [OK] 验证创建成功
        self.assertTrue(result.get('acknowledged', False), "索引应该创建成功")
        
        # [OK] 关键验证：检查数据库表中的列是否展开
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
                    (index_name,)
                )
                columns = [row[0] for row in cursor.fetchall()]
            finally:
                cursor.close()
        
        # 验证 nested 字段已展开为扁平列
        self.assertIn('author__first_name', columns, "first-name 应转换为 author__first_name")
        self.assertIn('author__last_name', columns, "last.name 应转换为 author__last_name")
        self.assertIn('author__age', columns, "age 应转换为 author__age")
        self.assertIn('title', columns, "title 字段存在")
        
        # 验证原始字段名不存在
        self.assertNotIn('first-name', columns, "原始字段 first-name 不应存在")
        self.assertNotIn('last.name', columns, "原始字段 last.name 不应存在")
        
        print("[PASS] Nested 字段标准化测试通过（展开为 author__first_name, author__last_name, author__age）")


if __name__ == '__main__':
    unittest.main(verbosity=2)
