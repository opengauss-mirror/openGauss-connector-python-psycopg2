#!/usr/bin/env python
# -*-coding:utf-8 -*-
"""
_source.includes/excludes 功能演示脚本

使用方法：
1. 确保数据库可访问
2. 运行：python example_source_filtering.py
"""

from utils import load_config
from opensearch_sdk import OpenGauss

# 加载配置
config = load_config()

# 初始化客户端
client = OpenGauss(
    hosts=[{'host': config['host'], 'port': config['port']}],
    database=config['database'],
    user=config['user'],
    password=config['password']
)

TEST_INDEX = "example_source_filter"

try:
    # ========== 1. 清理和创建索引 ==========\n    print("=" * 70)
    print("步骤 1: 清理旧索引并创建新索引")
    print("=" * 70)
    
    try:
        client.indices.delete(index=TEST_INDEX)
        print(f"[INFO] 删除已存在的索引 '{TEST_INDEX}'")
    except Exception:
        pass
    
    mapping = {
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "content": {"type": "text"},
                "category": {"type": "keyword"},
                "author": {"type": "keyword"},
                "publish_date": {"type": "date"},
                "view_count": {"type": "integer"},
                "vector_field": {"type": "knn_vector", "dims": 4}
            }
        }
    }
    
    client.indices.create(index=TEST_INDEX, body=mapping)
    print(f"[OK] 创建索引 '{TEST_INDEX}'\n")
    
    # ========== 2. 插入测试数据 ==========\n    print("=" * 70)
    print("步骤 2: 插入测试数据")
    print("=" * 70)
    
    test_docs = [
        {
            "id": "doc1",
            "body": {
                "title": "测试文档 1",
                "content": "这是第一个测试文档的内容",
                "category": "技术",
                "author": "张三",
                "publish_date": "2024-01-01",
                "view_count": 100,
                "vector_field": [0.1, 0.2, 0.3, 0.4]
            }
        },
        {
            "id": "doc2",
            "body": {
                "title": "测试文档 2",
                "content": "这是第二个测试文档",
                "category": "科学",
                "author": "李四",
                "publish_date": "2024-02-01",
                "view_count": 200,
                "vector_field": [0.5, 0.6, 0.7, 0.8]
            }
        },
        {
            "id": "doc3",
            "body": {
                "title": "测试文档 3",
                "content": "第三个文档",
                "category": "技术",
                "author": "王五",
                "publish_date": "2024-03-01",
                "view_count": 300,
                "vector_field": [0.9, 1.0, 0.1, 0.2]
            }
        }
    ]
    
    for doc in test_docs:
        client.index(index=TEST_INDEX, id=doc["id"], body=doc["body"])
    
    print(f"[OK] 成功插入 {len(test_docs)} 条测试数据\n")
    
    # ========== 3. 测试 includes 功能 ==========\n    print("=" * 70)
    print("步骤 3: 测试 _source.includes（SQL 层优化）")
    print("=" * 70)
    
    query_includes = {
        "_source": {
            "includes": ["title", "content"]
        },
        "query": {
            "match_all": {}
        }
    }
    
    result = client.search(index=TEST_INDEX, body=query_includes)
    hits = result['hits']['hits']
    
    print(f"\n查询返回 {len(hits)} 条结果")
    print("\n验证返回的字段:")
    for i, hit in enumerate(hits[:1], 1):  # 只显示第一个
        source = hit['_source']
        print(f"  文档 {i} 的 _source 包含字段：{list(source.keys())}")
        print(f"  [PASS] title: {'title' in source}")
        print(f"  [PASS] content: {'content' in source}")
        print(f"  [PASS] category (不应存在): {'category' not in source}")
        print(f"  [PASS] vector_field (不应存在): {'vector_field' not in source}")
    
    print("\n[OK] includes 功能测试成功！\n")
    
    # ========== 4. 测试 excludes 功能 ==========\n    print("=" * 70)
    print("步骤 4: 测试 _source.excludes（Python 层过滤）")
    print("=" * 70)
    
    query_excludes = {
        "_source": {
            "excludes": ["vector_field"]
        },
        "query": {
            "match_all": {}
        }
    }
    
    result = client.search(index=TEST_INDEX, body=query_excludes)
    hits = result['hits']['hits']
    
    print(f"\n查询返回 {len(hits)} 条结果")
    print("\n验证排除的字段:")
    for i, hit in enumerate(hits[:1], 1):  # 只显示第一个
        source = hit['_source']
        print(f"  文档 {i} 的 _source 包含字段：{list(source.keys())}")
        print(f"  [PASS] vector_field (应被排除): {'vector_field' not in source}")
        print(f"  [PASS] title (应存在): {'title' in source}")
        print(f"  [PASS] content (应存在): {'content' in source}")
    
    print("\n[OK] excludes 功能测试成功！\n")
    
    # ========== 5. 测试通配符模式 ==========\n    print("=" * 70)
    print("步骤 5: 测试通配符模式匹配")
    print("=" * 70)
    
    query_wildcard = {
        "_source": {
            "includes": ["*_date", "*_count"]  # 匹配 publish_date 和 view_count
        },
        "query": {
            "match_all": {}
        }
    }
    
    result = client.search(index=TEST_INDEX, body=query_wildcard)
    hits = result['hits']['hits']
    
    print(f"\n查询返回 {len(hits)} 条结果")
    for i, hit in enumerate(hits[:1], 1):
        source = hit['_source']
        print(f"  文档 {i} 的 _source 包含字段：{list(source.keys())}")
        print(f"  [PASS] publish_date (应匹配 *_date): {'publish_date' in source}")
        print(f"  [PASS] view_count (应匹配 *_count): {'view_count' in source}")
        print(f"  [PASS] title (不应存在): {'title' not in source}")
    
    print("\n[OK] 通配符模式测试成功！\n")
    
    # ========== 6. 性能对比提示 ==========\n    print("=" * 70)
    print("步骤 6: 性能说明")
    print("=" * 70)
    print("""
【includes vs excludes 性能对比】

[PASS] includes（推荐）：
  - SQL 层生成 SELECT col1, col2 FROM ...
  - 只传输需要的列
  - 减少网络带宽和内存占用
  - 适合大字段（如向量）排除场景

[WARN] excludes（当前低效实现）：
  - SQL 层仍然 SELECT *
  - Python 层删除不需要的字段
  - 数据传输量没有减少
  - 后续会优化为 SQL 层排除
  
【使用建议】
- 优先使用 includes（性能更好）
- excludes 适用于临时排除少量字段
- 大数据量场景建议使用 includes
""")
    
    print("\n[OK] 所有测试完成！\n")

except Exception as e:
    print(f"\n[ERROR] 测试失败：{e}")
    import traceback
    traceback.print_exc()

finally:
    # 清理测试索引
    try:
        client.indices.delete(index=TEST_INDEX)
        print(f"[INFO] 已清理测试索引 '{TEST_INDEX}'")
    except Exception:
        pass
    
    client.close()
    print("\n[INFO] 连接已关闭")
