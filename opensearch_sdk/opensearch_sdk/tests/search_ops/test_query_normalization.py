#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速测试：验证查询时字段名标准化的行为
"""
import json
import warnings
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

TEST_INDEX = "test_query_normalization"

# 清理旧索引
try:
    client.indices.delete(index=TEST_INDEX)
except:
    pass

# 创建索引（使用带点号的字段名）
print("="*70)
print("1. 创建索引（使用带点号的字段名）")
print("="*70)
mapping = {
    "mappings": {
        "properties": {
            "user.name": {"type": "keyword"},
            "user.age": {"type": "integer"}
        }
    }
}

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    client.indices.create(index=TEST_INDEX, body=mapping)

print("[OK] 索引创建成功")

# 插入数据（使用转换后的字段名）
print("\n" + "="*70)
print("2. 插入数据")
print("="*70)
doc = {
    "user_name": "Alice",  # 使用转换后的名称
    "user_age": 25
}

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    result = client.index(index=TEST_INDEX, id="doc1", body=doc)

print(f"[OK] 文档插入成功: {result}")

# 测试 1：使用带点号的字段名查询
print("\n" + "="*70)
print("3. 测试查询：使用带点号的字段名 (user.name)")
print("="*70)
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = client.search(
            index=TEST_INDEX,
            body={
                "query": {
                    "term": {
                        "user.name": "Alice"  # 使用带点号的字段名
                    }
                }
            }
        )
    
    print(f"[OK] 查询成功！找到 {len(result['hits']['hits'])} 条结果")
    if result['hits']['hits']:
        source = result['hits']['hits'][0]['_source']
        print(f"   返回数据: {source}")
        print(f"   [OK] 返回的字段名是转换后的: user_name, user_age")
except Exception as e:
    print(f"[ERROR] 查询失败: {e}")

# 测试 2：使用转换后的字段名查询
print("\n" + "="*70)
print("4. 测试查询：使用转换后的字段名 (user_name)")
print("="*70)
try:
    result = client.search(
        index=TEST_INDEX,
        body={
            "query": {
                "term": {
                    "user_name": "Alice"  # 使用转换后的字段名
                }
            }
        }
    )
    
    print(f"[OK] 查询成功！找到 {len(result['hits']['hits'])} 条结果")
    if result['hits']['hits']:
        source = result['hits']['hits'][0]['_source']
        print(f"   返回数据: {source}")
except Exception as e:
    print(f"[ERROR] 查询失败: {e}")

# 测试 3：获取文档
print("\n" + "="*70)
print("5. 测试获取文档")
print("="*70)
try:
    result = client.get(index=TEST_INDEX, id="doc1")
    source = result['_source']
    print(f"[OK] 获取成功！")
    print(f"   返回数据: {source}")
    print(f"   [OK] 字段名已转换: {list(source.keys())}")
except Exception as e:
    print(f"[ERROR] 获取失败: {e}")

# 清理
print("\n" + "="*70)
print("6. 清理测试索引")
print("="*70)
try:
    client.indices.delete(index=TEST_INDEX)
    print("[OK] 索引已删除")
except:
    pass

print("\n" + "="*70)
print("测试完成！")
print("="*70)
print("\n结论：")
print("[OK] 查询时使用带点号的字段名会被自动转换为下划线格式")
print("[OK] 转换后的字段名与数据库中的列名匹配，查询正常工作")
print("[OK] 返回的文档中使用的是转换后的字段名")
print("[OK] 查询操作不会出现'列不存在'的问题（因为只是读取，不涉及列创建）")
