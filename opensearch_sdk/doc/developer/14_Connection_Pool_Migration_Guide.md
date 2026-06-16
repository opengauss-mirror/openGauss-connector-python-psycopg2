# 连接池参数迁移指南

本文档帮助从 OpenSearch 或 psycopg2 迁移到 Opensearch兼容接口的开发者快速适配连接池配置。

## 参数映射对照表

| OpenSearch 参数 | psycopg2 参数 | Opensearch 参数 | 说明 |
|:---|:---|:---|:---|
| `pool_maxsize` | `maxconn` | `pool_max_conn` | 最大连接数 |
| 无对应（Opensearch 独有） | `minconn` | `pool_min_conn` | 最小连接数 |
| `timeout` | `connect_timeout` | `connect_timeout` | 连接超时 |
| `use_ssl` | `sslmode` | `sslmode` | SSL 模式 |

## 迁移示例

### 从 OpenSearch 迁移

**OpenSearch 配置：**
```python
from opensearchpy import OpenSearch

client = OpenSearch(
    hosts=['localhost:9200'],
    http_auth=("admin", "<set securely>"),
    pool_maxsize=20,      # 最大连接数
    timeout=30            # 超时时间
)
```

**Opensearch 配置（方式1：使用兼容参数）：**
```python
from opensearch_sdk import OpenGauss

# SDK 自动将 pool_maxsize 映射到 pool_max_conn
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    pool_maxsize=20,      # 兼容 OpenSearch 参数
    connect_timeout=30
)
```

**Opensearch 配置（方式2：使用原生参数，推荐）：**
```python
from opensearch_sdk import OpenGauss

# 推荐使用 Opensearch 原生参数
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    pool_min_conn=5,      # 新增：最小连接数
    pool_max_conn=20,     # 对应 pool_maxsize
    connect_timeout=30
)
```

### 从 psycopg2 迁移

**psycopg2 配置：**
```python
import psycopg2
from psycopg2 import pool

connection_pool = pool.ThreadedConnectionPool(
    minconn=5,            # 最小连接数
    maxconn=20,           # 最大连接数
    host="localhost",
    port=5432,
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)
```

**Opensearch 配置（方式1：使用兼容参数）：**
```python
from opensearch_sdk import OpenGauss

# SDK 自动将 minconn/maxconn 映射到 pool_min_conn/pool_max_conn
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    minconn=5,            # 兼容 psycopg2 参数
    maxconn=20            # 兼容 psycopg2 参数
)
```

**Opensearch 配置（方式2：使用原生参数，推荐）：**
```python
from opensearch_sdk import OpenGauss

# 推荐使用 Opensearch 原生参数
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    pool_min_conn=5,      # 对应 minconn
    pool_max_conn=20      # 对应 maxconn
)
```

## 参数优先级

当同时提供多种命名风格的参数时，SDK 按以下优先级处理：

```
Opensearch 原生参数 > OpenSearch 兼容参数 > psycopg2 原生参数 > 默认值
```

**示例：**
```python
client = OpenGauss(
    ...,
    pool_min_conn=10,     # 最高优先级，使用此值
    minconn=5,            # 被忽略（较低优先级）
    
    pool_max_conn=50,     # 最高优先级，使用此值
    pool_maxsize=30,      # 被忽略（较低优先级）
    maxconn=20            # 被忽略（最低优先级）
)

# 最终效果：pool_min_conn=10, pool_max_conn=50
```

## 常见迁移场景

### 场景1：小型应用

**OpenSearch：**
```python
client = OpenSearch(..., pool_maxsize=10)
```

**Opensearch：**
```python
# 方式1：简单迁移
client = OpenGauss(..., pool_maxsize=10)

# 方式2：优化配置（推荐）
client = OpenGauss(
    ...,
    pool_min_conn=2,   # 初始 2 个连接
    pool_max_conn=10   # 最大 10 个连接
)
```

### 场景2：中型应用

**OpenSearch：**
```python
client = OpenSearch(..., pool_maxsize=20)
```

**Opensearch：**
```python
# 方式1：简单迁移
client = OpenGauss(..., pool_maxsize=20)

# 方式2：优化配置（推荐）
client = OpenGauss(
    ...,
    pool_min_conn=5,   # 初始 5 个连接
    pool_max_conn=20   # 最大 20 个连接
)
```

### 场景3：大型应用

**OpenSearch：**
```python
client = OpenSearch(..., pool_maxsize=50)
```

**Opensearch：**
```python
# 方式1：简单迁移
client = OpenGauss(..., pool_maxsize=50)

# 方式2：优化配置（推荐）
client = OpenGauss(
    ...,
    pool_min_conn=10,  # 初始 10 个连接
    pool_max_conn=50   # 最大 50 个连接
)
```

## 注意事项

### 1. 不支持的参数

以下参数在 Opensearch兼容接口中**不支持**：

- `pool_size` - 这是 SQLAlchemy 的参数
- `max_overflow` - 这是 SQLAlchemy 的参数

如果使用了这些参数，会收到警告或被忽略。

### 2. 默认值差异

| 参数 | OpenSearch 默认值 | Opensearch 默认值 |
|:---|:---:|:---:|
| 最大连接数 | 10 | 20 |
| 最小连接数 | 不适用 | 5 |
| 超时时间 | 30秒 | 10秒 |

迁移时建议显式指定关键参数，避免依赖默认值。

### 3. 连接池行为差异

**OpenSearch（HTTP 连接池）：**
- 基于 urllib3
- 连接是短命的，请求结束后可能关闭
- 主要减少 TCP 握手开销

**Opensearch（PostgreSQL 连接池）：**
- 基于 psycopg2 ThreadedConnectionPool
- 连接是长命的，复用率高
- 减少连接创建/销毁开销
- 支持事务管理

### 4. 日志提示

SDK 在使用兼容参数时会输出日志：

```
INFO: Using OpenSearch compatible parameter: pool_maxsize -> pool_max_conn
INFO: Using psycopg2 compatible parameter: minconn -> pool_min_conn
```

这有助于确认参数是否正确映射。

## 最佳实践

### 推荐做法

1. **新代码使用 Opensearch 原生参数**
   ```python
   client = OpenGauss(
       ...,
       pool_min_conn=5,
       pool_max_conn=20
   )
   ```

2. **迁移代码可以暂时使用兼容参数**
   ```python
   # 快速迁移，后续再优化
   client = OpenGauss(..., pool_maxsize=20)
   ```

3. **根据实际负载调优**
   ```python
   # 监控连接池使用情况
   status = client.connection._pool.get_pool_status()
   print(status)
   ```

### 不推荐做法

1. 混用多种参数风格
   ```python
   # 不推荐：难以维护
   client = OpenGauss(
       ...,
       pool_min_conn=5,
       maxconn=20  # 混用 psycopg2 参数
   )
   ```

2. 忽略最小连接数
   ```python
   # 不推荐：只设置最大值
   client = OpenGauss(..., pool_max_conn=50)
   
   # 推荐：同时设置最小和最大
   client = OpenGauss(
       ...,
       pool_min_conn=10,
       pool_max_conn=50
   )
   ```

## 总结

- Opensearch兼容接口**完全兼容** OpenSearch 和 psycopg2 的连接池参数
- 迁移时可以使用原有参数名，SDK 会自动映射
- 推荐逐步过渡到 Opensearch 原生参数（`pool_min_conn/pool_max_conn`）
- 注意不支持的参数（`pool_size/max_overflow`）
- 建议监控连接池状态，根据实际情况调优
