# KNN 搜索基础

本章节介绍 Opensearch兼容接口提供的两种向量搜索方式及其基础用法。

## 1. 两种使用方式

Opensearch兼容接口提供了两套 API 用于向量搜索：

### 方式一：`client.multi.vector_search()`（推荐）

这是 `MultiRetrieverClient` 提供的专用接口，功能最完整且性能最优。

```python
result = client.multi.vector_search(
    table_name="my_table",
    query_vector=[0.1, 0.2, 0.3],
    top_k=10,
    metric="cosine"
)
```

**优点**：
- 支持高级特性（过滤、投影、自定义输出列）
- 专为向量检索优化，API 设计直观
- 返回结果为字典列表，易于处理

### 方式二：`client.search()`（OpenSearch 兼容）

适用于从 OpenSearch 迁移的场景，保持 API 100% 兼容。

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
- 与 OpenSearch 语法完全一致
- 无需修改现有业务代码

---

## 2. 相似度算法详解

在向量搜索中，`metric` 参数决定了如何计算向量之间的距离或相似度。

| 算法 | 操作符 | 说明 | 适用场景 |
|:---|:---|:---|:---|
| **cosine** | `<=>` | 余弦相似度 | 文本、语义搜索（最常用） |
| **l2** | `<->` | L2 距离（欧氏距离） | 空间距离、图像特征 |
| **dot_product** | `<#>` | 内积（点积） | 神经网络特征匹配、推荐系统 |

**注意**：HNSW 和 IVF 索引都支持所有三种相似度算法。

### 2.1 余弦相似度 (Cosine)

衡量两个向量方向的夹角，取值范围通常为 [-1, 1]。值越接近 1 表示越相似。

```python
result = client.multi.vector_search(
    table_name="vector_index",
    query_vector=query_vector,
    top_k=10,
    metric="cosine"
)
```

### 2.2 L2 距离 (Euclidean)

衡量两个点在空间中的直线距离。值越小表示越相似。

```python
result = client.multi.vector_search(
    table_name="vector_index",
    query_vector=query_vector,
    top_k=10,
    metric="l2"
)
```

---

## 3. 基础搜索示例

### 3.1 插入向量数据

在执行搜索前，需要确保数据已正确插入。向量通常以 JSON 字符串形式存储。

```python
import json

client.index(
    index="vector_index",
    id="doc1",
    body={
        "title": "Apple iPhone 15",
        "embedding": json.dumps([0.1, 0.2, 0.3] + [0.0] * 765)
    }
)
```

### 3.2 执行搜索并处理结果

#### 使用 `vector_search()`
```python
result = client.multi.vector_search(
    table_name="vector_index",
    query_vector=query_vector,
    top_k=3,
    metric="cosine"
)

for item in result:
    print(f"ID: {item['id']}, Distance: {item.get('_distance', 'N/A'):.4f}")
```

#### 使用 `search()`
```python
result = client.search(
    index="vector_index",
    body={
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": 3,
            "similarity": "cosine"
        }
    }
)

for hit in result['hits']['hits']:
    print(f"ID: {hit['_id']}, Score: {hit['_score']:.4f}")
```

---

## 4. 评分计算逻辑 (_score)

为了方便用户理解，SDK 会将原始的 `distance` 转换为 0-1 范围的 `_score`。

| Metric | Distance 含义 | Score 计算公式 |
|:---|:---|:---|
| **cosine** | 余弦距离 | `score = 1.0 - distance` |
| **l2_norm** | L2 距离 | `score = 1.0 / (1.0 + distance)` |
| **dot_product** | 负内积 | `score = 1.0 / (1.0 + abs(distance))` |

**提示**：推荐使用 `_score` 进行排序和比较，因为它符合“分数越高越相似”的直觉。

---

## 相关章节

- [向量索引创建](./06_01_Vector_Index_Creation.md)
- [高级搜索功能](./06_03_Advanced_Features.md)
- [内部实现原理](./06_04_Internal_Implementation.md)
