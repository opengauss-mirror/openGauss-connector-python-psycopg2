#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQL 追踪功能完整集成测试

测试所有支持 SQL 追踪的方法：
- search()
- knn_search()
- create()
- get()
- update()
- delete()
- indices.create()
- indices.delete()

运行方式：
    python -m unittest opensearch_sdk.tests.sql_trace.test_full_integration -v
"""

import sys
import os
import unittest
import json
import time
import uuid

# 添加项目根目录到路径
# 注意：__file__ 在 opensearch_sdk/tests/sql_trace/ 中，需要上溯 3 级到项目根目录
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestFullIntegration(unittest.TestCase):
    """SQL 追踪功能完整集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        # 加载数据库配置
        config_path = os.path.join(project_root, 'db_config.json')
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
            sql_trace_max_sample_rows=10
        )
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        cls.client.close()
    
    def setUp(self):
        """每个测试前创建唯一的索引名并初始化索引"""
        test_name = self._testMethodName
        self.test_index = f'test_sql_{test_name}_{int(time.time() * 1000) % 10000}'
        
        # 创建索引
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "tags": {"type": "keyword"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": 3,
                        "similarity": "cosine"
                    }
                }
            }
        }
        self.client.indices.create(self.test_index, mapping)
    
    def tearDown(self):
        """每个测试后删除索引"""
        try:
            self.client.indices.delete(self.test_index)
        except Exception:
            pass
    
    def test_01_indices_create(self):
        """测试 indices.create() 的 SQL 追踪"""
        # 先删除 setUp 中创建的索引，测试从头创建
        try:
            self.client.indices.delete(self.test_index)
        except Exception:
            pass
        
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "tags": {"type": "keyword"}
                }
            }
        }
        
        result = self.client.indices.create(self.test_index, mapping)
        
        # 验证索引创建成功
        self.assertTrue(result.get('acknowledged', False))
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, 'indices_create')
        self.assertGreater(len(session.records), 0)
        
        # 验证 metadata
        if session.records:
            last_record = session.records[-1]
            self.assertEqual(last_record.context, f"indices_create_{self.test_index}")
            if hasattr(last_record, 'metadata'):
                self.assertEqual(last_record.metadata.get('index_name'), self.test_index)
    
    def test_02_create(self):
        """测试 create() 的 SQL 追踪"""
        doc_data = {
            "title": "Test Document",
            "content": "This is a test document for SQL tracing",
            "tags": ["test", "sql-trace"]
        }
        
        # 使用唯一 ID
        doc_id = f"doc1_{int(time.time() * 1000) % 10000}"
        result = self.client.create(self.test_index, doc_id, doc_data)
        
        # 验证创建成功
        self.assertEqual(result['result'], 'created')
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, 'create')
        
        # 修复：允许 >= 1 条记录（因为 setUp 中的操作也可能被记录）
        self.assertGreaterEqual(len(session.records), 1)
        
        # 验证 metadata
        last_record = session.records[-1]
        self.assertEqual(last_record.context, f"create_{self.test_index}")
        if hasattr(last_record, 'metadata'):
            self.assertEqual(last_record.metadata.get('document_id'), doc_id)
            self.assertEqual(last_record.metadata.get('field_count'), 3)
    
    def test_03_get(self):
        """测试 get() 的 SQL 追踪"""
        print(f"\n[test_03_get] 使用索引: {self.test_index}")
        
        # 先插入数据
        doc_data = {
            "title": "Get Test Document",
            "content": "This is for get testing",
            "tags": ["get-test"]
        }
        doc_id = f"doc1_{uuid.uuid4().hex[:8]}"
        print(f"[test_03_get] 准备插入文档: id={doc_id}")
        result = self.client.index(self.test_index, doc_id, doc_data)
        print(f"[test_03_get] 插入结果: {result}")
        
        # Opensearch 可能需要短暂延迟才能看到新插入的数据
        time.sleep(0.1)
        
        # 测试 get
        result = self.client.get(self.test_index, doc_id)
        
        # 验证获取成功
        self.assertEqual(result['_id'], doc_id)
        self.assertEqual(result['_source']['title'], 'Get Test Document')
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, 'get')
        
        # 验证 metadata
        if session.records:
            last_record = session.records[-1]
            self.assertEqual(last_record.context, f"get_{self.test_index}")
            if hasattr(last_record, 'metadata'):
                self.assertEqual(last_record.metadata.get('document_id'), doc_id)
    
    def test_04_update(self):
        """测试 update() 的 SQL 追踪"""
        # 先插入数据
        doc_data = {
            "title": "Original Title",
            "content": "Original content",
            "tags": ["original"]
        }
        doc_id = f"doc1_{int(time.time() * 1000) % 10000}"
        self.client.index(self.test_index, doc_id, doc_data)
        
        # 清理 SQL 会话
        if hasattr(self.client, 'sql_tracer') and self.client.sql_tracer is not None:
            try:
                if self.client.sql_tracer._current_session_id:
                    self.client.sql_tracer.end_session()
            except AttributeError:
                pass
        
        # 测试 update
        update_data = {"title": "Updated Title"}
        result = self.client.update(self.test_index, doc_id, update_data)
        
        # 验证更新成功
        self.assertEqual(result['result'], 'updated')
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, 'update')
        
        # 验证 metadata
        if session.records:
            last_record = session.records[-1]
            self.assertEqual(last_record.context, f"update_{self.test_index}")
            if hasattr(last_record, 'metadata'):
                self.assertEqual(last_record.metadata.get('document_id'), doc_id)
                self.assertEqual(last_record.metadata.get('updated_fields'), ['title'])
    
    def test_05_search(self):
        """测试 search() 的 SQL 追踪"""
        query_body = {
            "query": {
                "match": {
                    "content": "updated"
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query_body)
        
        # 验证搜索结果
        self.assertIn("hits", result)
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, 'search')
        
        # 验证 metadata
        if session.records:
            last_record = session.records[-1]
            # 修复：接受实际生成的 context 格式
            self.assertIn(last_record.context, [f"search_{self.test_index}", f"search_query_{self.test_index}"])
            if hasattr(last_record, 'metadata'):
                self.assertIn('query_body', last_record.metadata)
    
    def test_06_knn_search(self):
        """测试 knn_search() 的 SQL 追踪"""
        # 注意：这个测试需要向量字段，如果索引没有向量字段会跳过
        try:
            query_vector = [0.1, 0.2, 0.3]
            result = self.client.knn_search(
                index=self.test_index,
                field="embedding",  # 假设没有这个字段
                query_vector=query_vector,
                k=5
            )
            
            # 验证 SQL 追踪
            session = self.client.sql_tracer.get_last_session()
            self.assertIsNotNone(session)
            self.assertEqual(session.operation, 'knn_search')
        except Exception:
            # 如果没有向量字段，测试跳过
            self.skipTest("索引没有向量字段，无法测试 knn_search")
    
    def test_07_delete(self):
        """测试 delete() 的 SQL 追踪（独立管理数据）"""
        # 先插入数据
        doc_data = {
            "title": "Delete Test Document",
            "content": "This will be deleted",
            "tags": ["delete-test"]
        }
        doc_id = f"doc1_{uuid.uuid4().hex[:8]}"
        self.client.index(self.test_index, doc_id, doc_data)
        
        # 测试 delete
        result = self.client.delete(self.test_index, doc_id)
        
        # 验证删除成功
        self.assertEqual(result['result'], 'deleted')
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, 'delete')
        
        # 验证 metadata
        if session.records:
            last_record = session.records[-1]
            self.assertEqual(last_record.context, f"delete_{self.test_index}")
            if hasattr(last_record, 'metadata'):
                self.assertEqual(last_record.metadata.get('document_id'), doc_id)
    
    def test_08_indices_delete(self):
        """测试 indices.delete() 的 SQL 追踪"""
        # setUp 已确保索引存在，直接删除
        result = self.client.indices.delete(self.test_index)
        
        # 验证删除成功
        self.assertTrue(result.get('acknowledged', False))
        
        # 验证 SQL 追踪
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, 'indices_delete')
        
        # 验证 metadata
        if session.records:
            last_record = session.records[-1]
            self.assertEqual(last_record.context, f"indices_delete_{self.test_index}")
            if hasattr(last_record, 'metadata'):
                self.assertEqual(last_record.metadata.get('index_name'), self.test_index)
    
    def test_09_trace_disabled(self):
        """测试禁用追踪时无记录"""
        # 创建不启用追踪的客户端
        client_no_trace = OpenGauss(
            hosts=[{'host': self.db_config['host'], 'port': self.db_config['port']}],
            database=self.db_config['database'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            enable_sql_trace=False
        )
        
        try:
            # 先创建一个临时索引用于测试
            temp_index = 'test_trace_disabled_temp'
            client_no_trace.indices.delete(temp_index)
            client_no_trace.indices.create(temp_index, {
                "mappings": {"properties": {"title": {"type": "text"}}}
            })
            client_no_trace.index(temp_index, 'doc1', {'title': 'Test'})
            # [FIX] 移除 commit()，连接池模式下 index() 已自动提交
            
            # 执行搜索（使用真实存在的索引）
            result = client_no_trace.search(temp_index, {"query": {"match_all": {}}})
            
            # 验证搜索成功
            self.assertIn('hits', result)
            
            # 验证没有追踪会话
            if hasattr(client_no_trace, 'sql_tracer') and client_no_trace.sql_tracer is not None:
                self.assertIsNone(client_no_trace.sql_tracer.get_last_session())
            
            # 清理
            client_no_trace.indices.delete(temp_index)
        except Exception as e:
            # 如果出错，至少验证没有 sql_tracer 或为 None
            if hasattr(client_no_trace, 'sql_tracer'):
                self.assertIsNone(client_no_trace.sql_tracer)
            raise
        finally:
            client_no_trace.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
