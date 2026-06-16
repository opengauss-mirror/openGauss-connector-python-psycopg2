#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Bool 查询测试 - 增强测试

功能说明：
- Should 子句中 match_phrase 的后过滤行为
- 嵌套 bool 查询的标记传递
- Filter 上下文的特殊场景
- Exists 查询在 bool 中的使用
- 复杂嵌套组合查询
- Process_filter_for_knn 的完整覆盖

依赖：
- db_config.json (位于项目根目录)

运行方式：
    python -m unittest opensearch_sdk.tests.bool_query.test_bool_query_enhanced -v
    python opensearch_sdk/tests/bool_query/test_bool_query_enhanced.py
"""

import os
import sys
import unittest

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from opensearch_sdk import OpenGauss
from opensearch_sdk.retrieval import IndexConfig, IndexType
from opensearch_sdk.tests.utils.config_loader import load_db_config


TEXT_FIELDS = ['categories', 'title', 'content', 'status', 'tags', 'author']


def _create_client():
    db_config = load_db_config()
    return OpenGauss(
        hosts=[{'host': db_config['host'], 'port': db_config['port']}],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )


def _delete_index_if_exists(client, index_name):
    try:
        if client.indices.exists(index=index_name):
            client.indices.delete(index=index_name)
            print(f"Deleted old test index: {index_name}")
    except Exception:
        pass


def _insert_docs(client, index_name, docs):
    for doc in docs:
        client.index(index_name, doc["id"], doc["data"])


def _enhanced_mapping():
    return {
        "mappings": {
            "properties": {
                "categories": {"type": "text"},
                "title": {"type": "text"},
                "content": {"type": "text"},
                "status": {"type": "text"},
                "tags": {"type": "text"},
                "author": {"type": "text"},
                "view_count": {"type": "integer"},
                "created_at": {"type": "date"}
            }
        }
    }


def _enhanced_docs():
    return [
        {
            "id": "doc1",
            "data": {
                "categories": "technology,tutorial",
                "title": "OpenSearch 基础教程",
                "content": "学习 OpenSearch 的基础知识，适合初学者",
                "status": "published",
                "tags": "tutorial,beginner,opensearch",
                "author": "张三",
                "view_count": 1000,
                "created_at": "2024-01-01"
            }
        },
        {
            "id": "doc2",
            "data": {
                "categories": "technology,advanced",
                "title": "Advanced Search Techniques",
                "content": "高级搜索技巧，包含 BM25 和向量搜索",
                "status": "published",
                "tags": "advanced,bm25,vector",
                "author": "李四",
                "view_count": 2500,
                "created_at": "2024-01-02"
            }
        },
        {
            "id": "doc3",
            "data": {
                "categories": "database,tutorial",
                "title": "Database Basics",
                "content": "数据库基础概念，关系型数据库介绍",
                "status": "draft",
                "tags": "database,beginner,sql",
                "author": "张三",
                "view_count": 500,
                "created_at": "2024-01-03"
            }
        },
        {
            "id": "doc4",
            "data": {
                "categories": "cloud,intro",
                "title": "Cloud Computing Introduction",
                "content": "云计算入门，AWS Azure 介绍",
                "status": "archived",
                "tags": "cloud,beginner,aws",
                "author": "王五",
                "view_count": 800,
                "created_at": "2024-01-04"
            }
        },
        {
            "id": "doc5",
            "data": {
                "categories": "technology,ai",
                "title": "Machine Learning with Python",
                "content": "Python 机器学习实战，深度学习框架对比",
                "status": "published",
                "tags": "ai,machine-learning,python",
                "author": "李四",
                "view_count": 3000,
                "created_at": "2024-01-05"
            }
        },
        {
            "id": "doc6",
            "data": {
                "categories": "tutorial,database",
                "title": "SQL Query Optimization",
                "content": "SQL 查询优化技巧，索引使用指南",
                "status": "published",
                "tags": "database,advanced,performance",
                "author": "赵六",
                "view_count": 1800,
                "created_at": "2024-01-06"
            }
        }
    ]


def _knn_filter_mapping():
    return {
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "category": {"type": "keyword"},
                "vector_field": {
                    "type": "dense_vector",
                    "dims": 3
                }
            }
        }
    }


def _knn_filter_docs():
    return [
        {"id": "vec1", "data": {"title": "Document One", "category": "A", "vector_field": [1.0, 0.0, 0.0]}},
        {"id": "vec2", "data": {"title": "Document Two", "category": "B", "vector_field": [0.0, 1.0, 0.0]}},
        {"id": "vec3", "data": {"title": "Document Three", "category": "A", "vector_field": [0.0, 0.0, 1.0]}},
    ]


class TestBoolQueryEnhanced(unittest.TestCase):
    """Bool 查询增强测试"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = _create_client()
        cls.test_index = 'test_bool_query_enhanced'
        _delete_index_if_exists(cls.client, cls.test_index)
        cls.client.indices.create(index=cls.test_index, body=_enhanced_mapping())
        cls._create_bm25_indexes()
        cls.prepare_test_data()

    @classmethod
    def _create_bm25_indexes(cls):
        with cls.client.connection.get_connection_for_operation() as conn:
            cursor = conn.cursor()
            try:
                for field in TEXT_FIELDS:
                    cls._create_bm25_index(cursor, field)
                conn.commit()
            finally:
                cursor.close()

    @classmethod
    def _create_bm25_index(cls, cursor, field):
        try:
            cursor.execute(f"DROP INDEX IF EXISTS idx_{field}_bm25")
            index_config = IndexConfig(
                name=f"idx_{field}_bm25",
                column=field,
                index_type=IndexType.BM25,
                parallel_workers=4
            )
            pre_sql = index_config.get_pre_create_sql(cls.test_index)
            if pre_sql:
                cursor.execute(pre_sql)
            cursor.execute(index_config.to_sql(cls.test_index))
        except Exception as e:
            print(f"Warning: Failed to create BM25 index for {field}: {e}")
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(index=cls.test_index)
            print(f"Cleaned up test index: {cls.test_index}")
        except Exception:
            pass
        cls.client.close()
    
    @classmethod
    def prepare_test_data(cls):
        """准备测试数据"""
        _insert_docs(cls.client, cls.test_index, _enhanced_docs())
    
    # [WARN] 已移动到 todo/test_bool_query_should_issues.py
    # def test_should_strict_match_phrase(self):
    #     """测试 should 子句中的严格 match_phrase（SQL OR 逻辑处理）"""
    #     # 纯 should 查询需要 minimum_should_match 参数
    #     pass
    
    # [WARN] 已移动到 todo/test_bool_query_should_issues.py
    # def test_should_multiple_strict_phrases(self):
    #     """测试 should 中包含多个严格 match_phrase（OR 逻辑）"""
    #     # 纯 should 查询需要 minimum_should_match 参数
    #     pass
    
    def test_should_with_slop(self):
        """测试 should 子句中包含 slop 的 match_phrase"""
        query = {
            "query": {
                "bool": {
                    "should": [
                        {
                            "match_phrase": {
                                "title": {
                                    "query": "Search Techniques",
                                    "slop": 2
                                }
                            }
                        }
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回 doc2（"Advanced Search Techniques"，slop=2 允许间隔）
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc2", hit_ids)
    
    # ==================== 嵌套 Bool 查询测试 ====================
    
    def test_nested_bool_in_must(self):
        """测试 must 中嵌套 bool 查询"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "must": [
                                    {"match_phrase": {"status": "published"}}
                                ],
                                "should": [
                                    {"match_phrase": {"tags": "tutorial"}}
                                ]
                            }
                        }
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回 published 且包含 tutorial 的文档
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc1", hit_ids)  # published + tutorial
    
    # [WARN] 已移动到 todo/test_bool_query_should_issues.py
    # def test_nested_bool_in_should(self):
    #     """测试 should 中嵌套 bool 查询（OR 逻辑）"""
    #     # 纯 should 查询需要 minimum_should_match 参数
    #     pass
    
    def test_nested_bool_in_must_not(self):
        """测试 must_not 中嵌套 bool 查询"""
        query = {
            "query": {
                "bool": {
                    "must_not": [
                        {
                            "bool": {
                                "must": [
                                    {"match_phrase": {"status": "published"}},
                                    {"match_phrase": {"tags": "beginner"}}
                                ]
                            }
                        }
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该排除 published + beginner 的文档
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertNotIn("doc1", hit_ids)  # published + beginner，应排除
        self.assertIn("doc2", hit_ids)  # published + advanced，应保留
    
    def test_deeply_nested_bool(self):
        """测试深度嵌套的 bool 查询（3 层嵌套）"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "should": [
                                    {
                                        "bool": {
                                            "must": [
                                                {"match_phrase": {"tags": "tutorial"}},
                                                {"match_phrase": {"tags": "beginner"}}
                                            ]
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回同时包含 tutorial 和 beginner 标签的文档
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc1", hit_ids)  # tutorial,beginner
    
    # ==================== Filter 上下文测试 ====================
    
    def test_filter_context_basic(self):
        """测试 filter 上下文的基本使用"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"content": "数据库"}}
                    ],
                    "filter": [
                        {"term": {"status": "draft"}}
                    ]
                }
            },
            "size": 10
        }
            
        result = self.client.search(self.test_index, query)
            
        for hit in result["hits"]["hits"]:
            self.assertEqual(hit["_source"]["status"], "draft")
    
    def test_multiple_filters(self):
        """测试多个 filter 条件"""
        query = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"status": "published"}},
                        {"range": {"view_count": {"gte": 1000}}}
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回 published 且浏览量>=1000 的文档
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc1", hit_ids)  # published, 1000 views
        self.assertIn("doc2", hit_ids)  # published, 2500 views
        self.assertIn("doc5", hit_ids)  # published, 3000 views
        self.assertIn("doc6", hit_ids)  # published, 1800 views
    
    def test_filter_with_bool_inside(self):
        """测试 filter 中包含 bool 查询"""
        query = {
            "query": {
                "bool": {
                    "filter": {
                        "bool": {
                            "should": [
                                {"term": {"author": "张三"}},
                                {"term": {"author": "李四"}}
                            ]
                        }
                    }
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回张三或李四的文章
        authors = set()
        for hit in result["hits"]["hits"]:
            authors.add(hit["_source"]["author"])
        
        self.assertEqual(authors, {"张三", "李四"})
    
    # ==================== Exists 查询测试 ====================
    
    def test_exists_in_bool(self):
        """测试 exists 查询在 bool 中的使用"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "author"}}
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 所有文档都有 author 字段
        self.assertEqual(result["hits"]["total"]["value"], 6)
    
    def test_exists_with_must_not(self):
        """测试 exists + must_not 组合"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"exists": {"field": "author"}}
                    ],
                    "must_not": [
                        {"term": {"author": "张三"}}
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回不是张三的文章
        for hit in result["hits"]["hits"]:
            self.assertNotEqual(hit["_source"]["author"], "张三")
    
    # ==================== 复杂组合查询测试 ====================
    
    def test_complex_mixed_query(self):
        """测试复杂的混合查询（must + should + must_not + filter）"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"status": "published"}}
                    ],
                    "should": [
                        {"match_phrase": {"tags": "tutorial"}},
                        {"match_phrase": {"tags": "advanced"}}
                    ],
                    "must_not": [
                        {"match_phrase": {"author": "王五"}}
                    ],
                    "filter": [
                        {"range": {"view_count": {"gte": 1000}}}
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 条件分析：
        # - must: published
        # - should: tutorial OR advanced（加分项）
        # - must_not: NOT 王五
        # - filter: view_count >= 1000
        # 
        # 符合的文档：
        # doc1: published + tutorial + 张三 + 1000 [OK]
        # doc2: published + advanced + 李四 + 2500 [OK]
        # doc5: published + ai,machine-learning,python + 李四 + 3000 (可能不符合 should)
        # doc6: published + database,advanced,performance + 赵六 + 1800 [OK]
        
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc1", hit_ids)
        self.assertIn("doc2", hit_ids)
        self.assertIn("doc6", hit_ids)
        self.assertNotIn("doc4", hit_ids)  # 王五的文章，应排除
    
    def test_should_minimum_should_match(self):
        """测试 should 的最小匹配数（通过 must 模拟）"""
        # Opensearch 可能不支持 minimum_should_match 参数
        # 这里测试通过多个 must 来模拟类似效果
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"match_phrase": {"tags": "tutorial"}},
                        {"match_phrase": {"tags": "beginner"}}
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 必须同时包含 tutorial 和 beginner
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc1", hit_ids)  # tutorial,beginner
        # doc3 只有 beginner，没有 tutorial，所以不应该返回
        self.assertNotIn("doc3", hit_ids)
    
    # ==================== 边界情况测试 ====================
    
    def test_empty_bool_clauses(self):
        """测试空的 bool 子句"""
        query = {
            "query": {
                "bool": {}
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 空 bool 应该返回所有文档
        self.assertEqual(result["hits"]["total"]["value"], 6)
    
    def test_single_dict_must(self):
        """测试 must 为单个 dict（非列表）"""
        query = {
            "query": {
                "bool": {
                    "must": {"match_phrase": {"categories": "technology"}}
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回 categories 包含 technology 的文档
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc1", hit_ids)
        self.assertIn("doc2", hit_ids)
        self.assertIn("doc5", hit_ids)
    
    def test_single_dict_should(self):
        """测试 should 为单个 dict（非列表）"""
        query = {
            "query": {
                "bool": {
                    "should": {"match_phrase": {"author": "张三"}}
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回张三的文章
        hit_ids = [hit["_id"] for hit in result["hits"]["hits"]]
        self.assertIn("doc1", hit_ids)
        self.assertIn("doc3", hit_ids)
    
    def test_single_dict_must_not(self):
        """测试 must_not 为单个 dict（非列表）"""
        query = {
            "query": {
                "bool": {
                    "must_not": {"match_phrase": {"status": "published"}}
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回非 published 状态的文档
        for hit in result["hits"]["hits"]:
            self.assertNotEqual(hit["_source"]["status"], "published")
    
    # ==================== Range 查询测试 ====================
    
    def test_range_gte_lte(self):
        """测试 range 查询的 gte 和 lte"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"range": {"view_count": {"gte": 1000, "lte": 2000}}}
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回浏览量在 1000-2000 之间的文档
        for hit in result["hits"]["hits"]:
            view_count = hit["_source"]["view_count"]
            self.assertGreaterEqual(view_count, 1000)
            self.assertLessEqual(view_count, 2000)
    
    def test_range_gt_lt(self):
        """测试 range 查询的 gt 和 lt"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"range": {"view_count": {"gt": 1000, "lt": 3000}}}
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回浏览量在 1000-3000 之间（不包含边界）的文档
        for hit in result["hits"]["hits"]:
            view_count = hit["_source"]["view_count"]
            self.assertGreater(view_count, 1000)
            self.assertLess(view_count, 3000)
    
    # ==================== Terms 查询测试 ====================
    
    def test_terms_in_bool(self):
        """测试 terms 查询在 bool 中的使用"""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"author": ["张三", "李四"]}}
                    ]
                }
            },
            "size": 10
        }
        
        result = self.client.search(self.test_index, query)
        
        # 应该返回张三或李四的文章
        authors = set()
        for hit in result["hits"]["hits"]:
            authors.add(hit["_source"]["author"])
        
        self.assertEqual(authors, {"张三", "李四"})


class TestProcessFilterForKnn(unittest.TestCase):
    """测试 process_filter_for_knn 函数的完整覆盖"""
    
    @classmethod
    def setUpClass(cls):
        """设置测试环境"""
        cls.client = _create_client()
        cls.test_index = 'test_knn_filter'
        _delete_index_if_exists(cls.client, cls.test_index)
        cls.client.indices.create(index=cls.test_index, body=_knn_filter_mapping())
        _insert_docs(cls.client, cls.test_index, _knn_filter_docs())
    
    @classmethod
    def tearDownClass(cls):
        """清理测试环境"""
        try:
            cls.client.indices.delete(index=cls.test_index)
        except Exception:
            pass
        cls.client.close()

    def _knn_filter_hits(self, filter_query):
        query = {
            "query": {
                "knn": {
                    "vector_field": {
                        "vector": [1.0, 0.1, 0.0],
                        "k": 3,
                        "filter": filter_query
                    }
                }
            }
        }
        result = self.client.search(self.test_index, query)
        return result["hits"]["hits"]

    def _assert_all_category_a(self, hits):
        for hit in hits:
            self.assertEqual(hit["_source"]["category"], "A")
    
    def test_knn_with_term_filter(self):
        """测试 kNN 搜索带 term 过滤"""
        hits = self._knn_filter_hits({"term": {"category": "A"}})
        self._assert_all_category_a(hits)

    def test_knn_with_bool_filter(self):
        """测试 kNN 搜索带 bool 过滤"""
        hits = self._knn_filter_hits({
            "bool": {
                "must": [
                    {"term": {"category": "A"}}
                ]
            }
        })
        self._assert_all_category_a(hits)


if __name__ == '__main__':
    unittest.main()
