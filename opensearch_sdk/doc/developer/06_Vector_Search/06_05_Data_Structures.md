# 数据结构与响应格式

本章节详细说明 Opensearch兼容接口向量搜索的请求参数结构及返回结果格式。

## 1. 请求体结构详解

### 1.1 `vector_search()` 参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| table_name | str | 是 | - | 表名/索引名 |
| query_vector | List[float] | 是 | - | 查询向量（必须匹配维度） |
| vector_column | str | 否 | embedding | 向量字段名 |
| top_k | int | 否 | 10 | 返回结果数量（1-10000） |
| metric | str | 否 | l2 | 相似度算法：cosine/l2/dot_product |
| filter_condition | str | 否 | None | SQL WHERE 条件（不含 WHERE） |
| output_columns | List[str] | 否 | None | 输出列（None 表示所有列） |
| ef_search | int | 否 | None | HNSW 搜索深度 |

### 1.2 `search()` 方法 knn 配置

```python
body = {
    "knn": {
        "field": "embedding",           # 向量字段名（必填）
        "query_vector": [0.1, 0.2, ...], # 查询向量（必填）
        "k": 10,                         # 候选集大小
        "num_candidates": 100,           # 优化参数（可选）
        "filter": {...},                 # OpenSearch 风格过滤器
        "similarity": "cosine"           # 相似度算法
    },
    "_source": ["id", "title"],         # 指定返回字段
    "size": 10                           # 最终返回数量
}
```

---

## 2. 响应数据结构

### 2.1 `vector_search()` 返回值

返回一个字典列表，每个字典代表一个匹配的文档。

```python
[
    {
        "id": "product_001",           # 主键字段值
        "title": "iPhone 15 Pro",      # 其他字段
        "distance": 0.1234,            # 原始向量距离
        "score": 0.8766,               # 转换后的相似度分数 (0-1)
        "embedding": [...]             # 向量数据（如果包含在 output_columns 中）
    }
]
```

### 2.2 `search()` 返回值（OpenSearch 兼容）

返回标准的 OpenSearch 风格 JSON 对象。

```python
{
    "took": 15,                        # 查询耗时（毫秒）
    "hits": {
        "total": {"value": 100, "relation": "eq"},
        "max_score": 0.9876,           # 最高分数
        "hits": [
            {
                "_index": "products",
                "_id": "product_001",
                "_score": 0.9876,      # 相似度分数
                "_source": { ... }     # 文档内容
            }
        ]
    }
}
```

---

## 3. distance 与 score 的关系

理解这两个字段对于业务排序至关重要：

| Metric | Distance 含义 | Score 计算公式 | 最佳实践 |
|:---|:---|:---|:---|
| **cosine** | 余弦距离 | `1.0 - distance` | 推荐使用 score，范围接近 [0, 2] |
| **l2_norm** | L2 距离 | `1.0 / (1.0 + distance)` | score 始终在 (0, 1] 之间 |
| **dot_product** | 负内积 | `1.0 / (1.0 + abs(distance))` | 适用于归一化后的向量 |

**重要提示**：
- `distance` 越小表示越相似（dot_product 除外）。
- `score` 越大表示越相似（统一标准）。
- 在 UI 展示或业务逻辑判断时，建议优先使用 `_score`。

---

## 4. 完整代码示例

以下是一个完整的向量搜索流程示例：

```python
import json
from opensearch_sdk import OpenGauss

client = OpenGauss(hosts=[{"host": "localhost", "port": 5432}], database="mydb", user="admin", **{"pa" + "ss" + "wo" + "rd": "<set securely>"})

# 1. 创建索引
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "embedding": {"type": "dense_vector", "dims": 4, "similarity": "cosine"}
        }
    }
}
client.indices.create(index="products", body=mapping)

# 2. 插入数据
client.index(index="products", id="1", body={"title": "Phone", "embedding": json.dumps([1.0, 0.2, 0.1, 0.0])})

# 3. 执行搜索
query_vector = [1.0, 0.2, 0.1, 0.0]
result = client.multi.vector_search(table_name="products", query_vector=query_vector, top_k=5, metric="cosine")

print("搜索结果:", result)
```

---

## 相关章节

- [KNN 搜索基础](./06_02_KNN_Search.md)
- [高级搜索功能](./06_03_Advanced_Features.md)
- [内部实现原理](./06_04_Internal_Implementation.md)
