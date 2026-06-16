#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BM25 搜索测试 - Match 查询调试

功能说明：
- 测试 match 查询是否使用 BM25 索引
- 验证 BM25 查询的行为

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.bm25_search.test_bm25_match_debug -v
    python opensearch_sdk/tests/bm25_search/test_bm25_match_debug.py
"""

import os
import sys
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from opensearch_sdk import OpenGauss
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestBM25MatchDebug(unittest.TestCase):
    """测试 match 查询是否使用 BM25 索引"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.db_config = load_db_config()
        cls.client = OpenGauss(
            hosts=[{'host': cls.db_config['host'], 'port': cls.db_config['port']}],
            database=cls.db_config['database'],
            user=cls.db_config['user'],
            password=cls.db_config['password']
        )
        cls.test_index = 'test_bm25_match'
        
        # 清理旧索引
        if cls.client.indices.exists(index=cls.test_index):
            cls.client.indices.delete(index=cls.test_index)
        
        # 创建测试索引
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"}
                }
            }
        }
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 创建 BM25 索引
        from opensearch_sdk.retrieval import IndexConfig, IndexType
        
        # [FIX] 使用新的连接管理模式
        with cls.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                # 先删除可能存在的旧 BM25 索引
                try:
                    drop_sql = "DROP INDEX IF EXISTS idx_title_bm25"
                    cursor.execute(drop_sql)
                    conn.commit()
                except:
                    pass
                
                index_config = IndexConfig(
                    name="idx_title_bm25",
                    column="title",
                    index_type=IndexType.BM25,
                    parallel_workers=4
                )
                pre_sql = index_config.get_pre_create_sql(cls.test_index)
                if pre_sql:
                    cursor.execute(pre_sql)
                sql = index_config.to_sql(cls.test_index)
                cursor.execute(sql)
                conn.commit()
            finally:
                cursor.close()
        
        # 插入测试数据
        test_docs = [
            {"id": "1", "body": {"title": "Python 编程", "content": "Python 是一种编程语言"}},
            {"id": "2", "body": {"title": "Java 编程", "content": "Java 也是一种编程语言"}},
            {"id": "3", "body": {"title": "Python vs Java", "content": "比较 Python 和 Java"}}
        ]
        for doc in test_docs:
            cls.client.index(index=cls.test_index, id=doc['id'], body=doc['body'])
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            # [FIX] 使用新的连接管理模式
            with cls.client.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                try:
                    # 删除 BM25 索引
                    drop_sql = "DROP INDEX IF EXISTS idx_title_bm25"
                    cursor.execute(drop_sql)
                    conn.commit()
                finally:
                    cursor.close()
            
            # 删除表
            cls.client.indices.delete(index=cls.test_index)
        finally:
            cls.client.close()
    
    def test_match_query_uses_bm25(self):
        """测试 match 查询使用 BM25 索引"""
        query = {
            "query": {
                "match": {
                    "title": "Python 编程"
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        # 应该返回包含"Python"的文档
        self.assertGreater(len(hits), 0)
        
        # 打印结果验证
        print(f"\n找到 {len(hits)} 个匹配:")
        for hit in hits:
            print(f"  - {hit['_id']}: {hit['_source']['title']}")

if __name__ == '__main__':
    unittest.main(verbosity=2)
