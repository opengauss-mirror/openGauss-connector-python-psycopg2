# 向量索引创建与配置

本章节详细介绍如何在 Opensearch 中创建和管理向量索引，包括 Mapping 配置、HNSW 与 IVF 索引的选择及参数调优。

## 1. Mapping 配置结构

### 1.1 完整的向量索引 Mapping

在 Opensearch 中，向量字段通常使用 `dense_vector` 或 `knn_vector` 类型定义。

```python
mapping = {
    "mappings": {
        "properties": {
            # 文本字段 - 用于全文搜索（BM25）
            "title": {
                "type": "text",           # 文本类型，会被分词器处理
                "analyzer": "standard"     # 标准分词器（可选）
            },
            
            # 关键词字段 - 用于精确匹配和过滤
            "category": {
                "type": "keyword"         # 不分词，精确匹配
            },
            
            # 向量字段 - 核心配置
            "embedding": {
                "type": "dense_vector",   # 密集向量类型
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

client.indices.create(index="products", body=mapping)
```

### 1.2 向量字段参数详解

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| type | str | 是 | - | `dense_vector` 或 `knn_vector` |
| dims/dimension | int | 是 | - | 向量维度，范围 1-10000 |
| similarity/space_type | str | 否 | cosine | 相似度算法：cosine/l2_norm/dot_product |
| m | int | 否 | 16 | HNSW 参数 M，控制节点连接数 |
| ef_construction | int | 否 | 64 | 构建时的搜索深度，越大索引质量越高 |
| ef_search | int | 否 | 256 | 搜索时的搜索深度，越大搜索越准确 |

---

## 2. 索引算法选择：HNSW vs IVF

### 2.1 HNSW 索引（默认，推荐用于中小规模数据）

HNSW（Hierarchical Navigable Small World）是一种基于图的索引结构，查询速度极快。

**适用场景**：
- 数据量 < 100 万
- 对延迟敏感（微秒级响应）
- 内存资源充足

**SQL 生成示例**：
```sql
CREATE INDEX IF NOT EXISTS idx_products_embedding_hnsw
ON products USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

### 2.2 IVF 索引（推荐用于大规模数据）

IVF（Inverted File Index）是一种基于聚类的索引结构，支持压缩技术，内存占用更低。

**适用场景**：
- 数据量 > 100 万
- 内存受限
- 可接受毫秒级响应

**OpenSearch 兼容格式**：
```python
mapping = {
    "mappings": {
        "properties": {
            "embedding": {
                "type": "knn_vector",
                "dimension": 768,
                "space_type": "cosinesimil",
                "method": {
                    "name": "ivf",          # IVF 索引
                    "parameters": {
                        "nlist": 100,       # 桶数量（默认 100）
                        "nprobes": 50       # 查询时探测的桶数
                    }
                }
            }
        }
    }
}
```

**SQL 生成示例**：
```sql
CREATE INDEX IF NOT EXISTS idx_embedding_ivf
ON my_index USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### 2.3 索引对比表

| 特性 | HNSW | IVF |
|:---|:---|:---|
| **数据结构** | 图结构（多跳） | 倒排索引（分区） |
| **适用规模** | 中小规模（<100 万） | 大规模（>100 万） |
| **查询速度** | 非常快（微秒级） | 较快（毫秒级） |
| **内存占用** | 较高（完整向量） | 较低（可压缩） |
| **精度** | 完全兼容 | 高 |

---

## 3. 高级压缩技术（IVF + PQ/RabitQ）

对于超大规模数据，IVF 索引支持量化压缩以进一步减少内存占用。

### 3.1 IVF + PQ 压缩

PQ（Product Quantization）将向量分解为多个子向量并分别编码。

```python
index_config = IndexConfig(
    name="idx_embedding_ivf_pq",
    column="embedding",
    index_type=IndexType.IVFFLAT,
    metric=DistanceMetric.L2,
    lists=200,
    enable_pq=True,           # 启用 PQ 量化
    pq_m=64,                  # PQ 子向量数量
    pq_ksub=256               # PQ 码本大小
)
```

### 3.2 IVF + RabitQ 压缩

RabitQ 是一种高精度的量化方法，适合对精度要求较高的场景。

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

---

## 4. 不同场景的推荐配置

### 场景 1：语义搜索（768 维 BERT 向量）
- **推荐**：HNSW, m=16, ef_construction=100
- **特点**：平衡性能和精度，适用于问答系统。

### 场景 2：图像检索（高维向量）
- **推荐**：HNSW, m=32, ef_search=512
- **特点**：高维度需要更大的 m 和 ef_search 以保证召回率。

### 场景 3：大规模数据（百万级以上）
- **推荐**：IVF + PQ, nlist=500
- **特点**：PQ 压缩大幅减少内存占用，适合超大规模数据集。

---

## 相关章节

- [KNN 搜索基础](./06_02_KNN_Search.md)
- [高级搜索功能](./06_03_Advanced_Features.md)
- [内部实现原理](./06_04_Internal_Implementation.md)
