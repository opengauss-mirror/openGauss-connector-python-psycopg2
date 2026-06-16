#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
索引重建功能示例
展示如何使用 rebuild_index 方法重建数据库索引

警告：索引重建是高风险操作！
- 重建过程中会锁定表，阻塞所有读写操作
- 大型表的索引重建可能需要很长时间
- 建议在业务低峰期执行，并提前评估影响
- 生产环境使用前务必在测试环境验证
"""

from utils import load_config
from opensearch_sdk import OpenGauss

# 加载配置
config = load_config()

# 创建客户端
client = OpenGauss(
    hosts=[{'host': config['host'], 'port': config['port']}],
    database=config['database'],
    user=config['user'],
    password=config['password']
)

try:
    # 示例1：重建 B-tree 索引
    print("=== 示例1：重建 B-tree 索引 ===")
    result = client.indices.rebuild_index(
        index_name="idx_user_email",
        table_name="users",
        column_name="email",
        index_type="btree"
    )
    print(f"结果: {result}")
    print()
    
    # 示例2：重建 GIN 索引（适合全文搜索）
    print("=== 示例2：重建 GIN 索引 ===")
    result = client.indices.rebuild_index(
        index_name="idx_product_description",
        table_name="products",
        column_name="description",
        index_type="gin"
    )
    print(f"结果: {result}")
    print()
    
    # 示例3：重建 HNSW 向量索引
    print("=== 示例3：重建 HNSW 向量索引 ===")
    result = client.indices.rebuild_index(
        index_name="idx_embedding",
        table_name="vectors",
        column_name="embedding",
        index_type="hnsw"
    )
    print(f"结果: {result}")
    
except Exception as e:
    print(f"错误: {e}")
finally:
    client.close()
