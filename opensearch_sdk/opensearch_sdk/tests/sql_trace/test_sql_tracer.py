import unittest
import time
import threading
from unittest.mock import Mock, MagicMock
from datetime import datetime

import sys
import os
from pathlib import Path

# 添加项目根目录到路径以便导入
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from opensearch_sdk.client.sql_tracer import (
    SQLTraceRecord,
    SQLTraceSession,
    SQLTracer,
    trace_context,
    get_global_tracer,
    set_global_tracer
)


class TestSQLTraceRecord(unittest.TestCase):
    """测试 SQLTraceRecord 数据类"""
    
    def test_basic_creation(self):
        """测试基本创建"""
        record = SQLTraceRecord(
            sql="SELECT * FROM users",
            params=("test",),
            context="test_query"
        )
        
        self.assertEqual(record.sql, "SELECT * FROM users")
        self.assertEqual(record.params, ("test",))
        self.assertEqual(record.context, "test_query")
        self.assertEqual(record.result_count, 0)
        self.assertIsNone(record.error)
    
    def test_record_to_dict(self):
        """测试 SQLTraceRecord 转换为字典格式"""
        record = SQLTraceRecord(
            sql="SELECT * FROM users WHERE id = %s",
            params=(123,),
            duration_ms=15.5,
            result_count=1,
            context="query"
        )
        
        data = record.to_dict()
        
        self.assertIn('sql', data)
        self.assertIn('params', data)
        self.assertIn('duration_ms', data)
        self.assertEqual(data['sql'], "SELECT * FROM users WHERE id = %s")
        self.assertEqual(data['params'], (123,))
        self.assertAlmostEqual(data['duration_ms'], 15.5, places=1)
    
    def test_param_masking(self):
        """测试参数脱敏"""
        # 不脱敏
        record = SQLTraceRecord(
            sql="INSERT INTO users (password) VALUES (%s)",
            params=("secret123",)
        )
        
        masked = record._get_masked_params(mask_sensitive=True)
        self.assertEqual(masked, ('***MASKED***',))
        
        # 关闭脱敏
        unmasked = record._get_masked_params(mask_sensitive=False)
        self.assertEqual(unmasked, ('secret123',))
    
    def test_sensitive_keyword_detection(self):
        """测试敏感关键词检测"""
        sensitive_cases = [
            ("password", "secret123"),
            ("api_key", "key789"),
            ("token", "token000"),
            ("secret_key", "secret")
        ]
        
        for keyword, value in sensitive_cases:
            record = SQLTraceRecord(
                sql=f"INSERT INTO config ({keyword}) VALUES (%s)",
                params=(value,)
            )
            
            masked = record._get_masked_params(mask_sensitive=True)
            self.assertEqual(masked[0], '***MASKED***', 
                           f"Failed to mask {keyword}")


class TestSQLTraceSession(unittest.TestCase):
    """测试 SQLTraceSession 会话类"""
    
    def test_session_creation(self):
        """测试会话创建"""
        session = SQLTraceSession(
            session_id="test_123",
            operation="search",
            index_name="my_index"
        )
        
        self.assertEqual(session.session_id, "test_123")
        self.assertEqual(session.operation, "search")
        self.assertEqual(session.index_name, "my_index")
        self.assertEqual(len(session.records), 0)
        self.assertEqual(session.total_duration_ms, 0)
    
    def test_add_record(self):
        """测试添加记录"""
        session = SQLTraceSession(
            session_id="test_123",
            operation="search"
        )
        
        record1 = SQLTraceRecord(sql="SELECT 1", duration_ms=5.0)
        record2 = SQLTraceRecord(sql="SELECT 2", duration_ms=10.0)
        
        session.add_record(record1)
        session.add_record(record2)
        
        self.assertEqual(len(session.records), 2)
        self.assertEqual(session.total_duration_ms, 15.0)
    
    def test_session_to_dict(self):
        """测试 SQLTraceSession 转换为字典"""
        session = SQLTraceSession(
            session_id="test_123",
            operation="create",
            index_name="test_table"
        )
        
        session.add_record(SQLTraceRecord(
            sql="CREATE TABLE test",
            duration_ms=20.0,
            result_count=0
        ))
        
        data = session.to_dict()
        
        self.assertEqual(data['session_id'], 'test_123')
        self.assertEqual(data['operation'], 'create')
        self.assertEqual(data['index_name'], 'test_table')
        self.assertEqual(data['record_count'], 1)
        self.assertIn('records', data)
    
    def test_get_summary(self):
        """测试获取摘要"""
        session = SQLTraceSession(
            session_id="abc123",
            operation="search",
            index_name="my_index"
        )
        
        summary = session.get_summary()
        
        self.assertIn("abc123", summary)
        self.assertIn("search", summary)
        self.assertIn("my_index", summary)
        self.assertIn("SQL Count: 0", summary)


class TestSQLTracer(unittest.TestCase):
    """测试 SQLTracer 核心类"""
    
    def setUp(self):
        """每个测试前的准备工作"""
        self.tracer = SQLTracer(
            enabled=True,
            mask_sensitive_params=True,
            max_sample_rows=10
        )
    
    def tearDown(self):
        """每个测试后的清理工作"""
        self.tracer.clear_history()
    
    def test_tracer_creation(self):
        """测试追踪器创建"""
        self.assertTrue(self.tracer.enabled)
        self.assertTrue(self.tracer.mask_sensitive_params)
        self.assertEqual(self.tracer.max_sample_rows, 10)
    
    def test_disabled_tracer(self):
        """测试禁用状态的追踪器"""
        disabled_tracer = SQLTracer(enabled=False)
        
        with disabled_tracer.trace_session("search", "test") as session:
            self.assertIsNone(session)
    
    def test_trace_session_context_manager(self):
        """测试会话上下文管理器"""
        with self.tracer.trace_session("search", "test_index") as session:
            self.assertIsNotNone(session)
            self.assertEqual(session.operation, "search")
            self.assertEqual(session.index_name, "test_index")
        
        # 会话结束后应该保存到历史
        self.assertEqual(len(self.tracer.get_sessions()), 1)
    
    def test_record_execution(self):
        """测试记录 SQL 执行"""
        mock_cursor = Mock()
        mock_cursor.rowcount = 5
        
        with self.tracer.trace_session("test", "test_table") as session:
            record = self.tracer.record_execution(
                cursor=mock_cursor,
                sql="SELECT * FROM test",
                params=(123,),
                context="main_query"
            )
            
            self.assertIsNotNone(record)
            self.assertEqual(record.sql, "SELECT * FROM test")
            self.assertEqual(record.result_count, 5)
            # [WARN] 不再自动采样，sampled_results 应该为空
            self.assertEqual(len(record.sampled_results), 0)
    
    def test_record_error(self):
        """测试记录错误"""
        error = Exception("Database connection failed")
        
        with self.tracer.trace_session("test", "test_table") as session:
            record = self.tracer.record_error(
                sql="INVALID SQL",
                error=error,
                context="error_test"
            )
            
            self.assertIsNotNone(record)
            self.assertEqual(record.error, "Database connection failed")
            self.assertEqual(record.context, "error_test")
    
    def test_get_last_session(self):
        """测试获取最后一次会话"""
        with self.tracer.trace_session("op1", "idx1"):
            pass
        
        with self.tracer.trace_session("op2", "idx2"):
            pass
        
        last_session = self.tracer.get_last_session()
        
        self.assertEqual(last_session.operation, "op2")
        self.assertEqual(last_session.index_name, "idx2")
    
    def test_session_history_limit(self):
        """测试会话历史限制"""
        # 创建 15 个会话（超过默认的 10 限制）
        for i in range(15):
            with self.tracer.trace_session(f"op{i}", f"idx{i}"):
                pass
        
        sessions = self.tracer.get_sessions()
        self.assertEqual(len(sessions), 10)  # 应该只保留最近 10 个
    
    def test_clear_history(self):
        """测试清空历史"""
        for i in range(5):
            with self.tracer.trace_session(f"op{i}", f"idx{i}"):
                pass
        
        self.tracer.clear_history()
        self.assertEqual(len(self.tracer.get_sessions()), 0)
    
    def test_export_to_markdown(self):
        """测试导出为 Markdown"""
        with self.tracer.trace_session("search", "test_index") as session:
            mock_cursor = Mock()
            mock_cursor.rowcount = 3
            mock_cursor.fetchmany.return_value = [('row1',), ('row2',)]
            self.tracer.record_execution(
                cursor=mock_cursor,
                sql="SELECT * FROM test",
                context="query"
            )
        
        filepath = self.tracer.export_to_file(export_format="markdown")
        
        # 检查文件扩展名
        self.assertTrue(filepath.endswith('.md') or '.md' in filepath)
        
        # 读取文件检查内容
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn("# SQL Trace Report", content)
            self.assertIn("search", content)
            self.assertIn("test_index", content)
    
    def test_export_to_json(self):
        """测试导出为 JSON"""
        with self.tracer.trace_session("create", "test_table") as session:
            mock_cursor = Mock()
            mock_cursor.rowcount = 0
            mock_cursor.fetchmany.return_value = []
            self.tracer.record_execution(
                cursor=mock_cursor,
                sql="CREATE TABLE test",
                context="ddl"
            )
        
        filepath = self.tracer.export_to_file(export_format="json")
        
        self.assertTrue(filepath.endswith('.json') or '.json' in filepath)
        
        # 读取文件检查内容
        with open(filepath, 'r', encoding='utf-8') as f:
            import json
            data = json.load(f)
            self.assertIn('session_id', data)
            self.assertIn('operation', data)
            self.assertEqual(data['operation'], 'create')


class TestTraceContext(unittest.TestCase):
    """测试独立的 trace_context 函数"""
    
    def test_standalone_context_manager(self):
        """测试独立的上下文管理器"""
        tracer = SQLTracer(enabled=True)
        
        with trace_context("test_op", "test_idx", tracer=tracer) as session:
            self.assertIsNotNone(session)
            self.assertEqual(session.operation, "test_op")
        
        self.assertEqual(len(tracer.get_sessions()), 1)
    
    def test_context_without_tracer(self):
        """测试没有指定追踪器时的行为"""
        # 没有设置全局追踪器
        with trace_context("test", "idx") as session:
            self.assertIsNone(session)


class TestGlobalTracer(unittest.TestCase):
    """测试全局追踪器功能"""
    
    def tearDown(self):
        """清理全局状态"""
        set_global_tracer(None)
    
    def test_set_and_get_global_tracer(self):
        """测试设置和获取全局追踪器"""
        tracer = SQLTracer(enabled=True)
        set_global_tracer(tracer)
        
        retrieved = get_global_tracer()
        self.assertEqual(tracer, retrieved)
    
    def test_context_with_global_tracer(self):
        """测试使用全局追踪器的上下文"""
        tracer = SQLTracer(enabled=True)
        set_global_tracer(tracer)
        
        with trace_context("test", "idx") as session:
            self.assertIsNotNone(session)
        
        self.assertEqual(len(tracer.get_sessions()), 1)


class TestThreadSafety(unittest.TestCase):
    """测试线程安全性"""
    
    def test_concurrent_sessions(self):
        """测试并发会话隔离"""
        tracer = SQLTracer(enabled=True)
        results = {}
        
        def worker(worker_id):
            with tracer.trace_session(f"op{worker_id}", f"idx{worker_id}") as session:
                time.sleep(0.01)  # 模拟一些延迟
                results[worker_id] = session.session_id
        
        # 启动多个线程
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        # 等待所有线程完成
        for t in threads:
            t.join()
        
        # 检查每个线程的会话是否独立
        self.assertEqual(len(results), 5)
        sessions = tracer.get_sessions()
        self.assertEqual(len(sessions), 5)
        
        # 验证会话 ID 各不相同
        session_ids = [s.session_id for s in sessions]
        self.assertEqual(len(set(session_ids)), 5)


if __name__ == '__main__':
    unittest.main()
