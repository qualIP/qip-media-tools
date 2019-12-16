#!/usr/bin/env python3

import unittest

from qip.collections import OrderedSet

class test_OrderedSet(unittest.TestCase):

    def test_OrderedSet(self):
        s = OrderedSet('abracadaba')
        t = OrderedSet('simsalabim')
        self.assertEqual(list(s), ['a', 'b', 'r', 'c', 'd'])
        self.assertEqual(list(t), ['s', 'i', 'm', 'a', 'l', 'b'])

if __name__ == '__main__':
    unittest.main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
