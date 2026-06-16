from typing import Any, Optional, Type

from opensearch_sdk.client.utils import _normalize_hosts, _validate_identifier, _validate_identifiers
from opensearch_sdk.transport import Transport
from opensearch_sdk.client.vector_client import MultiRetrieverClient
from opensearch_sdk.client.base import OpenGaussClient, CatClient
from opensearch_sdk.client.doc_utils import DocumentOpsMixin
from opensearch_sdk.client.search_ops import SearchOpsMixin
from opensearch_sdk.client.query_builder import QueryBuilder


class Client:
    """
    A generic Opensearch Vector client.
    """

    def __init__(
        self,
        hosts: Optional[str] = None,
        transport_class: Type[Transport] = Transport,
        **kwargs: Any
    ) -> None:
        """
        Opensearch Vector 客户端初始化

        参数说明:
        - hosts: 节点列表或单个节点，支持字典或 ``host[:port]`` 字符串格式
        - transport_class: Transport 子类，用于自定义传输层
        - kwargs: 传递给 Transport 和 Connection 的额外参数
        """
        self.transport = transport_class(_normalize_hosts(hosts), **kwargs)


__all__ = [
    'Client',
    'OpenGaussClient', 
    'CatClient',
    'DocumentOpsMixin',
    'SearchOpsMixin',
    'QueryBuilder',
    '_validate_identifier',
    '_validate_identifiers'
]
