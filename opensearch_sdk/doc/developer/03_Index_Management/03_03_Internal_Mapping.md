# 内部实现与映射配置

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

4. 分布式表转换（可选）
   ├── 如果 distributed=True，调用 _convert_to_distributed()
   ├── 执行 create_distributed_table() 函数
   ├── 失败时自动回滚（删除已创建的表）
   └── 在创建索引之前转换，避免重复建索引

5. 索引创建
   ├── 遍历 fields_to_index 列表
   ├── 为每个字段生成对应的索引 SQL
   │   ├── text/keyword → BM25 全文索引
   │   ├── long/integer/float/date/boolean → B-tree 索引
   │   └── float_vector/dense_vector/knn_vector → 向量索引
   │       ├── method.name = "ivf" → IVFFlat 索引（支持 PQ/RabitQ 压缩）
   │       └── 默认或 method.name = "hnsw" → HNSW 索引
   └── 执行并立即提交每个 CREATE INDEX
       └── 如果是分布式表，索引会自动在各个分片上并行创建

6. BM25 配置应用（可选）
   ├── 如果有 BM25 配置，生成 SET 命令
   ├── SET bm25_k1 = <value>
   ├── SET bm25_b = <value>
   └── 应用到当前会话和数据库

7. Mapping 存储
   ├── 将 mapping 信息保存到 opensearch_mapping 表
   ├── 用于动态列类型推断
   └── 支持 dynamic_templates
```

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

**处理逻辑**：
```python
# 1. 解析 mappings.properties
properties = body.get('mappings', {}).get('properties', {})

# 2. 展开 nested 字段（首值策略）
flat_fields = expand_nested_fields(properties)
# 例如：{"user": {"type": "nested", "properties": {"name": "text"}}}
# 展开为：[("user.name", "text", {...})]

# 3. 为每个字段生成列定义
columns = ['id VARCHAR PRIMARY KEY']  # 默认主键
for field_name, field_type, field_props in flat_fields:
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

### 3. Nested 字段处理机制

Opensearch兼容接口提供了完整的 nested 字段自动处理能力，包括**索引创建时的展开**、**写入时的扁平化**和**读取时的还原**。

#### 3.1 索引创建：Nested 字段展开

**实现位置**: `opensearch_sdk/client/indices/helpers.py` - `expand_nested_fields()`

**功能**: 在创建索引时，将 nested 字段定义展开为独立的数据库列。

**处理逻辑**：
```python
def expand_nested_fields(properties: dict, prefix: str = '') -> List[Tuple[str, str, Dict]]:
    """展开 nested 字段为扁平列列表（首值策略）"""
    
    for field_name, field_props in properties.items():
        field_type = field_props.get('type', 'text')
        current_path = f"{prefix}__{field_name}" if prefix else field_name  # 使用 __ 作为分隔符
        
        if field_type == 'nested':
            # 递归展开 nested 字段
            nested_properties = field_props.get('properties', {})
            nested_fields = expand_nested_fields(nested_properties, current_path)
            fields.extend(nested_fields)
        else:
            fields.append((current_path, field_type, field_props))
    
    return fields
```

**示例**：
```python
# OpenSearch 风格的 nested 定义
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "author": {
                "type": "nested",
                "properties": {
                    "name": {"type": "text"},
                    "age": {"type": "integer"}
                }
            }
        }
    }
}

# 展开后的扁平字段（使用 __ 分隔符）
flat_fields = [
    ("title", "text", {...}),
    ("author__name", "text", {...}),
    ("author__age", "integer", {...})
]

# 生成的 SQL 列定义
CREATE TABLE my_index (
    id VARCHAR PRIMARY KEY,
    title TEXT,
    author__name TEXT,    -- 注意：使用双下划线
    author__age INTEGER
)
```

#### 3.2 写入文档：自动扁平化

**实现位置**: `opensearch_sdk/client/doc_utils/nested_handler.py` - `_flatten_nested_document()`

**功能**: 在插入或更新文档时，自动将 nested 对象/数组转换为扁平字段。

**处理逻辑**：
```python
# 原始文档（OpenSearch 格式）
doc = {
    "title": "Test Document",
    "author": [
        {"name": "Alice", "age": 25},
        {"name": "Bob", "age": 30}
    ]
}

# 自动扁平化后（首值策略：只取第一个元素）
flat_doc = {
    "title": "Test Document",
    "author__name": "Alice",  # 使用 __ 作为分隔符
    "author__age": 25
}

# 实际存储到数据库的列值
INSERT INTO my_index (id, title, author__name, author__age) 
VALUES ('1', 'Test Document', 'Alice', 25);
```

**关键特性**：
- ✅ **智能检测**：自动识别 dict 和 list 类型的嵌套对象
- ✅ **首值策略**：数组多值只取第一个元素（性能优化）
- ✅ **分隔符**：使用 `__` 连接 nested 路径（如 `author__name`）
- ✅ **空数组处理**：空数组不添加任何字段（对应数据库 NULL）

#### 3.3 读取文档：自动还原

**实现位置**: `opensearch_sdk/client/doc_utils/nested_handler.py` - `_reconstruct_nested_structure()`

**功能**: 在查询返回结果时，自动将扁平字段还原为 nested 结构。

**处理逻辑**：
```python
# 数据库返回的扁平数据
source = {
    "title": "Test Document",
    "author__name": "Alice",  # 注意：数据库中是双下划线
    "author__age": 25
}

# 自动还原后（符合 OpenSearch 格式）
result = {
    "title": "Test Document",
    "author": [  # 包装为单元素列表
        {"name": "Alice", "age": 25}
    ]
}
```

**调用点**：
- `client.search()`: 搜索结果自动还原
- `client.knn_search()`: 向量搜索结果自动还原
- `client.get()`: 获取单个文档自动还原

#### 3.4 重要限制

⚠️ **由于采用“首值策略”，有以下限制**：

1. **数组多值只存储第一个元素**
   ```python
   # 插入多个作者
   doc = {
       "author": [
           {"name": "Alice", "age": 25},
           {"name": "Bob", "age": 30}  # ⚠️ 这个会被忽略
       ]
   }
   
   # 实际只存储 Alice
   # 查询时只能看到 Alice 的信息
   ```

2. **无法进行真正的 nested 聚合和多元素查询**
   - 不支持基于 nested 数组的多元素匹配
   - 不支持 nested 聚合操作
   - 查询时只能访问第一个元素的值

3. **推荐使用替代方案**
   - **扁平化设计**：直接使用 `author_name`, `author_age` 等独立字段
   - **JSONB 类型**：使用 `{"type": "jsonb"}` 存储完整数组
   - **关联表**：一对多关系使用单独的表

#### 3.5 最佳实践

✅ **推荐做法**：

**场景 1：单值嵌套对象**
```python
# 适合使用 nested（自动展开效果好）
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "author": {
                "type": "nested",
                "properties": {
                    "name": {"type": "text"},
                    "contact_ref": {"type": "keyword"}
                }
            }
        }
    }
}

# 插入（单值）
doc = {
    "title": "Test",
    "author": {"name": "Alice", "contact_ref": "alice-contact"}
}
client.index(index="my_index", id="1", body=doc)
```

**场景 2：多值数组**
```python
# 不适合 nested，推荐使用 JSONB
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "tags": {"type": "jsonb"}  # 存储完整数组
        }
    }
}

# 插入
doc = {
    "title": "Test",
    "tags": ["python", "database", "search"]
}
client.index(index="my_index", id="1", body=doc)
```

❌ **不推荐做法**：
```python
# 避免对多值数组使用 nested（会丢失数据）
doc = {
    "authors": [  # ⚠️ 只保留第一个作者
        {"name": "Alice"},
        {"name": "Bob"}
    ]
}
```

---

### 4. 字段类型映射

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
