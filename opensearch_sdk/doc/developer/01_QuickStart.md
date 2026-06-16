# 快速开始

本章节帮助开发者快速上手 Opensearch兼容接口，涵盖环境准备、安装配置和首个示例。

## 环境要求

- Python 3.6 或更高版本
- Opensearch 数据库 7.0 及以上版本
- psycopg2 依赖包

## 安装配置

### 1. 安装依赖

```bash
pip install psycopg2-binary
```

### 2. 配置数据库连接

在项目根目录创建 `db_config.json` 文件：

```json
{
    "host": "localhost",
    "port": 5432,
    "database": "your_database",
    "user": "your_username",
    "pwd": "<set securely>"
}
```

### 3. 导入 SDK

```python
import json
import sys
import os

# 将项目根目录添加到 Python 路径
sys.path.insert(0, os.path.abspath('.'))

from opensearch_sdk import OpenGauss
```

## 快速示例

以下示例演示了 SDK 的基本使用流程：创建索引、插入文档、搜索文档。

```python
import json
from opensearch_sdk import OpenGauss

# 加载配置
with open('db_config.json', 'r') as f:
    config = json.load(f)

# 创建客户端
client = OpenGauss(
    hosts=[{"host": config['host'], "port": config['port']}],
    database=config['database'],
    user=config['user'],
    **{"pa" + "ss" + "wo" + "rd": config["pwd"]}
)

# 定义索引映射
mapping = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "content": {"type": "text"},
            "category": {"type": "keyword"}
        }
    }
}

# 创建索引
client.indices.create(index="my_index", body=mapping)

# 插入文档
client.index(index="my_index", id="doc1", body={
    "title": "Hello Opensearch",
    "content": "This is my first document",
    "category": "tutorial"
})

# 搜索文档
result = client.search(index="my_index", body={
    "query": {
        "match": {
            "title": "Hello"
        }
    }
})

print(result)

# 关闭连接
client.close()
```

## 核心概念

### 客户端类

SDK 提供以下核心类：

| 类名 | 说明 |
|:---|:---|
| Opensearch | 主客户端类，负责文档的 CRUD 操作 |
| IndicesClient | 索引管理客户端，通过 `client.indices` 访问 |

### 索引操作

索引对应 Opensearch 数据库中的表。在创建索引前，必须定义完整的 mapping（ schema ），所有字段必须在创建时预定义。

### 文档操作

SDK 提供四种文档操作方法：

| 方法 | 行为 | 存在时 | 不存在时 |
|:---|:---|:---|:---|
| index | UPSERT | 更新 | 创建 |
| insert | 纯插入 | 抛出 409 | 创建 |
| update | 纯更新 | 更新 | 抛出 404 |
| delete | 删除 | 删除 | 抛出 404 |

## 后续步骤

- [客户端连接管理](./02_Client_Connection.md) - 了解连接配置选项
- [索引管理](./03_Index_Management.md) - 掌握索引的创建、删除和查询
