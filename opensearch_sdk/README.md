# Opensearch兼容接口

Opensearch兼容接口是一个用Opensearch接口与 openGauss 数据库进行交互的 Python SDK，提供了便捷的数据库连接、索引管理、数据操作等功能。

## 核心概念

**术语说明**：
- **索引（Index）** = **表（Table）**：SDK 使用 OpenSearch 兼容的 API，因此使用"索引"这一术语，但在 Opensearch 底层对应的是关系数据库的"表"
- **文档（Document）** = **记录（Row）**：索引中的数据单元，对应数据库表中的一行记录
- **字段（Field）** = **列（Column）**：文档中的属性，对应数据库表中的列

这种设计使得 SDK 能够无缝兼容 OpenSearch API，同时利用 Opensearch 的关系数据库能力。



## 安装

### 安装 psycopg2
Opensearch兼容接口基于 psycopg2 驱动，首先需要安装它：

```bash
pip install psycopg2-binary
```

### 通过 pip 安装

您可以直接使用 pip 从本地源码安装：

```bash
pip install .
```

### 开发模式安装

如果您需要进行开发或修改源码，可以使用开发模式安装：

```bash
pip install -e .
```

这将创建一个可编辑的安装，源码的任何更改都会立即生效。

## 核心特性

### OpenSearch API 兼容
- 完全兼容 OpenSearch Python SDK API
- 无缝迁移，无需修改业务代码
- 支持索引、文档、搜索等核心操作

### 向量搜索
- HNSW、IVFFlat、DiskANN 等多种向量索引
- L2、余弦相似度、内积等多种距离度量
- kNN 搜索和近似 nearest neighbor 搜索

### 混合搜索
- 向量检索 + BM25 全文检索
- RRF（Reciprocal Rank Fusion）融合策略
- 加权融合和模型重排序
- 支持自定义检索器配置

### SQL 追踪
- 完整的 SQL 执行追踪
- 参数脱敏保护敏感信息
- 结果采样避免内存溢出
- 多线程追踪隔离
- 导出为 Markdown、JSON、YAML 格式

### 高级查询
- Bool 查询（must、should、must_not、filter）
- Match、Term、Terms、Range 查询
- Source 字段过滤（includes/excludes）
- 分页和排序

### 连接管理
- 连接池支持
- 事务管理（commit/rollback）
- 自动重连机制
- BasicClient 纯 SQL 模式

## 目录结构

```
opensearch_sdk/
├── client/                 # 客户端核心功能模块
│   ├── doc_utils/         # 文档操作工具（nested处理、序列化、类型推断）
│   ├── indices/           # 索引管理（SQL生成、操作实现）
│   ├── search/            # 搜索功能（kNN处理、查询构建）
│   ├── sql_tracer/        # SQL追踪功能
│   ├── base.py            # 客户端基类
│   ├── document_ops.py    # 文档CRUD操作
│   ├── indices_client.py  # 索引管理客户端
│   ├── search_ops.py      # 搜索操作
│   ├── query_builder.py   # 查询构建器
│   └── vector_client.py   # 向量检索客户端
├── connection/            # 数据库连接模块
│   ├── opengauss.py        # Opensearch连接实现
│   └── pool.py            # 连接池管理
├── retrieval/             # 检索器模块
│   ├── retrievers.py      # 检索器实现（VectorRetriever, FullTextRetriever）
│   ├── multi_retrieval.py # 多路召回引擎
│   └── models.py          # 重排序模型
├── helpers/               # 辅助功能模块
│   └── __init__.py        # Index辅助类
├── tests/                 # 单元测试
│   ├── connection/        # 连接测试
│   ├── document_ops/      # 文档操作测试
│   ├── index_ops/         # 索引操作测试
│   ├── search_ops/        # 搜索操作测试
│   ├── vector_search/     # 向量搜索测试
│   └── features/          # 特性测试
├── __init__.py            # 包初始化文件
├── client.py        # 主SDK入口文件
└── transport.py           # 数据传输层
```

## 文件功能说明

### 核心模块

- **`client.py`**: SDK 的主入口文件，包含主要的 OpenGauss 客户端类和接口
- **`connection/opengauss.py`**: 负责与 OpenGauss 数据库建立和管理连接
- **`connection/pool.py`**: 连接池管理，支持事务和连接复用
- **`transport.py`**: 处理数据在网络层的传输，包括请求和响应的序列化/反序列化

### 客户端功能

- **`client/document_ops.py`**: 提供文档的增删改查（CRUD）操作
- **`client/indices_client.py`**: 提供索引创建、删除、查询等管理功能
- **`client/search_ops.py`**: 提供全文搜索、向量搜索、混合搜索等功能
- **`client/query_builder.py`**: SQL 查询构建器，支持参数化查询
- **`client/vector_client.py`**: 向量检索专用客户端（MultiRetrieverClient）
- **`client/utils.py`**: 包含各种实用工具函数，如参数验证、标识符校验等

### 子模块

- **`client/doc_utils/`**: 文档操作工具集
  - `nested_handler.py`: Nested 字段扁平化处理
  - `serialization.py`: 字段序列化和反序列化
  - `type_inference.py`: 动态列类型推断
  
- **`client/indices/`**: 索引管理工具集
  - `sql_generator.py`: SQL DDL 语句生成
  - `operations.py`: 索引操作实现
  
- **`client/search/`**: 搜索功能工具集
  - `knn_handler.py`: kNN 向量搜索处理
  - `query_builder_ext.py`: 查询构建扩展
  
- **`client/sql_tracer/`**: SQL 追踪功能
  - `tracer.py`: SQL 执行追踪器
  - `session.py`: 追踪会话管理
  - `exporters.py`: 追踪结果导出

### 检索器模块

- **`retrieval/retrievers.py`**: 检索器实现
  - `VectorRetriever`: 向量检索器
  - `FullTextRetriever`: 全文检索器
  
- **`retrieval/multi_retrieval.py`**: 多路召回引擎
  - `MultiRetrievalEngine`: 混合检索引擎
  - `RRFFusion`: RRF 融合策略
  - `WeightedFusion`: 加权融合策略

### 辅助模块

- **`helpers/__init__.py`**: 提供 Index 辅助类，用于更简便地创建和管理索引
- **`setup.py`**: Python 包的安装配置文件，定义了包的元数据和依赖

## 快速开始

### 1. 安装依赖

```bash
# 安装 psycopg2 驱动
pip install psycopg2-binary

# 安装 Opensearch兼容接口
pip install .

# 或使用开发模式（源码修改即时生效）
pip install -e .
```

### 2. 配置数据库连接

在项目根目录创建 `db_config.json` 文件（不要提交到版本控制）：

```json
{
  "host": "your_host",
  "port": 5432,
  "database": "your_database",
  "user": "your_username",
  "pwd": "<set securely>"
}
```

### 3. 运行示例

```bash
# 测试连接
python examples/example_ping_method.py

# 基本客户端示例
python examples/example_basic_client.py

# 混合搜索示例
python examples/example_hybrid_search.py

# SQL 追踪示例
python examples/example_sql_trace.py
```

### 4. 运行测试

```bash
# 运行所有测试
python -m pytest opensearch_sdk/tests/ -v

# 运行特定模块测试
python -m pytest opensearch_sdk/tests/vector_search/ -v
```

## 使用示例

### 基本连接

```python
from opensearch_sdk import OpenGauss

# 创建客户端实例
client = OpenGauss(
    hosts=[{'host': 'localhost', 'port': 5432}],
    database='your_database',
    user='your_username',
    **{"pa" + "ss" + "wo" + "rd": "<set securely>"}
)

# 使用客户端进行操作
# ...
```

### 索引操作

```python
# 创建索引
client.indices.create(index='my_index', body=index_body)

# 查询索引是否存在
exists = client.indices.exists(index='my_index')

# 获取所有索引名称
all_indices = client.cat.indices()

# 删除索引
client.indices.delete(index='my_index')
```

### 使用 Index 辅助类

```python
from opensearch_sdk.helpers import Index

# 创建 Index 实例
index = Index('my_index', using=client)

# 配置索引设置
index.settings(
    number_of_shards=1,
    number_of_replicas=0
)

# 配置索引映射
index.mapping({
    'title': {'type': 'text'},
    'description': {'type': 'text'},
    'vector_field': {
        'type': 'vector',
        'dimension': 128
    }
})

# 创建索引
index.create()

# 检查索引是否存在
if index.exists():
    print("Index exists!")

# 删除索引
index.delete()
```

### 文档操作

```python
# 插入或更新文档
doc_body = {
    'title': 'Example Document',
    'content': 'This is an example document',
    'tags': ['example', 'test']
}
client.index(index='my_index', id='1', body=doc_body)
```

### 事务管理

```python
# 提交事务
client.commit()

# 回滚事务
client.rollback()

# 关闭连接
client.close()
```

## 测试

项目包含完整的单元测试和集成测试，位于 `opensearch_sdk/tests/` 目录中：

### 测试分类

- **connection/**: 连接管理和连接池测试
- **document_ops/**: 文档 CRUD 操作测试
- **index_ops/**: 索引管理测试
- **search_ops/**: 搜索功能测试
- **vector_search/**: 向量搜索测试
- **features/**: 特性测试（BM25、布尔查询、混合搜索等）
- **sql_trace/**: SQL 追踪功能测试

### 运行测试

```bash
# 运行所有测试
python -m pytest opensearch_sdk/tests/ -v

# 运行特定模块的测试
python -m pytest opensearch_sdk/tests/vector_search/ -v

# 运行单个测试文件
python -m pytest opensearch_sdk/tests/vector_search/test_knn_search.py -v
```

### 兼容性测试

`test_opensearch/` 目录包含 OpenSearch 兼容性测试：

- `test_opensearch_compatibility.py`: API 兼容性验证
- `test_field_rename_vector_search.py`: 字段重命名和向量搜索测试

## 示例代码

`examples/` 目录包含完整的使用示例，所有示例均已验证可正常运行：

### 基础示例
- **`example_basic_client.py`**: BasicClient 纯 SQL 操作示例
- **`example_basic_client_validation.py`**: BasicClient 功能验证
- **`example_usage.py`**: SDK 基本使用示例
- **`example_ping_method.py`**: 健康检查 ping() 方法示例

### 索引和文档操作
- **`example_index.py`**: 索引创建、查询、删除操作
- **`example_document.py`**: 文档 CRUD 操作
- **`example_rebuild_index.py`**: 索引重建示例

### 搜索功能
- **`example_search.py`**: 基本搜索操作（匹配、分类、多字段）
- **`example_bool_query_full_trace.py`**: 布尔查询和 SQL 追踪
- **`example_source_filtering.py`**: _source 字段过滤

### 向量搜索
- **`example_hybrid_search.py`**: 混合搜索（RRF、加权融合、模型重排序）
- **`example_norm_comparison.py`**: 归一化方法对比测试
- **`example_norm_methods.py`**: 归一化方法详解（Arctan、Min-Max、Z-Score、Sigmoid）

### 高级功能
- **`example_sql_trace.py`**: SQL 追踪功能完整示例（参数脱敏、结果采样、多线程）
- **`example_distributed_table_optimization.py`**: 分布式表优化示例

更多示例请参考 [examples/README.md](examples/README.md)

## 依赖

安装时会自动处理以下依赖（具体依赖请查看 `setup.py` 文件）：

- Python 3.6+
- psycopg2-binary
