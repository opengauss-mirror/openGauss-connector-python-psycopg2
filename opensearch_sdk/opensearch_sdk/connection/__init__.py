# SPDX-License-Identifier: Apache-2.0
#
# This file contains code derived from opensearch-py.
# Original source: https://github.com/opensearch-project/opensearch-py
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
#
# Modifications Copyright OpenSearch Contributors. See
# GitHub history for details.
#
# Modifications Copyright 2026 openGauss Contributors
#
#  Licensed to Elasticsearch B.V. under one or more contributor
#  license agreements. See the NOTICE file distributed with
#  this work for additional information regarding copyright
#  ownership. Elasticsearch B.V. licenses this file to you under
#  the Apache License, Version 2.0 (the "License"); you may
#  not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
# 	http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an
#  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  KIND, either express or implied.  See the License for the
#  specific language governing permissions and limitations
#  under the License.

from typing import Any, Dict, Optional

class Connection:
    """
    Base class for all connections.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: Optional[int] = None,
        use_ssl: bool = False,
        url_prefix: str = "",
        timeout: int = 10,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        """
        :arg host: hostname of the node (default: localhost)
        :arg port: port to use (integer, default: 5432)
        :arg use_ssl: use ssl for the connection if `True`
        :arg url_prefix: optional url prefix for elasticsearch
        :arg timeout: default timeout in seconds (float, default: 10)
        :arg headers: default headers (dict, default: None)
        :arg kwargs: additional arguments subclasses might accept
        """
        if port is None:
            port = 5432

        # Work-around if the implementing class doesn't
        # define the headers property before calling super().__init__()
        if not hasattr(self, "headers"):
            self.headers = {}

        headers = headers or {}
        for key in headers:
            self.headers[key.lower()] = headers[key]

        self.headers.setdefault("content-type", "application/json")
        self.headers.setdefault("user-agent", self._get_default_user_agent())

        self.use_ssl = use_ssl
        self.scheme = "https" if use_ssl else "http"
        self.hostname = host
        self.port = port
        if ":" in host:  # IPv6
            self.host = f"{self.scheme}://[{host}]"
        else:
            self.host = f"{self.scheme}://{host}"
        if self.port is not None:
            self.host += f":{self.port}"
        if url_prefix:
            url_prefix = "/" + url_prefix.strip("/")
        self.url_prefix = url_prefix
        self.timeout = timeout

    @staticmethod
    def _get_default_user_agent() -> str:
        """
        Return the default user agent string
        """
        return "opengauss-vector-python-client/1.0.0"
