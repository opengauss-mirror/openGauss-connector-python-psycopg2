# Bool 组合查询

本章节介绍 Opensearch兼容接口的 `bool` 组合查询功能，包括 `must`, `should`, `must_not` 和 `filter` 子句的处理逻辑。

## 1. 基础 Bool 查询

### 代码示例
```python
body = {
    "query": {
        "bool": {
            "must": [{"match": {"title": "Opensearch"}}],
            "should": [{"term": {"featured": True}}],
            "must_not": [{"term": {"status": "deleted"}}]
        }
    }
}
result = client.search("my_index", body)
```

### 2026-03 重构更新
**支持复杂嵌套**：现在支持多层嵌套的 bool 查询，并能自动处理递归逻辑。
**后过滤标记机制**：自动识别需要 Python 层验证的场景（如 `match_phrase` with slop）。

---

## 2. must_not 条件处理 (SQL 层优化)

### 设计理念
为了减少数据传输并提升性能，`must_not` 条件现在直接在 SQL 层通过 `NOT ILIKE` 或 `NOT IN` 处理。

### SQL 生成示例
```sql
SELECT * FROM my_index 
WHERE (title <&> %s::text) > 0 
  AND status NOT ILIKE %s 
  AND content NOT ILIKE %s
```

### 处理策略
| 查询类型 | SQL 转换方式 |
|:---|:---|
| `match_phrase` | `field NOT ILIKE '%phrase%'` |
| `match` | `field NOT ILIKE '%keyword%'` |
| `term` | `field NOT ILIKE '%value%'` (兼容数组字段) |
| `terms` | `field NOT IN (%s, %s, ...)` |

---

## 3. 内部实现流程

### process_bool_clause()
负责递归处理 bool 子句：
1. **must**: 使用 `AND` 连接所有条件。
2. **should**: 使用 `OR` 连接所有条件。
3. **must_not**: 调用 `_build_must_not_condition()` 生成否定条件。
4. **filter**: 使用 `AND` 连接，不计算相关性得分。

### PostFilterMark 后过滤标记
SDK 引入了 `PostFilterMark` 类来标识那些无法在 SQL 层精确完成的匹配（如带 `slop` 的短语匹配），并在查询执行后在 Python 层进行二次过滤。
