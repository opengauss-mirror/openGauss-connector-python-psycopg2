"""
Test connection pool functionality
"""

import unittest
import json
import os
import threading
import time
from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestConnectionPool(unittest.TestCase):
    """测试连接池功能"""
    
    @classmethod
    def setUpClass(cls):
        """加载数据库配置"""
        cls.db_config = load_db_config()
    
    def test_connection_pool_creation(self):
        """测试连接池创建"""
        client = OpenGauss(
            hosts=[{
                "host": self.db_config["host"],
                "port": self.db_config["port"]
            }],
            database=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            use_connection_pool=True,
            pool_min_conn=3,
            pool_max_conn=10
        )
        
        # 检查连接池是否初始化
        self.assertIsNotNone(client.connection._pool)
        self.assertTrue(client.connection.use_connection_pool)
        
        # 获取连接池状态
        status = client.connection._pool.get_pool_status()
        print(f"Connection pool status: {status}")
        
        self.assertEqual(status['status'], 'active')
        self.assertEqual(status['min_conn'], 3)
        self.assertEqual(status['max_conn'], 10)
        
        client.close()
        print("OK Connection pool created and closed successfully")
    
    def test_single_connection_mode(self):
        """测试单连接模式"""
        client = OpenGauss(
            hosts=[{
                "host": self.db_config["host"],
                "port": self.db_config["port"]
            }],
            database=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            use_connection_pool=False
        )
        
        # 检查是否使用单连接模式
        self.assertFalse(client.connection.use_connection_pool)
        self.assertIsNone(client.connection._pool)
        
        # 执行查询
        with client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
        
        self.assertEqual(result[0], 1)
        
        client.close()
        print("OK Single connection mode works")
    
    def test_concurrent_queries_with_pool(self):
        """测试并发查询（连接池模式）"""
        client = OpenGauss(
            hosts=[{
                "host": self.db_config["host"],
                "port": self.db_config["port"]
            }],
            database=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            use_connection_pool=True,
            pool_min_conn=10,  # 增加最小连接数
            pool_max_conn=30   # 增加最大连接数
        )
        
        results = []
        errors = []
        
        def query_worker(worker_id):
            try:
                for i in range(5):
                    # 使用上下文管理器确保连接正确归还
                    with client.connection._pool.get_connection_context() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT %s", (worker_id * 10 + i,))
                        result = cursor.fetchone()
                        cursor.close()
                        results.append((worker_id, i, result[0]))
                        time.sleep(0.01)  # 模拟工作负载
            except Exception as e:
                errors.append((worker_id, str(e)))
        
        # 启动 10 个并发线程
        threads = []
        for i in range(10):
            t = threading.Thread(target=query_worker, args=(i,))
            threads.append(t)
            t.start()
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        # 检查结果
        print(f"Total queries executed: {len(results)}")
        print(f"Errors: {len(errors)}")
        
        self.assertEqual(len(results), 50)  # 10 threads * 5 queries
        self.assertEqual(len(errors), 0)
        
        # 检查连接池状态
        status = client.connection._pool.get_pool_status()
        print(f"Final pool status: {status}")
        
        client.close()
        print("OK Concurrent queries with connection pool succeeded")
    
    def test_connection_pool_auto_reconnect(self):
        """测试连接池自动重连"""
        client = OpenGauss(
            hosts=[{
                "host": self.db_config["host"],
                "port": self.db_config["port"]
            }],
            database=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            use_connection_pool=True,
            pool_min_conn=2,
            pool_max_conn=5
        )
        
        # 执行一些查询
        for i in range(5):
            with client.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT %s", (i,))
                result = cursor.fetchone()
                cursor.close()
            self.assertEqual(result[0], i)
        
        print("OK Connection pool auto-reconnect test passed")
        
        client.close()
    
    def test_pool_parameters_passed_correctly(self):
        """测试连接池参数正确传递"""
        client = OpenGauss(
            hosts=[{
                "host": self.db_config["host"],
                "port": self.db_config["port"]
            }],
            database=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            use_connection_pool=True,
            pool_min_conn=8,
            pool_max_conn=15
        )
        
        # 验证参数
        self.assertEqual(client.connection._pool.min_conn, 8)
        self.assertEqual(client.connection._pool.max_conn, 15)
        
        status = client.connection._pool.get_pool_status()
        self.assertEqual(status['min_conn'], 8)
        self.assertEqual(status['max_conn'], 15)
        
        client.close()
        print("OK Pool parameters passed correctly")


if __name__ == '__main__':
    unittest.main()
