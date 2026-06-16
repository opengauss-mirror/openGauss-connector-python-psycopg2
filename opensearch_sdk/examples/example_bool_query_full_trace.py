#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Opensearch兼容接口- Bool 查询全流程 SQL 追踪示例

本示例演示如何使用 SQL 追踪功能查看 bool 查询从建表到搜索的完整 SQL 执行过程。

功能说明：
1. 创建包含多个字段的索引
2. 批量插入测试数据
3. 执行复杂 bool 查询（must + filter）
4. 打印每一步执行的完整 SQL 语句

运行方式：
    python examples/example_bool_query_full_trace.py
"""

import sys
import time
from pathlib import Path

from utils import load_config

from opensearch_sdk import OpenGauss

config = load_config()


def print_section(title):
    """打印分隔符"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_sql_record(record, index=1):
    """打印单条 SQL 记录"""
    print(f"\n[SQL {index}] {record.context}")
    print(f"  耗时：{record.duration_ms:.2f}ms")
    print(f"  结果数：{record.result_count}")
    print(f"  SQL:\n    {record.sql}")
    
    if record.params:
        print(f"  参数：{record.params}")
    
    if record.sampled_results:
        print(f"  采样结果：{len(record.sampled_results)} 行")
        for i, row in enumerate(record.sampled_results[:3], 1):
            print(f"    {i}. {row}")
        if len(record.sampled_results) > 3:
            print(f"    ... 还有 {len(record.sampled_results) - 3} 行")


def main():
    """主函数"""
    print_section("Opensearch兼容接口- Bool 查询全流程 SQL 追踪示例")
    
    # 创建带 SQL 追踪的客户端
    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password'],
        enable_sql_trace=True,              # 启用 SQL 追踪
        sql_trace_mask_sensitive=True,      # 参数脱敏
        sql_trace_max_sample_rows=5         # 采样前 5 行
    )
    
    # 使用独立的索引名避免冲突
    test_index = f'example_bool_full_trace_{int(time.time())}'
    
    try:
        # =====================================================================
        # 步骤 1: 创建索引
        # =====================================================================
        print_section("步骤 1: 创建索引")
        
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text", "analyzer": "ik_max_word"},
                    "content": {"type": "text", "analyzer": "ik_max_word"},
                    "category": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "views": {"type": "integer"},
                    "publish_date": {"type": "date"}
                }
            }
        }
        
        result = client.indices.create(test_index, mapping)
        print(f"[OK] 索引创建成功：{result}")
        # 注意：不清空历史，保留建表 SQL
        
        # =====================================================================
        # 步骤 2: 批量插入测试数据
        # =====================================================================
        print_section("步骤 2: 批量插入测试数据")
        
        test_docs = [
            {
                "title": "OpenSearch 技术详解",
                "content": "本文介绍 OpenSearch 的架构和使用方法，包括索引管理、文档操作等",
                "category": "tech",
                "tags": ["opensearch", "search", "database"],
                "status": "published",
                "views": 1500,
                "publish_date": "2024-01-15"
            },
            {
                "title": "数据库优化最佳实践",
                "content": "数据库性能优化的 10 个技巧，帮助你提升查询效率",
                "category": "tech",
                "tags": ["database", "optimization", "performance"],
                "status": "published",
                "views": 2300,
                "publish_date": "2024-02-20"
            },
            {
                "title": "Python 编程指南",
                "content": "Python 高级编程技术分享，包括装饰器、元类等内容",
                "category": "programming",
                "tags": ["python", "coding", "tutorial"],
                "status": "draft",
                "views": 800,
                "publish_date": "2024-03-10"
            },
            {
                "title": "搜索引擎架构设计",
                "content": "大规模搜索引擎系统设计实践，涵盖分布式架构、负载均衡等",
                "category": "tech",
                "tags": ["search", "architecture", "system-design"],
                "status": "published",
                "views": 3200,
                "publish_date": "2024-01-05"
            },
            {
                "title": "数据分析入门",
                "content": "数据分析基础概念和工具介绍，适合初学者学习",
                "category": "data-science",
                "tags": ["data", "analytics", "beginner"],
                "status": "published",
                "views": 1800,
                "publish_date": "2024-02-28"
            }
        ]
        
        # 插入文档（不逐个显示 SQL）
        for i, doc in enumerate(test_docs, 1):
            doc_id = f"doc{i:03d}"
            result = client.create(test_index, doc_id, doc)
            print(f"[OK] 插入文档 {doc_id}: {doc['title']}")
        
        print(f"\n[OK] 已插入 {len(test_docs)} 个文档（SQL 将在最终报告中查看）")
        
        # =====================================================================
        # 步骤 3: 执行简单匹配查询
        # =====================================================================
        print_section("步骤 3: 简单匹配查询")
        
        simple_query = {
            "query": {
                "match": {
                    "content": "OpenSearch"
                }
            },
            "size": 10
        }
        
        result = client.search(test_index, simple_query)
        total_hits = result['hits']['total']['value']
        print(f"[OK] 简单匹配查询完成，命中 {total_hits} 条结果")
        
        # =====================================================================
        # 步骤 4: 执行复杂 bool 查询（重点）
        # =====================================================================
        print_section("步骤 4: 复杂 bool 查询（must + filter）")
        
        bool_query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "match": {
                                "category": "tech"
                            }
                        }
                    ],
                    "filter": [
                        {
                            "term": {
                                "status": "published"
                            }
                        },
                        {
                            "range": {
                                "views": {
                                    "gte": 1000
                                }
                            }
                        }
                    ]
                }
            },
            "size": 10,
            "sort": [
                {"views": "desc"}
            ]
        }
        
        print("Bool 查询条件:")
        print("  must: category = tech")
        print("  filter:")
        print("    - status = published")
        print("    - views >= 1000")
        print("  sort: views DESC")
        
        result = client.search(test_index, bool_query)
        total_hits = result['hits']['total']['value']
        print(f"\n[OK] Bool 查询完成，命中 {total_hits} 条结果")
        
        if total_hits > 0:
            print("\n返回的结果:")
            for i, hit in enumerate(result['hits']['hits'][:3], 1):
                source = hit['_source']
                print(f"  {i}. {source['title']} (views: {source['views']})")
        
        # 显示 Bool 查询的 SQL（重点）
        session = client.sql_tracer.get_last_session()
        print(f"\nBool 查询执行了 {len(session.records)} 条 SQL:")
        for i, record in enumerate(session.records, 1):
            print_sql_record(record, i)
        
        # =====================================================================
        # 步骤 5: 导出完整流程的 SQL 追踪报告
        # =====================================================================
        print_section("步骤 5: 导出完整流程的 SQL 追踪报告")
        
        export_dir = Path("tmp/sql_trace_exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        client.sql_tracer.export_dir = export_dir
        
        # 获取所有会话
        all_sessions = client.sql_tracer._sessions
        print(f"共记录了 {len(all_sessions)} 个操作会话")
        
        # 使用新增的 export_all_sessions 方法导出完整流程
        md_file = client.sql_tracer.export_all_sessions(export_format="markdown", filename_prefix="bool_full_workflow")
        print(f"[OK] 已导出完整流程报告：{md_file}")
        
        yaml_file = client.sql_tracer.export_all_sessions(export_format="yaml", filename_prefix="bool_full_workflow")
        print(f"[OK] 已导出完整 YAML 流程：{yaml_file}")
        
        sql_file = client.sql_tracer.export_all_sessions(export_format="sql", filename_prefix="bool_full_workflow")
        print(f"[OK] 已导出可执行 SQL 脚本：{sql_file}")
        
        # 导出最后一个查询的详细报告（原有功能）
        md_last = client.sql_tracer.export_to_file(export_format="markdown", verbose=False)
        print(f"[OK] 已导出 Markdown 报告：{md_last}")
        
        json_last = client.sql_tracer.export_to_file(export_format="json")
        print(f"[OK] 已导出 JSON 数据：{json_last}")
        
        yaml_last = client.sql_tracer.export_to_file(export_format="yaml")
        print(f"[OK] 已导出 YAML 格式：{yaml_last}")
        
        # =====================================================================
        # 完成
        # =====================================================================
        print_section("示例执行完成")
        print("Bool 查询全流程 SQL 追踪演示完毕!")
        print(f"\n提示：可以在 {export_dir.absolute()} 目录下查看导出的报告文件")
        
    except Exception as e:
        print(f"\n[ERROR] 发生错误：{e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理测试索引
        try:
            client.indices.delete(test_index)
            print(f"\n[OK] 已清理测试索引：{test_index}")
        except Exception:
            pass
        
        # 关闭连接
        client.close()
        print("[OK] 已关闭数据库连接")


if __name__ == '__main__':
    main()
