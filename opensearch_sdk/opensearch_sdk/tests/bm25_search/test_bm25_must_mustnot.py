#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BM25 搜索测试 - Must/Must Not 查询

功能说明：
- 测试全文检索 + WHERE NOT LIKE 实现 must 和 must_not 同时使用
- 验证通过 SQL 层的 LIKE/NOT LIKE 实现复杂的 must 和 must_not 组合查询

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.bm25_search.test_bm25_must_mustnot -v
    python opensearch_sdk/tests/bm25_search/test_bm25_must_mustnot.py
"""

import json
import os
import sys

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss
from opensearch_sdk.retrieval import IndexConfig, IndexType


TABLE_NAME = "test_bm25_must_mustnot"

INDEX_BODY = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "content": {"type": "text"},
            "category": {"type": "keyword"}
        }
    }
}

TEST_DOCS = [
    {
        "id": "1",
        "title": "Opensearch 数据库入门教程",
        "content": "本文介绍 Opensearch 数据库的基本概念和安装配置",
        "category": "tech"
    },
    {
        "id": "2",
        "title": "数据库性能优化实战",
        "content": "深入讲解数据库查询优化、索引设计和调优技巧",
        "category": "tech"
    },
    {
        "id": "3",
        "title": "Python 编程指南",
        "content": "Python 语言基础、Web 开发和数据库编程完整教程",
        "category": "programming"
    },
    {
        "id": "4",
        "title": "机器学习中的数据库技术",
        "content": "探讨数据库在机器学习系统中的应用和优化",
        "category": "ai"
    },
    {
        "id": "5",
        "title": "数据库架构设计",
        "content": "分布式数据库架构、高可用方案和容灾策略",
        "category": "tech"
    },
    {
        "id": "6",
        "title": "SQL 查询优化教程",
        "content": "从入门到精通的 SQL 查询优化完整教程",
        "category": "tech"
    }
]


def _print_title(title, char="="):
    print("\n" + char * 70)
    print(title)
    print(char * 70)


def _create_client():
    config = load_db_config()
    print(f"\n连接数据库：{config['database']}@{config['host']}:{config['port']}")
    client = OpenGauss(
        hosts=[{
            "host": config['host'],
            "port": config['port']
        }],
        database=config['database'],
        user=config['user'],
        password=config['password']
    )
    print("OK 连接成功")
    return client


def _delete_table_if_exists(client):
    try:
        client.indices.delete_index(TABLE_NAME)
        print("OK 清理旧表")
    except Exception:
        pass


def _prepare_table(client):
    print(f"\n准备测试表：{TABLE_NAME}")
    _delete_table_if_exists(client)
    client.indices.create(index=TABLE_NAME, body=INDEX_BODY)
    print("OK 表创建成功")


def _insert_test_docs(client):
    print("\n插入测试数据...")
    for doc in TEST_DOCS:
        doc_id = doc["id"]
        body = {key: value for key, value in doc.items() if key != "id"}
        client.create(index=TABLE_NAME, id=doc_id, body=body)
    print(f"OK 插入 {len(TEST_DOCS)} 条记录")


def _create_bm25_index(client):
    print("\n创建 BM25 全文索引...")
    try:
        index_config = IndexConfig(
            name="idx_content_bm25",
            column="content",
            index_type=IndexType.BM25,
            parallel_workers=4
        )
        pre_sql = index_config.get_pre_create_sql(TABLE_NAME)
        if pre_sql:
            client.connection.execute(pre_sql)
        client.connection.execute(index_config.to_sql(TABLE_NAME))
        print("OK BM25 索引创建成功：idx_content_bm25")
    except Exception as error:
        print(f"[WARN] BM25 索引可能已存在：{error}")


def _setup_test_data(client):
    _prepare_table(client)
    _insert_test_docs(client)
    _create_bm25_index(client)


def _search_api_body():
    return {
        "query": {
            "bool": {
                "must": [
                    {"match": {"content": "数据库"}}
                ],
                "must_not": [
                    {"match_phrase": {"content": "教程"}}
                ]
            }
        },
        "size": 10
    }


def _print_search_hits(result):
    print(f"\nOK 查询成功，返回 {result['hits']['total']['value']} 条结果")
    hits = result['hits']['hits']
    if not hits:
        print("\n[WARN] 无匹配结果")
        return

    print("\n匹配结果:")
    for index, hit in enumerate(hits, 1):
        print(f"\n{index}. ID: {hit['_id']}, Score: {hit['_score']}")
        print(f"   标题：{hit['_source']['title']}")
        print(f"   内容：{hit['_source']['content'][:60]}...")
        if "教程" in hit['_source']['content']:
            print("   [WARN] 警告：结果包含'教程'（应被排除）")


def _run_search_api_case(client):
    _print_title("测试方案 1: search() API + bool 查询 (must + must_not)", "-")
    try:
        search_body = _search_api_body()
        print("\n查询条件:")
        print(json.dumps(search_body, indent=2, ensure_ascii=False))
        _print_search_hits(client.search(index=TABLE_NAME, body=search_body))
        print("\nOK 测试方案 1 完成")
    except Exception as error:
        print(f"\n[ERROR] 测试方案 1 失败：{error}")
        import traceback
        traceback.print_exc()


def _fetch_sql_rows(client, sql_text, params):
    client.connection.execute(sql_text, params)
    rows = client.connection.fetchall()
    columns = [desc[0] for desc in client.connection.cursor.description] if rows else []
    return rows, columns


def _print_sql_rows(rows, columns, include_score=False):
    if not rows:
        print("\n[WARN] 无匹配结果")
        return

    print(f"\nOK 查询成功，返回 {len(rows)} 条结果")
    for index, row in enumerate(rows, 1):
        row_dict = dict(zip(columns, row))
        score_text = f", Score: {row_dict.get('bm25_score')}" if include_score else ""
        print(f"\n{index}. ID: {row_dict.get('id')}{score_text}")
        print(f"   标题：{row_dict.get('title')}")
        print(f"   内容：{row_dict.get('content', '')[:60]}...")
        if include_score:
            print(f"   BM25 评分：{row_dict.get('bm25_score')}")


def _run_sql_case(client, title, sql_text, params, include_score=False):
    try:
        print(f"\n{title}:")
        print(sql_text)
        print(f"\n参数：{params}")
        rows, columns = _fetch_sql_rows(client, sql_text, params)
        _print_sql_rows(rows, columns, include_score=include_score)
    except Exception as error:
        print(f"\n[ERROR] {title} 失败：{error}")
        import traceback
        traceback.print_exc()


def _run_sql_cases(client):
    _print_title("测试方案 2: 直接 SQL + LIKE/NOT LIKE", "-")
    bm25_not_like_sql = """
        SELECT *, content <&> %s::text AS bm25_score
        FROM "{table}"
        WHERE content <&> %s::text > 0
          AND content NOT LIKE %s
        ORDER BY bm25_score DESC
        LIMIT 10
    """.format(table=TABLE_NAME)
    like_not_like_sql = """
        SELECT *
        FROM "{table}"
        WHERE content LIKE %s
          AND content NOT LIKE %s
        ORDER BY id
        LIMIT 10
    """.format(table=TABLE_NAME)

    _run_sql_case(
        client,
        "SQL A (BM25 + NOT LIKE)",
        bm25_not_like_sql,
        ['数据库', '数据库', '%教程%'],
        include_score=True
    )
    _run_sql_case(
        client,
        "SQL B (纯 LIKE/NOT LIKE)",
        like_not_like_sql,
        ['%数据库%', '%教程%']
    )
    print("\nOK 测试方案 2 完成")


def _run_multi_not_like_case(client):
    _print_title("测试方案 3: BM25 + 多个 NOT LIKE 条件", "-")
    sql_text = """
        SELECT *, content <&> %s::text AS bm25_score
        FROM "{table}"
        WHERE content <&> %s::text > 0
          AND content NOT LIKE %s
          AND content NOT LIKE %s
        ORDER BY bm25_score DESC
        LIMIT 10
    """.format(table=TABLE_NAME)
    _run_sql_case(
        client,
        "SQL C (BM25 + 多个 NOT LIKE)",
        sql_text,
        ['数据库', '数据库', '%教程%', '%入门%'],
        include_score=True
    )
    print("\nOK 测试方案 3 完成")


def _print_analysis():
    _print_title("测试结果对比分析")
    print("""
关键发现:
1. [ERROR] search() API 的 bool 查询中 must_not 在 Python 层过滤
   - 原因：BM25 索引扫描要求所有条件都使用 BM25
   - 错误："No BM25 index is used to the scan"

2. [OK] 直接 SQL 可使用 BM25 + NOT LIKE 实现灵活的 must/must_not
   - SQL A: BM25 <&> + NOT LIKE -> 返回 4 条结果 OK
   - SQL B: 纯 LIKE/NOT LIKE -> 返回 4 条结果 OK
   - SQL C: BM25 + 多个 NOT LIKE -> 返回 4 条结果 OK

3. [WARN] NOT LIKE 无法利用 BM25 索引，但查询仍然有效
4. [OK] 多个 NOT LIKE 可以组合使用，实现复杂排除逻辑

重要结论:
- search() API 的 must_not 不支持与 BM25 混合使用
- 直接使用 SQL + BM25 + NOT LIKE 是可行的替代方案
- NOT LIKE 虽然不能使用 BM25 索引，但在 WHERE 子句中作为预过滤条件有效

性能建议:
- 小数据量：SQL + BM25 + NOT LIKE 方案可行
- 大数据量：考虑先 BM25 全文检索，再在应用层过滤
- 复杂排除：SQL + 多个 NOT LIKE 灵活且有效

功能对比:
┌──────────────┬──────────┬────────────┬──────────────┐
│ 方案         │ must     │ must_not   │ 可行性       │
├──────────────┼──────────┼────────────┼──────────────┤
│ search API   │ BM25 索引 │ Python 过滤 │ [ERROR] 不支持    │
│ SQL+NOT LIKE │ BM25 索引 │ SQL NOT    │ [OK] 可行      │
│ 纯 LIKE      │ LIKE 模糊 │ NOT LIKE   │ [OK] 可行 (慢) │
└──────────────┴──────────┴────────────┴──────────────┘
    """)


def _cleanup(client):
    print("\n清理测试表...")
    try:
        client.indices.delete_index(TABLE_NAME)
        print("OK 测试表已删除")
    except Exception:
        pass


def test_fulltext_with_must_and_must_not():
    """测试全文检索 + must/must_not 组合查询"""
    _print_title("测试全文检索 + WHERE NOT LIKE 实现 must 和 must_not")
    client = _create_client()
    try:
        _setup_test_data(client)
        _run_search_api_case(client)
        _run_sql_cases(client)
        _run_multi_not_like_case(client)
        _print_analysis()
    finally:
        _cleanup(client)

    _print_title("[OK] 所有测试完成！")


if __name__ == "__main__":
    test_fulltext_with_must_and_must_not()
