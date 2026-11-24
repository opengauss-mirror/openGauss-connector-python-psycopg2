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

from typing import Any, Dict, List, Optional


class Transport:
    """
    Encapsulation of transport-related to logic. Handles instantiation of connections,
    keep-alive logic, threading, connection pooling, etc.
    """

    def __init__(
        self,
        hosts: List[Dict[str, Any]],
        **kwargs: Any
    ) -> None:
        """
        :arg hosts: list of dictionaries, each containing keyword arguments to
            create a `connection.Connection` instance
        :arg kwargs: any additional arguments will be passed on to the
            :class:`~opengauss_vector_sdk.Connection` instances.
        """
        self.hosts = hosts
        self.kwargs = kwargs
        self.connection_pool = None
        self.sniffing_task = None

    def close(self) -> None:
        """
        Explicitly closes connections
        """
        raise NotImplementedError("Transport.close() is not implemented")