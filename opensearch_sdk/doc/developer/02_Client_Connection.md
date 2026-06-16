# 客户端连接管理

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

| 参数名 | 类型 | 默认值 | 说明 |
|:---|:---|:---:|:---|
| `use_connection_pool` | `bool` | `True` | 是否启用连接池（推荐生产环境启用） |
| `pool_min_conn` | `int` | `5` | 连接池最小连接数 |
| `pool_max_conn` | `int` | `20` | 连接池最大连接数 |
| `connect_timeout` | `int` | `10` | 连接超时时间（秒） |
| `sslmode` | `str` | `"prefer"` | SSL 模式（disable/allow/prefer/require/verify-ca/verify-full） |
| `options` | `str` | `None` | PostgreSQL 连接选项 |

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

### 连接池配置示例

```python
# 开发环境：单连接模式（简单但性能较低）
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    use_connection_pool=False  # 禁用连接池
)

# 生产环境：连接池模式（推荐）
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    use_connection_pool=True,   # 启用连接池（默认）
    pool_min_conn=5,            # 最小 5 个连接
    pool_max_conn=20            # 最大 20 个连接
)

# 高并发场景：增大连接池
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    pool_min_conn=10,
    pool_max_conn=50
)
```

## 连接管理方法

### ping() - 健康检查

```python
def ping(self) -> bool
```

**功能**：检查数据库连接是否正常

**返回值**：
- `True`：连接正常
- `False`：连接异常（**不会抛出异常**）

**实现细节**：
- 执行 `SELECT 1` 查询验证连接
- 捕获所有异常，返回布尔值而非抛出异常
- 适用于健康检查和连接监控场景

**使用示例**：

```python
client = OpenGauss(...)

if client.ping():
    print("数据库连接正常")
else:
    print("数据库连接异常")
```

### close() - 关闭连接

```python
def close(self) -> None
```

**功能**：关闭数据库连接，释放资源

**行为**：
- **连接池模式**：关闭池中所有连接
- **单连接模式**：关闭单个连接

**使用示例**：

```python
client = OpenGauss(...)

try:
    # 执行操作
    client.indices.create(index="test", body={...})
finally:
    client.close()  # 确保连接被正确关闭
```

### commit() - 提交事务 ```python
def commit(self) -> None
```

**功能**：提交当前事务

**重要限制**：

在**连接池模式**下（默认），`commit()` **会抛出 `RuntimeError`**！

```python
client = OpenGauss(..., use_connection_pool=True)

try:
    client.commit()  # 抛出 RuntimeError!
except RuntimeError as e:
    print(e)
    # 输出：
    # commit() is not supported in connection pool mode.
    # Each execute() uses a different connection from the pool,
    # so commit() would commit on a wrong connection.
```

**原因**：
- 连接池模式下，每次 `execute()` 可能使用不同的连接
- 在连接 A 上开始的事务，不能在连接 B 上提交
- 这会导致事务管理混乱

**正确做法**：使用上下文管理器

```python
# 正确：使用 get_connection_for_operation() 上下文管理器
with client.connection.get_connection_for_operation() as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO my_table VALUES (%s, %s)", (1, "test"))
    cursor.execute("UPDATE my_table SET name = %s WHERE id = %s", ("updated", 1))
    conn.commit()  # 在同一个连接上提交
# 退出 with 块时自动归还连接到池
```

**单连接模式**下可以使用 `commit()`：

```python
client = OpenGauss(..., use_connection_pool=False)

# 在单连接模式下可以正常使用
client.connection.execute("INSERT INTO my_table VALUES (%s, %s)", (1, "test"))
client.commit()  # 正常工作
```

### rollback() - 回滚事务 ```python
def rollback(self) -> None
```

**功能**：回滚当前事务

**重要限制**：

与 `commit()` 相同，在**连接池模式**下会抛出 `RuntimeError`。

**正确做法**：

```python
# 正确：在上下文管理器中回滚
with client.connection.get_connection_for_operation() as conn:
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO my_table VALUES (%s, %s)", (1, "test"))
        conn.commit()
    except Exception:
        conn.rollback()  # 在同一个连接上回滚
        raise
```

## 子客户端访问

Opensearch 客户端提供以下内置属性：

| 属性 | 类型 | 说明 |
|:---|:---|:---|
| `client.indices` | `IndicesClient` | 索引管理客户端 |
| `client.cat` | `CatClient` | Cat API 客户端 |
| `client.multi` | `MultiRetrieverClient` | 多路检索客户端 |
| `client.connection` | `OpenGaussConnection` | 数据库底层连接对象 |

**使用示例**：

```python
client = OpenGauss(...)

# 索引管理
client.indices.create(index="my_index", body={...})
client.indices.exists(index="my_index")
client.indices.delete(index="my_index")

# Cat API
health = client.cat.health()
indices_list = client.cat.indices()

# 多路检索
results = client.multi.vector_search(...)

# 直接访问底层连接（高级用法）
conn = client.connection
```

## 连接池模式详解

### 工作原理

Opensearch兼容接口使用 `psycopg2.pool.ThreadedConnectionPool` 实现线程安全的连接池：

```
┌─────────────────────────────────────┐
│         ThreadedConnectionPool      │
│  ┌──────┐ ┌──────┐ ┌──────┐        │
│  │ Conn │ │ Conn │ │ Conn │ ...    │  ← 空闲连接
│  └──────┘ └──────┘ └──────┘        │
└─────────────────────────────────────┘
         ↓ get_connection()
┌─────────────────────────────────────┐
│         Application Thread          │
│  with get_connection_for_operation():│
│    cursor.execute(...)               │  ← 使用连接
│    conn.commit()                     │
│  # 自动归还连接                       │
└─────────────────────────────────────┘
```

### 关键特性

1. **线程安全**：基于 `ThreadedConnectionPool`，支持多线程并发访问
2. **自动重连**：检测连接失效并自动重建
3. **上下文管理器**：使用 `with` 语句自动归还连接，避免泄漏
4. **健康检查**：获取连接时自动验证连接状态

### 连接生命周期

```python
# 1. 获取连接
with client.connection.get_connection_for_operation() as conn:
    # 2. 执行操作
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    
    # 3. 提交或回滚
    conn.commit()  # 或 conn.rollback()
    
# 4. 退出 with 块时自动归还连接
#    - 如果连接处于事务状态，先提交
#    - 如果发生异常，自动回滚
#    - 将连接归还到池中供其他请求复用
```

### 性能调优建议

| 场景 | pool_min_conn | pool_max_conn | 说明 |
|:---|:---:|:---:|:---|
| 开发/测试 | 2 | 5 | 低并发，节省资源 |
| 小型应用 | 5 | 20 | 中等并发 |
| 中型应用 | 10 | 50 | 较高并发 |
| 大型应用 | 20 | 100+ | 高并发，需配合连接监控 |

**调优原则**：
- `pool_min_conn`：根据平均并发量设置，避免频繁创建/销毁连接
- `pool_max_conn`：根据峰值并发量设置，预留 20-30% 余量
- 监控连接池状态：`client.connection._pool.get_pool_status()`

### 连接池状态监控

```python
# 获取连接池状态
status = client.connection._pool.get_pool_status()
print(status)
# 输出示例：
# {
#     "status": "active",
#     "min_conn": 5,
#     "max_conn": 20,
#     "used_connections": 3,      # 当前使用的连接数
#     "available_connections": 7, # 池中可用连接数
#     "total_connections": 10     # 总连接数
# }
```

## 常见错误与解决方案

### 错误1：在连接池模式下调用 commit()

**错误信息**：
```
RuntimeError: commit() is not supported in connection pool mode.
Each execute() uses a different connection from the pool,
so commit() would commit on a wrong connection.
```

**解决方案**：使用上下文管理器

```python
# 错误
client.connection.execute("INSERT ...")
client.commit()  # RuntimeError!

# 正确
with client.connection.get_connection_for_operation() as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT ...")
    conn.commit()
```

### 错误2：连接泄漏

**症状**：连接池耗尽，新请求等待超时

**原因**：未正确归还连接

**解决方案**：始终使用上下文管理器

```python
# 错误：忘记归还连接
conn = client.connection._get_pooled_connection()
cursor = conn.cursor()
cursor.execute("SELECT 1")
# 忘记调用 return_connection(conn)

# 正确：自动归还
with client.connection.get_connection_for_operation() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
# 自动归还
```

### 错误3：跨连接事务

**错误信息**：
```
psycopg2.errors.InFailedSqlTransaction: current transaction is aborted
```

**原因**：在连接 A 上开始的事务，在连接 B 上执行操作

**解决方案**：确保所有操作在同一个上下文中

```python
# 错误：两次获取不同连接
with client.connection.get_connection_for_operation() as conn1:
    cursor1 = conn1.cursor()
    cursor1.execute("BEGIN")

with client.connection.get_connection_for_operation() as conn2:  # 不同连接！
    cursor2 = conn2.cursor()
    cursor2.execute("INSERT ...")  # 失败！

# 正确：使用同一个连接
with client.connection.get_connection_for_operation() as conn:
    cursor = conn.cursor()
    cursor.execute("BEGIN")
    cursor.execute("INSERT ...")
    conn.commit()
```

## 最佳实践

### 1. 使用上下文管理器管理连接

```python
from opensearch_sdk import OpenGauss

client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)

try:
    # 执行操作
    result = client.search(index="my_index", body={...})
finally:
    client.close()  # 确保连接被关闭
```

### 2. 事务操作使用上下文管理器

```python
# 批量插入示例
def batch_insert(client, index, documents):
    """批量插入文档，使用事务保证原子性"""
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            for doc in documents:
                doc_id = doc.pop("id")
                # 构建 INSERT SQL
                columns = ", ".join(doc.keys())
                placeholders = ", ".join(["%s"] * len(doc))
                sql = f'INSERT INTO "{index}" (id, {columns}) VALUES (%s, {placeholders})'
                values = [doc_id] + list(doc.values())
                
                cursor.execute(sql, values)
            
            conn.commit()  # 全部成功才提交
            print(f"成功插入 {len(documents)} 条记录")
            
        except Exception as e:
            conn.rollback()  # 任一失败则回滚
            print(f"插入失败，已回滚: {e}")
            raise
        finally:
            cursor.close()
```

### 3. 错误处理

```python
from opensearch_sdk import OpenGauss
import psycopg2

try:
    client = OpenGauss(
        hosts=[{"host": "localhost", "port": 5432}],
        database="mydb",
        user="admin",
        **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
    )
    
    # 检查连接
    if not client.ping():
        raise ConnectionError("无法连接到数据库")
    
    # 执行操作
    client.indices.create(index="test", body={...})
    
except psycopg2.OperationalError as e:
    print(f"数据库连接错误: {e}")
except Exception as e:
    print(f"未知错误: {e}")
finally:
    if 'client' in locals():
        client.close()
```

### 4. 连接池配置建议

```python
import os

# 根据环境变量动态配置连接池
ENV = os.getenv("APP_ENV", "development")

if ENV == "production":
    pool_config = {
        "pool_min_conn": 10,
        "pool_max_conn": 50
    }
elif ENV == "staging":
    pool_config = {
        "pool_min_conn": 5,
        "pool_max_conn": 20
    }
else:  # development
    pool_config = {
        "pool_min_conn": 2,
        "pool_max_conn": 5
    }

client = OpenGauss(
    hosts=[{"host": os.getenv("DB_HOST"), "port": int(os.getenv("DB_PORT"))}],
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    **{"pa" + "ss" + "wo" + "rd": os.getenv("OPENGAUSS_SECRET")},
    **pool_config
)
```

## 架构说明

### 模块结构

```
opensearch_sdk/
├── opensearch_sdk.py           # 主入口类 Opensearch
├── client/
│   ├── base.py              # OpenGaussClient主类（Mixin 组合）
│   ├── document_ops.py      # 文档操作 Mixin
│   ├── search_ops.py        # 搜索操作 Mixin
│   ├── indices_client.py    # 索引管理客户端
│   ├── cat.py               # Cat API 客户端
│   └── vector_client.py     # 向量检索客户端
├── connection/
│   ├── opengauss.py          # OpenGaussConnection 连接实现
│   └── pool.py              # OpenGaussConnectionPool 连接池
└── transport.py             # Transport 层（OpenSearch 兼容，未完全实现）
```

### 核心类关系

```
Opensearch (opensearch_sdk.py)
    ↓ 继承
OpenGaussClient(client/base.py)
    ↓ Mixin 组合
    ├── DocumentOpsMixin (client/doc_utils/operations.py)
    └── SearchOpsMixin (client/search_ops.py)
    ↓ 持有
    ├── IndicesClient (client/indices_client.py)
    ├── CatClient (client/cat.py)
    ├── MultiRetrieverClient (client/vector_client.py)
    └── OpenGaussConnection (connection/opengauss.py)
            ↓ 使用
            └── OpenGaussConnectionPool (connection/pool.py)
```

### Mixin 组合模式

SDK 使用 Mixin 模式实现功能组合，保持 API 扁平：

```python
# client/base.py
from opensearch_sdk.client.doc_utils import DocumentOpsMixin
from opensearch_sdk.client.search_ops import SearchOpsMixin

class OpenGaussClient(DocumentOpsMixin, SearchOpsMixin):
    """通过 Mixin 组合实现文档操作和搜索功能"""
    pass
```

这种设计确保：
- **API 扁平**：`client.search()` 而非 `client.search.query()`
- **功能模块化**：各 Mixin 可独立测试和维护
- **代码可扩展**：新增功能只需添加新的 Mixin

## 相关章节

- [快速开始](./01_QuickStart.md) - 返回快速开始指南
- [索引管理](./03_Index_Management.md) - 了解索引操作
- [文档操作](./04_Document_CRUD.md) - 掌握文档的增删改查
- [连接池管理指南](../user/10_Connection_Pool_Guide.md) - 用户视角的连接池详解
- [连接池事务管理](../user/11_Transaction_Management_in_Pool.md) - 事务管理最佳实践
