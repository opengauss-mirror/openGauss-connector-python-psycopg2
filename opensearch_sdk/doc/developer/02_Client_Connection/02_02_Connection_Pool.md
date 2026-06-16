# 连接管理与连接池

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

### commit() 与 rollback() - 事务管理 在**连接池模式**下（默认），直接调用 `commit()` 或 `rollback()` **会抛出 `RuntimeError`**！

**原因**：
- 连接池模式下，每次 `execute()` 可能使用不同的连接
- 在连接 A 上开始的事务，不能在连接 B 上提交

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

## 子客户端访问

Opensearch 客户端提供以下内置属性：

| 属性 | 类型 | 说明 |
|:---|:---|:---|
| `client.indices` | `IndicesClient` | 索引管理客户端 |
| `client.cat` | `CatClient` | Cat API 客户端 |
| `client.multi` | `MultiRetrieverClient` | 多路检索客户端 |
| `client.connection` | `OpenGaussConnection` | 数据库底层连接对象 |

## 连接池模式详解

### 工作原理

Opensearch兼容接口使用 `psycopg2.pool.ThreadedConnectionPool` 实现线程安全的连接池。

### 关键特性

1. **线程安全**：基于 `ThreadedConnectionPool`，支持多线程并发访问
2. **自动重连**：检测连接失效并自动重建
3. **上下文管理器**：使用 `with` 语句自动归还连接，避免泄漏
4. **健康检查**：获取连接时自动验证连接状态

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
