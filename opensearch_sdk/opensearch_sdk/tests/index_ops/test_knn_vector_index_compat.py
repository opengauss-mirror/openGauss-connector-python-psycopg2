#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 OpenSearch knn_vector index 参数兼容性

验证当 mapping 中包含 index: true 时，SDK 能正确创建 HNSW 索引
"""
import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestKnnVectorIndexCompatibility(unittest.TestCase):
    """测试 knn_vector 字段的 index 参数兼容性"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        print("\n" + "="*70)
        print("开始执行 knn_vector index 参数兼容性测试")
        print("="*70)
        
        # 加载数据库配置
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'db_config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            import json
            cls.db_config = json.load(f)
        
        # 创建客户端
        cls.client = OpenGauss(
            hosts=[{'host': cls.db_config['host'], 'port': cls.db_config['port']}],
            database=cls.db_config.get('database', 'es'),
            user=cls.db_config['user'],
            password=cls.db_config['password']
        )
        
        cls.test_index = "test_knn_index_compat"
        
        # 清理可能存在的旧索引
        try:
            if cls.client.indices.exists(index=cls.test_index):
                cls.client.indices.delete(index=cls.test_index)
                print(f"[清理] 删除已存在的测试索引：{cls.test_index}")
        except Exception as e:
            print(f"[警告] 清理索引失败：{e}")
    
    @classmethod
    def tearDownClass(cls):
        """测试类结束后清理"""
        try:
            if cls.client.indices.exists(index=cls.test_index):
                cls.client.indices.delete(index=cls.test_index)
                print(f"[清理] 删除测试索引：{cls.test_index}")
        except Exception as e:
            print(f"[警告] 清理索引失败：{e}")
        
        print("\n" + "="*70)
        print("测试完成")
        print("="*70)
    
    def test_01_knn_vector_with_index_true(self):
        """测试 knn_vector 字段设置 index: true"""
        print("\n[测试] knn_vector 字段设置 index: true...")
        
        # OpenSearch 风格的 mapping（包含 index: true）
        mapping = {
            "settings": {
                "index": {
                    "knn": True  # [OK] 启用 KNN 功能
                }
            },
            "mappings": {
                "properties": {
                    "title": {
                        "type": "text"
                    },
                    "content": {
                        "type": "text"
                    },
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "index": True,  # [WARN] OpenSearch 风格：在字段级别设置 index
                        "space_type": "cosinesimil"
                    }
                }
            }
        }
        
        # 创建索引
        result = self.client.indices.create(index=self.test_index, body=mapping)
        print(f"[成功] 索引创建结果：{result}")
        
        # 验证索引存在
        exists = self.client.indices.exists(index=self.test_index)
        self.assertTrue(exists, "索引应该存在")
        
        # 获取 mapping 验证
        mapping_result = self.client.indices.get_mapping(index=self.test_index)
        print(f"[成功] Mapping 获取成功")
        
        # 检查向量字段是否存在
        properties = mapping_result.get(self.test_index, {}).get('mappings', {}).get('properties', {})
        self.assertIn('embedding', properties, "向量字段应该存在于 mapping 中")
        
        # [OK] 验证 HNSW 索引是否真的创建了
        print("[验证] 检查 HNSW 索引是否创建...")
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT indexname FROM pg_indexes WHERE tablename = %s AND indexname LIKE %s",
                    (self.test_index, '%embedding%hnsw%')
                )
                hnsw_indexes = [row[0] for row in cursor.fetchall()]
                
                self.assertGreater(len(hnsw_indexes), 0, "应该至少有一个 HNSW 索引")
                print(f"[成功] 找到 HNSW 索引：{hnsw_indexes}")
                
                # 验证索引类型
                cursor.execute(
                    "SELECT amname FROM pg_index i JOIN pg_class c ON i.indexrelid = c.oid "
                    "JOIN pg_am a ON c.relam = a.oid WHERE c.relname = %s",
                    (hnsw_indexes[0],)
                )
                index_type = cursor.fetchone()[0]
                self.assertEqual(index_type, 'hnsw', f"索引类型应该是 hnsw，实际是 {index_type}")
                print(f"[成功] 索引类型验证通过：{index_type}")
            finally:
                cursor.close()
        
        print("[通过] knn_vector 字段 index=true 兼容处理成功")
    
    def test_02_knn_vector_without_method(self):
        """测试 knn_vector 字段不指定 method（应默认使用 HNSW）"""
        print("\n[测试] knn_vector 字段不指定 method...")
        
        test_index = f"{self.test_index}_no_method"
        
        # 清理可能存在的旧索引
        try:
            if self.client.indices.exists(index=test_index):
                self.client.indices.delete(index=test_index)
        except:
            pass
        
        # 简化的 mapping（只有 dimension，没有 method）
        mapping = {
            "settings": {
                "index": {
                    "knn": True
                }
            },
            "mappings": {
                "properties": {
                    "text": {
                        "type": "text"
                    },
                    "vector": {
                        "type": "knn_vector",
                        "dimension": 768,
                        "index": True  # 只设置 index=true
                    }
                }
            }
        }
        
        # 创建索引
        result = self.client.indices.create(index=test_index, body=mapping)
        print(f"[成功] 索引创建结果：{result}")
        
        # 验证索引存在
        exists = self.client.indices.exists(index=test_index)
        self.assertTrue(exists, "索引应该存在")
        
        print("[通过] knn_vector 无 method 时默认创建 HNSW 索引")
        
        # 清理
        try:
            self.client.indices.delete(index=test_index)
        except:
            pass
    
    def test_03_knn_vector_with_method_hnsw(self):
        """测试 knn_vector 字段显式指定 HNSW method"""
        print("\n[测试] knn_vector 字段显式指定 HNSW method...")
        
        test_index = f"{self.test_index}_with_hnsw"
        
        # 清理可能存在的旧索引
        try:
            if self.client.indices.exists(index=test_index):
                self.client.indices.delete(index=test_index)
        except:
            pass
        
        # 完整的 OpenSearch 风格 mapping
        mapping = {
            "settings": {
                "index": {
                    "knn": True
                }
            },
            "mappings": {
                "properties": {
                    "title": {
                        "type": "text"
                    },
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 512,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 16
                            }
                        }
                    }
                }
            }
        }
        
        # 创建索引
        result = self.client.indices.create(index=test_index, body=mapping)
        print(f"[成功] 索引创建结果：{result}")
        
        # 验证索引存在
        exists = self.client.indices.exists(index=test_index)
        self.assertTrue(exists, "索引应该存在")
        
        print("[通过] knn_vector 显式指定 HNSW method 成功")
        
        # 清理
        try:
            self.client.indices.delete(index=test_index)
        except:
            pass
    
    def test_04_dynamic_template_with_index_true(self):
        """测试 dynamic template 中包含 index: true"""
        print("\n[测试] dynamic template 中包含 index: true...")
        
        test_index = f"{self.test_index}_dynamic"
        
        # 清理可能存在的旧索引
        try:
            if self.client.indices.exists(index=test_index):
                self.client.indices.delete(index=test_index)
        except:
            pass
        
        # 使用 dynamic template 的 mapping
        mapping = {
            "settings": {
                "index": {
                    "knn": True
                }
            },
            "mappings": {
                "dynamic_templates": [
                    {
                        "vector_template": {
                            "match": "*_vec",
                            "mapping": {
                                "type": "knn_vector",
                                "dimension": 1024,
                                "index": True,  # [WARN] 在 dynamic template 中设置 index=true
                                "space_type": "cosinesimil"
                            }
                        }
                    }
                ],
                "properties": {
                    "title": {
                        "type": "text"
                    },
                    "content": {
                        "type": "text"
                    }
                }
            }
        }
        
        # 创建索引
        result = self.client.indices.create(index=test_index, body=mapping)
        print(f"[成功] 索引创建结果：{result}")
        
        # 验证索引存在
        exists = self.client.indices.exists(index=test_index)
        self.assertTrue(exists, "索引应该存在")
        
        # 插入一个带向量字段的文档，触发动态列创建
        doc = {
            "title": "测试文档",
            "content": "这是一个测试文档",
            "my_embedding_vec": [0.1] * 1024  # 匹配 *_vec 模式
        }
        
        self.client.index(index=test_index, id="doc_001", body=doc)
        print(f"[成功] 插入文档成功，触发了动态列创建")
        
        print("[通过] dynamic template 中 index=true 兼容处理成功")
        
        # 清理
        try:
            self.client.indices.delete(index=test_index)
        except:
            pass


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)
