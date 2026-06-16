# 文档操作测试设计：基础 CRUD

**对应技术文档**: [`04_Document_CRUD.md`](04_Document_CRUD.md)  
**测试负责模块**: `opensearch_sdk/client/document_ops.py`  

## 一、单元测试设计

### 1.1 index() UPSERT 操作测试

#### 测试目标
验证 index() 方法的 UPSERT 语义（存在更新，不存在创建）

#### 测试用例设计

**TC-DO-001: index() 创建新文档测试**
```python
def test_index_create_new_document():
    """测试 index() 创建不存在的文档"""
    # 准备数据
    test_index = "test_index_upsert"
    doc_id = "doc_new_001"
    body = {
        "title": "New Document",
        "content": "This is a new document",
        "count": 10
    }
    
    # 执行操作
    result = client.index(index=test_index, id=doc_id, body=body)
    
    # 预期输出
    assert result['result'] == 'created'
    assert result['_id'] == doc_id
    assert result['_index'] == test_index
    
    # 验证方式
    retrieved = client.get(index=test_index, id=doc_id)
    assert retrieved['_source']['title'] == "New Document"
    assert retrieved['_source']['count'] == 10
```

**TC-DO-002: index() 更新已存在文档测试**
```python
def test_index_update_existing_document():
    """测试 index() 更新已存在的文档"""
    # 准备数据
    test_index = "test_index_upsert"
    doc_id = "doc_existing_001"
    
    # 先创建文档
    client.index(index=test_index, id=doc_id, body={
        "title": "Original Title",
        "count": 5
    })
    
    # 执行更新
    result = client.index(index=test_index, id=doc_id, body={
        "title": "Updated Title",
        "count": 20
    })
    
    # 预期输出
    assert result['result'] == 'updated'
    assert result['_id'] == doc_id
    
    # 验证方式
    retrieved = client.get(index=test_index, id=doc_id)
    assert retrieved['_source']['title'] == "Updated Title"
    assert retrieved['_source']['count'] == 20
```

---

### 1.2 create() 与 update() 方法测试

#### 测试目标
验证 create() 的强制创建行为和 update() 的强制更新行为

**TC-DO-003: create() 强制创建测试**
```python
def test_create_force_new():
    """测试 create() 强制创建新文档，若存在则报错"""
    doc_id = "doc_create_001"
    
    # 第一次创建成功
    result = client.create("my_index", doc_id, {"title": "Test"})
    assert result['result'] == 'created'
    
    # 第二次创建应抛出异常
    try:
        client.create("my_index", doc_id, {"title": "Duplicate"})
        assert False, "Should have raised an exception"
    except Exception as e:
        assert "already exists" in str(e).lower() or "409" in str(e)
```

**TC-DO-004: update() 强制更新测试**
```python
def test_update_force_existing():
    """测试 update() 强制更新现有文档，若不存在则报错"""
    doc_id = "doc_update_001"
    
    # 对不存在的文档执行 update 应报错
    try:
        client.update("my_index", doc_id, {"doc": {"title": "Test"}})
        assert False, "Should have raised an exception"
    except Exception as e:
        assert "not found" in str(e).lower() or "404" in str(e)
```
