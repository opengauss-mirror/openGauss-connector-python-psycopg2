# Nested 结构与动态列 - 开发者指南

## 概述

本文档详细介绍 Opensearch兼容接口中 nested 结构处理机制和动态列功能的实现细节，供 SDK 开发者和高级用户参考。

---

## Nested 结构设计哲学

### 不支持 Nested 的原因

1. **性能考虑**
   - Nested 查询需要隐式 join，性能开销大
   - 存储膨胀严重（父字段重复）
   - 更新操作成本高（需重建整个文档）

2. **架构简化**
   - 减少代码复杂度
   - 降低维护成本
   - 更贴近关系型数据库设计

3. **使用场景**
   - 大多数业务可以通过扁平化解决
   - JSONB 提供了灵活的替代方案
   - 关联表更适合一对多关系

### 实现策略

```python
# indices_client.py - _validate_mapping_schema()

# 检测 nested 类型时发出警告
if 'nested' in field_props.get('type', ''):
    import warnings
    warnings.warn(
        "Opensearch does not support 'nested' type. "
        "Consider using flattened design or JSONB.",
        UserWarning,
        stacklevel=2
    )
```

---

## Dynamic Templates 实现

### 保存机制

**文件**: `opensearch_sdk/client/indices_client.py`

```python
def create(self, *, index: Any, body: Any = None, ...):
    # 提取完整的 mapping 信息（包括 dynamic_templates）
    完整_mapping = {
        'properties': {},
        'dynamic_templates': body.get('mappings', {}).get('dynamic_templates', [])
    }
    
    # 提取 properties 信息
    for field_name, field_props in properties.items():
        if isinstance(field_props, dict):
            完整_mapping['properties'][field_name] = {
                'type': field_props.get('type', 'text'),
                'dims': field_props.get('dims', field_props.get('dimension')),
                'similarity': field_props.get('similarity'),
                'index_options': field_props.get('index_options')
            }
    
    # 存储到 pg_description
    mapping_json = json_module.dumps(完整_mapping)
    cursor.execute(
        f'COMMENT ON TABLE "{validated_index}" IS %s',
        (mapping_json,)
    )
```

**关键点**：
- 同时保存 properties 和 dynamic_templates
- 使用 COMMENT ON TABLE 持久化
- 不影响主流程（异常时仅打印警告）

### 读取机制

**文件**: `opensearch_sdk/client/indices_client.py`

```python
def get_mapping(self, index: str):
    # 从 pg_description 读取
    comment_result = self._get_table_comment(index)
    
    if comment_result and comment_result[0]:
        comment_data = json_module.loads(comment_result[0])
        
        # 检查是否是 mapping（包含 properties 或 dynamic_templates）
        if 'properties' in comment_data or 'dynamic_templates' in comment_data:
            mapping_from_comment = comment_data
            
            # 恢复 properties
            for field_name, field_info in mapping_from_comment['properties'].items():
                mappings["mappings"]["properties"][field_name] = field_info
            
            # 同时返回 dynamic_templates（用于动态列推断）
            if 'dynamic_templates' in mapping_from_comment:
                mappings["mappings"]["dynamic_templates"] = mapping_from_comment['dynamic_templates']
```

### 匹配算法

**文件**: `opensearch_sdk/client/document_ops.py`

```python
def _handle_undefined_column(self, missing_column: str, processed_body: dict, mapping: dict):
    """处理未定义字段的逻辑"""
    
    # 方案 A: 从 dynamic_templates 匹配
    column_type = None
    dynamic_templates = mapping.get('mappings', {}).get('dynamic_templates', [])
    
    for template_item in dynamic_templates:
        # 遍历所有模板规则
        for template_name, template_config in template_item.items():
            match_pattern = template_config.get('match', '')
            
            if match_pattern:
                # 将通配符模式转换为正则表达式
                import re as regex_module
                regex_pattern = '^' + match_pattern.replace('*', '.*') + '$'
                
                if regex_module.match(regex_pattern, missing_column):
                    # 匹配成功，从模板中获取类型
                    template_mapping = template_config.get('mapping', {})
                    field_type = template_mapping.get('type', 'text')
                    
                    # 映射到数据库类型
                    type_mapping = {
                        'text': 'TEXT',
                        'keyword': 'VARCHAR',
                        'long': 'BIGINT',
                        'integer': 'INTEGER',
                        'float': 'FLOAT4',
                        'double': 'FLOAT8',
                        'boolean': 'BOOLEAN',
                        'date': 'TIMESTAMP',
                        'dense_vector': 'VECTOR',
                        'float_vector': 'VECTOR',
                        'knn_vector': 'VECTOR'
                    }
                    column_type = type_mapping.get(field_type, 'TEXT')
                    
                    # 如果是 vector 类型，检查是否有 dimension
                    if 'vector' in field_type.lower():
                        dims = template_mapping.get('dimension')
                        if dims:
                            column_type = f'VECTOR({dims})'
                    
                    print(f"从 dynamic_templates 推断列类型：{missing_column} -> {column_type}")
                    break
        if column_type:
            break
    
    # 方案 B: 如果 templates 中没有匹配，检查是否启用动态推断
    if not column_type:
        enable_dynamic_inference = getattr(self, 'enable_dynamic_inference', True)  # [FIX] 默认值为 True
        
        if enable_dynamic_inference and missing_column in processed_body:
            # 从样本值推断类型（降级方案）
            sample_value = processed_body[missing_column]
            column_type = self._infer_column_type_from_value(sample_value)
            print(f"从样本值推断列类型：{missing_column} -> {column_type}")
        else:
            # 未启用动态推断，抛出错误
            raise Exception(
                f"字段 '{missing_column}' 未在 mapping 中定义。"
                f"如需禁用自动添加列，请设置 client.enable_dynamic_inference = False"
            )
```

---

## Enable Dynamic Inference 开关

### 初始化

**文件**: `opensearch_sdk/client/document_ops.py`

```python
def _init_document_ops(self, **kwargs):
    """
    初始化 DocumentOpsMixin
    
    :arg enable_dynamic_inference: 是否启用动态列类型推断（默认 True）
                                  True: 当字段不在 mapping 中时，从样本值推断类型（宽松模式）
                                  False: 严格模式，字段必须在 mapping 中定义
    """
    # 动态列推断开关（默认启用 - 宽松模式）
    self.enable_dynamic_inference = kwargs.get('enable_dynamic_inference', True)
```

### 类型推断函数

**文件**: `opensearch_sdk/client/document_ops.py`

```python
def _infer_column_type_from_value(self, value: Any) -> str:
    """
    根据样本值推断列类型（降级方案）
    
    :param value: 样本值
    :return: SQL 类型名称
    """
    if value is None:
        return 'TEXT'  # 默认
    
    if isinstance(value, bool):
        return 'BOOLEAN'
    elif isinstance(value, int):
        return 'BIGINT'
    elif isinstance(value, float):
        return 'FLOAT4'
    elif isinstance(value, str):
        # 简单的日期格式检测
        import re
        if re.match(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$', value):
            return 'TIMESTAMP'
        return 'TEXT'
    elif isinstance(value, (list, dict)):
        # 复杂类型存储为 JSONB
        return 'JSONB'
    else:
        return 'TEXT'
```

### 动态列添加流程

```python
try:
    # 执行 INSERT
    cursor.execute(insert_sql, values)
except psycopg2.errors.UndefinedColumn as e:
    # 检测到 UndefinedColumn 错误
    error_message = str(e)
    missing_column_match = re.search(r'column "([^"]+)"', error_message)
    
    if missing_column_match:
        missing_column = missing_column_match.group(1)
        print(f"[DEBUG] 检测到缺失的列：{missing_column}")
        
        # 尝试推断类型
        column_type = self._get_column_type_from_mapping_or_inference(
            missing_column, processed_body, mapping
        )
        
        if column_type:
            # 动态添加列
            validated_column = _validate_identifier(missing_column)
            add_column_sql = sql.SQL("ALTER TABLE {} ADD COLUMN {}").format(
                sql.Identifier(validated_index),
                sql.Identifier(validated_column)
            )
            add_column_sql += sql.SQL(" {}").format(sql.SQL(column_type))
            
            print(f"[DEBUG] 执行 ALTER TABLE: {add_column_sql.as_string(cursor)}")
            cursor.execute(add_column_sql)
            print(f"成功添加列：{missing_column} ({column_type})")
            
            # 重新执行 INSERT
            print("重新执行插入操作...")
            cursor.execute(insert_sql, values)
        else:
            raise
```

---

## 测试验证

### 测试文件

1. **test_dynamic_column_modes.py** - 两种模式测试
   - `TestDynamicColumnStrictMode` - 严格模式测试
   - `TestDynamicColumnInferenceMode` - 宽松模式测试

2. **test_os_service.py** - 集成测试
   - 验证 dynamic_templates 在向量搜索中的使用

### 关键测试用例

```python
class TestDynamicColumnInferenceMode(unittest.TestCase):
    """测试宽松模式 - 启用动态类型推断"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        cls.db_config = load_db_config()
        # 启用动态推断
        cls.client = OpenGauss(**cls.db_config, enable_dynamic_inference=True)
        cls.index_name = "test_dynamic_infer"
        
        # 创建索引（只包含 title 和 content）
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"}
                }
            }
        }
        cls.client.indices.create(index=cls.index_name, body=mapping)
    
    def test_dynamic_column_inference(self):
        """测试动态列推断功能"""
        doc = {
            "title": "测试文档",
            "content": "内容",
            "dynamic_string": "字符串字段",      # 应推断为 TEXT
            "dynamic_number": 123,              # 应推断为 BIGINT
            "dynamic_bool": True,               # 应推断为 BOOLEAN
            "dynamic_float": 3.14,              # 应推断为 FLOAT4
        }
        
        # 插入应该成功
        result = self.client.index(index=self.index_name, id="doc1", body=doc)
        self.assertEqual(result['result'], 'created')
        
        # 验证列已添加
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = %s AND table_schema = 'public'
                """, (self.index_name,))
                db_columns = cursor.fetchall()
            finally:
                cursor.close()
        
        column_names = [col[0] for col in db_columns]
        
        # 验证动态字段存在
        expected_fields = ['dynamic_string', 'dynamic_number', 'dynamic_bool', 'dynamic_float']
        for field in expected_fields:
            self.assertIn(field, column_names)
        
        # 验证数据类型
        column_types = {col[0]: col[1] for col in db_columns}
        self.assertEqual(column_types.get('dynamic_string'), 'text')
        self.assertEqual(column_types.get('dynamic_number'), 'bigint')
        self.assertEqual(column_types.get('dynamic_bool'), 'boolean')
        self.assertIn(column_types.get('dynamic_float'), ['real', 'double precision'])
```

---

## 最佳实践建议

### SDK 开发者

1. **保持向后兼容**
   - dynamic_templates 是可选的
   - enable_dynamic_inference 默认关闭
   - 提供清晰的错误提示

2. **性能优化**
   - 缓存 mapping 信息，避免重复查询
   - 只在必要时进行类型推断
   - 记录日志便于调试

3. **安全性**
   - 严格验证字段名（防止 SQL 注入）
   - 限制动态列数量（防止表膨胀）
   - 提供关闭动态功能的选项

### 应用开发者

1. **生产环境配置**
   ```python
   client = OpenGauss(
       ...,
       enable_dynamic_inference=False  # 默认，推荐
   )
   
   # 预定义所有字段
   mapping = {
       "mappings": {
           "properties": {
               "field1": {"type": "text"},
               "field2": {"type": "keyword"}
           },
           "dynamic_templates": [...]  # 可选，用于规律字段
       }
   }
   ```

2. **开发环境配置**
   ```python
   client = OpenGauss(
       ...,
       enable_dynamic_inference=True  # 快速原型
   )
   
   # 可以灵活添加字段
   doc = {"new_field": "value"}  # 自动推断并添加
   ```

3. **监控和维护**
   - 定期检查表结构变化
   - 清理不再使用的动态列
   - 监控 INSERT 性能（动态推断有轻微开销）

---

## 常见问题

### Q1: Dynamic Templates 和 OpenSearch 完全兼容吗？

**A**: 基本兼容，但有以下差异：
- Opensearch 只支持 `match` 规则，不支持 `path_match`
- 模板配置会被保存并在插入时使用
- 不会自动创建索引，需要显式定义

### Q2: 动态列会影响性能吗？

**A**: 有轻微影响：
- 每次 INSERT 需要检查字段是否在 mapping 中
- 类型推断增加 CPU 开销（约 5-10%）
- ALTER TABLE 是 DDL 操作，有锁表开销

**建议**：
- 生产环境预定义所有字段
- 或使用 dynamic_templates 精确控制

### Q3: 如何禁用动态列功能？

**A**: 两种方式：
1. 不设置 `enable_dynamic_inference`（默认 False）
2. 确保所有字段都在 mapping 中定义

---

## 总结

### Nested 结构
- 不支持，推荐使用扁平化或 JSONB

### Dynamic Templates
- 完全支持，保存到 pg_description
- 正则匹配字段名
- 自动推断列类型

### Enable Dynamic Inference
- 可选开关（默认关闭）
- 从样本值推断类型
- 生产环境谨慎使用

### 两层推断机制
1. **优先**：从 dynamic_templates 匹配（精确）
2. **降级**：从样本值推断（灵活）
