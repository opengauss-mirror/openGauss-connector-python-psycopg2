# 向量搜索测试设计：高级检索与性能

**对应技术文档**: [`06_Vector_Search.md`](06_Vector_Search.md)  
**测试负责模块**: `opensearch_sdk/client/search_ops.py`, `opensearch_sdk/retrieval/retrievers.py`  

## 二、高级检索功能测试

### 2.1 过滤条件测试

**TC-VS-004: 带过滤条件的 KNN 搜索测试**
```python
def test_knn_search_with_filter():
    """测试在向量搜索中应用布尔过滤条件"""
    filter_query = {
        "bool": {
            "must": [
                {"term": {"category": "electronics"}}
            ],
            "range": {
                "price": {"gte": 100}
            }
        }
    }
    
    results = client.knn_search(
        index="products",
        field="embedding",
        query_vector=[0.1, 0.2, ...],
        k=10,
        filter=filter_query
    )
    
    # 验证所有返回结果都满足过滤条件
    for hit in results['hits']['hits']:
        assert hit['_source']['category'] == 'electronics'
        assert hit['_source']['price'] >= 100
```

### 2.2 混合搜索测试

**TC-VS-005: 向量与文本混合搜索测试**
```python
def test_hybrid_vector_text_search():
    """测试结合向量相似度和 BM25 文本匹配的混合搜索"""
    search_body = {
        "query": {
            "bool": {
                "should": [
                    {
                        "knn": {
                            "embedding": {
                                "query_vector": [0.1, 0.2, ...],
                                "k": 20
                            }
                        }
                    },
                    {
                        "match": {
                            "description": "高性能处理器"
                        }
                    }
                ]
            }
        }
    }
    
    results = client.search(index="products", body=search_body)
    # 验证返回结果同时考虑了向量距离和文本相关性
    assert len(results['hits']['hits']) > 0
```

---

## 三、性能与压力测试

### 3.1 大规模向量搜索性能

**TC-VS-006: 百万级向量搜索延迟测试**
```python
def test_large_scale_vector_search_latency():
    """测试在百万级数据量下的向量搜索响应时间"""
    # 假设已有 1,000,000 条向量数据
    start_time = time.time()
    results = client.knn_search(
        index="large_vectors",
        field="embedding",
        query_vector=[0.1] * 768,
        k=10
    )
    end_time = time.time()
    
    latency = end_time - start_time
    print(f"Search latency: {latency:.3f}s")
    
    # 预期：HNSW 索引下应在 100ms 以内
    assert latency < 0.1
```

### 3.2 并发搜索稳定性

**TC-VS-007: 高并发向量搜索测试**
```python
def test_concurrent_vector_search():
    """测试多线程并发执行向量搜索时的稳定性"""
    def search_task():
        return client.knn_search(
            index="vectors",
            field="embedding",
            query_vector=[random.random() for _ in range(128)],
            k=5
        )
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(search_task) for _ in range(100)]
        results = [f.result() for f in futures]
    
    # 验证所有请求均成功返回
    assert all(len(r['hits']['hits']) > 0 for r in results)
```

---

## 四、测试执行建议

1. **向量生成**：使用随机数或预定义的基准向量集进行测试，确保维度一致性。
2. **索引预热**：在执行性能测试前，先执行几次搜索以触发 HNSW 索引的内存加载。
3. **资源监控**：监控数据库服务器的 CPU 和内存使用情况，特别是在大规模并发测试时。
4. **精度验证**：对于相似度算法，建议通过计算欧氏距离或余弦相似度手动验证 SDK 返回分数的准确性。
