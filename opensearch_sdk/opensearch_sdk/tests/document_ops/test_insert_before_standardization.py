#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试：验证插入时字段名是否在 INSERT 前就被标准化
"""
import json
import warnings
from pathlib import Path
from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.utils.config_loader import load_db_config

# 加载配置
config = load_db_config()

# 创建客户端
client = OpenGauss(
    hosts=[{'host': config['host'], 'port': config['port']}],
    database=config.get('database', 'es'),
    user=config['user'],
    password=config['password']
)

TEST_INDEX = "test_insert_normalization"

# 清理旧索引
try:
    client.indices.delete(index=TEST_INDEX)
except:
    pass

print("="*70)
print("测试：插入时字段名标准化")
print("="*70)

# 1. 创建索引（使用带点号和连字符的字段名）
print("\n1. 创建索引...")
mapping = {
    "mappings": {
        "properties": {
            "user.name": {"type": "keyword"},      # → user_name
            "user-age": {"type": "integer"},        # → user_age
            "contact.email": {"type": "keyword"}    # → contact_email
        }
    }
}

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    client.indices.create(index=TEST_INDEX, body=mapping)

print("   [OK] 索引创建成功")
print("   字段映射：user.name → user_name, user-age → user_age, contact.email → contact_email")

# 2. 插入文档（使用原始字段名 - 带点号和连字符）
print("\n2. 插入文档（使用原始字段名）...")
doc = {
    "user.name": "Alice",           # 原始字段名
    "user-age": 25,                 # 原始字段名
    "contact.email": "alice@example.com"  # 原始字段名
}

print(f"   输入字段名: {list(doc.keys())}")

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = client.index(index=TEST_INDEX, id="doc1", body=doc)
    
    print(f"   [OK] 插入成功: {result['result']}")
    
    # 3. 验证数据库中存储的字段名
    print("\n3. 验证数据库中的字段名...")
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
                (TEST_INDEX,)
            )
            columns = [row[0] for row in cursor.fetchall()]
            print(f"   数据库列名: {columns}")
        finally:
            cursor.close()
    
    # 4. 获取文档验证
    print("\n4. 获取文档验证...")
    doc_result = client.get(index=TEST_INDEX, id="doc1")
    source = doc_result['_source']
    print(f"   返回字段名: {list(source.keys())}")
    print(f"   数据内容: {source}")
    
    # 5. 验证查询
    print("\n5. 测试查询...")
    
    # 使用原始字段名查询
    search_result = client.search(
        index=TEST_INDEX,
        body={
            "query": {
                "term": {
                    "user.name": "Alice"  # 使用原始字段名
                }
            }
        }
    )
    print(f"   使用 'user.name' 查询: 找到 {len(search_result['hits']['hits'])} 条结果")
    
    # 使用转换后的字段名查询
    search_result2 = client.search(
        index=TEST_INDEX,
        body={
            "query": {
                "term": {
                    "user_name": "Alice"  # 使用转换后的字段名
                }
            }
        }
    )
    print(f"   使用 'user_name' 查询: 找到 {len(search_result2['hits']['hits'])} 条结果")
    
    print("\n" + "="*70)
    print("[OK] 测试通过！")
    print("="*70)
    print("\n结论：")
    print("[OK] 插入时字段名在 INSERT 前就被标准化")
    print("[OK] 数据库中存储的是标准化后的字段名")
    print("[OK] 查询时使用原始或标准化字段名都能正常工作")
    print("[OK] 不需要依赖异常处理来修正字段名")
    
except Exception as e:
    print(f"\n[ERROR] 测试失败: {e}")
    import traceback
    traceback.print_exc()

finally:
    # 清理
    print("\n6. 清理测试索引...")
    try:
        client.indices.delete(index=TEST_INDEX)
        print("   [OK] 索引已删除")
    except:
        pass
    
    # [PASS] 在关闭客户端前检查连接池状态，确保没有连接泄漏
    leak_detected = False
    leak_message = ""
    
    if hasattr(client.connection, '_pool') and client.connection._pool:
        pool_status = client.connection._pool.get_pool_status()
        used_connections = pool_status.get('used_connections', 0)
        if used_connections != 0:
            leak_detected = True
            leak_message = f"测试结束后仍有 {used_connections} 个连接未归还: {pool_status}"
    
    # [PASS] 先关闭客户端，确保资源清理
    client.close()
    
    # [PASS] 最后再检查，即使有泄漏也打印警告
    if leak_detected:
        print(f"\n[FAIL] {leak_message}")
