#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分布式表创建顺序优化示例

演示优化后的分布式表创建流程：
1. 先创建空表
2. 立即转换为分布式表（此时表为空，转换很快）
3. 在各个分片上并行创建索引

这种顺序避免了在单节点上创建索引后再重新分布的性能浪费。
"""

from utils import load_config
from opensearch_sdk import OpenGauss


def check_distributed_environment(client):
    """检查是否为分布式环境"""
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'spq'")
            row = cursor.fetchone()

            if not row:
                print("\n[WARN] SPQ 扩展未安装，无法使用分布式表功能")
                print("要启用分布式表，请执行: CREATE EXTENSION spq;")
                return False

            cursor.execute("SELECT COUNT(*) FROM spq_get_active_worker_nodes()")
            count = cursor.fetchone()[0]

            if count == 0:
                print("\n[WARN] 没有活跃的工作节点，无法使用分布式表功能")
                return False

            print(f"\n[OK] 检测到分布式环境 ({count} 个活跃节点)")
            return True
        finally:
            cursor.close()


def check_table_type(client, index_name):
    """检查表是普通表还是分布式表"""
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT logicalrelid FROM pg_dist_partition WHERE logicalrelid = %s::regclass",
                (index_name,)
            )
            row = cursor.fetchone()

            if row:
                print("[INFO] 表类型: 分布式表")
            else:
                print("[INFO] 表类型: 普通表")
        finally:
            cursor.close()


def check_distributed_table_details(client, index_name):
    """检查分布式表的详细信息"""
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT logicalrelid FROM pg_dist_partition WHERE logicalrelid = %s::regclass",
                (index_name,)
            )
            row = cursor.fetchone()

            if row:
                print("[INFO] 表类型: 分布式表 ✓")
            else:
                print("[INFO] 表类型: 普通表 ✗")

            cursor.execute(
                "SELECT COUNT(*) FROM pg_dist_shard WHERE logicalrelid = %s::regclass",
                (index_name,)
            )
            shard_count = cursor.fetchone()[0]
            print(f"[INFO] 分片数量: {shard_count}")

            cursor.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = %s
                AND indexname NOT LIKE '%%_pkey'
                ORDER BY indexname
            """, (index_name,))
            indexes = [row[0] for row in cursor.fetchall()]
            print(f"[INFO] 索引数量: {len(indexes)}")
            print(f"[INFO] 索引列表:")
            for idx in indexes:
                print(f"       - {idx}")
        finally:
            cursor.close()


def create_normal_table_example(client):
    """示例1：创建普通表（向后兼容）"""
    print("\n" + "-" * 70)
    print("示例1：创建普通表（默认行为）")
    print("-" * 70)

    index_name = "example_normal_table"

    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)
        print(f"[INFO] 删除已存在的索引: {index_name}")

    client.indices.create(
        index=index_name,
        body={
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "category": {"type": "keyword"}
                }
            }
        }
    )

    print(f"[OK] 普通表 '{index_name}' 创建成功")
    check_table_type(client, index_name)
    return index_name


def create_distributed_table_example(client):
    """示例2：创建分布式表（优化后的流程）"""
    print("\n" + "-" * 70)
    print("示例2：创建分布式表（优化后的流程）")
    print("-" * 70)

    dist_index_name = "example_distributed_table"

    if client.indices.exists(index=dist_index_name):
        client.indices.delete(index=dist_index_name)
        print(f"[INFO] 删除已存在的索引: {dist_index_name}")

    print("\n[INFO] 创建分布式表...")
    print("     优化流程:")
    print("     1. 创建空表")
    print("     2. 立即转换为分布式表（表为空，转换很快）")
    print("     3. 在各个分片上并行创建索引")

    client.indices.create(
        index=dist_index_name,
        body={
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "embedding": {"type": "float_vector", "dimension": 4}
                }
            }
        },
        distributed=True,
        distribution_column="user_id",
        shard_count=4
    )

    print(f"[OK] 分布式表 '{dist_index_name}' 创建成功")
    check_distributed_table_details(client, dist_index_name)
    return dist_index_name


def cleanup_tables(client, index_names):
    """清理测试表"""
    print("\n" + "-" * 70)
    print("清理测试数据...")
    print("-" * 70)

    for index_name in index_names:
        try:
            if client.indices.exists(index=index_name):
                client.indices.delete(index=index_name)
                print(f"[OK] 已删除索引: {index_name}")
        except Exception as e:
            print(f"[WARN] 删除索引 {index_name} 失败: {e}")


def main():
    """主函数"""
    config = load_config()

    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password']
    )

    print("=" * 70)
    print("分布式表创建顺序优化示例")
    print("=" * 70)

    try:
        if not check_distributed_environment(client):
            return

        normal_index = create_normal_table_example(client)
        dist_index = create_distributed_table_example(client)

        print("\n" + "=" * 70)
        print("优化效果说明")
        print("=" * 70)
        print("""
优化前（低效）:
  1. CREATE TABLE (单节点)
  2. CREATE INDEX title (单节点)
  3. CREATE INDEX embedding (单节点)
  4. create_distributed_table() → 需要重新分布数据 + 重建索引

优化后（高效）:
  1. CREATE TABLE (单节点)
  2. create_distributed_table() → 表为空，转换很快
  3. CREATE INDEX title (各分片并行创建)
  4. CREATE INDEX embedding (各分片并行创建)

性能提升:
  - 避免在单节点上创建索引后再丢弃
  - 索引直接在各个分片上并行创建
  - 减少不必要的资源浪费
""")

    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        cleanup_tables(client, ["example_normal_table", "example_distributed_table"])
        client.close()
        print("\n[OK] 示例执行完成")


if __name__ == '__main__':
    main()
