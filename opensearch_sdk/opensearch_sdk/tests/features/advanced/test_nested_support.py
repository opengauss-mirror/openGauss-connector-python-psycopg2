"""
Nested 类型支持测试（首值策略）

测试场景：
1. Mapping 验证：nested 类型的合法性校验
2. 索引创建：nested 字段展开为扁平列
3. 文档写入：支持数组和字典两种格式
4. 查询功能：nested 语法转换为扁平字段查询
5. Known Issue：多值数组只存首值的验证

设计决策说明：
- 采用首值策略：nested 数组只保留第一个对象
- 支持双格式输入：数组格式 [{}] 和字典格式 {}
- 适用场景：单一主要对象（一对一关系）
- 不适用场景：一对多关系（如多作者、多标签）
"""

import json
import unittest
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from opensearch_sdk import OpenGauss
from opensearch_sdk.client.indices import validate_mapping_schema
from opensearch_sdk.tests.utils.config_loader import load_db_config


class TestNestedSupport(unittest.TestCase):
    """Nested 类型支持测试套件"""

    @classmethod
    def setUpClass(cls):
        """设置测试环境（只执行一次）"""
        # 加载数据库配置
        db_config = load_db_config()
        print(f"\n连接数据库：{db_config['database']}@{db_config['host']}:{db_config['port']}")

        cls.client = OpenGauss(
            hosts=[{
                "host": db_config['host'],
                "port": db_config['port']
            }],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        print("Connection successful")

        cls.test_index = 'test_nested_support'

    def _create_bm25_index_with_conn(self, conn, field_name):
        """使用已有连接创建 BM25 索引"""
        from opensearch_sdk.retrieval import IndexConfig, IndexType
        with conn.cursor() as cursor:
            drop_sql = f"DROP INDEX IF EXISTS idx_{field_name}_bm25"
            cursor.execute(drop_sql)
            index_config = IndexConfig(
                name=f"idx_{field_name}_bm25",
                column=field_name,
                index_type=IndexType.BM25,
                parallel_workers=4
            )
            pre_sql = index_config.get_pre_create_sql(self.test_index)
            if pre_sql:
                cursor.execute(pre_sql)
            sql = index_config.to_sql(self.test_index)
            cursor.execute(sql)
            print(f"[SETUP] 创建 BM25 索引：{field_name}")

    def _create_bm25_index(self, field_name):
        """为指定字段创建 BM25 索引（提取为独立方法以降低嵌套深度）"""
        try:
            with self.client.connection.get_connection_for_operation() as conn:
                self._create_bm25_index_with_conn(conn, field_name)
        except Exception as e:
            print(f"[WARN] 创建 {field_name} BM25 索引失败：{e}")

    def setUp(self):
        """每个测试前创建索引"""
        self.mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "author": {
                        "type": "nested",
                        "properties": {
                            "name": {"type": "keyword"},
                            "email": {"type": "keyword"},
                            "age": {"type": "integer"}
                        }
                    },
                    "tags": {"type": "keyword"}
                }
            }
        }

        # 创建索引
        try:
            result = self.client.indices.create(
                index=self.test_index,
                body=self.mapping
            )
            print(f"[SETUP] 索引创建成功：{self.test_index}")
        except Exception as e:
            # 如果已存在，先删除
            self.client.indices.delete(self.test_index)
            result = self.client.indices.create(
                index=self.test_index,
                body=self.mapping
            )
        # 为 title 和 nested 字段创建 BM25 索引
        self._create_bm25_index("title")
        for field in ['author_name', 'author_email']:
            self._create_bm25_index(field)

    def tearDown(self):
        """每个测试后清理索引"""
        # [OK] 清理所有可能创建的测试索引
        test_indices = [
            self.test_index,  # test_nested_support
            'test_nested_create',  # test_03 使用的独立索引
        ]

        for index_name in test_indices:
            try:
                self.client.indices.delete(index_name)
                print(f"[TEARDOWN] 索引已清理：{index_name}")
            except Exception:
                pass

    def test_01_nested_mapping_validation(self):
        """测试 nested mapping 验证（合法场景）"""
        # 合法的 nested mapping
        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "author": {
                        "type": "nested",
                        "properties": {
                            "name": {"type": "keyword"},
                            "email": {"type": "keyword"}
                        }
                    }
                }
            }
        }

        # 应该不抛出异常
        validate_mapping_schema(mapping)
        print("[OK] Nested mapping 验证通过")

    def test_02_nested_mapping_missing_properties(self):
        """测试 nested 缺少 properties 时报错"""
        mapping = {
            "mappings": {
                "properties": {
                    "author": {"type": "nested"}  # [FAIL] 缺少 properties
                }
            }
        }

        with self.assertRaises(ValueError) as context:
            validate_mapping_schema(mapping)

        self.assertIn("must contain 'properties'", str(context.exception))
        print("[OK] 正确捕获 missing properties 错误")

    def test_03_create_index_with_nested(self):
        """测试创建包含 nested 的索引"""
        # [OK] 使用独立的索引名，避免与 setUp 创建的索引冲突
        test_index = 'test_nested_create'

        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "author": {
                        "type": "nested",
                        "properties": {
                            "name": {"type": "keyword"},
                            "email": {"type": "keyword"},
                            "age": {"type": "integer"}
                        }
                    },
                    "tags": {"type": "keyword"}
                }
            }
        }

        # 创建索引
        result = self.client.indices.create(
            index=test_index,
            body=mapping
        )

        self.assertTrue(result.get('acknowledged'))
        print("[OK] 索引创建成功")

        # 验证表结构（通过 SQL 查询 information_schema）
        # [FIX] 使用新的连接管理模式
        with self.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (test_index,))

                columns = cursor.fetchall()
                column_names = [col[0] for col in columns]
            finally:
                cursor.close()

        # 验证展开后的列存在
        self.assertIn('author__name', column_names)
        self.assertIn('author__email', column_names)
        self.assertIn('author__age', column_names)
        print(f"[OK] 列验证通过：{column_names}")
        # [OK] 索引清理由 tearDown 统一处理

    def test_04_insert_nested_dict_format(self):
        """测试插入字典格式的 nested 文档"""
        doc = {
            "title": "Test Article - Dict Format",
            "author": {
                "name": "John Doe",
                "email": "john@example.com",
                "age": 30
            },
            "tags": ["tech", "python"]
        }

        # 插入文档
        result = self.client.index(
            index=self.test_index,
            id='dict_001',
            body=doc
        )

        self.assertIsNotNone(result)
        print("[OK] 字典格式 nested 插入成功")

        # 验证存储的数据
        retrieved = self.client.get(index=self.test_index, id='dict_001')
        source = retrieved['_source']

        # [OK] 验证 nested 对象被自动还原为嵌套结构
        self.assertIn('author', source)
        self.assertIsInstance(source['author'], list)
        self.assertEqual(len(source['author']), 1)  # 首值策略
        self.assertEqual(source['author'][0]['name'], 'John Doe')
        self.assertEqual(source['author'][0]['email'], 'john@example.com')
        self.assertEqual(source['author'][0]['age'], 30)

        print("[OK] 字典格式数据验证通过")

    def test_05_insert_nested_array_format(self):
        """测试插入数组格式的 nested 文档（单元素）"""
        doc = {
            "title": "Test Article - Array Format",
            "author": [
                {
                    "name": "Jane Smith",
                    "email": "jane@example.com",
                    "age": 28
                }
            ],
            "tags": ["science"]
        }

        # 插入文档
        result = self.client.index(
            index=self.test_index,
            id='array_001',
            body=doc
        )

        self.assertIsNotNone(result)
        print("[OK] 数组格式 nested 插入成功")

        # 验证存储的数据
        retrieved = self.client.get(index=self.test_index, id='array_001')
        source = retrieved['_source']

        # [OK] 验证 nested 对象被自动还原为嵌套结构
        self.assertIn('author', source)
        self.assertIsInstance(source['author'], list)
        self.assertEqual(len(source['author']), 1)  # 首值策略
        self.assertEqual(source['author'][0]['name'], 'Jane Smith')
        self.assertEqual(source['author'][0]['email'], 'jane@example.com')
        self.assertEqual(source['author'][0]['age'], 28)

        print("[OK] 数组格式数据验证通过")

    def test_06_nested_term_query(self):
        """测试 nested term 查询"""
        # 准备测试数据
        doc = {
            "title": "Query Test Article",
            "author": {
                "name": "Bob Wilson",
                "email": "bob@example.com"
            }
        }
        self.client.index(index=self.test_index, id='query_001', body=doc)

        # Nested 查询
        query = {
            "query": {
                "nested": {
                    "path": "author",
                    "query": {
                        "term": {"name": "Bob Wilson"}
                    }
                }
            }
        }

        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']

        # [OK] 应该找到文档，返回嵌套结构
        self.assertEqual(len(hits), 1)
        self.assertIn('author', hits[0]['_source'])
        self.assertIsInstance(hits[0]['_source']['author'], list)
        self.assertEqual(hits[0]['_source']['author'][0]['name'], 'Bob Wilson')

        print("[OK] Nested term 查询通过")

    def test_07_nested_match_phrase_query(self):
        """测试 nested match_phrase 查询"""
        # 先插入测试数据
        doc = {
            "title": "Phrase Query Test",
            "author": {
                "name": "Bob Wilson",
                "email": "bob@example.com"
            }
        }
        self.client.index(index=self.test_index, id='phrase_001', body=doc)

        # Nested match_phrase 查询
        query = {
            "query": {
                "nested": {
                    "path": "author",
                    "query": {
                        "match_phrase": {"name": {"query": "Bob Wilson"}}
                    }
                }
            }
        }

        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']

        # 应该找到文档
        self.assertGreater(len(hits), 0)

        print("[OK] Nested match_phrase 查询通过")

    def test_08_bool_with_nested(self):
        """测试 bool 查询包含 nested 子句"""
        # 先插入测试数据
        doc = {
            "title": "Bool Nested Test",
            "author": {
                "name": "Charlie Brown",
                "email": "charlie@example.com"
            }
        }
        self.client.index(index=self.test_index, id='bool_001', body=doc)

        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match": {"title": "Bool Nested Test"}},
                        {
                            "nested": {
                                "path": "author",
                                "query": {
                                    "term": {"email": "charlie@example.com"}  # [OK] 使用原始字段名
                                }
                            }
                        }
                    ]
                }
            }
        }

        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']

        # 应该找到文档
        self.assertGreater(len(hits), 0)

        print("[OK] Bool + Nested 组合查询通过")

    def test_09_known_issue_multi_value_array(self):
        """测试 Known Issue：多值 nested 数组只存首值"""
        doc = {
            "title": "Multi-Author Article",
            "author": [  # [OK] 使用单数 author，与 mapping 一致
                {"name": "First Author", "email": "first@example.com"},
                {"name": "Second Author", "email": "second@example.com"},  # [WARN] 会被丢弃
                {"name": "Third Author", "email": "third@example.com"}     # [WARN] 会被丢弃
            ]
        }

        # 插入文档
        result = self.client.index(
            index=self.test_index,
            id='multi_001',
            body=doc
        )

        self.assertIsNotNone(result)
        print("[OK] 多值 nested 数组插入成功（静默丢弃）")

        # 验证只存储了第一个作者
        retrieved = self.client.get(index=self.test_index, id='multi_001')
        source = retrieved['_source']

        # [OK] 验证 nested 对象被自动还原为嵌套结构（首值策略）
        self.assertIn('author', source)
        self.assertIsInstance(source['author'], list)
        self.assertEqual(len(source['author']), 1)  # 首值策略：只保留第一个
        self.assertEqual(source['author'][0]['name'], 'First Author')
        self.assertEqual(source['author'][0]['email'], 'first@example.com')

        print("[WARN] Known Issue 验证：多值 nested 数组只存储首值")
        print(f"       原始数据：3 个作者 → 存储结果：1 个作者 ({source['author'][0]['name']})")

    def test_10_empty_nested_array(self):
        """测试空 nested 数组的处理"""
        doc = {
            "title": "No Author Article",
            "author": []  # 空数组
        }

        # 插入文档（应该不抛异常）
        result = self.client.index(
            index=self.test_index,
            id='empty_001',
            body=doc
        )

        self.assertIsNotNone(result)
        print("[OK] 空 nested 数组插入成功")

        # 验证存储的数据（应该为 NULL）
        retrieved = self.client.get(index=self.test_index, id='empty_001')
        source = retrieved['_source']

        # 空数组应该导致 nested 字段为 NULL
        self.assertIsNone(source.get('author_name'))
        self.assertIsNone(source.get('author_email'))

        print("[OK] 空 nested 数组处理通过")


if __name__ == '__main__':
    unittest.main(verbosity=2)
