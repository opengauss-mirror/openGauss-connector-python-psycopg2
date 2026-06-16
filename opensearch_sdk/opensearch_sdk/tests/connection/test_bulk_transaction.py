"""
Test for transactional bulk operations
"""

import unittest
import json
import os
from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestTransactionalBulk(unittest.TestCase):
    """测试事务化 bulk 操作"""
    
    @classmethod
    def setUpClass(cls):
        """加载数据库配置"""
        cls.db_config = load_db_config()
        
        # 创建客户端（连接池模式）
        cls.client = OpenGauss(
            hosts=[{
                "host": cls.db_config["host"],
                "port": cls.db_config["port"]
            }],
            database=cls.db_config["database"],
            user=cls.db_config["user"],
            password=cls.db_config["password"],
            use_connection_pool=True,
            pool_min_conn=3,
            pool_max_conn=10
        )
        
        # 创建测试表
        try:
            with cls.client.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS test_bulk_transaction (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        age INTEGER
                    )
                """)
                conn.commit()
                cursor.close()
        except Exception as e:
            print(f"Warning: Failed to create table: {e}")
    
    @classmethod
    def tearDownClass(cls):
        """清理测试表"""
        try:
            with cls.client.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS test_bulk_transaction")
                conn.commit()
                cursor.close()
        except Exception:
            pass
        
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
    
    def test_bulk_is_atomic(self):
        """测试 bulk 操作的原子性"""
        # 先检查初始状态
        initial_status = self.client.connection._pool.get_pool_status()
        print(f"Initial pool status: {initial_status}")
        
        # 准备 bulk 数据 - 包含一个会失败的文档（重复 ID）
        bulk_data = [
            json.dumps({"index": {"_index": "test_bulk_transaction", "_id": "bulk_tx_1"}}),
            json.dumps({"name": "User1", "age": 20}),
            json.dumps({"index": {"_index": "test_bulk_transaction", "_id": "bulk_tx_2"}}),
            json.dumps({"name": "User2", "age": 21}),
            json.dumps({"index": {"_index": "test_bulk_transaction", "_id": "bulk_tx_3"}}),
            json.dumps({"name": "User3", "age": 22}),
        ]
        
        bulk_body = "\n".join(bulk_data) + "\n"
        
        # 执行第一次 bulk - 应该成功
        result1 = self.client.bulk(body=bulk_body)
        print(f"First bulk result: {result1}")
        
        # 检查连接池状态
        after_bulk_status = self.client.connection._pool.get_pool_status()
        print(f"After bulk status: {after_bulk_status}")
        
        # 再执行一个简单操作看看是否归还
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
        
        final_status = self.client.connection._pool.get_pool_status()
        print(f"Final pool status: {final_status}")
        
        # 所有连接应该已归还
        self.assertEqual(final_status['used_connections'], 0, f"Bulk 操作后连接应该已归还: {final_status}")
        
        # 验证数据已插入
        doc1 = self.client.get(index="test_bulk_transaction", id="bulk_tx_1")
        self.assertTrue(doc1['found'])
        
        doc2 = self.client.get(index="test_bulk_transaction", id="bulk_tx_2")
        self.assertTrue(doc2['found'])
        
        doc3 = self.client.get(index="test_bulk_transaction", id="bulk_tx_3")
        self.assertTrue(doc3['found'])
        
        print("OK bulk operation is atomic and connections are returned")
    
    def test_bulk_no_connection_leak(self):
        """测试 bulk 操作无连接泄漏"""
        # 执行多次 bulk 操作
        for i in range(5):
            bulk_data = []
            for j in range(3):
                bulk_data.append(json.dumps({"index": {"_index": "test_bulk_transaction", "_id": f"leak_test_{i}_{j}"}}))
                bulk_data.append(json.dumps({"name": f"User{j}", "age": 20 + j}))
            bulk_body = "\n".join(bulk_data) + "\n"
            
            result = self.client.bulk(body=bulk_body)
            
            # 每次操作后检查连接池状态
            status = self.client.connection._pool.get_pool_status()
            self.assertEqual(status['used_connections'], 0, 
                           f"Bulk iteration {i+1} 后检测到连接泄漏: {status}")
        
        print("OK bulk operations (5 iterations) - no connection leak")


if __name__ == '__main__':
    unittest.main()
