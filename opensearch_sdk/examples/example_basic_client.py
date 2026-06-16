# BasicClient 使用示例
# 展示如何使用极简客户端进行纯 SQL 数据库操作
# 
# BasicClient 定位：
# - 仅提供连接管理 (connect/close)
# - 仅提供 SQL 执行 (execute)
# - 仅提供事务控制 (commit/rollback)
# - 不提供任何业务封装（表、索引、CRUD、搜索等需自己写 SQL）

import numpy as np
from utils import load_config
from opensearch_sdk import BasicClient

# 加载数据库配置
config = load_config()
config['dbname'] = config.pop('database')

def example_basic_usage():
    """基础使用示例 - 展示纯 SQL 操作"""
    print("=== BasicClient 基础使用示例（纯 SQL）===\n")
    
    # 创建客户端（自动建立连接）
    client = BasicClient(**config)
    
    try:
        # 0. 清理旧表（避免重复）
        print("0. 清理旧表...")
        client.execute("DROP TABLE IF EXISTS my_vectors")
        client.commit()
        print("   已清理旧表\n")
        
        # 1. 创建表（手写 SQL）
        print("1. 创建表...")
        client.execute("""
            CREATE TABLE IF NOT EXISTS my_vectors (
                id BIGINT PRIMARY KEY,
                embedding vector(768)
            )
        """)
        client.commit()
        print("   创建表成功\n")
        
        # 2. 创建 HNSW 索引（手写 SQL）
        print("2. 创建 HNSW 索引...")
        client.execute("""
            CREATE INDEX IF NOT EXISTS idx_hnsw_cosine ON my_vectors
            USING hnsw (embedding vector_cosine_ops)
            WITH (m=16, ef_construction=64)
        """)
        client.commit()
        print("   创建索引成功\n")
        
        # 3. 准备测试数据（批量插入）
        print("3. 批量插入数据...")
        num_vectors = 10
        dim = 768
        embeddings = [np.random.random(dim).tolist() for _ in range(num_vectors)]
        ids = list(range(1, num_vectors + 1))
        
        # 使用 execute_values 批量插入（需要导入）
        from psycopg2.extras import execute_values
        # 将向量列表转换为字符串格式
        values = [(doc_id, '[' + ','.join(map(str, emb)) + ']') for doc_id, emb in zip(ids, embeddings)]
        
        # 获取 cursor 并使用 execute_values
        cursor = client.conn.cursor()
        execute_values(
            cursor,
            "INSERT INTO my_vectors (id, embedding) VALUES %s",
            values
        )
        client.commit()
        print(f"   插入 {num_vectors} 条记录\n")
        
        # 4. 单个向量搜索（手写 SQL）
        print("4. 单个向量搜索...")
        query_vector = np.random.random(dim).tolist()
        query_str = '[' + ','.join(map(str, query_vector)) + ']'
        cursor = client.execute("""
            SELECT id
            FROM my_vectors
            ORDER BY embedding <=> %s::vector
            LIMIT 5
        """, (query_str,))
        results = [row[0] for row in cursor.fetchall()]
        print(f"   搜索结果 (ID): {results}\n")
        
        # 5. 带距离的搜索
        print("5. 带距离的搜索...")
        cursor = client.execute("""
            SELECT id, embedding <=> %s::vector AS distance
            FROM my_vectors
            ORDER BY embedding <=> %s::vector
            LIMIT 5
        """, (query_str, query_str))
        results_with_distance = [(row[0], row[1]) for row in cursor.fetchall()]
        print(f"   搜索结果 (ID, 距离): {results_with_distance}\n")
        
        # 6. 批量搜索（循环执行）
        print("6. 批量向量搜索...")
        query_vectors = [np.random.random(dim).tolist() for _ in range(3)]
        all_results = []
        for qv in query_vectors:
            qv_str = '[' + ','.join(map(str, qv)) + ']'
            cursor = client.execute("""
                SELECT id
                FROM my_vectors
                ORDER BY embedding <=> %s::vector
                LIMIT 3
            """, (qv_str,))
            results = [row[0] for row in cursor.fetchall()]
            all_results.append(results)
        
        for i, results in enumerate(all_results):
            print(f"   查询 {i+1} 结果：{results}")
        print()
        
        # 7. 更新向量（手写 SQL）
        print("7. 更新向量...")
        new_embedding = np.random.random(dim).tolist()
        new_emb_str = '[' + ','.join(map(str, new_embedding)) + ']'
        client.execute(
            "UPDATE my_vectors SET embedding = %s WHERE id = %s",
            (new_emb_str, 1)
        )
        client.commit()
        print("   更新成功\n")
        
        # 8. 删除记录（手写 SQL）
        print("8. 批量删除记录...")
        client.execute(
            "DELETE FROM my_vectors WHERE id IN (%s, %s, %s)",
            (1, 2, 3)
        )
        client.commit()
        deleted_count = 3  # 实际可以获取 rowcount
        print(f"   删除 {deleted_count} 条记录\n")
        
        # 9. 删除表（手写 SQL）
        print("9. 删除表...")
        client.execute("DROP TABLE IF EXISTS my_vectors")
        client.commit()
        print("   删除表成功\n")
        
    finally:
        # 关闭连接
        client.close()
        print("数据库连接已关闭")


def example_context_manager():
    """使用上下文管理器 - 自动管理连接"""
    print("\n=== 使用上下文管理器 ===\n")
    
    with BasicClient(**config) as client:
        # 在上下文中执行操作
        print("在上下文中创建临时表...")
        client.execute("""
            CREATE TEMPORARY TABLE temp_table (
                id BIGINT PRIMARY KEY,
                data TEXT
            )
        """)
        client.commit()
        print("创建临时表成功")
        
        # 退出上下文时自动关闭连接
        print("退出上下文，自动关闭连接")


def example_different_metrics():
    """不同相似度算法示例 - 手写 SQL 对比"""
    print("\n=== 不同相似度算法对比 ===\n")
    
    client = BasicClient(**config)
    
    try:
        # 清理旧表
        client.execute("DROP TABLE IF EXISTS metric_test")
        client.commit()
        
        # 创建表
        client.execute("""
            CREATE TABLE metric_test (
                id BIGINT PRIMARY KEY,
                embedding vector(3)
            )
        """)
        client.commit()
        
        # 插入简单数据
        embeddings = [
            [1.0, 0.0, 0.0],  # ID 1: x 轴
            [0.0, 1.0, 0.0],  # ID 2: y 轴
            [0.0, 0.0, 1.0],  # ID 3: z 轴
            [1.0, 1.0, 0.0],  # ID 4: xy 平面
        ]
        ids = [1, 2, 3, 4]
        
        # 使用 BasicClient 的 execute 方法执行 SQL
        for id_, emb in zip(ids, embeddings):
            # 将向量转换为字符串格式
            emb_str = '[' + ','.join(map(str, emb)) + ']'
            client.execute(
                "INSERT INTO metric_test (id, embedding) VALUES (%s, %s::vector)",
                (id_, emb_str)
            )
        client.commit()
        
        # 查询向量 (沿 x 轴)
        query = [1.0, 0.0, 0.0]
        
        # L2 距离 (<->)
        print("L2 距离 (<->) 搜索结果:")
        cursor = client.execute("""
            SELECT id, embedding <-> %s::vector AS distance
            FROM metric_test
            ORDER BY embedding <-> %s::vector
        """, (query, query))
        l2_results = cursor.fetchall()
        for id_, dist in l2_results:
            print(f"  ID {id_}: 距离={dist:.4f}")
        
        # 余弦相似度 (<=>)
        print("\n余弦相似度 (<=>) 搜索结果:")
        cursor = client.execute("""
            SELECT id, embedding <=> %s::vector AS distance
            FROM metric_test
            ORDER BY embedding <=> %s::vector
        """, (query, query))
        cosine_results = cursor.fetchall()
        for id_, dist in cosine_results:
            print(f"  ID {id_}: 距离={dist:.4f}")
        
        # 内积 (<#>)
        print("\n内积 (<#>) 搜索结果:")
        cursor = client.execute("""
            SELECT id, embedding <#> %s::vector AS distance
            FROM metric_test
            ORDER BY embedding <#> %s::vector
        """, (query, query))
        ip_results = cursor.fetchall()
        for id_, dist in ip_results:
            print(f"  ID {id_}: 距离={dist:.4f}")
        
        # 清理
        client.execute("DROP TABLE IF EXISTS metric_test")
        client.commit()
        
    finally:
        client.close()


def example_error_handling():
    """错误处理示例 - 展示事务回滚"""
    print("\n=== 错误处理与事务控制 ===\n")
    
    client = BasicClient(**config)
    
    try:
        # 尝试查询不存在的表
        print("查询不存在的表...")
        try:
            cursor = client.execute("SELECT * FROM non_existent_table")
            results = cursor.fetchall()
            print(f"结果：{results}")
        except Exception as e:
            print(f"捕获异常（预期）: {type(e).__name__}")
            print(f"错误信息：{str(e)[:100]}...")
            # 回滚失败的事务
            client.rollback()
        
        # 事务回滚示例
        print("\n事务回滚示例...")
        client.execute("CREATE TABLE IF NOT EXISTS test_txn (id BIGINT PRIMARY KEY, data TEXT)")
        client.commit()
        
        try:
            # 插入一些数据
            client.execute(
                "INSERT INTO test_txn (id, data) VALUES (%s, %s)",
                (1, 'test_data')
            )
            # 故意制造一个错误（维度不匹配）
            client.execute(
                "INSERT INTO test_txn (id, data) VALUES (%s, %s)",
                (2,)  # 缺少参数，会失败
            )
            client.commit()  # 不会执行到这里
        except Exception as e:
            print(f"插入失败，执行回滚：{type(e).__name__}")
            client.rollback()  # 回滚所有更改
            print("回滚成功")
        
        # 清理
        client.execute("DROP TABLE IF EXISTS test_txn")
        client.commit()
        
        print("\n错误处理演示完成")
        
    finally:
        client.close()


if __name__ == "__main__":
    # 运行所有示例
    example_basic_usage()
    example_context_manager()
    example_different_metrics()
    example_error_handling()
    
    print("\n=== 所有示例完成 ===")
