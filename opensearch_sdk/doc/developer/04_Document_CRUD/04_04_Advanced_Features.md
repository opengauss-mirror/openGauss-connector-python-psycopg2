# 高级特性

本章节介绍 Opensearch兼容接口文档操作的高级特性，包括动态列推断、Nested 字段处理以及事务管理。

## 1. 动态列类型推断 (Dynamic Inference)

### 功能描述
当插入的文档包含未在 mapping 中定义的字段时，SDK 可以自动从样本值推断列类型并创建新列。

### 初始化配置
```python
from opensearch_sdk import OpenGauss

# 启用动态列推断（默认启用）
client = OpenGauss(
    hosts=[{"host": "localhost", "port": 5432}],
    database="mydb",
    user="admin",
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"},
    enable_dynamic_inference=True
)
```

### 工作原理
1. **检查字段是否存在**：插入文档时，SDK 首先检查字段是否在 mapping 中定义。
2. **匹配 dynamic_templates**：如果未定义，尝试匹配 `dynamic_templates` 中的模板规则。
3. **类型推断**：如果模板也未匹配，根据样本值推断类型：
   - `str` → TEXT
   - `int` → INTEGER
   - `float` → REAL
   - `bool` → BOOLEAN
   - `list/dict` → JSONB
4. **创建新列**：使用 `ALTER TABLE` 添加新列。

### 示例
```python
# 假设索引 my_index 只有 title 字段
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"}
        }
    }
}
client.indices.create(index="my_index", body=mapping)

# 插入包含新字段的文档（enable_dynamic_inference=True）
client.index(
    index="my_index",
    id="doc1",
    body={
        "title": "Test",
        "author": "John",      # 新字段，自动推断为 TEXT
        "views": 100,          # 新字段，自动推断为 INTEGER
        "tags": ["a", "b"]     # 新字段，自动推断为 JSONB
    }
)
# SDK 会自动执行：
# ALTER TABLE my_index ADD COLUMN author TEXT
# ALTER TABLE my_index ADD COLUMN views INTEGER
# ALTER TABLE my_index ADD COLUMN tags JSONB
```

---

## 2. Nested 字段处理

### 设计理念
Opensearch 采用**扁平化策略**处理 nested 字段，将嵌套对象展开为 `field.subfield` 形式的列存储。

### 示例
```python
# 原始 nested 结构
document = {
    "title": "Product",
    "comments": [  # nested 数组
        {"user": "Alice", "rating": 5},
        {"user": "Bob", "rating": 4}
    ]
}

# 扁平化后存储为（首值策略，只取第一个元素）
document_flat = {
    "title": "Product",
    "comments__user": "Alice",   # 使用双下划线分隔符
    "comments__rating": 5
}
```

### 实现细节
1. **写入时扁平化**：SDK 在 `_flatten_nested_document()` 中将 nested 对象展开。
2. **读取时重构**：SDK 在 `_reconstruct_nested_structure()` 中恢复 nested 结构。
3. **分隔符**：使用 `__`（双下划线）作为 nested 字段分隔符。

### 限制与注意事项
- **Nested 数组多值丢失**：采用“首值策略”，nested 数组中的多个对象只保留第一个元素
  - 例如：`[{"user": "Alice"}, {"user": "Bob"}]` → 只存储 `{"user": "Alice"}`
  - 原因：关系数据库不支持原生的 nested 数组类型
- **Nested 对象完全支持**：单层 nested 对象（非数组）可以完美支持
- **不支持深层嵌套**：建议嵌套层级不超过 3 层
- **推荐使用替代方案**：对于复杂嵌套结构，建议使用 JSONB 类型或扁平化设计

---

## 3. 事务管理

### 连接池模式下的事务管理
Opensearch兼容接口使用 `get_connection_for_operation()` 上下文管理器确保在连接池模式下的事务一致性。

### 使用示例
```python
# 方式 1：使用 transaction() 上下文管理器（推荐）
with client.transaction() as conn:
    cursor = conn.cursor()
    try:
        # 在同一连接上执行多个操作
        cursor.execute("INSERT INTO my_index (id, title) VALUES (%s, %s)", ("doc1", "Title 1"))
        cursor.execute("INSERT INTO my_index (id, title) VALUES (%s, %s)", ("doc2", "Title 2"))
        # 正常退出时自动提交
    except Exception:
        # 异常时自动回滚
        raise

# 方式 2：直接使用 SDK 方法（自动管理事务）
try:
    client.index(index="my_index", id="doc1", body={"title": "Test"})
    client.index(index="my_index", id="doc2", body={"title": "Test 2"})
except Exception as e:
    print(f"操作失败: {e}")
```

### 重要说明
- **单连接模式**：可以直接使用 `client.commit()` 和 `client.rollback()`。
- **连接池模式**：必须使用 `transaction()` 上下文管理器或依赖自动事务管理。
- **禁止跨连接事务**：不能在多个 `get_connection_for_operation()` 之间共享事务。
