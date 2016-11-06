
__all__ = [
        'dbg_exec_cmd',
        'do_exec_cmd',
        'clean_cmd_output',
        'Executable',
        ]

import abc
import os
import re
import shutil
import subprocess
import time
import types
import errno
import logging
log = logging.getLogger(__name__)

from qip.app import app  # Also setup log.verbose
from qip.utils import byte_decode

def dbg_exec_cmd(cmd, hidden_args=[], **kwargs):
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s', subprocess.list2cmdline(cmd))
    return subprocess.check_output(cmd + hidden_args, **kwargs)

def do_exec_cmd(cmd, **kwargs):
    if getattr(app.args, 'dry_run', False):
        log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(cmd))
        return ''
    else:
        return dbg_exec_cmd(cmd, **kwargs)

# clean_cmd_output {{{

def clean_cmd_output(out):
    if isinstance(out, bytes):
        out = byte_decode(out)
    out = re.sub(r'\x1B\[[0-9;]*m', '', out)
    out = re.sub(r'\r\n', '\n', out)
    out = re.sub(r'.*\r', '', out, flags=re.MULTILINE)
    out = re.sub(r'\t', ' ', out)
    out = re.sub(r' +$', '', out, flags=re.MULTILINE)
    return out

# }}}

class Executable(metaclass=abc.ABCMeta):

    @property
    @abc.abstractmethod
    def name(self):
        raise NotImplementedError

    def which(self, mode=os.F_OK | os.X_OK, path=None, assert_found=True):
        cmd = shutil.which(self.name, mode=mode, path=path)
        if cmd is None and assert_found:
            raise OSError(errno.ENOENT, '{}: command not found'.format(self.name), self.name)
        return cmd

    def clean_cmd_output(self, out):
        return clean_cmd_output(out)

    @classmethod
    def kwargs_to_cmdargs(cls, **kwargs):
        if kwargs:
            raise ValueError('Unsupported keyword arguments: %r' % (kwargs,))
        return []

    def _run(self, *args, **kwargs):
        d = types.SimpleNamespace()
        run_func = kwargs.pop('run_func', None)
        cmd = [self.which()] + list(args) + self.kwargs_to_cmdargs(**kwargs)
        if run_func is None:
            t0 = time.time()
            d.out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            #d.subprocess_info = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            t1 = time.time()
            #d.out = d.subprocess_info.stdout
        else:
            t0 = time.time()
            d.out = run_func(cmd)
            t1 = time.time()
        d.elapsed_time = t1 - t0
        return d

    def __call__(self, *args, **kwargs):
        return self._run(*args, **kwargs)

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
