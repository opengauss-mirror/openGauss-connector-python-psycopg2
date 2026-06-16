# 查询与搜索

本章节详细介绍 Opensearch兼容接口的查询与搜索功能。

## 模块信息

**源文件**: `opensearch_sdk/client/search_ops.py`  
**Mixin 类**: `SearchOpsMixin`

## 重要架构说明

### 连接管理模式

Opensearch兼容接口使用 `get_connection_for_operation()` 上下文管理器确保每次搜索操作获取独立连接。

**关键优势**：
- **自动连接管理**：操作完成后自动归还连接到连接池
- **元数据可见性**：新连接自动看到最新的表结构和索引元数据
- **无需手动重连**：DDL 操作后不需要手动重连，新连接会立即感知变化

**详细说明**：请参阅 [索引管理 - 连接管理模式](03_Index_Management.md#连接管理模式)

## search 方法

### 功能描述

执行通用搜索查询，支持多种查询类型。

### 函数签名

```python
def search(self, index: str, body: Dict[str, Any]) -> Any
```

### 参数说明

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|:---|:---|:---:|:---:|:---|
| index | str | 是 | - | 索引名称 |
| body | dict | 是 | - | 搜索请求体 |

### 查询类型

#### match 查询

使用 BM25 全文索引进行关键词搜索：

```python
body = {"query": {"match": {"title": "Opensearch"}}}
result = client.search("my_index", body)
```

#### match_phrase 查询

短语精确匹配（使用 LIKE 实现）：

```python
body = {"query": {"match_phrase": {"content": "hello world"}}}
result = client.search("my_index", body)
```

#### term 查询

精确匹配（支持标量和数组）：

```python
body = {"query": {"term": {"status": "active"}}}
result = client.search("my_index", body)
```

#### terms 查询

多值精确匹配（OR 连接）：

```python
body = {"query": {"terms": {"category": ["tech", "news", "blog"]}}}
result = client.search("my_index", body)
```

#### bool 查询

组合查询：

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

**最新更新（2026-03 重构）**：

**支持复杂嵌套**：
```python
# 多层嵌套示例
body = {
    "query": {
        "bool": {
            "must": [
                {
                    "bool": {
                        "must": [{"match_phrase": {"status": "published"}}],
                        "filter": [{"range": {"view_count": {"gte": 100}}}]
                    }
                }
            ],
            "should": [{"match_phrase": {"tags": "tutorial"}}],
            "must_not": [{"term": {"author": "admin"}}],
            "filter": [{"term": {"category": "tech"}}]
        }
    }
}
```

**后过滤标记机制**：自动识别需要 Python 层验证的场景
- `match_phrase` 严格匹配 → LIKE 后过滤
- `match_phrase` with slop > 0 → 短语连续性验证
- 递归传播标记到所有嵌套层级

### must_not 条件处理

**最新更新（2026-03）**：must_not 条件现在在 SQL 层处理，使用 `NOT ILIKE`：

```python
# must_not 查询示例
body = {
    "query": {
        "bool": {
            "must": [{"match": {"title": "Opensearch"}}],
            "must_not": [
                {"term": {"status": "deleted"}},
                {"match": {"content": "obsolete"}}
            ]
        }
    }
}
```

**SQL 生成**：

``sql
SELECT * FROM my_index 
WHERE (title <&> %s::text) > 0 
  AND status NOT ILIKE %s 
  AND content NOT ILIKE %s
```

**优势**：

1. 减少数据传输（数据库层过滤）
2. 降低内存占用
3. 提升大数据量场景性能
4. 符合 Opensearch 查询优化器行为

### 实现细节

**内部实现流程**：

```
1. 验证索引名称
2. 构建基础 SQL: SELECT * FROM {index}
3. 处理查询条件
   ├── match: BM25 (<&> 操作符)
   ├── match_phrase: LIKE 模糊匹配
   ├── term: 精确匹配 (= 或 JSONB @>)
   ├── terms: OR 连接多值
   └── bool: must/must_not/should 组合（2026-03 重构）
       ├── process_bool_clause(): 递归处理嵌套
       │   ├── must: AND 连接，收集后过滤标记
       │   ├── should: OR 连接，收集后过滤标记
       │   ├── must_not: NOT 条件，SQL 层处理
       │   └── filter: AND 连接，无后过滤
       ├── process_query_item(): 单个查询项
       │   └── 返回 (Composable, params, PostFilterMark[])
       └── PostFilterMark: 标识需要 Python 层验证的场景
4. 执行 SQL 查询
5. 后过滤（如果有标记）
   └── PostValidator.validate(): 执行短语连续性验证
6. 处理排序和分页
```

**架构优势**：
- **职责分离**：QueryBuilder 负责 SQL，PostValidator 负责 Python 验证
- **性能优化**：Must Not 在 SQL 层过滤，减少数据传输
- **灵活扩展**：支持任意复杂度的嵌套查询

### QueryBuilder 查询构建器

#### 模块信息

**源文件**: `opensearch_sdk/client/query_builder.py`

**使用方式**：
```python
from opensearch_sdk.client.query_builder import QueryBuilder

# 构建 match 条件
condition, params = QueryBuilder.build_match_condition("title", "Opensearch")
```

#### 主要方法

| 方法 | 功能 | 返回值 |
|:---|:---|:---|
| `build_match_condition()` | BM25 match 全文检索条件 | `(SQL 条件，参数)` |
| `build_match_phrase_condition()` | match_phrase 短语精确匹配 | `(SQL 条件，参数)` |
| `build_term_condition()` | term 标量精确匹配 | `(SQL 条件，参数列表)` |
| `build_terms_condition()` | terms 多值精确匹配（OR） | `(SQL 条件，参数列表)` |
| `process_bool_clause()` | bool 组合查询（递归处理嵌套） | `(Composable, params, PostFilterMark[])` |
| `process_query_item()` | 单个查询项处理 | `(Composable, params, PostFilterMark[])` |
| `process_filter_for_knn()` | kNN 过滤条件处理 | `(SQL 条件，参数)` |

#### PostFilterMark 后过滤标记

**模块信息**: `opensearch_sdk/client/post_filter_mark.py`

```python
class PostFilterMark:
    """标识需要 Python 层后过滤的场景"""
    
    filter_type: Literal["match_phrase_strict", "match_phrase_slop"]
    field: str  # 字段名
    value: str  # 查询值
    slop: int  # 允许的词间距（仅 slop>0 时）
    requires_post_filter: bool  # 是否必须后过滤
```

**使用场景**：
- `match_phrase` 严格匹配 → `requires_post_filter=True`
- `match_phrase` with slop > 0 → `requires_post_filter=True`
- `must_not` 中的 match_phrase → `requires_post_filter=False` (SQL NOT ILIKE)
- `should` 中的 match_phrase → 视情况而定

## 其他搜索方法

### search_by_category

按分类精确搜索：

```python
result = client.search_by_category("my_index", "technology")
```

### search_by_multiple_fields

多字段搜索：

```python
result = client.search_by_multiple_fields(
    index="my_index",
    field_value_pairs={"category": ["tech", "news"]},
    size=20
)
```

### delete_by_query

按条件删除：

```python
result = client.delete_by_query(
    index="my_index",
    body={"query": {"term": {"status": "deleted"}}}
)
```

## 外部接口说明

### SearchOpsMixin 主要接口

#### search() 方法
```python
def search(self, index: str, body: Dict[str, Any]) -> Any
```
- **功能**: 执行通用搜索查询，支持全文搜索、向量搜索和混合搜索
- **参数**:
  - `index`: 索引名称（已验证）
  - `body`: 搜索请求体，支持 OpenSearch 兼容格式
- **返回值**: 标准化搜索结果，包含 hits 总数和文档列表
- **支持查询类型**: match, match_phrase, term, terms, bool, knn

#### knn_search() 方法
```python
def knn_search(
    self,
    index: str,
    field: str,
    query_vector: List[float],
    k: int = 10,
    num_candidates: int = None,
    filter_query: Dict[str, Any] = None,
    similarity: str = 'cosine',
    ef_search: int = None
) -> Any
```
- **功能**: 执行 kNN 向量相似度搜索
- **支持的相似度算法**: cosine, l2_norm, dot_product
- **向量操作符**:
  - `<->`: L2 距离（欧氏距离）
  - `<=>`: 余弦相似度
  - `<#>`: 负内积（点积）

#### 其他搜索方法
- `search_by_category()`: 按分类精确搜索
- `search_by_multiple_fields()`: 多字段搜索
- `delete_by_query()`: 按条件删除文档

### QueryBuilder 静态接口

#### 查询条件构建方法

```python
# 基础查询构建（返回 SQL 条件和参数）
QueryBuilder.build_match_condition(field: str, value: Any) -> Tuple[sql.Composable, Any]
# 示例：build_match_condition("title", "Opensearch")
# 返回：(sql.SQL("to_tsvector('simple', title) @@ plainto_tsquery('simple', %s::text)"), "Opensearch")

QueryBuilder.build_match_phrase_condition(field: str, value: str, negate: bool = False) -> Tuple[sql.Composable, Any]
# 示例：build_match_phrase_condition("content", "hello world")
# 返回：(sql.SQL("content LIKE %s"), "%hello%world%")

QueryBuilder.build_term_condition(field: str, value: Any) -> Tuple[sql.Composable, List[Any]]
# 示例：build_term_condition("status", "active")
# 返回：(sql.SQL("(status = %s OR status LIKE %s OR status LIKE %s)"), ["active", "active,%", "%,active,%"])

QueryBuilder.build_terms_condition(field: str, values: List[Any]) -> Tuple[sql.Composable, List[Any]]
# 示例：build_terms_condition("category", ["tech", "news"])
# 返回：(sql.SQL("(category = %s OR category LIKE %s OR ... )"), ["tech", "tech,%", "%,tech,%", "news", ...])
```

#### 复合查询处理方法

```python
# 布尔查询处理（分离 must/should/must_not）
QueryBuilder.process_bool_clause(
    bool_clause: Dict[str, Any],
    is_top_level: bool = False
) -> Tuple[List[sql.Composable], List[Any]]
# 示例：process_bool_clause({
#     "must": [{"match": {"title": "test"}}],
#     "must_not": [{"term": {"status": "deleted"}}]
# })
# 返回：([must_conditions], [params])

# 单个查询项处理（支持嵌套逻辑）
QueryBuilder.process_query_item(
    query_item: Dict[str, Any],
    negate: bool = False
) -> Tuple[Optional[sql.Composable], Any]
# 示例：process_query_item({"term": {"status": "active"}})
# 返回：(sql.SQL("(status = %s OR ...)"), "active")

# kNN 过滤条件处理（用于向量搜索）
QueryBuilder.process_filter_for_knn(
    filter_query: Dict[str, Any]
) -> Tuple[Optional[str], List[Any]]
# 示例：process_filter_for_knn({"term": {"category": "tech"}})
# 返回：("category = %s", ["tech"])
```

## 内部接口说明

### 1. SearchOpsMixin 类 (opensearch_sdk/client/search_ops.py)

SearchOpsMixin 是搜索操作的核心 Mixin 类，提供全文搜索、向量搜索和混合搜索功能。

#### 1.1 search() - 通用搜索

**函数签名**：
```python
def search(
    self,
    index: str,
    body: Dict[str, Any]
) -> Any
```

**功能描述**: 
执行通用搜索查询，支持多种查询类型（match、match_phrase、term、terms、bool、knn）。

**内部流程**：
```
1. 参数验证
   └── 验证索引名称合法性

2. 查询类型检测和路由
   ├── 检测到 "knn" → 调用 _handle_knn_query()
   └── 检测到 "query" → 调用 _process_fulltext_search()

3. 全文搜索处理
   ├── 解析 query 中的查询条件
   ├── 构建 WHERE 条件列表
   ├── 收集参数
   └── 处理 match_phrase 条件

4. 布尔查询处理
   ├── 分离 must/should/must_not 条件
   ├── must/should → SQL 层处理
   └── must_not → SQL 层 NOT ILIKE 处理

5. 排序和分页处理
   ├── 解析 sort 字段
   └── 解析 from/size 分页参数

6. SQL构建和执行
   ├── 生成最终 SQL
   ├── 执行参数化查询
   └── 获取结果

7. 结果格式化
   ├── 解析 JSON 字段
   ├── 计算 _score
   └── 返回标准化响应

8. match_phrase 精确验证
   └── 对搜索结果进行 Python 层短语匹配验证
```

**参数说明**：
- `index`: 索引名称
- `body`: 搜索请求体字典

**支持的查询类型**：
- `match`: BM25 全文检索
- `match_phrase`: 短语精确匹配
- `term`: 标量精确匹配
- `terms`: 多值精确匹配（OR）
- `bool`: 组合查询（must/should/must_not）
- `knn`: 向量相似度搜索

**返回值**：
```python
{
    "hits": {
        "total": {
            "value": 100,
            "relation": "eq"
        },
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

**相关方法**：
- `_handle_knn_query()`: kNN查询路由
- `_process_fulltext_search()`: 全文搜索处理
- `_process_bool_query()`: 布尔查询处理
- `_build_must_not_condition()`: must_not 条件构建

---

#### 1.2 knn_search() - kNN向量搜索

**函数签名**：
```python
def knn_search(
    self,
    index: str,
    field: str,
    query_vector: List[float],
    k: int = 10,
    num_candidates: int = None,
    filter_query: Dict[str, Any] = None,
    similarity: str = 'cosine',
    ef_search: int = None
) -> Any
```

**功能描述**: 
执行 kNN向量相似度搜索。

**内部流程**：
```
1. 参数校验
   ├── 验证索引名、字段名
   ├── 验证 query_vector 非空
   ├── 验证 k 值范围（1-10000）
   └── 验证 similarity 参数

2. 选择向量操作符
   ├── cosine → <=> (余弦相似度)
   ├── l2_norm → <-> (L2 距离)
   └── dot_product → <#> (内积)

3. 构建向量查询 SQL
   ├── SELECT *, {field} {operator} %s::vector AS distance
   ├── FROM {index}
   ├── WHERE {filter_conditions}
   ├── ORDER BY {field} {operator} %s::vector ASC/DESC
   └── LIMIT {k}

4. 设置 HNSW 参数（如有）
   └── SET hnsw.ef_search = {ef_search}

5. 执行查询
   ├── 执行参数化 SQL
   └── 获取结果

6. 处理结果
   ├── 获取列名和数据行
   ├── 解析 JSON 字段
   ├── 计算 _score（基于真实距离）
   └── 返回标准化响应
```

**参数说明**：
- `index`: 索引名称
- `field`: 向量字段名
- `query_vector`: 查询向量（List[float]）
- `k`: 返回结果数量（默认 10）
- `num_candidates`: 候选集大小（可选）
- `filter_query`: 过滤条件（可选）
- `similarity`: 相似度算法（cosine/l2_norm/dot_product）
- `ef_search`: HNSW 搜索深度（可选）

**相似度算法**：
- `cosine`: 余弦相似度，`<=>` 操作符
- `l2_norm`: L2 距离，`<->` 操作符
- `dot_product`: 负内积，`<#>` 操作符

**_score 计算逻辑**：
```python
if similarity == 'cosine':
    score = 1.0 - distance  # cosine 距离转相似度 (0-1 范围)
elif similarity == 'l2_norm':
    score = 1.0 / (1.0 + distance)  # L2 距离转相似度
elif similarity == 'dot_product':
    score = 1.0 / (1.0 - distance) if distance < 1 else 1.0 / (1.0 + abs(distance))
else:
    score = 1.0 / (1.0 + distance)  # 默认 fallback
```

**返回值**：
与 `search()` 方法相同的格式

---

#### 1.3 _handle_knn_query() - kNN查询路由

**函数签名**：
```python
def _handle_knn_query(
    self,
    index: str,
    knn_config: Dict[str, Any]
) -> Any
```

**功能描述**: 
处理 OpenSearch 风格的 knn 查询，提取参数并调用 knn_search。

**处理逻辑**：
```python
def _handle_knn_query(self, index, knn_config):
    # 提取 knn 配置参数
    field = knn_config.get('field')
    query_vector = knn_config.get('query_vector')
    k = knn_config.get('k', 10)
    similarity = knn_config.get('similarity', 'cosine')
    filter_query = knn_config.get('filter')
    
    # 调用底层 knn_search
    return self.knn_search(
        index=index,
        field=field,
        query_vector=query_vector,
        k=k,
        similarity=similarity,
        filter_query=filter_query
    )
```

---


### 2. 查询构建器内部机制 (QueryBuilder)

#### 2.1 build_match_condition() - match 查询构建

**函数签名**：
```python
def build_match_condition(
    field: str,
    value: Any
) -> Tuple[sql.Composable, Any]
```

**功能描述**: 
构建 BM25 match 查询条件。

**处理逻辑**：
```
def build_match_condition(field: str, value: Any):
    validated_field = _validate_identifier(field)
    phrase = str(value)
    words = phrase.split()
    
    if len(words) == 1:
        # 单个词：标准全文检索
        condition = sql.SQL("to_tsvector('simple', {}) @@ to_tsquery('simple', %s::text)").format(
            sql.Identifier(validated_field)
        )
    else:
        # 多个词：plainto_tsquery 自动处理分词和 AND 连接
        condition = sql.SQL("to_tsvector('simple', {}) @@ plainto_tsquery('simple', %s::text)").format(
            sql.Identifier(validated_field)
        )
    
    return condition, phrase
```

**生成的 SQL**：
```
-- 单个词
to_tsvector('simple', title) @@ to_tsquery('simple', 'Opensearch'::text)

-- 多个词
to_tsvector('simple', content) @@ plainto_tsquery('simple', '数据库 基础'::text)
```

---

#### 2.2 build_term_condition() - term 精确匹配构建

**函数签名**：
```python
def build_term_condition(
    field: str,
    value: Any
) -> Tuple[sql.Composable, List[Any]]
```

**功能描述**: 
构建 term 精确匹配条件，支持逗号分隔字符串的精确匹配。

**处理逻辑**：
```
def build_term_condition(field: str, value: Any):
    validated_field = _validate_identifier(field)
    # 支持逗号分隔字符串的精确匹配
    condition = sql.SQL("({} = %s OR {} LIKE %s OR {} LIKE %s)").format(
        sql.Identifier(validated_field),
        sql.Identifier(validated_field),
        sql.Identifier(validated_field)
    )
    params = [value, f'{value},%', f'%,{value}%']
    return condition, params
```

**生成的 SQL**：
```
(category = %s OR category LIKE %s OR category LIKE %s)
-- params: ['tech', 'tech,%', '%,tech,%']
```

---


#### 2.3 _build_must_not_condition() - must_not 条件构建

**函数签名**：
```python
def _build_must_not_condition(
    self,
    clause: Dict[str, Any]
) -> Tuple[Optional[sql.Composable], Any]
```

**功能描述**: 
为 must_not 子句生成 NOT ILIKE SQL 条件。

**设计理念**：
1. 减少数据传输：数据库层过滤，避免传输不需要的记录
2. 降低内存占用：不需要在 Python 层加载被排除的记录
3. 提升性能：特别是大数据量场景的性能优势明显

**处理逻辑**：
```
def _build_must_not_condition(self, clause):
    if "match_phrase" in clause:
        # 短语匹配：NOT ILIKE '%phrase%'
        field, value = next(iter(clause["match_phrase"].items()))
        validated_field = _validate_identifier(field)
        condition = sql.SQL("{} NOT ILIKE %s").format(sql.Identifier(validated_field))
        return condition, f'%{value}%'
    
    elif "match" in clause:
        # 关键词匹配：NOT ILIKE '%keyword%'
        field, value = next(iter(clause["match"].items()))
        validated_field = _validate_identifier(field)
        condition = sql.SQL("{} NOT ILIKE %s").format(sql.Identifier(validated_field))
        return condition, f'%{value}%'
    
    elif "term" in clause:
        # 精确匹配：NOT ILIKE '%value%'（兼容数组字段）
        field, value = next(iter(clause["term"].items()))
        validated_field = _validate_identifier(field)
        condition = sql.SQL("{} NOT ILIKE %s").format(sql.Identifier(validated_field))
        return condition, f'%{value}%'
    
    elif "terms" in clause:
        # 多值匹配：NOT IN (value1, value2, ...)
        field, values = next(iter(clause["terms"].items()))
        validated_field = _validate_identifier(field)
        placeholders = sql.SQL(", ").join([sql.Placeholder()] * len(values))
        condition = sql.SQL("{} NOT IN ({})").format(sql.Identifier(validated_field), placeholders)
        return condition, values
```

**生成的 SQL**：
```
-- match_phrase
content NOT ILIKE '%hello world%'

-- term  
status NOT ILIKE '%deleted%'

-- terms
category NOT IN ('tech', 'news')
```

---

#### 2.4 process_bool_clause() - 布尔查询处理

**函数签名**：
```python
def process_bool_clause(
    bool_clause: Dict[str, Any],
    is_top_level: bool = False
) -> Tuple[List[sql.Composable], List[Any]]
```

**功能描述**: 
处理布尔查询的 must/should/must_not子句。

**处理逻辑**：
```
def process_bool_clause(bool_clause, is_top_level=False):
    must_conditions = []    # AND 逻辑
    should_conditions = []  # OR 逻辑
    must_not_conditions = [] # AND NOT 逻辑
    
    # 处理 must 子句（AND 连接）
    for clause in bool_clause.get("must", []):
        cond, param = QueryBuilder.process_query_item(clause, negate=False)
        must_conditions.append((cond, param))
    
    # 处理 should 子句（OR 连接）
    for clause in bool_clause.get("should", []):
        cond, param = QueryBuilder.process_query_item(clause, negate=False)
        should_conditions.append((cond, param))
    
    # 处理 must_not 子句（SQL 层 NOT ILIKE）
    for clause in bool_clause.get("must_not", []):
        cond, param = self._build_must_not_condition(clause)
        must_not_conditions.append((cond, param))
    
    # 组合所有条件
    return combine_conditions(must_conditions, should_conditions, must_not_conditions)
```

---

### 3. 辅助方法

#### 3.1 _verify_match_phrase() - match_phrase 精确验证

**函数签名**：
```python
def _verify_match_phrase(
    self,
    doc_value: Any,
    phrase: str
) -> bool
```

**功能描述**: 
验证文档内容是否包含指定短语。

**为什么需要双重验证？**
1. SQL层：`to_tsvector @@ plainto_tsquery` 提供全文检索性能
2. Python 层：确保短语连续性的语义准确性

**处理逻辑**：
```
def _verify_match_phrase(self, doc_value: Any, phrase: str):
    if isinstance(doc_value, list):
        # 数组字段：检查是否有任何元素包含该短语作为子串
        return any(phrase.lower() in str(item).lower() for item in doc_value)
    else:
        # 标量字段：直接检查
        return phrase.lower() in str(doc_value).lower()
```

---

#### 3.2 _verify_match_phrase_results() - 搜索结果验证

**函数签名**：
```python
def _verify_match_phrase_results(
    self,
    hits: List[Dict],
    conditions: List[Tuple[str, str]]
) -> List[Dict]
```

**功能描述**: 
对搜索结果进行 match_phrase 精确验证。

**处理逻辑**：
```
def _verify_match_phrase_results(self, hits, conditions):
    filtered_hits = []
    for hit in hits:
        is_match = all(
            self._verify_match_phrase(hit["_source"].get(field, ''), phrase)
            for field, phrase in conditions
        )
        if is_match:
            filtered_hits.append(hit)
    return filtered_hits
```

## 数据结构与请求体详解

### 搜索请求体（Search Body）

#### 1. 基础查询结构

```python
search_body = {
    "query": {
        # match：BM25 全文检索
        "match": {"field": "value"},
        
        # match_phrase：短语精确匹配
        "match_phrase": {"field": "phrase"},
        
        # term：标量精确匹配
        "term": {"field": "exact_value"},
        
        # terms：多值精确匹配（OR 连接）
        "terms": {"field": ["value1", "value2"]},
        
        # bool：组合查询
        "bool": {
            "must": [...],      # AND 逻辑，所有条件必须满足
            "should": [...],    # OR 逻辑，至少一个满足
            "must_not": [...]   # AND NOT 逻辑，所有条件都不能满足
        }
    },
    
    # 排序配置
    "sort": [
        "field1",                           # 简单字段升序
        {"field2": {"order": "desc"}}      # 指定降序
    ],
    
    # 分页配置
    "size": 10,     # 每页数量（默认 10，最大 10000）
    "from": 0       # 偏移量（默认 0）
}
```

**使用说明**：
- `query`：查询条件，支持多种查询类型
- `sort`：可选，支持多字段排序
- `size`：可选，返回结果数量限制
- `from`：可选，分页偏移量

---

#### 2. kNN向量查询结构

```python
knn_body = {
    "knn": {
        # 必填参数
        "field": "vector_field",                # 向量字段名
        "query_vector": [0.1, 0.2, ...],        # 查询向量（List[float]）
        "k": 10,                                # 返回最相似的 k 个结果
        
        # 可选参数
        "num_candidates": 100,                  # 候选集大小（默认=k）
        "filter": {                             # 过滤条件
            "term": {"category": "tech"}
        },
        "similarity": "cosine"                  # 相似度算法：cosine/l2_norm/dot_product
    }
}
```

**参数说明**：
- `field`: 向量字段名称（必须是 dense_vector 或 float_vector 类型）
- `query_vector`: 查询向量，维度必须与索引中定义的维度一致
- `k`: 返回结果数量（范围：1-10000）
- `num_candidates`: 候选集大小，增大可提高准确率但降低性能
- `filter`: 过滤条件，支持 term/terms/bool 等查询类型
- `similarity`: 相似度算法
  - `cosine`：余弦相似度（推荐用于文本、语义搜索）
  - `l2_norm`：L2 距离（欧氏距离，推荐用于图像、物理距离）
  - `dot_product`：负内积（推荐用于推荐系统）

---

#### 3. 混合查询结构（全文 + 向量）

```python
hybrid_body = {
    # 全文搜索部分
    "query": {
        "bool": {
            "must": [{"match": {"title": "keyword"}}],
            "filter": [{"term": {"status": "active"}}]
        }
    },
    
    # 向量搜索部分
    "knn": {
        "field": "embedding",
        "query_vector": [0.1, 0.2, ...],
        "k": 5,
        "num_candidates": 50
    }
}
```

**执行逻辑**：
1. 分别执行全文搜索和向量搜索
2. 合并两个结果集
3. 根据 `_score` 重新排序
4. 应用 `size` 限制返回最终结果

**适用场景**：
- 语义搜索 + 关键词匹配
- 推荐系统 + 内容过滤
- 多模态检索

---

### 搜索响应结构（Search Response）

```python
search_response = {
    "hits": {
        # 总数统计
        "total": {
            "value": 100,           # 匹配的文档总数
            "relation": "eq"        # 计数类型：eq=精确计数，gte=至少
        },
        
        # 命中结果
        "hits": [
            {
                "_index": "my_index",       # 索引名称
                "_id": "doc_id",            # 文档 ID
                "_score": 1.0,              # 相关性得分（统一分数）
                "_source": {                # 文档内容
                    "title": "Document Title",
                    "content": "Document content..."
                }
            }
        ]
    }
}
```

**字段说明**：
- `hits.total.value`: 匹配的文档总数
- `hits.total.relation`: 计数类型
  - `eq`: 精确计数（默认）
  - `gte`: 至少这么多（当启用 `track_total_hits: false` 时）
- `hits.hits[]`: 命中的文档列表，按 `_score` 降序排列
- `_score`: 相关性得分，越高越相关

---

### 内部处理数据结构

#### 1. 查询条件元组

```python
# SQL 条件 + 参数的元组
query_condition = Tuple[sql.Composable, Any]
# 示例：(sql.SQL("title LIKE %s"), "%keyword%")
```

#### 2. 布尔查询分解

```python
bool_query_components = {
    "must_conditions": List[Tuple[sql.Composable, Any]],      # AND 条件列表
    "should_conditions": List[Tuple[sql.Composable, Any]],    # OR 条件列表
    "must_not_conditions": List[Tuple[sql.Composable, Any]]   # NOT 条件列表
}
```

#### 3. match_phrase 验证列表

```python
match_phrase_conditions = List[Tuple[str, str]]
# 示例：[("content", "hello world"), ("title", "important")]
# 用于 Python 层二次验证短语连续性
```

## 主要实现逻辑说明

### 1. 搜索处理主流程

**完整处理步骤**：

1. **输入验证**：首先验证索引名称的合法性，防止 SQL 注入攻击

2. **查询类型路由**：检测请求体中的查询类型
   - 如果包含 `knn` 字段，调用 kNN 查询处理方法
   - 如果包含 `query` 字段，调用全文搜索处理方法

3. **全文搜索处理**：
   - 提取 query 中的查询条件
   - 初始化 WHERE 条件列表、参数列表和 match_phrase 验证列表

4. **布尔查询处理**：
   - 如果查询是 bool 类型，调用布尔查询处理方法分离 must/should/must_not 条件
   - 如果是简单查询，直接处理单个查询条件

5. **排序和分页处理**：解析 sort 和分页参数（from/size）

6. **SQL 构建和执行**：
   - 根据条件生成最终 SQL 语句
   - 执行参数化查询
   - 获取查询结果

7. **结果格式化**：
   - 解析 JSON 字段
   - 计算 _score 相关性得分
   - 转换为标准化响应格式

8. **match_phrase 精确验证**：
   - 如果存在 match_phrase 条件，对搜索结果进行 Python 层二次验证
   - 确保短语连续性要求

9. **返回标准化响应**：构建包含 hits 总数和文档列表的响应对象

10. **异常处理**：捕获所有异常并抛出统一的错误信息格式

---

### 2. must_not 条件 SQL 层处理逻辑

**设计理念**：
- 减少数据传输：在数据库层过滤不需要的记录
- 降低内存占用：避免加载被排除的记录到 Python 层
- 提升性能：特别是大数据量场景的性能优势明显

**处理策略**：

1. **match_phrase 条件**：
   - 提取字段名和短语值
   - 验证字段名合法性
   - 生成 NOT ILIKE '%phrase%' SQL 条件
   - 返回条件和参数

2. **match 条件**：
   - 提取字段名和关键词值
   - 验证字段名合法性
   - 生成 NOT ILIKE '%keyword%' SQL 条件
   - 返回条件和参数

3. **term 条件**：
   - 提取字段名和精确值
   - 验证字段名合法性
   - 生成 NOT ILIKE '%value%' SQL 条件（兼容数组字段）
   - 返回条件和参数

4. **terms 条件**：
   - 提取字段名和多值列表
   - 验证字段名合法性
   - 生成 NOT IN (value1, value2, ...) SQL 条件
   - 使用占位符防 SQL 注入
   - 返回条件和参数列表

---

### 3. match_phrase 精确验证逻辑

**为什么需要双重验证？**

1. **SQL 层**：使用 `to_tsvector @@ plainto_tsquery` 提供全文检索性能，但无法保证短语连续性
2. **Python 层**：确保短语连续性的语义准确性

**验证流程**：

1. **单个文档验证**：
   - 检查文档值类型
   - 如果是数组：遍历所有元素，检查是否有任何元素包含该短语作为子串
   - 如果是标量：直接检查是否包含该短语
   - 返回验证结果（True/False）

2. **搜索结果批量验证**：
   - 遍历所有命中的文档
   - 对每个文档应用所有 match_phrase 条件
   - 只有满足所有条件的文档才会被保留
   - 返回过滤后的结果列表

---

### 4. kNN 查询处理逻辑

**完整处理流程**：

1. **参数验证**：
   - 验证索引名称和字段名的合法性
   - 检查查询向量是否为非空列表
   - 验证 k 值范围（1-10000）
   - 验证相似度算法参数

2. **相似度算法映射**：
   - cosine → `<=>` （余弦相似度）
   - l2_norm → `<->` （L2 距离）
   - dot_product → `<#>` （负内积）
   - 默认使用余弦相似度

3. **构建向量查询 SQL**：
   - 将查询向量列表转换为字符串格式
   - 构建基础 SELECT 语句
   - 添加向量距离计算条件
   - 根据相似度算法选择 ASC 或 DESC 排序
     - 点积：值越大越相似，使用 DESC
     - 距离：值越小越相似，使用 ASC

4. **添加过滤条件**：
   - 如果提供了 filter_query，调用 kNN 过滤器处理
   - 将过滤条件与向量距离条件用 AND 连接
   - 合并参数列表

5. **设置 HNSW 参数**（可选）：
   - 如果指定了 ef_search，设置 HNSW 搜索深度
   - 提高搜索准确率但可能降低性能

6. **执行查询**：
   - 执行参数化 SQL 语句
   - 获取所有结果行

7. **格式化结果**：
   - 获取列名和数据行
   - 解析 JSON 字段
   - 计算 _score（基于真实距离转换）
   - 返回标准化响应格式

## 主要代码文件

### 1. [`opensearch_sdk/client/search_ops.py`](opensearch_sdk/client/search_ops.py:1)
**代码说明**: 搜索操作核心模块，实现全文搜索、向量搜索和混合搜索功能
- **主要类**: [`SearchOpsMixin`](opensearch_sdk/client/search_ops.py:47)
- **核心方法**:
  - [`search()`](opensearch_sdk/client/search_ops.py:212): 通用搜索入口，支持多种查询类型
  - [`knn_search()`](opensearch_sdk/client/search_ops.py:462): kNN 向量相似度搜索
  - [`_build_must_not_condition()`](opensearch_sdk/client/search_ops.py:67): must_not 条件 SQL 层处理
  - [`_verify_match_phrase()`](opensearch_sdk/client/search_ops.py:52): match_phrase 精确验证
- **设计特点**:
  - DDL 重连机制说明和自动处理
  - must_not 条件 SQL 层优化处理
  - match_phrase 双重验证机制
  - OpenSearch 兼容的查询语法支持

### 2. [`opensearch_sdk/client/query_builder.py`](opensearch_sdk/client/query_builder.py:1)
**代码说明**: 查询构建器，负责将 OpenSearch 风格查询转换为 Opensearch SQL
- **主要类**: [`QueryBuilder`](opensearch_sdk/client/query_builder.py:15)
- **核心方法**:
  - [`build_match_condition()`](opensearch_sdk/client/query_builder.py:22): BM25 match 条件构建
  - [`build_match_phrase_condition()`](opensearch_sdk/client/query_builder.py:52): match_phrase 条件构建
  - [`build_term_condition()`](opensearch_sdk/client/query_builder.py:90): term 精确匹配构建
  - [`process_bool_clause()`](opensearch_sdk/client/query_builder.py:126): 布尔查询处理
  - [`process_filter_for_knn()`](opensearch_sdk/client/query_builder.py:223): kNN 过滤条件处理
- **设计特点**:
  - 静态方法设计，无状态查询构建
  - 完整的 OpenSearch 查询语法支持
  - 参数化 SQL 防注入机制
  - 支持复合查询和嵌套逻辑

### 3. [`opensearch_sdk/client/constants.py`](opensearch_sdk/client/constants.py:1)
**代码说明**: 查询相关常量定义
- **主要常量**:
  - `MAX_QUERY_LIMIT`: 查询结果最大数量限制
  - `MIN_QUERY_LIMIT`: 查询结果最小数量限制
  - `MAX_KNN_TOP_K`: kNN 搜索最大返回数量
  - `MIN_KNN_TOP_K`: kNN 搜索最小返回数量

### 4. [`opensearch_sdk/client/utils.py`](opensearch_sdk/client/utils.py:1)
**代码说明**: 查询工具函数
- **主要函数**:
  - [`_validate_identifier()`](opensearch_sdk/client/utils.py:1): 标识符验证，防止 SQL 注入
  - [`_validate_identifiers()`](opensearch_sdk/client/utils.py:1): 批量标识符验证

### 5. [`opensearch_sdk/client/base.py`](opensearch_sdk/client/base.py:1)
**代码说明**: 客户端基类，通过 Mixin 模式集成搜索功能
- **集成方式**: [`SearchOpsMixin`](opensearch_sdk/client/search_ops.py:47) 通过 Mixin 模式集成到 [`OpenGaussClient`](opensearch_sdk/client/base.py:1)
- **功能暴露**: 所有搜索方法通过客户端实例直接调用

### 6. [`opensearch_sdk/connection/opengauss.py`](opensearch_sdk/connection/opengauss.py:1)
**代码说明**: 数据库连接层，负责 SQL 执行和结果处理
- **核心功能**:
  - 参数化查询执行
  - 结果集获取和类型转换
  - 事务管理和连接池
  - DDL 操作后的重连处理

## 相关章节

- [客户端连接](./02_Client_Connection.md)
- [索引管理](./03_Index_Management.md)
- [文档操作](./04_Document_CRUD.md)
- [向量搜索](./06_Vector_Search.md)
