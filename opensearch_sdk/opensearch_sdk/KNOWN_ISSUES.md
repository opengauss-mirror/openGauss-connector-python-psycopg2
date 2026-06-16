# openGauss SDK 已知功能限制

## ISSUE-001: BM25 不支持短语匹配操作符

---

### 现象描述

使用 `match_phrase` 查询时，无法利用 BM25 全文索引，退化为 LIKE 全表扫描。

- 查询性能下降（大数据量场景显著恶化）
- 失去 BM25 相关性评分
- 功能正常，能返回正确结果

---

### 影响范围

**受影响的查询类型：**
- `match_phrase` 查询
- `bool.must` / `bool.should` / `bool.must_not` 中的 `match_phrase`

**受影响的业务场景：**
- 分类搜索（`search_by_category`）
- 任何需要精确短语匹配的查询

---

### 根本原因

openGauss 的 BM25 实现存在技术限制：

```sql
-- 不支持 tsquery 类型
text_field <&> to_tsquery('hello world')

-- 不支持短语匹配操作符
text_field <&> to_tsquery('hello <-> world')
-- 报错："operator does not exist: text <&> tsquery"

-- 仅支持基本全文匹配
text_field <&> 'hello'::text
```

**当前实现**（`opensearch_sdk/opensearch_sdk.py`）：
```python
# match_phrase 降级为 LIKE 匹配
if "match_phrase" in query:
 where_conditions.append(sql.SQL("{} LIKE %s").format(field))
 params.append('%' + phrase + '%')
```

生成的 SQL：
```sql
WHERE categories LIKE '%one%'
```

---

### 解决方案

#### 方案 A：改用 keyword 类型 + terms 查询 [推荐]（推荐）

**适用场景**：分类标签、枚举值等精确匹配

```python
# 修改 mapping
mapping = {
 "mappings": {
 "properties": {
 "categories": {
 "type": "keyword", # 改为 keyword
 "index": True
 }
 }
 }
}

# 修改查询
query = {
 "query": {
 "terms": {
 "categories": ["one"]
 }
 }
}
```

**优点：**
- 精确匹配，不误匹配
- 使用 B-tree 索引，性能好
- 支持数组字段（JSONB @>）

---

#### 方案 B：改用 match 查询 [备选]

**适用场景**：可接受部分匹配的全文检索

```python
query = {
 "query": {
 "match": {
 "categories": "one"
 }
 }
}
```

**优点：**
- 利用 BM25 索引，性能好
- 支持相关性评分

**缺点：**
- 不保证短语完整性
- 可能返回更多结果

---

#### 方案 C：保持现状 [可选]

**适用场景**：数据量小（< 10 万条）

如果数据量较小，LIKE 的性能影响可接受。

---

### 验证方法

```bash
# 运行专项测试
python test_match_phrase.py

# 查看执行计划
EXPLAIN SELECT * FROM table WHERE content LIKE '%phrase%';
```
---

## ISSUE-002: Nested 类型支持采用首值策略（多值数据会丢失）

---

### 现象描述

SDK 支持 OpenSearch 风格的 nested 类型 mapping，但采用**首值策略**处理 nested 数组：

- **数组格式输入**：`"authors": [{"name": "John"}, {"name": "Jane"}]` → 只存储第一个对象 `{"name": "John"}`
- **字典格式输入**：`"authors": {"name": "John"}` → 正常存储
- **多值场景**：如果业务需要存储多个 nested 对象，会导致数据丢失

---

### 影响范围

**受限制的场景：**
- 不支持一对多关系的 nested 对象存储（如多作者、多标签）
- 无法查询 nested 数组中的非首个元素
- 写入多值 nested 数组时静默丢弃后续元素（不抛异常）

**不受影响的场景：**
- 单一主要对象（如文章的主要作者、商品的生产厂商）
- 一对一关系（如用户的个人资料、订单的收货地址）
- 配置信息（如系统配置、主题设置）

---

### 技术方案说明

#### 核心设计决策

**为什么采用首值策略？**

1. **保持架构一致性**：与现有扁平化存储方案无缝集成
2. **性能最优**：避免 JSON 解析的性能开销和复杂查询逻辑
3. **实现简单**：无需管理关联表或多值数组的复杂性
4. **业务适配**：当前业务场景最多只有一个 nested 对象

#### 实现细节

**Mapping 验证阶段** (`indices.py`)：
```python
supported_types = {
 'text', 'keyword', 'long', 'integer', 'float', 
 'boolean', 'date', 'float_vector', 'dense_vector', 'knn_vector',
 'nested' # 新增：支持 nested 类型
}
```

**索引创建阶段** - 扁平化展开：
```python
# 原始 nested mapping
{
 "author": {
 "type": "nested",
 "properties": {
 "name": {"type": "keyword"},
 "contact_ref": {"type": "keyword"}
 }
 }
}

# 展开后的表结构
CREATE TABLE articles (
 id VARCHAR PRIMARY KEY,
 author_name VARCHAR,
 author_contact_ref VARCHAR
);
```

**文档写入阶段** - 首值提取 (`document_ops.py`)：
```python
def _flatten_nested_value(value: Any) -> Any:
 """处理 nested 字段的值，支持数组和字典两种格式（首值策略）"""
 if value is None:
 return None
 
 if isinstance(value, list):
 # 数组格式：取第一个元素
 if len(value) == 0:
 return None
 else:
 return value[0] # Known Issue: 多值情况只取第一个
 elif isinstance(value, dict):
 # 字典格式：直接返回
 return value
 else:
 return value
```

**查询阶段** - 字段名扁平化 (`query_builder.py`)：
```python
# 用户查询
{
 "query": {
 "nested": {
 "path": "author",
 "query": {
 "term": {"name": "John Doe"}
 }
 }
 }
}

# SDK 转换为 SQL
SELECT * FROM articles 
WHERE author_name = 'John Doe'
```

---

### 解决方案

#### 方案 A：使用本 SDK 的 nested 支持 [推荐]（推荐用于单一对象场景）

**适用场景**：一对一关系、主要对象、默认配置

```python
# 正确用法：单个 nested 对象
doc = {
 "title": "Article",
 "author": {"name": "John Doe", "contact_ref": "john-contact"}
}
client.index(index='articles', id='1', body=doc)

# 正确用法：单元素 nested 数组
doc = {
 "title": "Article",
 "author": [{"name": "John Doe", "contact_ref": "john-contact"}]
}
client.index(index='articles', id='1', body=doc)
```

**优点：**
- 语法兼容 OpenSearch
- 实现简单，性能优秀
- 支持数组和字典双格式输入

**缺点：**
- 多值 nested 数组会丢失数据

---

#### 方案 B：关联表方案 [备选]（推荐用于多值场景）

**适用场景**：一对多关系、需要保留所有元素

```python
# 主表
CREATE TABLE articles (
 id VARCHAR PRIMARY KEY,
 title TEXT,
 content TEXT
);

# Nested 展开为关联表
CREATE TABLE article_authors (
 article_id VARCHAR REFERENCES articles(id),
 name VARCHAR,
 contact_ref VARCHAR,
 role VARCHAR
);

# 插入数据
client.index(index='articles', id='1', body={"title": "Article"})
client.execute_sql(
 "INSERT INTO article_authors (article_id, name, contact_ref) VALUES (%s, %s, %s)",
 ('1', 'John Doe', 'john-contact')
)
client.execute_sql(
 "INSERT INTO article_authors (article_id, name, contact_ref) VALUES (%s, %s, %s)",
 ('1', 'Jane Smith', 'jane-contact')
)
```

**优点：**
- 完全规范化，符合关系型数据库设计
- 支持复杂查询和聚合
- 无数据丢失

**缺点：**
- 实现复杂，需要管理多表一致性
- 写入开销增加（涉及多表操作）

---

#### 方案 C：JSONB 字段存储 [可选]（灵活但不推荐）

**适用场景**：数据结构不确定或频繁变化

```python
# 使用 JSONB 类型存储整个 nested 数组
mapping = {
 "mappings": {
 "properties": {
 "authors": {"type": "jsonb"} # 存储任意 JSON 数据
 }
 }
}

doc = {
 "title": "Article",
 "authors": [
 {"name": "John", "contact_ref": "john-contact"},
 {"name": "Jane", "contact_ref": "jane-contact"}
 ]
}
client.index(index='articles', id='1', body=doc)
```

**优点：**
- 灵活，可存储任意结构的数据
- 无数据丢失

**缺点：**
- 查询需要使用 JSON 函数，性能较差
- 无法利用常规索引（需要 GIN 索引）

---

### 验证方法

```python
# 正确用法示例
doc = {
 "title": "Test Article",
 "author": {
 "name": "John Doe",
 "contact_ref": "john-contact"
 }
}
result = client.index(index='test_articles', id='1', body=doc)
print(f"写入成功：{result}")

# 错误用法示例（会丢失数据）
doc = {
 "title": "Multi-Author Article",
 "authors": [
 {"name": "First Author", "contact_ref": "first-contact"},
 {"name": "Second Author", "contact_ref": "second-contact"}, # 会被丢弃
 {"name": "Third Author", "contact_ref": "third-contact"} # 会被丢弃
 ]
}
result = client.index(index='test_articles', id='2', body=doc)

# 验证存储结果
retrieved = client.get(index='test_articles', id='2')
print(f"存储的作者：{retrieved['_source'].get('authors_name')}")
# 输出：First Author（只有第一个作者被存储）
```

---

## ISSUE-003: terms 查询对 keyword 多值字段的特殊处理

### 现象描述

当使用 `terms` 查询 keyword 类型的多值字段时，SDK 会将多个值拼接为一个字符串进行 BM25 匹配：

```python
# 用户查询
query = {
 "query": {
 "terms": {
 "category": ["electronics", "books"]
 }
 }
}

# SDK 内部转换为
WHERE (category <&> 'electronics books'::text) > 0
ORDER BY category <&> 'electronics books'::text DESC
```

**行为特点：**
- 能正确返回包含任一值的文档（OR 逻辑）
- 利用 BM25 倒排索引，性能优秀
- **依赖 BM25 分词器行为，可能产生意外匹配**（见下方示例）

---

### 影响范围

**受影响的查询类型：**
- `terms` 查询（多个值的精确匹配）
- `bool.must/filter/should` 中的 `terms` 子句

**字段类型要求：**
- keyword 字段（必须有 BM25 索引）
- integer/float 等数值字段（使用 SQL IN）

---

### 根本原因

**设计决策：**

1. **BM25 必须在 ORDER BY 中使用**
 - openGauss 的 BM25 优化器要求 `<&>` 操作符同时出现在 WHERE 和 ORDER BY 中
 - 否则报错："No BM25 index is used to the scan"

2. **多个 OR 连接的复杂性**
 ```sql
 -- 方案 A：多个 OR（复杂）
 WHERE (field <&> 'val1') > 0 OR (field <&> 'val2') > 0
 ORDER BY field <&> 'val1'::text DESC -- 只用第一个值排序
 
 -- 方案 B：拼接字符串（简洁） WHERE (field <&> 'val1 val2'::text) > 0
 ORDER BY field <&> 'val1 val2'::text DESC
 ```

3. **数值字段的特殊处理**
 - 数值字段没有 BM25 索引
 - 使用 SQL IN 更合适：`WHERE price IN (50, 100)`

---

### 潜在问题：BM25 分词导致的误匹配

**示例场景：**

```python
# 假设文档数据
doc1 = {"category": "electronics"} # 单个值
doc2 = {"category": "electronic devices"} # 包含 "electronic"

# terms 查询
query = {
 "query": {
 "terms": {
 "category": ["electronics"] # 期望只匹配 doc1
 }
 }
}

# SDK 转换为
WHERE (category <&> 'electronics'::text) > 0

# BM25 分词后可能匹配：
# - "electronics" → 匹配 # - "electronic devices" → 也可能匹配 （因为 "electronic" 是 "electronics" 的词干）
```

**根本原因：**
- BM25 使用全文检索分词器，会对查询词进行分词和词干提取
- `"electronics books"` 会被分词为 `["electronics", "books"]`
- 如果文档中包含这些词的变体（如 "electronic"），也可能被匹配

**影响程度：**
- **低**：对于 keyword 字段，通常存储的是标准化后的值
- **中**：如果字段内容包含自然语言文本，可能产生误匹配

---

### 解决方案

#### 当前实现（已优化）[推荐]

**query_builder.py 中的智能策略：**

```python
def build_terms_condition(field: str, values: List[Any]):
 # 检查是否所有值都是纯数值类型
 all_numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
 
 if all_numeric:
 # 数值类型：使用 SQL IN
 condition = sql.SQL("{} IN ({})").format(...)
 params = list(values)
 else:
 # 字符串类型：拼接后用 BM25
 combined_value = " ".join(str(val) for val in values)
 condition = sql.SQL("({} <&> %s::text) > 0").format(...)
 params = [combined_value]
```

**search_ops.py 中的 BM25 检测：**

```python
# 在 bool 查询分支中也添加 BM25 检测
if "bool" in query:
 where_conds, params, _ = QueryBuilder.process_bool_clause(bool_query, depth=0)
 
 if where_conds:
 # 检测是否有 <&> 操作符
 for cond in where_conds:
 if '<&>' in str(cond):
 # 提取字段名并添加 ORDER BY
 bm25_field = extract_field_name(cond)
 order_by = f"ORDER BY {bm25_field} <&> %s::text DESC"
 params.append(params[0]) # 复用第一个参数
```

---

### 验证方法

```bash
# 运行测试套件
python opensearch_sdk/tests/other_features/test_terms_query.py
python -m unittest opensearch_sdk.tests.other_features.test_keyword_multi_value

# 预期结果：所有测试通过
```

---

### 注意事项

1. **必须为 keyword 字段创建 BM25 索引**
 ```python
 from opensearch_sdk.retrieval import IndexConfig, IndexType
 
 index_config = IndexConfig(
 name="idx_category_bm25",
 column="category",
 index_type=IndexType.BM25
 )
 client.connection.execute(index_config.to_sql(table_name))
 ```

2. **数值字段自动使用 SQL IN**
 - 无需手动干预
 - 性能更优（B-tree 索引）

3. **嵌套在 bool 查询中也能正常工作**
 - 已修复 search_ops.py 的检测逻辑
 - 支持 must/filter/should 子句

---

---
