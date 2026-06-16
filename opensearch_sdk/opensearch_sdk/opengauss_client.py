"""
Opensearch兼容接口
提供与 OpenSearch 兼容的 API 接口

主要模块：
- client/base: 主客户端类（opengausssdkClient）
- client/document_ops: 文档 CRUD 操作
- client/search_ops: 搜索操作
- client/query_builder: 查询构建器
- client/indices: 索引管理
- client/vector_client: 向量客户端

使用示例：
    from opensearch_sdk import OpenGauss
    
    # 建议从配置文件或环境变量加载密码
    client = OpenGauss(
        hosts=[{"host": "localhost", "port": 5432}],
        database="test",
        user="user",
        password=os.getenv("DB_PASSWORD")  # 或使用 config.get("password")
    )
    
    # 文档操作
    client.create("index", "id", {"field": "value"})
    client.search("index", {"query": {"match": {"field": "value"}}})
    client.knn_search("index", "embedding", [0.1, 0.2, 0.3])
"""

import logging
from typing import Any, Optional, Type, Dict, List

from opensearch_sdk.client import Client
from opensearch_sdk.client.base import OpenGaussClient as _OpenGaussClient
from opensearch_sdk.client.indices_client import IndicesClient
from opensearch_sdk.client.cat import CatClient
from opensearch_sdk.transport import Transport
from opensearch_sdk.connection.opengauss import OpenGaussConnection
from opensearch_sdk.client.vector_client import MultiRetrieverClient
from opensearch_sdk.client.utils import _validate_identifier, _validate_identifiers
from opensearch_sdk.client.query_builder import QueryBuilder

logger = logging.getLogger("opengauss")


class OpenGauss(_OpenGaussClient):
    """
    Opensearch 客户端，与 OpenSearch 语法兼容。
    
    这是 SDK 的主入口类，提供了与 OpenSearch 兼容的 API 接口。
    文档操作和搜索功能通过 Mixin 组合实现。
    
    使用示例::
    
        client = OpenGauss(
            hosts=[{"host": "localhost", "port": 5432}],
            database="your_database",
            user="your_username",
            password=os.getenv("DB_PASSWORD")  # 建议使用环境变量
        )
    """
    
    def __init__(
        self,
        hosts: Optional[List[Dict[str, Any]]] = None,
        transport_class: Type[Transport] = Transport,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """
        初始化 Opensearch 客户端
        
        :arg hosts: 连接主机列表
        :arg transport_class: 传输层类
        :arg database: 数据库名称
        :arg user: 用户名
        :arg password: 密码
        :arg kwargs: 额外参数（可能包含 host, port 等）
        """
        # 处理 kwargs 中可能的 host/port 参数（兼容 db_config 解包）
        if hosts is None and ('host' in kwargs or 'port' in kwargs):
            # 如果 hosts 未指定但 kwargs 中有 host/port，构造 hosts
            host = kwargs.pop('host', 'localhost')
            port = kwargs.pop('port', 5432)
            hosts = [{'host': host, 'port': port}]
        
        # 如果 database/user/password 未指定但从 kwargs 中获取
        if database is None and 'database' in kwargs:
            database = kwargs.pop('database')
        if user is None and 'user' in kwargs:
            user = kwargs.pop('user')
        if password is None and 'password' in kwargs:
            password = kwargs.pop('password')
        
        super().__init__(
            hosts=hosts,
            transport_class=transport_class,
            database=database,
            user=user,
            password=password,
            **kwargs
        )
    
    def __repr__(self) -> Any:
        try:
            cons: Any = self.transport.hosts
            if len(cons) > 5:
                cons = cons[:5] + ["..."]
            return f"<{self.__class__.__name__}({cons})>"
        except Exception:
            return super().__repr__()


# 导出公共 API
__all__ = [
    "OpenGauss",
    "Client",
    "_validate_identifier",
    "QueryBuilder",
    "CatClient"
]
