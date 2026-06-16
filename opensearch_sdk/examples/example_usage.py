# Example usage of the Opensearch兼容接口compatible with OpenSearch syntax

from utils import load_config
from opensearch_sdk.opengauss_client import OpenGauss
from opensearch_sdk.helpers import Index

# 加载数据库配置
config = load_config()

# Create a client with database connection
# The client will automatically establish connection and create cursor
client = OpenGauss(
    hosts=[{'host': config['host'], 'port': config['port']}],
    database=config['database'],
    user=config['user'],
    password=config['password']
)

try:
    # Direct usage of indices client
    # Create an index (table in Opensearch)
    
    client.indices.create(
        index='test1',
        body={
            'settings': {
                'number_of_shards': 1,
                'number_of_replicas': 0
            },
            'mappings': {
                'properties': {
                    'title': {'type': 'text'},
                    'description': {'type': 'text'},
                    'vector_field': {
                        'type': 'float_vector',
                        'dimension': 128
                    }
                }
            }
        }
    )
    print("Index 'test1' created successfully.")

    # Check if index exists
    if client.indices.exists(index='test1'):
        print("Index 'test1' exists!")

    # Get index information
    info = client.indices.get(index='test1')
    print(f"Index information: {info}")

    # Delete the index
    client.indices.delete(index='test1')
    print("Index 'test1' deleted.")

    # Method 2: Using the Index helper class
    index = Index('test1', using=client)

    # Configure index settings
    index.settings(
        number_of_shards=1,
        number_of_replicas=0
    )

    # Configure index mappings
    index.mapping({
        'title': {'type': 'text'},
        'description': {'type': 'text'},
        'vector_field': {
            'type': 'float_vector',
            'dimension': 128
        }
    })

    # Create the index
    index.create()
    print("Index 'test1' created using helper class.")

    # Check if index exists
    if index.exists():
        print("Index 'test1' exists!")

    # Delete the index
    index.delete()
    print("Index 'test1' deleted using helper class.")

finally:
    # Always close the connection when done
    client.close()
    print("Database connection closed.")
