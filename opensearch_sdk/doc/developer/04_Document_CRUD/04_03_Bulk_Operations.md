# 批量操作 (Bulk)

本章节介绍 Opensearch兼容接口的批量操作功能，支持通过 NDJSON 格式一次性执行多个文档操作。

## 1. bulk 方法

### 功能描述
解析 NDJSON（Newline Delimited JSON）格式的批量操作指令并执行。

### 函数签名
```python
def bulk(self, body: str, *, refresh: bool = False) -> Any
```

### NDJSON 格式
```json
{action_and_metadata}
optional_source
{action_and_metadata}
optional_source
...
```

### 支持的操作类型
| 操作 | 语法 | 说明 |
|:---|:---|:---|
| index | `{"index": {"_index": "...", "_id": "..."}}` | 插入或更新 |
| create | `{"create": {"_index": "...", "_id": "..."}}` | 仅插入 |
| update | `{"update": {"_index": "...", "_id": "..."}}` | 更新 |
| delete | `{"delete": {"_index": "...", "_id": "..."}}` | 删除 |

### 代码示例
```python
# 批量操作
body = """
{"index": {"_index": "my_index", "_id": "doc1"}}
{"title": "Doc 1", "content": "Content 1"}
{"index": {"_index": "my_index", "_id": "doc2"}}
{"title": "Doc 2", "content": "Content 2"}
{"update": {"_index": "my_index", "_id": "doc1"}}
{"doc": {"views": 100}}
{"delete": {"_index": "my_index", "_id": "doc3"}}
"""

result = client.bulk(body)
print(result)
```

### 返回值结构
```python
{
    "took": 123,  # 耗时（毫秒）
    "errors": False,  # 是否有错误
    "items": [
        {"index": {"_id": "1", "result": "created", "status": 201}},
        {"update": {"_id": "2", "result": "updated", "status": 200}},
        {"delete": {"_id": "3", "result": "deleted", "status": 200}}
    ]
}
```

### 重要说明
- **事务原子性**：所有操作在同一个事务中执行，任何失败都会回滚全部操作
- **索引一致性**：bulk 请求中的所有操作必须针对同一个索引
- **不支持跨索引操作**：如果检测到不同索引会抛出 `ValueError`

### 内部流程
1. **解析 NDJSON**：按行分割，解析操作元数据和可选的文档内容。
2. **验证索引一致性**：所有操作必须针对同一个索引，否则会抛出错误。
3. **事务化执行**：在单个数据库连接上开启事务，依次执行每个操作。
4. **原子性保证**：任何操作失败都会回滚整个事务，确保数据一致性。
5. **收集结果**：返回所有操作的执行结果列表和总耗时。
