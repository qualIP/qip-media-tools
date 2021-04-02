#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import unittest

from pathlib import Path
import collections
import itertools
import os
import sys

from qip.utils import Indexable, indexable, adviter, advenumerate

import logging
#logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

test_dir = Path(__file__).parent.absolute()


class test_adviter(unittest.TestCase):

    @property
    def tmp_dir(self):
        return test_dir / f'tmp{Path(self.id()).suffix}'

    def test_indexable_isinstance(self):
        self.assertIsInstance([1,2,3], Indexable)
        self.assertIsInstance((1,2,3), Indexable)
        self.assertIsInstance('abc', Indexable)
        self.assertIsInstance(collections.UserList(), Indexable)
        self.assertNotIsInstance(iter([1,2,3]), Indexable)

    def test_indexable_noop(self):
        for l in (
                [1,2,3],
                (1,2,3),
                'abc',
        ):
            it = indexable(l)
            self.assertIs(it, l)

    def test_indexable(self):
        col = indexable(itertools.count(start=10))
        self.assertEqual(col[0], 10)
        self.assertEqual(col[10], 20)
        self.assertEqual(col[5], 15)

    def test_advenumerate(self):
        l = 'abc'
        it = advenumerate(l)
        v = next(it)
        self.assertEqual(v, (0, 'a'))
        it = advenumerate(l, start=2)
        v = next(it)
        self.assertEqual(v, (2, 'c'))
        it.send(1)
        v = next(it)
        self.assertEqual(v, (1, 'b'))
        v = next(it)
        self.assertEqual(v, (2, 'c'))
        it.send(3)
        with self.assertRaises(StopIteration):
            v = next(it)

    def test_adviter(self):
        l = 'abc'
        it = adviter(l)
        v = next(it)
        self.assertEqual(v, 'a')
        it = adviter(l, start=2)
        v = next(it)
        self.assertEqual(v, 'c')
        it.send(1)
        v = next(it)
        self.assertEqual(v, 'b')
        v = next(it)
        self.assertEqual(v, 'c')
        it.send(3)
        with self.assertRaises(StopIteration):
            v = next(it)

    def test_advenumerate_it(self):
        l = 'abc'
        it = advenumerate(iter(l))
        v = next(it)
        self.assertEqual(v, (0, 'a'))
        it = advenumerate(iter(l), start=2)
        v = next(it)
        self.assertEqual(v, (2, 'c'))
        it.send(1)
        v = next(it)
        self.assertEqual(v, (1, 'b'))
        v = next(it)
        self.assertEqual(v, (2, 'c'))
        it.send(3)
        with self.assertRaises(StopIteration):
            v = next(it)

if __name__ == '__main__':
    unittest.main()
