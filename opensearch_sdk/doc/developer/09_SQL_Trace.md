# SQL 追踪功能 - Developer 文档

## 概述

SQL 追踪功能是 Opensearch兼容接口v1.0+ 的核心调试工具，用于捕获和记录所有数据库操作生成的 SQL 语句。

**版本**: v1.0  
**最后更新**: 2026-03-31  
**维护者**: Opensearch Team

---

## 功能特性

### 核心特性

- **非侵入式设计** - 默认关闭，生产环境零性能开销
- **全面追踪** - 覆盖所有核心方法（8/8）
- **灵活配置** - 支持参数脱敏、结果采样
- **线程安全** - 完全线程隔离
- **Metadata 记录** - 每个操作记录关键信息

### 支持的方法

| 类别 | 方法 | Metadata | Context 格式 |
|------|------|----------|-------------|
| **搜索** | search() | query_body | search_{index} |
| | knn_search() | query_vector, k, similarity | knn_search_{index} |
| **CRUD** | create() | document_id, field_count | create_{index} |
| | get() | document_id | get_{index} |
| | update() | document_id, updated_fields | update_{index} |
| | delete() | document_id | delete_{index} |
| **索引管理** | indices.create() | index_name, field_count | indices_create_{index} |
| | indices.delete() | index_name | indices_delete_{index} |

---

## 技术架构

### 三层包装器模式

```python
# Layer 1: 公共入口（条件路由）
def method(self, ...):
    if hasattr(self, 'sql_tracer') and self.sql_tracer.enabled:
        return self._method_with_trace(...)
    else:
        return self._method_impl(...)

# Layer 2: 追踪包装器（上下文管理）
def _method_with_trace(self, ...):
    with self.sql_tracer.trace_session("operation", index) as session:
        result = self._method_impl(...)
        
        # 记录 metadata
        if session.records:
            last_record.metadata['key'] = value
            last_record.context = f"operation_index"
        
        return result

# Layer 3: 原始实现（业务逻辑）
def _method_impl(self, ...):
    # 原有的业务逻辑代码
    pass
```

---

## 模块说明

### sql_tracer.py

**核心类**:

1. **SQLTraceRecord** (@dataclass)
   ```python
   @dataclass
   class SQLTraceRecord:
       sql: str
       params: Optional[Tuple] = None
       start_time: float = field(default_factory=time.time)
       end_time: float = 0.0
       duration_ms: float = 0.0
       result_count: int = 0
       error: Optional[str] = None
       context: str = ""
       sampled_results: List[Any] = field(default_factory=list)
       metadata: Dict[str, Any] = field(default_factory=dict)
   ```

2. **SQLTraceSession** (@dataclass)
   ```python
   @dataclass
   class SQLTraceSession:
       session_id: str
       operation: str
       index_name: Optional[str] = None
       records: List[SQLTraceRecord] = field(default_factory=list)
       start_time: float = field(default_factory=time.time)
       end_time: float = 0.0
       total_duration_ms: float = 0.0
   ```

3. **SQLTracer** (核心追踪器)
   ```python
   class SQLTracer:
       def __init__(
           self,
           enabled: bool = False,
           mask_sensitive_params: bool = True,
           max_sample_rows: int = 10,
           store_full_results: bool = False,
           export_dir: Optional[str] = None
       )
       
       @contextmanager
       def trace_session(operation: str, index_name: Optional[str] = None)
       
       def record_execution(cursor, sql, params, context)
       
       def get_last_session() -> Optional[SQLTraceSession]
   ```

---

## 使用指南

### 基础使用

```python
from opensearch_sdk import OpenGauss

# 启用 SQL 追踪
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="test_db",
    enable_sql_trace=True,              # 启用追踪
    sql_trace_mask_sensitive=True,      # 参数脱敏
    sql_trace_max_sample_rows=10        # 采样 10 行
)

# 执行操作
result = client.search("my_index", {
    "query": {"match": {"content": "hello"}}
})

# 查看追踪信息
session = client.sql_tracer.get_last_session()
print(f"Operation: {session.operation}")
print(f"SQL Count: {len(session.records)}")

for record in session.records:
    print(f"SQL: {record.sql}")
    print(f"Context: {record.context}")
    print(f"Metadata: {record.metadata}")

client.close()
```

### 高级用法

#### 1. 参数脱敏

敏感参数会自动检测并替换为 `***MASKED***`：

```python
# 检测到以下关键词会自动脱敏：
# - password
# - secret
# - token
# - key
# - credential

client.execute("INSERT INTO users (password) VALUES (%s)", ("secret123",))
# 记录的参数：('***MASKED***',)
```

#### 2. 结果采样

默认只保存前 10 行结果，避免内存溢出：

```python
# 修改采样配置
client = OpenGauss(
    ...,
    sql_trace_max_sample_rows=50,  # 采样前 50 行
    store_full_results=False       # 不保存完整结果集
)

# 关闭采样（不推荐）
client = OpenGauss(
    ...,
    sql_trace_max_sample_rows=0
)
```

#### 3. 多线程支持

每个线程有独立的会话，互不干扰：

```python
import threading

def worker(thread_id):
    client = OpenGauss(..., enable_sql_trace=True)
    result = client.search(f"index_{thread_id}", query)
    session = client.sql_tracer.get_last_session()
    print(f"Thread {thread_id}: {len(session.records)} SQLs")

threads = []
for i in range(5):
    t = threading.Thread(target=worker, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
```

---

## 测试规范

### 单元测试

所有测试基于 unittest 框架：

```python
import unittest
from opensearch_sdk import OpenGauss

class TestSQLTrace(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = OpenGauss(
            hosts=[...],
            enable_sql_trace=True
        )
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        cls.client.close()
    
    def test_search_trace(self):
        """测试 search 的 SQL 追踪"""
        result = self.client.search("index", {"query": {"match_all": {}}})
        
        session = self.client.sql_tracer.get_last_session()
        self.assertIsNotNone(session)
        self.assertEqual(session.operation, 'search')
        self.assertGreater(len(session.records), 0)

if __name__ == '__main__':
    unittest.main(verbosity=2)
```

### 测试文件列表

1. **test_sql_tracer.py** - 核心功能单元测试（23 个用例）
2. **test_full_integration.py** - 完整集成测试（9 个用例）
3. **quick_verify.py** - 快速验证脚本
4. **verify_knn_trace.py** - KNN 搜索验证
5. **verify_crud_trace.py** - CRUD 操作验证

---

## 注意事项

### 1. 性能影响

- **禁用时**: 零开销（直接调用原始方法）
- **启用时**: 每条 SQL 增加约 0.1-0.5ms 开销
- **建议**: 开发/测试环境启用，生产环境按需开启

### 2. 内存使用

- 默认只采样前 10 行结果
- 大结果集可能占用较多内存
- 调整 `sql_trace_max_sample_rows` 控制采样量

### 3. 线程安全

- 完全线程安全
- 每个线程独立会话
- 跨线程共享 tracer 需注意隔离

### 4. 测试规范

- 测试前后必须清理环境
- 禁止在通过的测试中输出调试信息
- 使用 unittest 框架，保持与现有测试体系一致

---

## 变更记录

### v1.0 (2026-03-31)

**新增功能**:
- SQLTracer 核心模块
- 8 个核心方法集成（search, knn_search, create, get, update, delete, indices.create, indices.delete）
- 参数脱敏
- 结果采样
- 线程安全
- Metadata 记录

**技术亮点**:
- 统一的三层包装器模式
- 非侵入式设计
- 完整的单元测试覆盖

---

## 相关资源

### 文档
- [SQL_TRACE_GUIDE.md](../examples/example_sql_trace.py) - 使用示例
- [项目总结报告.md](opensearch_sdk/tests/sql_trace/) - 测试目录

### 代码
- [`sql_tracer.py`](opensearch_sdk/client/sql_tracer.py) - 核心模块
- [`search_ops.py`](opensearch_sdk/client/search_ops.py) - 搜索方法
- [`document_ops.py`](opensearch_sdk/client/document_ops.py) - CRUD 方法
- [`indices_client.py`](opensearch_sdk/client/indices_client.py) - 索引管理

### 测试
- [`test_sql_tracer.py`](opensearch_sdk/tests/sql_trace/test_sql_tracer.py)
- [`test_full_integration.py`](opensearch_sdk/tests/sql_trace/test_full_integration.py)

---

**最后更新**: 2026-03-31  
**维护状态**: 活跃维护  
**生产就绪**: 是
