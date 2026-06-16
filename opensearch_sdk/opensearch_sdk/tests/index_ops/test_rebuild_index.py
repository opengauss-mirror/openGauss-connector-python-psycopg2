#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
索引重建功能测试
测试 rebuild_index 方法的正确性
"""

import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from opensearch_sdk import OpenGauss


class TestRebuildIndex(unittest.TestCase):
    """索引重建功能测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备：创建测试表和索引"""
        # 加载配置
        config_path = os.path.join(os.path.dirname(__file__), '..', 'db_config.json')
        if not os.path.exists(config_path):
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'db_config.json')
        
        with open(config_path, 'r', encoding='utf-8') as f:
            import json
            cls.config = json.load(f)
        
        # 创建客户端（Opensearch 需要 hosts 参数）
        cls.client = OpenGauss(
            hosts=[{'host': cls.config.get('host', 'localhost'), 'port': cls.config.get('port', 5432)}],
            database=cls.config.get('database') or cls.config.get('dbname'),
            user=cls.config.get('user'),
            password=cls.config.get('password')
        )
        
        # 清理旧表
        try:
            cls.client.indices.delete('test_rebuild_table')
        except:
            pass
        
        # 创建测试表（使用简单 mapping）
        mapping = {
            "mappings": {
                "properties": {
                    "name": {"type": "keyword"},
                    "email": {"type": "keyword"},
                    "description": {"type": "text"}
                }
            }
        }
        cls.client.indices.create('test_rebuild_table', body=mapping)
        
        # 插入测试数据
        for i in range(5):
            cls.client.index(
                index='test_rebuild_table',
                id=str(i+1),
                body={
                    "name": f"user_{i+1}",
                    "email": f"user{i+1}@test.com",
                    "description": f"Test user {i+1}"
                }
            )
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理：删除测试表"""
        try:
            cls.client.indices.delete('test_rebuild_table')
        except:
            pass
        
        cls.client.close()
    
    def test_rebuild_btree_index(self):
        """测试重建 B-tree 索引"""
        # 先创建一个 B-tree 索引
        index_name = "idx_test_name"
        table_name = "test_rebuild_table"
        column_name = "name"
        
        # 创建初始索引
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"CREATE INDEX {index_name} ON {table_name} USING btree ({column_name})")
                conn.commit()
            finally:
                cursor.close()
        
        # 验证索引存在
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT indexname FROM pg_indexes 
                    WHERE tablename = %s AND indexname = %s
                """, (table_name, index_name))
                result = cursor.fetchone()
                self.assertIsNotNone(result, "索引应该存在")
            finally:
                cursor.close()
            conn.rollback()  # [FIX] 清理 SELECT 开启的事务
        
        # 重建索引
        result = self.client.indices.rebuild_index(
            index_name=index_name,
            table_name=table_name,
            column_name=column_name,
            index_type="btree"
        )
        
        # 验证结果
        self.assertTrue(result['acknowledged'])
        self.assertEqual(result['index'], index_name)
        self.assertEqual(result['table'], table_name)
        self.assertEqual(result['column'], column_name)
        self.assertEqual(result['type'], 'btree')
        
        # 验证索引仍然存在
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT indexname FROM pg_indexes 
                    WHERE tablename = %s AND indexname = %s
                """, (table_name, index_name))
                result = cursor.fetchone()
                self.assertIsNotNone(result, "重建后索引应该存在")
            finally:
                cursor.close()
            conn.rollback()  # [FIX] 清理 SELECT 开启的事务
        
        # 清理测试索引
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
                conn.commit()
            finally:
                cursor.close()
    
    def test_rebuild_with_invalid_params(self):
        """测试无效参数"""
        # 缺少必要参数
        with self.assertRaises(ValueError):
            self.client.indices.rebuild_index(
                index_name="",
                table_name="test_table",
                column_name="col"
            )
        
        with self.assertRaises(ValueError):
            self.client.indices.rebuild_index(
                index_name="idx",
                table_name="",
                column_name="col"
            )
        
        with self.assertRaises(ValueError):
            self.client.indices.rebuild_index(
                index_name="idx",
                table_name="test_table",
                column_name=""
            )
    
    def test_rebuild_nonexistent_index(self):
        """测试重建不存在的索引（应该成功创建）"""
        index_name = "idx_nonexistent"
        table_name = "test_rebuild_table"
        column_name = "email"
        
        # 确保索引不存在
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
                conn.commit()
            finally:
                cursor.close()
        
        # 重建（实际上是创建）
        result = self.client.indices.rebuild_index(
            index_name=index_name,
            table_name=table_name,
            column_name=column_name,
            index_type="btree"
        )
        
        # 验证结果
        self.assertTrue(result['acknowledged'])
        
        # 验证索引已创建
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT indexname FROM pg_indexes 
                    WHERE tablename = %s AND indexname = %s
                """, (table_name, index_name))
                result = cursor.fetchone()
                self.assertIsNotNone(result, "索引应该被创建")
            finally:
                cursor.close()
        
        # 清理
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
                conn.commit()
            finally:
                cursor.close()
    
    def test_rebuild_with_auto_detect(self):
        """测试自动检测索引类型"""
        index_name = "idx_test_name_btree"
        table_name = "test_rebuild_table"
        column_name = "name"
        
        # 先创建一个 B-tree 索引
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"CREATE INDEX {index_name} ON {table_name} USING btree ({column_name})")
                conn.commit()
            finally:
                cursor.close()
        
        # 验证原索引是 B-tree 类型
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT am.amname 
                    FROM pg_index i
                    JOIN pg_class c ON i.indexrelid = c.oid
                    JOIN pg_am am ON c.relam = am.oid
                    WHERE c.relname = %s
                """, (index_name,))
                result = cursor.fetchone()
                self.assertEqual(result[0], 'btree', "原索引应该是 B-tree 类型")
            finally:
                cursor.close()
        
        # 重建索引（不指定类型，应该自动检测为 btree）
        result = self.client.indices.rebuild_index(
            index_name=index_name,
            table_name=table_name,
            column_name=column_name
            # 不指定 index_type，使用默认值 btree
        )
        
        # 验证结果
        self.assertTrue(result['acknowledged'])
        self.assertEqual(result['type'], 'btree', "应该使用检测到的 B-tree 类型")
        self.assertEqual(result['original_type'], 'btree')
        self.assertTrue(result['auto_detected'])
        self.assertIsNotNone(result['original_definition'])
        
        # 验证索引仍然是 B-tree 类型
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT am.amname 
                    FROM pg_index i
                    JOIN pg_class c ON i.indexrelid = c.oid
                    JOIN pg_am am ON c.relam = am.oid
                    WHERE c.relname = %s
                """, (index_name,))
                result = cursor.fetchone()
                self.assertEqual(result[0], 'btree', "重建后索引应该仍是 B-tree 类型")
            finally:
                cursor.close()
        
        # 清理
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
                conn.commit()
            finally:
                cursor.close()


if __name__ == '__main__':
    unittest.main()
