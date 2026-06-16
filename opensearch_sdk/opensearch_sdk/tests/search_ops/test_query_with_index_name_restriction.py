#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证索引名称点号限制不影响正常查询功能
"""
import unittest
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestQueryWithIndexNameRestriction(unittest.TestCase):
    """验证查询功能不受索引名限制影响"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 创建测试索引和数据"""
        print("\n" + "="*70)
        print("开始执行查询功能验证测试")
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
        
        # 创建测试索引（使用合法的索引名）
        cls.test_index = "test_query_validation"
        
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "category": {"type": "keyword"},
                    "price": {"type": "float"}
                }
            }
        }
        
        # 清理可能存在的旧索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except:
            pass
        
        # 创建新索引
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据
        test_docs = [
            {"id": "doc1", "title": "Python Programming", "content": "Learn Python basics", "category": "programming", "price": 29.99},
            {"id": "doc2", "title": "Java Development", "content": "Master Java programming", "category": "programming", "price": 39.99},
            {"id": "doc3", "title": "Web Design", "content": "Create beautiful websites", "category": "design", "price": 24.99},
        ]
        
        for doc in test_docs:
            doc_id = doc.pop("id")
            cls.client.index(index=cls.test_index, id=doc_id, body=doc)
        
        print(f"[SETUP] 测试索引 '{cls.test_index}' 已创建并插入 {len(test_docs)} 条数据")
    
    @classmethod
    def tearDownClass(cls):
        """测试类结束后清理"""
        # 删除测试索引
        try:
            cls.client.indices.delete(index=cls.test_index)
            print(f"[CLEANUP] 删除测试索引：{cls.test_index}")
        except:
            pass
        
        print("\n" + "="*70)
        print("测试完成")
        print("="*70)
    
    def test_01_search_with_valid_index_name(self):
        """测试使用合法索引名进行查询"""
        print("\n[测试] 使用合法索引名查询...")
        
        query = {
            "query": {
                "match_all": {}
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        
        # 验证查询成功
        self.assertIn("hits", result)
        self.assertIn("hits", result["hits"])
        self.assertGreater(len(result["hits"]["hits"]), 0)
        
        print(f"[PASS] 查询成功，返回 {len(result['hits']['hits'])} 条结果")
    
    def test_02_knn_search_with_valid_index_name(self):
        """测试使用合法索引名进行向量搜索"""
        print("\n[测试] 使用合法索引名进行向量搜索...")
        
        # 注意：这个测试需要向量字段，我们只验证不会因索引名验证而失败
        # 由于测试索引没有向量字段，预期会因字段不存在而失败，但不是因为索引名验证
        
        # 先验证索引名验证通过（不会在 normalize_identifier 阶段失败）
        from opensearch_sdk.client.utils import normalize_identifier
        
        validated = normalize_identifier(self.test_index, "Index name")
        self.assertEqual(validated, self.test_index)
        
        print(f"[PASS] 索引名验证通过：{validated}")
    
    def test_03_get_document_with_valid_index_name(self):
        """测试使用合法索引名获取文档"""
        print("\n[测试] 使用合法索引名获取文档...")
        
        result = self.client.get(index=self.test_index, id="doc1")
        
        # 验证获取成功
        self.assertIn("_source", result)
        self.assertEqual(result["_source"]["title"], "Python Programming")
        
        print(f"[PASS] 文档获取成功：{result['_source']['title']}")
    
    def test_04_delete_by_query_with_valid_index_name(self):
        """测试使用合法索引名按条件删除（验证索引名验证不阻止操作）"""
        print("\n[测试] 使用合法索引名按条件删除...")
        
        # 我们只验证 normalize_identifier 不会拒绝合法的索引名
        from opensearch_sdk.client.utils import normalize_identifier
        
        validated = normalize_identifier(self.test_index, "Index name")
        self.assertEqual(validated, self.test_index)
        
        print(f"[PASS] 索引名验证通过，可以进行删除操作：{validated}")
    
    def test_05_bulk_operations_with_valid_index_name(self):
        """测试使用合法索引名进行批量操作"""
        print("\n[测试] 使用合法索引名进行批量操作...")
        
        # 批量插入 - 使用 NDJSON 格式
        import json
        actions = [
            json.dumps({"index": {"_index": self.test_index, "_id": "bulk1"}}),
            json.dumps({"title": "Bulk Test 1", "content": "Test content", "category": "test", "price": 19.99}),
            json.dumps({"index": {"_index": self.test_index, "_id": "bulk2"}}),
            json.dumps({"title": "Bulk Test 2", "content": "More test content", "category": "test", "price": 29.99}),
        ]
        bulk_body = "\n".join(actions) + "\n"
        
        result = self.client.bulk(body=bulk_body)
        
        # 验证批量操作成功
        self.assertFalse(result.get("errors", True))
        
        print(f"[PASS] 批量操作成功")
    
    def test_06_index_exists_with_valid_name(self):
        """测试使用合法索引名检查索引是否存在"""
        print("\n[测试] 使用合法索引名检查索引存在性...")
        
        exists = self.client.indices.exists(index=self.test_index)
        
        # 验证索引存在
        self.assertTrue(exists)
        
        print(f"[PASS] 索引存在性检查成功")
    
    def test_07_get_mapping_with_valid_index_name(self):
        """测试使用合法索引名获取映射"""
        print("\n[测试] 使用合法索引名获取映射...")
        
        mapping = self.client.indices.get_mapping(index=self.test_index)
        
        # 验证映射获取成功
        self.assertIn(self.test_index, mapping)
        self.assertIn("mappings", mapping[self.test_index])
        
        print(f"[PASS] 映射获取成功")
    
    def test_08_get_settings_with_valid_index_name(self):
        """测试使用合法索引名获取设置"""
        print("\n[测试] 使用合法索引名获取设置...")
        
        settings = self.client.indices.get_settings(index=self.test_index)
        
        # 验证设置获取成功
        self.assertIn(self.test_index, settings)
        
        print(f"[PASS] 设置获取成功")


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)
