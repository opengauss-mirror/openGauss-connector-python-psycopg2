# Opensearch兼容接口- OpenSearch 索引转换规则

本文档详细说明了 Opensearch兼容接口如何将 OpenSearch 的索引定义转换为 Opensearch（基于 openGauss）的表结构和索引。

---

## 1. 核心设计理念

Opensearch兼容接口通过以下方式实现 OpenSearch 兼容：

1. **索引 → 表**：OpenSearch 的 Index 映射为 Opensearch 的 Table
2. **Mapping → Schema**：字段定义转换为数据库列定义
3. **自动索引创建**：根据字段类型自动创建相应的数据库索引（BM25、B-tree、HNSW 等）
4. **配置持久化**：将完整的 mapping 信息存储到 `pg_description` 中，便于后续查询和动态推断

---

## 2. 字段类型转换规则

### 2.1 基础类型映射

| OpenSearch 类型 | Opensearch 类型 | SQL 类型 | 说明 |
|----------------|---------------|----------|------|
| `text` | TEXT | TEXT | 全文检索文本，自动创建 BM25 索引 |
| `keyword` | TEXT | TEXT | 精确匹配字符串，自动创建 B-tree 索引 |
| `long` | BIGINT | BIGINT | 64位整数，自动创建 B-tree 索引 |
| `integer` | INTEGER | INTEGER | 32位整数，自动创建 B-tree 索引 |
| `short` | SHORTINT | SMALLINT | 16位整数，自动创建 B-tree 索引 |
| `byte` | TINYINT | TINYINT | 8位整数，自动创建 B-tree 索引 |
| `float` | FLOAT4 | REAL | 32位浮点数，自动创建 B-tree 索引 |
| `double` | FLOAT8 | DOUBLE PRECISION | 64位浮点数，自动创建 B-tree 索引 |
| `boolean` | BOOLEAN | BOOLEAN | 布尔值，自动创建 B-tree 索引 |
| `date` | TIMESTAMP | TIMESTAMP | 日期时间，自动创建 B-tree 索引 |

**代码位置**：[`opensearch_sdk/client/indices/sql_generator.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/sql_generator.py#L72-L109)

### 2.2 向量类型映射

| OpenSearch 类型 | Opensearch 类型 | SQL 类型 | 说明 |
|----------------|---------------|----------|------|
| `knn_vector` | VECTOR(n) | VECTOR(dimension) | KNN 向量，自动创建 HNSW/IVF 索引 |
| `dense_vector` | VECTOR(n) | VECTOR(dims) | 密集向量，自动创建 HNSW 索引 |
| `float_vector` | VECTOR(n) | VECTOR(dims) | 浮点向量，自动创建 HNSW 索引 |

**维度要求**：
- 最小维度：`MIN_VECTOR_DIMENSION`（通常为 1）
- 最大维度：`MAX_VECTOR_DIMENSION`（通常为 10000）
- 默认维度：128（如果未指定）

**智能数组识别**：
- 字段名以 `list` 或 `List` 结尾时，强制使用 `TEXT` 类型而非向量类型
- 示例：`tagsList` → TEXT, `embedding_list` → TEXT

---

## 3. 相似度算法转换规则

### 3.1 OpenSearch space_type → Opensearch similarity

OpenSearch 使用 `space_type` 参数，Opensearch 转换为内部 `similarity` 参数：

| OpenSearch space_type | Opensearch similarity | 向量操作符 | 数学含义 |
|----------------------|---------------------|-----------|---------|
| `l2` | `l2_norm` | `<->` | L2 距离（欧氏距离） |
| `cosinesimil` | `cosine` | `<=>` | 余弦相似度 |
| `innerproduct` | `dot_product` | `<#>` | 内积（点积） |

**转换逻辑**：
```python
space_to_similarity = {
    'l2': 'l2_norm',
    'cosinesimil': 'cosine',
    'innerproduct': 'dot_product'
}
```

**代码位置**：[`opensearch_sdk/client/indices/helpers.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/helpers.py#L147-L154)

### 3.2 Elasticsearch similarity → Opensearch similarity

Elasticsearch 直接使用 `similarity` 参数，SDK 直接支持：

| Elasticsearch similarity | Opensearch similarity | 说明 |
|-------------------------|---------------------|------|
| `cosine` | `cosine` | 余弦相似度 |
| `l2_norm` | `l2_norm` | L2 归一化距离 |
| `dot_product` | `dot_product` | 点积相似度 |
| `l1` | `l1` | L1 距离（曼哈顿距离） |
| `linf` | `linf` | L∞ 距离（切比雪夫距离） |

**优先级规则**：
- 如果同时设置 `space_type` 和 `similarity`，**`space_type` 优先**
- 如果都未设置，默认使用 `cosine`

**代码位置**：[`opensearch_sdk/client/indices/helpers.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/helpers.py#L142-L165)

---

## 4. 向量索引创建规则

### 4.1 索引算法选择

SDK 根据 `method.name` 参数选择索引算法：

| method.name | Opensearch 索引类型 | 适用场景 |
|-------------|------------------|---------|
| `hnsw` (或未指定) | HNSW | 高精度、内存充足 |
| `ivf` | IVFFlat | 大数据量、可接受精度损失 |

**默认行为**：
- 未指定 `method` 时，默认使用 **HNSW** 算法

### 4.2 HNSW 索引参数

**OpenSearch 格式**：
```json
{
  "type": "knn_vector",
  "dimension": 768,
  "method": {
    "name": "hnsw",
    "parameters": {
      "m": 16,
      "ef_construction": 100
    }
  }
}
```

**Opensearch SQL**：
```sql
CREATE INDEX idx_table_field_hnsw 
ON table USING hnsw(field vector_cosine_ops) 
WITH (m=16, ef_construction=64);
```

**默认参数**：
- `m`: 16（每个节点的连接数）
- `ef_construction`: 100（构建时的搜索深度，与 OpenSearch 2.12+ 保持一致）

**代码位置**：[`opensearch_sdk/client/indices/sql_generator.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/sql_generator.py#L252-L275)

### 4.3 IVF 索引参数

**OpenSearch 格式**：
```json
{
  "type": "knn_vector",
  "dimension": 768,
  "method": {
    "name": "ivf",
    "parameters": {
      "nlist": 100,
      "nprobes": 50
    }
  }
}
```

**Opensearch SQL**：
```sql
CREATE INDEX idx_table_field_ivf 
ON table USING ivfflat(field vector_cosine_ops) 
WITH (lists=100);
```

**默认参数**：
- `nlist`: 100（聚类中心数量）
- `nprobes`: 10（查询时探测的聚类数量）

**代码位置**：[`opensearch_sdk/client/indices/sql_generator.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/sql_generator.py#L202-L249)



---

## 6. 非向量字段索引规则

### 6.1 文本字段（text/keyword）

**OpenSearch 配置**：
```json
{
  "title": {
    "type": "text",
    "index": true
  }
}
```

**Opensearch SQL**：
```sql
-- 创建表
CREATE TABLE my_index (
  id VARCHAR PRIMARY KEY,
  title TEXT
);

-- 自动创建 BM25 索引
CREATE INDEX idx_my_index_title_bm25 
ON my_index USING bm25(title);
```

**索引命名规则**：`idx_{table_name}_{field_name}_bm25`

### 6.2 数值/日期/布尔字段

**OpenSearch 配置**：
```json
{
  "price": {"type": "float"},
  "publish_date": {"type": "date"},
  "is_active": {"type": "boolean"}
}
```

**Opensearch SQL**：
```sql
CREATE TABLE my_index (
  id VARCHAR PRIMARY KEY,
  price FLOAT4,
  publish_date TIMESTAMP,
  is_active BOOLEAN
);

-- 自动创建 B-tree 索引
CREATE INDEX idx_my_index_price_float ON my_index USING btree(price);
CREATE INDEX idx_my_index_publish_date_datetime ON my_index USING btree(publish_date);
CREATE INDEX idx_my_index_is_active_bool ON my_index USING btree(is_active);
```

**索引后缀规则**：
- `long/integer` → `_numeric`
- `float/double` → `_float`
- `date` → `_datetime`
- `boolean` → `_bool`

**代码位置**：[`opensearch_sdk/client/indices/sql_generator.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/sql_generator.py#L130-L175)

### 6.3 index: false 控制

如果字段设置 `"index": false`，则**不创建任何索引**，仅存储数据：

```json
{
  "content": {
    "type": "text",
    "index": false
  }
}
```

**效果**：只创建列，不创建索引，节省存储空间。

---

## 7. Nested 结构处理规则

### 7.1 扁平化策略（首值策略）

OpenSearch 的 nested 字段会被**扁平化**为多个列：

**OpenSearch 配置**：
```json
{
  "author": {
    "type": "nested",
    "properties": {
      "name": {"type": "keyword"},
      "age": {"type": "integer"}
    }
  }
}
```

**Opensearch 转换**：
```sql
CREATE TABLE my_index (
  id VARCHAR PRIMARY KEY,
  author__name TEXT,   -- 嵌套字段扁平化为 author__name（双下划线）
  author__age INTEGER  -- 嵌套字段扁平化为 author__age（双下划线）
);

-- 为扁平后的字段创建索引
CREATE INDEX idx_my_index_author__name_bm25 ON my_index USING bm25(author__name);
CREATE INDEX idx_my_index_author__age_numeric ON my_index USING btree(author__age);
```

**命名规则**：`{parent_field}__{child_field}`（使用双下划线 `__` 连接）

**限制**：
- 不支持嵌套的 nested（nested 内不能再包含 nested）
- 支持一层嵌套

**代码位置**：[`opensearch_sdk/client/indices/helpers.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/helpers.py#L281-L296)

---

## 8. Dynamic Templates 处理规则

### 8.1 保存与复用

Opensearch兼容接口**不支持真正的动态模板**，但会保存配置用于后续插入时的类型推断：

**OpenSearch 配置**：
```json
{
  "mappings": {
    "dynamic_templates": [
      {
        "vector_template": {
          "match": "*_vec",
          "mapping": {
            "type": "knn_vector",
            "dimension": 1024
          }
        }
      }
    ],
    "properties": {
      "title": {"type": "text"}
    }
  }
}
```

**SDK 行为**：
1. 创建表时**忽略** dynamic_templates（不会创建动态列）
2. 将完整 mapping（包括 dynamic_templates）保存到 `pg_description`
3. 插入文档时，如果字段不存在，会根据模板**自动推断类型并添加列**

**通配符转换**：
- `*_vec` → 正则表达式 `.*_vec`
- 匹配字段名如：`title_vec`, `content_vec`, `embedding_vec`

**代码位置**：
- 保存：[`opensearch_sdk/client/indices/sql_generator.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/sql_generator.py#L292-L319)
- 应用：[`opensearch_sdk/client/doc_utils/type_inference.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/doc_utils/type_inference.py)

---

## 9. Settings 配置处理

### 9.1 支持的 Settings

| OpenSearch Setting | Opensearch 处理 | 说明 |
|-------------------|--------------|------|
| `index.knn` | 解析但不使用 | Opensearch 自动管理向量索引 |
| `number_of_shards` | 忽略 | Opensearch 单节点，固定为 1 |
| `number_of_replicas` | 忽略 | Opensearch 不支持副本 |
| `similarity.BM25` | 转换为 SET 命令 | 设置全局 BM25 参数 |

### 9.2 BM25 参数配置

**OpenSearch 格式**：
```json
{
  "settings": {
    "similarity": {
      "my_bm25": {
        "type": "BM25",
        "k1": 1.5,
        "b": 0.8
      }
    }
  }
}
```

**Opensearch 转换**：
```sql
-- 执行 SET 命令应用到当前会话
SET bm25_k1 = 1.5;
SET bm25_b = 0.8;

-- 同时保存到表注释（用于记录）
COMMENT ON TABLE my_index IS '{"bm25_config": {...}}';
```

**默认值**：
- `k1`: 1.2
- `b`: 0.75

**代码位置**：[`opensearch_sdk/client/indices/sql_generator.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/sql_generator.py#L112-L127)

---

## 10. 标识符规范化规则

### 10.1 索引名（表名）规范

**禁止字符**：
- 点号 `.`（OpenSearch 也不允许）
- 支持下划线 `_` 和连字符 `-`

**转换规则**：
- `my.index` → 抛出错误（提示使用下划线）
- `my-index` → `my_index`

**代码位置**：[`opensearch_sdk/client/utils.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/utils.py#L193-L222)

### 10.2 字段名规范

**特殊处理**：
- `.keyword` 后缀会被移除（兼容 OpenSearch 的子字段）
  - `libId.keyword` → `libId`
- 点号和连字符转换为下划线
  - `user-name` → `user_name`
  - `meta.data` → `meta_data`

---

## 11. Mapping 持久化机制

### 11.1 存储位置

完整的 mapping 信息存储在 PostgreSQL 系统表 `pg_description` 中：

```sql
-- 查询 mapping
SELECT description 
FROM pg_description 
WHERE objoid = 'my_index'::regclass;
```

### 11.2 存储内容

```json
{
  "properties": {
    "title": {
      "type": "text"
    },
    "embedding": {
      "type": "knn_vector",
      "dims": 768,
      "similarity": "cosine",
      "index_options": {
        "m": 16,
        "ef_construction": 64
      }
    }
  },
  "dynamic_templates": [...]
}
```

**用途**：
1. `get_mapping()` API 返回完整的 OpenSearch 风格 mapping
2. 插入文档时用于类型推断
3. 支持动态字段扩展

**代码位置**：
- 保存：[`opensearch_sdk/client/indices/sql_generator.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/sql_generator.py#L292-L319)
- 读取：[`opensearch_sdk/client/indices/operations.py`](file://d:/移动/向量/es2pw/opensearch_sdk/client/indices/operations.py#L130-L158)

---

## 13. 完整转换示例

### 13.1 OpenSearch 输入

```json
{
  "settings": {
    "index": {
      "knn": true
    },
    "similarity": {
      "custom_bm25": {
        "type": "BM25",
        "k1": 1.5,
        "b": 0.8
      }
    }
  },
  "mappings": {
    "dynamic_templates": [
      {
        "vector_fields": {
          "match": "*_vector",
          "mapping": {
            "type": "knn_vector",
            "dimension": 768
          }
        }
      }
    ],
    "properties": {
      "title": {
        "type": "text",
        "index": true
      },
      "category": {
        "type": "keyword",
        "index": true
      },
      "price": {
        "type": "float",
        "index": true
      },
      "description": {
        "type": "text",
        "index": false
      },
      "embedding": {
        "type": "knn_vector",
        "dimension": 768,
        "space_type": "cosinesimil",
        "method": {
          "name": "hnsw",
          "parameters": {
            "m": 16,
            "ef_construction": 100
          }
        }
      },
      "author": {
        "type": "nested",
        "properties": {
          "name": {"type": "keyword"},
          "age": {"type": "integer"}
        }
      }
    }
  }
}
```

### 13.2 Opensearch 输出

**SQL 执行序列**：

```sql
-- 1. 创建表
CREATE TABLE my_index (
  id VARCHAR PRIMARY KEY,
  title TEXT,
  category TEXT,
  price FLOAT4,
  description TEXT,
  embedding VECTOR(768),
  author__name TEXT,      -- nested 字段使用双下划线
  author__age INTEGER     -- nested 字段使用双下划线
);

-- 2. 创建 BM25 索引（text 字段）
CREATE INDEX idx_my_index_title_bm25 ON my_index USING bm25(title);

-- 3. 创建 B-tree 索引（keyword/数值字段）
CREATE INDEX idx_my_index_category_bm25 ON my_index USING bm25(category);
CREATE INDEX idx_my_index_price_float ON my_index USING btree(price);
CREATE INDEX idx_my_index_author__name_bm25 ON my_index USING bm25(author__name);
CREATE INDEX idx_my_index_author__age_numeric ON my_index USING btree(author__age);

-- 4. 创建 HNSW 向量索引
CREATE INDEX idx_my_index_embedding_hnsw 
ON my_index USING hnsw(embedding vector_cosine_ops) 
WITH (m=16, ef_construction=100);

-- 5. 设置 BM25 参数
SET bm25_k1 = 1.5;
SET bm25_b = 0.8;

-- 6. 保存 mapping 到 pg_description
COMMENT ON TABLE my_index IS '{"properties": {...}, "dynamic_templates": [...]}';
```

**注意**：
- `description` 字段设置了 `index: false`，所以**没有创建索引**
- `author` nested 字段被扁平化为 `author__name` 和 `author__age`（使用双下划线 `__`）
- `dynamic_templates` 被保存但未立即应用

---

## 14. 常见问题

### Q1: 为什么不支持 analyzer 配置？

**A**: Opensearch 使用内置的分词器，不支持自定义 analyzer。配置会被忽略并给出警告。

### Q2: 向量维度超出范围怎么办？

**A**: SDK 会进行验证：
- 维度 < MIN_VECTOR_DIMENSION 或 > MAX_VECTOR_DIMENSION 时抛出错误
- 未指定维度时使用默认值 128

### Q3: 如何查看已创建的索引？

**A**: 使用以下 API：
```python
# 获取所有索引
client.indices.get_all_index_names()

# 获取特定索引的 mapping
client.indices.get_mapping(index="my_index")
```

### Q4: 如何修改已有索引的 mapping？

**A**: Opensearch **不支持动态修改 mapping**。需要：
1. 删除旧索引
2. 创建新索引（带新的 mapping）
3. 重新导入数据

### Q5: 为什么我的向量搜索很慢？

**A**: 检查以下几点：
1. 确认向量字段创建了 HNSW/IVF 索引
2. 调整 HNSW 参数（增大 `ef_search` 提高精度，减小 `m` 提高速度）
3. 对于大数据量，考虑使用 IVF + PQ 压缩

---

## 15. 参考文档

- [Opensearch 索引管理文档](../doc/developer/03_Index_Management.md)
- [向量搜索文档](../doc/developer/06_Vector_Search.md)
- [Nested 结构与动态列](../doc/developer/10_Nested_Dynamic.md)
- [OpenSearch k-NN Plugin](https://opensearch.org/docs/latest/search-plugins/knn/)
- [pgvector 文档](https://github.com/pgvector/pgvector)

---

**文档版本**: v1.0  
**最后更新**: 2024-04-17  
**维护者**: Opensearch兼容接口Team
