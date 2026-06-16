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