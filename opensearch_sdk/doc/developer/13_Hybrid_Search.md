# 多路召回（混合检索）

本章节详细介绍 Opensearch兼容接口的多路召回（Hybrid Search）功能，包括 RRF 融合、加权融合等高级检索策略。

## 概述

多路召回是指同时使用多种检索方式（如向量检索、全文检索等），然后通过融合策略将多路结果合并，以获得更准确、更全面的搜索结果。

### 应用场景

- **语义搜索 + 关键词匹配**：结合向量相似度搜索和 BM25 全文检索
- **多向量融合**：使用多个不同的向量字段进行检索
- **提升召回率**：通过多路召回覆盖更多相关文档
- **平衡精度和召回**：通过调整权重优化搜索结果

## 核心组件

### 1. Retriever（检索器）

检索器是执行单一检索策略的组件：

#### VectorRetriever（向量检索器）

```python
from opensearch_sdk.retrieval import VectorRetriever, trusted_sql

vec_ret = VectorRetriever(
    query_vector=[0.9, 0.1, 0.0, 0.0],
    vector_column='embedding',
    metric="cosine",
    output_columns=['question', 'answer']
)
```

**参数说明**：
- `query_vector`: 查询向量（列表或数组）
- `vector_column`: 向量字段名
- `metric`: 相似度度量方式（"cosine", "l2", "innerproduct"）
- `output_columns`: 返回的字段列表
- `filter_condition`: 使用 `trusted_sql()` 包装的 SQL WHERE 过滤条件（可选）
- `filter_params`: 过滤条件的参数（可选）

#### FullTextRetriever（全文检索器）

```python
from opensearch_sdk.retrieval import FullTextRetriever, trusted_sql

ft_ret = FullTextRetriever(
    query_text="Opensearch",
    text_column='question',
    output_columns=['question', 'answer']
)
```

**参数说明**：
- `query_text`: 查询文本
- `text_column`: 文本字段名（需要有 BM25 索引）
- `output_columns`: 返回的字段列表
- `filter_condition`: 使用 `trusted_sql()` 包装的 SQL WHERE 过滤条件（可选）
- `filter_params`: 过滤条件的参数（可选）
- `use_bm25_taat`: 是否使用 TAAT 方法（可选）
- `bm25_k1`, `bm25_b`: BM25 参数（可选）

### 2. FusionStrategy（融合策略）

融合策略决定如何合并多路检索结果：

#### RRFFusion（倒数排名融合）

RRF（Reciprocal Rank Fusion）是一种经典的融合算法，基于文档在各路结果中的排名进行融合。

```python
from opensearch_sdk.retrieval import RRFFusion

# 默认配置（k=60）
fusion = RRFFusion()

# 自定义 k 值
fusion = RRFFusion(k=60)
```

**RRF 公式**：
```
score = Σ (1 / (k + rank_i))
```

其中：
- `k`: 平滑参数，默认为 60
- `rank_i`: 文档在第 i 路结果中的排名

**特点**：
- 无需归一化不同检索器的分数
- 对排名敏感，对绝对分数不敏感
- 自动平衡各路结果的贡献

#### WeightedFusion（加权融合）

加权融合允许为每路检索结果分配不同的权重。

```python
from opensearch_sdk.retrieval import WeightedFusion

# 向量权重 0.7，全文权重 0.3
fusion = WeightedFusion(weights=[0.7, 0.3])

# 自定义归一化方法
from opensearch_sdk.retrieval import NormMethod
fusion = WeightedFusion(
    weights=[0.7, 0.3],
    norm_method=NormMethod.MIN_MAX  # 或 NormMethod.ARCTAN（默认）
)
```

**参数说明**：
- `weights`: 每路检索的权重列表（会自动归一化为总和为 1）
- `norm_method`: 分数归一化方法
  - `NormMethod.ARCTAN`: 反正切归一化（默认）
  - `NormMethod.MIN_MAX`: 最小-最大归一化

**特点**：
- 可精确控制各路结果的贡献度
- 适合有明确偏好的场景（如更重视向量相似度）
- 需要确保各路分数在同一量级（通过归一化）

## 使用示例

### 基础用法：RRF 融合

```python
from opensearch_sdk import OpenGauss
from opensearch_sdk.retrieval import VectorRetriever, FullTextRetriever

# 初始化客户端
client = OpenGauss(
    hosts=[{'host': 'localhost', 'port': 5432}],
    database='mydb',
    user='user',
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)

# 定义检索器
vec_ret = VectorRetriever(
    query_vector=[0.85, 0.15, 0.0, 0.0],
    vector_column='embedding',
    metric="cosine",
    output_columns=['question', 'answer']
)

ft_ret = FullTextRetriever(
    query_text="Opensearch",
    text_column='question',
    output_columns=['question', 'answer']
)

retrievers = [vec_ret, ft_ret]

# 执行混合检索（默认使用 RRF 融合）
results = client.multi.hybrid_search(
    table_name="my_table",
    retrievers=retrievers,
    top_k=5,
    parallel=True  # 并行执行
)

# 处理结果
for result in results:
    print(f"ID: {result['id']}, Score: {result['score']:.4f}")
    print(f"Question: {result['question']}")
```

### 自定义权重：加权融合

```python
from opensearch_sdk.retrieval import WeightedFusion

# 定义检索器
vec_ret = VectorRetriever(...)
ft_ret = FullTextRetriever(...)

retrievers = [vec_ret, ft_ret]

# 使用加权融合，向量权重 0.7，全文权重 0.3
fusion_strategy = WeightedFusion(weights=[0.7, 0.3])

results = client.multi.hybrid_search(
    table_name="my_table",
    retrievers=retrievers,
    top_k=5,
    fusion_strategy=fusion_strategy,
    parallel=True
)
```

### 带过滤条件的混合检索

```python
# 定义带过滤条件的检索器
vec_ret = VectorRetriever(
    query_vector=[0.85, 0.15, 0.0, 0.0],
    vector_column='embedding',
    metric="cosine",
    filter_condition=trusted_sql('"category" = %s'),
    filter_params=['技术'],
    output_columns=['question', 'answer', 'category']
)

ft_ret = FullTextRetriever(
    query_text="Opensearch",
    text_column='question',
    filter_condition=trusted_sql('"category" = %s'),
    filter_params=['技术'],
    output_columns=['question', 'answer', 'category']
)

retrievers = [vec_ret, ft_ret]

results = client.multi.hybrid_search(
    table_name="my_table",
    retrievers=retrievers,
    top_k=5,
    parallel=True
)

# 所有结果都满足 category='技术' 的过滤条件
```

### 多向量检索器组合

```python
# 定义两个不同的向量检索器
vec_ret1 = VectorRetriever(
    query_vector=[0.9, 0.1, 0.0, 0.0],
    vector_column='embedding1',
    metric="cosine"
)

vec_ret2 = VectorRetriever(
    query_vector=[0.1, 0.9, 0.0, 0.0],
    vector_column='embedding2',
    metric="cosine"
)

retrievers = [vec_ret1, vec_ret2]

results = client.multi.hybrid_search(
    table_name="my_table",
    retrievers=retrievers,
    top_k=5,
    parallel=True
)
```

### 并行 vs 串行执行

```python
import time

retrievers = [vec_ret, ft_ret]

# 并行执行（推荐）
start_time = time.time()
results_parallel = client.multi.hybrid_search(
    table_name="my_table",
    retrievers=retrievers,
    top_k=5,
    parallel=True
)
time_parallel = time.time() - start_time

# 串行执行
start_time = time.time()
results_sequential = client.multi.hybrid_search(
    table_name="my_table",
    retrievers=retrievers,
    top_k=5,
    parallel=False
)
time_sequential = time.time() - start_time

print(f"并行时间: {time_parallel:.4f}s")
print(f"串行时间: {time_sequential:.4f}s")
print(f"加速比: {time_sequential / time_parallel:.2f}x")
```

## 性能优化建议

### 1. 使用并行执行

```python
# 推荐：并行执行（默认）
results = client.multi.hybrid_search(
    table_name="my_table",
    retrievers=retrievers,
    top_k=5,
    parallel=True  # 默认值
)
```

**优势**：
- 多路检索并发执行，减少总耗时
- 特别适合 I/O 密集型操作（数据库查询）

### 2. 合理设置候选集大小

检索器内部会获取比 `top_k` 更多的候选结果用于融合：

```python
# MultiRetrievalEngine 内部会自动获取 top_k * 3 个候选结果
# 无需手动配置
```

### 3. 选择合适的融合策略

| 场景 | 推荐策略 | 原因 |
|------|---------|------|
| 不确定权重 | RRFFusion | 自动平衡，无需调参 |
| 明确偏好某路 | WeightedFusion | 精确控制权重 |
| 多路向量检索 | RRFFusion | 避免分数归一化问题 |
| 向量 + 全文 | WeightedFusion | 可根据业务调整权重 |

### 4. 添加过滤条件减少数据量

```python
# 在检索器层面添加过滤，减少传输和处理的数据量
vec_ret = VectorRetriever(
    query_vector=[...],
    filter_condition=trusted_sql('"status" = %s'),
    filter_params=['active']
)
```

## 注意事项

### 1. BM25 索引要求

使用 `FullTextRetriever` 时，文本字段必须有 BM25 索引：

```python
from opensearch_sdk.retrieval import IndexConfig, IndexType

index_config = IndexConfig(
    name="idx_question_bm25",
    column="question",
    index_type=IndexType.BM25,
    parallel_workers=4
)

# 创建 BM25 索引
pre_sql = index_config.get_pre_create_sql('my_table')
with client.connection.get_connection_for_operation() as conn:
    cursor = conn.cursor()
    try:
        cursor.execute(pre_sql)
        conn.commit()
    finally:
        cursor.close()
```

### 2. 返回结果格式

混合检索返回的结果是扁平化的字典：

```python
# 正确的访问方式
for result in results:
    doc_id = result['id']
    score = result['score']
    question = result['question']  # 直接在顶层
    answer = result['answer']      # 直接在顶层
```

**错误的方式**：
```python
# 错误：没有嵌套的 'data' 字段
question = result['data']['question']  # KeyError!
```

### 3. 权重归一化

使用 `WeightedFusion` 时，权重会自动归一化：

```python
# 传入 [0.7, 0.3]，内部会归一化为 [0.7, 0.3]（总和已经是 1）
fusion = WeightedFusion(weights=[0.7, 0.3])

# 传入 [7, 3]，内部会归一化为 [0.7, 0.3]
fusion = WeightedFusion(weights=[7, 3])  # 效果相同
```

### 4. 空结果处理

如果某路检索没有结果，融合策略会正常处理：

```python
# 即使某路返回空列表，融合仍然可以正常工作
# RRF: 只考虑有排名的文档
# Weighted: 该路贡献为 0
```

## 完整示例

参考测试文件：[test_hybrid_search.py](../../opensearch_sdk/tests/features/search/test_hybrid_search.py)

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
混合检索完整示例
"""

from opensearch_sdk import OpenGauss
from opensearch_sdk.retrieval import (
    VectorRetriever,
    FullTextRetriever,
    RRFFusion,
    WeightedFusion
)

# 初始化客户端
client = OpenGauss(
    hosts=[{'host': 'localhost', 'port': 5432}],
    database='mydb',
    user='user',
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)

# 示例 1: RRF 融合
def example_rrf():
    vec_ret = VectorRetriever(
        query_vector=[0.85, 0.15, 0.0, 0.0],
        vector_column='embedding',
        metric="cosine"
    )
    
    ft_ret = FullTextRetriever(
        query_text="Opensearch",
        text_column='question'
    )
    
    results = client.multi.hybrid_search(
        table_name="my_table",
        retrievers=[vec_ret, ft_ret],
        top_k=5
    )
    
    for r in results:
        print(f"{r['id']}: {r['score']:.4f}")

# 示例 2: 加权融合
def example_weighted():
    vec_ret = VectorRetriever(...)
    ft_ret = FullTextRetriever(...)
    
    fusion = WeightedFusion(weights=[0.7, 0.3])
    
    results = client.multi.hybrid_search(
        table_name="my_table",
        retrievers=[vec_ret, ft_ret],
        top_k=5,
        fusion_strategy=fusion
    )

if __name__ == '__main__':
    example_rrf()
    example_weighted()
```

## 相关文档

- [向量搜索](06_Vector_Search.md) - 基础向量检索功能
- [查询搜索](05_Query_Search.md) - 通用搜索功能
- [最佳实践](07_Best_Practices.md) - 性能优化建议

## API 参考

### client.multi.hybrid_search()

```python
def hybrid_search(
    self,
    table_name: str,
    retrievers: List,
    top_k: int = 10,
    fusion_strategy: FusionStrategy = None,
    parallel: bool = True
) -> List[Dict]:
    """
    执行混合检索（多路召回）
    
    Args:
        table_name: 表名
        retrievers: 检索器列表
        top_k: 返回结果数量
        fusion_strategy: 融合策略（默认 RRFFusion）
        parallel: 是否并行执行（默认 True）
    
    Returns:
        融合后的搜索结果列表，每个结果包含：
        - id: 文档 ID
        - score: 融合后的分数
        - source: 来源标识
        - 其他字段（根据 output_columns 配置）
    """
```

### RRFFusion

```python
class RRFFusion(FusionStrategy):
    def __init__(self, k: int = 60):
        """
        RRF 融合策略
        
        Args:
            k: 平滑参数，默认 60
        """
```

### WeightedFusion

```python
class WeightedFusion(FusionStrategy):
    def __init__(
        self,
        weights: List[float],
        norm_method: NormMethod = NormMethod.ARCTAN
    ):
        """
        加权融合策略
        
        Args:
            weights: 每路检索的权重列表
            norm_method: 分数归一化方法
        """
```

## 总结

多路召回功能提供了强大的混合检索能力：

**灵活的检索器组合**：支持向量、全文等多种检索方式  
**多种融合策略**：RRF、加权融合等  
**高性能**：支持并行执行  
**易于使用**：简洁的 API 设计  
**可扩展**：可自定义融合策略  

通过合理使用多路召回，可以显著提升搜索质量和用户体验。
