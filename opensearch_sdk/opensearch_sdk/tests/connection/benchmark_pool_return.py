"""
Benchmark connection pool return overhead
"""

import time
import json
import os
from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.utils.config_loader import load_db_config


def benchmark_return_connection():
    """测试归还连接的开销"""
    
    # 加载配置
    db_config = load_db_config()
    
    # 创建客户端
    client = OpenGauss(
        hosts=[{
            "host": db_config["host"],
            "port": db_config["port"]
        }],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
        use_connection_pool=True,
        pool_min_conn=5,
        pool_max_conn=20
    )
    
    print("=" * 70)
    print("连接池归还操作性能测试")
    print("=" * 70)
    
    # 测试1：单次归还操作的耗时
    print("\n[测试1] 单次归还操作耗时")
    iterations = 1000
    total_time = 0
    
    for i in range(iterations):
        start = time.perf_counter()
        
        # 获取连接
        conn = client.connection._pool.get_connection()
        
        # 执行简单查询
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        
        # 归还连接
        client.connection._pool.return_connection(conn)
        
        end = time.perf_counter()
        total_time += (end - start)
    
    avg_time_ms = (total_time / iterations) * 1000
    print(f"  迭代次数: {iterations}")
    print(f"  总耗时: {total_time * 1000:.2f} ms")
    print(f"  平均每次: {avg_time_ms:.4f} ms")
    print(f"  QPS: {iterations / total_time:.0f}")
    
    # 测试2：使用上下文管理器的开销
    print("\n[测试2] 上下文管理器（with语句）开销")
    total_time = 0
    
    for i in range(iterations):
        start = time.perf_counter()
        
        with client.connection._pool.get_connection_context() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
        
        end = time.perf_counter()
        total_time += (end - start)
    
    avg_time_ms = (total_time / iterations) * 1000
    print(f"  迭代次数: {iterations}")
    print(f"  总耗时: {total_time * 1000:.2f} ms")
    print(f"  平均每次: {avg_time_ms:.4f} ms")
    print(f"  QPS: {iterations / total_time:.0f}")
    
    # 测试3：对比创建新连接的开销（不归还不推荐，仅做对比）
    print("\n[测试3] 创建新连接的开销（对比参考）")
    total_time = 0
    
    # 先清理所有连接
    client.close()
    
    # 重新创建客户端
    client = OpenGauss(
        hosts=[{
            "host": db_config["host"],
            "port": db_config["port"]
        }],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
        use_connection_pool=False,  # 使用单连接模式
    )
    
    for i in range(100):  # 减少迭代次数，因为创建连接很慢
        start = time.perf_counter()
        
        # 关闭旧连接（仅在单连接模式下）
        if not client.connection.use_connection_pool:
            if client.connection.conn and not client.connection.conn.closed:
                client.connection.conn.close()
            
            # 创建新连接
            client.connection.connect()
            
            cursor = client.connection.conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
        
        end = time.perf_counter()
        total_time += (end - start)
    
    avg_time_ms = (total_time / 100) * 1000
    print(f"  迭代次数: 100")
    print(f"  总耗时: {total_time * 1000:.2f} ms")
    print(f"  平均每次: {avg_time_ms:.4f} ms")
    print(f"  QPS: {100 / total_time:.0f}")
    print(f"  [INFO] 对比：创建新连接比归还连接慢约 {avg_time_ms / 0.035:.0f} 倍")
    
    client.close()
    
    # 测试4：不同并发下的表现
    print("\n[测试4] 并发场景下的归还开销")
    
    # 重新创建使用连接池的客户端
    client = OpenGauss(
        hosts=[{
            "host": db_config["host"],
            "port": db_config["port"]
        }],
        database=db_config["database"],
        user=db_config["user"],
        password=db_config["password"],
        use_connection_pool=True,
        pool_min_conn=10,
        pool_max_conn=50
    )
    
    import threading
    
    for concurrency in [1, 5, 10, 20]:
        results = []
        errors = []
        
        def worker(worker_id):
            try:
                start = time.perf_counter()
                for i in range(50):
                    with client.connection._pool.get_connection_context() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT %s", (worker_id * 50 + i,))
                        result = cursor.fetchone()
                        cursor.close()
                end = time.perf_counter()
                results.append(end - start)
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        start_all = time.perf_counter()
        
        for i in range(concurrency):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        end_all = time.perf_counter()
        total_queries = concurrency * 50
        total_time = end_all - start_all
        
        print(f"  并发数: {concurrency:2d} | "
              f"总查询: {total_queries:4d} | "
              f"总耗时: {total_time * 1000:7.2f} ms | "
              f"QPS: {total_queries / total_time:7.0f} | "
              f"错误: {len(errors)}")
    
    # 显示连接池状态
    print("\n[连接池状态]")
    status = client.connection._pool.get_pool_status()
    for key, value in status.items():
        print(f"  {key}: {value}")
    
    client.close()
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == '__main__':
    benchmark_return_connection()
