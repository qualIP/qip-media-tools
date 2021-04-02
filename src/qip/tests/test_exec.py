#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import unittest

from pathlib import Path
import codecs
import collections
import io
import os
import pexpect
import subprocess
import sys

from qip.exec import Executable, spawn as _exec_spawn

import logging
#logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

test_dir = Path(__file__).parent.absolute()


class Echo_out_err(Executable):

    def __init__(self, *, encoding=None, encoding_errors=None, **kwargs):
        self.encoding = encoding
        self.encoding_errors = encoding_errors
        super().__init__(**kwargs)

    name = test_dir / 'echo-out-err'

echo_out_err = Echo_out_err()

re_eol = r'\r?\n'


class Echo_out_err_spawn(Echo_out_err):

    run_func = Executable._spawn_run_func

    class spawn(_exec_spawn):

        def __init__(self, *args, **kwargs):
            self.lines = []
            super().__init__(*args, **kwargs)

        def unknown_line(self, str):
            raise ValueError(str)

        def cb_line(self, str):
            self.lines.append(str)
            return True

        def get_pattern_dict(self):
            pattern_dict = collections.OrderedDict([
                (fr'^out{re_eol}', self.cb_line),
                (fr'^err{re_eol}', self.cb_line),
                (fr'[^\n]*?{re_eol}', self.unknown_line),
                (pexpect.EOF, False),
            ])
            return pattern_dict

echo_out_err_spawn = Echo_out_err_spawn()


class test_exec(unittest.TestCase):

    @property
    def tmp_dir(self):
        return test_dir / f'tmp{Path(self.id()).suffix}'

    def test_run(self):
        out = echo_out_err()
        self.assertIn(out.out, (
            b'out\nerr\n',
            b'err\nout\n',
        ))

    def test_popen(self):
        p = echo_out_err.popen(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        out, err = p.communicate()
        self.assertEqual(out, b'out\n')
        self.assertEqual(err, b'err\n')

    def test_spawn(self):
        out = echo_out_err_spawn()
        self.assertIn(out.out, (
            b'out\r\nerr\r\n',
            b'err\r\nout\r\n',
        ))
        self.assertIn(out.spawn.lines, (
            [b'out\r\n', b'err\r\n'],
            [b'err\r\n', b'out\r\n'],
        ))

    def test_spawn_text(self):
        echo_out_err_spawn = Echo_out_err_spawn(encoding='utf-8')
        out = echo_out_err_spawn()
        self.assertIn(out.out, (
            'out\r\nerr\r\n',
            'err\r\nout\r\n',
        ))

    def test_io_binary(self):
        writer = io.BytesIO()
        writer.write(b'abc')
        value = writer.getvalue()
        self.assertEqual(value, b'abc')

    def test_io_text(self):
        encoding = 'utf-8'
        errors = 'strict'
        decoder = codecs.getincrementaldecoder(encoding)(errors)
        value = decoder.decode(b'abc')
        self.assertEqual(value, 'abc')

    def test_run_new(self):
        comp = echo_out_err.run_new(capture_output=True)
        self.assertEqual(comp.stdout, b'out\n')
        self.assertEqual(comp.stderr, b'err\n')

    def test_run_new_dry_run(self):
        comp = echo_out_err.run_new(capture_output=True, dry_run=True)
        self.assertEqual(comp.stdout, b'')
        self.assertEqual(comp.stderr, b'')

    def test_run_new_text(self):
        echo_out_err = Echo_out_err(encoding='utf-8')
        comp = echo_out_err.run_new(capture_output=True)
        self.assertEqual(comp.stdout, 'out\n')
        self.assertEqual(comp.stderr, 'err\n')

if __name__ == '__main__':
    unittest.main()
