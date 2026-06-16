#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
动态列功能测试 - 严格模式

功能说明：
- 测试动态列在严格模式下的行为
- 验证未定义字段的自动添加
- 检查数据库列的动态创建

运行方式：
    python -m unittest opensearch_sdk.tests.features.data_types.test_dynamic_column -v
"""

import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.features.data_types.dynamic_column_common import (
    delete_index_safely,
    fetch_columns,
    recreate_base_index,
    refresh_index_safely,
)
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestDynamicColumn(unittest.TestCase):
    """测试动态列功能"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = OpenGauss(**load_db_config())
        cls.index_name = "test_dynamic_column"
        recreate_base_index(cls.client, cls.index_name)
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            delete_index_safely(cls.client, cls.index_name)
            cls.client.close()
        except Exception:
            pass
    
    def test_dynamic_column_full_workflow(self):
        """测试动态列完整工作流程：插入、验证列存在、查询数据"""
        # 步骤 1: 插入包含动态字段的文档
        doc = {
            "title": "测试文档",
            "content": "这是一个测试文档",
            "dynamic_field": "动态添加的字段",
            "dynamic_number": 123,
            "dynamic_bool": True
        }
        
        result = self.client.index(index=self.index_name, id="doc1", body=doc)
        self.assertIsNotNone(result)
        print(f"\n[PASS] 文档插入成功：{result}")
        
        refresh_index_safely(self.client, self.index_name)
        
        # 步骤 2: 验证动态字段已添加到数据库
        db_columns = fetch_columns(self.client, self.index_name)
        
        print(f"\n数据库中的列:")
        for col_name, col_type in sorted(db_columns):
            print(f"  - {col_name}: {col_type}")
        
        # 检查动态字段是否存在
        expected_fields = ['dynamic_field', 'dynamic_number', 'dynamic_bool']
        column_names = [col[0] for col in db_columns]
        
        for field in expected_fields:
            self.assertIn(field, column_names, f"动态字段 '{field}' 应该被添加")
            print(f"[PASS] 动态字段 '{field}' 已成功添加")

        print(f"\n[PASS] 查询到 {len(column_names)} 列")


if __name__ == "__main__":
    unittest.main()
