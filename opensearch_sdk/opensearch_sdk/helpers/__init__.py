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

from typing import Any, Dict


class Index:
    """
    Simple Index class that can be used to create and manage indices.
    """

    def __init__(self, name: str, using: Any = None) -> None:
        """
        :arg name: name of the index
        :arg using: client connection to use
        """
        self.name = name
        self._using = using
        self._settings: Dict[str, Any] = {}
        self._mapping: Dict[str, Any] = {}

    def settings(self, **kwargs: Any) -> "Index":
        """
        Associate settings with the index.
        """
        self._settings.update(kwargs)
        return self

    def mapping(self, properties: Dict[str, Any]) -> "Index":
        """
        Associate a mapping with the index.
        """
        self._mapping = {"properties": properties}
        return self

    def create(self) -> Any:
        """
        Create the index in Opensearch Vector.
        """
        if self._using is None:
            raise ValueError("No client connection provided")

        body = {}
        if self._settings:
            body["settings"] = self._settings
        if self._mapping:
            body["mappings"] = self._mapping

        return self._using.indices.create(index=self.name, body=body)

    def delete(self) -> Any:
        """
        Delete the index.
        """
        if self._using is None:
            raise ValueError("No client connection provided")

        return self._using.indices.delete(index=self.name)

    def exists(self) -> bool:
        """
        Check if the index exists.
        """
        if self._using is None:
            raise ValueError("No client connection provided")

        return self._using.indices.exists(index=self.name)