#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试 Opensearch兼容接口的 ping() 方法
使用 mock 模拟数据库连接
"""

import unittest
from unittest.mock import Mock, patch
from opensearch_sdk.client.base import OpenGaussClient


class TestPingMethod(unittest.TestCase):
    """测试 ping 方法"""
    
    def setUp(self):
        """设置测试环境"""
        # Mock 连接对象
        self.mock_connection = Mock()
        self.mock_cursor = Mock()

        # 配置 mock 行为
        self.mock_connection.execute.return_value = self.mock_cursor
        self.mock_cursor.fetchone.return_value = (1,)

    @staticmethod
    def _mock_context(mock_conn_instance):
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_conn_instance)
        mock_context.__exit__ = Mock(return_value=False)
        return mock_context

    def _client_with_connection(self, mock_connection_class, mock_conn_instance):
        mock_conn_instance.get_connection_for_operation = Mock(
            return_value=self._mock_context(mock_conn_instance)
        )
        mock_connection_class.return_value = mock_conn_instance

        client = OpenGaussClient(
            hosts=[{'host': 'localhost', 'port': 5432}],
            database='test',
            user='user',
            password='password'
        )
        client.connection = mock_conn_instance
        return client

    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_ping_returns_true_on_success(self, mock_connection_class):
        """测试正常连接时 ping 返回 True"""
        # 配置 mock
        mock_conn_instance = Mock()
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn_instance.cursor = Mock(return_value=mock_cursor)
        client = self._client_with_connection(mock_connection_class, mock_conn_instance)
        
        # 测试 ping
        result = client.ping()
        
        # 验证
        self.assertTrue(result)
        mock_cursor.execute.assert_called_with("SELECT 1")
        mock_cursor.fetchone.assert_called_once()
        mock_cursor.close.assert_called_once()
    
    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_ping_returns_false_on_exception(self, mock_connection_class):
        """测试连接异常时 ping 返回 False"""
        # 配置 mock 抛出异常
        mock_conn_instance = Mock()
        mock_cursor = Mock()
        mock_cursor.execute.side_effect = Exception("Connection failed")
        mock_conn_instance.cursor = Mock(return_value=mock_cursor)
        client = self._client_with_connection(mock_connection_class, mock_conn_instance)
        
        # 测试 ping
        result = client.ping()
        
        # 验证
        self.assertFalse(result)
        mock_cursor.execute.assert_called_with("SELECT 1")
    
    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_ping_method_exists(self, mock_connection_class):
        """测试 ping 方法存在"""
        mock_conn_instance = Mock()
        mock_connection_class.return_value = mock_conn_instance
        
        client = OpenGaussClient(
            hosts=[{'host': 'localhost', 'port': 5432}],
            database='test',
            user='user',
            password='password'
        )
        
        # 验证 ping 方法存在且可调用
        self.assertTrue(hasattr(client, 'ping'))
        self.assertTrue(callable(getattr(client, 'ping')))


if __name__ == '__main__':
    unittest.main()
