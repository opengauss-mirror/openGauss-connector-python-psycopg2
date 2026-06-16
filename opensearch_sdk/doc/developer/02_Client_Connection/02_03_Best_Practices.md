# 最佳实践与架构说明

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
