#!/usr/bin/env python

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _is_vector_module(name):
    return (
        name == "psycopg2" or name.startswith("psycopg2.")
        or name == "opensearch_sdk" or name.startswith("opensearch_sdk.")
    )


def _snapshot_vector_modules():
    return {n: m for n, m in sys.modules.items() if _is_vector_module(n)}


def _clear_vector_modules():
    for name in [n for n in sys.modules if _is_vector_module(n)]:
        del sys.modules[name]


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_vector_modules():
    _clear_vector_modules()

    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.__path__ = []
    sys.modules["psycopg2"] = psycopg2

    extras = types.ModuleType("psycopg2.extras")
    extras.RealDictCursor = object
    extras.execute_values = lambda *args, **kwargs: None
    sys.modules["psycopg2.extras"] = extras
    psycopg2.extras = extras

    pool = types.ModuleType("psycopg2.pool")
    pool.ThreadedConnectionPool = object
    sys.modules["psycopg2.pool"] = pool
    psycopg2.pool = pool

    sql = types.ModuleType("psycopg2.sql")
    sql.Composable = object
    sql.SQL = str
    sql.Identifier = lambda name: '"{}"'.format(str(name).replace('"', '""'))
    sql.Literal = repr
    sys.modules["psycopg2.sql"] = sql
    psycopg2.sql = sql

    opensearch_sdk = types.ModuleType("opensearch_sdk")
    opensearch_sdk.__path__ = []
    sys.modules["opensearch_sdk"] = opensearch_sdk

    client_pkg = types.ModuleType("opensearch_sdk.client")
    client_pkg.__path__ = []
    sys.modules["opensearch_sdk.client"] = client_pkg
    opensearch_sdk.client = client_pkg

    constants = types.ModuleType("opensearch_sdk.client.constants")
    constants.DEFAULT_BATCH_SIZE = 1000
    constants.DEFAULT_HNSW_EF_SEARCH = 40
    constants.DEFAULT_RABITQ_SAMPLE_ROWS = 1000
    constants.MAX_KNN_TOP_K = 10000
    constants.MIN_KNN_TOP_K = 1
    constants.NESTED_FIELD_SEPARATOR = "__"
    sys.modules["opensearch_sdk.client.constants"] = constants
    client_pkg.constants = constants

    vector_types = _load_module("psycopg2.vector_types", "lib/vector_types.py")
    retrievers = _load_module("psycopg2.retrievers", "lib/retrievers.py")
    _load_module("psycopg2.multi_retrieval", "lib/multi_retrieval.py")
    vector_client = _load_module("psycopg2.vector_client", "lib/vector_client.py")
    sdk_vector_client = _load_module(
        "opensearch_sdk.client.vector_client",
        "opensearch_sdk/opensearch_sdk/client/vector_client.py",
    )
    return vector_types, retrievers, vector_client, sdk_vector_client


def load_search_ops_modules():
    vector_types, retrievers, _, _ = load_vector_modules()

    def _module(name):
        module = types.ModuleType(name)
        sys.modules[name] = module
        return module

    utils = _load_module(
        "opensearch_sdk.client.utils",
        "opensearch_sdk/opensearch_sdk/client/utils.py",
    )
    sys.modules["opensearch_sdk"].client.utils = utils

    post_filter_mark = _module("opensearch_sdk.client.post_filter_mark")
    post_filter_mark.PostFilterMark = object

    doc_utils = _module("opensearch_sdk.client.doc_utils")
    doc_utils.__path__ = []
    helpers = _module("opensearch_sdk.client.doc_utils.helpers")

    def with_search_trace(*decorator_args, **decorator_kwargs):
        if decorator_args and callable(decorator_args[0]) and not decorator_kwargs:
            return decorator_args[0]
        return lambda fn: fn

    helpers.with_search_trace = with_search_trace

    search_pkg = _module("opensearch_sdk.client.search")
    search_pkg.__path__ = []
    _module("opensearch_sdk.client.search.convenience")
    knn_handler = _module("opensearch_sdk.client.search.knn_handler")
    knn_handler.parse_knn_config = lambda *args, **kwargs: None
    knn_handler.merge_knn_and_bool_filters = lambda knn, bool_: knn or bool_ or {}

    query_builder_ext = _module("opensearch_sdk.client.search.query_builder_ext")
    query_builder_ext.build_select_clause = lambda *args, **kwargs: (None, False)
    query_builder_ext.build_sort_clause = lambda body, sort, params: ([], params)
    query_builder_ext.build_limit_clause = lambda body: None

    result_builder = _module("opensearch_sdk.client.search.result_builder")
    result_builder.build_search_hits = lambda *args, **kwargs: []
    result_builder.format_search_response = lambda hits: hits
    result_builder.build_knn_hits = lambda *args, **kwargs: []
    result_builder.build_retriever_hits = lambda *args, **kwargs: []

    indices = _module("opensearch_sdk.client.indices")
    indices.ENABLE_PYTHON_VALIDATION = True

    post_validator = _module("opensearch_sdk.client.post_validator")
    post_validator.PostValidator = type(
        "PostValidator", (), {"validate": staticmethod(lambda hits, marks: hits)}
    )

    query_builder = _load_module(
        "opensearch_sdk.client.query_builder",
        "opensearch_sdk/opensearch_sdk/client/query_builder.py",
    )
    search_ops = _load_module(
        "opensearch_sdk.client.search_ops",
        "opensearch_sdk/opensearch_sdk/client/search_ops.py",
    )
    return vector_types, retrievers, query_builder, search_ops


class ModuleCacheIsolationTests(unittest.TestCase):
    def test_vector_security_case_restores_replaced_modules(self):
        original = _snapshot_vector_modules()
        case = VectorSqlSecurityTests(
            "test_drop_identifiers_escape_embedded_quotes"
        )
        case.setUp()
        try:
            case.doCleanups()
            restored = _snapshot_vector_modules()
        finally:
            _clear_vector_modules()
            sys.modules.update(original)

        self.assertEqual(restored, original)


class VectorSqlSecurityTests(unittest.TestCase):
    def setUp(self):
        self._saved_modules = _snapshot_vector_modules()
        self.addCleanup(self._restore_modules)
        (
            self.vector_types, self.retrievers, self.vector_client,
            self.sdk_vector_client,
        ) = load_vector_modules()

    def _restore_modules(self):
        _clear_vector_modules()
        sys.modules.update(self._saved_modules)

    def _capture(self, module):
        client = object.__new__(module.MultiRetrieverClient)
        captured = []

        def execute_sql(query, params=None, fetch=True):
            captured.append((query, params, fetch))
            return []

        client.execute_sql = execute_sql
        return client, captured

    def _capture_client(self):
        return self._capture(self.vector_client)

    def _capture_sdk_client(self):
        return self._capture(self.sdk_vector_client)

    def _assert_drop_escapes(self, make_client):
        client, captured = make_client()
        self.assertTrue(client.drop_table('safe"; DROP TABLE pwned; --'))
        self.assertTrue(client.drop_index('idx"; DROP TABLE pwned; --'))
        self.assertIn('"safe""; DROP TABLE pwned; --"', captured[0][0])
        self.assertNotIn('"safe"; DROP TABLE pwned; --"', captured[0][0])
        self.assertIn('"idx""; DROP TABLE pwned; --"', captured[1][0])
        self.assertNotIn('"idx"; DROP TABLE pwned; --"', captured[1][0])

    def _assert_query_hardening(self, make_client):
        client, captured = make_client()
        with self.assertRaises(ValueError):
            client.query("docs", condition="id = 1")
        with self.assertRaises(ValueError):
            client.query("docs", order_by="id DESC")
        with self.assertRaises(ValueError):
            client.query("docs", limit="2")

        client.query('docs"; DROP TABLE pwned; --',
                     columns=['id"; DROP TABLE pwned; --'], limit=2, offset=1)
        query, params, _ = captured[-1]
        self.assertIn('"docs""; DROP TABLE pwned; --"', query)
        self.assertIn('"id""; DROP TABLE pwned; --"', query)
        self.assertIn("LIMIT %s", query)
        self.assertIn("OFFSET %s", query)
        self.assertEqual(params, (2, 1))

    def test_drop_identifiers_escape_embedded_quotes(self):
        self._assert_drop_escapes(self._capture_client)

    def test_create_table_escapes_table_column_and_comment_targets(self):
        column_schema_cls = self.vector_types.ColumnSchema
        column_type_cls = self.vector_types.ColumnType
        table_schema_cls = self.vector_types.TableSchema

        client, captured = self._capture_client()
        schema = table_schema_cls(columns=[
            column_schema_cls('id"; DROP TABLE pwned; --', column_type_cls.INTEGER, primary_key=True,
                         comment="col comment"),
        ], comment="table comment")

        self.assertTrue(client.create_table('docs"; DROP TABLE pwned; --', schema))

        create_sql = captured[0][0]
        table_comment_sql = captured[1][0]
        column_comment_sql = captured[2][0]
        self.assertIn('"docs""; DROP TABLE pwned; --"', create_sql)
        self.assertIn('"id""; DROP TABLE pwned; --"', create_sql)
        self.assertIn('"docs""; DROP TABLE pwned; --"', table_comment_sql)
        self.assertIn('"id""; DROP TABLE pwned; --"', column_comment_sql)

    def test_create_table_binds_comment_values(self):
        column_schema_cls = self.vector_types.ColumnSchema
        column_type_cls = self.vector_types.ColumnType
        table_schema_cls = self.vector_types.TableSchema

        table_comment = "\\'; DROP TABLE pwned; --"
        column_comment = "column \\' comment"
        client, captured = self._capture_client()
        schema = table_schema_cls(columns=[
            column_schema_cls("id", column_type_cls.INTEGER, primary_key=True,
                         comment=column_comment),
        ], comment=table_comment)

        self.assertTrue(client.create_table("docs", schema))

        self.assertEqual(captured[1], (
            'COMMENT ON TABLE "docs" IS %s', (table_comment,), False,
        ))
        self.assertEqual(captured[2], (
            'COMMENT ON COLUMN "docs"."id" IS %s', (column_comment,), False,
        ))
        self.assertNotIn(table_comment, captured[1][0])
        self.assertNotIn(column_comment, captured[2][0])

    def test_schema_defaults_and_index_metadata_are_fail_closed(self):
        column_schema_cls = self.vector_types.ColumnSchema
        column_type_cls = self.vector_types.ColumnType
        index_config_cls = self.vector_types.IndexConfig
        index_type_cls = self.vector_types.IndexType

        column = column_schema_cls("name", column_type_cls.TEXT, default="x'); DROP TABLE pwned; --")
        self.assertIn("DEFAULT E'x''); DROP TABLE pwned; --'", column.to_sql())

        backslash_column = column_schema_cls(
            "path", column_type_cls.TEXT, default="\\'; DROP TABLE pwned; --"
        )
        self.assertIn(
            "DEFAULT E'\\\\''; DROP TABLE pwned; --'",
            backslash_column.to_sql(),
        )

        index = index_config_cls(
            name='idx"; DROP TABLE pwned; --',
            index_type=index_type_cls.BTREE,
            column='name"; DROP TABLE pwned; --',
        )
        sql_text = index.to_sql('docs"; DROP TABLE pwned; --')
        self.assertIn('"idx""; DROP TABLE pwned; --"', sql_text)
        self.assertIn('"docs""; DROP TABLE pwned; --"', sql_text)
        self.assertIn('"name""; DROP TABLE pwned; --"', sql_text)

        index.where = "id = 1"
        with self.assertRaises(ValueError):
            index.to_sql("docs")

    def test_schema_default_allows_known_sql_keywords_only(self):
        column_schema_cls = self.vector_types.ColumnSchema
        column_type_cls = self.vector_types.ColumnType

        current_ts = column_schema_cls(
            "created_at", column_type_cls.TIMESTAMP, default="CURRENT_TIMESTAMP"
        )
        lowercase_now = column_schema_cls("created_at", column_type_cls.TIMESTAMP, default="now()")
        unsafe_function = column_schema_cls(
            "created_at", column_type_cls.TIMESTAMP,
            default="now()); DROP TABLE pwned; --",
        )

        self.assertIn("DEFAULT CURRENT_TIMESTAMP", current_ts.to_sql())
        self.assertIn("DEFAULT NOW()", lowercase_now.to_sql())
        self.assertIn("DEFAULT E'now()); DROP TABLE pwned; --'", unsafe_function.to_sql())

        class UnsafeDefault:
            def __str__(self):
                return "now()); DROP TABLE pwned; --"

        with self.assertRaises(ValueError):
            column_schema_cls(
                "created_at", column_type_cls.TIMESTAMP, default=UnsafeDefault()
            ).to_sql()

    def test_crud_rejects_untrusted_sql_fragments_and_normalizes_limits(self):
        self._assert_query_hardening(self._capture_client)

        client, _ = self._capture_client()
        with self.assertRaises(ValueError):
            client.update("docs", {"name": "x"}, None)

    def test_retrievers_escape_identifiers_and_reject_untrusted_fragments(self):
        vector_retriever_cls = self.retrievers.VectorRetriever

        retriever = vector_retriever_cls([1.0, 2.0], vector_column='embedding"; DROP TABLE pwned; --')
        with self.assertRaises(ValueError):
            retriever._build_query("docs", "3", None, None, None)

        query, params = retriever._build_query(
            'docs"; DROP TABLE pwned; --', 3, None, None,
            ['title"; DROP TABLE pwned; --'])

        self.assertIn('"docs""; DROP TABLE pwned; --"', query)
        self.assertIn('"embedding""; DROP TABLE pwned; --"', query)
        self.assertIn('"title""; DROP TABLE pwned; --"', query)
        self.assertIn("LIMIT %s", query)
        self.assertEqual(params[-1], 3)

        with self.assertRaises(ValueError):
            retriever._build_query("docs", 3, "id = 1", None, None)

    def test_opensearch_sdk_client_hardens_sql_construction(self):
        column_schema_cls = self.vector_types.ColumnSchema
        column_type_cls = self.vector_types.ColumnType
        table_schema_cls = self.vector_types.TableSchema

        client, captured = self._capture_sdk_client()
        schema = table_schema_cls(columns=[
            column_schema_cls('id"; DROP TABLE pwned; --', column_type_cls.INTEGER, primary_key=True),
        ])
        self.assertTrue(client.create_table('docs"; DROP TABLE pwned; --', schema))
        self.assertIn('"docs""; DROP TABLE pwned; --"', captured[0][0])
        self.assertIn('"id""; DROP TABLE pwned; --"', captured[0][0])

        self._assert_drop_escapes(self._capture_sdk_client)
        self._assert_query_hardening(self._capture_sdk_client)

        client, _ = self._capture_sdk_client()
        with self.assertRaises(ValueError):
            client.update("docs", {"name": "x"}, "id = 1")
        with self.assertRaises(ValueError):
            client.delete("docs", condition="id = 1")

    def test_sdk_generated_retriever_filter_is_trusted(self):
        vector_types, retrievers, _, search_ops = load_search_ops_modules()

        return_annotation = (
            search_ops.SearchOpsMixin._prepare_retriever_filter
            .__annotations__["return"]
        )
        self.assertIn("TrustedSQL", str(return_annotation))

        def build(filter_query):
            cond, cond_params = search_ops.SearchOpsMixin._prepare_retriever_filter(
                filter_query
            )
            self.assertIsInstance(cond, vector_types.TrustedSQL)
            return retrievers.VectorRetriever([1.0, 2.0])._build_query(
                "docs", 3, cond, cond_params, None
            )

        query, params = build({"term": {"category": "tech"}})
        self.assertIn('WHERE "category" = %s', query)
        self.assertEqual(params, ["[1.0,2.0]", "tech", "[1.0,2.0]", 3])

        # A generated filter over an attacker-controlled field stays escaped
        # once wrapped as TrustedSQL and embedded by the retriever.
        evil_query, _ = build({"term": {'x"; DROP TABLE pwned; --': "v"}})
        self.assertIn('WHERE "x""; DROP TABLE pwned; __" = %s', evil_query)
        self.assertNotIn('"x"; DROP TABLE pwned;', evil_query)

    def test_knn_filter_fields_escape_embedded_quotes(self):
        _, _, query_builder, _ = load_search_ops_modules()
        query_builder_cls = query_builder.QueryBuilder

        evil = 'x"; DROP TABLE pwned; --'
        # normalize_* turns '.'/'-' into '_' but leaves '"' intact; the fix is
        # quote_identifier doubling the embedded quote so it cannot break out.
        expected_field = '"x""; DROP TABLE pwned; __"'

        cases = [
            ({"term": {evil: "v"}}, ["v"], f'{expected_field} = %s'),
            ({"terms": {evil: ["a", "b"]}}, ["a", "b"], f'{expected_field} IN (%s,%s)'),
            ({"match": {evil: "v"}}, ["%v%"], f'{expected_field} LIKE %s::text'),
            ({"range": {evil: {"gte": 1}}}, [1], f'{expected_field} >= %s'),
        ]
        for filter_query, expected_params, expected_fragment in cases:
            cond, params = query_builder_cls.process_filter_for_knn(filter_query)
            self.assertEqual(cond, expected_fragment)
            self.assertEqual(params, expected_params)
            # The raw (unescaped) breakout form must never appear.
            self.assertNotIn('"x"; DROP TABLE pwned;', cond)

    def test_numeric_sql_uses_canonical_builtin_values(self):
        class EvilInt(int):
            def __str__(self):
                return "1); DROP TABLE pwned; --"

        class EvilFloat(float):
            def __str__(self):
                return "1); DROP TABLE pwned; --"

        vector_column = self.vector_types.ColumnSchema(
            "embedding",
            self.vector_types.ColumnType.VECTOR,
            dimension=EvilInt(16),
        )
        default_column = self.vector_types.ColumnSchema(
            "score",
            self.vector_types.ColumnType.DOUBLE_PRECISION,
            default=EvilFloat(1.5),
        )

        self.assertEqual(vector_column.to_sql(), '"embedding" VECTOR(16)')
        self.assertEqual(
            default_column.to_sql(),
            '"score" DOUBLE PRECISION DEFAULT 1.5',
        )
        self.assertEqual(
            self.vector_types.normalize_non_negative_int(EvilInt(4), "ef_search"),
            4,
        )
        self.assertIs(
            type(self.vector_types.normalize_non_negative_int(EvilInt(4), "ef_search")),
            int,
        )

    def test_non_finite_numeric_sql_is_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            column = self.vector_types.ColumnSchema(
                "score",
                self.vector_types.ColumnType.DOUBLE_PRECISION,
                default=value,
            )
            with self.assertRaisesRegex(ValueError, "finite"):
                column.to_sql()

def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == "__main__":
    unittest.main()
