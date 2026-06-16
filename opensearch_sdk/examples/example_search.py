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
    print("--- Opensearch兼容接口Search Operations Example ---")
    
    # 创建测试索引
    print("\nCreating test index...")
    mapping = {
        "mappings": {
            "properties": {
                "categories": {"type": "text"},
                "question": {"type": "text"},
                "answerList": {"type": "text"},
                "doc_uuid": {"type": "keyword"}
            }
        }
    }
    
    client.create_index("test_index_search", mapping)
    print("Created index: test_index_search")
    
    # 插入测试数据
    print("\nInserting test documents...")
    test_documents = [
        {
            "id": "doc_001",
            "data": {
                "categories": "一级分类1/二级分类1",
                "question": "标准问题1",
                "answerList": "答案1",
                "doc_uuid": "uuid1"
            }
        },
        {
            "id": "doc_002",
            "data": {
                "categories": "一级分类1/二级分类2",
                "question": "标准问题2",
                "answerList": "答案2",
                "doc_uuid": "uuid2"
            }
        },
        {
            "id": "doc_003",
            "data": {
                "categories": "一级分类2/二级分类1",
                "question": "标准问题3",
                "answerList": "答案3",
                "doc_uuid": "uuid3"
            }
        },
        {
            "id": "doc_004",
            "data": {
                "categories": "一级分类1/二级分类1",
                "question": "另一个问题",
                "answerList": "答案4",
                "doc_uuid": "uuid4"
            }
        }
    ]
    
    for doc in test_documents:
        result = client.index("test_index_search", doc["id"], doc["data"])
        print(f"Inserted document {doc['id']}: {result['result']}")
    
    # 3.1 通用搜索 (search)
    print("\n--- 3.1 Generic Search ---")
    # 接口：os_client.search()
    # 功能：执行通用搜索查询
    # 示例：
    search_body = {
        "query": {
            "match": {
                "question": "标准问题"
            }
        },
        "size": 10
    }
    results = client.search("test_index_search", search_body)
    print(f"Search results for '标准问题':")
    for hit in results["hits"]["hits"]:
        print(f"  - {hit['_source']}")
    
    # 3.2 按分类搜索 (search_by_category)
    print("\n--- 3.2 Search by Category ---")
    # 接口：os_client.search() with match_phrase
    # 功能：按分类精确搜索
    # 示例：
    results = client.search_by_category("test_index_search", "一级分类1/二级分类1")
    print(f"Search results for category '一级分类1/二级分类1':")
    for hit in results["hits"]["hits"]:
        print(f"  - {hit['_source']}")
    
    # 3.3 多字段条件搜索 (search_by_multiple_fields)
    print("\n--- 3.3 Search by Multiple Fields ---")
    # 接口：os_client.search() with bool query
    # 功能：根据多个字段值进行搜索
    # 示例：
    field_value_pairs = {
        "doc_uuid": ["uuid1", "uuid2"]
    }
    results = client.search_by_multiple_fields(
        "test_index_search", 
        field_value_pairs, 
        source_fields=["question", "answerList"],
        size=20
    )
    print(f"Search results for doc_uuid in ['uuid1', 'uuid2']:")
    for hit in results["hits"]["hits"]:
        print(f"  - {hit['_source']}")
    
    # 3.4 按条件删除文档 (delete_docs_by_field_values)
    print("\n--- 3.4 Delete Documents by Field Values ---")
    # 接口：os_client.delete_by_query()
    # 功能：根据字段值删除文档
    # 示例：
    result = client.delete_docs_by_field_values(
        "test_index_search", 
        "doc_uuid", 
        ["uuid3", "uuid4"]
    )
    print(f"Deleted {result['deleted']} documents with doc_uuid in ['uuid3', 'uuid4']")
    
    # 验证删除结果
    print("\nVerifying deletion by searching for remaining documents...")
    # 使用空查询来获取所有文档，这相当于match_all查询
    all_docs = client.search("test_index_search", {"query": {}})
    print(f"Remaining documents: {all_docs['hits']['total']['value']}")
    for hit in all_docs["hits"]["hits"]:
        print(f"  - {hit['_source']}")

finally:
    # 清理测试数据
    print("\nCleaning up test index...")
    try:
        client.delete_index("test_index_search")
        print("Deleted test index: test_index_search")
    except Exception as e:
        print(f"Error deleting test index: {e}")
    
    # 关闭连接
    client.close()
    print("Database connection closed.")