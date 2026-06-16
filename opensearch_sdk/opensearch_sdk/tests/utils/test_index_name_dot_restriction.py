#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试索引名称禁止包含点号的限制
"""
import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opensearch_sdk.client.utils import normalize_identifier


class TestIndexNameDotRestriction(unittest.TestCase):
    """测试索引名称点号限制"""
    
    def test_index_name_with_dot_raises_error(self):
        """测试索引名包含点号时抛出 ValueError"""
        with self.assertRaises(ValueError) as context:
            normalize_identifier("my.index", "Index name")
        
        # 验证错误信息包含关键内容
        error_msg = str(context.exception)
        self.assertIn("my.index", error_msg)
        self.assertIn("dots", error_msg.lower())
        self.assertIn("not allowed", error_msg.lower())
        self.assertIn("Opensearch", error_msg)
        print(f"[PASS] 正确抛出错误：{error_msg}")
    
    def test_index_name_with_multiple_dots_raises_error(self):
        """测试索引名包含多个点号时抛出 ValueError"""
        with self.assertRaises(ValueError) as context:
            normalize_identifier("my.index.v1", "Index name")
        
        error_msg = str(context.exception)
        self.assertIn("my.index.v1", error_msg)
        print(f"[PASS] 正确抛出错误：{error_msg}")
    
    def test_index_name_with_hyphen_converts_to_underscore(self):
        """测试索引名包含连字符时转换为下划线（已移除警告）"""
        result = normalize_identifier("my-index", "Index name")
        
        self.assertEqual(result, "my_index")
        print(f"[PASS] 连字符转换成功：my-index -> {result}")
    
    def test_index_name_normal_passes(self):
        """测试正常的索引名通过验证"""
        result = normalize_identifier("my_index", "Index name")
        self.assertEqual(result, "my_index")
        print("[PASS] 正常索引名通过验证")
    
    def test_field_name_with_dot_still_converts(self):
        """测试字段名包含点号时仍然转换为下划线（不报错，已移除警告）"""
        result = normalize_identifier("user.name", "Document field")
        
        self.assertEqual(result, "user_name")
        print(f"[PASS] 字段名点号转换成功：user.name -> {result}")
    
    def test_field_name_with_both_dot_and_hyphen(self):
        """测试字段名同时包含点号和连字符"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("user-info.email", "Document field")
            
            self.assertEqual(result, "user_info_email")
            print(f"[PASS] 字段名多重转换成功：user-info.email -> {result}")
    
    def test_context_detection_case_insensitive(self):
        """测试上下文检测不区分大小写"""
        # 各种形式的 "Index name" 都应该触发点号检查
        test_cases = [
            "Index name",
            "index name",
            "INDEX NAME",
            "Index Name",
        ]
        
        for context in test_cases:
            with self.assertRaises(ValueError):
                normalize_identifier("test.index", context)
        
        print(f"[PASS] 上下文检测对所有大小写形式都有效")
    
    def test_non_index_context_allows_dots(self):
        """测试非索引名的上下文允许点号（会转换但不报错）"""
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Sort field 不是 Index name，所以允许点号
            result = normalize_identifier("field.subfield", "Sort field")
            self.assertEqual(result, "field_subfield")
            print(f"[PASS] 非索引名上下文允许点号：field.subfield -> {result}")


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)
