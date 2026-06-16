#!/usr/bin/env python
# -*-coding: utf-8 -*-
"""
文档操作测试 - 创建和更新操作

功能说明：
- 测试 create() 方法的功能
- 测试 update() 方法的功能
- 验证创建和更新操作的正确性

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.document_ops.test_create_update -v
    python opensearch_sdk/tests/document_ops/test_create_update.py
"""
import json
import os
import sys
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

# 加载数据库配置
DB_CONFIG = load_db_config()


class TestCreateAndUpdate(unittest.TestCase):
    """测试 create() 和 update() 方法"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = OpenGauss(
            hosts=[{'host': DB_CONFIG['host'], 'port': DB_CONFIG['port']}],
            database=DB_CONFIG['database'],
            user=DB_CONFIG['user'],
            password=DB_CONFIG['password']
        )
        cls.test_index = "test_create_update"
        cls.test_id = "1"
        
        # [OK] 先删除可能存在的索引，避免冲突
        try:
            if cls.client.indices.exists(index=cls.test_index):
                cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
        
        # 创建索引
        mapping = {
            "mappings": {
                "properties": {
                    "field1": {"type": "keyword"},
                    "field2": {"type": "text"}
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            if cls.client.indices.exists(index=cls.test_index):
                cls.client.indices.delete(index=cls.test_index)
        except Exception as e:
            print(f"[WARN] Failed to delete index: {e}")
        finally:
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
            try:
                cls.client.close()
            except Exception as e:
                print(f"[WARN] Failed to close client: {e}")
            
            # [PASS] 最后再断言，即使失败也不影响资源清理
            if leak_detected:
                raise AssertionError(leak_message)
    
    def test_create_new_document(self):
        """测试 create() 方法 - 创建新文档"""
        print(f"\n[DEBUG] test_create_new_document 开始执行")
        print(f"[DEBUG] 使用索引：{self.test_index}, ID: {self.test_id}")
        
        # 检查索引是否存在
        index_exists = self.client.indices.exists(index=self.test_index)
        print(f"[DEBUG] 索引存在：{index_exists}")
        
        if not index_exists:
            print(f"[DEBUG] 索引不存在，正在创建...")
            mapping = {
                "mappings": {
                    "properties": {
                        "field1": {"type": "keyword"},
                        "field2": {"type": "text"}
                    }
                }
            }
            self.client.indices.create(index=self.test_index, body=mapping)
            print(f"[DEBUG] 索引创建成功")
        
        # 检查文档是否已存在（可能是之前测试的残留）
        try:
            existing_doc = self.client.get(index=self.test_index, id=self.test_id)
            print(f"[DEBUG] 警告：文档已存在！{existing_doc}")
            print(f"[DEBUG] 删除已存在的文档...")
            self.client.delete(index=self.test_index, id=self.test_id)
            print(f"[DEBUG] 文档已删除")
        except Exception as e:
            print(f"[DEBUG] 文档不存在（正常）：{e}")
        
        doc_data = {"field1": "value1", "field2": "value2"}
        print(f"[DEBUG] 开始创建文档...")
        result = self.client.create(index=self.test_index, id=self.test_id, body=doc_data)
        print(f"[DEBUG] 创建结果：{result}")
        self.assertIsNotNone(result)
        print(f"[DEBUG] test_create_new_document 通过")
    
    def test_create_existing_document_should_fail(self):
        """测试 create() 方法 - 创建已存在的文档（应该失败）"""
        # 首先确保文档已存在
        try:
            self.client.create(index=self.test_index, id=self.test_id, body={"field1": "original"})
            print("\n[DEBUG] 第一次 create() 成功")
        except Exception as e:
            print(f"\n[DEBUG] 第一次 create() 失败：{e}")
            raise
        
        # 尝试再次创建，应该抛出异常
        try:
            self.client.create(index=self.test_index, id=self.test_id, body={"field1": "new_value"})
            print("[DEBUG] 第二次 create() 没有抛出异常 - 这是 FAIL 的原因！")
            # 如果没有抛出异常，测试失败
            self.fail("create() 方法在创建已存在文档时应该抛出异常，但实际没有抛出")
        except Exception as e:
            error_msg = str(e)
            print(f"[DEBUG] 第二次 create() 抛出异常：{error_msg}")
            # 验证异常消息是否包含预期内容
            self.assertTrue("409 Conflict" in error_msg or "already exists" in error_msg or "409" in error_msg,
                          f"异常消息不符合预期：{error_msg}")
    
    def test_update_existing_document(self):
        """测试 update() 方法 - 更新已存在的文档"""
        new_data = {"field1": "updated_value1", "field2": "updated_value2"}
        result = self.client.update(index=self.test_index, id=self.test_id, body=new_data)
        self.assertIsNotNone(result)
        
        # 验证更新后的数据
        retrieved = self.client.get(index=self.test_index, id=self.test_id)
        self.assertEqual(retrieved['_source']['field1'], "updated_value1")
    
    def test_update_nonexistent_document_should_fail(self):
        """测试 update() 方法 - 更新不存在的文档（应该失败）"""
        non_existent_id = "999"
        with self.assertRaises(Exception) as context:
            self.client.update(index=self.test_index, id=non_existent_id, body={"field1": "value"})
        
        error_msg = str(context.exception)
        self.assertTrue("404 Not Found" in error_msg or "not found" in error_msg)
    
    def test_index_upsert_semantic(self):
        """测试 index() 方法 - UPSERT 语义"""
        # 创建新文档
        result = self.client.index(index=self.test_index, id="2", body={"field1": "new_doc_value1"})
        self.assertIsNotNone(result)
        
        # 更新已存在的文档
        result = self.client.index(index=self.test_index, id="2", body={"field1": "updated_new_doc_value1"})
        self.assertIsNotNone(result)
        
        # 验证
        retrieved = self.client.get(index=self.test_index, id="2")
        self.assertEqual(retrieved['_source']['field1'], "updated_new_doc_value1")
    
    def test_performance_batch_insert(self):
        """性能对比测试 - 移除 exists 检查后的性能提升"""
        import time
        
        # 测试 100 次写入
        start_time = time.time()
        for i in range(100, 200):
            self.client.index(index=self.test_index, id=str(i), body={"field1": f"value_{i}"})
        elapsed_time = time.time() - start_time
        
        print(f"\n[OK] 完成 100 次写入，耗时：{elapsed_time:.3f}秒")
        print(f"[OK] 平均每次写入：{elapsed_time/100*1000:.2f}毫秒")


if __name__ == "__main__":
    unittest.main(verbosity=2)
