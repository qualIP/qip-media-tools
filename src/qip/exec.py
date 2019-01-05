
__all__ = [
        'dbg_exec_cmd',
        'do_exec_cmd',
        'suggest_exec_cmd',
        'dbg_spawn_cmd',
        'do_spawn_cmd',
        'clean_cmd_output',
        'Executable',
        'EDITOR',
        'edfile',
        'edvar',
        ]

import abc
import errno
import os
import pexpect
import re
import shutil
import subprocess
import sys
import time
import types
import logging
log = logging.getLogger(__name__)

from qip.app import app  # Also setup log.verbose
from qip.utils import byte_decode

def dbg_exec_cmd(cmd, hidden_args=[], log_append='', **kwargs):
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
    return subprocess.check_output(cmd + hidden_args, **kwargs)

def do_exec_cmd(cmd, log_append='', **kwargs):
    if getattr(app.args, 'dry_run', False):
        log.verbose('CMD (dry-run): %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
        return ''
    else:
        return dbg_exec_cmd(cmd, log_append=log_append, **kwargs)

def dbg_system_cmd(cmd, hidden_args=[], log_append='', **kwargs):
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
    return os.system(subprocess.list2cmdline(cmd + hidden_args), **kwargs)

def do_system_cmd(cmd, log_append='', **kwargs):
    if getattr(app.args, 'dry_run', False):
        log.verbose('CMD (dry-run): %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
        return ''
    else:
        return dbg_system_cmd(cmd, log_append=log_append, **kwargs)

def suggest_exec_cmd(cmd, **kwargs):
    log.info('SUGGEST: %s', subprocess.list2cmdline(cmd))

def dbg_spawn_cmd(cmd, hidden_args=[], no_status=False, yes=False, logfile=True):
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.verbose('CMD: %s', subprocess.list2cmdline(cmd))
    out = ''
    if logfile is True:
        logfile = sys.stdout.buffer
    elif logfile is False:
        logfile = None
    p = pexpect.spawn(cmd[0], args=cmd[1:] + hidden_args, timeout=None,
            logfile=logfile)
    while True:
        index = p.expect([
            r'Select match, 0 for none(?: \[0-\d+\]\?\r*\n)?',  # 0
            r'File \'.*\' already exists\. Overwrite \? \[y/N\] $',  # 1
            r'.*[\r\n]',  # 2
            pexpect.EOF,  # 3
            ])
        if index == 2:
            #app.log.debug('<<< %s%s', byte_decode(p.before), byte_decode(p.match.group(0)))
            out += byte_decode(p.before) + byte_decode(p.match.group(0))
        elif index == 0:
            #app.log.debug('<<< %s%s', byte_decode(p.before), p.match.group(0))
            #puts [list <<< $expect_out(buffer)]
            out += byte_decode(p.before) + byte_decode(p.match.group(0))
            logfile = p.logfile
            logfile_send = p.logfile_send
            try:
                if yes:
                    s = "0"
                else:
                    print('<interact>', end='', flush=True)
                    s = input()
                    print('</interact>', end='', flush=True)
                    p.logfile = None
                    p.logfile_send = None
                #app.log.debug('>>> sending %r', s)
                p.send(s)
                #puts [list >>> sending eol]
                p.send('\r')
            finally:
                p.logfile_send = logfile_send
                p.logfile = logfile
        elif index == 1:
            #app.log.debug('<<< %s%s', byte_decode(p.before), p.match.group(0))
            #puts [list <<< $expect_out(buffer)]
            out += byte_decode(p.before) + byte_decode(p.match.group(0))
            logfile = p.logfile
            logfile_send = p.logfile_send
            try:
                if yes:
                    s = "y"
                else:
                    print('<interact>', end='', flush=True)
                    s = input()
                    print('</interact>', end='', flush=True)
                    p.logfile = None
                    p.logfile_send = None
                #app.log.debug('>>> sending %r', s)
                p.send(s)
                #puts [list >>> sending eol]
                p.send('\r')
            finally:
                p.logfile_send = logfile_send
                p.logfile = logfile
        elif index == 3:
            #app.log.debug('<<< %s%s', byte_decode(p.before))
            out += byte_decode(p.before)
            break
    try:
        p.wait()
    except pexpect.ExceptionPexpect as err:
        if err.value != 'Cannot wait for dead child process.':
            raise
    p.close()
    if p.signalstatus is not None:
        raise Exception('Command exited due to signal %r' % (p.signalstatus,))
    if not no_status and p.exitstatus:
        raise subprocess.CalledProcessError(
                returncode=p.exitstatus,
                cmd=subprocess.list2cmdline(cmd),
                output=out)
    return out

def do_spawn_cmd(cmd, **kwargs):
    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(cmd))
        return ''
    else:
        return dbg_spawn_cmd(cmd, **kwargs)

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

    run_func = None

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

    def build_cmd(self, *args, **kwargs):
        return [self.which()] \
                + list(str(e) for e in args) \
                + self.kwargs_to_cmdargs(**kwargs)

    def _run(self, *args, run_func=None, dry_run=False, **kwargs):
        d = types.SimpleNamespace()
        cmd = self.build_cmd(*args, **kwargs)
        if dry_run:
            log.verbose('CMD (dry-run): %s',
                        subprocess.list2cmdline(cmd))
            d.out = ''
            d.elapsed_time = 0
        else:
            if run_func is None:
                run_func = self.run_func
            if run_func is None:
                t0 = time.time()
                d.out = do_exec_cmd(cmd, stderr=subprocess.STDOUT)
                #d.subprocess_info = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                t1 = time.time()
                #d.out = d.subprocess_info.stdout
            else:
                t0 = time.time()
                d.out = run_func(cmd)
                t1 = time.time()
            d.elapsed_time = t1 - t0
        return d

    run = __call__ = _run

class Editor(Executable):

    _name = None
    @property
    def run_func(self):
        return do_system_cmd

    @property
    def name(self):
        editor = self._name
        if not editor:
            editor = os.environ.get('EDITOR', None)
        if not editor:
            for e in ('vim', 'vi', 'emacs'):
                editor = shutil.which(e)
                if editor:
                    break
        if not editor:
            raise Exception('No editor found; Please set \'EDITOR\' environment variable.')
        return editor

    @name.setter
    def name(self, value):
        self._name = value

EDITOR = Editor()

# edfile {{{

def edfile(file):
    file = str(file)
    startMtime = os.path.getmtime(file)
    EDITOR(file)
    return os.path.getmtime(file) != startMtime

# }}}
# edvar {{{

def edvar(value, *, encoding='utf-8'):
    from qip.file import TempFile
    from qip import json
    import tempfile

    with TempFile(file_name=None) as tmp_file:
        fd, tmp_file.file_name = tempfile.mkstemp(suffix='.json', text=True)
        with os.fdopen(fd, 'w') as fp:
            json.dump(value, fp, indent=2, sort_keys=True, ensure_ascii=False)
            print('', file=fp)
        if not edfile(tmp_file):
            return (False, value)
        with tmp_file.open(mode='r', encoding=encoding) as fp:
            new_value = json.load(fp)
            #if type(new_value) is not type(value):
            #    raise ValueError(new_value)
            return (True, new_value)

# }}}

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
