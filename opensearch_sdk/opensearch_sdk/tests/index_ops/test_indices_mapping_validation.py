"""
索引操作测试 - 索引映射验证

功能说明：
- 测试索引名称和字段名的验证规则
- 测试映射 schema 的验证逻辑
- 确保标识符符合数据库规范

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.index_ops.test_indices_mapping_validation -v
    python opensearch_sdk/tests/index_ops/test_indices_mapping_validation.py
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)

# 添加 tests 目录到 Python 路径，以便导入 utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 直接导入函数
from opensearch_sdk.client.indices import validate_mapping_schema as _validate_mapping_schema
from opensearch_sdk.client.utils import _validate_identifier


class TestMappingValidation(unittest.TestCase):
    
    def test_validate_identifier_valid_cases(self):
        """测试有效的标识符"""
        valid_identifiers = ['test', '_test', 'test123', 'Test_Field']
        for identifier in valid_identifiers:
            result = _validate_identifier(identifier)
            self.assertEqual(result, identifier)
    
    def test_validate_identifier_invalid_cases(self):
        """测试无效的标识符"""
        invalid_identifiers = ['', '123test', 'test-field', 'test.field', 'test field']
        for identifier in invalid_identifiers:
            with self.assertRaises(ValueError) as context:
                _validate_identifier(identifier)
            self.assertIn("Invalid database identifier", str(context.exception))
    
    def test_validate_mapping_schema_valid_full_mapping(self):
        """测试完整的有效mapping配置"""
        valid_mapping = {
            "mappings": {
                "properties": {
                    "categories": {
                        "type": "text",
                        "index": True
                    },
                    "question": {
                        "type": "keyword",
                        "index": True
                    },
                    "score": {
                        "type": "float"
                    },
                    "count": {
                        "type": "long"
                    },
                    "active": {
                        "type": "boolean"
                    },
                    "created_date": {
                        "type": "date"
                    },
                    "embedding": {
                        "type": "dense_vector",
                        "dims": 128
                    }
                }
            }
        }
        
        # 应该不抛出异常
        _validate_mapping_schema(valid_mapping)
    
    def test_validate_mapping_schema_missing_required_keys(self):
        """测试缺少必需键的情况"""
        # 缺少mappings
        with self.assertRaises(ValueError) as context:
            _validate_mapping_schema({})
        self.assertIn("Mapping must contain 'mappings' key", str(context.exception))
        
        # 缺少properties
        with self.assertRaises(ValueError) as context:
            _validate_mapping_schema({"mappings": {}})
        self.assertIn("Mapping must contain 'properties' key", str(context.exception))
        
        # properties为空
        with self.assertRaises(ValueError) as context:
            _validate_mapping_schema({"mappings": {"properties": {}}})
        self.assertIn("'properties' cannot be empty", str(context.exception))
    
    def test_validate_mapping_schema_invalid_field_definitions(self):
        """测试无效的字段定义"""
        # 字段配置不是字典
        invalid_mapping = {
            "mappings": {
                "properties": {
                    "test_field": "not_a_dict"
                }
            }
        }
        with self.assertRaises(ValueError) as context:
            _validate_mapping_schema(invalid_mapping)
        self.assertIn("configuration must be a dictionary", str(context.exception))
        
        # 缺少type字段
        invalid_mapping = {
            "mappings": {
                "properties": {
                    "test_field": {}
                }
            }
        }
        with self.assertRaises(ValueError) as context:
            _validate_mapping_schema(invalid_mapping)
        self.assertIn("must specify 'type'", str(context.exception))
        
        # type不是字符串
        invalid_mapping = {
            "mappings": {
                "properties": {
                    "test_field": {"type": 123}
                }
            }
        }
        with self.assertRaises(ValueError) as context:
            _validate_mapping_schema(invalid_mapping)
        self.assertIn("type must be a string", str(context.exception))
    
    def test_validate_mapping_schema_unsupported_field_types(self):
        """测试不支持的字段类型"""
        invalid_mapping = {
            "mappings": {
                "properties": {
                    "test_field": {"type": "unsupported_type"}
                }
            }
        }
        with self.assertRaises(ValueError) as context:
            _validate_mapping_schema(invalid_mapping)
        self.assertIn("unsupported type", str(context.exception))
        self.assertIn("supported types", str(context.exception).lower())
    
    def test_validate_mapping_schema_vector_field_validation(self):
        """测试向量字段的验证"""
        # 缺少dims参数
        invalid_mapping = {
            "mappings": {
                "properties": {
                    "embedding": {"type": "dense_vector"}
                }
            }
        }
        with self.assertRaises(ValueError) as context:
            _validate_mapping_schema(invalid_mapping)
        self.assertIn("must specify 'dims' or 'dimension'", str(context.exception))
        
        # 无效的dims值
        invalid_dims_values = [-1, 0, 10001, "not_a_number"]
        for dims in invalid_dims_values:
            invalid_mapping = {
                "mappings": {
                    "properties": {
                        "embedding": {"type": "dense_vector", "dims": dims}
                    }
                }
            }
            with self.assertRaises(ValueError) as context:
                _validate_mapping_schema(invalid_mapping)
            # 检查错误消息是否包含维度相关的验证信息
            error_msg = str(context.exception).lower()
            self.assertTrue(
                "dimension must be" in error_msg or "must specify" in error_msg,
                f"错误消息应包含维度验证信息，实际: {context.exception}"
            )
    
    def test_validate_mapping_schema_valid_index_attribute(self):
        """测试index属性的处理"""
        # index为True的情况
        mapping_with_index_true = {
            "mappings": {
                "properties": {
                    "indexed_field": {"type": "text", "index": True},
                    "non_indexed_field": {"type": "text", "index": False}
                }
            }
        }
        # 应该不抛出异常
        _validate_mapping_schema(mapping_with_index_true)
        
        # 缺少index属性（应该默认为True）
        mapping_without_index = {
            "mappings": {
                "properties": {
                    "test_field": {"type": "text"}
                }
            }
        }
        # 应该不抛出异常
        _validate_mapping_schema(mapping_without_index)


class TestIndicesClientIntegration(unittest.TestCase):
    """IndicesClient 真实数据库集成测试"""
    
    @classmethod
    def _drop_table(cls, conn, table_name):
        """删除单个旧表"""
        try:
            with conn.cursor() as drop_cursor:
                drop_cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
                conn.commit()
        except Exception:
            pass

    @classmethod
    def _drop_old_tables_with_conn(cls, conn):
        """使用已有连接查询并清理旧表"""
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE tablename LIKE 'test_indices_integration%'"
            )
            for table in cursor.fetchall():
                cls._drop_table(conn, table[0])

    @classmethod
    def _cleanup_old_tables(cls):
        """清理所有相关旧表"""
        try:
            with cls.client.connection.get_connection_for_operation() as conn:
                cls._drop_old_tables_with_conn(conn)
        except Exception:
            pass

    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        # 加载数据库配置
        from opensearch_sdk.tests.utils.config_loader import load_db_config
        db_config = load_db_config()
        
        # 创建真实的 Opensearch 客户端
        from opensearch_sdk import OpenGauss
        cls.client = OpenGauss(
            hosts=[{
                'host': db_config['host'],
                'port': db_config['port']
            }],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        cls.test_index = "test_indices_integration"
        
        # [OK] 清理所有相关旧表（使用 CASCADE 确保彻底删除）
        cls._cleanup_old_tables()
    
    @classmethod
    def tearDownClass(cls):
        """清理测试资源"""
        try:
            cls.client.indices.delete(cls.test_index)
            cls.client.close()
        except Exception:
            pass
    
    def test_create_method_calls_validation(self):
        """测试 create 方法调用 schema 验证"""
        test_index = self.test_index + "_validate"
        test_mapping = {
            "mappings": {
                "properties": {
                    "test_field": {"type": "text"}
                }
            }
        }
        
        # 执行 create 方法（应该成功创建）
        result = self.client.indices.create(index=test_index, body=test_mapping)
        
        # 验证创建成功
        self.assertTrue(result.get("acknowledged"))
        
        # 清理
        try:
            self.client.indices.delete(test_index)
        except Exception:
            pass
    
    def test_create_method_handles_index_attribute(self):
        """测试 create 方法正确处理 index 属性"""
        test_index = self.test_index + "_index_attr"
        test_mapping = {
            "mappings": {
                "properties": {
                    "indexed_text": {"type": "text", "index": True},
                    "indexed_keyword": {"type": "keyword", "index": True},
                    "non_indexed_field": {"type": "text", "index": False}
                }
            }
        }
        
        # 执行 create 方法（应该成功创建）
        result = self.client.indices.create(index=test_index, body=test_mapping)
        
        # 验证创建成功
        self.assertTrue(result.get("acknowledged"))
        
        # 验证索引存在
        self.assertTrue(self.client.indices.exists(test_index))
        
        # 插入测试数据验证可以正常写入
        test_doc = {
            "indexed_text": "test content",
            "indexed_keyword": "category1",
            "non_indexed_field": "some data"
        }
        doc_result = self.client.index(test_index, id="doc1", body=test_doc)
        self.assertIsNotNone(doc_result)
        
        # 查询验证
        retrieved = self.client.get(test_index, id="doc1")
        self.assertEqual(retrieved['_source']['indexed_keyword'], 'category1')


if __name__ == '__main__':
    unittest.main()
