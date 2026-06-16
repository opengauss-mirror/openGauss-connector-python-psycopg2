# Opensearch兼容接口示例代码

本目录包含 Opensearch兼容接口的使用示例，展示各种常见操作场景。

## 示例列表

### 1. panzhi_index_example.py - 索引操作示例

**功能**: 演示索引的创建、查询、删除等完整生命周期管理

**主要操作**:
-  检查索引是否存在
-  创建新索引（带 mapping 配置）
-  获取所有索引名称
-  获取索引详细信息
-  删除索引

**运行方式**:
```bash
cd examples
python panzhi_index_example.py
```

---

### 2. panzhi_document_example.py - 文档操作示例

**功能**: 演示文档的增删改查（CRUD）操作

**主要操作**:
-  插入单个文档（insert）
-  批量插入文档（bulk）
-  获取指定 ID 文档（get_id）
-  删除指定 ID 文档（delete_id）
-  批量删除文档（delete_ids）

**运行方式**:
```bash
cd examples
python panzhi_document_example.py
```

---

### 3. panzhi_search_example.py - 搜索操作示例

**功能**: 演示各种搜索查询功能

**主要操作**:
-  通用搜索（search）
-  按分类精确搜索（search_by_category）
-  多字段条件搜索（search_by_multiple_fields）
-  按条件删除文档（delete_docs_by_field_values）

**运行方式**:
```bash
cd examples
python panzhi_search_example.py
```

---

## [SETUP] 配置说明

所有示例脚本都从项目根目录的 `db_config.json` 加载数据库配置：

```json
{
  "database": "es",
  "user": "your_username",
  "password": "your_password",
  "host": "database_host",
  "port": 5432
}
```

**注意**: 请确保 `db_config.json` 中的数据库连接信息正确无误。

---

## 快速开始

1. **配置数据库连接**
   ```bash
   # 编辑根目录的 db_config.json
   # 填入正确的数据库连接信息
   ```

2. **安装依赖**
   ```bash
   pip install -e .
   ```

3. **运行示例**
   ```bash
   cd examples
   python panzhi_index_example.py
   ```

---

## 学习路径建议

**新用户推荐顺序**:
1. 先运行 `panzhi_index_example.py` - 了解索引管理
2. 再运行 `panzhi_document_example.py` - 学习文档 CRUD
3. 最后运行 `panzhi_search_example.py` - 掌握查询搜索

---

## [LINK] 相关资源

- **测试套件**: `opensearch_sdk/tests/` - 单元测试和集成测试
- **开发文档**: `doc/` 目录 - 详细的 API 文档和最佳实践
- **已知问题**: `KNOWN_ISSUES.md` - 当前限制和使用注意事项

---

## [QUESTION] 常见问题

### Q: 这些示例代码可以直接用于生产环境吗？

A: 不建议直接使用。示例代码主要用于演示和学习，生产环境需要：
- 添加错误处理和重试机制
- 实现连接池管理
- 考虑性能和安全性
- 根据实际业务需求调整

### Q: 如何修改示例以适应我的需求？

A: 建议步骤：
1. 复制示例文件到您的项目目录
2. 修改 mapping 配置以匹配您的数据结构
3. 调整查询条件和业务逻辑
4. 添加适当的错误处理

### Q: 运行示例时报错怎么办？

A: 检查清单：
-  数据库连接配置是否正确
-  数据库服务是否正常运行
-  是否已安装 opensearch_sdk
-  是否有足够的数据库权限

---

**最后更新**: 2026-03-13  
**维护者**: Opensearch兼容接口Team
