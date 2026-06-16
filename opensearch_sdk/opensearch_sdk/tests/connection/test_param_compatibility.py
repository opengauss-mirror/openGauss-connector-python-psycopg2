"""
测试连接池参数兼容性

验证 Opensearch兼容接口支持多种参数命名风格：
1. Opensearch 原生参数：pool_min_conn, pool_max_conn
2. OpenSearch 兼容参数：pool_maxsize
3. psycopg2 原生参数：minconn, maxconn
"""

import unittest
from unittest.mock import patch, MagicMock
from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestConnectionPoolParameterCompatibility(unittest.TestCase):
    """测试连接池参数兼容性"""

    def setUp(self):
        """每个测试前重置 mock"""
        self.mock_connection = MagicMock()
        self.mock_connection.connect = MagicMock()
        self.mock_connection.close = MagicMock()

    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_opengauss_native_params(self, mock_connection_class):
        """测试 Opensearch 原生参数"""
        mock_connection_class.return_value = self.mock_connection
        
        client = OpenGauss(
            hosts=[{"host": "localhost", "port": 5432}],
            database="testdb",
            user="testuser",
            password="testpass",
            pool_min_conn=10,
            pool_max_conn=50
        )
        
        # 验证 OpenGaussConnection 被正确调用
        mock_connection_class.assert_called_once()
        call_kwargs = mock_connection_class.call_args[1]
        
        self.assertEqual(call_kwargs['pool_min_conn'], 10)
        self.assertEqual(call_kwargs['pool_max_conn'], 50)
        
        client.close()

    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_opensearch_compatible_params(self, mock_connection_class):
        """测试 OpenSearch 兼容参数（pool_maxsize）"""
        mock_connection_class.return_value = self.mock_connection
        
        client = OpenGauss(
            hosts=[{"host": "localhost", "port": 5432}],
            database="testdb",
            user="testuser",
            password="testpass",
            pool_maxsize=30  # OpenSearch 参数
        )
        
        # 验证参数被正确映射
        mock_connection_class.assert_called_once()
        call_kwargs = mock_connection_class.call_args[1]
        
        # pool_maxsize 应该映射到 pool_max_conn
        self.assertEqual(call_kwargs['pool_max_conn'], 30)
        # pool_min_conn 使用默认值
        self.assertEqual(call_kwargs['pool_min_conn'], 5)
        
        client.close()

    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_psycopg2_native_params(self, mock_connection_class):
        """测试 psycopg2 原生参数（minconn/maxconn）"""
        mock_connection_class.return_value = self.mock_connection
        
        client = OpenGauss(
            hosts=[{"host": "localhost", "port": 5432}],
            database="testdb",
            user="testuser",
            password="testpass",
            minconn=8,   # psycopg2 参数
            maxconn=40   # psycopg2 参数
        )
        
        # 验证参数被正确映射
        mock_connection_class.assert_called_once()
        call_kwargs = mock_connection_class.call_args[1]
        
        # minconn/maxconn 应该映射到 pool_min_conn/pool_max_conn
        self.assertEqual(call_kwargs['pool_min_conn'], 8)
        self.assertEqual(call_kwargs['pool_max_conn'], 40)
        
        client.close()

    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_parameter_priority(self, mock_connection_class):
        """测试参数优先级：Opensearch > OpenSearch > psycopg2"""
        mock_connection_class.return_value = self.mock_connection
        
        # 同时提供多种参数，Opensearch 原生参数应该优先
        client = OpenGauss(
            hosts=[{"host": "localhost", "port": 5432}],
            database="testdb",
            user="testuser",
            password="testpass",
            pool_min_conn=10,  # Opensearch 原生（最高优先级）
            pool_max_conn=50,  # Opensearch 原生（最高优先级）
            pool_maxsize=30,   # OpenSearch（较低优先级，应被忽略）
            minconn=8,         # psycopg2（最低优先级，应被忽略）
            maxconn=40         # psycopg2（最低优先级，应被忽略）
        )
        
        # 验证使用了 Opensearch 原生参数
        mock_connection_class.assert_called_once()
        call_kwargs = mock_connection_class.call_args[1]
        
        self.assertEqual(call_kwargs['pool_min_conn'], 10)  # 使用 pool_min_conn
        self.assertEqual(call_kwargs['pool_max_conn'], 50)  # 使用 pool_max_conn
        
        client.close()

    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_default_values(self, mock_connection_class):
        """测试默认值"""
        mock_connection_class.return_value = self.mock_connection
        
        # 不提供任何连接池参数
        client = OpenGauss(
            hosts=[{"host": "localhost", "port": 5432}],
            database="testdb",
            user="testuser",
            password="testpass"
        )
        
        # 验证使用默认值
        mock_connection_class.assert_called_once()
        call_kwargs = mock_connection_class.call_args[1]
        
        self.assertEqual(call_kwargs['pool_min_conn'], 5)   # 默认值
        self.assertEqual(call_kwargs['pool_max_conn'], 20)  # 默认值
        
        client.close()

    @patch('opensearch_sdk.client.base.OpenGaussConnection')
    def test_mixed_params_opensearch_and_psycopg2(self, mock_connection_class):
        """测试混合使用 OpenSearch 和 psycopg2 参数"""
        mock_connection_class.return_value = self.mock_connection
        
        # 只提供部分参数
        client = OpenGauss(
            hosts=[{"host": "localhost", "port": 5432}],
            database="testdb",
            user="testuser",
            password="testpass",
            pool_maxsize=25,  # OpenSearch 参数（设置 max）
            minconn=7         # psycopg2 参数（设置 min）
        )
        
        # 验证参数被正确映射
        mock_connection_class.assert_called_once()
        call_kwargs = mock_connection_class.call_args[1]
        
        self.assertEqual(call_kwargs['pool_min_conn'], 7)   # 来自 minconn
        self.assertEqual(call_kwargs['pool_max_conn'], 25)  # 来自 pool_maxsize
        
        client.close()


if __name__ == '__main__':
    unittest.main()
