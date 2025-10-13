#!/bin/bash
#######################################################################
# Copyright (c): 2020-2025, Huawei Tech. Co., Ltd.
# descript: Testing concurrent query capabilities with vector inputs.
# date:     2025-10-10
#######################################################################
import os
import time
import unittest

import psycopg2
from psycopg2.extras import (init_worker, close_connection, execute_single,
    execute_multi_search, init_conn_pool, close_conn_pool)

from . import testutils
from .testutils import ConnectingTestCase


class ConnectInfo:
    def __init__(self):
        self.dbname = os.environ.get('PSYCOPG2_TESTDB', 'psycopg2_test')
        self.dbhost = os.environ.get('PSYCOPG2_TESTDB_HOST', os.environ.get('PGHOST'))
        self.dbport = os.environ.get('PSYCOPG2_TESTDB_PORT', os.environ.get('PGPORT'))
        self.dbuser = os.environ.get('PSYCOPG2_TESTDB_USER', os.environ.get('PGUSER'))
        self.dbpass = os.environ.get('PSYCOPG2_TESTDB_PASSWORD', os.environ.get('PGPASSWORD'))

        self.sql_template = "SELECT * FROM test_table1 ORDER BY embedding <-> %s LIMIT %s;"
        self.scan_params = {"enable_seqscan": "off", "hnsw_ef_search": 40}
        self.dbconfig = {'user': self.dbuser, 'password': self.dbpass, 'host': self.dbhost,
            'dbname': self.dbname, 'port': self.dbport}

class ParallelVectorScanTests(ConnectingTestCase):
    """Testing concurrent query capabilities with vector inputs."""

    def setUp(self):
        ConnectingTestCase.setUp(self)

        conn = self.connect()
        cur = conn.cursor()
        
        cur.execute("create table if not exists test_table1 (id integer, embedding vector(3));")
        cur.execute("insert into test_table1 values(1, '[1,2,3]'),(2, '[2,2,2]');")
        conn.commit()
    
    def test_init_worker(self):
        info = ConnectInfo()
        local_argslist = (('[1,2,2]', 2),)

        init_worker(info.scan_params, info.dbconfig)
        res = execute_single(local_argslist, info.sql_template)
        self.assertEqual(len(res[0]), 2)
        close_connection()

    def test_invalid_conninfo(self):
        info = ConnectInfo()
        dbconfig = {'user': "test", 'password': info.dbpass, 'host': info.dbhost,
            'dbname': info.dbname, 'port': info.dbport}
        argslist = [('[1,1,1]', 1), ('[2,2,3]', 2)]
        try:
            res = execute_multi_search(dbconfig, None, info.sql_template, argslist, info.scan_params, 2)
        except Exception as e:
            self.assertIsNotNone(e)
    
    def test_check_connection_pool(self):
        info = ConnectInfo()
        argslist = [('[1,1,1]', 1), ('[2,2,3]', 2)]
        conn_pool_mgr = init_conn_pool(info.dbconfig, 2, info.scan_params)

        start_time = time.time()
        while conn_pool_mgr.check_health():
            if time.time() - start_time > 5:
                break
            res = execute_multi_search(None, conn_pool_mgr, info.sql_template, argslist, info.scan_params, 2)
            self.assertEqual(len(res), 2)
        close_conn_pool(conn_pool_mgr)
    
    def test_connection_pool(self):
        argslist = [('[1,1,1]', 1), ('[2,2,3]', 2)]
        info = ConnectInfo()

        conn_pool_mgr = init_conn_pool(info.dbconfig, 2, info.scan_params)
        res = execute_multi_search(info.dbconfig, conn_pool_mgr, info.sql_template, argslist, info.scan_params, 2)
        self.assertEqual(len(res), 2)
        close_conn_pool(conn_pool_mgr)

    def test_direct_connection(self):
        argslist = [('[1,1,1]', 1), ('[2,2,3]', 2)]
        info = ConnectInfo()

        res = execute_multi_search(info.dbconfig, None, info.sql_template, argslist, info.scan_params, 2)
        self.assertEqual(len(res), 2)

    def test_argslist(self):
        info = ConnectInfo()

        argslist = [('[1,1,1]')]
        res = execute_multi_search(info.dbconfig, None, info.sql_template, argslist, info.scan_params, 2)
        self.assertIn("not all arguments converted during string formatting", str(res))

        argslist = [(1)]
        res = execute_multi_search(info.dbconfig, None, info.sql_template, argslist, info.scan_params, 2)
        self.assertIn("'int' object does not support indexing", str(res))

    def test_distance(self):
        info = ConnectInfo()
        argslist = [('[1,1,1]', 1), ('[2,2,3]', 2)]
        sql_template = "SELECT * FROM test_table1 ORDER BY embedding <#> %s LIMIT %s;"
        res = execute_multi_search(info.dbconfig, None, info.sql_template, argslist, info.scan_params, 2)
        self.assertEqual(len(res), 2)

        sql_template = "SELECT * FROM test_table1 ORDER BY embedding <=> %s LIMIT %s;"
        res = execute_multi_search(info.dbconfig, None, info.sql_template, argslist, info.scan_params, 2)
        self.assertEqual(len(res), 2)

        sql_template = "SELECT * FROM test_table1 ORDER BY embedding <+> %s LIMIT %s;"
        res = execute_multi_search(info.dbconfig, None, info.sql_template, argslist, info.scan_params, 2)
        self.assertEqual(len(res), 2)

    def test_sql_template(self):
        info = ConnectInfo()
        sql_template = "SELECT * FROM test_table1 ORDER BY embedding <-> %s LIMIT %s;\
            SELECT * FROM test_table1 where id>%s ORDER BY embedding <-> %s LIMIT %s;"
        argslist = [('[1,1,1]', 1, 1, '[2,3,4.5]', 10), ('[2,2,3]', 2, 100, '[5.6,7,8]', 10)]
        try:
            res = execute_multi_search(info.dbconfig, None, sql_template, argslist, info.scan_params, 2)
        except Exception as e:
            self.assertIn("Only one select statement is allowed", str(e))

        sql_template = "SELECT * FROM test_table1 where id>%s ORDER BY embedding <-> %s LIMIT %s;"
        argslist = [(1, '[2,3,4.5]', 1), (2, '[5.6,7,8]', 1)]
        res = execute_multi_search(info.dbconfig, None, sql_template, argslist, info.scan_params, 2)
        self.assertEqual(len(res), 2)

        sql_template = "SELECT * FROM (SELECT * FROM test_table1 ORDER BY  embedding <-> %s LIMIT %s)\
            ORDER BY embedding <=> %s LIMIT %s;"
        argslist = [('[4,4,4]', 1, '[2,3,4.5]', 1), ('[2,2,3]', 2, '[5.6,7,8]', 1)]
        res = execute_multi_search(info.dbconfig, None, sql_template, argslist, info.scan_params, 2)
        self.assertEqual(len(res), 2)

    def tearDown(self):
        ConnectingTestCase.tearDown(self)

        conn = self.connect()
        cur = conn.cursor()

        cur.execute("drop table if exists test_table1;")
        conn.commit()

def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == "__main__":
    unittest.main()
