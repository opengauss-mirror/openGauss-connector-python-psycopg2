# Copyright (c) 2026 Huawei Technologies Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
