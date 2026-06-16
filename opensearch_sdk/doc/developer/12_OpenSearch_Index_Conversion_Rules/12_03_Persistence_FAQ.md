# 持久化机制与转换示例

## 7. Mapping 持久化机制

### 7.1 存储位置

完整的 mapping 信息存储在 PostgreSQL 系统表 `pg_description` 中：

```sql
-- 查询 mapping
SELECT description 
FROM pg_description 
WHERE objoid = 'my_index'::regclass;
```

### 7.2 存储内容

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

---

## 8. 完整转换示例

### 8.1 OpenSearch 输入

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

### 8.2 Opensearch 输出（SQL 执行序列）

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

## 9. 常见问题 (FAQ)

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
