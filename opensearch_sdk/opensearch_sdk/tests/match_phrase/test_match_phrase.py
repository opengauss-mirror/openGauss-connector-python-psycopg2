#!/usr/bin/env python
# -*-coding: utf-8 -*-
"""
Match Phrase 查询测试 - 基本功能

功能说明：
- 测试 match_phrase 查询功能
- 验证方案 C 的实现
- 测试短语匹配的准确性

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.match_phrase.test_match_phrase -v
    python opensearch_sdk/tests/match_phrase/test_match_phrase.py
"""
import sys
import os
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


def test_match_phrase_implementation():
    """测试 match_phrase 查询的实现"""
    
    print("=" * 80)
    print("match_phrase 查询功能测试（方案 C）")
    print("=" * 80)
    
    db_config = load_db_config()
    
    client = OpenGauss(
        hosts=[{'host': db_config['host'], 'port': db_config['port']}],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    test_index = 'test_match_phrase_impl'
    
    try:
        # 1. 清理并创建索引
        try:
            client.delete_index(test_index)
        except:
            pass
        
        mapping = {
            "mappings": {
                "properties": {
                    "categories": {
                        "type": "text",
                        "index": True
                    },
                    "content": {
                        "type": "text",
                        "index": True
                    }
                }
            }
        }
        
        print("\n[步骤 1] 创建索引和 BM25 索引")
        client.create_index(test_index, mapping)
        print("[OK] 索引创建成功")
        
        # 2. 插入测试数据
        print("\n[步骤 2] 插入测试数据")
        test_data = [
            {"categories": ["one", "two"], "content": "test question one"},
            {"categories": ["one", "three"], "content": "another question"},
            {"categories": ["two"], "content": "third item"},
        ]
        
        for i, doc in enumerate(test_data, 1):
            client.create(test_index, str(i), doc)
            print(f"  Document {i}: categories={doc['categories']}")
        
        # 3. 测试 match_phrase 查询
        print("\n[步骤 3] 测试 match_phrase 查询")
        
        # 测试 A: 查询 categories 包含 "one"
        print("\n--- 测试 A: match_phrase 查询 categories='one' ---")
        try:
            result = client.search(
                index=test_index,
                body={
                    "query": {
                        "match_phrase": {
                            "categories": "one"
                        }
                    },
                    "size": 10
                }
            )
            print(f"[OK] 查询成功：找到 {len(result['hits']['hits'])} 个文档")
            for hit in result['hits']['hits']:
                print(f"  - ID: {hit['_id']}, categories: {hit['_source']['categories']}")
        except Exception as e:
            print(f"[FAIL] 失败：{e}")
            import traceback
            traceback.print_exc()
        
        # 测试 B: 查询 content 包含 "test question"
        print("\n--- 测试 B: match_phrase 查询 content='test question' ---")
        try:
            result = client.search(
                index=test_index,
                body={
                    "query": {
                        "match_phrase": {
                            "content": "test question"
                        }
                    },
                    "size": 10
                }
            )
            print(f"[OK] 查询成功：找到 {len(result['hits']['hits'])} 个文档")
            for hit in result['hits']['hits']:
                print(f"  - ID: {hit['_id']}, content: {hit['_source']['content']}")
        except Exception as e:
            print(f"[FAIL] 失败：{e}")
            import traceback
            traceback.print_exc()
        
        # 4. 测试 bool 查询中的 match_phrase
        print("\n[步骤 4] 测试 bool 查询中的 match_phrase")
        
        print("\n--- 测试 C: bool.must 中的 match_phrase ---")
        try:
            result = client.search(
                index=test_index,
                body={
                    "query": {
                        "bool": {
                            "must": {
                                "match_phrase": {
                                    "categories": "one"
                                }
                            }
                        }
                    },
                    "size": 10
                }
            )
            print(f"[OK] 查询成功：找到 {len(result['hits']['hits'])} 个文档")
            for hit in result['hits']['hits']:
                print(f"  - ID: {hit['_id']}, categories: {hit['_source']['categories']}")
        except Exception as e:
            print(f"[FAIL] 失败：{e}")
            import traceback
            traceback.print_exc()
        
        print("\n--- 测试 D: bool.should 中的 match_phrase ---")
        try:
            result = client.search(
                index=test_index,
                body={
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "match_phrase": {
                                        "categories": "two"
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": 10
                }
            )
            print(f"[OK] 查询成功：找到 {len(result['hits']['hits'])} 个文档")
            for hit in result['hits']['hits']:
                print(f"  - ID: {hit['_id']}, categories: {hit['_source']['categories']}")
        except Exception as e:
            print(f"[FAIL] 失败：{e}")
            import traceback
            traceback.print_exc()
        
        # 5. 查看生成的 SQL（通过日志）
        print("\n[步骤 5] 验证 LIKE 查询行为")
        print("[INFO] 当前实现使用 LIKE 进行短语匹配")
        print("   生成的 SQL 类似：WHERE categories LIKE '%one%'")
        
        # 6. 性能提示
        print("\n" + "=" * 80)
        print("[WARN] 性能提示")
        print("=" * 80)
        print("• match_phrase 当前使用 LIKE 模糊匹配（无法利用 BM25 索引）")
        print("• 大数据量场景建议改用 keyword 类型 + terms 查询")
        print("• 详见 KNOWN_ISSUES.md 文档")
        
    except Exception as e:
        print(f"\n[FAIL] 测试失败：{e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        print("\n[清理]")
        try:
            client.delete_index(test_index)
            print("[OK] 测试索引已删除")
        except:
            pass
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)


if __name__ == '__main__':
    test_match_phrase_implementation()
