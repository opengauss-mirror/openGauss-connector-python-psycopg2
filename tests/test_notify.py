#!/usr/bin/env python

# test_notify.py - unit test for async notifications
#
# Copyright (C) 2010-2019 Daniele Varrazzo  <daniele.varrazzo@gmail.com>
# Copyright (C) 2020-2021 The Psycopg Team
#
# psycopg2 is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# In addition, as a special exception, the copyright holders give
# permission to link this program with the OpenSSL library (or with
# modified versions of OpenSSL that use the same license as OpenSSL),
# and distribute linked combinations including the two.
#
# You must obey the GNU Lesser General Public License in all respects for
# all of the code used other than OpenSSL.
#
# psycopg2 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public
# License for more details.

import unittest
from collections import deque

import psycopg2
from psycopg2 import extensions
from psycopg2.extensions import Notify
from .testutils import ConnectingTestCase, skip_if_crdb, slow
from .testconfig import dsn

import sys
import time
import select
from subprocess import Popen, PIPE


@skip_if_crdb("notify")
class NotifiesTests(ConnectingTestCase):

    def autocommit(self, conn):
        """Set a connection in autocommit mode."""
        conn.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)

    def notify(self, name, sec=0, payload=None):
        """Send a notification to the database, eventually after some time."""
        if payload is None:
            payload = ''
        else:
            payload = f", {payload!r}"

        script = ("""\
import time
time.sleep({sec})
import {module} as psycopg2
import {module}.extensions as ext
conn = psycopg2.connect({dsn!r})
conn.set_isolation_level(ext.ISOLATION_LEVEL_AUTOCOMMIT)
print(conn.info.backend_pid)
curs = conn.cursor()
curs.execute("NOTIFY " {name!r} {payload!r})
curs.close()
conn.close()
""".format(
            module=psycopg2.__name__,
            dsn=dsn, sec=sec, name=name, payload=payload))

        return Popen([sys.executable, '-c', script], stdout=PIPE)

    def test_notify_init(self):
        n = psycopg2.extensions.Notify(10, 'foo')
        self.assertEqual(10, n.pid)
        self.assertEqual('foo', n.channel)
        self.assertEqual('', n.payload)
        (pid, channel) = n
        self.assertEqual((pid, channel), (10, 'foo'))

        n = psycopg2.extensions.Notify(42, 'bar', 'baz')
        self.assertEqual(42, n.pid)
        self.assertEqual('bar', n.channel)
        self.assertEqual('baz', n.payload)
        (pid, channel) = n
        self.assertEqual((pid, channel), (42, 'bar'))

    def test_compare(self):
        data = [(10, 'foo'), (20, 'foo'), (10, 'foo', 'bar'), (10, 'foo', 'baz')]
        for d1 in data:
            for d2 in data:
                n1 = psycopg2.extensions.Notify(*d1)
                n2 = psycopg2.extensions.Notify(*d2)
                self.assertEqual((n1 == n2), (d1 == d2))
                self.assertEqual((n1 != n2), (d1 != d2))

    def test_compare_tuple(self):
        self.assertEqual((10, 'foo'), Notify(10, 'foo'))
        self.assertEqual((10, 'foo'), Notify(10, 'foo', 'bar'))
        self.assertNotEqual((10, 'foo'), Notify(20, 'foo'))
        self.assertNotEqual((10, 'foo'), Notify(10, 'bar'))

    def test_hash(self):
        self.assertEqual(hash((10, 'foo')), hash(Notify(10, 'foo')))
        self.assertNotEqual(hash(Notify(10, 'foo', 'bar')),
            hash(Notify(10, 'foo')))


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)


if __name__ == "__main__":
    unittest.main()
