#!/usr/bin/env python
# -*-coding: utf-8 -*-
"""
BasicClient 功能验证示例 - 纯 SQL 方式

用途：演示如何使用 BasicClient 执行原生 SQL 操作
运行方式：python examples/example_basic_client_validation.py
"""
import sys
import numpy as np

from utils import load_config
from opensearch_sdk import BasicClient

def test_basic_client():
    """测试 BasicClient 的基本功能（纯 SQL 方式）"""
    print("=== BasicClient 纯 SQL 操作验证 ===\n")
    
    # 加载数据库配置
    config = load_config()
    print("[OK] 配置文件加载成功")
    config['dbname'] = config.pop('database')

    # 创建客户端
    try:
        client = BasicClient(**config)
        print("[OK] 客户端创建成功")
    except Exception as e:
        print(f"[FAIL] 客户端创建失败：{e}")
        return False
    
    table_name = "test_basic_client"
    
    try:
        # 1. 使用 CREATE TABLE 创建表
        print("\n1. 创建表...")
        client.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id BIGINT PRIMARY KEY,
                embedding vector(128)
            )
        """)
        client.commit()
        print("[OK] 表创建成功")
        
        # 2. 验证表是否存在
        print("\n2. 验证表是否存在...")
        cursor = client.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = %s AND table_schema = 'public'
            )
        """, (table_name,))
        
        exists = cursor.fetchone()[0]
        if exists:
            print(f"[OK] 表 {table_name} 存在")
        else:
            print(f"[FAIL] 表 {table_name} 不存在")
        
        # 3. 创建 HNSW 索引
        print("\n3. 创建 HNSW 索引...")
        client.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_embedding_hnsw
            ON {table_name}
            USING hnsw (embedding vector_cosine_ops)
            WITH (m=16, ef_construction=64)
        """)
        client.commit()
        print("[OK] 索引创建成功")
        
        # 4. 插入测试数据
        print("\n4. 插入测试数据...")
        embeddings = [np.random.random(128).tolist() for _ in range(5)]
        ids = [1, 2, 3, 4, 5]
        
        for doc_id, emb in zip(ids, embeddings):
            # 将列表转换为字符串格式
            emb_str = '[' + ','.join(map(str, emb)) + ']'
            client.execute(f"""
                INSERT INTO {table_name} (id, embedding) 
                VALUES (%s, %s::vector)
            """, (doc_id, emb_str))
        
        client.commit()
        print(f"[OK] 插入 {len(ids)} 条数据")
        
        # 5. 查询数据
        print("\n5. 查询数据...")
        cursor = client.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"[OK] 表中共有 {count} 条数据")
        
        # 6. 向量搜索
        print("\n6. 向量搜索...")
        query = np.random.random(128).tolist()
        query_str = '[' + ','.join(map(str, query)) + ']'
        
        cursor = client.execute(f"""
            SELECT id, embedding <=> %s::vector AS distance
            FROM {table_name}
            ORDER BY embedding <=> %s::vector
            LIMIT 3
        """, (query_str, query_str))
        
        results = cursor.fetchall()
        print(f"[OK] 搜索成功，返回 {len(results)} 个结果")
        for i, (doc_id, distance) in enumerate(results, 1):
            print(f"   {i}. ID={doc_id}, Distance={distance:.4f}")
        
        # 7. 清理
        print("\n7. 清理测试表...")
        client.execute(f"DROP TABLE IF EXISTS {table_name}")
        client.commit()
        print("[OK] 测试表已删除")
        
        print("\n" + "=" * 70)
        print("所有测试通过！BasicClient 工作正常")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n[ERROR] 测试过程中出错：{e}")
        import traceback
        traceback.print_exc()
        client.rollback()
        return False
        
    finally:
        client.close()
        print("\n数据库连接已关闭")

if __name__ == "__main__":
    success = test_basic_client()
    sys.exit(0 if success else 1)
