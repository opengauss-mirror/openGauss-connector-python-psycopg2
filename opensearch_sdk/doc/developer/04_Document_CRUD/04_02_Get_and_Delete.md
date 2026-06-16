# 查询与删除操作

本章节介绍 Opensearch兼容接口的文档查询 (`get`) 和批量删除 (`delete_ids`) 功能。

## 1. get 方法 (文档查询)

### 功能描述
根据文档 ID 获取文档内容。如果文档不存在，将抛出 404 Not Found 错误。

### 函数签名
```python
def get(self, index: str, id: str) -> Any
```

### 代码示例
```python
# 获取文档
result = client.get(
    index="my_index",
    id="doc1"
)
print(result)
# 输出: {'_index': 'my_index', '_id': 'doc1', '_source': {...}}
```

---

## 2. delete_ids 方法 (批量删除)

### 功能描述
根据 ID 列表批量删除文档。

### 函数签名
```python
def delete_ids(self, index: str, ids: List[str]) -> Any
```

### 内部流程
1. **参数验证**：验证索引名称合法性及 ID 列表非空。
2. **批量删除**：构建 `DELETE FROM {index} WHERE id IN (%s, %s, ...)` SQL 并执行。
3. **返回结果**：统计并返回删除的文档数量。

### 代码示例
```python
# 批量删除
result = client.delete_ids(
    index="my_index",
    ids=["doc1", "doc2", "doc3"]
)
print(result)
# 输出: {'deleted': 3}
```
