#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Match Phrase 查询测试 - Slop 集成测试

功能说明：
- 验证优化后的 match_phrase 查询
- 测试词序颠倒和 slop 间隔的支持
- 确保短语匹配的灵活性

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.match_phrase.test_match_phrase_slop_integration -v
    python opensearch_sdk/tests/match_phrase/test_match_phrase_slop_integration.py
"""

import unittest
import sys
import os
from opensearch_sdk.tests.utils.config_loader import load_db_config

# 添加项目根目录到 Python 路径（3 级父目录）
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from opensearch_sdk import OpenGauss


class TestMatchPhraseslopIntegration(unittest.TestCase):
    """match_phrase slop 匹配集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        # 加载配置
        cls.db_config = load_db_config()
        
        # 创建客户端
        cls.client = OpenGauss(
            hosts=[{
                'host': cls.db_config['host'],
                'port': cls.db_config['port']
            }],
            database=cls.db_config['database'],
            user=cls.db_config['user'],
            password=cls.db_config['password']
        )
        
        # 创建测试索引
        cls.test_index = 'test_match_phrase_slop'
        
        # 先尝试删除已存在的索引
        try:
            cls.client.indices.delete(index=cls.test_index)
        except:
            pass
        
        # 创建新索引（BM25 + 向量）
        mapping = {
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                }
            },
            "mappings": {
                "properties": {
                    "title": {
                        "type": "text",
                        "analyzer": "simple"
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "simple"
                    }
                }
            }
        }
        
        cls.client.indices.create(index=cls.test_index, body=mapping)
        
        # 准备测试数据
        cls.setup_test_data()
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(index=cls.test_index)
        except:
            pass
    
    @classmethod
    def setup_test_data(cls):
        """准备测试数据"""
        test_docs = [
            # 严格相邻
            {
                "id": "doc1",
                "body": {"title": "the quick brown fox jumps over the lazy dog"}
            },
            # 间隔 1 个词
            {
                "id": "doc2",
                "body": {"title": "the quick very brown fox jumps"}
            },
            # 词序颠倒 - fox 在 quick 前面
            {
                "id": "doc3",
                "body": {"title": "the fox is quick and brown"}
            },
            # 间隔多个词
            {
                "id": "doc4",
                "body": {"title": "the quick big bad brown fox"}
            },
            # 完全匹配
            {
                "id": "doc5",
                "body": {"title": "quick brown fox"}
            }
        ]
        
        for doc in test_docs:
            cls.client.index(index=cls.test_index, id=doc['id'], body=doc['body'])
    
    def test_01_strict_phrase_match(self):
        """测试 1：严格短语匹配（slop=0）"""
        query = {
            "query": {
                "match_phrase": {
                    "title": {
                        "query": "quick brown fox",
                        "slop": 0
                    }
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        # 应该匹配 doc1 和 doc5（严格相邻）
        hit_ids = [hit['_id'] for hit in hits]
        self.assertIn('doc1', hit_ids, "应该匹配 doc1（严格相邻）")
        self.assertIn('doc5', hit_ids, "应该匹配 doc5（完全匹配）")
        self.assertNotIn('doc2', hit_ids, "不应该匹配 doc2（有间隔）")
    
    def test_02_phrase_with_slop_1(self):
        """测试 2：允许间隔 1 个词（slop=1）"""
        query = {
            "query": {
                "match_phrase": {
                    "title": {
                        "query": "quick brown fox",
                        "slop": 1
                    }
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        # slop=1 允许短语中的词移动最多 1 个位置
        # 应该匹配 doc1, doc2, doc5
        # - doc1: "quick brown fox" (0 间隔) [OK]
        # - doc2: "quick very brown fox" (1 间隔) [OK]
        # - doc4: "quick big bad brown fox" (2 间隔) [FAIL] 需要 slop=2
        # - doc5: "quick brown fox" (0 间隔) [OK]
        hit_ids = [hit['_id'] for hit in hits]
        self.assertIn('doc1', hit_ids, "应该匹配 doc1")
        self.assertIn('doc2', hit_ids, "应该匹配 doc2（间隔 1 个词）")
        self.assertIn('doc5', hit_ids, "应该匹配 doc5")
        self.assertNotIn('doc4', hit_ids, "slop=1 不应该匹配 doc4（间隔 2 个词）")
    
    def test_02b_phrase_with_slop_2(self):
        """测试 2b：允许间隔 2 个词（slop=2）"""
        query = {
            "query": {
                "match_phrase": {
                    "title": {
                        "query": "quick brown fox",
                        "slop": 2
                    }
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        # slop=2 允许短语中的词移动最多 2 个位置
        # 应该匹配 doc1, doc2, doc4, doc5
        # - doc4: "quick big bad brown fox" (2 间隔) [OK]
        hit_ids = [hit['_id'] for hit in hits]
        self.assertIn('doc1', hit_ids, "应该匹配 doc1")
        self.assertIn('doc2', hit_ids, "应该匹配 doc2（间隔 1 个词）")
        self.assertIn('doc4', hit_ids, "应该匹配 doc4（间隔 2 个词）")
        self.assertIn('doc5', hit_ids, "应该匹配 doc5")
    
    def test_03_reversed_word_order(self):
        """测试 3：词序颠倒匹配"""
        query = {
            "query": {
                "match_phrase": {
                    "title": {
                        "query": "fox quick",
                        "slop": 2
                    }
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        # 应该匹配 doc3（fox 在 quick 前面，且间隔合理）
        hit_ids = [hit['_id'] for hit in hits]
        self.assertIn('doc3', hit_ids, "应该匹配 doc3（词序颠倒）")
    
    def test_04_reversed_insufficient_slop(self):
        """测试 4：词序颠倒但 slop 不足"""
        query = {
            "query": {
                "match_phrase": {
                    "title": {
                        "query": "fox quick",
                        "slop": 0
                    }
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        # slop=0 时不应该匹配词序颠倒的情况
        hit_ids = [hit['_id'] for hit in hits]
        self.assertNotIn('doc3', hit_ids, "slop=0 时不应该匹配词序颠倒")
    
    def test_05_no_slop_parameter(self):
        """测试 5：不指定 slop 参数（默认行为）"""
        query = {
            "query": {
                "match_phrase": {
                    "title": {
                        "query": "quick brown fox"
                    }
                }
            }
        }
        
        result = self.client.search(index=self.test_index, body=query)
        hits = result['hits']['hits']
        
        # 默认应该使用 slop=0（严格匹配）
        hit_ids = [hit['_id'] for hit in hits]
        self.assertIn('doc1', hit_ids, "应该匹配 doc1")
        self.assertIn('doc5', hit_ids, "应该匹配 doc5")
        # 可能不匹配有间隔的文档


if __name__ == '__main__':
    print("=" * 70)
    print("match_phrase slop 匹配功能集成测试")
    print("=" * 70)
    unittest.main(verbosity=2)
