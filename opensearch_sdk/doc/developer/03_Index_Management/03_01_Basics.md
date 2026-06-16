# 索引管理基础

本章节详细介绍 Opensearch兼容接口的索引管理操作，包括创建索引、删除索引和检查索引存在性。

## 模块信息

**源文件**: `opensearch_sdk/client/indices_client.py`  
**客户端类**: `IndicesClient`

**相关模块**:
- `opensearch_sdk/client/indices/helpers.py`: 映射验证和辅助函数
- `opensearch_sdk/client/indices/sql_generator.py`: SQL生成逻辑
- `opensearch_sdk/client/indices/operations.py`: 索引操作方法

## 概述

在 Opensearch兼容接口中，索引对应于数据库中的表。创建索引时需要定义完整的 mapping（schema）。

**核心设计理念**：
- **明确定义**：所有字段应在 properties 中预定义
- **动态扩展**：支持 dynamic_templates 和 enable_dynamic_inference 两种动态列机制
- **类型安全**：严格模式默认关闭动态推断，确保数据结构稳定

**详细说明**：请参阅 [Nested 结构与动态列](10_Nested_Dynamic.md)

## 重要架构特性

### 连接管理模式

**设计理念**：

Opensearch兼容接口采用现代化的连接管理模式，通过 `get_connection_for_operation()` 上下文管理器确保每次操作都获取独立的数据库连接。

**关键优势**：

1. **自动连接管理**：操作完成后自动归还连接到连接池
2. **元数据可见性**：新连接自动看到最新的表结构和索引元数据
3. **事务隔离**：每个操作在独立的事务中执行，避免交叉污染
4. **无需手动重连**：DDL 操作后不需要手动重连，新连接会立即感知变化

**代码示例**：

```python
# 创建索引后，新连接会自动看到索引，无需手动重连
client.indices.create(
    index="my_index",
    body={
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "content": {"type": "text"}
            }
        }
    }
)

# 直接查询，索引已就绪（新连接自动获取）
result = client.search("my_index", {"query": {"match": {"title": "test"}}})
```

**实现细节**：

SDK 内部使用以下方式管理连接：

```python
with self.client.connection.get_connection_for_operation() as conn:
    cursor = conn.cursor()
    try:
        cursor.execute(sql_query)
        conn.commit()  # DDL 操作立即提交
    finally:
        cursor.close()
# with 块退出时自动归还连接到连接池
```

## IndicesClient 访问

索引管理通过 `client.indices` 访问：

```python
from opensearch_sdk import OpenGauss

client = OpenGauss(...)
indices_client = client.indices
```

## 外部接口说明

### 1. 索引客户端访问

```python
from opensearch_sdk import OpenGauss

client = OpenGauss(...)

# 获取索引管理客户端
indices_client = client.indices
```

### 2. 外部调用接口

#### 2.1 创建索引接口

**函数签名**：
```python
def create(
    self,
    *,
    index: Any,
    body: Any = None,
    params: Any = None,
    headers: Any = None
) -> Any
```

**参数说明**：
- `index`: 索引名称（对应数据库表名）
- `body`: 索引配置字典，包含 mappings（字段映射）和 settings（索引设置）
- `params`: 额外查询参数字典（可选）
- `headers`: 额外请求头字典（可选）

```python
# 基础索引创建
client.indices.create(
    index="my_index",
    body={
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "category": {"type": "keyword"},
                "price": {"type": "float"}
            }
        }
    }
)

# 向量索引创建
client.indices.create(
    index="vector_index",
    body={
        "mappings": {
            "properties": {
                "content": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 768,
                    "similarity": "cosine",
                    "index_options": {
                        "m": 16,
                        "ef_construction": 64
                    }
                }
            }
        }
    }
)
```

#### 2.2 删除索引接口

**函数签名**：
```python
def delete(
    self,
    *,
    index: Any,
    params: Any = None,
    headers: Any = None
) -> Any
```

**参数说明**：
- `index`: 索引名称（支持逗号分隔的多个索引名）
- `params`: 额外查询参数字典（可选）
- `headers`: 额外请求头字典（可选）

```python
# 删除单个索引
client.indices.delete(index="my_index")

# 删除多个索引
client.indices.delete(index="index1,index2,index3")
```

#### 2.3 索引检查接口

**函数签名**：
```python
def exists(
    self,
    *,
    index: Any,
    params: Any = None,
    headers: Any = None
) -> bool
```

**参数说明**：
- `index`: 索引名称
- `params`: 额外查询参数字典（可选）
- `headers`: 额外请求头字典（可选）

```python
# 检查索引是否存在
exists = client.indices.exists(index="my_index")

# 获取所有索引名称
index_names = client.indices.get_all_index_names()
```
