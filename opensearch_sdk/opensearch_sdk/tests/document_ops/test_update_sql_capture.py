#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档操作测试 - SQL 捕获更新操作

功能说明：
- 捕获并显示 update() 方法实际执行的 SQL
- 验证更新操作的 SQL 生成逻辑

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.document_ops.test_update_sql_capture -v
    python opensearch_sdk/tests/document_ops/test_update_sql_capture.py
"""

import os
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from opensearch_sdk.tests.document_ops.update_common import (
    assert_partial_update,
    cleanup_index_and_assert_no_leaks,
    create_index_if_missing,
    create_update_client,
    update_mapping,
)


class TestUpdateSQLCapture(unittest.TestCase):
    """测试 update() 方法的 SQL"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = create_update_client()
        cls.test_index = "test_update_sql"
        create_index_if_missing(cls.client, cls.test_index, update_mapping())
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        cleanup_index_and_assert_no_leaks(cls.client, cls.test_index)
    
    def test_update_partial_with_sql_capture(self):
        """测试部分更新功能并捕获 SQL"""
        # 插入完整文档
        original_doc = {
            "title": "原始标题",
            "content": "原始内容",
            "category": "tech",
            "views": 100
        }
        partial_update = {
            "title": "更新后的标题",
            "views": 200
        }
        assert_partial_update(
            self,
            self.client,
            self.test_index,
            original_doc,
            partial_update,
            {
                "content": "原始内容",
                "category": "tech",
                "title": "更新后的标题",
                "views": 200
            }
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
