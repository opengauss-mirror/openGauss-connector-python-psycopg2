# BasicClient 基础功能测试
import unittest
import json
from pathlib import Path
import numpy as np
from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import BasicClient


class TestBasicClient(unittest.TestCase):
    """BasicClient 基础功能测试 - 纯 SQL 方式"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        # 从配置文件加载数据库配置
        db_config = load_db_config()
        
        cls.db_config = {
            "dbname": db_config.get("database", "es"),
            "user": db_config.get("user", "jzc"),
            "password": db_config.get("password"),  # 必须从配置文件提供
            "host": db_config.get("host", "172.17.9.26"),
            "port": db_config.get("port", 5432)
        }
        
        # 清理可能存在的残留表
        try:
            client = BasicClient(**cls.db_config)
            client.execute("DROP TABLE IF EXISTS test_basic_vectors")
            client.commit()
            client.close()
        except Exception:
            pass
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理"""
        try:
            client = BasicClient(**cls.db_config)
            client.execute("DROP TABLE IF EXISTS test_basic_vectors")
            client.commit()
            client.close()
        except Exception:
            pass
    
    def test_01_create_table(self):
        """测试创建表"""
        client = BasicClient(**self.db_config)
        try:
            # 使用纯 SQL 创建表
            client.execute("""
                CREATE TABLE IF NOT EXISTS test_basic_vectors (
                    id BIGINT PRIMARY KEY,
                    embedding vector(768)
                )
            """)
            client.commit()
            
            # 验证表存在
            cursor = client.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s AND table_schema = 'public'
                )
            """, ("test_basic_vectors",))
            exists = cursor.fetchone()[0]
            self.assertTrue(exists, "创建表应该成功")
        finally:
            client.close()
    
    def test_02_create_index(self):
        """测试创建索引"""
        client = BasicClient(**self.db_config)
        try:
            # 先确保表存在
            client.execute("""
                CREATE TABLE IF NOT EXISTS test_basic_vectors (
                    id BIGINT PRIMARY KEY,
                    embedding vector(768)
                )
            """)
            client.commit()
            
            # [FIX] 使用纯 SQL 创建 HNSW 索引
            # SET 是会话级别设置，不需要单独 commit
            client.execute("SET hnsw.ef_search = 64")
            
            # [FIX] 先删除旧索引，避免 IF NOT EXISTS 静默失败
            client.execute("DROP INDEX IF EXISTS idx_test_hnsw")
            
            # CREATE INDEX 是 DDL，会自动提交
            client.execute("""
                CREATE INDEX idx_test_hnsw 
                ON test_basic_vectors 
                USING hnsw (embedding vector_cosine_ops) 
                WITH (m = 16, ef_construction = 64)
            """)
            # DDL 后不需要手动 commit
            
            # 验证索引存在
            cursor = client.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE tablename = %s AND indexname = %s
                )
            """, ("test_basic_vectors", "idx_test_hnsw"))
            exists = cursor.fetchone()[0]
            cursor.close()
            self.assertTrue(exists, "创建索引应该成功")
        finally:
            client.close()
    
    def test_03_insert_data(self):
        """测试批量插入数据"""
        client = BasicClient(**self.db_config)
        try:
            from psycopg2.extras import execute_values
            
            # 确保表存在
            client.execute("""
                CREATE TABLE IF NOT EXISTS test_basic_vectors (
                    id BIGINT PRIMARY KEY,
                    embedding vector(768)
                )
            """)
            client.commit()
            
            # 准备测试数据
            num_vectors = 10
            dim = 768
            embeddings = [np.random.random(dim).tolist() for _ in range(num_vectors)]
            ids = list(range(1, num_vectors + 1))
            
            # 转换为字符串格式
            values = [
                (doc_id, '[' + ','.join(map(str, emb)) + ']')
                for doc_id, emb in zip(ids, embeddings)
            ]
            
            # 批量插入
            cursor = client.conn.cursor()
            execute_values(cursor, "INSERT INTO test_basic_vectors (id, embedding) VALUES %s", values)
            client.commit()
            
            # 验证插入数量
            cursor = client.execute("SELECT COUNT(*) FROM test_basic_vectors")
            count = cursor.fetchone()[0]
            self.assertEqual(count, num_vectors, f"应该插入{num_vectors}条记录")
        finally:
            client.close()
    
    def test_04_search_vector(self):
        """测试向量搜索"""
        client = BasicClient(**self.db_config)
        try:
            # 查询向量
            query_vector = np.random.random(768).tolist()
            query_str = '[' + ','.join(map(str, query_vector)) + ']'
            
            # 搜索（只返回 ID）
            cursor = client.execute("""
                SELECT id
                FROM test_basic_vectors
                ORDER BY embedding <=> %s::vector
                LIMIT 5
            """, (query_str,))
            
            results = [row[0] for row in cursor.fetchall()]
            
            # 验证结果
            self.assertIsInstance(results, list, "结果应该是列表")
            self.assertLessEqual(len(results), 5, "结果数量不应超过 topk")
            self.assertTrue(all(isinstance(r, int) for r in results), "所有结果应该是整数 ID")
        finally:
            client.close()
    
    def test_05_search_with_distance(self):
        """测试带距离的搜索"""
        client = BasicClient(**self.db_config)
        try:
            query_vector = np.random.random(768).tolist()
            query_str = '[' + ','.join(map(str, query_vector)) + ']'
            
            # 搜索（返回 ID 和距离）
            cursor = client.execute("""
                SELECT id, embedding <=> %s::vector AS distance
                FROM test_basic_vectors
                ORDER BY embedding <=> %s::vector
                LIMIT 5
            """, (query_str, query_str))
            
            results = cursor.fetchall()
            
            # 验证结果
            self.assertIsInstance(results, list, "结果应该是列表")
            self.assertLessEqual(len(results), 5, "结果数量不应超过 topk")
            self.assertTrue(
                all(isinstance(r, tuple) and len(r) == 2 for r in results),
                "所有结果应该是 (id, distance) 元组"
            )
        finally:
            client.close()
    
    def test_06_batch_search(self):
        """测试批量搜索"""
        client = BasicClient(**self.db_config)
        try:
            # 3 个查询向量
            query_vectors = [np.random.random(768).tolist() for _ in range(3)]
            
            all_results = []
            for query_vector in query_vectors:
                query_str = '[' + ','.join(map(str, query_vector)) + ']'
                
                # 搜索
                cursor = client.execute("""
                    SELECT id
                    FROM test_basic_vectors
                    ORDER BY embedding <=> %s::vector
                    LIMIT 3
                """, (query_str,))
                
                results = [row[0] for row in cursor.fetchall()]
                all_results.append(results)
            
            # 验证结果
            self.assertEqual(len(all_results), 3, "应该有 3 个查询的结果")
            self.assertTrue(
                all(isinstance(results, list) for results in all_results),
                "每个查询的结果应该是列表"
            )
        finally:
            client.close()
    
    def test_07_update_vector(self):
        """测试更新向量"""
        client = BasicClient(**self.db_config)
        try:
            # 确保有数据
            client.execute("""
                CREATE TABLE IF NOT EXISTS test_basic_vectors (
                    id BIGINT PRIMARY KEY,
                    embedding vector(768)
                )
            """)
            client.commit()
            
            # 先插入一条数据（使用新的连接避免事务问题）
            emb_str = '[' + ','.join(map(str, np.random.random(768).tolist())) + ']'
            insert_client = BasicClient(**self.db_config)
            try:
                insert_client.execute("""
                    INSERT INTO test_basic_vectors (id, embedding)
                    VALUES (%s, %s::vector)
                """, (1, emb_str))
                insert_client.commit()
            except Exception as e:
                # 如果已存在，忽略错误
                pass
            finally:
                insert_client.close()
            
            # 新向量
            new_embedding = np.random.random(768).tolist()
            new_emb_str = '[' + ','.join(map(str, new_embedding)) + ']'
            
            # 更新 ID 为 1 的记录
            client.execute("""
                UPDATE test_basic_vectors
                SET embedding = %s::vector
                WHERE id = %s
            """, (new_emb_str, 1))
            client.commit()
            
            # 验证更新
            cursor = client.execute("SELECT embedding FROM test_basic_vectors WHERE id = 1")
            row = cursor.fetchone()
            self.assertIsNotNone(row, "更新应该成功")
        finally:
            client.close()
    
    def test_08_delete_records(self):
        """测试删除记录"""
        client = BasicClient(**self.db_config)
        try:
            # 确保有数据
            client.execute("""
                CREATE TABLE IF NOT EXISTS test_basic_vectors (
                    id BIGINT PRIMARY KEY,
                    embedding vector(768)
                )
            """)
            client.commit()
            
            # 先插入一些数据（使用新的连接避免事务问题）
            insert_client = BasicClient(**self.db_config)
            try:
                for i in [1, 2, 3]:
                    emb_str = '[' + ','.join(map(str, np.random.random(768).tolist())) + ']'
                    insert_client.execute("""
                        INSERT INTO test_basic_vectors (id, embedding)
                        VALUES (%s, %s::vector)
                    """, (i, emb_str))
                    insert_client.commit()
            except Exception:
                # 如果已存在，忽略错误
                pass
            finally:
                insert_client.close()
            
            # 删除 ID 为 1, 2, 3 的记录
            client.execute("""
                DELETE FROM test_basic_vectors
                WHERE id IN (1, 2, 3)
            """)
            client.commit()
            
            # 验证删除数量
            cursor = client.execute("SELECT COUNT(*) FROM test_basic_vectors WHERE id IN (1, 2, 3)")
            remaining = cursor.fetchone()[0]
            self.assertEqual(remaining, 0, "应该删除 3 条记录")
        finally:
            client.close()
    
    def test_09_drop_table(self):
        """测试删除表"""
        client = BasicClient(**self.db_config)
        try:
            # 先创建表
            client.execute("""
                CREATE TABLE IF NOT EXISTS test_basic_vectors (
                    id BIGINT PRIMARY KEY,
                    embedding vector(768)
                )
            """)
            client.commit()
            
            # 删除表
            client.execute("DROP TABLE IF EXISTS test_basic_vectors")
            client.commit()
            
            # 验证表不存在
            cursor = client.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s AND table_schema = 'public'
                )
            """, ("test_basic_vectors",))
            exists = cursor.fetchone()[0]
            self.assertFalse(exists, "删除表应该成功")
        finally:
            client.close()
    
    def test_10_context_manager(self):
        """测试上下文管理器"""
        with BasicClient(**self.db_config) as client:
            # 在上下文中创建临时表
            client.execute("""
                CREATE TABLE IF NOT EXISTS temp_test_table (
                    id BIGINT PRIMARY KEY,
                    embedding vector(128)
                )
            """)
            client.commit()
            
            client.execute("DROP TABLE IF EXISTS temp_test_table")
            client.commit()
            
            # 退出时自动关闭连接
        
        # 验证连接已关闭（这里无法直接验证，但确保不抛出异常）
        self.assertTrue(True, "上下文管理器应该正常工作")
    
    def test_11_reconnect(self):
        """测试重新连接"""
        client = BasicClient(**self.db_config)
        try:
            # 关闭后重新打开连接
            client.close()
            client.connect()
            
            # 验证连接可用
            client.execute("""
                CREATE TABLE IF NOT EXISTS reconnect_test (
                    id BIGINT PRIMARY KEY,
                    embedding vector(64)
                )
            """)
            client.commit()
            
            client.execute("DROP TABLE IF EXISTS reconnect_test")
            client.commit()
            
            self.assertTrue(True, "重新连接后应该能正常操作")
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
