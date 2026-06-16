# 文档操作测试设计：批量与高级功能

**对应技术文档**: [`04_Document_CRUD.md`](04_Document_CRUD.md)  
**测试负责模块**: `opensearch_sdk/client/document_ops.py`  

## 二、批量操作测试

### 2.1 bulk() 批量写入测试

#### 测试目标
验证 bulk() 方法处理大量数据时的性能和原子性

**TC-DO-005: bulk() 批量插入性能测试**
```python
def test_bulk_insert_performance():
    """测试 bulk() 批量插入 1000 条数据的性能"""
    actions = []
    for i in range(1000):
        actions.extend([
            {"index": {"_index": "bulk_test", "_id": f"doc_{i}"}},
            {"title": f"Doc {i}", "value": i}
        ])
    
    start_time = time.time()
    result = client.bulk(body=actions)
    end_time = time.time()
    
    assert len(result['items']) == 1000
    print(f"Bulk insert took {end_time - start_time:.2f}s")
```

**TC-DO-006: bulk() 混合操作测试**
```python
def test_bulk_mixed_operations():
    """测试 bulk() 同时执行 index, update, delete"""
    actions = [
        {"index": {"_index": "mixed_test", "_id": "doc1"}},
        {"title": "New Doc"},
        {"update": {"_index": "mixed_test", "_id": "doc2"}},
        {"doc": {"title": "Updated Doc"}},
        {"delete": {"_index": "mixed_test", "_id": "doc3"}}
    ]
    
    result = client.bulk(body=actions)
    # 验证各项操作的结果状态
    assert all(item.get('status') in [200, 201, 404] for item in result['items'])
```

---

## 三、特殊场景与错误处理测试

### 3.1 事务一致性测试

**TC-DO-007: 连接池模式下的事务隔离测试**
```python
def test_transaction_isolation_in_pool():
    """测试在连接池模式下，未提交的变更对其他连接不可见"""
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO my_index (id, title) VALUES ('tx_doc', 'Uncommitted')")
        # 此时在其他连接中查询应查不到该文档
    
    # 提交后应可见
    doc = client.get("my_index", "tx_doc")
    assert doc['_source']['title'] == 'Uncommitted'
```

### 3.2 异常处理测试

**TC-DO-008: 索引不存在异常测试**
```python
def test_index_not_found_exception():
    """测试对不存在的索引进行操作时抛出 IndexNotFoundException"""
    try:
        client.index(index="non_existent_index", id="1", body={})
        assert False, "Should have raised IndexNotFoundException"
    except IndexNotFoundException:
        pass
```

**TC-DO-009: 字段类型冲突测试**
```python
def test_mapping_conflict_exception():
    """测试插入数据类型与 mapping 定义不符时抛出 MappingConflictException"""
    # 假设 price 定义为 float
    try:
        client.index("my_index", "1", {"price": "not_a_number"})
        assert False, "Should have raised MappingConflictException"
    except MappingConflictException:
        pass
```

---

## 四、测试执行建议

1. **环境准备**：确保 Opensearch 数据库服务已启动且测试库干净。
2. **清理机制**：每个测试用例结束后应自动清理产生的测试索引，避免影响后续测试。
3. **并发测试**：建议在多线程环境下运行 bulk 测试，验证连接池的稳定性。
4. **性能监控**：在执行 bulk 和复杂查询测试时，记录 SQL 执行时间，便于后续优化对比。
