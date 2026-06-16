# Term 与 Terms 精确匹配

本章节介绍 Opensearch兼容接口的 `term` 和 `terms` 查询，用于处理标量和多值字段的精确匹配。

## 1. term 查询 (标量精确匹配)

### 功能描述
用于精确匹配单个值。根据字段类型自动选择最优的 SQL 实现方式。

### 代码示例
```python
body = {"query": {"term": {"status": "active"}}}
result = client.search("my_index", body)
```

### SQL 生成逻辑
根据值类型选择不同的 SQL 策略：

**文本类型（str）**：
```sql
(field <&> %s::text) > 0
-- params: ['active']
```
使用 BM25 操作符进行全文检索，支持中文分词。

**非文本类型（int/float/bool）**：
```sql
field = %s
-- params: [42] 或 [True]
```
使用简单的等值比较，性能更高。

### 类型检测逻辑
- `isinstance(value, str)` → 使用 BM25
- 其他类型 → 使用 `=` 运算符

这种设计确保了文本字段能利用 BM25 索引加速，而非文本字段则使用高效的等值比较。

---

## 2. terms 查询 (多值精确匹配)

### 功能描述
用于匹配多个可能的值，逻辑上等同于 SQL 中的 `OR` 连接。

### 代码示例
```python
body = {"query": {"terms": {"category": ["tech", "news", "blog"]}}}
result = client.search("my_index", body)
```

### SQL 生成逻辑
根据值类型选择不同的 SQL 策略：

**数值类型（int/float）**：
```sql
field IN (%s, %s, %s)
-- params: [10, 20, 30]
```
使用标准的 SQL `IN` 子句，性能最优。

**字符串类型**：
```sql
(
  (field <&> %s::text) > 0 AND 
  CASE WHEN field LIKE '[%' THEN 
    EXISTS (SELECT 1 FROM json_array_elements_text(field::json) AS elem WHERE elem = %s)
  ELSE field = %s END
) OR (
  (field <&> %s::text) > 0 AND 
  CASE WHEN field LIKE '[%' THEN 
    EXISTS (SELECT 1 FROM json_array_elements_text(field::json) AS elem WHERE elem = %s)
  ELSE field = %s END
) OR ...
-- params: ['tech', 'tech', 'tech', 'news', 'news', 'news', ...]
```
每个值包含三个部分：
1. **BM25 初筛**：`(field <&> %s::text) > 0` 快速过滤
2. **JSON 数组处理**：如果字段是 JSON 数组，使用 `json_array_elements_text` 展开后匹配
3. **标量精确匹配**：否则直接使用 `=` 比较

这种复杂的设计确保了 terms 查询能同时支持：
- 普通标量字段
- JSONB 数组字段
- BM25 索引加速

---

## 3. QueryBuilder 核心方法

### build_term_condition()
构建单个值的精确匹配条件，自动处理数组兼容性。

### build_terms_condition()
构建多值匹配条件，遍历所有值并调用 `build_term_condition` 进行组合。
