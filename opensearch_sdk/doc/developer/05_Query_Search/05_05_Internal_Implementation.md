# 内部实现原理

本章节深入解析 Opensearch兼容接口搜索功能的底层实现，重点介绍 `QueryBuilder` 和 SQL 转换逻辑。

## 1. 核心模块

| 代码路径 | 说明 |
|:---|:---|
| [`opensearch_sdk/client/search_ops.py`](opensearch_sdk/client/search_ops.py) | `SearchOpsMixin` 实现，提供搜索入口 |
| [`opensearch_sdk/client/query_builder.py`](opensearch_sdk/client/query_builder.py) | `QueryBuilder` 静态类，负责 OpenSearch DSL 到 SQL 的转换 |
| [`opensearch_sdk/client/post_filter_mark.py`](opensearch_sdk/client/post_filter_mark.py) | 后过滤标记机制，标识需要 Python 层验证的场景 |

---

## 2. QueryBuilder 核心方法

### build_match_condition()
构建 BM25 全文检索条件。
- **单关键词**：使用 `to_tsquery`。
- **多关键词**：使用 `plainto_tsquery` 自动处理分词和 AND 连接。

### process_bool_clause()
递归处理布尔查询。它会将复杂的嵌套结构分解为 `must_conditions`, `should_conditions` 和 `must_not_conditions` 列表，并最终组合成一个完整的 SQL `WHERE` 子句。

### process_query_item()
处理单个查询项（如 `{"match": {...}}`），返回对应的 SQL 片段、参数列表以及可能的后过滤标记。

---

## 3. SQL 转换原理与优化

### 架构优势
1. **职责分离**：`QueryBuilder` 专注 SQL 生成，`PostValidator` 专注 Python 层验证。
2. **性能优化**：`must_not` 条件下沉到 SQL 层执行，显著减少网络传输和内存占用。
3. **防注入机制**：所有用户输入均通过 `psycopg2.sql.Identifier` 和占位符处理。

### 混合搜索支持
SDK 支持同时包含 `query` (全文) 和 `knn` (向量) 的请求体。内部会分别执行两个查询，然后根据 `_score` 进行合并排序，实现语义与关键词的互补。

---

## 4. 辅助工具

### _validate_identifier()
位于 `utils.py`，用于严格校验索引名和字段名，防止 SQL 注入攻击。

### PostFilterMark
一个轻量级数据结构，用于在查询构建阶段“打点”，告诉执行引擎哪些结果需要在内存中进行二次清洗。
