#!/bin/bash
#######################################################################
# Copyright (c): 2020-2025, Huawei Tech. Co., Ltd.
# descript: Testing pool.
# date:     2025-10-10
#######################################################################
import os
import unittest

import psycopg2
from psycopg2 import pool

from . import testutils
from .testutils import ConnectingTestCase

class ConnectInfo:
    def __init__(self):
        self.dbname = os.environ.get('PSYCOPG2_TESTDB', 'psycopg2_test')
        self.dbhost = os.environ.get('PSYCOPG2_TESTDB_HOST', os.environ.get('PGHOST'))
        self.dbport = os.environ.get('PSYCOPG2_TESTDB_PORT', os.environ.get('PGPORT'))
        self.dbuser = os.environ.get('PSYCOPG2_TESTDB_USER', os.environ.get('PGUSER'))
        self.dbpass = os.environ.get('PSYCOPG2_TESTDB_PASSWORD', os.environ.get('PGPASSWORD'))
    
class TestPool(ConnectingTestCase):
    def test_simple_connection_pool(self):
        info = ConnectInfo()
        simple_connection_pool = psycopg2.pool.SimpleConnectionPool(2, 10, user=info.dbuser,
                                                               password=info.dbpass,
                                                               host=info.dbhost,
                                                               port=info.dbport,
                                                               database=info.dbname)
        sc_connection = simple_connection_pool.getconn()
        if (sc_connection):
            sc_cursor = sc_connection.cursor()
            sc_cursor.execute("SELECT 1;")
            res = sc_cursor.fetchall()
            sc_connection.commit()
            self.assertEqual(res[0][0], 1)
            sc_cursor.close()
            simple_connection_pool.putconn(sc_connection)
        
        if simple_connection_pool:
            simple_connection_pool.closeall()
    
    def test_thread_connection_pool(self):
        info = ConnectInfo()
        thread_connection_pool = psycopg2.pool.ThreadedConnectionPool(2, 10, user=info.dbuser,
                                                               password=info.dbpass,
                                                               host=info.dbhost,
                                                               port=info.dbport,
                                                               database=info.dbname)
        tc_connection = thread_connection_pool.getconn()
        if (tc_connection):
            tc_cursor = tc_connection.cursor()
            tc_cursor.execute("SELECT 1;")
            res = tc_cursor.fetchall()
            tc_connection.commit()
            self.assertEqual(res[0][0], 1)
            tc_cursor.close()
            thread_connection_pool.putconn(tc_connection)
        
        if thread_connection_pool:
            thread_connection_pool.closeall()

def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == "__main__":
    unittest.main()