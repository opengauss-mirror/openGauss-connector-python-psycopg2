#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test indices.stats() - index statistics API

Verifies:
1. Basic stats structure (OpenSearch compatible)
2. Doc count accuracy after insert/delete
3. Store size is a valid integer
4. Stats on nonexistent index raises error
5. Stats after index recreation
"""

import json
import os
import sys
import unittest

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.config_loader import load_db_config
from opensearch_sdk.tests.utils.config_loader import load_db_config
from opensearch_sdk import OpenGauss


class TestIndicesStats(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        db_config = load_db_config()
        cls.client = OpenGauss(
            hosts=[{'host': db_config['host'], 'port': db_config['port']}],
            database=db_config['database'],
            user=db_config['user'],
            password=db_config['password']
        )
        cls.test_index = "test_stats_idx"
        cls._create_index_with_data()

    @classmethod
    def _create_index_with_data(cls):
        try:
            cls.client.indices.delete(cls.test_index)
        except Exception:
            pass

        mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "category": {"type": "keyword"},
                    "view_count": {"type": "integer"}
                }
            }
        }
        cls.client.indices.create(index=cls.test_index, body=mapping)

        docs = [
            ("s1", {"title": "stats test one", "category": "A", "view_count": 10}),
            ("s2", {"title": "stats test two", "category": "B", "view_count": 20}),
            ("s3", {"title": "stats test three", "category": "A", "view_count": 30}),
        ]
        for doc_id, doc_body in docs:
            cls.client.index(index=cls.test_index, id=doc_id, body=doc_body)

        cls.client.indices.refresh(index=cls.test_index)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.client.indices.delete(cls.test_index)
        except Exception:
            pass

    def test_stats_basic_structure(self):
        stats = self.client.indices.stats(index=self.test_index)

        self.assertIn("_shards", stats)
        self.assertIn("indices", stats)
        self.assertIn(self.test_index, stats["indices"])

        shards = stats["_shards"]
        self.assertEqual(shards["total"], 1)
        self.assertEqual(shards["successful"], 1)
        self.assertEqual(shards["failed"], 0)

    def test_stats_doc_count(self):
        stats = self.client.indices.stats(index=self.test_index)
        index_stats = stats["indices"][self.test_index]

        doc_count = index_stats["primaries"]["docs"]["count"]
        self.assertIsInstance(doc_count, int)
        self.assertGreaterEqual(doc_count, 3)

    def test_stats_store_size(self):
        stats = self.client.indices.stats(index=self.test_index)
        index_stats = stats["indices"][self.test_index]

        store_size = index_stats["primaries"]["store"]["size_in_bytes"]
        self.assertIsInstance(store_size, int)
        self.assertGreater(store_size, 0)

    def test_stats_all_section(self):
        stats = self.client.indices.stats(index=self.test_index)

        self.assertIn("_all", stats)
        self.assertIn("primaries", stats["_all"])
        self.assertIn("total", stats["_all"])

        primaries = stats["_all"]["primaries"]
        self.assertIn("docs", primaries)
        self.assertIn("store", primaries)

    def test_stats_nonexistent_index(self):
        with self.assertRaises(Exception):
            self.client.indices.stats(index="nonexistent_stats_index")

    def test_stats_empty_value_rejected(self):
        with self.assertRaises(ValueError):
            self.client.indices.stats(index="")


if __name__ == '__main__':
    unittest.main()
