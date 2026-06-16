import json
import os
from typing import Dict, Iterable, List

from opensearch_sdk import OpenGauss


def create_client():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'db_config.json')
    with open(config_path, 'r', encoding='utf-8') as config_file:
        config = json.load(config_file)

    return OpenGauss(
        hosts=[{
            'host': config['host'],
            'port': config['port']
        }],
        user=config['user'],
        password=config['password'],
        database=config['database']
    )


def delete_index_if_exists(client, index_name: str, success_message: str = None) -> None:
    try:
        if client.indices.exists(index=index_name):
            client.indices.delete(index=index_name)
            if success_message:
                print(success_message)
    except Exception as error:
        print(f"[WARN] 清理索引失败: {error}")


def recreate_index(client, index_name: str, mapping: Dict) -> None:
    delete_index_if_exists(client, index_name, f"[PASS] 已清理旧索引: {index_name}")
    client.indices.create(index=index_name, body=mapping)
    print(f"[PASS] 创建测试索引: {index_name}")


def insert_docs(client, index_name: str, docs: Iterable[Dict], ignore_errors: bool = False) -> int:
    inserted_count = 0
    for doc in docs:
        doc_id = doc["id"]
        body = {key: value for key, value in doc.items() if key != "id"}
        try:
            client.index(index=index_name, id=doc_id, body=body)
            inserted_count += 1
        except Exception:
            if not ignore_errors:
                raise
    return inserted_count


def match_all_body(size: int = None) -> Dict:
    body = {"query": {"match_all": {}}}
    if size is not None:
        body["size"] = size
    return body


def search_hits(client, index_name: str, size: int = None) -> List[Dict]:
    return client.search(index=index_name, body=match_all_body(size))['hits']['hits']


def total_count(client, index_name: str) -> int:
    return client.search(index=index_name, body=match_all_body(0))['hits']['total']['value']


def category_should_query(categories: Iterable[str], minimum_should_match: int = 1) -> Dict:
    return {
        "query": {
            "bool": {
                "should": [
                    {"term": {"category": category}}
                    for category in categories
                ],
                "minimum_should_match": minimum_should_match
            }
        }
    }


def field_match_should_query(field_name: str, values: Iterable[str], minimum_should_match: int = 1) -> Dict:
    return {
        "query": {
            "bool": {
                "should": [
                    {"match": {field_name: value}}
                    for value in values
                ],
                "minimum_should_match": minimum_should_match
            }
        }
    }


def close_client_and_report_leaks(client) -> None:
    leak_message = _connection_pool_leak_message(client)
    client.close()
    if leak_message:
        print(f"\n[FAIL] {leak_message}")


def cleanup_index_and_close(client, index_name: str) -> None:
    delete_index_if_exists(client, index_name, f"\n[CLEANUP] 已清理测试索引: {index_name}")
    close_client_and_report_leaks(client)


def _connection_pool_leak_message(client) -> str:
    if not hasattr(client.connection, '_pool') or not client.connection._pool:
        return ""

    pool_status = client.connection._pool.get_pool_status()
    used_connections = pool_status.get('used_connections', 0)
    if used_connections == 0:
        return ""

    return f"测试结束后仍有 {used_connections} 个连接未归还: {pool_status}"
