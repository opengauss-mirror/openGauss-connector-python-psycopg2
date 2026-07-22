# 高级搜索功能

本章节介绍 Opensearch兼容接口向量搜索的高级特性，包括过滤条件、参数调优及混合搜索。

## 1. 带过滤的向量搜索

在实际业务中，通常需要在特定范围内（如特定分类、价格区间）进行向量相似度匹配。

### 1.1 使用 `vector_search()` 进行过滤

通过 `filter_condition` 和 `filter_params` 传入 SQL WHERE 子句。SQL 结构需使用
`trusted_sql()` 显式包装，动态值继续通过参数绑定。

```python
from opensearch_sdk.retrieval import trusted_sql

result = client.multi.vector_search(
    table_name="products",
    query_vector=query_vector,
    top_k=10,
    metric="cosine",
    filter_condition=trusted_sql("category = %s AND price > %s"),
    filter_params=("electronics", 100)
)
```

### 1.2 使用 `search()` 进行过滤

在 `knn` 配置中直接嵌入 OpenSearch 风格的 `filter` 对象。

```python
result = client.search(
    index="products",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 10,
            "filter": {
                "bool": {
                    "must": [
                        {"term": {"category": "electronics"}},
                        {"range": {"price": {"gte": 100}}}
                    ]
                }
            },
            "similarity": "cosine"
        }
    }
)
```

### 1.3 自动合并过滤条件 (2026-03 更新)

SDK 现在支持自动合并 `knn.filter` 和 `bool.query.filter`，解决了两者同时存在时的冲突问题。

**示例**：
```python
body = {
    "query": {
        "bool": {
            "must": [{"term": {"category": "tech"}}]
        }
    },
    "knn": {
        "field": "embedding",
        "query_vector": [0.1, 0.2, ...],
        "k": 10,
        "filter": {"term": {"status": "published"}}
    }
}
# 实际执行的 SQL: WHERE category = 'tech' AND status = 'published' ORDER BY ...
```

---

## 2. k 与 size 的区别

在 OpenSearch 兼容模式下，`k` 和 `size` 扮演着不同的角色：

| 参数 | 作用阶段 | 含义 | 影响 |
|:---:|:---:|:---:|:---:|
| **k** | 向量检索阶段 | KNN 算法返回的候选集大小 | 决定从索引中找到多少个最相似的向量 |
| **size** | 后处理阶段 | 最终返回给用户的数量 | 决定过滤后返回多少条结果 |

**工作流程**：
1. **向量检索**：使用 `k` 找到候选向量。
2. **应用过滤**：可能过滤掉部分候选。
3. **返回结果**：从剩余候选中取前 `size` 个返回。

**最佳实践**：
- **无过滤时**：设置 `k = size`。
- **有过滤时**：建议设置 `k = 5-10 × size`，以确保过滤后仍有足够结果。

---

## 3. 性能调优参数

### 3.1 HNSW 搜索深度 (`ef_search`)

`ef_search` 决定了搜索时遍历的节点数量。增大该值可以提高召回率，但会增加延迟。

```python
result = client.multi.vector_search(
    table_name="products",
    query_vector=query_vector,
    top_k=10,
    ef_search=256  # 默认为 256，可根据精度需求调整
)
```

### 3.2 IVF 探测次数 (`probes`)

对于 IVF 索引，`probes` 决定了查询时探测的桶数量。

```python
result = client.multi.vector_search(
    table_name="products",
    query_vector=query_vector,
    top_k=10,
    probes=50  # 默认为 lists/30
)
```

---

## 4. 混合搜索结构 (Hybrid Search)

混合搜索结合了全文检索（BM25）和向量检索的优势，能提供更精准的语义匹配。

```python
result = client.hybrid_search(
    index="products",
    query_text="machine learning",    # 文本查询
    text_field="title",               # 文本字段
    query_vector=[0.1, 0.2, ...],     # 向量查询
    vector_field="embedding",         # 向量字段
    top_k=10,                         # 最终返回数量
    weights={"text": 0.5, "vector": 0.6}, # 权重配置
    rerank=True                       # 启用重排序
)
```

**核心参数**：
- **coarse_top_k**: 每一路召回的初始数量（默认 50）。
- **rrf_k**: Reciprocal Rank Fusion 融合参数（默认 60）。
- **rerank**: 是否对融合后的结果进行二次精排。

---

## 相关章节

- [KNN 搜索基础](./06_02_KNN_Search.md)
- [内部实现原理](./06_04_Internal_Implementation.md)
- [数据结构详解](./06_05_Data_Structures.md)
