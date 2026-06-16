#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
集成测试：验证字段名标准化后在数据库中的实际查询效果
"""
import unittest
import sys
import os
import warnings

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestFieldNameNormalizationIntegration(unittest.TestCase):
    """集成测试：字段名标准化后的实际查询验证"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 创建测试索引和数据"""
        print("\n" + "="*70)
        print("开始执行字段名标准化集成测试")
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
        
        # 创建测试索引（使用带点号的字段名）
        cls.test_index = "test_field_normalization"
        
        # 清理可能存在的旧索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except:
            pass
        
        # 创建索引 - 使用带点号的字段名（会被转换为下划线）
        mapping = {
            "mappings": {
                "properties": {
                    "user.name": {"type": "keyword"},      # → user_name
                    "user.age": {"type": "integer"},        # → user_age
                    "contact.email": {"type": "keyword"},   # → contact_email
                    "price.value": {"type": "float"},       # → price_value
                    "address.city": {"type": "keyword"}     # → address_city
                }
            }
        }
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # 忽略转换警告
            cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 插入测试数据 - 使用转换后的字段名（因为 Mapping 定义时已经转换）
        # 注意：虽然 Mapping 中定义的是 user.name，但实际数据库中是 user_name
        test_docs = [
            {
                "id": "doc1",
                "user_name": "Alice",              # 使用转换后的名称
                "user_age": 25,                     # 使用转换后的名称
                "contact_email": "alice@example.com",  # 使用转换后的名称
                "price_value": 99.99,               # 使用转换后的名称
                "address_city": "Beijing"           # 使用转换后的名称
            },
            {
                "id": "doc2",
                "user_name": "Bob",
                "user_age": 30,
                "contact_email": "bob@example.com",
                "price_value": 149.99,
                "address_city": "Shanghai"
            },
            {
                "id": "doc3",
                "user_name": "Charlie",
                "user_age": 35,
                "contact_email": "charlie@example.com",
                "price_value": 199.99,
                "address_city": "Guangzhou"
            }
        ]
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # 忽略转换警告
            for doc in test_docs:
                doc_id = doc.pop("id")
                cls.client.index(index=cls.test_index, id=doc_id, body=doc)
        
        print(f"[SETUP] 测试索引 '{cls.test_index}' 已创建并插入 {len(test_docs)} 条数据")
        print(f"[SETUP] 字段名映射：user.name → user_name, contact.email → contact_email, etc.")
    
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
    
    def test_01_search_with_dotted_field_names(self):
        """测试使用带点号的字段名进行查询"""
        print("\n[测试] 使用带点号的字段名查询...")
        
        # 使用带点号的字段名进行 term 查询
        query = {
            "query": {
                "term": {
                    "user.name": "Alice"  # 会被转换为 user_name
                }
            }
        }
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = self.client.search(index=self.test_index, body=query)
        
        # 验证查询成功
        self.assertIn("hits", result)
        self.assertEqual(len(result["hits"]["hits"]), 1)
        self.assertEqual(result["hits"]["hits"][0]["_source"]["user_name"], "Alice")
        
        print(f"[PASS] 查询成功：user.name='Alice' → 找到 1 条结果")
    
    def test_02_get_document_with_dotted_fields(self):
        """测试获取包含带点号字段名的文档"""
        print("\n[测试] 获取包含带点号字段名的文档...")
        
        result = self.client.get(index=self.test_index, id="doc1")
        
        # 验证文档获取成功，字段名已被转换
        self.assertIn("_source", result)
        source = result["_source"]
        
        # 注意：数据库中存储的是转换后的字段名
        self.assertIn("user_name", source)
        self.assertIn("contact_email", source)
        self.assertIn("price_value", source)
        
        self.assertEqual(source["user_name"], "Alice")
        self.assertEqual(source["contact_email"], "alice@example.com")
        self.assertEqual(source["price_value"], 99.99)
        
        print(f"[PASS] 文档获取成功，字段名已转换：")
        print(f"       user_name={source['user_name']}")
        print(f"       contact_email={source['contact_email']}")
    
    def test_03_sort_by_dotted_field(self):
        """测试按带点号的字段排序"""
        print("\n[测试] 按带点号的字段排序...")
        
        query = {
            "query": {"match_all": {}},
            "sort": [
                {"price.value": "asc"}  # 会被转换为 price_value
            ]
        }
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = self.client.search(index=self.test_index, body=query)
        
        # 验证排序成功
        self.assertEqual(len(result["hits"]["hits"]), 3)
        
        # 验证排序顺序（价格从低到高）
        prices = [hit["_source"]["price_value"] for hit in result["hits"]["hits"]]
        self.assertEqual(prices, [99.99, 149.99, 199.99])
        
        print(f"[PASS] 排序成功：price.value asc → {prices}")
    
    def test_04_update_document_with_dotted_fields(self):
        """测试更新包含带点号字段的文档"""
        print("\n[测试] 更新包含带点号字段的文档...")
        
        # 更新文档 - 使用带点号和连字符的字段名
        update_body = {
            "user.age": 26,           # 会被转换为 user_age
            "address-city": "Shenzhen"  # 会被转换为 address_city
        }
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.client.update(index=self.test_index, id="doc1", body=update_body)
        
        # 验证更新成功
        result = self.client.get(index=self.test_index, id="doc1")
        source = result["_source"]
        
        self.assertEqual(source["user_age"], 26)
        self.assertEqual(source["address_city"], "Shenzhen")
        
        print(f"[PASS] 文档更新成功：")
        print(f"       user_age={source['user_age']}")
        print(f"       address_city={source['address_city']}")
    
    def test_05_delete_by_field_with_dotted_name(self):
        """测试按带点号的字段值删除文档"""
        print("\n[测试] 按带点号的字段值删除文档...")
        
        # 先找到要删除的文档ID
        search_query = {
            "query": {
                "term": {
                    "user.name": "Charlie"  # 会被转换为 user_name
                }
            }
        }
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            search_result = self.client.search(index=self.test_index, body=search_query)
        
        # 验证找到了文档
        self.assertEqual(len(search_result["hits"]["hits"]), 1)
        doc_id = search_result["hits"]["hits"][0]["_id"]
        
        # 统计总数
        count_before = len(self.client.search(index=self.test_index, body={"query": {"match_all": {}}})["hits"]["hits"])
        
        # 直接通过 ID 删除（避免 BM25 索引问题）
        delete_result = self.client.delete(index=self.test_index, id=doc_id)
        
        # 验证删除成功
        self.assertEqual(delete_result["result"], "deleted")
        
        # 验证文档确实被删除
        count_after = len(self.client.search(index=self.test_index, body={"query": {"match_all": {}}})["hits"]["hits"])
        self.assertEqual(count_after, count_before - 1)
        
        print(f"[PASS] 删除成功：文档 '{doc_id}' 已被删除")
    
    def test_06_mapping_reflects_converted_names(self):
        """验证映射中反映的是转换后的字段名"""
        print("\n[测试] 验证映射中字段名已转换...")
        
        mapping = self.client.indices.get_mapping(index=self.test_index)
        properties = mapping[self.test_index]["mappings"]["properties"]
        
        # 验证字段名已被转换
        self.assertIn("user_name", properties)
        self.assertIn("user_age", properties)
        self.assertIn("contact_email", properties)
        self.assertIn("price_value", properties)
        self.assertIn("address_city", properties)
        
        # 验证原始带点号的字段名不存在
        self.assertNotIn("user.name", properties)
        self.assertNotIn("contact.email", properties)
        
        print(f"[PASS] 映射中字段名已转换：")
        print(f"       存在的字段：{list(properties.keys())}")
    
    def test_07_direct_sql_verification(self):
        """直接通过 SQL 验证数据库中的字段名"""
        print("\n[测试] 直接通过 SQL 验证数据库字段名...")
        
        # [FIX] 使用新的连接管理模式
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                # 查询表的列信息
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
                    (self.test_index,)
                )
                columns = [row[0] for row in cursor.fetchall()]
            finally:
                cursor.close()
        
        # 验证转换后的字段名存在
        self.assertIn("user_name", columns)
        self.assertIn("contact_email", columns)
        self.assertIn("price_value", columns)
        
        # 验证原始带点号的字段名不存在
        self.assertNotIn("user.name", columns)
        self.assertNotIn("contact.email", columns)
        
        print(f"[PASS] 数据库中字段名已转换：")
        print(f"       列名：{columns}")
    
    def test_08_insert_with_dotted_fields(self):
        """测试插入包含带点号字段的新文档"""
        print("\n[测试] 插入包含带点号字段的新文档...")
        
        new_doc = {
            "user.name": "David",
            "user-age": 28,
            "contact.email": "david@example.com",
            "price.value": 129.99,
            "address-city": "Hangzhou"
        }
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.client.index(index=self.test_index, id="doc4", body=new_doc)
        
        # 验证插入成功
        result = self.client.get(index=self.test_index, id="doc4")
        source = result["_source"]
        
        self.assertEqual(source["user_name"], "David")
        self.assertEqual(source["contact_email"], "david@example.com")
        
        print(f"[PASS] 新文档插入成功，字段名已转换")


if __name__ == "__main__":
    # 运行测试
    unittest.main(verbosity=2)
