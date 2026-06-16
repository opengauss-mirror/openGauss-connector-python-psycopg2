#!/usr/bin/env python
# -*-coding: utf-8 -*-
"""
BM25 搜索测试 - 文本测试

功能说明：
- 测试 BM25 索引的正确使用方式
- 验证 BM25 全文检索功能

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.bm25_search.test_bm25_text -v
    python opensearch_sdk/tests/bm25_search/test_bm25_text.py
"""
import os
import sys
import unittest
import json

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

db_config = load_db_config()

client = OpenGauss(
    hosts=[{'host': db_config['host'], 'port': db_config['port']}],
    database=db_config['database'],
    user=db_config['user'],
    password=db_config['password']
)

TEST_INDEX = "test_bm25_text"

try:
    # 1. 清理并创建新索引
    if client.indices.exists(index=TEST_INDEX):
        print(f"Deleting existing index: {TEST_INDEX}")
        client.delete_index(TEST_INDEX)
    
    # 2. 创建索引 - categories 作为 text 字段
    mapping = {
        "mappings": {
            "properties": {
                "categories": {
                    "type": "text",
                    "index": True
                },
                "title": {
                    "type": "text",
                    "index": True
                }
            }
        }
    }
    
    print(f"\nCreating index: {TEST_INDEX}")
    result = client.create_index(TEST_INDEX, mapping)
    print(f"Index created successfully")
    
    # 3. 插入测试数据 - 使用纯文本而非数组
    test_data_1 = {
        "categories": "one/two",  # 纯文本格式
        "title": "Test Article 1"
    }
    
    test_data_2 = {
        "categories": "three/four",  # 纯文本格式
        "title": "Test Article 2"
    }
    
    print(f"\nInserting test data (plain text format)...")
    client.index(TEST_INDEX, "doc1", test_data_1)
    client.index(TEST_INDEX, "doc2", test_data_2)
    print(f"Data inserted successfully")
    
    # 4. 查看实际存储的数据
    print("\nChecking actual stored data...")
    doc1 = client.get(TEST_INDEX, "doc1")
    doc2 = client.get(TEST_INDEX, "doc2")
    print(f"Document 1: {json.dumps(doc1['_source'], indent=2, ensure_ascii=False)}")
    print(f"Document 2: {json.dumps(doc2['_source'], indent=2, ensure_ascii=False)}")
    
    # 5. 测试 match_phrase 查询
    print("\nTesting match_phrase query (searching for 'one')...")
    search_body = {
        "query": {
            "match_phrase": {
                "categories": "one"
            }
        },
        "size": 10
    }
    
    try:
        result = client.search(TEST_INDEX, search_body)
        print(f"match_phrase query successful, found {len(result['hits']['hits'])} records")
        for hit in result['hits']['hits']:
            print(f"  - ID: {hit['_id']}, Score: {hit['_score']}, Categories: {hit['_source']['categories']}")
    except Exception as e:
        print(f"match_phrase query failed: {e}")
    
    # 6. 测试 BM25 评分排序
    print("\nTesting BM25 scoring sort...")
    search_body_score = {
        "query": {
            "match": {
                "categories": "one"
            }
        },
        "size": 10
    }
    
    try:
        result = client.search(TEST_INDEX, search_body_score)
        print(f"match query successful, found {len(result['hits']['hits'])} records")
        for hit in result['hits']['hits']:
            print(f"  - ID: {hit['_id']}, Score: {hit['_score']}, Categories: {hit['_source']['categories']}")
    except Exception as e:
        print(f"match query failed: {e}")
        
finally:
    # 清理测试索引
    try:
        if client.indices.exists(index=TEST_INDEX):
            print(f"\nCleaning up test index: {TEST_INDEX}")
            client.delete_index(TEST_INDEX)
    except Exception:
        pass
    
    client.close()
