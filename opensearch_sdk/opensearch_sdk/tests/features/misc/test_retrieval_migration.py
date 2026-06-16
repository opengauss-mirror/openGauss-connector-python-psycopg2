"""
检索迁移测试 - 模块导入和类型实例化

功能说明：
- 测试检索功能的迁移
- 验证所有模块的导入
- 确保向后兼容性

运行方式：
    python -m unittest opensearch_sdk.tests.features.misc.test_retrieval_migration -v
"""

import os
import sys
import unittest
from pathlib import Path

# 注意：不需要手动设置 sys.path，run_all_tests.py 已经正确配置了 PYTHONPATH


class TestRetrievalMigration(unittest.TestCase):
    """测试检索模块迁移"""
    
    def _ensure_path(self):
        """确保正确的 Python 路径"""
        project_root = str(Path(__file__).parent.parent.parent)
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
    
    def test_01_import_types_module(self):
        """测试 types 模块导入"""
        self._ensure_path()
        from opensearch_sdk.retrieval.types import (
            ColumnType,
            IndexType,
            VectorDataType,
            DistanceMetric,
            RabitQRefineType,
            ColumnSchema,
            TableSchema,
            IndexConfig,
            RetrievalResult,
            SearchResult,
            VectorDBException,
            TableNotFoundException
        )
        print("\n[PASS] types module imported successfully")
    
    def test_02_import_retrievers_module(self):
        """测试 retrievers 模块导入"""
        self._ensure_path()
        from opensearch_sdk.retrieval.retrievers import (
            RetrievalResult,
            BaseRetriever,
            VectorRetriever,
            FullTextRetriever
        )
        print("[PASS] retrievers module imported successfully")
    
    def test_03_import_main_package(self):
        """测试主包导入"""
        self._ensure_path()
        import opensearch_sdk
        from opensearch_sdk.tests.utils.config_loader import load_db_config
        from opensearch_sdk import retrieval
        print("[PASS] opensearch_sdk.retrieval package imported successfully")
    
    def test_04_enum_values(self):
        """测试枚举值"""
        self._ensure_path()
        from opensearch_sdk.retrieval.types import (
            ColumnType, IndexType, DistanceMetric
        )
        
        self.assertEqual(ColumnType.VECTOR.value, "VECTOR")
        self.assertEqual(IndexType.HNSW.value, "hnsw")
        self.assertEqual(DistanceMetric.COSINE.value, "vector_cosine_ops")
        print("\n[PASS] Enumerations working correctly")
    
    def test_05_data_class_instantiation(self):
        """测试数据类实例化"""
        self._ensure_path()
        from opensearch_sdk.retrieval.types import (
            ColumnType, ColumnSchema, TableSchema, IndexConfig
        )
        
        # 测试 ColumnSchema
        column = ColumnSchema(
            name="embedding",
            type=ColumnType.VECTOR,
            dimension=3
        )
        self.assertEqual(column.name, "embedding")
        self.assertEqual(column.type, ColumnType.VECTOR)
        self.assertEqual(column.dimension, 3)
        
        print("[PASS] Data classes can be instantiated")


if __name__ == '__main__':
    unittest.main()
