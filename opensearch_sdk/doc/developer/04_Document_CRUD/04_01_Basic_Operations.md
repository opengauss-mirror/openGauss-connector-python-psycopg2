# 基础文档操作

本章节详细介绍 Opensearch兼容接口的基础文档操作，包括 `index` (UPSERT), `create` (纯插入), `update` (纯更新) 和 `delete` (删除)。

## 1. index 方法 (UPSERT)

### 功能描述
插入或更新单个文档。如果文档 ID 已存在则更新，不存在则创建。

### 函数签名
```python
def index(self, index: str, id: str, body: Dict[str, Any], refresh: bool = False) -> Any
```

### 参数说明
| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| index | str | 是 | - | 索引名称（对应数据库表名） |
| id | str | 是 | - | 文档 ID |
| body | dict | 是 | - | 文档内容 |
| refresh | bool | 否 | False | 是否刷新（Opensearch 中此参数被忽略） |

### 返回值
成功时返回：
```python
{
    "result": "created" | "updated",
    "_id": "文档ID",
    "_index": "索引名"
}
```

### 代码示例
```python
# 插入或更新文档
result = client.index(
    index="my_index",
    id="doc1",
    body={
        "title": "Hello Opensearch",
        "content": "This is a test document",
        "count": 10
    }
)
print(result)
# 输出: {'result': 'created', '_id': 'doc1', '_index': 'my_index'}

# 再次调用则会更新
result = client.index(
    index="my_index",
    id="doc1",
    body={"title": "Updated Title"}
)
print(result)
# 输出: {'result': 'updated', '_id': 'doc1', '_index': 'my_index'}
```

### SQL 生成示例
```sql
-- INSERT SQL
INSERT INTO my_index (id, title, count) VALUES (%s, %s, %s)

-- UPDATE SQL (当 INSERT 失败时)
UPDATE my_index SET title = %s, count = %s WHERE id = %s
```

---

## 2. create 方法 (纯插入)

### 功能描述
纯粹的 INSERT 操作。如果文档已存在，将抛出 409 Conflict 错误。

### 函数签名
```python
def create(self, index: str, id: str, body: Dict[str, Any], refresh: bool = False) -> Any
```

### 代码示例
```python
# 插入新文档
result = client.create(
    index="my_index",
    id="doc1",
    body={
        "title": "Hello Opensearch",
        "content": "This is a test document"
    }
)
print(result)
# 输出: {'result': 'created', '_id': 'doc1', '_index': 'my_index'}

# 尝试插入已存在的文档
try:
    client.create(
        index="my_index",
        id="doc1",
        body={"title": "Another"}
    )
except Exception as e:
    print(e)
    # 输出: Document with id 'doc1' already exists (409 Conflict)
```

---

## 3. update 方法 (纯更新)

### 功能描述
纯 UPDATE 操作。如果文档不存在，将抛出 404 Not Found 错误。

### 函数签名
```python
def update(self, index: str, id: str, body: Dict[str, Any], refresh: bool = False) -> Any
```

### 代码示例
```python
# 更新已存在的文档
result = client.update(
    index="my_index",
    id="doc1",
    body={
        "title": "Updated Title",
        "views": 100
    }
)
print(result)
# 输出: {'result': 'updated', '_id': 'doc1', '_index': 'my_index'}

# 尝试更新不存在的文档
try:
    client.update(
        index="my_index",
        id="nonexistent",
        body={"title": "Test"}
    )
except Exception as e:
    print(e)
    # 输出: ##OS## - Update Document Error | ... error: Document with id 'nonexistent' not found (404 Not Found)
```

---

## 4. delete 方法 (删除)

### 功能描述
删除指定 ID 的文档。如果文档不存在，将抛出 404 Not Found 错误。

### 函数签名
```python
def delete(self, index: str, id: str, refresh: bool = False) -> Any
```

### 代码示例
```python
# 删除文档
result = client.delete(
    index="my_index",
    id="doc1"
)
print(result)
# 输出: {'result': 'deleted', '_id': 'doc1', '_index': 'my_index'}

# 尝试删除不存在的文档
try:
    client.delete(
        index="my_index",
        id="nonexistent"
    )
except Exception as e:
    print(e)
    # 输出: ##OS## - Delete Document Error | ... error: Document with id 'nonexistent' not found in index 'my_index'
```
