#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
其他功能测试 - 后过滤标记机制

功能说明：
- 后过滤标记机制单元测试
- 测试 Match Phrase 严格匹配（需要后过滤）
- 测试 Match Phrase with slop > 0（必须后过滤）
- 测试 Must Not 中的 match_phrase（不需要后过滤）
- 测试 Should 中的 match_phrase（可选，默认不收集）
- 测试嵌套 bool 的后过滤标记传播

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.other_features.test_post_filter_mark -v
    python opensearch_sdk/tests/other_features/test_post_filter_mark.py
"""

import unittest
from opensearch_sdk.client.post_filter_mark import PostFilterMark
from opensearch_sdk.client.post_validator import PostValidator


class TestPostFilterMark(unittest.TestCase):
    """测试 PostFilterMark 数据类"""
    
    def test_strict_phrase_mark(self):
        """测试严格短语匹配的标记"""
        mark = PostFilterMark(
            filter_type="match_phrase_strict",
            field="title",
            phrase="quick fox",
            slop=None,
            bool_type="must"
        )
        
        self.assertEqual(mark.filter_type, "match_phrase_strict")
        self.assertTrue(mark.requires_post_filter)
    
    def test_slop_phrase_mark(self):
        """测试 slop>0 的短语标记"""
        mark = PostFilterMark(
            filter_type="match_phrase_slop",
            field="title",
            phrase="quick fox",
            slop=1,
            bool_type="must"
        )
        
        self.assertEqual(mark.filter_type, "match_phrase_slop")
        self.assertTrue(mark.requires_post_filter)
    
    def test_must_not_no_filter(self):
        """测试 must_not 中的标记（不需要后过滤）"""
        mark = PostFilterMark(
            filter_type="match_phrase_strict",
            field="title",
            phrase="spam",
            slop=None,
            bool_type="must_not"
        )
        
        # Must Not 自动设置为 False
        self.assertFalse(mark.requires_post_filter)
    
    def test_should_optional_filter(self):
        """测试 should 中的严格短语（可选，默认不收集）"""
        mark = PostFilterMark(
            filter_type="match_phrase_strict",
            field="title",
            phrase="tutorial",
            slop=None,
            bool_type="should"
        )
        
        # Should 中的严格短语自动设置为 False
        self.assertFalse(mark.requires_post_filter)
    
    def test_should_slop_required(self):
        """测试 should 中的 slop>0（必须后过滤）"""
        mark = PostFilterMark(
            filter_type="match_phrase_slop",
            field="title",
            phrase="quick fox",
            slop=1,
            bool_type="should"
        )
        
        # Slop>0 无论在哪都必须后过滤
        self.assertTrue(mark.requires_post_filter)


class TestPostValidator(unittest.TestCase):
    """测试 PostValidator 后验证器"""
    
    def test_strict_phrase_match(self):
        """测试严格短语匹配"""
        hits = [
            {
                "_index": "test",
                "_id": "1",
                "_score": 1.0,
                "_source": {"title": "the quick fox jumps"}
            },
            {
                "_index": "test",
                "_id": "2",
                "_score": 1.0,
                "_source": {"title": "the quick brown fox"}  # 不连续
            }
        ]
        
        marks = [
            PostFilterMark(
                filter_type="match_phrase_strict",
                field="title",
                phrase="quick fox",
                slop=None,
                bool_type="must"
            )
        ]
        
        filtered = PostValidator.validate(hits, marks)
        
        # 应该只返回第一个（包含连续的 "quick fox"）
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["_id"], "1")
    
    def test_slop_phrase_match(self):
        """测试 slop>0 的短语匹配"""
        hits = [
            {
                "_index": "test",
                "_id": "1",
                "_score": 1.0,
                "_source": {"title": "the quick brown fox jumps"}  # brown 是 1 个词
            },
            {
                "_index": "test",
                "_id": "2",
                "_score": 1.0,
                "_source": {"title": "the quick very brown fox"}  # very brown 是 2 个词
            }
        ]
        
        marks = [
            PostFilterMark(
                filter_type="match_phrase_slop",
                field="title",
                phrase="quick fox",
                slop=1,  # 允许 1 个词的间隔
                bool_type="must"
            )
        ]
        
        filtered = PostValidator.validate(hits, marks)
        
        # 应该只返回第一个（间隔 <= 1）
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["_id"], "1")
    
    def test_no_marks(self):
        """测试没有标记的情况"""
        hits = [
            {"_id": "1", "_source": {"title": "test"}}
        ]
        
        filtered = PostValidator.validate(hits, [])
        
        # 应该返回所有结果
        self.assertEqual(len(filtered), 1)
    
    def test_array_field_match(self):
        """测试数组字段的短语匹配"""
        hits = [
            {
                "_index": "test",
                "_id": "1",
                "_score": 1.0,
                "_source": {"tags": ["tutorial", "quick fox guide"]}
            },
            {
                "_index": "test",
                "_id": "2",
                "_score": 1.0,
                "_source": {"tags": ["quick", "fox", "guide"]}
            }
        ]
        
        marks = [
            PostFilterMark(
                filter_type="match_phrase_strict",
                field="tags",
                phrase="quick fox",
                slop=None,
                bool_type="must"
            )
        ]
        
        filtered = PostValidator.validate(hits, marks)
        
        # 应该只返回第一个（有元素包含 "quick fox"）
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["_id"], "1")


if __name__ == "__main__":
    unittest.main()
