#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import unittest

from pathlib import Path
import os
import sys

import qip.utils

import logging
#logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

import reprlib
reprlib.aRepr.maxdict = 100

test_dir = Path(__file__).parent.absolute()


class test_utils(unittest.TestCase):

    @property
    def tmp_dir(self):
        return test_dir / f'tmp{Path(self.id()).suffix}'

    def test_is_term_dark(self):

        for COLORFGBG, dark in (
                (None, None),
                ('0;0', True),
                ('0;6', True),
                ('0;7', False),
                ('0;8', True),
                ('08', None),
                ('0;1;2', None),
        ):
            with self.subTest(COLORFGBG=COLORFGBG):
                if COLORFGBG is None:
                    try:
                        del os.environ['COLORFGBG']
                    except KeyError:
                        pass
                else:
                    os.environ['COLORFGBG'] = COLORFGBG
                self.assertIs(qip.utils.is_term_dark(default=None), dark)

if __name__ == '__main__':
    unittest.main()
