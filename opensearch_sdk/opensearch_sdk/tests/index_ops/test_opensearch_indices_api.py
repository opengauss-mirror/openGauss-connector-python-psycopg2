#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 OpenSearch 索引管理接口的兼容性

验证 SDK 是否支持以下 OpenSearch 标准接口：
1. indices.get_mapping() - 查看索引 mapping
2. indices.get_settings() - 查看索引 settings（需补充）
3. indices.stats() - 查看索引统计（需补充）
4. indices.exists() - 检查索引是否存在
"""

import json
import os
import sys
import unittest

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestIndicesAPICompatibility(unittest.TestCase):
    """测试索引管理 API 的 OpenSearch 兼容性"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备"""
        # 读取数据库配置 - 使用智能查找
        db_config = load_db_config()
        
        cls.client = OpenGauss(
            hosts=[{'host': db_config['host'], 'port': db_config['port']}],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        
        print("\n[INFO] 数据库连接成功")
        
        # 创建测试索引
        test_index = "test_articles"
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "author": {"type": "keyword"},
                    "publish_date": {"type": "date"},
                    "view_count": {"type": "integer"},
                    "is_published": {"type": "boolean"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 768,
                        "space_type": "cosinesimil",
                        "method": {
                            "name": "hnsw"
                        }
                    }
                }
            }
        }
        
        try:
            cls.client.indices.delete(test_index)
        except Exception:
            pass
        
        cls.client.indices.create(index=test_index, body=mapping)
        print(f"[INFO] 测试索引 '{test_index}' 创建成功")
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理"""
        try:
            cls.client.indices.delete("test_articles")
            print("[INFO] 测试环境清理完成")
        except Exception as e:
            print(f"[WARN] 清理失败：{e}")
    
    def test_exists(self):
        """测试 indices.exists() - 检查索引是否存在"""
        print("\n[Test] 测试 indices.exists()...")
        
        # 测试存在的索引
        exists = self.client.indices.exists(index="test_articles")
        self.assertTrue(exists, "应该检测到索引存在")
        print(f"[OK] 索引存在检查：{exists}")
        
        # 测试不存在的索引
        not_exists = self.client.indices.exists(index="nonexistent_index")
        self.assertFalse(not_exists, "应该检测到索引不存在")
        print(f"[OK] 索引不存在检查：{not_exists}")
    
    def test_get_mapping(self):
        """测试 indices.get_mapping() - 查看索引 mapping"""
        print("\n[Test] 测试 indices.get_mapping()...")
        
        mapping = self.client.indices.get_mapping(index="test_articles")
        print(f"[OK] Mapping: {json.dumps(mapping, indent=2, ensure_ascii=False)}")
        
        # 验证映射结构
        self.assertIn("test_articles", mapping, "应该包含索引名")
        self.assertIn("mappings", mapping["test_articles"], "应该包含 mappings")
        self.assertIn("properties", mapping["test_articles"]["mappings"], "应该包含 properties")
        
        # 验证字段类型
        props = mapping["test_articles"]["mappings"]["properties"]
        self.assertEqual(props["title"]["type"], "text", "title 应该是 text 类型")
        self.assertEqual(props["author"]["type"], "keyword", "author 应该是 keyword 类型")
        self.assertEqual(props["view_count"]["type"], "long", "view_count 应该是 long 类型")
        self.assertEqual(props["publish_date"]["type"], "date", "publish_date 应该是 date 类型")
        self.assertEqual(props["is_published"]["type"], "boolean", "is_published 应该是 boolean 类型")
        self.assertIn(props["embedding"]["type"], ["dense_vector", "knn_vector"], "embedding 应该是向量类型")
        
        print("[OK] Mapping 验证通过")
    
    def test_get(self):
        """测试 indices.get() - 获取索引信息（包含 mapping）"""
        print("\n[Test] 测试 indices.get()...")
        
        index_info = self.client.indices.get(index="test_articles")
        print(f"[OK] Index Info: {json.dumps(index_info, indent=2, ensure_ascii=False)}")
        
        # get() 和 get_mapping() 应该返回相似的结构
        self.assertIn("test_articles", index_info)
        
        print("[OK] 索引信息获取成功")
    
    def test_get_settings(self):
        """测试 indices.get_settings() - 查看索引 settings"""
        print("\n[Test] 测试 indices.get_settings()...")
        
        settings = self.client.indices.get_settings(index="test_articles")
        print(f"[OK] Settings: {json.dumps(settings, indent=2, ensure_ascii=False)}")
        
        # 验证设置结构
        self.assertIn("test_articles", settings, "应该包含索引名")
        self.assertIn("settings", settings["test_articles"], "应该包含 settings")
        self.assertIn("index", settings["test_articles"]["settings"], "应该包含 index")
        
        index_settings = settings["test_articles"]["settings"]["index"]
        self.assertEqual(index_settings["provided_name"], "test_articles", "索引名应该匹配")
        
        print("[OK] Settings 验证通过")
    
    def test_stats(self):
        """测试 indices.stats() - 查看索引统计"""
        print("\n[Test] 测试 indices.stats()...")
        
        stats = self.client.indices.stats(index="test_articles")
        print(f"[OK] Stats: {json.dumps(stats, indent=2, ensure_ascii=False)}")
        
        # 验证统计结构
        self.assertIn("_shards", stats, "应该包含 _shards")
        self.assertIn("indices", stats, "应该包含 indices")
        self.assertIn("test_articles", stats["indices"], "应该包含索引名")
        
        # 验证分片信息
        self.assertEqual(stats["_shards"]["total"], 1, "总分数应该是 1")
        self.assertEqual(stats["_shards"]["successful"], 1, "成功分片应该是 1")
        self.assertEqual(stats["_shards"]["failed"], 0, "失败分片应该是 0")
        
        # 验证文档计数
        index_stats = stats["indices"]["test_articles"]
        doc_count = index_stats["primaries"]["docs"]["count"]
        self.assertIsInstance(doc_count, int, "文档数应该是整数")
        self.assertGreaterEqual(doc_count, 0, "文档数应该大于等于 0")
        
        # 验证存储大小
        store_size = index_stats["primaries"]["store"]["size_in_bytes"]
        self.assertIsInstance(store_size, int, "存储大小应该是整数")
        self.assertGreaterEqual(store_size, 0, "存储大小应该大于等于 0")
        
        print(f"[OK] 统计信息验证通过（文档数：{doc_count}, 存储：{store_size} bytes）")
    
    def test_delete_and_recreate(self):
        """测试索引删除和重新创建"""
        print("\n[Test] 测试索引删除和重新创建...")
        
        # 创建临时索引
        temp_index = "test_articles_temp"
        simple_mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"}
                }
            }
        }
        
        create_response = self.client.indices.create(index=temp_index, body=simple_mapping)
        self.assertTrue(create_response.get("acknowledged"), "应该成功创建索引")
        print(f"[OK] 创建响应：{create_response}")
        
        # 验证索引存在
        exists = self.client.indices.exists(index=temp_index)
        self.assertTrue(exists, "索引应该存在")
        print(f"[OK] 索引存在验证：{exists}")
        
        # 删除索引
        delete_response = self.client.indices.delete(index=temp_index)
        self.assertTrue(delete_response.get("acknowledged"), "应该成功删除索引")
        print(f"[OK] 删除响应：{delete_response}")
        
        # 验证索引不存在
        not_exists = self.client.indices.exists(index=temp_index)
        self.assertFalse(not_exists, "索引应该不存在")
        print(f"[OK] 索引不存在验证：{not_exists}")


if __name__ == "__main__":
    print("="*80)
    print("OpenSearch 索引管理接口兼容性测试")
    print("="*80)
    
    # 运行测试
    unittest.main(verbosity=2)
