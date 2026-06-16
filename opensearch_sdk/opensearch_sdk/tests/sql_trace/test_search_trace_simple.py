"""
SQL 追踪功能简单集成测试
用于快速验证 search() 方法的 SQL 追踪是否正常工作

注意：此测试需要真实数据库连接
"""

import unittest
import json
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestSearchSQLTrace(unittest.TestCase):
    """测试 search 方法的 SQL 追踪"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境（只执行一次）"""
        # 加载数据库配置
        config_path = project_root / 'db_config.json'
        with open(config_path, 'r', encoding='utf-8') as f:
            cls.db_config = json.load(f)
        
        # 创建带 SQL 追踪的客户端
        cls.client = OpenGauss(
            hosts=[{'host': cls.db_config['host'], 'port': cls.db_config['port']}],
            database=cls.db_config['database'],
            user=cls.db_config['user'],
            password=cls.db_config['password'],
            enable_sql_trace=True,
            sql_trace_mask_sensitive=True,
            sql_trace_max_sample_rows=5
        )
        
        cls.test_index = 'test_search_trace_simple'
        
        # 清理旧索引
        try:
            cls.client.indices.delete(cls.test_index)
        except Exception:
            pass
        
        # 创建测试索引并插入数据
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text", "analyzer": "ik_max_word"},
                    "content": {"type": "text", "analyzer": "ik_max_word"},
                    "category": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "publish_date": {"type": "date"}
                }
            }
        }
        cls.client.indices.create(cls.test_index, mapping)
        
        # 插入测试数据（注意：不要包含 id 字段，因为 create() 会单独处理）
        test_docs = [
            {"title": "Hello World", "content": "This is a test document", "category": "news", "status": "published", "publish_date": "2024-01-15"},
            {"title": "Important News", "content": "Breaking news today", "category": "news", "status": "published", "publish_date": "2024-02-20"},
            {"title": "Tech Update", "content": "Technology updates", "category": "tech", "status": "draft", "publish_date": "2024-03-10"},
        ]
        
        doc_ids = ["doc1", "doc2", "doc3"]
        for i, doc in enumerate(test_docs):
            cls.client.create(cls.test_index, doc_ids[i], doc)
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(cls.test_index)
        except Exception:
            pass
        cls.client.close()
    
    def setUp(self):
        """每个测试前清理追踪历史"""
        if hasattr(self.client, 'sql_tracer'):
            self.client.sql_tracer.clear_history()
    
    def test_search_with_trace_enabled(self):
        """测试启用追踪时的 search 方法"""
        # 执行搜索
        query_body = {
            "query": {
                "match": {
                    "content": "test"
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query_body)
        
        # 验证搜索结果
        self.assertIn('hits', result)
        
        # 验证有会话记录
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, "search")
        self.assertEqual(session.index_name, self.test_index)
        
        # 验证至少有一条 SQL 记录
        self.assertGreater(len(session.records), 0)
        
        # 验证 SQL 被正确记录（应该是完整的 SQL 字符串，不是 Composed 对象）
        last_record = session.records[-1]
        self.assertIsInstance(last_record.sql, str)
        self.assertIn("SELECT", last_record.sql.upper())
        self.assertEqual(last_record.context, "search_query_" + self.test_index)
        
        # 验证 metadata 包含查询体
        self.assertIn('query_body', last_record.metadata)
        self.assertEqual(last_record.metadata['query_body'], query_body)
    
    def test_search_without_trace(self):
        """测试未启用追踪时的 search 方法"""
        # 创建不启用追踪的客户端
        client_no_trace = OpenGauss(
            hosts=[{'host': self.db_config['host'], 'port': self.db_config['port']}],
            database=self.db_config['database'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            enable_sql_trace=False
        )
        
        try:
            query_body = {
                "query": {
                    "term": {"category": "news"}
                }
            }
            
            result = client_no_trace.search(self.test_index, query_body)
            
            # 验证有搜索结果
            self.assertIn('hits', result)
            
            # 验证没有追踪会话
            if hasattr(client_no_trace, 'sql_tracer') and client_no_trace.sql_tracer:
                self.assertIsNone(client_no_trace.sql_tracer.get_last_session())
        finally:
            client_no_trace.close()
    
    def test_search_complex_bool_query(self):
        """测试复杂 bool 查询的追踪"""
        complex_query = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"title": "News"}},
                        {"match": {"content": "today"}}
                    ],
                    "filter": [
                        {"term": {"status": "published"}},
                        {"range": {"publish_date": {"gte": "2024-01-01"}}}
                    ]
                }
            },
            "size": 20,
            "sort": [{"publish_date": "desc"}]
        }
        
        result = self.client.search(self.test_index, complex_query)
        
        # 验证搜索结果
        self.assertIn('hits', result)
        
        # 验证会话记录
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        
        # 应该有多个 SQL 记录（可能有预检查等）
        # 静默输出，只在失败时显示
        if len(session.records) == 0:
            print(f"\n警告：没有记录到 SQL")
    
    def test_search_error_handling(self):
        """测试错误情况下的追踪"""
        # 使用不存在的索引来触发错误
        query_body = {
            "query": {"match_all": {}}
        }
        
        # 应该抛出异常（索引不存在）
        with self.assertRaises(Exception):
            self.client.search("non_existent_index_12345", query_body)
        
        # 即使出错也应该有记录
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
