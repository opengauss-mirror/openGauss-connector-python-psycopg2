# 结果处理与分页

本章节介绍 Opensearch兼容接口如何处理搜索结果、执行分页以及进行 `match_phrase` 的二次验证。

## 1. 搜索响应结构

### 标准化响应
SDK 始终返回符合 OpenSearch 规范的 JSON 结构：
```python
{
    "hits": {
        "total": {"value": 100, "relation": "eq"},
        "hits": [
            {
                "_index": "my_index",
                "_id": "doc1",
                "_score": 1.0,
                "_source": {...}
            }
        ]
    }
}
```

---

## 2. 排序与分页

### 参数说明
- **sort**: 支持多字段排序，如 `["field1", {"field2": {"order": "desc"}}]`。
- **size**: 每页返回数量（默认 10，最大 10000）。
- **from**: 分页偏移量（默认 0）。

### SQL 生成
```sql
SELECT * FROM my_index 
WHERE ... 
ORDER BY field1 ASC, field2 DESC 
LIMIT %s OFFSET %s
```

---

## 3. match_phrase 精确验证流程

由于底层 SQL 使用 `LIKE` 无法保证短语连续性，SDK 在获取结果后会执行 Python 层过滤：

1. **收集标记**：在构建 SQL 时，识别所有 `match_phrase` 条件并记录。
2. **执行查询**：通过 SQL 获取初步候选集。
3. **二次验证**：遍历 `hits`，对每个文档调用 `_verify_match_phrase()`。
4. **过滤结果**：只保留满足所有短语连续性要求的文档，并更新 `total` 计数。

### 为什么需要双重验证？
- **SQL 层**：利用数据库索引提供高性能的初步筛选。
- **Python 层**：确保业务逻辑上“短语匹配”语义的绝对准确。
