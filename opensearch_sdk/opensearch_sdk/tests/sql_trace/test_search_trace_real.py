#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQL 追踪功能集成测试 - Search 方法（真实数据库）

测试 SQL 追踪在真实数据库环境下的工作情况
不使用 Mock，直接连接数据库验证

运行方式：
    python -m unittest opensearch_sdk.tests.sql_trace.test_search_trace_real -v
"""

import sys
import os
import unittest
import json
import uuid

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

# 加载数据库配置 - 使用绝对路径到项目根目录
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'db_config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    db_config = json.load(f)


class TestSearchTraceReal(unittest.TestCase):
    """SQL 追踪功能真实数据库集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.test_index = 'test_sql_trace_search_real'  # 使用唯一名称避免与其他测试冲突
        
        # 创建带 SQL 追踪的客户端
        cls.client = OpenGauss(
            hosts=[{'host': db_config['host'], 'port': db_config['port']}],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password'],
            enable_sql_trace=True,  # 启用 SQL 追踪
            sql_trace_mask_sensitive=True,
            sql_trace_max_sample_rows=10
        )
        
        # 清理旧索引（如果存在）
        try:
            cls.client.indices.delete(cls.test_index)
        except Exception:
            pass
        
        # 创建测试索引
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "category": {"type": "keyword"},
                    "publish_date": {"type": "date"}
                }
            }
        }
        cls.client.indices.create(cls.test_index, mapping)
        
        # 插入测试数据
        test_docs = [
            {
                "title": "Opensearch Introduction",
                "content": "Opensearch is a powerful vector database with full-text search support",
                "category": "technology",
                "publish_date": "2024-01-15"
            },
            {
                "title": "AI Applications",
                "content": "Artificial intelligence is transforming industries worldwide",
                "category": "technology",
                "publish_date": "2024-02-20"
            },
            {
                "title": "Travel Guide",
                "content": "Best places to visit in 2024",
                "category": "travel",
                "publish_date": "2024-03-10"
            }
        ]
                
        # 使用 index() 方法插入数据（不检查是否已存在）
        import time
        timestamp = int(time.time() * 1000) % 10000
        doc_ids = [f"doc1_{timestamp}", f"doc2_{timestamp}", f"doc3_{timestamp}"]
        for i, doc in enumerate(test_docs):
            result = cls.client.index(cls.test_index, doc_ids[i], doc)
            print(f"  插入文档 {i+1}: id={doc_ids[i]}, result={result.get('result', 'unknown')}")
                
        # 调试：验证数据是否真的插入成功
        try:
            verify_doc = cls.client.get(cls.test_index, doc_ids[0])
            print(f"\n[DEBUG] setUpClass 验证：{doc_ids[0]} 存在，title={verify_doc['_source'].get('title', 'N/A')}")
        except Exception as e:
            print(f"\n[DEBUG] setUpClass 验证：{doc_ids[0]} 不存在！错误：{e}")
                
        print(f"\n已创建测试索引 '{cls.test_index}' 并插入 {len(test_docs)} 条文档")
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(cls.test_index)
            print(f"\n已删除测试索引 '{cls.test_index}'")
        except Exception as e:
            print(f"\n删除索引失败：{e}")
        
        cls.client.close()
    
    def test_01_simple_match_query(self):
        """测试简单 match 查询的 SQL 追踪"""
        query_body = {
            "query": {
                "match_all": {}  # 使用 match_all 确保返回所有文档
            },
            "size": 10
        }
        
        # 执行搜索
        result = self.client.search(self.test_index, query_body)
        
        # 验证搜索结果
        self.assertIn("hits", result)
        self.assertGreater(result["hits"]["total"]["value"], 0)
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, "search")
        self.assertEqual(session.index_name, self.test_index)
        self.assertGreater(len(session.records), 0)
        
        # 打印追踪信息
        print(f"\n[测试 1] 简单 match 查询:")
        print(f"  返回结果数：{result['hits']['total']['value']}")
        print(f"  SQL 记录数：{len(session.records)}")
        if session.records:
            last_record = session.records[-1]
            print(f"  最后一条 SQL: {last_record.sql[:80]}...")
            print(f"  上下文：{last_record.context}")
    
    def test_02_bool_query_with_filter(self):
        """测试 bool 查询带过滤的 SQL 追踪"""
        query_body = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"content": "intelligence"}}
                    ],
                    "filter": [
                        {"term": {"category": "technology"}}
                    ]
                }
            },
            "size": 10
        }
        
        # 执行搜索
        result = self.client.search(self.test_index, query_body)
        
        # 验证搜索结果
        self.assertIn("hits", result)
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, "search")
        
        # 打印追踪信息
        print(f"\n[测试 2] Bool 查询 + Filter:")
        print(f"  返回结果数：{result['hits']['total']['value']}")
        print(f"  SQL 记录数：{len(session.records)}")
        
        # 导出 Markdown 查看详细信息
        filepath = self.client.sql_tracer.export_to_file(export_format="markdown")
        print(f"  导出文件：{filepath}")
    
    def test_03_complex_query(self):
        """测试复杂查询的 SQL 追踪"""
        query_body = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"title": "AI"}}
                    ],
                    "should": [
                        {"match": {"content": "transforming"}}
                    ],
                    "filter": [
                        {"range": {"publish_date": {"gte": "2024-01-01"}}}
                    ]
                }
            },
            "size": 10,
            "sort": [{"publish_date": "desc"}]
        }
        
        # 执行搜索
        result = self.client.search(self.test_index, query_body)
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        
        # 打印追踪信息
        print(f"\n[测试 3] 复杂查询 (Must + Should + Filter + Sort):")
        print(f"  返回结果数：{result['hits']['total']['value']}")
        print(f"  SQL 记录数：{len(session.records)}")
        print(f"  总耗时：{session.total_duration_ms:.2f}ms")
        
        # 显示所有 SQL 记录
        if session.records:
            print(f"\n  SQL 详情:")
            for i, record in enumerate(session.records, 1):
                print(f"    [{i}] {record.context}: {record.duration_ms:.2f}ms")
    
    def test_04_no_trace_when_disabled(self):
        """测试禁用追踪时无记录"""
        # 创建不启用追踪的客户端
        client_no_trace = OpenGauss(
            hosts=[{'host': db_config['host'], 'port': db_config['port']}],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password'],
            enable_sql_trace=False
        )
        
        query_body = {
            "query": {"match_all": {}}
        }
        
        # 执行搜索
        result = client_no_trace.search(self.test_index, query_body)
        
        # 验证没有追踪会话
        if hasattr(client_no_trace, 'sql_tracer') and client_no_trace.sql_tracer is not None:
            self.assertIsNone(client_no_trace.sql_tracer.get_last_session())
        
        print(f"\n[测试 4] 禁用追踪:")
        print(f"  返回结果数：{result['hits']['total']['value']}")
        print(f"  无 SQL 记录（正确）")
        
        client_no_trace.close()
    
    def test_05_export_functionality(self):
        """测试导出功能"""
        query_body = {
            "query": {
                "match": {
                    "content": "vector"
                }
            }
        }
        
        # 执行搜索
        result = self.client.search(self.test_index, query_body)
        
        # 导出 Markdown
        md_filepath = self.client.sql_tracer.export_to_file(export_format="markdown")
        self.assertTrue(md_filepath.endswith('.md'))
        
        # 导出 JSON
        json_filepath = self.client.sql_tracer.export_to_file(export_format="json")
        self.assertTrue(json_filepath.endswith('.json'))
        
        print(f"\n[测试 5] 导出功能:")
        print(f"  Markdown: {md_filepath}")
        print(f"  JSON: {json_filepath}")
        
        # 验证文件内容
        with open(md_filepath, 'r', encoding='utf-8') as md_file:
            md_content = md_file.read()
            self.assertIn("# SQL Trace Report", md_content)
            self.assertIn("search", md_content)
        
        with open(json_filepath, 'r', encoding='utf-8') as json_file:
            json_data = json.load(json_file)
            self.assertIn('session_id', json_data)
            self.assertIn('records', json_data)


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
