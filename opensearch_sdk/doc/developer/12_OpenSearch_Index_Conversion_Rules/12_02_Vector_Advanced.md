# 向量索引与高级特性

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
      "ef_construction": 64
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

---

## 5. Nested 结构与 Dynamic Templates

### 5.1 Nested 结构处理（扁平化策略）

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

### 5.2 Dynamic Templates 处理

Opensearch兼容接口**不支持真正的动态模板**，但会保存配置用于后续插入时的类型推断：

**SDK 行为**：
1. 创建表时**忽略** dynamic_templates（不会创建动态列）
2. 将完整 mapping（包括 dynamic_templates）保存到 `pg_description`
3. 插入文档时，如果字段不存在，会根据模板**自动推断类型并添加列**

**通配符转换**：
- `*_vec` → 正则表达式 `.*_vec`
- 匹配字段名如：`title_vec`, `content_vec`, `embedding_vec`

---

## 6. Settings 配置与标识符规范

### 6.1 Settings 配置处理

| OpenSearch Setting | Opensearch 处理 | 说明 |
|-------------------|--------------|------|
| `index.knn` | 解析但不使用 | Opensearch 自动管理向量索引 |
| `number_of_shards` | 忽略 | Opensearch 单节点，固定为 1 |
| `number_of_replicas` | 忽略 | Opensearch 不支持副本 |
| `similarity.BM25` | 转换为 SET 命令 | 设置全局 BM25 参数 |

**BM25 参数配置**：
```sql
-- OpenSearch 格式的 k1/b 参数会转换为 SET 命令
SET bm25_k1 = 1.5;
SET bm25_b = 0.8;
```

### 6.2 标识符规范化

**索引名（表名）规范**：
- 点号 `.`（OpenSearch 也不允许）
- 支持下划线 `_` 和连字符 `-`
- 转换：`my-index` → `my_index`

**字段名规范**：
- `.keyword` 后缀会被移除（兼容 OpenSearch 的子字段）
  - `libId.keyword` → `libId`
- 点号和连字符转换为下划线
  - `user-name` → `user_name`
