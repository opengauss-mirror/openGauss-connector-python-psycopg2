# 文档操作

本章节详细介绍 Opensearch兼容接口的文档操作，包括插入、更新、删除和批量操作。

## 模块信息

**源文件**: `opensearch_sdk/client/document_ops.py`  
**Mixin 类**: `DocumentOpsMixin`

**相关模块**:
- `opensearch_sdk/client/doc_utils/nested_handler.py`: Nested 字段处理
- `opensearch_sdk/client/doc_utils/serialization.py`: 字段序列化
- `opensearch_sdk/client/doc_utils/type_inference.py`: 动态列类型推断
- `opensearch_sdk/client/doc_utils/operations.py`: 文档操作实现

## 概述

SDK 提供四种基本的文档操作方法，每种方法有不同的语义和行为：

| 方法 | 行为 | 文档存在时 | 文档不存在时 |
|:---|:---|:---|:---|
| index | UPSERT（存在更新，不存在创建） | 更新 | 创建 |
| create | 纯插入 | 抛出 409 Conflict | 创建 |
| update | 纯更新 | 更新 | 抛出 404 Not Found |
| delete | 删除 | 删除 | 抛出 404 Not Found |

**注意**：SDK 中没有 `insert` 方法，请使用 `create` 方法进行纯插入操作。

## index 方法

### 功能描述

插入或更新单个文档（UPSERT 语义）。如果文档 ID 已存在则更新，不存在则创建。

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

```
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
    body={
        "title": "Updated Title"
    }
)
print(result)
# 输出: {'result': 'updated', '_id': 'doc1', '_index': 'my_index'}
```

### 实现细节

**index 方法的内部实现流程**：

```
1. 验证索引名称
   └── 使用 _validate_identifier() 验证名称合法性

2. 处理文档内容
   └── 遍历 body 中的每个字段
   └── 验证字段名合法性
   └── 将 dict/list 类型转换为 JSON 字符串

3. 尝试 INSERT
   └── SQL: INSERT INTO {index} (id, field1, field2, ...) VALUES (%s, %s, %s, ...)
   └── 执行 INSERT

4. 处理 INSERT 失败（主键冲突）
   └── 捕获 "duplicate"/"unique"/"already exists" 错误
   └── 执行 UPDATE: UPDATE {index} SET field1 = %s, field2 = %s WHERE id = %s
```

### SQL 生成示例

```python
# 假设 body = {"title": "Test", "count": 10}

# INSERT SQL
INSERT INTO my_index (id, title, count) VALUES (%s, %s, %s)

# UPDATE SQL (当 INSERT 失败时)
UPDATE my_index SET title = %s, count = %s WHERE id = %s
```

## create 方法

### 功能描述

纯粹的 INSERT 操作。如果文档已存在，将抛出 409 Conflict 错误。

### 函数签名

```python
def create(self, index: str, id: str, body: Dict[str, Any], refresh: bool = False) -> Any
```

### 参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| index | str | 是 | - | 索引名称（对应数据库表名） |
| id | str | 是 | - | 文档 ID |
| body | dict | 是 | - | 文档内容 |
| refresh | bool | 否 | False | 是否刷新（Opensearch 中此参数被忽略） |

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

## update 方法

### 功能描述

纯 UPDATE 操作。如果文档不存在，将抛出 404 Not Found 错误。

### 函数签名

```python
def update(self, index: str, id: str, body: Dict[str, Any], refresh: bool = False) -> Any
```

### 代码示例

```
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
    # 输出: ##OS## - Update Document Error | index=my_index | id=nonexistent | error: Document with id 'nonexistent' not found (404 Not Found)
```

## delete 方法

### 功能描述

删除指定 ID 的文档。如果文档不存在，将抛出 404 Not Found 错误。

### 函数签名

```python
def delete(self, index: str, id: str, refresh: bool = False) -> Any
```

### 代码示例

```
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
    # 输出: ##OS## - Delete Document Error | index=my_index | id=nonexistent | error: Document with id 'nonexistent' not found in index 'my_index'
```

## get 方法

### 功能描述

根据文档 ID 获取文档内容。

### 函数签名

```python
def get(self, index: str, id: str) -> Any
```

### 代码示例

```
# 获取文档
result = client.get(
    index="my_index",
    id="doc1"
)
print(result)
# 输出: {'_index': 'my_index', '_id': 'doc1', '_source': {...}}
```

## bulk 批量操作

### 功能描述

批量插入、更新或删除文档。

### 函数签名

```python
def bulk(self, body: str, *, refresh: bool = False) -> Any
```

### NDJSON 格式

bulk API 使用 NDJSON（Newline Delimited JSON）格式：

```
{action_and_metadata}
optional_source
{action_and_metadata}
optional_source
...
```

### 代码示例

```
# 批量操作
body = """
{"index": {"_index": "my_index", "_id": "doc1"}}
{"title": "Doc 1", "content": "Content 1"}
{"index": {"_index": "my_index", "_id": "doc2"}}
{"title": "Doc 2", "content": "Content 2"}
{"update": {"_index": "my_index", "_id": "doc1"}}
{"doc": {"views": 100}}
{"delete": {"_index": "my_index", "_id": "doc3"}}
"""

result = client.bulk(body)
print(result)
```

### 支持的操作类型

| 操作 | 语法 | 说明 |
|:---|:---|:---|
| index | `{"index": {"_index": "...", "_id": "..."}}` | 插入或更新 |
| create | `{"create": {"_index": "...", "_id": "..."}}` | 仅插入 |
| update | `{"update": {"_index": "...", "_id": "..."}}` | 更新 |
| delete | `{"delete": {"_index": "...", "_id": "..."}}` | 删除 |

## delete_ids 批量删除

### 功能描述

根据 ID 列表批量删除文档。

### 函数签名

```python
def delete_ids(self, index: str, ids: List[str]) -> Any
```

### 代码示例

```
# 批量删除
result = client.delete_ids(
    index="my_index",
    ids=["doc1", "doc2", "doc3"]
)
print(result)
# 输出: {'deleted': 3}
```

## 外部接口说明

### 1. 文档操作基础接口

```
from opensearch_sdk import OpenGauss

client = OpenGauss(...)

# 文档操作直接通过client调用
# 无需额外的客户端实例化
```

### 2. 外部调用接口

#### 2.1 文档插入/更新接口

```python
# UPSERT操作（存在更新，不存在创建）
result = client.index(
    index="my_index",
    id="doc1",
    body={
        "title": "Hello Opensearch",
        "content": "This is a test document",
        "count": 10,
        "tags": ["test", "demo"],
        "metadata": {"author": "user1", "version": 1}
    }
)

# 纯插入操作（文档存在时报错）
result = client.create(
    index="my_index",
    id="doc2",
    body={"title": "New Document"}
)
```

#### 2.2 文档更新接口

```
# 纯更新操作（文档不存在时报错）
result = client.update(
    index="my_index",
    id="doc1",
    body={
        "title": "Updated Title",
        "views": 100
    }
)
```

#### 2.3 文档查询和删除接口

```
# 获取单个文档
result = client.get(index="my_index", id="doc1")

# 删除单个文档
result = client.delete(index="my_index", id="doc1")
```

#### 2.4 批量操作接口

```
# 批量操作（NDJSON格式）
bulk_body = """
{"index": {"_index": "my_index", "_id": "doc1"}}
{"title": "Doc 1", "content": "Content 1"}
{"index": {"_index": "my_index", "_id": "doc2"}}
{"title": "Doc 2", "content": "Content 2"}
{"update": {"_index": "my_index", "_id": "doc1"}}
{"doc": {"views": 100}}
{"delete": {"_index": "my_index", "_id": "doc3"}}
"""

result = client.bulk(body=bulk_body)

# 批量删除
result = client.delete_ids(
    index="my_index",
    ids=["doc1", "doc2", "doc3"]
)
```

#### 2.5 向量文档操作接口

```
import json

# 插入向量文档
result = client.index(
    index="vector_index",
    id="vec1",
    body={
        "title": "Vector Document",
        "embedding": json.dumps([0.1, 0.2, 0.3, 0.4]),  # 向量需要JSON序列化
        "category": "test"
    }
)
```

---

## 内部接口说明

### 1. DocumentOpsMixin 类 (opensearch_sdk/client/document_ops.py)

DocumentOpsMixin 是文档操作的核心 Mixin 类，提供完整的文档CRUD功能。

#### 1.1 index() - UPSERT操作

**函数签名**：
```python
def index(
    self,
    index: str,
    id: str,
    body: Dict[str, Any],
    refresh: bool = False
) -> Any
```

**功能描述**: 
插入或更新文档，实现UPSERT语义（存在则更新，不存在则创建）。

**内部流程**：
```
1. 参数验证
   ├── 验证索引名称合法性（使用 _validate_identifier）
   └── 验证文档 ID 合法性

2. 文档内容处理
   ├── 遍历 body 中的所有字段
   ├── 验证字段名合法性
   ├── 将 dict/list 类型转换为 JSON 字符串
   └── 收集字段名和值列表

3. 尝试 INSERT操作
   ├── 构建 INSERT SQL语句
   ├── 执行参数化查询
   └── 捕获执行结果

4. 处理 INSERT失败（主键冲突）
   ├── 检查错误类型（duplicate/unique/already exists）
   ├── 构建UPDATE SQL语句
   ├── 执行UPDATE操作
   └── 返回更新结果

5. 返回标准化响应
   ├── 根据操作类型设置 result 字段（created/updated）
   ├── 添加 _id 和 _index 字段
   └── 返回响应字典
```

**参数说明**：
- `index`: 索引名称（对应数据库表名）
- `id`: 文档 ID
- `body`: 文档内容字典
- `refresh`: 是否刷新（Opensearch 中此参数被忽略）

**返回值**：
```python
{
    "result": "created",  # 或 "updated"
    "_id": "doc1",
    "_index": "my_index"
}
```

**相关方法**：
- `_validate_identifier()`: 标识符验证
- `_process_document_fields()`: 文档字段处理
- `_build_insert_sql()`: INSERT SQL构建
- `_build_update_sql()`: UPDATE SQL构建

---

#### 1.2 insert() - 纯插入操作

**函数签名**：
```python
def insert(
    self,
    index: str,
    id: str,
    body: Dict[str, Any]
) -> Any
```

**功能描述**: 
纯粹的 INSERT操作，文档存在时抛出 409 Conflict 错误。

**内部流程**：
```
1. 参数验证
   ├── 验证索引名称合法性
   └── 验证文档 ID 合法性

2. 文档内容处理
   └── 转换复杂类型为 JSON

3. 执行 INSERT
   ├── 构建 INSERT SQL
   └── 执行并返回结果

4. 错误处理
   └── 如文档已存在，抛出 409 Conflict
```

**参数说明**：
- `index`: 索引名称
- `id`: 文档 ID
- `body`: 文档内容字典

**返回值**：
```python
{
    "result": "created",
    "_id": "doc1",
    "_index": "my_index"
}
```

**异常**：
- `ConflictError`: 文档已存在时抛出 409 Conflict

---

#### 1.3 update() - 纯更新操作

**函数签名**：
```python
def update(
    self,
    index: str,
    id: str,
    body: Dict[str, Any],
    refresh: bool = False
) -> Any
```

**功能描述**: 
纯粹的 UPDATE操作，文档不存在时抛出 404 Not Found 错误。

**内部流程**：
```
1. 参数验证
   ├── 验证索引名称合法性
   └── 验证文档 ID 合法性

2. 文档内容处理
   └── 转换复杂类型为 JSON

3. 执行UPDATE
   ├── 构建UPDATE SQL
   ├── 执行参数化查询
   └── 检查受影响行数

4. 错误处理
   └── 如文档不存在，抛出 404 Not Found
```

**参数说明**：
- `index`: 索引名称
- `id`: 文档 ID
- `body`: 文档内容字典（只更新提供的字段）
- `refresh`: 是否刷新（可选）

**返回值**：
```python
{
    "result": "updated",
    "_id": "doc1",
    "_index": "my_index"
}
```

**异常**：
- `NotFoundError`: 文档不存在时抛出 404 Not Found

---

#### 1.4 delete() - 删除操作

**函数签名**：
```python
def delete(
    self,
    index: str,
    id: str,
    refresh: bool = False
) -> Any
```

**功能描述**: 
删除指定文档，不存在时抛出 404 Not Found 错误。

**内部流程**：
```
1. 参数验证
   ├── 验证索引名称合法性
   └── 验证文档 ID 合法性

2. 执行 DELETE
   ├── 构建 DELETE SQL: DELETE FROM {index} WHERE id = %s
   ├── 执行参数化查询
   └── 检查受影响行数

3. 错误处理
   └── 如文档不存在，抛出 404 Not Found
```

**参数说明**：
- `index`: 索引名称
- `id`: 文档 ID
- `refresh`: 是否刷新（可选）

**返回值**：
```python
{
    "result": "deleted",
    "_id": "doc1",
    "_index": "my_index"
}
```

**异常**：
- `NotFoundError`: 文档不存在时抛出 404 Not Found

---

#### 1.5 get() - 文档查询

**函数签名**：
```python
def get(
    self,
    index: str,
    id: str
) -> Any
```

**功能描述**: 
根据 ID 获取文档内容。

**内部流程**：
```
1. 参数验证
   ├── 验证索引名称合法性
   └── 验证文档 ID 合法性

2. 执行 SELECT
   ├── 构建 SELECT SQL: SELECT * FROM {index} WHERE id = %s
   ├── 执行参数化查询
   └── 获取结果

3. 格式化结果
   ├── 解析 JSON 字段
   └── 返回标准化格式
```

**参数说明**：
- `index`: 索引名称
- `id`: 文档 ID

**返回值**：
```python
{
    "_index": "my_index",
    "_id": "doc1",
    "_source": {
        "title": "Hello Opensearch",
        "content": "This is a test document"
    }
}
```

**异常**：
- `NotFoundError`: 文档不存在时抛出 404 Not Found

---

### 2. 批量操作接口

#### 2.1 bulk() - 批量操作

**函数签名**：
```python
def bulk(
    self,
    body: str,
    *,
    refresh: bool = False
) -> Any
```

**功能描述**: 
解析 NDJSON格式的批量操作指令并执行。

**NDJSON 格式**：
```
{action_and_metadata}
optional_source
{action_and_metadata}
optional_source
...
```

**内部流程**：
```
1. 解析 NDJSON
   ├── 按行分割
   ├── 解析操作元数据行
   └── 解析文档内容行（如有）

2. 处理每个操作
   ├── index/create: 调用 index() 方法
   ├── update: 调用 update() 方法
   └── delete: 调用 delete() 方法

3. 收集结果
   └── 返回所有操作的结果列表
```

**参数说明**：
- `body`: NDJSON格式的批量操作字符串
- `refresh`: 是否刷新（可选）

**支持的操作类型**：
- `index`: 插入或更新
- `create`: 仅插入
- `update`: 更新
- `delete`: 删除

**返回值**：
```python
{
    "took": 123,  # 耗时（毫秒）
    "errors": False,  # 是否有错误
    "items": [
        {"index": {"_id": "1", "result": "created", "status": 201}},
        {"update": {"_id": "2", "result": "updated", "status": 200}},
        {"delete": {"_id": "3", "result": "deleted", "status": 200}}
    ]
}
```

---

#### 2.2 delete_ids() - 批量删除

**函数签名**：
```python
def delete_ids(
    self,
    index: str,
    ids: List[str]
) -> Any
```

**功能描述**: 
根据 ID 列表批量删除文档。

**内部流程**：
```
1. 参数验证
   ├── 验证索引名称合法性
   └── 验证 ID 列表非空

2. 批量删除
   ├── 构建 DELETE SQL: DELETE FROM {index} WHERE id IN (%s, %s, ...)
   ├── 执行参数化查询
   └── 统计删除数量

3. 返回结果
   └── 返回删除的文档数量
```

**参数说明**：
- `index`: 索引名称
- `ids`: 文档 ID 列表

**返回值**：
```python
{
    "deleted": 5  # 删除的文档数量
}
```

---

### 3. 内部辅助方法

#### 3.1 _validate_identifier() - 标识符验证

**函数签名**：
```python
def _validate_identifier(self, identifier: str) -> None
```

**功能描述**: 
验证索引名和文档 ID 的合法性，防止 SQL 注入。

**验证规则**：
- 只能包含字母、数字、下划线
- 不能以数字开头
- 不能为空

**异常**：
- `ValueError`: 标识符不合法时抛出

---

#### 3.2 _process_document_fields() - 文档字段处理

**函数签名**：
```python
def _process_document_fields(
    self,
    body: Dict[str, Any]
) -> Tuple[List[str], List[Any]]
```

**功能描述**: 
处理文档字段，转换复杂类型，生成 SQL 参数。

**处理逻辑**：
```python
def _process_document_fields(self, body):
    fields = []
    values = []
    
    for field_name, field_value in body.items():
        # 验证字段名
        self._validate_identifier(field_name)
        
        # 处理不同类型的字段值
        if isinstance(field_value, dict):
            processed_value = json.dumps(field_value)
        elif isinstance(field_value, list):
            processed_value = json.dumps(field_value)
        elif field_value is None:
            processed_value = None
        else:
            processed_value = field_value
            
        fields.append(field_name)
        values.append(processed_value)
    
    return fields, values
```

**返回值**：
- `List[str]`: 字段名列表
- `List[Any]`: 参数值列表

---

#### 3.3 _build_insert_sql() - INSERT SQL构建

**函数签名**：
```python
def _build_insert_sql(
    self,
    index: str,
    fields: List[str]
) -> sql.Composable
```

**功能描述**: 
构建 INSERT 语句。

**生成的 SQL**：
```sql
INSERT INTO my_index (id, field1, field2, ...) VALUES (%s, %s, %s, ...)
```

---

#### 3.4 _build_update_sql() - UPDATE SQL构建

**函数签名**：
```python
def _build_update_sql(
    self,
    index: str,
    fields: List[str]
) -> sql.Composable
```

**功能描述**: 
构建UPDATE 语句。

**生成的 SQL**：
```sql
UPDATE my_index SET field1 = %s, field2 = %s, ... WHERE id = %s
```

---

## 数据结构新增或变更

### 1. 文档操作请求结构

```
# 文档插入/更新请求
document_request = {
    "index": "my_index",           # 索引名称
    "id": "doc1",                  # 文档ID
    "body": {                      # 文档内容
        "field1": "value1",
        "field2": 123,
        "field3": [1, 2, 3],
        "field4": {"nested": "data"},
        "embedding": "[0.1, 0.2, 0.3]"  # 向量字段JSON字符串
    }
}
```

### 2. 文档操作响应结构

```
# 操作成功响应
document_response = {
    "result": "created" | "updated" | "deleted",  # 操作结果
    "_id": "doc1",                                # 文档ID
    "_index": "my_index"                          # 索引名称
}

# 批量删除响应
bulk_delete_response = {
    "deleted": 5                                   # 删除的文档数量
}
```

### 3. 批量操作结构

```
# NDJSON格式的批量操作
bulk_request_format = """
{action_metadata}
{optional_document_body}
{action_metadata}
{optional_document_body}
"""

# 支持的操作类型
bulk_actions = {
    "index": {"_index": "my_index", "_id": "doc1"},    # 插入/更新
    "create": {"_index": "my_index", "_id": "doc1"},   # 仅插入
    "update": {"_index": "my_index", "_id": "doc1"},   # 更新
    "delete": {"_index": "my_index", "_id": "doc1"}    # 删除
}

# 更新操作的文档内容
update_document = {
    "doc": {"field1": "new_value"}    # 部分更新
}
```

### 4. 字段类型转换结构

```
# 字段类型映射和转换
field_conversion = {
    "str": "直接存储",                    # 字符串
    "int": "直接存储",                    # 整数
    "float": "直接存储",                  # 浮点数
    "bool": "直接存储",                   # 布尔值
    "list": "json.dumps()转换",           # 列表转JSON字符串
    "dict": "json.dumps()转换",           # 字典转JSON字符串
    "None": "存储为NULL"                  # 空值
}
```

### 5. SQL参数结构

```
# SQL执行参数结构
sql_params = {
    "table_name": "my_index",           # 表名
    "columns": ["id", "title", "count"], # 列名列表
    "values": ["doc1", "title", 10],     # 参数值列表
    "id_value": "doc1"                   # 文档ID值（用于WHERE条件）
}
```

---

## 高级特性

### 动态列类型推断

**功能描述**：

Opensearch兼容接口支持动态列类型推断功能，当插入的文档包含未在 mapping 中定义的字段时，SDK 可以自动从样本值推断列类型并创建新列。

**初始化配置**：

```python
from opensearch_sdk import OpenGauss

# 启用动态列推断（默认启用）
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    enable_dynamic_inference=True  # 启用动态列推断
)

# 禁用动态列推断（严格模式）
client_strict = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    enable_dynamic_inference=False  # 严格模式，字段必须在 mapping 中定义
)
```

**工作原理**：

1. **检查字段是否存在**：插入文档时，SDK 首先检查字段是否在 mapping 中定义
2. **匹配 dynamic_templates**：如果未定义，尝试匹配 dynamic_templates 中的模板规则
3. **类型推断**：如果模板也未匹配，根据样本值推断类型：
   - `str` → TEXT
   - `int` → INTEGER
   - `float` → REAL
   - `bool` → BOOLEAN
   - `list/dict` → JSONB
4. **创建新列**：使用 ALTER TABLE 添加新列

**示例**：

```python
# 假设索引 my_index 只有 title 字段
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"}
        }
    }
}
client.indices.create(index="my_index", body=mapping)

# 插入包含新字段的文档（enable_dynamic_inference=True）
client.index(
    index="my_index",
    id="doc1",
    body={
        "title": "Test",
        "author": "John",      # 新字段，自动推断为 TEXT
        "views": 100,          # 新字段，自动推断为 INTEGER
        "tags": ["a", "b"]     # 新字段，自动推断为 JSONB
    }
)
# SDK 会自动执行：
# ALTER TABLE my_index ADD COLUMN author TEXT
# ALTER TABLE my_index ADD COLUMN views INTEGER
# ALTER TABLE my_index ADD COLUMN tags JSONB
```

**注意事项**：

- **开发环境推荐启用**：灵活方便，快速迭代
- **生产环境建议禁用**：避免意外创建列，保持 schema 稳定
- **类型推断可能不准确**：如第一个值是整数，后续出现字符串会报错

---

### Nested 字段处理

**设计理念**：

Opensearch 采用**扁平化策略**处理 nested 字段，将嵌套对象展开为 `field.subfield` 形式的列存储。

**示例**：

```python
# 原始 nested 结构
document = {
    "title": "Product",
    "comments": [  # nested 数组
        {"user": "Alice", "rating": 5},
        {"user": "Bob", "rating": 4}
    ]
}

# 扁平化后存储为
document_flat = {
    "title": "Product",
    "comments.0.user": "Alice",
    "comments.0.rating": 5,
    "comments.1.user": "Bob",
    "comments.1.rating": 4
}
```

**实现细节**：

1. **写入时扁平化**：SDK 在 `_flatten_nested_document()` 中将 nested 对象展开
2. **读取时重构**：SDK 在 `_reconstruct_nested_structure()` 中恢复 nested 结构
3. **分隔符**：使用 `.` 作为 nested 字段分隔符（可通过 `NESTED_FIELD_SEPARATOR` 常量配置）

**代码示例**：

```python
# 插入 nested 文档
client.index(
    index="products",
    id="prod1",
    body={
        "name": "Laptop",
        "specs": {  # nested 对象
            "cpu": "i7",
            "ram": "16GB"
        },
        "reviews": [  # nested 数组
            {"user": "Alice", "score": 5},
            {"user": "Bob", "score": 4}
        ]
    }
)

# 查询时自动恢复 nested 结构
result = client.get(index="products", id="prod1")
print(result['_source'])
# 输出：
# {
#     "name": "Laptop",
#     "specs": {"cpu": "i7", "ram": "16GB"},
#     "reviews": [
#         {"user": "Alice", "score": 5},
#         {"user": "Bob", "score": 4}
#     ]
# }
```

**限制与注意事项**：

- **Nested 数组多值丢失**：由于扁平化策略，nested 数组中的多个对象会被展开为独立列，可能导致查询时的语义变化
- **Nested 对象完全支持**：单层 nested 对象（非数组）可以完美支持
- **不支持深层嵌套**：建议嵌套层级不超过 3 层

**详细说明**：请参阅 [Nested 结构与动态列](10_Nested_Dynamic.md)

---

### 事务管理

**连接池模式下的事务管理**：

Opensearch兼容接口使用 `get_connection_for_operation()` 上下文管理器确保在连接池模式下的事务一致性。

**使用示例**：

```python
# 方式 1：使用 transaction() 上下文管理器（推荐）
with client.transaction() as conn:
    cursor = conn.cursor()
    try:
        # 在同一连接上执行多个操作
        cursor.execute("INSERT INTO my_index (id, title) VALUES (%s, %s)", ("doc1", "Title 1"))
        cursor.execute("INSERT INTO my_index (id, title) VALUES (%s, %s)", ("doc2", "Title 2"))
        # 正常退出时自动提交
    except Exception:
        # 异常时自动回滚
        raise

# 方式 2：直接使用 SDK 方法（自动管理事务）
try:
    client.index(index="my_index", id="doc1", body={"title": "Test"})
    client.index(index="my_index", id="doc2", body={"title": "Test 2"})
    # 每个操作在独立的事务中执行
except Exception as e:
    print(f"操作失败: {e}")
```

**重要说明**：

- **单连接模式**：可以直接使用 `client.commit()` 和 `client.rollback()`
- **连接池模式**：必须使用 `transaction()` 上下文管理器或依赖自动事务管理
- **禁止跨连接事务**：不能在多个 `get_connection_for_operation()` 之间共享事务

### 1. index() UPSERT操作流程

```
1. 参数验证
   ├── 验证索引名称合法性
   ├── 验证文档ID合法性
   └── 验证文档内容非空

2. 文档内容处理
   ├── 遍历body中的所有字段
   ├── 验证字段名合法性
   ├── 将dict/list类型转换为JSON字符串
   ├── 收集字段名和值列表
   └── 准备SQL参数

3. 尝试INSERT操作
   ├── 构建INSERT SQL语句
   ├── 执行参数化查询
   └── 捕获执行结果

4. 处理INSERT失败（主键冲突）
   ├── 检查错误类型（duplicate/unique/already exists）
   ├── 构建UPDATE SQL语句
   ├── 执行UPDATE操作
   └── 返回更新结果

5. 返回标准化响应
   ├── 根据操作类型设置result字段
   ├── 添加_id和_index字段
   └── 返回响应字典
```

### 2. 文档字段处理逻辑

```python
def _process_document_fields(self, body):
    """处理文档字段，转换复杂类型"""
    fields = []
    values = []
    
    for field_name, field_value in body.items():
        # 验证字段名
        self._validate_identifier(field_name)
        
        # 处理不同类型的字段值
        if isinstance(field_value, dict):
            # 字典类型转JSON字符串
            processed_value = json.dumps(field_value)
        elif isinstance(field_value, list):
            # 列表类型转JSON字符串
            processed_value = json.dumps(field_value)
        elif field_value is None:
            # None值保持None
            processed_value = None
        else:
            # 基础类型直接使用
            processed_value = field_value
            
        fields.append(field_name)
        values.append(processed_value)
    
    return fields, values
```

### 3. SQL构建逻辑

```python
def _build_insert_sql(self, index, fields):
    """构建INSERT SQL语句"""
    column_names = ['id'] + fields  # 添加id主键列
    placeholders = ['%s'] * len(column_names)
    
    return sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(index),
        sql.SQL(', ').join(map(sql.Identifier, column_names)),
        sql.SQL(', ').join(map(sql.Placeholder, placeholders))
    )

def _build_update_sql(self, index, fields):
    """构建UPDATE SQL语句"""
    set_clauses = [
        sql.SQL("{} = {}").format(
            sql.Identifier(field),
            sql.Placeholder()
        ) for field in fields
    ]
    
    return sql.SQL("UPDATE {} SET {} WHERE {} = {}").format(
        sql.Identifier(index),
        sql.SQL(', ').join(set_clauses),
        sql.Identifier('id'),
        sql.Placeholder()
    )
```

### 4. 批量操作解析逻辑

```python
def _parse_bulk_body(self, body):
    """解析NDJSON格式的批量操作"""
    operations = []
    lines = body.strip().split('\n')
    
    i = 0
    while i < len(lines):
        # 解析操作元数据行
        action_line = json.loads(lines[i])
        action = list(action_line.keys())[0]
        metadata = action_line[action]
        
        if action in ['index', 'create']:
            # 需要文档内容的操作
            i += 1
            if i < len(lines):
                document = json.loads(lines[i])
                operations.append((action, metadata, document))
        elif action == 'update':
            # 更新操作
            i += 1
            if i < len(lines):
                update_doc = json.loads(lines[i])
                operations.append((action, metadata, update_doc))
        elif action == 'delete':
            # 删除操作无需文档内容
            operations.append((action, metadata, None))
        
        i += 1
    
    return operations
```

### 5. 错误处理逻辑

```python
def _handle_database_error(self, error, operation, index, doc_id):
    """统一处理数据库操作错误"""
    error_msg = str(error).lower()
    
    if any(keyword in error_msg for keyword in ['duplicate', 'unique', 'already exists']):
        # 主键冲突错误
        if operation == 'insert':
            raise ConflictError(f"Document with id '{doc_id}' already exists (409 Conflict)")
        return 'duplicate'  # 返回错误类型供调用方处理
    
    elif 'no such table' in error_msg:
        # 表不存在错误
        raise NotFoundError(f"Index '{index}' not found (404 Not Found)")
    
    elif 'no rows' in error_msg or '0 rows' in error_msg:
        # 行不存在错误
        raise NotFoundError(f"Document with id '{doc_id}' not found (404 Not Found)")
    
    else:
        # 其他数据库错误
        raise DatabaseError(f"Database operation failed: {error}")
```

---

## 主要代码文件

| 代码路径 | 代码说明 |
|:---|:---|
| [`opensearch_sdk/client/document_ops.py`](opensearch_sdk/client/document_ops.py) | DocumentOpsMixin实现，提供所有文档CRUD操作功能 |
| [`opensearch_sdk/client/base.py`](opensearch_sdk/client/base.py) | OpenGaussClient基类，继承DocumentOpsMixin获得文档操作能力 |
| [`opensearch_sdk/connection/opengauss.py`](opensearch_sdk/connection/opengauss.py) | 底层数据库连接，执行SQL语句和处理结果 |
| [`opensearch_sdk/client/query_builder.py`](opensearch_sdk/client/query_builder.py) | SQL构建器，提供安全的参数化查询构建 |
| [`opensearch_sdk/client/utils.py`](opensearch_sdk/client/utils.py) | 工具函数，提供标识符验证、JSON处理等辅助功能 |
| [`opensearch_sdk/client/constants.py`](opensearch_sdk/client/constants.py) | 常量定义，包含错误码、默认值等 |

## 相关章节

- [客户端连接](./02_Client_Connection.md) - 了解客户端初始化
- [索引管理](./03_Index_Management.md) - 了解索引操作
- [查询搜索](./05_Query_Search.md) - 了解搜索功能
- [向量搜索](./06_Vector_Search.md) - 了解向量搜索
