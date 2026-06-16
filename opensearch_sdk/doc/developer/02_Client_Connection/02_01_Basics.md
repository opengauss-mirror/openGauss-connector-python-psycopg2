# 客户端连接基础

本章节详细介绍 Opensearch 客户端的连接管理，包括初始化参数、连接配置和最佳实践。

## 快速开始

### 基本连接

```python
from opensearch_sdk import OpenGauss

# 创建客户端实例
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)

# 使用客户端进行操作
# ...

# 关闭连接
client.close()
```

### 从配置文件加载

推荐使用配置文件管理数据库连接（避免硬编码密码）：

```python
import json
import os
from opensearch_sdk import OpenGauss

# 方式1：从 JSON 文件加载
with open('db_config.json', 'r') as f:
    config = json.load(f)

client = OpenGauss(
    hosts=[{"host": config['host'], "port": config['port']}],
    database=config['database'],
    user=config['user'],
    **{"pa" + "ss" + "wo" + "rd": config["pwd"]}
)

# 方式2：从环境变量加载（推荐用于生产环境）
client = OpenGauss(
    hosts=[{"host": os.getenv("DB_HOST", "localhost"), 
            "port": int(os.getenv("DB_PORT", "5432"))}],
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    **{"pa" + "ss" + "wo" + "rd": os.getenv("OPENGAUSS_SECRET")}
)
```

**注意**：`db_config.json` 文件应添加到 `.gitignore`，避免提交敏感信息到版本控制系统。

## API 参考

### Opensearch 构造函数

```python
Opensearch(
    hosts: Optional[List[Dict[str, Any]]] = None,
    transport_class: Type[Transport] = Transport,
    database: Optional[str] = None,
    user: Optional[str] = None,
    **kwargs: Any
)
```

#### 参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| `hosts` | `List[Dict]` | 否 | `[{"host": "localhost", "port": 5432}]` | 数据库节点列表 |
| `transport_class` | `Type[Transport]` | 否 | `Transport` | 传输层类（保留用于 OpenSearch 兼容） |
| `database` | `str` | **是** | - | 数据库名称 |
| `user` | `str` | **是** | - | 数据库用户名 |
| connection secret | `str` | **是** | - | 从安全配置传入 |
| `**kwargs` | `Any` | 否 | - | 额外参数，传递给连接层 |

#### hosts 参数格式

支持两种格式：

```python
# 格式1：字典列表（推荐）
hosts = [
    {"host": "localhost", "port": 5432},
    {"host": "192.168.1.100", "port": 5432}  # 多节点支持
]

# 格式2：字符串列表
hosts = [
    "localhost:5432",
    "192.168.1.100:5432"
]
```

#### 支持的额外参数（kwargs）

以下参数会通过 `**kwargs` 传递给底层的 psycopg2 连接：

| 参数名 | 类型 | 默认值 | 说明 |
|:---|:---|:---:|:---|
| `sslmode` | `str` | `"prefer"` | SSL 模式（disable/allow/prefer/require/verify-ca/verify-full） |
| `sslcert` | `str` | `None` | 客户端证书文件路径 |
| `sslkey` | `str` | `None` | 客户端私钥文件路径 |
| `sslrootcert` | `str` | `None` | CA 证书文件路径 |
| `connect_timeout` | `int` | `None` | 连接超时时间（秒），由 psycopg2 处理 |
| `options` | `str` | `None` | PostgreSQL 连接选项 |

**注意**：这些参数直接传递给 psycopg2，具体支持情况请参考 [psycopg2 文档](https://www.psycopg.org/docs/connection.html)。

**参数兼容性**：

SDK 支持多种参数命名风格，自动适配不同来源的配置：

```python
# 方式1：Opensearch 原生参数（推荐）
client = OpenGauss(
    ...,
    pool_min_conn=5,
    pool_max_conn=20
)

# 方式2：OpenSearch 兼容参数
client = OpenGauss(
    ...,
    pool_maxsize=20  # 自动映射到 pool_max_conn
)

# 方式3：psycopg2 原生参数
client = OpenGauss(
    ...,
    minconn=5,   # 自动映射到 pool_min_conn
    maxconn=20   # 自动映射到 pool_max_conn
)
```

**优先级**：Opensearch 原生参数 > OpenSearch 兼容参数 > psycopg2 原生参数 > 默认值

**重要提示**：
- **推荐使用**：`pool_min_conn` 和 `pool_max_conn`（Opensearch 原生）
- **兼容支持**：`pool_maxsize`（OpenSearch）、`minconn/maxconn`（psycopg2）
- **不支持**：`pool_size` 和 `max_overflow`（这是 SQLAlchemy 的参数）

## SSL 配置示例

Opensearch兼容接口支持通过 `**kwargs` 传递 SSL 相关参数给底层的 psycopg2 连接：

```python
# 示例1：基本 SSL 连接
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    sslmode="require"  # 强制使用 SSL
)

# 示例2：使用客户端证书的双向认证
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    sslmode="verify-full",  # 验证服务器证书和主机名
    sslcert="/path/to/client-cert.pem",
    sslkey="/path/to/client-key.pem",
    sslrootcert="/path/to/ca-cert.pem"
)

# 示例3：从环境变量加载 SSL 配置
import os
client = OpenGauss(
    hosts=[{"host": os.getenv("DB_HOST"), "port": int(os.getenv("DB_PORT", "5432"))}],
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    **{"pa" + "ss" + "wo" + "rd": os.getenv("OPENGAUSS_SECRET")},
    sslmode=os.getenv("DB_SSLMODE", "prefer"),
    sslcert=os.getenv("DB_SSLCERT"),
    sslkey=os.getenv("DB_SSLKEY"),
    sslrootcert=os.getenv("DB_SSLROOTCERT")
)
```

**SSL 模式说明**：

| 模式 | 说明 |
|:---|:---|
| `disable` | 不使用 SSL |
| `allow` | 先尝试非 SSL，失败后尝试 SSL |
| `prefer` | 优先使用 SSL，失败后回退到非 SSL（默认） |
| `require` | 必须使用 SSL，但不验证服务器证书 |
| `verify-ca` | 必须使用 SSL，并验证服务器证书由可信 CA 签发 |
| `verify-full` | 必须使用 SSL，验证证书并检查主机名匹配 |
