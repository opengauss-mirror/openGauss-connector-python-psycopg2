#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试分布式表创建功能
"""

import unittest
import json
from pathlib import Path
from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestDistributedTableCreation(unittest.TestCase):
    """测试分布式表创建功能"""
    
    @classmethod
    def setUpClass(cls):
        """初始化客户端并检查分布式环境"""
        config = load_db_config()
        
        cls.client = OpenGauss(
            hosts=[{'host': config['host'], 'port': config['port']}],
            database=config['database'],
            user=config['user'],
            password=config['password']
        )
        
        # 检查是否为分布式环境
        cls.is_distributed = cls._check_distributed_environment()
        if not cls.is_distributed:
            print("\n[WARN]  WARNING: SPQ distributed cluster is not configured.")
            print("   Distributed table tests will be skipped.")
            print("   To enable: CREATE EXTENSION spq; and configure nodes.\n")
    
    @classmethod
    def _check_spq_extension(cls, conn):
        """
        检查 spq 扩展和活跃节点

        :arg conn: 数据库连接
        :return: True 如果是分布式环境，False 否则
        """
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT extname FROM pg_extension WHERE extname = 'spq'"
            )
            if not cursor.fetchone():
                print("[INFO] SPQ extension not installed")
                return False

            cursor.execute(
                "SELECT COUNT(*) FROM spq_get_active_worker_nodes()"
            )
            count = cursor.fetchone()[0]
            if count == 0:
                print("[INFO] No active worker nodes found")
                return False

            print(f"[INFO] Distributed environment detected ({count} active nodes)")
            return True

    @classmethod
    def _check_distributed_environment(cls):
        """
        检查是否为 SPQ 分布式环境
        
        :return: True 如果是分布式环境，False 否则
        """
        try:
            with cls.client.connection.get_connection_for_operation() as conn:
                return cls._check_spq_extension(conn)
        except Exception as e:
            print(f"[INFO] Failed to check distributed environment: {e}")
            return False
    
    @classmethod
    def tearDownClass(cls):
        """关闭客户端"""
        if hasattr(cls, 'client'):
            cls.client.close()
    
    def tearDown(self):
        """清理测试索引"""
        test_indexes = [
            'test_distributed_table',
            'test_normal_table',
            'test_distributed_custom',
            'test_backward_compat'
        ]
        for idx in test_indexes:
            try:
                self.client.indices.delete(index=idx)
            except:
                pass
    
    def test_01_create_normal_table(self):
        """测试创建普通表（默认行为）"""
        if not self.is_distributed:
            self.skipTest("SPQ distributed cluster is not configured")
        
        result = self.client.indices.create(
            index="test_normal_table",
            body={
                "mappings": {
                    "properties": {
                        "title": {"type": "text"},
                        "embedding": {"type": "float_vector", "dimension": 4}
                    }
                }
            }
        )
        
        self.assertTrue(result.get('acknowledged'))
        print("[OK] 普通表创建成功")
    
    def test_02_create_distributed_table_default(self):
        """测试创建分布式表（使用默认参数）"""
        if not self.is_distributed:
            self.skipTest("SPQ distributed cluster is not configured")
        
        result = self.client.indices.create(
            index="test_distributed_table",
            body={
                "mappings": {
                    "properties": {
                        "title": {"type": "text"},
                        "embedding": {"type": "float_vector", "dimension": 4}
                    }
                }
            },
            distributed=True
        )
        
        self.assertTrue(result.get('acknowledged'))
        
        # 验证是否为分布式表
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT logicalrelid FROM pg_dist_partition WHERE logicalrelid = %s::regclass",
                    ('test_distributed_table',)
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        
        self.assertIsNotNone(row, "表应该是分布式表")
        print("[OK] 分布式表创建成功（默认分布列: id, 分片数: 6）")
    
    def test_03_create_distributed_table_custom(self):
        """测试创建分布式表（自定义参数）"""
        if not self.is_distributed:
            self.skipTest("SPQ distributed cluster is not configured")
        
        result = self.client.indices.create(
            index="test_distributed_custom",
            body={
                "mappings": {
                    "properties": {
                        "title": {"type": "text"},
                        "embedding": {"type": "float_vector", "dimension": 4}
                    }
                }
            },
            distributed=True,
            distribution_column="id",
            shard_count=4
        )
        
        self.assertTrue(result.get('acknowledged'))
        
        # 验证是否为分布式表
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT logicalrelid FROM pg_dist_partition WHERE logicalrelid = %s::regclass",
                    ('test_distributed_custom',)
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        
        self.assertIsNotNone(row, "表应该是分布式表")
        print(f"[OK] 分布式表创建成功（分布列: id, 分片数: 4）")
    
    def test_04_backward_compatibility(self):
        """测试向后兼容性（不传新参数）"""
        if not self.is_distributed:
            self.skipTest("SPQ distributed cluster is not configured")
        
        # 不应该影响现有代码
        result = self.client.indices.create(
            index="test_backward_compat",
            body={
                "mappings": {
                    "properties": {
                        "title": {"type": "text"}
                    }
                }
            }
        )
        
        self.assertTrue(result.get('acknowledged'))
        
        # 验证不是分布式表
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT logicalrelid FROM pg_dist_partition WHERE logicalrelid = %s::regclass",
                    ('test_backward_compat',)
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        
        self.assertIsNone(row, "表应该是普通表")
        print("[OK] 向后兼容性验证通过")
    
    def _drop_test_table(self, table_name):
        """清理测试表"""
        try:
            with self.client.connection.get_connection_for_operation() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                    conn.commit()
        except Exception:
            pass

    def test_05_pure_sql_distributed_table(self):
        """测试纯 SQL 创建分布式表（验证底层功能）"""
        if not self.is_distributed:
            self.skipTest("SPQ distributed cluster is not configured")
        
        import time
        table_name = f"test_sql_dist_{int(time.time() * 1000)}"
        
        try:
            # [FIX] 使用新的连接管理模式
            with self.client.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                try:
                    # 步骤 1：创建普通表
                    cursor.execute(f"""
                        CREATE TABLE {table_name} (
                            id BIGINT PRIMARY KEY,
                            title TEXT,
                            value INTEGER
                        )
                    """)
                    conn.commit()
                    
                    # 验证是普通表
                    cursor.execute(
                        "SELECT logicalrelid FROM pg_dist_partition WHERE logicalrelid = %s::regclass",
                        (table_name,)
                    )
                    row = cursor.fetchone()
                    self.assertIsNone(row, "初始状态应该是普通表")
                    
                    # 步骤 2：转换为分布式表
                    cursor.execute(
                        "SELECT create_distributed_table(%s, %s, shard_count:=%s)",
                        (table_name, 'id', 4)
                    )
                    conn.commit()
                    
                    # 验证是分布式表
                    cursor.execute(
                        "SELECT logicalrelid FROM pg_dist_partition WHERE logicalrelid = %s::regclass",
                        (table_name,)
                    )
                    row = cursor.fetchone()
                    
                    self.assertIsNotNone(row, "转换后应该是分布式表")
                    
                    # 步骤 3：验证分片数量
                    cursor.execute(
                        "SELECT COUNT(*) FROM pg_dist_shard WHERE logicalrelid = %s::regclass",
                        (table_name,)
                    )
                    shard_count = cursor.fetchone()[0]
                    
                    self.assertEqual(shard_count, 4, f"应该有 4 个分片，实际有 {shard_count} 个")
                    
                    # 步骤 4：插入数据并验证路由
                    cursor.execute(
                        f"INSERT INTO {table_name} (id, title, value) VALUES (%s, %s, %s)",
                        (1, 'Test Title 1', 100)
                    )
                    cursor.execute(
                        f"INSERT INTO {table_name} (id, title, value) VALUES (%s, %s, %s)",
                        (2, 'Test Title 2', 200)
                    )
                    conn.commit()
                    
                    # 验证数据可查询
                    cursor.execute(
                        f"SELECT COUNT(*) FROM {table_name}"
                    )
                    count = cursor.fetchone()[0]
                    
                    self.assertEqual(count, 2, "应该能查询到插入的数据")
                    
                    # 步骤 5：验证分片分布
                    cursor.execute("""
                        SELECT s.shardid, p.nodename, p.nodeport
                        FROM pg_dist_shard s
                        JOIN pg_dist_shard_placement p ON s.shardid = p.shardid
                        WHERE s.logicalrelid = %s::regclass
                        ORDER BY s.shardid
                    """, (table_name,))
                    shards = cursor.fetchall()
                    
                    self.assertEqual(len(shards), 4, "应该有 4 个分片记录")
                    
                    print(f"[OK] 纯 SQL 分布式表测试通过（分片数: {len(shards)}）")
                finally:
                    cursor.close()
            
        finally:
            self._drop_test_table(table_name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
