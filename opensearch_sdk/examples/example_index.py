from utils import load_config

from opensearch_sdk.opengauss_client import OpenGauss

mapping = {
    "mappings": {
        "properties": {
            "categories": {"type": "text", "index": True},
            "question": {"type": "keyword", "index": True},
            "answerList": {"type": "text"}
        }
    }
}

# 加载数据库配置
config = load_config()

# Create a client with database connection
# The client will automatically establish connection and create cursor
os_client = OpenGauss(
    hosts=[{'host': config['host'], 'port': config['port']}],
    database=config['database'],
    user=config['user'],
    password=config['password']
)

try:
    # 获取所有索引名称 (初始状态)
    print("Getting all index names (initial state)...")
    index_names = os_client.cat.indices()
    print(f"All index names: {index_names}")
    
    # 检查索引是否存在
    print("\nChecking if index 'test_index' exists...")
    exists = os_client.indices.exists(index="test_index")
    print(f"Index 'test_index' exists: {exists}")
    
    # 创建索引
    print("\nCreating index 'test_index'...")
    result = os_client.create_index("test_index", mapping)
    print(f"Index creation result: {result}")
    
    # 再次检查索引是否存在
    print("\nChecking if index 'test_index' exists after creation...")
    exists = os_client.indices.exists(index="test_index")
    print(f"Index 'test_index' exists: {exists}")
    
    # 获取索引信息
    print("\nGetting index 'test_index' information...")
    info = os_client.indices.get(index="test_index")
    print(f"Index information: {info}")
    
    # 再次获取所有索引名称 (创建索引后)
    print("\nGetting all index names (after creating test_index)...")
    index_names = os_client.cat.indices()
    print(f"All index names: {index_names}")
    
    # 直接通过主客户端获取所有索引名称
    print("\nGetting all index names using direct method...")
    index_names = os_client.get_all_index_names()
    print(f"All index names: {index_names}")
    
    # 删除索引
    print("\nDeleting index 'test_index'...")
    result = os_client.delete_index("test_index")
    print(f"Index deletion result: {result}")
    
    # 再次检查索引是否存在
    print("\nChecking if index 'test_index' exists after deletion...")
    exists = os_client.indices.exists(index="test_index")
    print(f"Index 'test_index' exists: {exists}")
    
    # 最后获取所有索引名称 (删除索引后)
    print("\nGetting all index names (after deleting test_index)...")
    index_names = os_client.cat.indices()
    print(f"All index names: {index_names}")

finally:
    # 关闭连接
    os_client.close()
    print("\nDatabase connection closed.")