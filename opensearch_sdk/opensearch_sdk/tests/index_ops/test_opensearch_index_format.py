#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 OpenSearch 标准索引创建格式

验证 opensearch_sdk 完全兼容 OpenSearch 的 knn_vector 索引定义格式
"""

import json
import os
import sys

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


def test_opensearch_standard_index_format():
    """测试 OpenSearch 标准的索引创建格式"""
    
    # 读取数据库配置
    db_config = load_db_config()
    
    # 创建客户端
    client = OpenGauss(
        hosts=[{'host': db_config['host'], 'port': db_config['port']}],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    
    print("\n" + "="*80)
    print("测试 1: OpenSearch 标准 knn_vector 索引格式（L2 距离）")
    print("="*80)
    
    # OpenSearch 官方文档的标准格式
    opensearch_mapping_l2 = {
        "settings": {
            "index": {
                "knn": True
            }
        },
        "mappings": {
            "properties": {
                "my_vector": {
                    "type": "knn_vector",
                    "dimension": 3,
                    "space_type": "l2",
                    "method": {
                        "name": "hnsw"
                    }
                },
                "title": {
                    "type": "text"
                },
                "category": {
                    "type": "keyword"
                }
            }
        }
    }
    
    index_name = "test_opensearch_l2"
    
    try:
        # 清理已有索引
        try:
            client.indices.delete(index_name)
            print(f"[OK] 删除已有索引：{index_name}")
        except Exception:
            pass
        
        # 创建索引（使用 OpenSearch 标准格式）
        print(f"\n创建索引：{index_name}")
        print("Mapping 配置:")
        print(json.dumps(opensearch_mapping_l2, indent=2, ensure_ascii=False))
        
        response = client.indices.create(index=index_name, body=opensearch_mapping_l2)
        print(f"\n[OK] 索引创建成功！")
        print(f"响应：{response}")
        
        # 验证索引是否存在
        exists = client.indices.exists(index_name)
        if exists:
            print(f"[OK] 索引验证存在：{index_name}")
        else:
            print(f"[FAIL] 索引验证失败：{index_name} 不存在")
            return False
        
        # 插入测试数据
        test_doc = {
            "my_vector": [1.0, 2.0, 3.0],
            "title": "Test Product",
            "category": "electronics"
        }
        
        doc_id = "doc1"
        client.index(index=index_name, id=doc_id, body=test_doc)
        print(f"[OK] 插入测试文档：{doc_id}")
        
        # 测试向量搜索
        print("\n测试向量搜索...")
        search_query = {
            "knn": {
                "my_vector": {
                    "vector": [1.0, 2.0, 3.0],
                    "k": 10
                }
            }
        }
        
        result = client.search(index=index_name, body=search_query)
        print(f"[OK] 向量搜索成功，返回 {len(result['hits']['hits'])} 个结果")
        
        # 清理索引
        client.indices.delete(index_name)
        print(f"[OK] 删除测试索引：{index_name}")
        
        print("\n[PASS] 测试 1 通过：OpenSearch L2 距离格式完全兼容")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] 测试 1 失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_opensearch_cosine_format():
    """测试 OpenSearch 标准的余弦相似度格式"""
    
    # 读取数据库配置
    db_config = load_db_config()
    
    client = OpenGauss(
        hosts=[{'host': db_config['host'], 'port': db_config['port']}],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    
    print("\n" + "="*80)
    print("测试 2: OpenSearch 标准 knn_vector 索引格式（余弦相似度）")
    print("="*80)
    
    # OpenSearch 余弦相似度标准格式
    opensearch_mapping_cosine = {
        "mappings": {
            "properties": {
                "title_vector": {
                    "type": "knn_vector",
                    "dimension": 768,
                    "space_type": "cosinesimil",
                    "method": {
                        "name": "hnsw",
                        "parameters": {
                            "m": 16,
                            "ef_construction": 64
                        }
                    }
                },
                "title": {"type": "text"}
            }
        }
    }
    
    index_name = "test_opensearch_cosine"
    
    try:
        # 清理已有索引
        try:
            client.indices.delete(index_name)
        except Exception:
            pass
        
        print(f"\n创建索引：{index_name}")
        print("Mapping 配置:")
        print(json.dumps(opensearch_mapping_cosine, indent=2, ensure_ascii=False))
        
        response = client.indices.create(index=index_name, body=opensearch_mapping_cosine)
        print(f"\n[OK] 索引创建成功！")
        
        # 插入测试文档
        import random
        test_vector = [random.random() for _ in range(768)]
        test_doc = {
            "title_vector": test_vector,
            "title": "Machine Learning Article"
        }
        
        client.index(index=index_name, id="article1", body=test_doc)
        print(f"[OK] 插入测试文档")
        
        # 测试搜索
        query_vector = [random.random() for _ in range(768)]
        search_query = {
            "knn": {
                "title_vector": {
                    "vector": query_vector,
                    "k": 10
                }
            }
        }
        
        result = client.search(index=index_name, body=search_query)
        print(f"[OK] 向量搜索成功，返回 {len(result['hits']['hits'])} 个结果")
        
        # 清理
        client.indices.delete(index_name)
        print(f"[OK] 删除测试索引：{index_name}")
        
        print("\n[PASS] 测试 2 通过：OpenSearch 余弦相似度格式完全兼容")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] 测试 2 失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_backward_compatibility():
    """测试向后兼容性（旧的 dense_vector 格式）"""
    
    # 读取数据库配置
    db_config = load_db_config()
    
    client = OpenGauss(
        hosts=[{'host': db_config['host'], 'port': db_config['port']}],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    
    print("\n" + "="*80)
    print("测试 3: 向后兼容性测试（dense_vector 格式）")
    print("="*80)
    
    # 旧的 Opensearch 风格格式
    old_style_mapping = {
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "dense_vector",
                    "dims": 128,
                    "similarity": "cosine",
                    "index_options": {
                        "m": 16,
                        "ef_construction": 64
                    }
                },
                "content": {"type": "text"}
            }
        }
    }
    
    index_name = "test_dense_vector_compat"
    
    try:
        # 清理
        try:
            client.indices.delete(index_name)
        except Exception:
            pass
        
        print(f"\n创建索引：{index_name}")
        print("Mapping 配置 (旧格式):")
        print(json.dumps(old_style_mapping, indent=2, ensure_ascii=False))
        
        response = client.indices.create(index=index_name, body=old_style_mapping)
        print(f"\n[OK] 索引创建成功（向后兼容）！")
        
        # 简单验证
        test_vector = [0.1] * 128
        test_doc = {
            "embedding": test_vector,
            "content": "Test content"
        }
        
        client.index(index=index_name, id="test1", body=test_doc)
        print(f"[OK] 插入测试文档")
        
        # 清理
        client.indices.delete(index_name)
        print(f"[OK] 删除测试索引：{index_name}")
        
        print("\n[PASS] 测试 3 通过：向后兼容性完好")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] 测试 3 失败：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "="*80)
    print("OpenSearch 标准索引格式兼容性测试套件")
    print("="*80)
    
    results = []
    
    # 运行所有测试
    results.append(("OpenSearch L2 格式", test_opensearch_standard_index_format()))
    results.append(("OpenSearch 余弦格式", test_opensearch_cosine_format()))
    results.append(("向后兼容性", test_backward_compatibility()))
    
    # 打印汇总报告
    print("\n" + "="*80)
    print("测试汇总报告")
    print("="*80)
    
    for test_name, passed in results:
        status = "[PASS] 通过" if passed else "[FAIL] 失败"
        print(f"{status} - {test_name}")
    
    total_passed = sum(1 for _, p in results if p)
    total_tests = len(results)
    
    print(f"\n总计：{total_passed}/{total_tests} 测试通过")
    
    if total_passed == total_tests:
        print("\n[SUCCESS] 所有测试通过！OpenSearch 格式完全兼容！")
        sys.exit(0)
    else:
        print(f"\n[WARN] {total_tests - total_passed} 个测试失败")
        sys.exit(1)
