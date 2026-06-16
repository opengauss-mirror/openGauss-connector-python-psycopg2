# 内部实现原理

本章节深入解析 Opensearch兼容接口向量搜索的底层实现机制，包括 SQL 生成、评分算法及核心类结构。

## 1. 核心执行流程

### 1.1 `vector_search()` 方法流程

1. **参数验证**：检查表名合法性、向量维度匹配及 `top_k` 范围。
2. **操作符选择**：根据 `metric` 映射到 PostgreSQL 向量操作符（如 `<=>`）。
3. **SQL 构建**：
   - 基础查询：`SELECT {columns} FROM {table}`
   - 过滤条件：`WHERE {filter_condition}`
   - 排序逻辑：`ORDER BY {field} {operator} %s::vector ASC`
4. **结果处理**：使用 `RealDictCursor` 获取字典格式结果，并自动解析 JSON 字段。

### 1.2 `knn_search()` 底层接口

这是 `SearchOpsMixin` 提供的底层 kNN 实现，负责将 OpenSearch 风格的请求转换为 SQL。

**关键 SQL 示例**：
```sql
-- 基础向量搜索（余弦相似度）
SELECT *, embedding <=> %s::vector AS distance 
FROM products 
ORDER BY embedding <=> %s::vector ASC 
LIMIT 10;

-- 带过滤的搜索
SELECT id, title FROM products 
WHERE category = 'electronics' 
ORDER BY embedding <=> %s::vector ASC 
LIMIT 10;
```

---

## 2. 评分计算逻辑 (_score)

SDK 通过 `_calculate_score()` 函数将原始距离转换为直观的相似度分数。

| Metric | Distance 含义 | Score 计算公式 |
|:---|:---|:---|
| **cosine** | 余弦距离 | `score = 1.0 - distance` |
| **l2_norm** | L2 距离 | `score = 1.0 / (1.0 + distance)` |
| **dot_product** | 负内积 | `score = 1.0 / (1.0 + abs(distance))` |

**设计初衷**：
- 统一分数范围为 [0, 1]，符合“分数越高越相似”的用户直觉。
- 解决不同算法下距离值含义不一致的问题。

---

## 3. 核心类与模块

### 3.1 SearchOpsMixin (`search_ops.py`)

提供全文搜索、向量搜索和混合搜索的基础能力。
- **`_handle_knn_query()`**: 路由逻辑，提取 `knn` 配置并调用底层接口。
- **`_get_similarity_ops()`**: 维护相似度算法到 SQL 操作符的映射。

### 3.2 MultiRetrieverClient (`vector_client.py`)

高级检索客户端，封装了更复杂的业务逻辑。
- **`vector_search()`**: 支持过滤、投影和自定义索引参数的高级接口。
- **`hybrid_search()`**: 实现多路召回与 RRF 融合。

### 3.3 IndicesClient (`indices.py`)

负责索引生命周期的管理。
- **`create()`**: 解析 Mapping，自动生成 `CREATE TABLE` 和 `CREATE INDEX` 语句。
- **连接管理**：使用 `get_connection_for_operation()` 确保 DDL 操作的原子性。

---

## 4. 错误处理机制

### 4.1 常见异常

| 异常类型 | 触发场景 | 解决方案 |
|:---|:---|:---|
| `ValueError` | 向量维度不匹配 | 检查输入向量长度是否与 Mapping 定义一致 |
| `ValueError` | 无效的 metric | 确保使用 `cosine`, `l2` 或 `dot_product` |
| `Exception` | 索引/字段不存在 | 确认索引已创建且字段名拼写正确 |

### 4.2 调试建议

开启 SQL 追踪功能可以查看实际执行的 SQL 语句：
```python
client.enable_sql_trace = True
result = client.multi.vector_search(...)
sessions = client.sql_tracer.get_all_sessions()
for record in sessions[-1].get_records():
    print(record.sql)
```

---

## 相关章节

- [高级搜索功能](./06_03_Advanced_Features.md)
- [数据结构详解](./06_05_Data_Structures.md)
- [索引管理文档](../03_Index_Management.md)
