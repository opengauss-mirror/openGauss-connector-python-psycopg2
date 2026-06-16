# 索引转换核心规则

本文档详细说明了 Opensearch兼容接口如何将 OpenSearch 的索引定义转换为 Opensearch（基于 openGauss）的表结构和索引。

## 1. 核心设计理念

Opensearch兼容接口通过以下方式实现 OpenSearch 兼容：

1. **索引 → 表**：OpenSearch 的 Index 映射为 Opensearch 的 Table
2. **Mapping → Schema**：字段定义转换为数据库列定义
3. **自动索引创建**：根据字段类型自动创建相应的数据库索引（BM25、B-tree、HNSW 等）
4. **配置持久化**：将完整的 mapping 信息存储到 `pg_description` 中，便于后续查询和动态推断

---

## 2. 字段类型转换规则

### 2.1 基础类型映射

| OpenSearch 类型 | Opensearch 类型 | SQL 类型 | 说明 |
|----------------|---------------|----------|------|
| `text` | TEXT | TEXT | 全文检索文本，自动创建 BM25 索引 |
| `keyword` | TEXT | TEXT | 精确匹配字符串，自动创建 B-tree 索引 |
| `long` | BIGINT | BIGINT | 64位整数，自动创建 B-tree 索引 |
| `integer` | INTEGER | INTEGER | 32位整数，自动创建 B-tree 索引 |
| `short` | SHORTINT | SMALLINT | 16位整数，自动创建 B-tree 索引 |
| `byte` | TINYINT | TINYINT | 8位整数，自动创建 B-tree 索引 |
| `float` | FLOAT4 | REAL | 32位浮点数，自动创建 B-tree 索引 |
| `double` | FLOAT8 | DOUBLE PRECISION | 64位浮点数，自动创建 B-tree 索引 |
| `boolean` | BOOLEAN | BOOLEAN | 布尔值，自动创建 B-tree 索引 |
| `date` | TIMESTAMP | TIMESTAMP | 日期时间，自动创建 B-tree 索引 |

### 2.2 向量类型映射

| OpenSearch 类型 | Opensearch 类型 | SQL 类型 | 说明 |
|----------------|---------------|----------|------|
| `knn_vector` | VECTOR(n) | VECTOR(dimension) | KNN 向量，自动创建 HNSW/IVF 索引 |
| `dense_vector` | VECTOR(n) | VECTOR(dims) | 密集向量，自动创建 HNSW 索引 |
| `float_vector` | VECTOR(n) | VECTOR(dims) | 浮点向量，自动创建 HNSW 索引 |

**维度要求**：
- 最小维度：`MIN_VECTOR_DIMENSION`（通常为 1）
- 最大维度：`MAX_VECTOR_DIMENSION`（通常为 10000）
- 默认维度：128（如果未指定）

**智能数组识别**：
- 字段名以 `list` 或 `List` 结尾时，强制使用 `TEXT` 类型而非向量类型
- 示例：`tagsList` → TEXT, `embedding_list` → TEXT

---

## 3. 相似度算法转换规则

### 3.1 OpenSearch space_type → Opensearch similarity

OpenSearch 使用 `space_type` 参数，Opensearch 转换为内部 `similarity` 参数：

| OpenSearch space_type | Opensearch similarity | 向量操作符 | 数学含义 |
|----------------------|---------------------|-----------|---------|
| `l2` | `l2_norm` | `<->` | L2 距离（欧氏距离） |
| `cosinesimil` | `cosine` | `<=>` | 余弦相似度 |
| `innerproduct` | `dot_product` | `<#>` | 内积（点积） |

**转换逻辑**：
```python
space_to_similarity = {
    'l2': 'l2_norm',
    'cosinesimil': 'cosine',
    'innerproduct': 'dot_product'
}
```

### 3.2 Elasticsearch similarity → Opensearch similarity

Elasticsearch 直接使用 `similarity` 参数，SDK 直接支持：

| Elasticsearch similarity | Opensearch similarity | 说明 |
|-------------------------|---------------------|------|
| `cosine` | `cosine` | 余弦相似度 |
| `l2_norm` | `l2_norm` | L2 归一化距离 |
| `dot_product` | `dot_product` | 点积相似度 |
| `l1` | `l1` | L1 距离（曼哈顿距离） |
| `linf` | `linf` | L∞ 距离（切比雪夫距离） |

**优先级规则**：
- 如果同时设置 `space_type` 和 `similarity`，**`space_type` 优先**
- 如果都未设置，默认使用 `cosine`
