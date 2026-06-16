#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证字段名（变量名）的标准化处理不受索引名限制影响
"""
import unittest
import sys
import os
import warnings

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opensearch_sdk.client.utils import normalize_identifier


class TestFieldNameNormalization(unittest.TestCase):
    """测试字段名标准化处理"""
    
    def test_document_field_with_dot_converts(self):
        """测试文档字段名含点号时转换（不报错）"""
        result = normalize_identifier("user.name", "Document field")
        
        self.assertEqual(result, "user_name")
        print(f"[PASS] 文档字段名点号转换：user.name -> {result}")
    
    def test_document_field_with_hyphen_converts(self):
        """测试文档字段名含连字符时转换"""
        result = normalize_identifier("user-name", "Document field")
        
        self.assertEqual(result, "user_name")
        print(f"[PASS] 文档字段名连字符转换：user-name -> {result}")
    
    def test_query_field_with_dot_converts(self):
        """测试查询字段名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("price.value", "Query field")
            
            self.assertEqual(result, "price_value")
            print(f"[PASS] 查询字段名点号转换：price.value -> {result}")
    
    def test_mapping_field_with_dot_converts(self):
        """测试映射字段名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("field.subfield", "Mapping field")
            
            self.assertEqual(result, "field_subfield")
            print(f"[PASS] 映射字段名点号转换：field.subfield -> {result}")
    
    def test_index_column_with_dot_converts(self):
        """测试索引列名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("column.name", "Index column")
            
            self.assertEqual(result, "column_name")
            print(f"[PASS] 索引列名点号转换：column.name -> {result}")
    
    def test_nested_field_with_dot_converts(self):
        """测试嵌套字段名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("address.city", "Nested field 'user'")
            
            self.assertEqual(result, "address_city")
            print(f"[PASS] 嵌套字段名点号转换：address.city -> {result}")
    
    def test_sort_field_with_dot_converts(self):
        """测试排序字段名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("sort.field", "Sort field")
            
            self.assertEqual(result, "sort_field")
            print(f"[PASS] 排序字段名点号转换：sort.field -> {result}")
    
    def test_vector_column_with_dot_converts(self):
        """测试向量字段名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("vector.embedding", "Vector column")
            
            self.assertEqual(result, "vector_embedding")
            print(f"[PASS] 向量字段名点号转换：vector.embedding -> {result}")
    
    def test_text_column_with_dot_converts(self):
        """测试文本字段名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("text.content", "Text column")
            
            self.assertEqual(result, "text_content")
            print(f"[PASS] 文本字段名点号转换：text.content -> {result}")
    
    def test_delete_by_field_with_dot_converts(self):
        """测试删除条件字段名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("delete.field", "Delete by field")
            
            self.assertEqual(result, "delete_field")
            print(f"[PASS] 删除条件字段名点号转换：delete.field -> {result}")
    
    def test_dynamic_column_with_dot_converts(self):
        """测试动态列名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("dynamic.column", "Dynamic column")
            
            self.assertEqual(result, "dynamic_column")
            print(f"[PASS] 动态列名点号转换：dynamic.column -> {result}")
    
    def test_column_name_from_db_with_dot_converts(self):
        """测试数据库列名含点号时转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("db.column", "Column name from DB")
            
            self.assertEqual(result, "db_column")
            print(f"[PASS] 数据库列名点号转换：db.column -> {result}")
    
    def test_field_with_both_dot_and_hyphen(self):
        """测试字段名同时含点号和连字符"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("user-info.email", "Document field")
            
            self.assertEqual(result, "user_info_email")
            print(f"[PASS] 字段名多重转换：user-info.email -> {result}")
    
    def test_normal_field_no_conversion(self):
        """测试正常字段名无需转换"""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_identifier("normal_field", "Document field")
            
            self.assertEqual(result, "normal_field")
            self.assertEqual(len(w), 0)  # 不应该有警告
            print(f"[PASS] 正常字段名无转换：normal_field")
    
    def test_context_detection_only_for_index_name(self):
        """验证只有 'Index name' context 才会触发点号检查"""
        # 这些 context 都不应该触发点号检查
        safe_contexts = [
            "Document field",
            "Query field",
            "Mapping field",
            "Index column",
            "Sort field",
            "Vector column",
            "Text column",
            "Delete by field",
            "Dynamic column",
            "Column name from DB",
            "Nested field",
        ]
        
        for context in safe_contexts:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                # 含点号的字段名应该被转换，但不应该抛出 ValueError
                result = normalize_identifier("test.field", context)
                self.assertEqual(result, "test_field")
        
        print(f"[PASS] 所有非索引名 context 都允许字段名含点号（会转换）")


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)
