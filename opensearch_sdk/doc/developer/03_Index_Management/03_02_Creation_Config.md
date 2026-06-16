# 索引创建与配置

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
| float_vector | vector | 浮点向量（别名：dense_vector, knn_vector） |
| dense_vector | vector | 密集向量（别名：float_vector, knn_vector） |
| knn_vector | vector | KNN向量（别名：float_vector, dense_vector） |
| jsonb | JSONB | JSON 对象 |

**重要限制**：

- **不支持自定义 Analyzer**：Opensearch 使用内置的中文分词器，不支持配置 `analyzer`、`search_analyzer` 等参数
- 如果在 mapping 中指定了 analyzer 配置，SDK 会静默忽略这些配置（不会报错）
- **推荐做法**：直接使用 `{"type": "text"}`，无需额外配置
- **不支持 Multi-fields（多字段映射）**：OpenSearch 的 `fields` 配置不被支持
  - 例如：`{"type": "text", "fields": {"keyword": {"type": "keyword"}}}` 中的 `fields` 会被忽略
  - `ignore_above` 等参数也不会生效
  - **推荐做法**：显式定义多个独立字段，如 `categories` (text) 和 `categories_keyword` (keyword)
- **Nested 字段有限制**：虽然支持 nested 类型和查询语法，但采用“首值策略”
  - 数组多值只存储第一个元素
  - 无法进行真正的 nested 聚合和多元素查询
- **不支持地理位置类型**：geo_point、geo_shape 等类型暂不支持

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

## 创建分布式表（Distributed Table）

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
