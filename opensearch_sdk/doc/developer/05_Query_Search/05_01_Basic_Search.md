# 基础搜索功能

本章节介绍 Opensearch兼容接口的基础全文检索功能，包括 `match` 和 `match_phrase` 查询。

## 1. match 查询 (BM25 全文检索)

### 功能描述
使用 BM25 算法进行全文关键词搜索。底层通过 PostgreSQL 的 `to_tsvector` 和 `plainto_tsquery` 实现。

### 代码示例
```python
body = {"query": {"match": {"title": "Opensearch"}}}
result = client.search("my_index", body)
```

### SQL 生成逻辑
- **单关键词**：`to_tsvector('simple', title) @@ to_tsquery('simple', 'Opensearch'::text)`
- **多关键词**：`to_tsvector('simple', content) @@ plainto_tsquery('simple', '数据库 基础'::text)`

---

## 2. match_phrase 查询 (短语精确匹配)

### 功能描述
执行短语精确匹配。采用 BM25 + LIKE 双重过滤策略，并在 Python 层进行二次验证以确保短语的连续性。

### 代码示例
```python
# 严格短语匹配（slop=0）
body = {"query": {"match_phrase": {"content": "hello world"}}}
result = client.search("my_index", body)

# 允许间隔词的短语匹配（slop=2）
body = {
    "query": {
        "match_phrase": {
            "content": {
                "query": "hello world",
                "slop": 2  # 允许单词间最多间隔 2 个词
            }
        }
    }
}
result = client.search("my_index", body)
```

### 双重验证机制
1. **SQL 层初筛**：
   - 使用 `(<&> 'phrase'::text) > 0` 快速筛选包含所有词的文档
   - 如果是严格短语（slop=None 或 0），额外添加 `field ILIKE '%phrase%'` 条件
2. **Python 层精验**：
   - 调用 `_verify_strict_phrase()` 确保短语在文本中连续出现（slop=0）
   - 调用 `_verify_slop_phrase()` 检查词间距是否满足 slop 要求（slop>0）

### Slop 参数说明
- **slop=None 或 0**：严格短语匹配，词必须紧密相连
  - 例如：`"quick fox"` 只能匹配 `"the quick fox jumps"`，不能匹配 `"the quick brown fox"`
- **slop>0**：允许词之间有间隔，但间隔词数不能超过 slop
  - 例如：`"quick fox" slop=1` 可以匹配 `"the quick brown fox"`（brown 是 1 个词）
  - 但不能匹配 `"the quick very brown fox"`（very brown 是 2 个词）

### 内部实现
```python
# 严格短语验证（slop=0）
def _verify_strict_phrase(hit, mark):
    text = str(hit["_source"].get(mark.field, ""))
    words = mark.phrase.split()
    pattern = r'\b' + r'\s+'.join(re.escape(word) for word in words) + r'\b'
    return re.search(pattern, text, re.IGNORECASE) is not None

# Slop 短语验证（slop>0）
def _verify_slop_phrase(hit, mark):
    # 找到所有词的位置，检查是否存在满足 slop 要求的组合
    all_positions = _find_word_positions(text, words)
    return _check_position_combinations(text, all_positions, mark.slop)
```
