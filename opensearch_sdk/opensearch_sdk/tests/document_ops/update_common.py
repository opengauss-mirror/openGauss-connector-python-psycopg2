"""Shared helpers for document update integration tests."""

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


def create_update_client():
    db_config = load_db_config()
    return OpenGauss(
        hosts=[{"host": db_config['host'], "port": db_config['port']}],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )


def update_mapping(include_tags=False):
    properties = {
        "title": {"type": "text"},
        "content": {"type": "text"},
        "category": {"type": "keyword"},
        "views": {"type": "integer"}
    }
    if include_tags:
        properties["tags"] = {"type": "keyword"}

    return {
        "mappings": {
            "properties": properties
        }
    }


def create_index_if_missing(client, index_name, mapping):
    try:
        client.indices.create(index=index_name, body=mapping)
    except Exception as e:
        if "already exists" not in str(e):
            raise


def cleanup_index_and_assert_no_leaks(client, index_name):
    try:
        client.indices.delete(index=index_name)
    finally:
        leak_message = _connection_pool_leak_message(client)
        client.close()
        if leak_message:
            raise AssertionError(leak_message)


def assert_partial_update(testcase, client, index_name, original_doc, partial_update, expected_source):
    client.create(index=index_name, id="doc1", body=original_doc)

    result = client.update(index=index_name, id="doc1", body=partial_update)
    testcase.assertIsNotNone(result)

    source = client.get(index=index_name, id="doc1")['_source']
    for field_name, expected_value in expected_source.items():
        testcase.assertEqual(source[field_name], expected_value)


def _connection_pool_leak_message(client):
    if not hasattr(client.connection, '_pool') or not client.connection._pool:
        return ""

    pool_status = client.connection._pool.get_pool_status()
    used_connections = pool_status.get('used_connections', 0)
    if used_connections == 0:
        return ""

    return f"tearDownClass 后仍有 {used_connections} 个连接未归还: {pool_status}"
