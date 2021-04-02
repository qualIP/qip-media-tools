#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import unittest

from pathlib import Path
import os
import sys

from qip.collections import OrderedSet

import logging
#logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

test_dir = Path(__file__).parent.absolute()


class test_OrderedSet(unittest.TestCase):

    @property
    def tmp_dir(self):
        return test_dir / f'tmp{Path(self.id()).suffix}'

    def test_OrderedSet(self):
        s = OrderedSet('abracadaba')
        t = OrderedSet('simsalabim')
        self.assertEqual(list(s), ['a', 'b', 'r', 'c', 'd'])
        self.assertEqual(list(t), ['s', 'i', 'm', 'a', 'l', 'b'])

if __name__ == '__main__':
    unittest.main()
