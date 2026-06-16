# Term 和 Terms 查询处理规范

## 概述

本文档详细说明 Opensearch兼容接口中 `term` 和 `terms` 查询的 SQL 转换策略、实现原理和最佳实践。

### OpenSearch 兼容性说明

**`.keyword` 子字段语法支持**：

Opensearch兼容接口在查询时兼容 OpenSearch 的 `.keyword` 子字段语法，采用**自动剥离策略**：

```python
# OpenSearch 风格（SDK 会自动处理）
query = {
    "term": {
        "categories.keyword": "人工智能"  # SDK 会移除 .keyword 后缀
    }
}

# 等效于
query = {
    "term": {
        "categories": "人工智能"  # 直接使用基础字段名
    }
}
```

**实现位置**：
- `opensearch_sdk/client/query_builder.py`: term/terms 查询处理
- `opensearch_sdk/client/utils.py`: 标识符标准化

**重要提示**：
- **索引创建时不支持 `fields` 配置**：`{"type": "text", "fields": {"keyword": {...}}}` 中的 `fields` 会被忽略
- **查询时支持 `.keyword` 语法**：SDK 会自动剥离后缀并使用基础字段名
- **语义差异**：OpenSearch 中 `field` 和 `field.keyword` 是两个独立字段，Opensearch 中只有一个字段，通过不同查询操作符区分语义

---

## 1. Term 查询（单值精确匹配）

### 1.1 OpenSearch 语义

```json
{
  "query": {
    "term": {
      "tags": "sale"
    }
  }
}
```

**语义**：精确匹配字段值为 `"sale"` 的文档（不分词、不评分）。

### 1.2 SQL 转换策略

#### 策略选择

根据调用上下文，`term` 查询有两种模式：

| 模式 | 使用场景 | SQL 结构 | 性能特点 |
|------|---------|---------|---------|
| **BM25 混合模式** | 独立 term 查询 | `(BM25 AND 精确验证)` | 利用索引，大数据量快 |
| **纯精确模式** | bool 上下文中的 term | `CASE WHEN ...` | 简单直接，兼容性好 |

#### BM25 混合模式（use_bm25=True）

**生成的 SQL**：
```sql
WHERE (
    (tags <&> 'sale'::text) > 0 
    AND 
    CASE WHEN tags LIKE '[%' 
        THEN EXISTS (SELECT 1 FROM json_array_elements_text(tags::json) AS elem WHERE elem = 'sale')
        ELSE tags = 'sale'
    END
)
```

**工作原理**：
1. **BM25 初筛**：`(tags <&> 'sale'::text) > 0`
   - 利用 BM25 全文索引快速过滤候选集
   - 适用于大数据量场景
   
2. **精确验证**：`CASE WHEN ...`
   - JSON 数组字段：使用 `EXISTS` 子查询展开数组并精确匹配
   - 单值字段：直接使用 `=` 比较
   - 确保真正的精确匹配语义

3. **参数传递**：3 个参数
   - `'sale'` - BM25 操作符
   - `'sale'` - EXISTS 子查询
   - `'sale'` - 单值比较

**优势**：
- 利用 BM25 索引加速大数据量查询
- 精确验证确保准确性
- 兼容单值和数组字段

**适用场景**：
- 独立的 term 查询
- 大数据量（> 10K 文档）
- keyword 类型字段

#### 纯精确模式（use_bm25=False）

**生成的 SQL**：
```sql
WHERE CASE WHEN tags LIKE '[%' 
    THEN EXISTS (SELECT 1 FROM json_array_elements_text(tags::json) AS elem WHERE elem = 'sale')
    ELSE tags = 'sale'
END
```

**工作原理**：
- 不使用 BM25，直接精确匹配
- 通过 `CASE WHEN` 兼容单值和数组字段

**优势**：
- SQL 结构简单
- 避免 openGauss 解析复杂嵌套的问题
- 适合 bool 上下文中的多个条件组合

**适用场景**：
- bool 查询中的 must/should/filter 子句
- 小数据量查询
- 需要与其他条件组合的场景

### 1.3 代码实现

```python
@staticmethod
def build_term_condition(field: str, value: Any, use_bm25: bool = True) -> Tuple[sql.Composable, List[Any]]:
    """
    构建 term 查询条件
    
    :param field: 字段名
    :param value: 查询值
    :param use_bm25: 是否使用 BM25 操作符（默认 True）
    :return: (SQL 条件，参数列表)
    """
    validated_field = normalize_identifier(field, "Query field")
    
    if use_bm25:
        # BM25 初筛 + CASE WHEN 精确验证（混合策略）
        condition = sql.SQL(
            "(({} <&> %s::text) > 0 AND CASE WHEN {} LIKE '[%%' THEN EXISTS (SELECT 1 FROM json_array_elements_text({}::json) AS elem WHERE elem = %s) ELSE {} = %s END)"
        ).format(
            sql.Identifier(validated_field),
            sql.Identifier(validated_field),
            sql.Identifier(validated_field),
            sql.Identifier(validated_field)
        )
        params = [str(value), value, value]  # 三个参数：BM25、EXISTS、单值比较
    else:
        # 纯精确匹配（用于 bool 上下文）
        condition = sql.SQL(
            "CASE WHEN {} LIKE '[%%' THEN EXISTS (SELECT 1 FROM json_array_elements_text({}::json) AS elem WHERE elem = %s) ELSE {} = %s END"
        ).format(
            sql.Identifier(validated_field),
            sql.Identifier(validated_field),
            sql.Identifier(validated_field)
        )
        params = [value, value]
    
    return condition, params
```

---

## 2. Terms 查询（多值 OR 逻辑）

### 2.1 OpenSearch 语义

```json
{
  "query": {
    "terms": {
      "tags": ["sale", "hot", "new"]
    }
  }
}
```

**语义**：匹配字段值为 `"sale"` **或** `"hot"` **或** `"new"` 的文档（OR 逻辑）。

等价于：
```json
{
  "query": {
    "bool": {
      "should": [
        {"term": {"tags": "sale"}},
        {"term": {"tags": "hot"}},
        {"term": {"tags": "new"}}
      ]
    }
  }
}
```

### 2.2 SQL 转换策略

#### 数值类型优化

如果所有值都是数值类型，使用 SQL `IN` 操作符：

```sql
WHERE price IN (100, 200, 300)
```

**优势**：
- SQL 简洁高效
- 数据库原生支持，性能好

#### 字符串类型（当前实现）

**生成的 SQL**（terms: `["sale", "hot"]`）：
```sql
WHERE 
    CASE WHEN tags LIKE '[%' 
        THEN EXISTS (SELECT 1 FROM json_array_elements_text(tags::json) AS elem WHERE elem = 'sale')
        ELSE tags = 'sale'
    END
    OR
    CASE WHEN tags LIKE '[%' 
        THEN EXISTS (SELECT 1 FROM json_array_elements_text(tags::json) AS elem WHERE elem = 'hot')
        ELSE tags = 'hot'
    END
```

**工作原理**：
1. **为每个值生成独立的精确匹配条件**
   - 兼容单值和数组字段
   - 不使用 BM25（避免复杂嵌套导致 openGauss 解析失败）

2. **用 OR 连接所有条件**
   - 符合 OpenSearch 的 terms OR 语义
   - PostgreSQL 会进行 OR 短路优化

3. **参数传递**：每个值 2 个参数
   - `'sale'` - EXISTS 子查询
   - `'sale'` - 单值比较
   - 2 个 values = 4 个参数

**设计决策说明**：

**为什么不使用 BM25？**

早期尝试过以下方案，但都失败了：

1. **方案 1：每个值都用 BM25 + 精确验证，然后 OR 连接**
   ```sql
   WHERE ((BM25_1 AND CASE_1) OR (BM25_2 AND CASE_2))
   ```
   - 嵌套深度 O(n)，openGauss 解析失败
   - Composed 对象嵌套过深

2. **方案 2：扁平化结构 (BM25_1 OR BM25_2) AND (CASE_1 OR CASE_2)**
   ```sql
   WHERE ((BM25_1 OR BM25_2) AND (CASE_1 OR CASE_2))
   ```
   - 技术上可行，测试通过
   - 但用户修改后移除了 BM25

**最终选择：纯精确匹配**
- SQL 结构简单，无嵌套问题
- 语义正确，完全符合 terms OR 逻辑
- 大数据量下性能依赖 B-tree 索引

### 2.3 代码实现

```python
@staticmethod
def build_terms_condition(field: str, values: List[Any]) -> Tuple[sql.Composable, List[Any]]:
    """
    构建 terms 查询条件（多个值的 OR 逻辑）
    
    策略：将每个值转换为独立的 term 条件，用 OR 连接
    例如：terms: {"field": ["a", "b"]} → (term: field=a) OR (term: field=b)
        
    :param field: 字段名
    :param values: 值列表
    :return: (SQL 条件，参数列表)
    """
    validated_field = normalize_identifier(field, "Query field")
    
    # 空数组处理
    if not values:
        return sql.SQL("1 = 0"), []
    
    # 检查是否所有值都是纯数值类型
    all_numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
    
    if all_numeric:
        # 数值类型：使用 SQL IN
        placeholders = sql.SQL(", ").join([sql.SQL("%s")] * len(values))
        condition = sql.SQL("{} IN ({})").format(
            sql.Identifier(validated_field),
            placeholders
        )
        params = list(values)
    else:
        # 字符串类型：为每个值构建独立的 term 条件，然后用 OR 连接
        # 简化策略：直接使用精确匹配，不使用 BM25 初筛
        
        term_conditions = []
        params = []
        
        for value in values:
            # 直接使用精确匹配（兼容单值和数组）
            exact_cond = sql.SQL(
                "CASE WHEN {} LIKE '[%%' THEN EXISTS (SELECT 1 FROM json_array_elements_text({}::json) AS elem WHERE elem = %s) ELSE {} = %s END"
            ).format(
                sql.Identifier(validated_field),
                sql.Identifier(validated_field),
                sql.Identifier(validated_field)
            )
            term_conditions.append(exact_cond)
            params.extend([value, value])
        
        # 将所有 term 条件用 OR 连接
        if len(term_conditions) == 1:
            condition = term_conditions[0]
        else:
            condition = sql.SQL(" OR ").join(term_conditions)
    
    return condition, params
```

---

## 3. 关键技术点

### 3.1 JSON 数组兼容性

Opensearch 中，keyword 类型的多值字段会被序列化为 JSON 数组存储在 TEXT 列中：

| 存储形式 | 示例 | 查询方式 |
|---------|------|---------|
| **单值** | `"sale"` | `tags = 'sale'` |
| **数组** | `["sale", "hot"]` | `EXISTS (SELECT 1 FROM json_array_elements_text(tags::json) AS elem WHERE elem = 'sale')` |

**兼容策略**：使用 `CASE WHEN` 动态判断：
```sql
CASE WHEN tags LIKE '[%' 
    THEN -- 数组：使用 EXISTS 子查询
    ELSE -- 单值：使用 = 比较
END
```

### 3.2 性能优化建议

#### 添加 B-tree 索引

对于频繁查询的 keyword 字段，建议创建 B-tree 索引：

```sql
CREATE INDEX idx_tags ON table_name (tags);
```

**效果**：
- 单值字段：索引加速明显
- 数组字段：索引帮助有限（需要 JSON 解析）

#### 限制 terms 的 values 数量

- **建议**：terms 的 values 数量控制在 10 以内
- **原因**：
  - 每个 value 生成一个完整的 CASE WHEN 条件
  - SQL 长度随 values 数量线性增长
  - 过多 values 可能导致 SQL 过长

#### 大数据量场景

如果数据量 > 100K 且 terms 查询频繁：
1. 考虑使用 `bool.should` 替代 `terms`
2. 或者恢复 BM25 混合模式（需解决 openGauss 解析问题）

### 3.3 常见陷阱

#### 陷阱 1：误用 BM25 进行精确匹配

**错误做法**：
```sql
-- BM25 会对 "sale hot" 分词和评分，不是真正的 OR
WHERE (tags <&> 'sale hot'::text) > 0
```

**正确做法**：
```sql
-- 每个值独立匹配，用 OR 连接
WHERE (tags = 'sale') OR (tags = 'hot')
```

#### 陷阱 2：忽略数组字段的特殊性

**错误做法**：
```sql
-- 无法匹配数组字段
WHERE tags = 'sale'
```

**正确做法**：
```sql
-- 兼容单值和数组
CASE WHEN tags LIKE '[%' 
    THEN EXISTS (...)
    ELSE tags = 'sale'
END
```

#### 陷阱 3：过度嵌套导致解析失败

**错误结构**（嵌套过深）：
```sql
WHERE ((BM25_1 AND CASE_1) OR (BM25_2 AND CASE_2) OR ...)
```

**优化结构**（扁平化）：
```sql
WHERE (CASE_1 OR CASE_2 OR ...)
```

---

## 4. 测试验证

### 4.1 单元测试

运行 keyword 多值测试：
```bash
python -m unittest opensearch_sdk.tests.features.data_types.test_keyword_multi_value
```

**测试覆盖**：
- 数组存储和标量存储
- term 查询单值字段
- term 查询多值字段
- terms 查询多值字段
- 精确匹配（不包括相似值）
- OR 逻辑验证

### 4.2 性能基准

**1000 条数据测试结果**：

| 查询类型 | 平均耗时 | 命中数 | 说明 |
|---------|---------|--------|------|
| 单值 term | 8.90 ms | 100 | category 字段（单值） |
| 数组 term | 17.89 ms | 400 | tags 字段（数组） |
| terms (2值) | 11.33 ms | 800 | tags 字段，OR 逻辑 |

**分析**：
- terms 查询性能介于单值和数组 term 之间
- OR 短路优化有效
- 数组字段比单值字段慢 ~2x（JSON 解析开销）

---

## 5. 最佳实践

### 5.1 何时使用 term vs terms

| 场景 | 推荐查询 | 原因 |
|------|---------|------|
| 单个精确值 | `term` | 语义清晰，SQL 简单 |
| 2-5 个值 | `terms` | OR 逻辑明确，代码简洁 |
| > 10 个值 | `bool.should` + 多个 `term` | 更灵活，可控制 min_should_match |
| 范围查询 | `range` | 专门的 range 查询更高效 |

### 5.2 字段类型选择

| 字段类型 | 适用场景 | 查询方式 |
|---------|---------|---------|
| `keyword` | 精确匹配、聚合、排序 | `term`, `terms` |
| `text` | 全文检索、模糊匹配 | `match`, `match_phrase` |
| `multi_keyword` | 多值精确匹配 | `term`, `terms` |

### 5.3 索引策略

```sql
-- 为频繁查询的 keyword 字段创建索引
CREATE INDEX idx_category ON products (category);
CREATE INDEX idx_tags ON products (tags);

-- 复合索引（如果经常组合查询）
CREATE INDEX idx_category_tags ON products (category, tags);
```

---

## 6. 常见问题 FAQ

### Q1: 为什么 terms 不使用 BM25？

**A**: 早期实现尝试过 BM25，但遇到以下问题：
1. openGauss 对深层嵌套的 Composed SQL 解析失败
2. BM25 是全文检索操作符，不适合精确匹配的 terms 语义
3. 纯精确匹配 + B-tree 索引已能满足大部分场景

如果需要更好的性能，可以考虑：
- 添加 B-tree 索引
- 限制 terms 的 values 数量
- 使用 `bool.should` 替代

### Q2: 数组字段的性能为什么比单值字段差？

**A**: 数组字段需要：
1. JSON 解析：`tags::json`
2. 数组展开：`json_array_elements_text()`
3. EXISTS 子查询：逐元素匹配

这些操作的开销远大于简单的 `=` 比较。优化建议：
- 添加 B-tree 索引（对单值有帮助）
- 尽量避免在高频查询中使用数组字段
- 考虑将常用值提取为单独的字段

### Q3: 如何调试 terms 查询生成的 SQL？

**A**: 启用 SQL 追踪：
```python
client.enable_sql_trace = True
result = client.search(index='my_index', body={'query': {'terms': {...}}})
sessions = client.sql_tracer.get_all_sessions()
for session in sessions:
    for record in session.get_records():
        print(record.sql)
        print(record.params)
```

---

## 7. 总结

### 核心要点

1. **Term 查询**：
   - 支持 BM25 混合模式和纯精确模式
   - 根据调用上下文自动选择
   - 兼容单值和数组字段

2. **Terms 查询**：
   - 将每个值转换为独立的 term 条件
   - 用 OR 连接所有条件
   - 数值类型使用 SQL IN 优化
   - 字符串类型使用纯精确匹配

3. **兼容性**：
   - 使用 `CASE WHEN LIKE '[%'` 检测 JSON 数组
   - 自动适配单值和数组字段
   - 无需应用层判断字段类型

4. **性能**：
   - 小数据量：纯精确匹配足够
   - 大数据量：依赖 B-tree 索引
   - 建议限制 terms 的 values 数量

### 未来优化方向

1. **恢复 BM25 混合模式**（可选）
   - 解决 openGauss 解析问题
   - 提供配置开关让用户选择

2. **智能索引建议**
   - 自动检测高频查询字段
   - 提示用户创建索引

3. **查询计划分析**
   - 集成 EXPLAIN 分析
   - 自动优化慢查询

---

**文档版本**: v1.0  
**最后更新**: 2026-04-13  
**维护者**: Opensearch兼容接口Team
