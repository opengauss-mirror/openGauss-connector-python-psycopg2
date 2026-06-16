# 向量搜索

本章节详细介绍 Opensearch兼容接口的向量搜索功能（kNN 搜索）。

## 概述

向量搜索允许您基于向量相似度查找最相似的文档。适用于语义搜索、图像检索、推荐系统等场景。

## 两种使用方式

Opensearch兼容接口提供两种向量搜索方式：

### 方式一：使用 `client.multi.vector_search()` 方法（推荐用于生产环境）

```python
result = client.multi.vector_search(
    table_name="my_table",
    query_vector=[0.1, 0.2, 0.3],
    top_k=10,
    metric="cosine"
)
```

**优点**：
- 功能最完整，支持 hybrid_search、fulltext_search 等高级功能
- 性能最优，专门为向量检索优化
- API 设计清晰，参数直观
- 支持更多高级特性（过滤、投影、自定义输出列等）

### 方式二：使用 `search()` 方法（推荐用于 OpenSearch 迁移）

```python
result = client.search(
    index="my_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": [0.1, 0.2, 0.3],
            "k": 10,
            "similarity": "cosine"
        }
    }
)
```

**优点**：
- 与 OpenSearch 100% API 兼容
- 无需修改现有代码
- 适合从 OpenSearch 迁移的用户

---

## client.multi.vector_search() 方法详解

### 功能描述

执行 kNN 向量相似度搜索，这是 `MultiRetrieverClient` 提供的专用向量检索接口。

### 函数签名

```python
def vector_search(
    self,
    table_name: str,
    query_vector: List[float],
    vector_column: str = "embedding",
    top_k: int = 10,
    metric: str = "l2",
    id_column: str = "id",
    filter_condition: str = None,
    filter_params: Dict = None,
    output_columns: List[str] = None,
    use_index: bool = True,
    ef_search: int = None,
    probes: int = None
) -> List[Dict]
```

### 参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| table_name | str | 是 | - | 表名/索引名 |
| query_vector | List[float] | 是 | - | 查询向量 |
| vector_column | str | 否 | embedding | 向量字段名 |
| top_k | int | 否 | 10 | 返回结果数量 |
| metric | str | 否 | l2 | 相似度算法：cosine/l2/dot_product |
| id_column | str | 否 | id | 主键列名 |
| filter_condition | str | 否 | None | SQL WHERE 条件（不含 WHERE 关键字） |
| filter_params | dict | 否 | None | 过滤参数 |
| output_columns | List[str] | 否 | None | 输出列（None 表示所有列） |
| use_index | bool | 否 | True | 是否使用索引 |
| ef_search | int | 否 | None | HNSW 搜索深度 |
| probes | int | 否 | None | IVFFlat 探测次数 |

### metric 参数说明

| 值 | 操作符 | 说明 | 适用场景 |
|:---|:---|:---|:---|
| cosine | `<=>` | 余弦相似度 | 文本、语义搜索 |
| l2 | `<->` | L2 距离（欧氏距离） | 空间距离 |
| dot_product | `<#>` | 内积（点积） | 神经网络特征 |

**注意**: HNSW 索引不支持 `dot_product` 算法。

### 返回值

```python
[
    {
        "id": "文档 ID",
        "embedding": [0.1, 0.2, 0.3],
        "title": "文档标题",
        "_distance": 0.1234  # 向量距离
    },
    ...
]
```

### 实现细节

**vector_search 方法的内部实现流程**：

```
1. 验证参数
   └── 验证表名、字段名合法性
   └── 验证 query_vector 非空
   └── 验证 top_k 范围（1-10000）
   └── 验证 metric 参数

2. 选择向量操作符
   └── cosine -> <=> (余弦相似度)
   └── l2 -> <-> (L2 距离)
   └── dot_product -> <#> (内积)

3. 构建基础 SQL
   └── SELECT {output_columns} FROM {table_name}

4. 处理过滤条件（filter_condition）
   └── 支持任意 SQL WHERE 条件
   └── 参数化查询防止 SQL 注入

5. 添加向量相似度计算
   └── ORDER BY {vector_column} {operator} %s::vector ASC

6. 限制返回结果数量
   └── LIMIT {top_k}

7. 执行查询并转换结果
   └── 使用 RealDictCursor 返回字典格式
   └── 自动解析 JSON 字段
```

**关键 SQL 生成示例**：

```python
# 基础向量搜索
"SELECT * FROM my_table ORDER BY embedding <=> %s::vector ASC LIMIT 10"

# 带过滤的向量搜索
"SELECT * FROM my_table WHERE category = %s ORDER BY embedding <=> %s::vector ASC LIMIT 10"

# 指定输出列
"SELECT id, title FROM my_table ORDER BY embedding <=> %s::vector ASC LIMIT 10"

# 使用自定义 ef_search 参数
"SET hnsw.ef_search = 100; SELECT * FROM my_table ORDER BY embedding <=> %s::vector ASC LIMIT 10"
```

---

## 使用前准备

### 1. 创建向量索引

#### 方式一：HNSW 索引（默认，推荐用于中小规模数据）

```python
# 创建包含向量字段的索引
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "embedding": {
                "type": "dense_vector",
                "dims": 768,  # 向量维度
                "similarity": "cosine",  # 相似度算法
                "index_options": {
                    "m": 16,
                    "ef_construction": 64
                }
            }
        }
    }
}

client.indices.create(index="vector_index", body=mapping)
```

#### 方式二：IVF 索引（推荐用于大规模数据）

**OpenSearch 兼容格式**：
```python
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "keyword"},
            "embedding": {
                "type": "knn_vector",
                "dimension": 768,
                "space_type": "cosinesimil",
                "method": {
                    "name": "ivf",          # IVF 索引
                    "engine": "faiss",
                    "parameters": {
                        "nlist": 100,       # 桶数量（默认 100）
                        "nprobes": 50,      # 查询时探测的桶数（可选）
                        # 可选：PQ 压缩配置
                        "encoder": {
                            "name": "pq",
                            "parameters": {
                                "m": 64,         # 子向量数量
                                "code_size": 8   # 编码位数
                            }
                        }
                    }
                }
            }
        }
    }
}

client.indices.create(index="ivf_index", body=mapping)
```

**原生 SDK API**：
```python
from opensearch_sdk.retrieval.types import IndexType, DistanceMetric, IndexConfig

# 配置 IVF 索引
index_config = IndexConfig(
    name="idx_embedding_ivf",
    column="embedding",
    index_type=IndexType.IVFFLAT,
    metric=DistanceMetric.COSINE,
    lists=100,           # IVF 桶数量
    probes=50            # 查询时探测数（可选）
)

# 创建表后手动创建索引
client.multi.execute_sql("""
    CREATE TABLE test_ivf (
        id VARCHAR PRIMARY KEY,
        embedding VECTOR(768)
    )
""")

# 创建 IVF 索引
client.multi.create_index(table_name="test_ivf", config=index_config)
```

**IVF + PQ 压缩**（超大规模数据）：
```python
index_config = IndexConfig(
    name="idx_embedding_ivf_pq",
    column="embedding",
    index_type=IndexType.IVFFLAT,
    metric=DistanceMetric.L2,
    lists=200,
    enable_pq=True,           # 启用 PQ 量化
    pq_m=64,                  # PQ 子向量数量
    pq_ksub=256               # PQ 码本大小（2^code_size）
)
```

**IVF + RabitQ 压缩**（高精度压缩）：
```python
index_config = IndexConfig(
    name="idx_embedding_ivf_rbq",
    column="embedding",
    index_type=IndexType.IVFFLAT,
    metric=DistanceMetric.COSINE,
    lists=200,
    enable_rabitq=True,              # 启用 RabitQ 量化
    rabitq_refine_type="SQ8",        # 精细化类型：SQ8/FP32/none
    rabitq_fht=True                  # 启用 FHT 随机旋转
)
```

### 2. 插入向量数据

```python
import json

# 插入向量数据
client.index(
    index="vector_index",
    id="doc1",
    body={
        "title": "Apple iPhone 15",
        "embedding": json.dumps([0.1, 0.2, 0.3] + [0.0] * 765)  # 768 维向量
    }
)

client.index(
    index="vector_index",
    id="doc2",
    body={
        "title": "Samsung Galaxy S24",
        "embedding": json.dumps([0.15, 0.25, 0.35] + [0.0] * 765)
    }
)
```

---

## 基础搜索

### 使用 client.multi.vector_search()（推荐）

```python
# 余弦相似度搜索
query_vector = [0.1, 0.2, 0.3] + [0.0] * 765

result = client.multi.vector_search(
    table_name="vector_index",
    query_vector=query_vector,
    top_k=10,
    metric="cosine"
)

print(f"找到 {len(result)} 条结果")
for item in result:
    print(f"ID: {item['id']}, Distance: {item.get('_distance', 'N/A')}")
```

### 使用 search()（OpenSearch 兼容）

```python
# 余弦相似度搜索
query_vector = [0.1, 0.2, 0.3] + [0.0] * 765

result = client.search(
    index="vector_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 10,
            "similarity": "cosine"
        }
    }
)

print(f"找到 {result['hits']['total']['value']} 条结果")
for hit in result['hits']['hits']:
    print(f"ID: {hit['_id']}, Score: {hit['_score']:.4f}")
```

### L2 距离搜索

#### 使用 vector_search()

```python
result = client.multi.vector_search(
    table_name="vector_index",
    query_vector=query_vector,
    top_k=10,
    metric="l2"
)
```

#### 使用 search()

```python
result = client.search(
    index="vector_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 10,
            "similarity": "l2_norm"
        }
    }
)
```

### 内积搜索

**注意**: HNSW 索引不支持内积算法，仅在某些场景下可用。

#### 使用 vector_search()

```python
result = client.multi.vector_search(
    table_name="vector_index",
    query_vector=query_vector,
    top_k=10,
    metric="dot_product"
)
```

#### 使用 search()

```python
result = client.search(
    index="vector_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 10,
            "similarity": "dot_product"
        }
    }
)
```

---

## 使用 search() 方法进行向量搜索

### OpenSearch 风格接口

`search()` 方法支持直接在 body 中传入 knn 查询，与 OpenSearch 完全兼容：

```python
result = client.search(
    index="my_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": [0.1, 0.2, 0.3],
            "k": 10,
            "similarity": "cosine"
        }
    }
)
```

### 参数说明

- **field** str（必填） - 向量字段名
- **query_vector** List[float]（必填） - 查询向量
- **k** int（可选，默认：10） - 返回结果数量
- **num_candidates** int（可选） - 候选集大小
- **filter** dict（可选） - 过滤条件
- **similarity** str（可选，默认：cosine） - 相似度算法 |

### 带过滤的示例

```python
result = client.search(
    index="products",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 10,
            "filter": {
                "term": {"category": "electronics"}
            },
            "similarity": "cosine"
        }
    }
)
```

### 返回值

与 `knn_search()` 方法返回相同的格式：

```python
{
    "hits": {
        "total": {"value": 数量，"relation": "eq"},
        "hits": [
            {
                "_index": "索引名",
                "_id": "文档 ID",
                "_score": 相似度分数（基于真实距离计算）,
                "_source": {文档内容}
            }
        ]
    }
}
```

**注意**：`_score` 现在基于真实的向量距离计算，而非排序位置。

---

### 带过滤的搜索

#### 使用 vector_search()（推荐）

```python
# 按关键词过滤
result = client.multi.vector_search(
    table_name="vector_index",
    query_vector=query_vector,
    top_k=10,
    metric="cosine",
    filter_condition="category = %s",
    filter_params=("electronics",)
)
```

#### 使用 search()

```python
result = client.search(
    index="vector_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 10,
            "filter": {"term": {"category": "electronics"}},
            "similarity": "cosine"
        }
    }
)
```

### knn.filter 与 bool.query.filter 合并（2026-03 更新）

**最新更新**：SDK 现在支持自动合并 knn.filter 和 bool.query.filter，解决两者同时存在时的冲突。

**问题场景**：
```python
# 之前的限制：knn.filter 和 bool.filter 无法同时使用
body = {
    "query": {
        "bool": {
            "filter": [{"term": {"category": "tech"}}]
        }
    },
    "knn": {
        "field": "embedding",
        "query_vector": [0.1, 0.2, ...],
        "k": 10,
        "filter": {"term": {"status": "published"}}  # 会与 bool.filter 冲突
    }
}
```

**解决方案**：新增 `_merge_knn_and_bool_filters()` 方法

```python
# 现在 SDK 会自动合并两个过滤条件
body = {
    "query": {
        "bool": {
            "must": [
                {"term": {"category": "tech"}}
            ]
        }
    },
    "knn": {
        "field": "embedding",
        "query_vector": [0.1, 0.2, ...],
        "k": 10,
        "filter": {"term": {"status": "published"}}
    }
}

# 实际执行的 SQL:
# WHERE category = 'tech' AND status = 'published'
# ORDER BY embedding <=> %s::vector ASC LIMIT 10
```

**支持的格式**：
- `knn.filter: {"term": {...}}` - 单个条件
- `bool.filter: [{"term": ...}, {"range": ...}]` - 数组
- `bool: {"must": [...], "filter": [...]}` - 嵌套 bool

**实现细节**：
```python
def _merge_knn_and_bool_filters(
    knn_filter: Optional[Dict], 
    bool_query_filter: Optional[Dict]
) -> Dict:
    """合并两个过滤条件为 AND 逻辑"""
    # 1. 解析 knn.filter
    # 2. 解析 bool.filter
    # 3. 合并为 AND 连接
    # 4. 返回统一的过滤条件
```

### 组合过滤

#### 使用 vector_search()

```python
result = client.multi.vector_search(
    table_name="vector_index",
    query_vector=query_vector,
    top_k=10,
    metric="cosine",
    filter_condition="category = %s AND in_stock = %s",
    filter_params=("electronics", True)
)
```

#### 使用 search()

```python
result = client.search(
    index="vector_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 10,
            "filter": {
                "bool": {
                    "must": [
                        {"term": {"category": "electronics"}},
                        {"term": {"in_stock": True}}
                    ]
                }
            },
            "similarity": "cosine"
        }
    }
)
```

---

## 代码示例

### 完整示例

```
import json
from opensearch_sdk import OpenGauss

client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)

# 1. 创建向量索引
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "category": {"type": "keyword"},
            "embedding": {
                "type": "dense_vector",
                "dims": 4,
                "similarity": "cosine"
            }
        }
    }
}
client.indices.create(index="products", body=mapping)

# 2. 插入示例数据
products = [
    {"id": "1", "title": "iPhone 15", "category": "electronics", "embedding": [1.0, 0.2, 0.1, 0.0]},
    {"id": "2", "title": "MacBook Pro", "category": "electronics", "embedding": [0.9, 0.3, 0.2, 0.1]},
    {"id": "3", "title": "Python Book", "category": "books", "embedding": [0.1, 0.8, 0.9, 0.2]},
    {"id": "4", "title": "Java Book", "category": "books", "embedding": [0.1, 0.7, 0.8, 0.3]},
]

for p in products:
    client.index(
        index="products",
        id=p["id"],
        body={
            "title": p["title"],
            "category": p["category"],
            "embedding": json.dumps(p["embedding"])
        }
    )

# 3. 执行向量搜索

# 方式一：使用 vector_search()（推荐）
query_vector = [1.0, 0.2, 0.1, 0.0]

result = client.multi.vector_search(
    table_name="products",
    query_vector=query_vector,
    top_k=3,
    metric="cosine"
)

print("vector_search() 搜索结果:")
for item in result:
    print(f"  {item['id']}: {item.get('title', 'N/A')} (distance: {item.get('_distance', 'N/A'):.4f})")

# 只搜索电子产品
result = client.multi.vector_search(
    table_name="products",
    query_vector=query_vector,
    top_k=3,
    metric="cosine",
    filter_condition="category = %s",
    filter_params=("electronics",)
)

print("\n电子产品搜索结果 (vector_search):")
for item in result:
    print(f"  {item['id']}: {item.get('title', 'N/A')} (distance: {item.get('_distance', 'N/A'):.4f})")

# 方式二：使用 search()（OpenSearch 兼容）
query_vector = [1.0, 0.2, 0.1, 0.0]

result = client.search(
    index="products",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 3,
            "similarity": "cosine"
        }
    }
)

print("\nsearch() 方法搜索结果:")
for hit in result['hits']['hits']:
    print(f"  {hit['_id']}: {hit['_source'].get('title', 'N/A')} (score: {hit['_score']:.4f})")

# 只搜索电子产品
result = client.search(
    index="products",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 3,
            "filter": {"term": {"category": "electronics"}},
            "similarity": "cosine"
        }
    }
)

print("\n电子产品搜索结果 (search):")
for hit in result['hits']['hits']:
    print(f"  {hit['_id']}: {hit['_source'].get('title', 'M/A')} (score: {hit['_score']:.4f})")

---

## 数据结构与请求体详解

### 1. Mapping 配置结构

#### 1.1 完整的向量索引 Mapping

```python
mapping = {
    "mappings": {
        "properties": {
            # 文本字段 - 用于全文搜索
            "title": {
                "type": "text",           # 文本类型，会被分词
                "analyzer": "standard"     # 使用标准分词器（可选）
            },
            
            # 关键词字段 - 用于精确匹配和过滤
            "category": {
                "type": "keyword"         # 不分词，精确匹配
            },
            
            # 数值字段 - 用于范围查询和排序
            "price": {
                "type": "float"          # 浮点数类型
            },
            
            # 向量字段 - 核心配置
            "embedding": {
                "type": "dense_vector",   # 密集向量类型
                "dims": 768,              # 向量维度（1-10000）
                "similarity": "cosine",   # 相似度算法
                "index_options": {        # HNSW 索引配置（可选）
                    "m": 16,              # 每个节点的连接数（1-100）
                    "ef_construction": 64, # 构建时的搜索深度（1-1000）
                    "ef_search": 256      # 搜索时的搜索深度（1-1000）
                }
            }
        }
    }
}
```

#### 1.2 向量字段配置参数详解

**HNSW 索引参数**：

| 参数 | 默认值 | 范围 | 说明 |
|:---|:---:|:---:|:---|
| dims | 必填 | 1-10000 | 向量维度 |
| similarity | cosine | cosine/l2_norm/dot_product | 相似度算法 |
| m | 16 | 1-100 | HNSW 参数 M |
| ef_construction | 64 | 1-1000 | HNSW 参数 ef_construction |
| ef_search | 256 | 1-1000 | HNSW 参数 ef_search（可选）|

**IVF 索引参数**（OpenSearch 格式）：

| 参数 | 默认值 | 范围 | 说明 |
|:---|:---:|:---:|:---|
| dimension | 必填 | 1-10000 | 向量维度 |
| space_type | cosinesimil | cosinesimil/l2/innerproduct | 相似度算法 |
| method.name | ivf | ivf/hnsw | 索引类型 |
| parameters.nlist | 100 | 1-10000 | IVF 桶数量（lists） |
| parameters.nprobes | nlist/30 | 1-nlist | 查询时探测的桶数（probes） |
| parameters.encoder.name | - | pq/rabitq | 量化压缩方法（可选） |
| parameters.encoder.m | - | 1-dims | PQ 子向量数量 |
| parameters.encoder.code_size | 8 | 4/8/16 | PQ 编码位数 |

**IVF 索引参数**（SDK API）：

| 参数 | 默认值 | 范围 | 说明 |
|:---|:---:|:---:|:---|
| lists | 100 | 1-10000 | IVF 桶数量 |
| probes | lists/30 | 1-lists | 查询时探测数 |
| enable_pq | False | - | 是否启用 PQ 量化 |
| pq_m | dims/2 | 1-dims | PQ 子向量数量 |
| pq_ksub | 256 | - | PQ 码本大小（2^code_size） |
| enable_rabitq | False | - | 是否启用 RabitQ 量化 |
| rabitq_refine_type | FP32 | SQ8/FP32/none | 精细化类型 |
| rabitq_fht | False | - | 是否启用 FHT 随机旋转 |

---

## 相关章节

- [查询与搜索](./05_Query_Search.md) - 文本搜索
- [文档操作](./04_Document_CRUD.md) - 文档 CRUD
- [最佳实践](./07_Best_Practices.md) - 最佳实践

---

## 外部接口说明

### 1. 客户端入口

```python
from opensearch_sdk import OpenGauss

client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)
```

### 2. 外部调用接口

#### 2.1 索引创建接口 (client.indices.create)

```python
client.indices.create(
    index="my_index",
    body={
        "mappings": {
            "properties": {
                "title": {"type": "text"},
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

#### 2.2 向量搜索接口 (client.multi.vector_search)

```python
result = client.multi.vector_search(
    table_name="my_index",
    query_vector=[0.1, 0.2, ...],
    top_k=10,
    metric="cosine",
    filter_condition="category = %s",
    filter_params=("electronics",)
)
```

#### 2.3 OpenSearch 风格搜索接口 (client.search)

```python
result = client.search(
    index="my_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": [0.1, 0.2, ...],
            "k": 10,
            "similarity": "cosine",
            "filter": {"term": {"category": "electronics"}}
        }
    }
)
```

#### 2.4 底层 kNN 接口 (client.knn_search)

```python
result = client.knn_search(
    index="my_index",
    field="embedding",
    query_vector=[0.1, 0.2, ...],
    k=10,
    similarity="cosine",
    ef_search=256
)
```

---

## 内部接口说明

### 1. SearchOpsMixin 类 (opensearch_sdk/client/search_ops.py)

SearchOpsMixin 是搜索操作的核心 Mixin 类，提供全文搜索、向量搜索和混合搜索功能。

#### 1.1 knn_search() - 底层 kNN实现

**函数签名**：
```python
def knn_search(
    self,
    index: str,
    field: str,
    query_vector: List[float],
    k: int = 10,
    num_candidates: int = None,
    filter_query: Dict[str, Any] = None,
    similarity: str = 'cosine',
    ef_search: int = None
) -> Any
```

**功能描述**: 
执行 kNN向量相似度搜索，生成 SQL并返回标准化结果。

**内部流程**：
```
1. 参数校验
   ├── 验证索引名合法性（使用 _validate_identifier）
   ├── 验证字段名合法性
   ├── 验证 query_vector 非空且为列表
   ├── 验证 k 值范围（1-10000）
   └── 验证 similarity 参数有效性

2. 选择向量操作符
   ├── cosine → <=> (余弦相似度，越接近 0 越相似)
   ├── l2_norm → <-> (L2 距离，越小越相似)
   └── dot_product → <#> (负内积，越大越相似)

3. 构建向量查询 SQL
   ├── SELECT *, {field} {operator} %s::vector AS distance
   ├── FROM {index}
   ├── WHERE {filter_conditions}（如有过滤）
   ├── ORDER BY {field} {operator} %s::vector ASC/DESC
   └── LIMIT {k}

4. 设置 HNSW 参数（如有）
   └── SET hnsw.ef_search = {ef_search}

5. 执行查询
   ├── 执行参数化 SQL
   └── 获取结果集

6. 处理结果
   ├── 获取列名和数据行
   ├── 解析 JSON 字段
   ├── 计算 _score（基于真实距离）
   └── 返回标准化响应格式
```

**参数说明**：
- `index`: 索引名称
- `field`: 向量字段名
- `query_vector`: 查询向量（List[float]）
- `k`: 返回结果数量（默认 10）
- `num_candidates`: 候选集大小（可选，用于优化性能）
- `filter_query`: 过滤条件字典（可选）
- `similarity`: 相似度算法（cosine/l2_norm/dot_product）
- `ef_search`: HNSW 搜索深度（可选）

**向量操作符映射**：
```python
SIMILARITY_OPS = {
    'cosine': '<=>',        # 余弦相似度
    'l2_norm': '<->',       # L2 距离
    'dot_product': '<#>'    # 负内积
}
```

**_score 计算逻辑**：
```python
def calculate_score(distance: float, similarity: str) -> float:
    if similarity == 'cosine':
        return 1.0 - distance  # cosine 距离转相似度 (0-1 范围)
    elif similarity == 'l2_norm':
        return 1.0 / (1.0 + distance)  # L2 距离转相似度
    elif similarity == 'dot_product':
        score = 1.0 / (1.0 - distance) if distance < 1 else 1.0 / (1.0 + abs(distance))
        return score
    else:
        return 1.0 / (1.0 + distance)  # 默认 fallback
```

**返回值**：
```python
{
    "hits": {
        "total": {"value": 10, "relation": "eq"},
        "hits": [
            {
                "_index": "my_index",
                "_id": "doc1",
                "_score": 0.9876,
                "_source": {
                    "title": "Document 1",
                    "embedding": "[...]"
                }
            }
        ]
    }
}
```

**相关方法**：
- `_handle_knn_query()`: kNN查询路由
- `_get_similarity_ops()`: 获取向量操作符

---

#### 1.2 _handle_knn_query() - kNN查询路由

**函数签名**：
```python
def _handle_knn_query(
    self,
    index: str,
    knn_config: Dict[str, Any]
) -> Any
```

**功能描述**: 
处理 OpenSearch 风格的 knn 查询，提取参数并调用 knn_search。

**处理逻辑**：
```python
def _handle_knn_query(self, index, knn_config):
    # 提取 knn 配置参数
    field = knn_config.get('field')
    query_vector = knn_config.get('query_vector')
    k = knn_config.get('k', 10)
    similarity = knn_config.get('similarity', 'cosine')
    filter_query = knn_config.get('filter')
    num_candidates = knn_config.get('num_candidates')
    
    # 调用底层 knn_search
    return self.knn_search(
        index=index,
        field=field,
        query_vector=query_vector,
        k=k,
        similarity=similarity,
        filter_query=filter_query,
        num_candidates=num_candidates
    )
```

---

### 2. MultiRetrieverClient 类 (opensearch_sdk/client/vector_client.py)

MultiRetrieverClient 是高级检索客户端，提供更丰富的向量搜索功能。

#### 2.1 vector_search() - 高级向量搜索

**函数签名**：
```python
def vector_search(
    self,
    table_name: str,
    query_vector: List[float],
    vector_column: str = "embedding",
    top_k: int = 10,
    metric: str = "l2",
    id_column: str = "id",
    filter_condition: str = None,
    filter_params: Dict = None,
    output_columns: List[str] = None,
    use_index: bool = True,
    ef_search: int = None,
    probes: int = None
) -> List[Dict]
```

**功能描述**: 
基于 VectorRetriever 的高级向量搜索接口。

**内部流程**：
```
1. 参数验证和预处理
   ├── 验证表名合法性
   ├── 验证 query_vector 非空
   ├── 验证 top_k 范围
   └── 验证 metric 参数

2. 创建 VectorRetriever实例
   └── 使用配置初始化检索器

3. 构建检索参数
   ├── 基础参数：table_name, query_vector, vector_column
   ├── 过滤参数：filter_condition, filter_params
   ├── 输出控制：output_columns
   └── 索引参数：use_index, ef_search, probes

4. 执行检索
   └── 调用 retriever.retrieve() 方法

5. 格式化结果
   ├── 转换为字典列表
   └── 返回最终结果
```

**参数说明**：
- `table_name`: 表名/索引名
- `query_vector`: 查询向量（List[float]）
- `vector_column`: 向量字段名（默认 "embedding"）
- `top_k`: 返回结果数量（默认 10）
- `metric`: 相似度算法（cosine/l2/dot_product）
- `id_column`: 主键列名（默认 "id"）
- `filter_condition`: SQL WHERE 条件（不含 WHERE 关键字）
- `filter_params`: 过滤参数字典
- `output_columns`: 输出列列表（None 表示所有列）
- `use_index`: 是否使用索引（默认 True）
- `ef_search`: HNSW 搜索深度（可选）
- `probes`: IVFFlat 探测次数（可选）

**metric 参数映射**：
```python
METRIC_MAP = {
    'cosine': 'cosine',      # 余弦相似度
    'l2': 'l2',             # L2 距离
    'dot_product': 'dot_product'  # 内积
}
```

**过滤条件示例**：
```python
# 单个条件
filter_condition="category = %s",
filter_params={"category": "electronics"}

# 多个条件
filter_condition="category = %s AND price > %s",
filter_params={"category": "electronics", "min_price": 100}
```

**返回值**：
```python
[
    {
        "id": "doc1",
        "title": "Product 1",
        "price": 99.99,
        "distance": 0.123,
        "score": 0.877
    },
    ...
]
```

**优势**：
- 支持 hybrid_search（混合搜索）
- 支持 fulltext_search（全文搜索）
- 支持过滤条件和输出列控制
- 专门为向量检索优化

---

### 3. IndicesClient 类 (opensearch_sdk/client/indices.py)

索引管理客户端，包含向量索引创建逻辑。

#### 3.1 create() - 索引创建

**函数签名**：
```python
def create(
    self,
    index: Any = None,
    body: Any = None,
    params: Any = None,
    headers: Any = None,
    **kwargs: Any
) -> Any
```

**功能描述**:
1. 解析 OpenSearch 风格的 mapping 配置
2. 创建表结构（CREATE TABLE）
3. 根据字段类型创建相应索引（BM25、B-tree、HNSW/IVF）
4. 使用现代连接管理模式，无需手动重连

**向量索引创建流程**：
```
1. 解析 mapping 中的向量字段
   ├── 提取 type: dense_vector/float_vector/knn_vector
   ├── 提取 dims/dimension: 向量维度
   ├── 提取 similarity/space_type: 相似度算法
   └── 提取 method.name: 索引类型（HNSW vs IVF）
       ├── HNSW: 提取 index_options (m, ef_construction)
       └── IVF: 提取 parameters (nlist, nprobes, encoder)

2. 生成 CREATE TABLE SQL
   └── VECTOR(dims) 类型定义

3. 创建向量索引
   ├── HNSW 索引
   │   ├── 选择向量操作符（<=>/<->/<#>）
   │   ├── 设置 HNSW 参数（m, ef_construction）
   │   └── 执行 CREATE INDEX ... USING hnsw
   └── IVF 索引
       ├── 选择向量操作符
       ├── 设置 IVF 参数（lists, probes）
       ├── 可选：PQ/RabitQ 压缩配置
       └── 执行 CREATE INDEX ... USING ivfflat

4. 连接管理
   - 使用 `get_connection_for_operation()` 上下文管理器
   - DDL 操作后自动提交事务
   - 无需手动重连，连接池自动管理
```

**生成的 SQL 示例**：

**HNSW 索引**：
```sql
-- 创建表
CREATE TABLE IF NOT EXISTS my_index (
    id VARCHAR PRIMARY KEY,
    title TEXT,
    embedding VECTOR(768)
)

-- 创建 HNSW 索引（注意：使用 vector_cosine_ops/vector_l2_ops/vector_ip_ops）
CREATE INDEX IF NOT EXISTS idx_my_index_embedding_hnsw
ON my_index USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64)
```

**IVF 索引**：
```sql
-- 创建表
CREATE TABLE IF NOT EXISTS my_ivf_index (
    id VARCHAR PRIMARY KEY,
    content TEXT,
    embedding VECTOR(768)
)

-- 创建 IVF 索引（带 PQ 压缩）
CREATE INDEX IF NOT EXISTS idx_my_ivf_index_embedding_ivf
ON my_ivf_index USING ivfflat (embedding vector_cosine_ops)
WITH (
    lists = 200,
    enable_pq = on,
    pq_m = 64,
    pq_ksub = 256
)
```

**IVF 索引（带 RabitQ 压缩）**：
```sql
CREATE INDEX IF NOT EXISTS idx_embedding_ivf_rbq
ON my_ivf_index USING ivfflat (embedding vector_l2_ops)
WITH (
    lists = 200,
    enable_rabitq = on,
    rabitq_refine_type = 'SQ8',
    rabitq_fht = on
)
```

**相关方法**：
- `_parse_mapping()`: 解析 mapping 配置
- `_create_table()`: 创建表结构
- `_create_indexes()`: 创建索引
- 连接管理由 `connection.get_connection_for_operation()` 统一处理

---

### 4. 辅助方法和工具函数

#### 4.1 _get_similarity_ops() - 获取向量操作符

**函数签名**：
```python
def _get_similarity_ops(similarity: str) -> str
```

**功能描述**: 
根据相似度算法名称返回对应的向量操作符。

**映射关系**：
```python
def _get_similarity_ops(similarity):
    OPS_MAP = {
        'cosine': '<=>',        # 余弦相似度
        'l2_norm': '<->',       # L2 距离
        'dot_product': '<#>'    # 负内积
    }
    return OPS_MAP.get(similarity, '<=>')  # 默认 cosine
```

---

#### 4.2 _validate_vector_dimension() - 向量维度验证

**函数签名**：
```python
def _validate_vector_dimension(dims: int) -> None
```

**功能描述**: 
验证向量维度的合法性。

**验证规则**：
- 必须是正整数
- 范围：1 <= dims <= 10000

**异常**：
- `ValueError`: 维度不合法时抛出

---

#### 4.3 _calculate_score() - _score计算

**函数签名**：
```python
def _calculate_score(distance: float, similarity: str) -> float
```

**功能描述**: 
根据距离值和相似度算法计算 _score。

**计算逻辑**：
```python
def _calculate_score(distance, similarity):
    if similarity == 'cosine':
        # cosine 距离范围 [-1, 1]，转换为 [0, 1] 的相似度
        return 1.0 - distance
    elif similarity == 'l2_norm':
        # L2 距离 >= 0，转换为 (0, 1] 的相似度
        return 1.0 / (1.0 + distance)
    elif similarity == 'dot_product':
        # 内积可正可负，特殊处理
        if distance < 1:
            return 1.0 / (1.0 - distance)
        else:
            return 1.0 / (1.0 + abs(distance))
    else:
        # 默认 fallback
        return 1.0 / (1.0 + distance)
```

**为什么需要转换？**
- OpenSearch/Opensearch 返回的是原始距离值
- 用户期望看到的是相似度分数（越高越好）
- _score 统一为 [0, 1] 范围，便于理解和使用


---

## 数据结构与请求体详解（开发者参考）

### 1. Mapping 配置深度解析

#### 1.1 完整的向量索引 Mapping 结构

```python
mapping = {
    "mappings": {
        "properties": {
            # 文本字段 - 用于全文搜索（BM25）
            "title": {
                "type": "text",           # 文本类型，会被分词器处理
                "analyzer": "standard"     # 标准分词器（可选，默认 standard）
            },
            
            # 关键词字段 - 用于精确匹配、过滤和聚合
            "category": {
                "type": "keyword"         # 不分词，整个字符串作为一个词条
            },
            
            # 数值字段 - 用于范围查询、排序和聚合
            "price": {
                "type": "float"          # 单精度浮点数（32 位）
            },
            
            # 整数字段 - 用于计数、过滤等
            "stock": {
                "type": "integer"        # 32 位有符号整数
            },
            
            # 日期字段 - 用于时间范围查询
            "created_at": {
                "type": "date",          # ISO 8601 格式日期时间
                "format": "strict_date_optional_time||epoch_millis"
            },
            
            # JSON 对象字段 - 存储结构化数据
            "attributes": {
                "type": "jsonb",          # PostgreSQL JSONB 类型
                "properties": {           # 可选的嵌套字段定义
                    "color": {"type": "keyword"},
                    "size": {"type": "keyword"}
                }
            },
            
            # 向量字段 - 核心配置，用于相似度搜索
            "embedding": {
                "type": "dense_vector",   # 密集向量类型（768 维常用）
                "dims": 768,              # 向量维度（必填，1-10000）
                "similarity": "cosine",   # 相似度算法（默认 cosine）
                "index_options": {        # HNSW 索引配置（可选但推荐）
                    "m": 16,              # 每个节点的连接数（1-100，默认 16）
                    "ef_construction": 64, # 构建时的搜索深度（1-1000，默认 64）
                    "ef_search": 256      # 搜索时的搜索深度（1-1000，默认 256）
                }
            }
        }
    }
}
```

#### 1.2 向量字段参数详解

- **type** string（必填） - `dense_vector` 或 `float_vector`
- **dims** integer（必填） - 向量维度，范围 1-10000，创建后不可修改
- **similarity** string（可选，默认：cosine） - 相似度算法：cosine/l2_norm/dot_product
- **index_options.m** integer（可选，默认：16） - HNSW 参数 M，范围 1-100，控制节点连接数。越大记忆越好，但占用更多内存
- **index_options.ef_construction** integer（可选，默认：64） - 构建时的搜索深度，范围 1-1000，越大索引质量越高，但建索引越慢
- **index_options.ef_search** integer（可选，默认：256） - 搜索时的搜索深度，范围 1-1000，越大搜索越准确，但速度越慢

#### 1.3 不同场景的推荐配置

**场景 1：语义搜索（768 维 BERT 向量）**
```python
{
    "embedding": {
        "type": "dense_vector",
        "dims": 768,
        "similarity": "cosine",
        "index_options": {
            "m": 16,
            "ef_construction": 100,
            "ef_search": 256
        }
    }
}
```
- **适用场景**：文本语义相似度、问答系统
- **特点**：平衡性能和精度

**场景 2：图像检索（高维向量）**
```python
{
    "embedding": {
        "type": "dense_vector",
        "dims": 2048,
        "similarity": "l2_norm",
        "index_options": {
            "m": 32,
            "ef_construction": 200,
            "ef_search": 512
        }
    }
}
```
- **适用场景**：图像特征向量检索
- **特点**：高维度需要更大的 m 和 ef_search

**场景 3：快速近似搜索（低维向量）**
```python
{
    "embedding": {
        "type": "dense_vector",
        "dims": 128,
        "similarity": "cosine",
        "index_options": {
            "m": 8,
            "ef_construction": 40,
            "ef_search": 64
        }
    }
}
```
- **适用场景**：对延迟敏感的应用
- **特点**：牺牲少量精度换取更快的速度

**场景 4：大规模数据（百万级以上）**
```python
{
    "embedding": {
        "type": "knn_vector",
        "dimension": 768,
        "space_type": "cosinesimil",
        "method": {
            "name": "ivf",
            "parameters": {
                "nlist": 500,      # 更多的桶
                "encoder": {
                    "name": "pq",
                    "parameters": {
                        "m": 64,
                        "code_size": 8
                    }
                }
            }
        }
    }
}
```
- **适用场景**：百万级以上的向量检索
- **特点**：PQ 压缩大幅减少内存占用，适合超大规模

---

### HNSW vs IVF 索引对比

| 特性 | HNSW | IVF |
|:---|:---|:---|
| **数据结构** | 图结构（多跳） | 倒排索引（分区） |
| **适用规模** | 中小规模（<100 万） | 大规模（>100 万） |
| **查询速度** | 非常快（微秒级） | 较快（毫秒级） |
| **内存占用** | 较高（完整向量） | 较低（可压缩） |
| **构建速度** | 较慢 | 较快 |
| **压缩支持** | PQ/RabitQ | PQ/RabitQ |
| **精度** | 完全兼容 | 高 |
| **参数调优** | m, ef_construction, ef_search | lists, probes |

**选择建议**：
- **< 10 万向量**：优先选择 HNSW（速度快，精度高）
- **10 万 -100 万向量**：根据内存和速度需求选择
- **> 100 万向量**：优先选择 IVF+PQ（内存友好）
- **实时性要求高**：HNSW（微秒级响应）
- **内存受限**：IVF+PQ（压缩比可达 10-20 倍）

---

### 2. 请求体结构详解

#### 2.1 vector_search() 方法的参数结构

```python
result = client.multi.vector_search(
    table_name="products",          # 表名/索引名（必填）
    query_vector=[0.1, 0.2, ...],   # 查询向量（必填，List[float]）
    vector_column="embedding",      # 向量字段名（默认：embedding）
    top_k=10,                       # 返回数量（默认：10，范围：1-10000）
    metric="cosine",                # 相似度算法（默认：l2）
    id_column="id",                 # 主键列名（默认：id）
    filter_condition="category = %s AND price > %s",  # SQL WHERE 条件（不含 WHERE）
    filter_params={"category": "electronics", "min_price": 100},  # 参数化查询参数
    output_columns=["id", "title", "price"],  # 输出列（None 表示所有列）
    use_index=True,                 # 是否使用索引（默认：True）
    ef_search=256,                  # HNSW 搜索深度（可选）
    probes=3                        # IVFFlat 探测次数（可选）
)
```

**参数详细说明**：

- **table_name** str（必填） - 表名/索引名
- **query_vector** List[float]（必填） - 查询向量，必须是指定维度的 float 列表
- **vector_column** str（可选，默认：embedding） - 向量字段名，需与 mapping 中一致
- **top_k** int（可选，默认：10） - 返回结果数量，范围 1-10000
- **metric** str（可选，默认：l2） - 相似度算法：cosine/l2/dot_product
- **id_column** str（可选，默认：id） - 主键列名，用于唯一标识
- **filter_condition** str（可选） - SQL WHERE 条件（不含 WHERE 关键字），支持参数化
- **filter_params** dict（可选） - 过滤参数字典，防止 SQL 注入
- **output_columns** List[str]（可选） - 输出列列表，None 表示所有列
- **use_index** bool（可选，默认：True） - 是否使用 HNSW 索引，False 则暴力扫描
- **ef_search** int（可选） - HNSW 搜索深度，不设置则使用索引默认值
- **probes** int（可选） - IVFFlat 索引的探测次数

#### 2.2 search() 方法的 knn 查询结构（OpenSearch 兼容）

```python
result = client.search(
    index="products",
    body={
        "knn": {
            "field": "embedding",           # 向量字段名（必填）
            "query_vector": [0.1, 0.2, ...], # 查询向量（必填）
            "k": 10,                         # 返回数量（默认：10）
            "num_candidates": 100,           # 候选集大小（可选）
            "filter": {                      # 过滤器（可选）
                "bool": {
                    "must": [
                        {"term": {"category": "electronics"}},
                        {"range": {"price": {"gte": 100}}}
                    ]
                }
            },
            "similarity": "cosine"           # 相似度算法（默认：cosine）
        },
        "_source": ["id", "title", "price"], # 返回的字段（可选）
        "size": 10                           # 返回数量（可选）
    }
)
```

**knn 配置参数详解**：

- **field** str（必填） - 向量字段名称
- **query_vector** List[float]（必填） - 查询向量
- **k** int（可选，默认：10） - KNN 算法的候选集大小
- **num_candidates** int（可选） - 候选集大小，影响性能
- **filter** dict（可选） - OpenSearch 风格的过滤器
- **similarity** str（可选，默认：cosine） - 相似度算法

**k 与 size 的区别**：

在 OpenSearch 兼容的向量检索中，`k` 和 `size` 有不同的作用：

| 参数 | 作用阶段 | 含义 | 影响 |
|:---:|:---:|:---:|:---:|
| **k** | 向量检索阶段 | KNN 算法返回的候选集大小 | 决定从索引中找到多少个最相似的向量 |
| **size** | 后处理阶段 | 最终返回给用户的数量 | 决定过滤后返回多少条结果 |

**工作流程**：
```
1. 向量检索 (使用 k)
   └─> 从索引中找到 k 个最相似的候选向量
   
2. 应用过滤条件 (可选)
   └─> 可能过滤掉部分候选
   
3. 返回结果 (使用 size)
   └─> 从候选中取前 size 个返回
```

**最佳实践**：
- **无过滤时**: `k = size`（直接返回 top-k）
- **有过滤时**: `k > size`（建议 `k = 5-10 × size`），确保过滤后仍有足够结果
- **性能考虑**: `k` 越大，计算量越大，但召回率越高

**示例**：
```python
# 示例 1：k = size（最常见）
result = client.search(
    index="products",
    body={
        "knn": {
            "embedding": {
                "vector": query_vector,
                "k": 10  # 找 10 个最相似的
            }
        },
        "size": 10  # 返回 10 个结果
    }
)

# 示例 2：k > size（推荐用于生产环境）
result = client.search(
    index="products",
    body={
        "knn": {
            "embedding": {
                "vector": query_vector,
                "k": 100  # 先找 100 个候选
            }
        },
        "size": 10,  # 只返回前 10 个
        "query": {
            "bool": {
                "filter": [
                    {"term": {"category": "electronics"}}
                ]
            }
        }
    }
)
# 实际返回: min(k, size) = 10 个结果
```

**Opensearch兼容接口实现逻辑**：
```python
# 如果指定了 size，使用 min(k, size) 作为实际的 k 值
if size is not None and isinstance(size, int) and size > 0:
    effective_k = min(k, size)
else:
    effective_k = k
```

#### 2.3 hybrid_search() 混合搜索结构（高级功能）

```python
result = client.hybrid_search(
    index="products",
    query_text="machine learning",    # 文本查询（用于全文搜索）
    text_field="title",               # 文本字段名
    query_vector=[0.1, 0.2, ...],     # 向量查询
    vector_field="embedding",         # 向量字段名
    top_k=10,                         # 最终返回数量
    coarse_top_k=50,                  # 每路召回数量（默认：50）
    rrf_k=60,                         # RRF 融合参数（默认：60）
    weights={"text": 0.5, "vector": 0.6},  # 权重配置
    rerank=True,                      # 是否启用重排序（默认：False）
    rerank_top_k=20,                  # 重排序数量（默认：top_k * 2）
    return_columns=["title", "content"]  # 返回字段
)
```

**混合搜索参数详解**：

- **query_text** str（必填） - 文本查询语句
- **text_field** str（必填） - 用于全文搜索的字段
- **query_vector** List[float]（必填） - 向量查询
- **vector_field** str（必填） - 向量字段名
- **top_k** int（默认：10） - 最终返回的结果数量
- **coarse_top_k** int（默认：50） - 每一路召回的结果数量
- **rrf_k** int（默认：60） - Reciprocal Rank Fusion 的参数
- **weights** dict（默认：{"text": 0.5, "vector": 0.5}） - 文本和向量的权重
- **rerank** bool（默认：False） - 是否启用重排序
- **rerank_top_k** int（默认：top_k * 2） - 重排序的候选数量 |

---

### 3. 响应数据结构

#### 3.1 vector_search() 返回值格式

```python
[
    {
        "id": "product_001",           # 主键字段值
        "title": "iPhone 15 Pro",      # 其他字段
        "price": 999.99,
        "distance": 0.1234,            # 向量距离（根据 metric 不同含义不同）
        "score": 0.8766,               # 相似度分数（0-1 范围）
        "embedding": [...]             # 向量数据（如果包含在 output_columns 中）
    },
    {
        "id": "product_002",
        "title": "Samsung Galaxy S24",
        "price": 899.99,
        "distance": 0.1567,
        "score": 0.8433
    },
    ...
]
```

**字段说明**：
- `id`: 文档的唯一标识
- `distance`: 向量距离，值越小越相似（dot_product 除外）
- `score`: 相似度分数，0-1 范围，越大越相似
- 其他字段为文档的实际数据

#### 3.2 search() 返回值格式（OpenSearch 兼容）

```python
{
    "took": 15,                        # 查询耗时（毫秒）
    "timed_out": False,                # 是否超时
    "hits": {
        "total": {
            "value": 100,              # 总结果数
            "relation": "eq"           # 关系：eq（等于）/gte（至少）
        },
        "max_score": 0.9876,           # 最高分数
        "hits": [
            {
                "_index": "products",  # 索引名称
                "_id": "product_001",  # 文档 ID
                "_score": 0.9876,      # 相似度分数
                "_source": {           # 文档内容
                    "id": "product_001",
                    "title": "iPhone 15 Pro",
                    "price": 999.99,
                    "embedding": [...]
                },
                "fields": {...}        # 额外字段（如果有）
            },
            ...
        ]
    }
}
```

**字段说明**：
- `took`: 查询执行时间（毫秒）
- `hits.total.value`: 匹配的文档总数
- `hits.max_score`: 最高相似度分数
- `hits.hits[]`: 匹配的文档列表

#### 3.3 distance 与 score 的关系

| metric | distance 含义 | distance 范围 | score 计算公式 | score 范围 |
|:---|:---|:---|:---|:---|
| **cosine** | 余弦距离 | [-1, 1] | `score = 1.0 - distance` | [0, 2] |
| **l2_norm** | L2 距离 | [0, +∞) | `score = 1.0 / (1.0 + distance)` | (0, 1] |
| **dot_product** | 负内积 | (-∞, +∞) | `score = 1.0 / (1.0 + abs(distance))` | (0, 1] |

**重要提示**：
- `distance` 越小表示越相似（除了 dot_product）
- `score` 越大表示越相似（统一标准）
- 推荐使用 `score` 进行排序和比较
- `_score` 在 OpenSearch 兼容模式下自动计算

---

## 主要逻辑说明（开发者参考）

### 1. 向量搜索的核心流程

#### 1.1 vector_search() 方法执行流程

```
1. 参数验证与预处理
   ├── 验证表名合法性（防止 SQL 注入）
   ├── 验证向量字段名合法性
   ├── 验证 query_vector 非空且为列表
   ├── 验证 top_k 范围（1-10000）
   └── 验证 metric 参数有效性

2. 选择向量操作符
   ├── cosine → <=> (余弦相似度，越接近 0 越相似)
   ├── l2 → <-> (L2 距离，越小越相似)
   └── dot_product → <#> (内积，越大越相似)

3. 构建基础 SQL 查询
   ├── SELECT {output_columns} FROM {table_name}
   └── 确定输出列

4. 处理过滤条件（如有）
   ├── 解析 filter_condition 中的占位符
   ├── 绑定 filter_params 参数
   └── 生成 WHERE 子句

5. 添加向量相似度计算
   ├── ORDER BY {vector_column} {operator} %s::vector ASC/DESC
   └── 注意：不同 metric 的排序方向可能不同

6. 设置 HNSW 参数（如有）
   └── SET hnsw.ef_search = {ef_search}

7. 限制返回数量
   └── LIMIT {top_k}

8. 执行查询并处理结果
   ├── 使用 RealDictCursor 获取字典格式结果
   ├── 自动解析 JSON 字段
   ├── 计算 _score（基于 distance）
   └── 返回最终结果列表
```

**关键 SQL 示例**：

```sql
-- 基础向量搜索（余弦相似度）
SELECT * FROM products 
ORDER BY embedding <=> %s::vector ASC 
LIMIT 10;

-- 带过滤的向量搜索
SELECT id, title, price FROM products 
WHERE category = %s AND price > %s
ORDER BY embedding <=> %s::vector ASC 
LIMIT 10;

-- 设置 HNSW 参数
SET hnsw.ef_search = 256;
SELECT * FROM products 
ORDER BY embedding <=> %s::vector ASC 
LIMIT 10;
```

#### 1.2 knn_search() 方法执行流程（底层接口）

```
1. 参数校验
   ├── 验证索引名（使用 _validate_identifier）
   ├── 验证字段名
   ├── 验证 query_vector
   ├── 验证 k 值范围
   └── 验证 similarity 参数

2. 映射相似度算法到操作符
   └── SIMILARITY_OPS = {
       'cosine': '<=>',
       'l2_norm': '<->',
       'dot_product': '<#>'
   }

3. 构建 SQL 查询
   ├── SELECT *, {field} {operator} %s::vector AS distance
   ├── FROM {index}
   ├── WHERE {filter_conditions}（如有过滤）
   ├── ORDER BY {field} {operator} %s::vector ASC/DESC
   └── LIMIT {k}

4. 执行查询
   └── 使用参数化查询防止 SQL 注入

5. 处理结果集
   ├── 获取列名和数据行
   ├── 解析 JSON 字段
   ├── 计算 _score（调用 _calculate_score）
   └── 构建标准化响应格式

6. 返回结果
   └── {
       "hits": {
           "total": {"value": N, "relation": "eq"},
           "hits": [...]
       }
   }
```

#### 1.3 _handle_knn_query() 路由逻辑

```python
def _handle_knn_query(self, index, knn_config):
    """
    处理 OpenSearch 风格的 knn 查询
    
    流程：
    1. 从 knn_config 中提取参数
    2. 转换为 knn_search() 所需的参数格式
    3. 调用 knn_search() 执行实际查询
    4. 返回结果
    """
    # 提取参数
    field = knn_config.get('field')
    query_vector = knn_config.get('query_vector')
    k = knn_config.get('k', 10)
    similarity = knn_config.get('similarity', 'cosine')
    filter_query = knn_config.get('filter')
    num_candidates = knn_config.get('num_candidates')
    
    # 调用底层接口
    return self.knn_search(
        index=index,
        field=field,
        query_vector=query_vector,
        k=k,
        similarity=similarity,
        filter_query=filter_query,
        num_candidates=num_candidates
    )
```

---

### 2. 评分计算逻辑

#### 2.1 _calculate_score() 函数实现

```python
def _calculate_score(distance: float, similarity: str) -> float:
    """
    将原始距离转换为 0-1 范围的相似度分数
    
    Args:
        distance: 向量距离（原始计算结果）
        similarity: 相似度算法名称
    
    Returns:
        相似度分数（0-1 范围，越大越相似）
    """
    if similarity == 'cosine':
        # 余弦距离范围 [-1, 1]，转换为 [0, 2]
        # 但实际上通常使用归一化向量，范围接近 [0, 1]
        return 1.0 - distance
    
    elif similarity == 'l2_norm':
        # L2 距离 >= 0，使用倒数转换为 (0, 1]
        return 1.0 / (1.0 + distance)
    
    elif similarity == 'dot_product':
        # 内积可正可负，特殊处理
        if distance < 1:
            return 1.0 / (1.0 - distance)
        else:
            return 1.0 / (1.0 + abs(distance))
    
    else:
        # 默认 fallback 到 L2 的处理方式
        return 1.0 / (1.0 + distance)
```

#### 2.2 为什么需要转换？

**问题**：
- OpenSearch/Opensearch 底层返回的是原始距离值
- 不同 metric 的距离含义和范围不同
- 用户难以理解距离值的实际意义

**解决方案**：
- 统一转换为相似度分数（score）
- score 范围统一为 [0, 1]（或接近）
- 符合用户直觉：分数越高越相似

**实际应用**：
```python
# 用户看到的
{
    "_score": 0.95,  # 很容易理解：非常相似
    "_source": {...}
}

# 而不是
{
    "distance": 0.05,  # 不容易理解：这个值是好是坏？
    "_source": {...}
}
```

---

### 3. 索引创建逻辑

#### 3.1 向量索引的创建流程

```
1. 解析 Mapping 配置
   ├── 识别 dense_vector 类型的字段
   ├── 提取 dims（维度）
   ├── 提取 similarity（相似度算法）
   └── 提取 index_options（HNSW 参数）

2. 生成 CREATE TABLE 语句
   ├── 将 dense_vector 映射为 VECTOR(dims)
   ├── 添加其他字段定义
   └── 设置主键

3. 生成 HNSW 索引创建语句
   ├── 选择合适的向量操作符
   ├── 设置 HNSW 参数（m, ef_construction）
   └── 执行 CREATE INDEX

4. 连接管理
   - 使用上下文管理器自动处理连接生命周期
   - DDL 操作后自动提交事务
   - 连接池负责连接的复用和管理
```

**生成的 SQL 示例**：

```sql
-- 创建表
CREATE TABLE IF NOT EXISTS products (
    id VARCHAR PRIMARY KEY,
    title TEXT,
    category VARCHAR,
    price FLOAT,
    embedding VECTOR(768)
);

-- 创建 HNSW 索引（使用 vector_cosine_ops）
CREATE INDEX IF NOT EXISTS idx_products_embedding_hnsw
ON products USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

### 4. 错误处理机制

#### 4.1 常见错误及处理

```python
# 1. 向量维度不匹配
try:
    client.index(
        index="products",
        body={"embedding": [0.1, 0.2]}  # 期望 768 维，实际 2 维
    )
except ValueError as e:
    # 错误：Vector dimension mismatch: expected 768, got 2

# 2. 无效的相似度算法
try:
    client.multi.vector_search(
        table_name="products",
        query_vector=[...],
        metric="invalid_metric"
    )
except ValueError as e:
    # 错误：Invalid metric. Must be one of: cosine, l2, dot_product

# 3. 索引不存在
try:
    client.search(index="nonexistent_index", body={...})
except Exception as e:
    # 错误：Index 'nonexistent_index' does not exist

# 4. 向量字段不存在
try:
    client.multi.vector_search(
        table_name="products",
        query_vector=[...],
        vector_column="nonexistent_field"
    )
except Exception as e:
    # 错误：Column 'nonexistent_field' does not exist
```

---

## 主要代码文件（开发者参考）

### 核心文件列表

- **opensearch_sdk/client/search_ops.py** - SearchOpsMixin: 提供 kNN 搜索、_handle_knn_query、_calculate_score 等底层向量搜索功能
- **opensearch_sdk/client/vector_client.py** - MultiRetrieverClient: 高级检索客户端，提供 vector_search()、hybrid_search() 等高级接口
- **opensearch_sdk/client/indices.py** - IndicesClient: 索引管理，解析 mapping 配置并创建向量索引（HNSW）
- **opensearch_sdk/retrieval/retrievers.py** - VectorRetriever: 检索器实现，封装向量搜索底层细节，提供统一检索接口
- **opensearch_sdk/client/base.py** - OpenGaussClient: 基类，继承 SearchOpsMixin 和 DocumentOpsMixin获得完整能力
- **opensearch_sdk/connection/opengauss.py** - 底层数据库连接，执行SQL语句和处理结果集
- **opensearch_sdk/client/query_builder.py** - SQL构建器，提供安全的参数化查询构建
- **opensearch_sdk/client/utils.py** - 工具函数，提供标识符验证、向量维度验证、JSON 字段解析等辅助功能
- **opensearch_sdk/retrieval/types.py** - 数据类型定义，包含 SearchResult、HybridSearchResult 等数据类
- **opensearch_sdk/client/constants.py** - 常量定义，包含错误码、默认值、相似度算法映射等

---

## 相关章节

- [查询与搜索](./05_Query_Search.md) - 文本搜索和布尔查询
- [索引管理](./03_Index_Management.md) - 创建和管理索引
- [最佳实践](./07_Best_Practices.md) - 性能优化建议
