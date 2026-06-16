# SPDX-2.0-License-Identifier: Apache
#
# Opensearch兼容接口- Base Client Module
# 主类定义，通过 Mixin 组合实现文档操作和搜索功能
#
# -*- coding: utf-8 -*-

import logging
from typing import Any, Optional, Type, Dict, List

from opensearch_sdk.client.doc_utils import DocumentOpsMixin
from opensearch_sdk.client.search_ops import SearchOpsMixin
from opensearch_sdk.client.indices_client import IndicesClient
from opensearch_sdk.client.cat import CatClient
from opensearch_sdk.client.vector_client import MultiRetrieverClient
from opensearch_sdk.transport import Transport
from opensearch_sdk.connection.opengauss import OpenGaussConnection
from opensearch_sdk.client.constants import DEFAULT_DB_HOST, DEFAULT_DB_PORT
from opensearch_sdk.client.sql_tracer import SQLTracer

logger = logging.getLogger("opengauss")


class OpenGaussClient(DocumentOpsMixin, SearchOpsMixin):
    """
    Opensearch 客户端，与 OpenSearch 语法兼容。

    通过 Mixin 组合实现文档操作和搜索功能。
    """

    @staticmethod
    def _parse_host_info(hosts):
        host_info = hosts[0] if isinstance(hosts, list) and hosts else {
            "host": DEFAULT_DB_HOST,
            "port": DEFAULT_DB_PORT
        }
        if isinstance(host_info, dict):
            return host_info.get("host", DEFAULT_DB_HOST), host_info.get("port", DEFAULT_DB_PORT)
        host = host_info.split(":")[0] if ":" in host_info else host_info
        port = int(host_info.split(":")[1]) if ":" in host_info else DEFAULT_DB_PORT
        return host, port

    @staticmethod
    def _build_sql_tracer(
        enable_sql_trace: bool,
        sql_trace_mask_sensitive: bool,
        sql_trace_max_sample_rows: int,
        sql_trace_export_dir: Optional[str]
    ):
        if not enable_sql_trace:
            return None
        logger.info("SQL tracing enabled")
        return SQLTracer(
            enabled=True,
            mask_sensitive_params=sql_trace_mask_sensitive,
            max_sample_rows=sql_trace_max_sample_rows,
            export_dir=sql_trace_export_dir
        )

    @staticmethod
    def _extract_doc_ops_kwargs(kwargs, bulk_batch_size):
        doc_ops_kwargs = {}
        if 'enable_dynamic_inference' in kwargs:
            doc_ops_kwargs['enable_dynamic_inference'] = kwargs.pop('enable_dynamic_inference')

        if bulk_batch_size is None:
            from opensearch_sdk.client.constants import DEFAULT_BATCH_SIZE
            bulk_batch_size = DEFAULT_BATCH_SIZE
        doc_ops_kwargs['bulk_batch_size'] = bulk_batch_size
        return doc_ops_kwargs

    @staticmethod
    def _extract_pool_kwargs(kwargs):
        use_connection_pool = kwargs.pop('use_connection_pool', True)
        pool_min_conn = kwargs.pop('pool_min_conn', None)
        pool_max_conn = kwargs.pop('pool_max_conn', None)

        if pool_max_conn is None and 'pool_maxsize' in kwargs:
            pool_max_conn = kwargs.pop('pool_maxsize')
            logger.info("Using OpenSearch compatible parameter: pool_maxsize -> pool_max_conn")

        if pool_min_conn is None and 'minconn' in kwargs:
            pool_min_conn = kwargs.pop('minconn')
            logger.info("Using psycopg2 compatible parameter: minconn -> pool_min_conn")
        if pool_max_conn is None and 'maxconn' in kwargs:
            pool_max_conn = kwargs.pop('maxconn')
            logger.info("Using psycopg2 compatible parameter: maxconn -> pool_max_conn")

        return {
            'use_connection_pool': use_connection_pool,
            'pool_min_conn': 5 if pool_min_conn is None else pool_min_conn,
            'pool_max_conn': 20 if pool_max_conn is None else pool_max_conn,
        }

    def __init__(
        self,
        hosts: Optional[List[Dict[str, Any]]] = None,
        transport_class: Type[Transport] = Transport,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        enable_sql_trace: bool = False,
        sql_trace_mask_sensitive: bool = True,
        sql_trace_max_sample_rows: int = 10,
        sql_trace_export_dir: Optional[str] = None,
        bulk_batch_size: int = None,
        **kwargs: Any
    ) -> None:
        """
        初始化 Opensearch 客户端

        :arg hosts: 连接主机列表
        :arg transport_class: 传输层类
        :arg database: 数据库名称
        :arg user: 用户名
        :arg password: 密码
        :arg enable_sql_trace: 是否启用 SQL 追踪（默认 False）
        :arg sql_trace_mask_sensitive: 是否脱敏敏感参数（默认 True）
        :arg sql_trace_max_sample_rows: 最大采样行数（默认 10）
        :arg sql_trace_export_dir: SQL 日志导出目录（默认 tmp/sql/exports）
        :arg bulk_batch_size: Bulk 批量操作大小（默认 100）
        :arg kwargs: 额外参数
        """
        # 不需要调用 super().__init__()，因为 Mixin 没有 __init__

        # 初始化 Transport（用于兼容性）
        self.transport = transport_class(hosts, **kwargs) if hosts else None

        host, port = self._parse_host_info(hosts)

        # 初始化 SQL 追踪器
        self.sql_tracer = self._build_sql_tracer(
            enable_sql_trace,
            sql_trace_mask_sensitive,
            sql_trace_max_sample_rows,
            sql_trace_export_dir
        )

        # 提取 DocumentOpsMixin 的参数（避免传递给连接层）
        doc_ops_kwargs = self._extract_doc_ops_kwargs(kwargs, bulk_batch_size)

        # 提取连接池参数 - 支持多种命名风格
        # 优先级：Opensearch原生 > OpenSearch兼容 > psycopg2原生 > 默认值
        pool_kwargs = self._extract_pool_kwargs(kwargs)

        # 创建 Opensearch 连接
        self.connection = OpenGaussConnection(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            sql_tracer=self.sql_tracer,
            **pool_kwargs,
            **kwargs
        )

        # 建立连接
        self.connection.connect()

        # 子客户端初始化
        self.indices = IndicesClient(self)
        self.cat = CatClient(self)
        self.multi = MultiRetrieverClient(self)

        # DocumentOpsMixin 初始化（在连接之后）
        self._init_document_ops(**doc_ops_kwargs)

    def get_connection(self):
        """
        获取数据库连接（用于 Retriever 模式兼容）
        """
        return self.connection

    def return_connection(self, conn):
        """
        归还连接到池（池模式有效，单连接模式无操作）
        如果 conn 是 OpenGaussConnection，则释放其从连接池借出的连接。
        """
        if hasattr(conn, '_release_borrowed_connection'):
            conn._release_borrowed_connection()

    def __repr__(self) -> Any:
        try:
            cons: Any = self.transport.hosts
            if len(cons) > 5:
                cons = cons[:5] + ["..."]
            return f"<{self.__class__.__name__}({cons})>"
        except AttributeError:
            # transport 可能未初始化，使用备用表示
            return f"<{self.__class__.__name__} at {hex(id(self))}>"

    def close(self) -> None:
        """
        关闭数据库连接和游标
        """
        self.connection.close()

    def commit(self) -> None:
        """
        提交当前事务
        """
        self.connection.commit()

    def rollback(self) -> None:
        """
        回滚当前事务
        """
        self.connection.rollback()

    def ping(self) -> bool:
        """
        检查数据库连接是否正常

        与 OpenSearch SDK 的 ping() 方法保持一致，用于健康检查。

        :return: True 如果连接正常，False 否则

        使用示例::

            client = OpenGauss(...)
            if client.ping():
                print("数据库连接正常")
            else:
                print("数据库连接异常")
        """
        try:
            # [FIX] 使用 get_connection_for_operation() 确保正确管理连接
            with self.connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
            return True
        except Exception:
            return False


# 导出
__all__ = ['OpenGaussClient', 'CatClient']
