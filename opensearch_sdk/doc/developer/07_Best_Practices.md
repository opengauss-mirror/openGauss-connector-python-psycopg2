# 最佳实践

本章节汇总 Opensearch兼容接口的最佳实践和常见问题解决方案。

## 1. 连接管理

### 使用上下文管理器

```python
from opensearch_sdk import OpenGauss

# 推荐：使用 try-finally 确保连接关闭
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)

try:
    # 执行操作
    client.indices.create(index="test", body=mapping)
    client.index(index="test", id="1", body={})
finally:
    client.close()

# 避免：不关闭连接
client = OpenGauss(...)
client.index(...)  # 操作完成后连接未关闭
```

### 使用配置文件

```python
# 推荐：使用配置文件
import json
with open('config.json') as f:
    config = json.load(f)
client = OpenGauss(**config)

# 避免：硬编码配置
client = OpenGauss(hosts=[{"host": "192.168.1.100", "port": 5432}], ...)
```

---

## 2. 索引设计

### 预定义完整 Mapping

```python
# 推荐：创建索引时定义所有字段
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "content": {"type": "text"},
            "category": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "price": {"type": "float"},
            "created_at": {"type": "date"}
        }
    }
}
client.indices.create(index="products", body=mapping)

# 避免：期望动态添加字段
client.index(index="products", id="1", body={"new_field": "value"})
# 会报错：column "new_field" does not exist
```

### 使用 JSONB 存储动态数据

```python
# 需要存储灵活字段时
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "extra_data": {"type": "jsonb"}
        }
    }
}
client.indices.create(index="flexible", body=mapping)

# 存储动态数据
import json
client.index(
    index="flexible",
    id="doc1",
    body={
        "title": "Hello",
        "extra_data": json.dumps({"any_field": "any_value"})
    }
)
```

---

## 3. 文档操作

### 选择正确的方法

| 场景 | 推荐方法 | 原因 |
|:---|:---|:---|
| 不确定文档是否存在 | `index()` | 自动处理创建和更新 |
| 确保创建新文档 | `create()` | 存在时抛 409 错误 |
| 确保更新现有文档 | `update()` | 不存在时抛 404 错误 |
| 批量操作 | `bulk()` | 高性能批量处理 |

### 批量操作示例

```python
# 推荐：使用 bulk 进行批量操作
body = ""
for doc in documents:
    body += json.dumps({"index": {"_index": "my_index", "_id": doc["id"]}}) + "\n"
    body += json.dumps(doc) + "\n"

result = client.bulk(body=body)
```

---

## 4. 向量搜索

### 合理选择向量维度

```python
# 常用模型对应的维度
embedding_configs = {
    "text-embedding-ada-002": 1536,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "sentence-transformers": 384,  # 常用模型
}

embedding_config = {
    "type": "dense_vector",
    "dims": 1536,  # 根据使用的 embedding 模型选择
    "similarity": "cosine"
}
```

### 选择合适的相似度算法

| 场景 | 推荐算法 | 原因 |
|:---|:---|:---|
| 文本语义搜索 | cosine | 忽略向量长度，关注方向 |
| 推荐系统 | cosine 或 dot_product | 考虑或不考虑长度 |
| 图像/坐标 | l2_norm | 物理距离 |

---

## 5. 查询优化

### 使用 filter 而非 must

```python
# 推荐：filter 不计算相关性，性能更好
client.search(
    index="products",
    body={
        "query": {
            "bool": {
                "must": [{"match": {"title": "phone"}}],
                "filter": [{"term": {"category": "electronics"}}]
            }
        }
    }
)

# 避免：全部使用 must
client.search(
    index="products",
    body={
        "query": {
            "bool": {
                "must": [
                    {"match": {"title": "phone"}},
                    {"term": {"category": "electronics"}}
                ]
            }
        }
    }
)
```

### 指定返回字段

```python
# 推荐：只返回需要的字段
client.search(
    index="products",
    body={
"query": {"match_all": {}},
        "_source": ["title", "price"]  # 只返回这两个字段
    }
)
```

---

## 6. 错误处理

### 捕获特定异常

```python
try:
    client.create(index="my_index", id="doc1", body={})
except Exception as e:
    error_msg = str(e)
    if "409" in error_msg:
        print("文档已存在")
    elif "404" in error_msg:
        print("文档不存在")
    else:
        print(f"其他错误: {error_msg}")
```

### 验证索引存在性

```python
# 操作前检查索引是否存在
if client.indices.exists(index="my_index"):
    client.index(index="my_index", id="doc1", body={})
else:
    print("索引不存在，请先创建")
```

---

## 7. 性能建议

### 批量操作

```python
# 推荐：使用 bulk 批量操作
body = "\n".join([
    json.dumps({"index": {"_index": "my_index", "_id": str(i)}}) + "\n" +
    json.dumps({"field": f"value_{i}"})
    for i in range(1000)
])
client.bulk(body=body)

# 避免：循环中单个插入
for i in range(1000):
    client.index(index="my_index", id=str(i), body={"field": f"value_{i}"})
```

### 事务管理注意事项

在连接池模式下，每个操作使用独立的连接，因此无法跨操作手动提交事务。

```python
# 推荐：依赖自动提交（默认行为）
for i in range(100):
    client.index(index="my_index", id=str(i), body={"field": f"value_{i}"})
# 每个 index() 调用自动提交

# 避免：在连接池模式下手动 commit()
for i in range(100):
    client.index(index="my_index", id=str(i), body={})
    client.commit()  # RuntimeError: commit() is not supported in connection pool mode
```

如需手动控制事务，请使用单连接模式或底层连接管理器：

```python
# 高级用法：使用 get_connection_for_operation() 手动管理事务
with client.connection.get_connection_for_operation() as conn:
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO my_table VALUES (%s, %s)", (1, 'value1'))
        cursor.execute("INSERT INTO my_table VALUES (%s, %s)", (2, 'value2'))
        conn.commit()  # 在同一连接上提交
    except Exception:
        conn.rollback()  # 失败时回滚
        raise
```

---

## 相关章节

- [快速开始](./01_QuickStart.md) - 快速入门
- [客户端连接管理](./02_Client_Connection.md) - 连接配置
- [索引管理](./03_Index_Management.md) - 索引操作
- [文档操作](./04_Document_CRUD.md) - 文档 CRUD
- [查询与搜索](./05_Query_Search.md) - 搜索
- [向量搜索](./06_Vector_Search.md) - 向量搜索
