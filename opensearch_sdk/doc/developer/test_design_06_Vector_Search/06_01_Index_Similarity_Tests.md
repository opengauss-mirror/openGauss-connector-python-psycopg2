# 向量搜索测试设计：索引与相似度

**对应技术文档**: [`06_Vector_Search.md`](06_Vector_Search.md)  
**测试负责模块**: `opensearch_sdk/client/search_ops.py`, `opensearch_sdk/client/vector_client.py`  

## 一、单元测试设计

### 1.1 向量索引创建测试

#### 测试目标
验证向量索引创建功能，包括维度验证、similarity 参数、HNSW 参数等

#### 补充测试用例

**TC-VS-001: 向量索引维度边界测试**
```python
def test_vector_index_dimension_boundaries():
    """测试向量索引维度的边界值"""
    from opensearch_sdk.client.constants import MIN_VECTOR_DIMENSION, MAX_VECTOR_DIMENSION
    
    # 测试最小维度 (1)
    mapping_min = {
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "dense_vector",
                    "dims": MIN_VECTOR_DIMENSION
                }
            }
        }
    }
    result = client.indices.create(index="test_min_dim", body=mapping_min)
    assert result['acknowledged'] == True
    
    # 测试非法维度（0）
    mapping_invalid = {
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "dense_vector",
                    "dims": 0
                }
            }
        }
    }
    try:
        client.indices.create(index="test_invalid_dim", body=mapping_invalid)
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "dims" in str(e).lower()
```

**TC-VS-002: HNSW 参数验证测试**
```python
def test_vector_index_hnsw_parameters():
    """测试 HNSW 索引参数的正确性"""
    # 测试自定义 m 和 ef_construction
    mapping_custom = {
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "dense_vector",
                    "dims": 128,
                    "similarity": "cosine",
                    "index_options": {
                        "m": 32,
                        "ef_construction": 128
                    }
                }
            }
        }
    }
    result = client.indices.create(index="test_hnsw_custom", body=mapping_custom)
    assert result['acknowledged'] == True
    
    # 验证方式：检查底层 SQL 索引定义
    index_def = client.connection.execute("""
        SELECT indexdef FROM pg_indexes 
        WHERE tablename = %s AND indexname LIKE '%embedding%'
    """, ("test_hnsw_custom",)).fetchone()
    
    assert "m=32" in index_def[0]
    assert "ef_construction=128" in index_def[0]
```

---

### 1.2 相似度算法测试

**TC-VS-003: 不同相似度算法对比测试**
```python
def test_similarity_algorithms_comparison():
    """测试 cosine, l2_norm, dot_product 三种算法的返回结果差异"""
    # 准备数据
    query_vec = [0.1, 0.2, 0.3]
    
    # 分别在不同算法的索引上执行搜索
    for sim_type in ['cosine', 'l2_norm', 'dot_product']:
        results = client.knn_search(
            index=f"test_{sim_type}",
            field="embedding",
            query_vector=query_vec,
            k=5,
            similarity=sim_type
        )
        
        # 验证返回结果格式
        assert 'hits' in results
        assert len(results['hits']['hits']) <= 5
        
        # 验证分数范围（cosine 应在 [-1, 1] 之间）
        if sim_type == 'cosine':
            for hit in results['hits']['hits']:
                assert -1.0 <= hit['_score'] <= 1.0
```
