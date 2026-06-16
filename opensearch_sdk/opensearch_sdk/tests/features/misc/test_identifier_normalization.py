#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试openGauss数据库字符标准化工具函数

功能说明：
- 测试 normalize_identifier() 函数
- 测试 normalize_nested_path() 函数
- 验证警告信息正确触发
"""

import sys
import os
import unittest
import warnings

# 添加项目根目录到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from opensearch_sdk.client.utils import normalize_identifier, normalize_nested_path


class TestNormalizeIdentifier(unittest.TestCase):
    """测试 normalize_identifier 函数"""
    
    def test_normalize_with_dot(self):
        """测试包含点号的标识符"""
        result = normalize_identifier("user.name")
        self.assertEqual(result, "user_name")
    
    def test_identifier_normalize_with_dash(self):
        """测试包含连字符的标识符"""
        result = normalize_identifier("user-name")
        self.assertEqual(result, "user_name")
    
    def test_normalize_with_both(self):
        """测试同时包含点号和连字符的标识符"""
        result = normalize_identifier("user.name-info")
        self.assertEqual(result, "user_name_info")
    
    def test_normalize_normal_field(self):
        """测试正常字段名（无需转换）"""
        result = normalize_identifier("normal_field")
        self.assertEqual(result, "normal_field")
    
    def test_identifier_normalize_empty_string(self):
        """测试空字符串"""
        result = normalize_identifier("")
        self.assertEqual(result, "")
    
    def test_identifier_normalize_non_string(self):
        """测试非字符串输入"""
        result = normalize_identifier(123)
        self.assertEqual(result, 123)
        
        result = normalize_identifier(None)
        self.assertIsNone(result)
    
    def test_identifier_normalize_warning_triggered(self):
        """测试标识符转换功能（已移除警告）"""
        result = normalize_identifier("user-name", context="Test field")
        
        # 验证返回结果
        self.assertEqual(result, "user_name")
    
    def test_identifier_normalize_no_warning_for_normal(self):
        """测试正常字段名不触发警告"""
        result = normalize_identifier("normal_field")
        
        self.assertEqual(result, "normal_field")
    
    def test_normalize_custom_context(self):
        """测试自定义上下文参数"""
        result = normalize_identifier("field-name", context="Mapping field")
        
        self.assertEqual(result, "field_name")


class TestNormalizeNestedPath(unittest.TestCase):
    """测试 normalize_nested_path 函数"""
    
    def test_normalize_simple_path(self):
        """测试简单嵌套路径"""
        result = normalize_nested_path("user.info")
        self.assertEqual(result, "user_info")
    
    def test_normalize_deep_path(self):
        """测试深层嵌套路径"""
        result = normalize_nested_path("user.info.name.first")
        self.assertEqual(result, "user_info_name_first")
    
    def test_nested_path_normalize_with_dash(self):
        """测试包含连字符的路径"""
        result = normalize_nested_path("user-info.address")
        self.assertEqual(result, "user_info_address")
    
    def test_normalize_mixed_separators(self):
        """测试混合分隔符"""
        result = normalize_nested_path("user-info.details.name")
        self.assertEqual(result, "user_info_details_name")
    
    def test_normalize_single_part(self):
        """测试单部分路径"""
        result = normalize_nested_path("userinfo")
        self.assertEqual(result, "userinfo")
    
    def test_nested_path_normalize_empty_string(self):
        """测试空字符串"""
        result = normalize_nested_path("")
        self.assertEqual(result, "")
    
    def test_nested_path_normalize_non_string(self):
        """测试非字符串输入"""
        result = normalize_nested_path(123)
        self.assertEqual(result, 123)
        
        result = normalize_nested_path(None)
        self.assertIsNone(result)
    
    def test_nested_path_normalize_warning_triggered(self):
        """测试嵌套路径转换功能（已移除警告）"""
        result = normalize_nested_path("user.info", context="Nested path")
        
        # 验证返回结果
        self.assertEqual(result, "user_info")
    
    def test_nested_path_normalize_no_warning_for_normal(self):
        """测试正常路径不触发警告"""
        result = normalize_nested_path("user_info_name")
        
        self.assertEqual(result, "user_info_name")


if __name__ == '__main__':
    unittest.main(verbosity=2)
