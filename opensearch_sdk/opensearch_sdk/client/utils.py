from typing import Any, Dict, List, Optional, Union
import re


# 全局配置：是否启用 Python 端参数校验
# True: 在 Python 端进行严格的参数校验（推荐用于开发环境）
# False: 仅做基础校验，依赖数据库层校验（推荐用于生产环境，减少重复校验开销）
ENABLE_PYTHON_VALIDATION = True


def set_validation_enabled(enabled: bool):
    """
    设置是否启用 Python 端参数校验
    
    :arg enabled: True 启用校验，False 禁用校验（依赖数据库层）
    """
    global ENABLE_PYTHON_VALIDATION
    ENABLE_PYTHON_VALIDATION = enabled


def get_validation_enabled() -> bool:
    """
    获取当前 Python 端参数校验的启用状态
    
    :return: True 表示启用，False 表示禁用
    """
    return ENABLE_PYTHON_VALIDATION


def _validate_identifier(identifier: str) -> str:
    """
    验证数据库标识符（表名、字段名等）是否合法
    只允许字母、数字、下划线，且必须以字母或下划线开头
    
    性能优化：
    - 当 ENABLE_PYTHON_VALIDATION=False 时，跳过正则检测，直接返回原字符串
    - 使用 inline 实现，避免额外的函数调用开销
    
    :param identifier: 待验证的标识符
    :return: 验证通过的标识符
    :raises ValueError: 如果标识符不合法
    """
    # 快速路径：禁用校验时直接返回，零开销
    if not ENABLE_PYTHON_VALIDATION:
        return identifier
    
    # 校验路径：正则检测
    if not identifier or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        raise ValueError(f"Invalid database identifier: {identifier}")
    return identifier


def _validate_identifiers(identifiers: List[str]) -> List[str]:
    """
    验证多个数据库标识符
    
    性能优化：
    - 当 ENABLE_PYTHON_VALIDATION=False 时，直接返回原列表
    - 使用 inline 实现，避免额外的函数调用开销
    
    :param identifiers: 待验证的标识符列表
    :return: 验证通过的标识符列表
    """
    # 快速路径：禁用校验时直接返回，零开销
    if not ENABLE_PYTHON_VALIDATION:
        return identifiers
    
    # 校验路径：逐个验证
    return [_validate_identifier(ident) for ident in identifiers]


class NamespacedClient:
    """
    Base class for all nested clients - a client that makes requests on behalf of
    a parent client to a specific namespace (e.g. indices, cluster, etc.)
    """

    def __init__(self, client: Any) -> None:
        """
        :arg client: instance of :class:`~opengauss_vector_sdk.client.Client` that is
            going to be used for making requests
        """
        self.client = client
        self.transport = client.transport


def _normalize_hosts(hosts: Optional[Union[str, List[Dict[str, Any]]]]) -> List[Dict[str, Any]]:
    """
    Normalize a list of hosts to a list of dictionaries with host/port keys.
    """
    if hosts is None:
        return [{"host": "localhost", "port": 5432}]

    if isinstance(hosts, str):
        hosts = [hosts]

    normalized_hosts = []
    for host in hosts:
        if isinstance(host, str):
            # Parse host string
            if "://" in host:
                # Remove scheme
                host = host.split("://", 1)[1]
            if "/" in host:
                # Remove path
                host = host.split("/", 1)[0]
            if "@" in host:
                # Remove auth part
                host = host.split("@", 1)[1]
            
            # Split host and port
            if ":" in host:
                host, port = host.split(":")
                port = int(port)
            else:
                port = 5432
            
            normalized_hosts.append({"host": host, "port": port})
        else:
            normalized_hosts.append(host)
    
    return normalized_hosts


def query_params(*params: str):
    """
    Decorator that pops the query params from kwargs and inserts the
    query string into the kwargs for the wrapped function.
    """
    def _wrapper(func: Any) -> Any:
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            params_dict = {}
            for p in params:
                if p in kwargs:
                    params_dict[p] = kwargs.pop(p)
            
            # Add params to the request
            if params_dict:
                kwargs.setdefault("params", {}).update(params_dict)
            
            return func(*args, **kwargs)
        return _wrapped
    return _wrapper


SKIP_IN_PATH = ("", None)


def _make_path(*parts: Any) -> str:
    """
    Create a path from parts.
    """
    return "/" + "/".join(str(p).strip("/") for p in parts if p not in SKIP_IN_PATH)


# ========== openGauss数据库字符标准化适配工具 ==========

def normalize_identifier(identifier: str, context: str = "field") -> str:
    """
    标准化标识符（字段名、索引名、参数名等）
    
    - 对于索引名（表名）：不允许包含点号（.），连字符（-）会被转换为下划线
    - 对于字段名：点号和连字符都会被转换为下划线
    
    Args:
        identifier: 原始标识符
        context: 上下文（用于错误/警告信息），如 "Index name", "Document field" 等
    
    Returns:
        标准化后的标识符
    
    Raises:
        ValueError: 当索引名包含点号时抛出
    
    Examples:
        >>> normalize_identifier("user-name", "Document field")
        'user_name'
        >>> normalize_identifier("my-index", "Index name")
        'my_index'
        >>> normalize_identifier("my.index", "Index name")  # [FAIL] 抛出 ValueError
        ValueError: Index name 'my.index' contains dots which are not allowed...
        >>> normalize_identifier("normal_field")
        'normal_field'
    """
    if not isinstance(identifier, str):
        return identifier
    
    # [OK] 特殊处理：索引名（表名）包含点号时抛出错误
    is_index_name = "index" in context.lower() and "name" in context.lower()
    
    if is_index_name and '.' in identifier:
        raise ValueError(
            f"{context} '{identifier}' contains dots which are not allowed in Opensearch. "
            f"Please use underscores instead: '{identifier.replace('.', '_')}'"
        )
    
    # [OK] 兼容 OpenSearch 的 keyword 子字段 (如 libId.keyword)
    # 如果以 .keyword 结尾，说明是精确匹配子字段，在 Opensearch 中通常直接对应原列名
    if identifier.endswith('.keyword'):
        identifier = identifier[:-len('.keyword')]
    
    # 对于字段名或其他标识符，将 . 和 - 都转换为 _
    normalized = identifier.replace('.', '_').replace('-', '_')
    
    if normalized != identifier:
        pass
    
    return normalized


def normalize_nested_path(path: str, context: str = "nested path") -> str:
    """
    标准化嵌套路径（如 "user.info.name" -> "user_info_name"）
    
    将路径中的每个部分分别进行标准化，然后用下划线连接
    
    Args:
        path: 嵌套路径字符串
        context: 上下文（用于警告信息）
    
    Returns:
        标准化后的路径
    
    Examples:
        >>> normalize_nested_path("user.info.name")
        'user_info_name'
        >>> normalize_nested_path("user-info.address")
        'user_info_address'
    """
    if not isinstance(path, str):
        return path
    
    parts = path.split('.')
    normalized_parts = [part.replace('-', '_') for part in parts]
    normalized = '_'.join(normalized_parts)
    
    if normalized != path:
        pass
    
    return normalized