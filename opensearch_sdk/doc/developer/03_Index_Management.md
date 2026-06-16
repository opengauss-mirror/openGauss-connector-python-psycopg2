# 索引管理

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

## 创建索引

### create 方法

**功能描述**：创建新索引，同时自动创建相应字段的索引。

**函数签名**：

```python
def create(self, *, index: Any, body: Any = None, params: Any = None, headers: Any = None) -> Any
```

### 参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| index | str | 是 | - | 索引名称 |
| body | dict | 否 | None | 索引配置，包含 mappings 和 settings |
| params | dict | 否 | None | 额外查询参数 |
| headers | dict | 否 | None | 额外请求头 |

### Mapping 配置

创建索引时必须定义 `mappings`：

```python
mapping = {
    "mappings": {
        "properties": {
            "字段名": {"type": "字段类型"},
            ...
        }
    }
}
```

#### Dynamic Templates 支持

Opensearch 支持保存和使用 `dynamic_templates`，详见 [Nested 结构与动态列](10_Nested_Dynamic.md)。

**示例**：

```python
mapping = {
    "mappings": {
        "dynamic_templates": [
            {
                "vector_template": {
                    "match": "*_vec",
                    "mapping": {
                        "type": "knn_vector",
                        "dimension": 1024
                    }
                }
            }
        ],
        "properties": {
            "title": {"type": "text"}
        }
    }
}
```

**实现细节**：
- SDK 会保存完整的 mapping（包括 dynamic_templates）到 pg_description
- 插入文档时会自动匹配模板并推断列类型
- 通配符模式会被转换为正则表达式进行匹配

### 支持的字段类型

| 字段类型 | Opensearch 列类型 | 说明 |
|:---|:---|:---|
| text | TEXT | 全文检索文本 |
| keyword | VARCHAR | 精确匹配字符串 |
| long | INTEGER | 64位整数 |
| integer | INTEGER | 32位整数 |
| float | REAL | 32位浮点数 |
| boolean | BOOLEAN | 布尔值 |
| date | TIMESTAMP | 日期时间 |
| float_vector | vector | 浮点向量 |
| dense_vector | vector | 密集向量 |
| jsonb | JSONB | JSON 对象 |

### 代码示例

```python
# 创建基础索引（所有字段默认 index: true）
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

# 创建向量索引（向量字段默认 index: true，自动创建 HNSW 索引）
client.indices.create(
    index="vector_index",
    body={
        "mappings": {
            "properties": {
                "text": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 768,
                    "similarity": "cosine"
                }
            }
        }
    }
)

# 使用 index: false 关闭字段索引（节省存储空间）
client.indices.create(
    index="docs_index",
    body={
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "content": {
                    "type": "text",
                    "index": False  # 不创建索引，仅存储数据
                },
                "embedding": {
                    "type": "dense_vector",
                    "dims": 768,
                    "similarity": "cosine",
                    "index": True  # 显式启用索引（默认就是 true）
                }
            }
        }
    }
)
```

### 创建分布式表（Distributed Table）

**功能描述**：Opensearch兼容接口支持将索引创建为分布式表，通过 hash 分区实现数据分片存储，提升大规模数据的查询性能和存储扩展性。

**新增参数**：

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| distributed | bool | 否 | False | 是否创建为分布式表 |
| distribution_column | str | 否 | "id" | 分布列名称（用于 hash 计算） |
| shard_count | int | 否 | 6 | 分片数量 |

**重要约束**：

1. **分布列类型限制**：
   - 推荐：`BIGINT`, `INTEGER`, `SMALLINT`（整数类型）
   - 可用：`TIMESTAMP`, `DATE`, `BOOLEAN`
   - 禁止：`vector`, `halfvec`, `sparsevec`（向量类型）
   - 不推荐：`TEXT`, `VARCHAR`（字符串类型，除非使用 deterministic collation）

2. **只能转换一次**：普通表转换为分布式表后，无法再转回普通表

3. **查询透明**：转换后，所有 SQL 查询无需修改，系统自动路由到对应分片

**使用示例**：

```python
# 示例 1：创建普通表（默认行为，向后兼容）
client.indices.create(
    index="my_index",
    body={
        "mappings": {
            "properties": {
                "id": {"type": "long"},
                "title": {"type": "text"}
            }
        }
    }
)

# 示例 2：创建分布式表（使用默认参数）
client.indices.create(
    index="my_distributed_index",
    body={
        "mappings": {
            "properties": {
                "id": {"type": "long"},
                "title": {"type": "text"},
                "embedding": {"type": "float_vector", "dimension": 768}
            }
        }
    },
    distributed=True  # 分布列默认为 "id"，分片数默认为 6
)

# 示例 3：创建分布式表（自定义参数）
client.indices.create(
    index="my_distributed_custom",
    body={
        "mappings": {
            "properties": {
                "user_id": {"type": "long"},
                "title": {"type": "text"},
                "embedding": {"type": "float_vector", "dimension": 768}
            }
        }
    },
    distributed=True,
    distribution_column="user_id",  # 自定义分布列
    shard_count=8                   # 自定义分片数
)
```

**错误处理与回滚**：

如果分布式表转换失败（例如分布列类型不支持），SDK 会自动回滚：
- 删除已创建的普通表
- 抛出异常并记录详细错误信息

```python
try:
    client.indices.create(
        index="test_index",
        body={...},
        distributed=True,
        distribution_column="embedding"  # 错误：向量类型不能作为分布列
    )
except Exception as e:
    print(f"创建失败：{e}")
    # 输出：创建分布式表失败，已回滚: ...
    # 表已被自动删除，不会留下脏数据
```

**验证分布式表**：

```python
# 查询是否为分布式表
cursor = client.connection.execute(
    "SELECT logicalrelid FROM pg_dist_partition WHERE logicalrelid = %s::regclass",
    ('my_distributed_index',)
)
row = cursor.fetchone()
cursor.close()

if row:
    print("是分布式表")
else:
    print("是普通表")

# 查看分片分布情况
cursor = client.connection.execute("SELECT * FROM pg_dist_shard")
for row in cursor.fetchall():
    print(row)
cursor.close()
```

**最佳实践**：

1. **选择合适的分布列**：
   - 使用主键或唯一标识符（如 `id`, `user_id`）
   - 经常 JOIN 的表使用相同的分布列

2. **分片数量选择**：
   - 小数据集（< 100GB）：4-8 个分片
   - 中等数据集（100GB-1TB）：16-32 个分片
   - 大数据集（> 1TB）：64+ 个分片

3. **性能特点**：
   - 单点查询：性能相当或略好
   - 聚合查询（COUNT/SUM/AVG）：显著提升（并行计算）
   - 全表扫描：可能略差（需要协调多个分片）
   - 跨分片 JOIN：显著变差

**详细说明**：请参阅 [分布式表知识](../../knowledge/distributed_tables.md)

## 删除索引

### delete 方法

```python
client.indices.delete(index="my_index")
```

## 检查索引存在性

### exists 方法

```python
exists = client.indices.exists(index="my_index")
```

## 获取所有索引

### get_all_index_names 方法

```python
index_names = client.indices.get_all_index_names()
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

---

## 内部实现说明

### 1. IndicesClient 类 (opensearch_sdk/client/indices_client.py)

IndicesClient 是索引管理的核心客户端类，提供完整的索引 CRUD 操作功能。

#### 1.1 create() - 索引创建

**函数签名**：
```python
def create(
    self,
    *,
    index: Any = None,
    body: Any = None,
    params: Any = None,
    headers: Any = None,
    distributed: bool = False,
    distribution_column: str = "id",
    shard_count: int = 6
) -> Any
```

**功能描述**: 
创建新索引，解析 mapping 配置，创建表结构和索引。使用新的连接管理模式，无需手动重连。

**内部流程**：
```
1. 参数验证和预处理
   ├── 验证索引名称合法性（使用 normalize_identifier）
   ├── 解析 body 中的 mappings 配置
   └── 提取 settings 配置（如有）

2. SQL 生成（通过 sql_generator 模块）
   ├── generate_create_table_sql(): 生成 CREATE TABLE SQL
   ├── generate_index_sql(): 为每个字段生成 CREATE INDEX SQL
   └── generate_bm25_set_sql(): 生成 BM25 配置 SET 命令

3. 表结构创建
   ├── 使用 get_connection_for_operation() 获取连接
   ├── 执行 CREATE TABLE SQL
   └── 立即提交事务（DDL 操作）

4. 分布式表转换（可选，优先执行）
   ├── 如果 distributed=True，调用 _convert_to_distributed()
   ├── 执行 create_distributed_table() 函数
   ├── 失败时自动回滚（删除已创建的表）
   └── [OPTIMIZATION] 在创建索引之前转换，避免重复建索引

5. 索引创建
   ├── 遍历 fields_to_index 列表
   ├── 为每个字段生成对应的索引 SQL
   │   ├── text → BM25 全文索引
   │   ├── keyword/long/integer/float/date/boolean → B-tree 索引
   │   └── float_vector/dense_vector → HNSW 向量索引
   └── 执行并立即提交每个 CREATE INDEX
       └── 如果是分布式表，索引会自动在各个分片上并行创建

6. Mapping 存储
   ├── 将 mapping 信息保存到 opensearch_mapping 表
   ├── 用于动态列类型推断
   └── 支持 dynamic_templates
```

**参数说明**：
- `index`: 索引名称（对应数据库表名）
- `body`: 索引配置字典，包含 mappings（字段映射）和 settings（索引设置）
- `params`: 额外查询参数字典（可选）
- `headers`: 额外请求头字典（可选）
- `distributed`: 是否创建为分布式表（默认：False）
- `distribution_column`: 分布列名称（默认："id"）
- `shard_count`: 分片数量（默认：6）

**返回值**：
```python
{
    "acknowledged": True  # 是否成功
}
```

**相关模块**：
- `opensearch_sdk/client/indices/sql_generator.py`: SQL 生成逻辑
- `opensearch_sdk/client/indices/helpers.py`: 映射验证和辅助函数
- `opensearch_sdk/client/doc_utils/mapping_storage.py`: Mapping 存储

---

#### 1.2 delete() - 索引删除

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

**功能描述**: 
删除指定索引，同时删除底层表结构。委托给 `execute_delete()` 函数执行。

**内部流程**：
```
1. 参数验证
   ├── 验证索引名称合法性
   └── 支持逗号分隔的多个索引名

2. 执行删除
   └── 调用 execute_delete(self.client, index)
       ├── 生成 DROP TABLE IF EXISTS SQL
       ├── 使用 get_connection_for_operation() 获取连接
       └── 执行并返回结果
```

**参数说明**：
- `index`: 索引名称（支持逗号分隔的多个索引名）
- `params`: 额外查询参数字典（可选）
- `headers`: 额外请求头字典（可选）

**返回值**：
```python
{
    "acknowledged": True  # 是否成功
}
```

---

#### 1.3 exists() - 索引存在性检查

**函数签名**：
```python
def exists(
    self,
    *,
    index: Any,
    params: Any = None,
    headers: Any = None,
    connection: Any = None
) -> bool
```

**功能描述**: 
检查索引是否存在，查询系统表获取表信息。委托给 `execute_exists()` 函数执行。

**内部流程**：
```
1. 参数验证
   └── 验证索引名称合法性

2. 执行查询
   └── 调用 execute_exists(self.client, index, connection=connection)
       ├── 查询 pg_tables 系统表
       ├── SELECT tablename FROM pg_tables WHERE tablename = %s
       └── 返回布尔值
```

**参数说明**：
- `index`: 索引名称
- `params`: 额外查询参数字典（可选）
- `headers`: 额外请求头字典（可选）
- `connection`: 可选的连接对象（用于事务性批量操作）

**返回值**：
- `True`: 索引存在
- `False`: 索引不存在

---

#### 1.4 get_all_index_names() - 获取所有索引

**函数签名**：
```python
def get_all_index_names(self) -> List[str]
```

**功能描述**: 
查询数据库获取所有用户表的名称。

**内部流程**：
```
1. 查询系统表
   └── SELECT tablename FROM pg_tables WHERE schemaname = 'public'

2. 提取表名
   └── 遍历结果集，提取所有表名

3. 返回列表
   └── 返回字符串列表
```

**返回值**：
```python
[
    "index1",
    "index2",
    "index3"
]
```

---

### 2. SQL 生成模块 (opensearch_sdk/client/indices/sql_generator.py)

该模块负责将 OpenSearch 风格的 mapping 配置转换为 Opensearch SQL 语句。

#### 2.1 generate_create_table_sql() - 生成 CREATE TABLE SQL

**函数签名**：
```python
def generate_create_table_sql(index: str, body: Dict[str, Any]) -> Tuple[str, List[Tuple], Dict]
```

**功能描述**: 
根据索引名称和 body 配置生成 CREATE TABLE SQL，同时返回需要创建索引的字段列表和 BM25 配置。

**返回值**：
- `sql_query`: CREATE TABLE SQL 语句
- `fields_to_index`: 需要创建索引的字段列表 [(field_name, field_type, field_props), ...]
- `bm25_config`: BM25 配置字典（如果有）

**处理逻辑**：
```python
# 1. 解析 mappings.properties
properties = body.get('mappings', {}).get('properties', {})

# 2. 为每个字段生成列定义
columns = ['id VARCHAR PRIMARY KEY']  # 默认主键
for field_name, field_config in properties.items():
    field_type = field_config.get('type')
    opengauss_type = map_opensearch_type_to_opengauss(field_type)
    
    if field_type in ['float_vector', 'dense_vector']:
        dims = field_config.get('dims')
        columns.append(f"{field_name} VECTOR({dims})")
    else:
        columns.append(f"{field_name} {opengauss_type}")

# 3. 生成 SQL
sql_query = f"CREATE TABLE IF NOT EXISTS {index} ({', '.join(columns)})"
```

---

#### 2.2 generate_index_sql() - 生成 CREATE INDEX SQL

**函数签名**：
```python
def generate_index_sql(index: str, field_name: str, field_type: str, field_props: Dict) -> Optional[str]
```

**功能描述**: 
根据字段类型生成相应的 CREATE INDEX SQL。

**索引类型映射**：
- `TEXT` → BM25 全文索引: `CREATE INDEX ... USING bm25 (field text_ops)`
- `VARCHAR` → B-tree 索引: `CREATE INDEX ... ON table (field)`
- `INTEGER/REAL/TIMESTAMP/BOOLEAN` → B-tree 索引
- `VECTOR` → HNSW 向量索引: `CREATE INDEX ... USING hnsw (field vector_cosine_ops) WITH (m=16, ef_construction=64)`

**示例**：
```python
# Text 字段
sql = "CREATE INDEX IF NOT EXISTS idx_my_index_title_bm25 ON my_index USING bm25 (title text_ops)"

# Vector 字段
sql = "CREATE INDEX IF NOT EXISTS idx_my_index_embedding_hnsw ON my_index USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
```

---

#### 2.3 generate_bm25_set_sql() - 生成 BM25 SET 命令

**函数签名**：
```python
def generate_bm25_set_sql(bm25_config: Dict) -> List[str]
```

**功能描述**: 
生成 BM25 配置的 SET 命令，用于调整全文检索参数。

**示例**：
```python
set_statements = [
    "SET enable_bm25 = on",
    "SET bm25_similarity = 'okapi'"
]
```

---

### 3. 字段类型映射

#### OpenSearch 到 Opensearch 的类型映射表

```python
TYPE_MAPPING = {
    'text': 'TEXT',              # 全文检索文本
    'keyword': 'VARCHAR',        # 精确匹配字符串
    'long': 'INTEGER',           # 64 位整数
    'integer': 'INTEGER',        # 32 位整数
    'float': 'REAL',             # 32 位浮点数
    'boolean': 'BOOLEAN',        # 布尔值
    'date': 'TIMESTAMP',         # 日期时间
    'float_vector': 'VECTOR',    # 浮点向量
    'dense_vector': 'VECTOR',    # 密集向量
    'jsonb': 'JSONB'             # JSON 对象
}
```

**使用示例**：
```python
# OpenSearch 风格
{"type": "text"}
{"type": "dense_vector", "dims": 768}

# 映射到 Opensearch
TEXT
VECTOR(768)
```

---

## Mapping 配置结构详解

### OpenSearch 风格 mapping 配置

```python
mapping_config = {
    "mappings": {
        "dynamic_templates": [  # 可选：动态模板
            {
                "vector_template": {
                    "match": "*_vec",
                    "mapping": {
                        "type": "knn_vector",
                        "dimension": 1024
                    }
                }
            }
        ],
        "properties": {
            "field_name": {
                "type": "text|keyword|long|integer|float|boolean|date|float_vector|dense_vector|jsonb",
                "dims": 768,                    # 向量维度（向量字段必填）
                "similarity": "cosine|l2_norm|dot_product",  # 向量相似度算法
                "index": True/False,            # 是否为该字段创建索引（默认：True）
                "index_options": {              # HNSW 索引参数（向量字段专用）
                    "m": 16,
                    "ef_construction": 64
                }
            }
        }
    }
}
```

**Mapping 配置参数详解**：

- **type** string（必填） - 字段类型，决定字段的存储方式和查询能力
- **dims** integer（可选） - 向量维度，仅向量字段需要，范围 1-10000
- **similarity** string（可选，默认：cosine） - 向量相似度算法：cosine/l2_norm/dot_product
- **index** boolean（可选，默认：True） - 是否为该字段创建索引。
  - `True`：为该字段创建相应类型的索引（BM25、B-tree、HNSW 等）
  - `False`：不创建索引，字段仅用于数据存储，无法用于高效查询
  - **适用场景**：
    - 不需要查询的字段可设置 `index: False` 以节省存储空间
    - 仅用于展示的大文本字段建议关闭索引
    - 向量字段通常保持 `index: True` 以支持快速相似搜索
- **index_options** dict（可选） - HNSW 索引参数配置，仅向量字段有效
  - `m`：每个节点的连接数（默认：16，范围：1-100）
  - `ef_construction`：构建时的搜索深度（默认：64，范围：1-1000）

---

## 主要代码文件

- [`opensearch_sdk/client/indices_client.py`](file://d:\移动\向量\es2pw\opensearch_sdk\client\indices_client.py): IndicesClient 主实现，负责索引创建、删除、检查等操作
- [`opensearch_sdk/client/indices/helpers.py`](file://d:\移动\向量\es2pw\opensearch_sdk\client\indices\helpers.py): 映射验证和辅助函数
- [`opensearch_sdk/client/indices/sql_generator.py`](file://d:\移动\向量\es2pw\opensearch_sdk\client\indices\sql_generator.py): SQL 生成逻辑
- [`opensearch_sdk/client/indices/operations.py`](file://d:\移动\向量\es2pw\opensearch_sdk\client\indices\operations.py): 索引操作方法（delete, exists 等）
- [`opensearch_sdk/client/doc_utils/mapping_storage.py`](file://d:\移动\向量\es2pw\opensearch_sdk\client\doc_utils\mapping_storage.py): Mapping 存储到数据库表
- [`opensearch_sdk/connection/opengauss.py`](file://d:\移动\向量\es2pw\opensearch_sdk\connection\opengauss.py): OpenGaussConnection 底层连接实现

## 相关章节

- [客户端连接](./02_Client_Connection.md)
- [文档操作](./04_Document_CRUD.md)
- [查询搜索](./05_Query_Search.md)
- [向量搜索](./06_Vector_Search.md)
