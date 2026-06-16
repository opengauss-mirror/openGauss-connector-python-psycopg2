#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""调试测试失败原因"""

import json
from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss

# 加载配置
config = load_db_config()

client = OpenGauss(
    hosts=[{'host': config['host'], 'port': config['port']}],
    database=config['database'],
    user=config['user'],
    password=config['password']
)

TEST_INDEX = 'test_bool_refactor_integration'

try:
    # 测试 1: 严格 match_phrase
    print("="*60)
    print("测试 1: must + match_phrase 'quick fox'")
    print("="*60)
    query1 = {
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"title": "quick fox"}}
                ]
            }
        }
    }
    result1 = client.search(TEST_INDEX, query1)
    print(f"结果数：{result1['hits']['total']['value']}")
    for hit in result1['hits']['hits']:
        print(f"  ID: {hit['_id']}, Title: {hit['_source']['title']}")
    
    print("\n预期：只返回 ID=1 (the quick fox jumps)")
    print("实际数据:")
    for i in range(1, 6):
        try:
            doc = client.get(TEST_INDEX, str(i))
            print(f"  ID{i}: {doc['_source']['title']}")
        except:
            pass
    
    # 测试 2: slop=1
    print("\n" + "="*60)
    print("测试 2: must + match_phrase 'quick fox' slop=1")
    print("="*60)
    query2 = {
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"title": {"query": "quick fox", "slop": 1}}}
                ]
            }
        }
    }
    result2 = client.search(TEST_INDEX, query2)
    print(f"结果数：{result2['hits']['total']['value']}")
    for hit in result2['hits']['hits']:
        print(f"  ID: {hit['_id']}, Title: {hit['_source']['title']}")
    
    print("\n预期：返?ID=1,2 (间隔<=1)")
    
except Exception as e:
    print(f"错误：{e}")
    import traceback
    traceback.print_exc()
finally:
    client.close()
