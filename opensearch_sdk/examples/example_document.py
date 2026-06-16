# Example usage of the Opensearch兼容接口document operations

from utils import load_config
from opensearch_sdk import OpenGauss

# 加载数据库配置
config = load_config()

# Create a client with database connection
client = OpenGauss(
    hosts=[{'host': config['host'], 'port': config['port']}],
    database=config['database'],
    user=config['user'],
    password=config['password']
)

try:
    # 0. 清理旧数据（避免重复）
    print("Cleaning up existing data...")
    try:
        client.delete_index("test_index")
        print("Old index deleted successfully")
    except Exception:
        pass  # 索引不存在也没关系
    
    # 1. 创建索引 (表)
    mapping = {
        "mappings": {
            "properties": {
                "categories": {"type": "text"},
                "question": {"type": "text"},
                "answerList": {"type": "text"},
                "keywordList": {"type": "text"}
            }
        }
    }
    
    print("Creating index 'test_index'...")
    # 创建索引
    result = client.create_index("test_index", mapping)
    print(f"Index creation result: {result}")

    # 2.1 插入/更新单个文档 (create)
    print("\n--- Inserting/Updating Single Document ---")
    data = {
        "categories": ["一级分类 1", "一级分类 1/二级分类 1"],
        "question": "标准问题",
        "answerList": ["答案 1", "答案 2"],
        "keywordList": ["关键词 1", "关键词 2"]
    }
    result = client.create("test_index", "doc_id_001", data)
    print(f"Inserted document: {result}")

    # 2.2 批量插入/更新文档 (bulk) - 使用NDJSON格式
    print("\n--- Bulk Inserting/Updating Documents ---")
    NDJSON_DATA = """{"index":{"_index":"test_index","_id":"doc_001"}}
{"categories":["分类1"],"question":"问题1","answerList":["答案1"]}
{"index":{"_index":"test_index","_id":"doc_002"}}
{"categories":["分类2"],"question":"问题2","answerList":["答案2"]}
"""

    result = client.bulk(NDJSON_DATA)
    print(f"Bulk inserted documents: {result}")

    # 2.3 获取指定ID文档 (get_id)
    print("\n--- Getting Document by ID ---")
    doc = client.get_id("test_index", "doc_id_001")
    print(f"Retrieved document: {doc}")

    # 2.4 删除指定ID文档 (delete_id)
    print("\n--- Deleting Document by ID ---")
    result = client.delete_id("test_index", "doc_id_001")
    print(f"Deleted document: {result}")

    # 2.5 批量删除文档 (delete_ids)
    print("\n--- Bulk Deleting Documents ---")
    doc_ids = ["doc_001", "doc_002"]
    result = client.delete_ids("test_index", doc_ids)
    print(f"Bulk deleted documents: {result}")

    # 清理：删除索引
    print("\nDeleting index 'test_index'...")
    result = client.delete_index("test_index")
    print(f"Index deletion result: {result}")

finally:
    # Always close the connection when done
    client.close()
    print("Database connection closed.")