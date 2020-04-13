
__all__ = [
        'SpawnedProcessError',
        'dbg_exec_cmd',
        'do_exec_cmd',
        'suggest_exec_cmd',
        'dbg_system_cmd',
        'do_system_cmd',
        'dbg_popen_cmd',
        'do_popen_cmd',
        'dbg_spawn_cmd',
        'do_spawn_cmd',
        'clean_cmd_output',
        'Executable',
        'PipedExecutable',
        'PipedScript',
        'PipedPortableScript',
        'XdgExecutable',
        'do_srun_cmd',
        'do_sbatch_cmd',
        'EDITOR',
        'DIFFTOOL',
        'edfile',
        'edvar',
        'eddiff',
        'xdg_open',
        'nice',
        'renice',
        'ionice',
        'list2cmdlist',
        'list2cmdline',
        'stdout_wrapper',
        ]

from pathlib import Path
import abc
import collections
import enum
import errno
import functools
import logging
import os
import pexpect
import pexpect.popen_spawn
import pexpect.spawnbase
import pexpect.utils
import pexpect.fdpexpect
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import types
import xdg
import xml.etree.ElementTree as ET
log = logging.getLogger(__name__)

from qip.app import app  # Also setup log.verbose
from qip.utils import byte_decode
from qip.xdg import XdgResource

_mswindows = (sys.platform == "win32")

try:
    from queue import Queue, Empty  # Python 3
except ImportError:
    from Queue import Queue, Empty  # Python 2

def arg2cmdarg(arg):
    return (os.fspath(arg) if isinstance(arg, os.PathLike)
            else (
                str(arg)))

def list2cmdlist(cmd):
    return [arg2cmdarg(e) for e in cmd]

def list2cmdline(cmd):
    return subprocess.list2cmdline(
        list2cmdlist(cmd))

class SpawnedProcessError(subprocess.CalledProcessError):

    def __init__(self, returncode, cmd, output=None, stderr=None, spawn=None):
        self.spawn = spawn
        super().__init__(returncode=returncode, cmd=cmd, output=output, stderr=stderr)


class _SpawnMixin(pexpect.spawnbase.SpawnBase):

    def __init__(self, *args, errors=None, **kwargs):
        super().__init__(*args, codec_errors=errors, **kwargs)

    def communicate(self, pattern_dict, **kwargs):
        pattern_kv_list = list(pattern_dict.items())
        pattern_list = [k for k, v in pattern_kv_list]
        compiled_pattern_list = self.compile_pattern_list(pattern_list)
        while True:
            idx = self.expect_list(compiled_pattern_list, **kwargs)
            if idx is None:
                break
            k, v = pattern_kv_list[idx]
            yield v

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if exc_type and not getattr(self, 'closed', True):
            self.close(force=True)
        try:
            if not self.terminated:
                try:
                    self.wait()
                except pexpect.ExceptionPexpect as err:
                    if err.value != 'Cannot wait for dead child process.':
                        raise
        finally:
            if not getattr(self, 'closed', True):
                self.close()

class spawn(_SpawnMixin, pexpect.spawn):

    def __init__(self, command, args=[],
                 **kwargs):
        if command is not None:
            command = os.fspath(command)
        args = list2cmdlist(args)
        super().__init__(command=command, args=args,
                         **kwargs)

class fdspawn(_SpawnMixin, pexpect.fdpexpect.fdspawn):

    def __init__(self, fd, command=None, args=None,
                 cwd=None,
                 **kwargs):
        assert cwd is None  # Not supported by pexpect.fdpexpect.fdspawn
        super().__init__(fd=fd, args=args, **kwargs)
        self.args = args  # pexpect.fdpexpect.fdspawn sets to None
        self.command = command  # pexpect.fdpexpect.fdspawn sets to None

    def close(self, *, force=None, **kwargs):
        return super().close(
            # force=force  # Not supported by pexpect.fdpexpect.fdspawn
            **kwargs)

class popen_spawn(_SpawnMixin, pexpect.popen_spawn.PopenSpawn):
    # See pexpect/popen_spawn.py

    def __init__(self, cmd, *, timeout=30, maxread=2000, searchwindowsize=None,
                 logfile=None, env=None, encoding=None,
                 errors='strict', preexec_fn=None,
                 bufsize=0,
                 stdin=None, stdout=None, stderr=None,
                 read_from='auto',
                 **kwargs):
        pexpect.spawnbase.SpawnBase.__init__(  # Skip pexpect.popen_spawn.PopenSpawn!
                self, timeout=timeout, maxread=maxread,
                searchwindowsize=searchwindowsize, logfile=logfile,
                encoding=encoding, codec_errors=errors)

        # Note that `SpawnBase` initializes `self.crlf` to `\r\n`
        # because the default behaviour for a PTY is to convert
        # incoming LF to `\r\n` (see the `onlcr` flag and
        # https://stackoverflow.com/a/35887657/5397009). Here we set
        # it to `os.linesep` because that is what the spawned
        # application outputs by default and `popen` doesn't translate
        # anything.
        if encoding is None:
            self.crlf = os.linesep.encode ("ascii")
        else:
            self.crlf = self.string_type (os.linesep)

        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs['startupinfo'] = startupinfo
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

        if isinstance(cmd, pexpect.utils.string_types) and sys.platform != 'win32':
            cmd = shlex.split(cmd, posix=os.name == 'posix')

        if read_from == 'auto':
            if stdout == subprocess.PIPE:
                read_from = 'stdout'
            elif stderr == subprocess.PIPE:
                read_from = 'stderr'
            else:
                # raise ValueError('read_from not set and neither stdout nor stderr are pipes')
                read_from = None

        self.proc = subprocess.Popen(cmd,
                                     bufsize=bufsize,
                                     stdin=stdin, stdout=stdout, stderr=stderr,
                                     **kwargs)
        self.pid = self.proc.pid
        self.closed = False
        self._buf = self.string_type()


        self._read_from = read_from
        if self._read_from:
            self._read_queue = Queue()
            self._read_thread = threading.Thread(target=self._read_incoming)
            self._read_thread.setDaemon(True)
            self._read_thread.start()
        else:
            self._read_reached_eof = True

    def _read_incoming(self):
        """Run in a thread to move output from a pipe to a queue."""
        fileno = getattr(self.proc, self._read_from).fileno()
        while 1:
            buf = b''
            try:
                buf = os.read(fileno, 1024)
            except OSError as e:
                self._log(e, 'read')

            if not buf:
                # This indicates we have reached EOF
                self._read_queue.put(None)
                return

            self._read_queue.put(buf)

    def close(self, force=True):
        # Missing from pexpect.popen_spawn.PopenSpawn!
        if not force and self.proc.stdin:
            self.flush()
            self.sendeof()
        self.kill(signal.SIGKILL if force else signal.SIGTERM)
        self.closed = True

def dbg_exec_cmd(cmd, *, hidden_args=[],
                 dry_run=None, log_append='', return_CompletedProcess=False,
                 fd=None,
                 stdout=None,
                 **kwargs):
    assert fd is None
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    list2cmdline(cmd),
                    log_append)
    # return subprocess.check_output(cmd + hidden_args, **kwargs)
    if 'input' in kwargs and kwargs['input'] is None:
        # Explicitly passing input=None was previously equivalent to passing an
        # empty string. That is maintained here for backwards compatibility.
        kwargs['input'] = '' if kwargs.get('universal_newlines', False) else b''
    if stdout is None:
        stdout = subprocess.PIPE
    cmd = list2cmdlist(cmd)
    hidden_args = list2cmdlist(hidden_args)
    run_out = subprocess.run(cmd + hidden_args,
                             stdout=stdout,
                             check=True, **kwargs)
    if return_CompletedProcess:
        return run_out
    else:
        return run_out.stdout

def do_exec_cmd(cmd, *,
                dry_run=None, log_append='', return_CompletedProcess=False,
                **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        log.verbose('CMD (dry-run): %s%s',
                    list2cmdline(cmd),
                    log_append)
        if return_CompletedProcess:
            return subprocess.CompletedProcess(args=None, returncode=0, stdout='', stderr='')
        else:
            return ''
    else:
        return dbg_exec_cmd(cmd, log_append=log_append, return_CompletedProcess=return_CompletedProcess, **kwargs)

def suggest_exec_cmd(cmd, dry_run=None, **kwargs):
    log.info('SUGGEST: %s',
             list2cmdline(cmd))

def dbg_system_cmd(cmd, *, hidden_args=[], dry_run=None, log_append='',
                   cwd=None,
                   fd=None,
                   encoding=None, errors=None, text=None,
                   **kwargs):
    assert fd is None
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    list2cmdline(cmd),
                    log_append)
    # text_mode = text or encoding or errors
    assert not kwargs, kwargs
    assert cwd is None
    return os.system(list2cmdline(cmd),
                     **kwargs)

def do_system_cmd(cmd, *, dry_run=None, log_append='', **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        log.verbose('CMD (dry-run): %s%s',
                    list2cmdline(cmd),
                    log_append)
        return ''
    else:
        return dbg_system_cmd(cmd, log_append=log_append, **kwargs)

def dbg_popen_cmd(cmd, *, hidden_args=[], dry_run=None, log_append='', **kwargs):
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    list2cmdline(cmd),
                    log_append)
    cmd = list2cmdlist(cmd)
    hidden_args = list2cmdlist(hidden_args)
    return subprocess.Popen(cmd + hidden_args, **kwargs)

def do_popen_cmd(cmd, *, dry_run=None, log_append='', **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        log.verbose('CMD (dry-run): %s%s',
                    list2cmdline(cmd),
                    log_append)
        import contextlib
        p = types.SimpleNamespace()
        pcm = contextlib.nullcontext(p)
        scm = contextlib.nullcontext(None)
        pcm.stdout = p.stdout = scm
        return pcm
    else:
        return dbg_popen_cmd(cmd, log_append=log_append, **kwargs)

def dbg_popen_spawn_cmd(cmd, *, hidden_args=[], dry_run=None, log_append='', **kwargs):
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    list2cmdline(cmd),
                    log_append)
    return popen_spawn(cmd + hidden_args, **kwargs)

def do_popen_spawn_cmd(cmd, *, dry_run=None, log_append='', **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        log.verbose('CMD (dry-run): %s%s',
                    list2cmdline(cmd),
                    log_append)
        import contextlib
        p = types.SimpleNamespace()
        pcm = contextlib.nullcontext(p)
        scm = contextlib.nullcontext(None)
        pcm.stdout = p.stdout = scm
        return pcm
    else:
        return dbg_popen_spawn_cmd(cmd, log_append=log_append, **kwargs)

def dbg_spawn_cmd(cmd, hidden_args=[],
                  fd=None,
                  dry_run=None, no_status=False, yes=False, logfile=True,
                  cwd=None,
                  encoding=None, errors=None,
                  ):
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.verbose('CMD: %s',
                        list2cmdline(cmd))
    out = ''
    if logfile is True:
        logfile = sys.stdout.buffer
    elif logfile is False:
        logfile = None
    spawn_func = functools.partial(fdspawn, fd=fd) if fd is not None else spawn
    p = spawn_func(cmd[0], args=cmd[1:] + hidden_args, timeout=None,
                   cwd=cwd,
                   encoding=encoding, errors=errors,
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
                cmd=list2cmdline(cmd),
                output=out)
    return out

def do_spawn_cmd(cmd, dry_run=None, **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        app.log.verbose('CMD (dry-run): %s',
                        list2cmdline(cmd))
        return ''
    else:
        return dbg_spawn_cmd(cmd, **kwargs)

def clean_cmd_output(out):
    out = byte_decode(out)
    out = re.sub(r'\x1B\[[0-9;]*m', '', out)
    out = re.sub(r'\r\n', '\n', out)
    out = re.sub(r'.*\r', '', out, flags=re.MULTILINE)
    out = re.sub(r'\t', ' ', out)
    out = re.sub(r' +$', '', out, flags=re.MULTILINE)
    return out

class IoniceClass(enum.IntEnum):
    # None = 0
    Realtime = 1
    BestEffort = 2
    Idle = 3


class FakeDryRunPopen(subprocess.Popen):

    def __init__(self, args, *,
                 stdin=None, stdout=None, stderr=None,
                 **kwargs):
        self._in_stdout = stdout
        self._in_stderr = stderr
        super().__init__(args=args,
                         stdin=None, stdout=None, stderr=None,
                         **kwargs)

    def _execute_child(self, *args, **kwargs):
        self._child_created = False
        self._closed_child_pipe_fds = True

    def communicate(self, *args, **kwargs):
        self._communication_started = True
        self.returncode = 0
        stdout = ('' if self.text_mode else b'') if self._in_stdout == subprocess.PIPE else None
        stderr = ('' if self.text_mode else b'') if self._in_stderr == subprocess.PIPE else None
        return (stdout, stderr)


class Args(object):
    """Save given arguments and keywords.
    """

    def __new__(cls,
                # 3.8: /,
                *args, **keywords):

        self = super(Args, cls).__new__(cls)

        self.args = args
        self.keywords = keywords
        return self

    @classmethod
    def new_from(cls, other):
        if isinstance(other, Args):
            return Args(*other.args, **other.keywords)
        if isinstance(other, collections.Mapping):
            return Args(**other)
        if isinstance(other, collections.Sequence):
            return Args(*other)
        raise TypeError(other)

    def __add__(self, other):
        args = self.args + other.args
        keywords = dict(self.keywords)
        keywords.update(other.keywords)
        return self.__class__(*args, **keywords)


class Executable(metaclass=abc.ABCMeta):

    Args = Args

    popen_class = subprocess.Popen

    run_func = None
    run_func_options = tuple()
    popen_func = None
    popen_func_options = tuple()

    encoding = None
    encoding_errors = None

    nice_adjustment = None
    ionice_class = None
    ionice_level = None
    ionice_ignore = True

    needs_tty = False

    def _spawn_run_func(self, cmd=None, *, fd=None, hidden_args=[], dry_run=None, no_status=False, logfile=None,
                        stdin=None, stdout=None, stderr=None,
                        encoding=None, errors=None, text=None, universal_newlines=None,
                        **kwargs):

        if universal_newlines:
            # Backward compatibility
            text = True

        text_mode = encoding or errors or text
        if text_mode and encoding is None:
            # Sane default -- See _pyio.py TextIOWrapper
            encoding = 'utf-8'

        if stdin or stdout or stderr:
            stdin = stdin or subprocess.PIPE
            stdout = stdout or subprocess.PIPE
            stderr = stderr or subprocess.STDOUT  # Default from Executable._run
            assert self.popen_func and self.popen_spawn, f'self={self!r}: popen_func={self.popen_func!r} and popen_spawn={self.popen_spawn!r}'
            assert logfile is None
            assert no_status == False
            assert fd is None
            return self.popen(cmd, hidden_args=hidden_args, dry_run=dry_run,
                              stdin=stdin, stdout=stdout, stderr=stderr,
                              encoding=encoding, errors=errors, text=text,
                              **kwargs)

        if fd is not None:
            if cmd is None:
                cmd = ['<fd>']

        if dry_run is None:
             dry_run = getattr(app.args, 'dry_run', False)
        if dry_run:
            app.log.verbose('CMD (dry-run): %s',
                            list2cmdline(cmd))
            return ''
        if logfile is True:
            logfile = sys.stdout.buffer
        elif logfile is False:
            logfile = None
        if app.log.isEnabledFor(logging.DEBUG):
            app.log.verbose('CMD: %s',
                            list2cmdline(cmd))

        spawn_func = functools.partial(self.fdspawn, fd=fd) if fd is not None else self.spawn
        p = spawn_func(cmd[0], args=cmd[1:] + hidden_args, logfile=logfile,
                       encoding=encoding, errors=errors,  # text=text,
                       **kwargs)
        with p:
            pattern_dict = p.get_pattern_dict()
            out = '' if text_mode else b''
            for v in p.communicate(pattern_dict=pattern_dict):
                out += p.before
                if p.match and p.match is not pexpect.EOF:
                    out += p.match.group(0)
                if callable(v):
                    if p.match is pexpect.EOF:
                        b = v(None)
                    else:
                        b = v(p.match.group(0))
                    if not b:
                        break
                if p.after is pexpect.EOF:
                    break
        if p.signalstatus is not None:
            raise Exception('Command exited due to signal %r' % (p.signalstatus,))
        if not no_status and p.exitstatus:
            raise SpawnedProcessError(
                returncode=p.exitstatus,
                cmd=list2cmdline(cmd),
                output=out,
                spawn=p)
        if text_mode:
            out = byte_decode(out)
        return {
            'out': out,
            'spawn': p,
        }

    def _spawn_popen_func(self, cmd, hidden_args=[], dry_run=None, no_status=False, logfile=None, **kwargs):
        if dry_run is None:
             dry_run = getattr(app.args, 'dry_run', False)
        if dry_run:
            app.log.verbose('CMD (dry-run): %s',
                            list2cmdline(cmd))
            return ''
        if app.log.isEnabledFor(logging.DEBUG):
            app.log.verbose('CMD: %s',
                            list2cmdline(cmd))
        if logfile is True:
            logfile = sys.stdout.buffer
        elif logfile is False:
            logfile = None
        p = self.popen_spawn(cmd + hidden_args, logfile=logfile, **kwargs)
        with p:
            pattern_dict = p.get_pattern_dict()
            out = ''
            for v in p.communicate(pattern_dict=pattern_dict):
                out += byte_decode(p.before)
                if p.match and p.match is not pexpect.EOF:
                    out += byte_decode(p.match.group(0))
                if callable(v):
                    if p.match is pexpect.EOF:
                        b = v(None)
                    else:
                        b = v(p.match.group(0))
                    if not b:
                        break
                if p.after is pexpect.EOF:
                    break
        if p.signalstatus is not None:
            raise Exception('Command exited due to signal %r' % (p.signalstatus,))
        if not no_status and p.exitstatus:
            raise SpawnedProcessError(
                returncode=p.exitstatus,
                cmd=list2cmdline(cmd),
                output=out,
                spawn=p)
        return out

    @property
    @abc.abstractmethod
    def name(self):
        raise NotImplementedError

    def which(self, mode=os.F_OK | os.X_OK, path=None, assert_found=True):
        cmd = shutil.which(os.fspath(self.name), mode=mode, path=path)
        if cmd is None and assert_found:
            raise OSError(errno.ENOENT, 'Command not found', self.name)
        return cmd

    @classmethod
    def clean_cmd_output(cls, out):
        return clean_cmd_output(out)

    @classmethod
    def kwargs_to_cmdargs(cls, **kwargs):
        if kwargs:
            raise ValueError('Unsupported keyword arguments: %r' % (kwargs,))
        return []

    @classmethod
    def kwargs_to_cmdargs_gnu_getopt(cls, **kwargs):
        cmdargs = []
        for k, v in kwargs.items():
            if v in (None, False):
                # Dropped for ease of passing unused arguments
                continue
            k = {
                '_class': 'class',
                '_continue': 'continue',
            }.get(k, k)
            if len(k) == 1:
                cmdargs.append('-' + k)
            else:
                cmdargs.append('--' + k)
            if v is not True:
                cmdargs.append(arg2cmdarg(v))
        return cmdargs

    @classmethod
    def kwargs_to_cmdargs_win_slash(cls, **kwargs):
        cmdargs = []
        for k, v in kwargs.items():
            if v in (None, False):
                # Dropped for ease of passing unused arguments
                continue
            k = {
                '_class': 'class',
                '_continue': 'continue',
            }.get(k, k)
            cmdargs.append('/' + k)
            if v is not True:
                cmdargs.append(arg2cmdarg(v))
        return cmdargs

    def build_cmd(self, *args, **kwargs):
        nice_adjustment = kwargs.pop('nice_adjustment', self.nice_adjustment)
        ionice_class = kwargs.pop('ionice_class', self.ionice_class)
        ionice_level = kwargs.pop('ionice_level', self.ionice_level)
        ionice_ignore = kwargs.pop('ionice_ignore', self.ionice_ignore)

        cmd = [self.which()] \
            + list2cmdlist(args) \
            + self.kwargs_to_cmdargs(**kwargs)

        if ionice_class is not None or ionice_level is not None:
            if ionice_class is not None:
                ionice_class = int(IoniceClass(ionice_class))
            if ionice_level is not None:
                ionice_level = int(ionice_level)
            if ionice_ignore is not None:
                ionice_ignore = bool(ionice_ignore)
            cmd = ionice.build_cmd(*cmd,
                                   _class=ionice_class,
                                   classdata=ionice_level,
                                   ignore=ionice_ignore,
                                   )

        if nice_adjustment is not None:
            if nice_adjustment is not None:
                nice_adjustment = int(nice_adjustment)
            cmd = nice.build_cmd(*cmd,
                                 adjustment=nice_adjustment,
                                 )

        return cmd

    def popen_new(self, *args,
                  cwd=None,
                  stdin=None, stdout=None, stderr=None,
                  capture_output=False,
                  text=None, encoding=None, errors=None,
                  dry_run=None,
                  **kwargs):
        if dry_run is None:
             dry_run = getattr(app.args, 'dry_run', False)

        if capture_output:
            if stdout is not None or stderr is not None:
                raise ValueError('stdout and stderr arguments may not be used '
                                 'with capture_output.')
            stdout = subprocess.PIPE
            stderr = subprocess.PIPE

        cmd = self.build_cmd(*args, **kwargs)
        cmd = list2cmdlist(cmd)
        text_mode, encoding, errors = self.get_text_mode_info(
            cmd=cmd, text=text, encoding=encoding, errors=errors)

        if dry_run:
            log.verbose('CMD (dry-run): %s',
                        list2cmdline(cmd))
            popen_class = FakeDryRunPopen
        else:
            if log.isEnabledFor(logging.DEBUG):
                log.verbose('CMD: %s',
                            list2cmdline(cmd))
            popen_class = self.popen_class

        return popen_class(cmd,
                           cwd=cwd,
                           stdin=stdin, stdout=stdout, stderr=stderr,
                           encoding=encoding, errors=errors,
                           **kwargs)

    def run_new(self, *args,
                cwd=None,
                stdin=None, stdout=None, stderr=None,
                capture_output=False,
                text=None, encoding=None, errors=None,
                timeout=None, check=False,
                dry_run=None,
                **kwargs):

        with self.popen_new(*args,
                            cwd=cwd,
                            stdin=stdin, stdout=stdout, stderr=stderr,
                            capture_output=capture_output,
                            encoding=encoding, errors=errors,
                            dry_run=dry_run,
                            **kwargs) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except TimeoutExpired as exc:
                process.kill()
                if _mswindows:
                    # Windows accumulates the output in a single blocking
                    # read() call run on child threads, with the timeout
                    # being done in a join() on those threads.  communicate()
                    # _after_ kill() is required to collect that and add it
                    # to the exception.
                    exc.stdout, exc.stderr = process.communicate()
                else:
                    # POSIX _communicate already populated the output so
                    # far into the TimeoutExpired exception.
                    process.wait()
                raise
            except:  # Including KeyboardInterrupt, communicate handled that.
                process.kill()
                # We don't call process.wait() as .__exit__ does that for us.
                raise
            retcode = process.poll()
        comp = subprocess.CompletedProcess(process.args, retcode, stdout, stderr)
        if check:
            comp.check_returncode()
        return comp

    def _run(self, *args,
             fd=None,
             cwd=None,
             run_func=None, dry_run=False,
             **kwargs):
        #print(f'Executable._run(args={args!r}, fd={fd!r}, cwd={cwd!r}, run_func={run_func!r}, dry_run={dry_run!r}, kwargs={kwargs!r}')
        d = types.SimpleNamespace()

        run_func_kwargs = {}
        for k in self.run_func_options:
            try:
                run_func_kwargs[k] = kwargs.pop(k)
            except KeyError:
                pass
        run_func_kwargs.setdefault('encoding', self.encoding)
        run_func_kwargs.setdefault('errors', self.encoding_errors)
        cmd = self.build_cmd(*args, **kwargs)
        cmd = list2cmdlist(cmd)

        run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)

        t0 = time.time()
        out = run_func(cmd, fd=fd,
                       cwd=cwd,
                       dry_run=dry_run,
                       **run_func_kwargs)
        if isinstance(out, collections.abc.Mapping):
            for k, v in out.items():
                setattr(d, k, v)
        else:
            d.out = out
        t1 = time.time()
        d.elapsed_time = t1 - t0
        return d

    def run(self, *args, **kwargs):
        return self._run(*args, **kwargs)

    __call__ = run

    def popen(self, *args, **kwargs):
        return self._popen(*args, **kwargs)

    def get_text_mode_info(self, cmd=None, text=None, encoding=None, errors=None):
        encoding = encoding or self.encoding
        errors = errors or self.encoding_errors
        text_mode = bool(text or encoding or errors)
        if text_mode:
            if encoding is None:
                encoding = 'utf-8'
            if errors is None:
                errors = 'strict'
        return text_mode, encoding, errors

    def _popen(self, *args, popen_func=None, dry_run=False,
               cwd=None,
               stdin=None, stdout=None, stderr=None,
               text=None, encoding=None, bufsize=-1,
               **kwargs):
        text_mode, encoding, errors = self.get_text_mode_info(text=text, encoding=encoding)
        """p1 = myexe1.popen([...], stdout=subprocess.PIPE)
           p2 = myexe2.popen([...], stdin=p1.stdout, stdout=myfile.fp)
        """
        popen_func_kwargs = {}
        for k in self.popen_func_options:
            try:
                popen_func_kwargs[k] = kwargs.pop(k)
            except KeyError:
                pass
        cmd = self.build_cmd(*args, **kwargs)
        cmd = list2cmdlist(cmd)
        popen_func = popen_func or self.popen_func or do_popen_cmd
        return popen_func(
            cmd,
            cwd=cwd,
            dry_run=dry_run,
            stdin=stdin, stdout=stdout, stderr=stderr,
            encoding=encoding, errors=errors,
            universal_newlines=text,  # 3.7: text=text
            bufsize=bufsize,
            **popen_func_kwargs,
            )

class PipedExecutable(Executable):
    pass

class PipedScript(PipedExecutable):
    pass

class PipedPortableScript(PipedScript):
    pass

class XdgExecutable(Executable, XdgResource):

    @property
    def xdg_resource(self):
        return self.name

class Xdg_open(Executable):

    name = 'xdg-open'

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

xdg_open = Xdg_open()


class Nice(Executable):

    name = 'nice'

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def build_cmd(self, *args, **kwargs):
        # kwargs before args
        cmd = [self.which()] \
            + self.kwargs_to_cmdargs(**kwargs) \
            + list2cmdlist(args)
        return cmd

nice = Nice()


class Renice(Executable):

    name = 'renice'

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def build_cmd(self, *args, **kwargs):
        keys1 = set(kwargs.keys())
        keys2 = keys1 & {
            'g', 'pgrp',
            'p', 'pid',
            'u', 'user',
        }
        keys1 -= keys2
        cmd = [self.which()] \
            + self.kwargs_to_cmdargs(**{k: v for k, v in kwargs.items() if k in keys1}) \
            + self.kwargs_to_cmdargs(**{k: v for k, v in kwargs.items() if k in keys2}) \
            + list2cmdlist(args)
        return cmd

renice = Renice()


class Ionice(Executable):

    name = 'ionice'

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def build_cmd(self, *args, **kwargs):
        keys1 = set(kwargs.keys())
        keys2 = keys1 & {
            'p', 'pid',
            'P', 'pgid',
        }
        keys1 -= keys2
        cmd = [self.which()] \
            + self.kwargs_to_cmdargs(**{k: v for k, v in kwargs.items() if k in keys1}) \
            + self.kwargs_to_cmdargs(**{k: v for k, v in kwargs.items() if k in keys2}) \
            + list2cmdlist(args)
        return cmd

ionice = Ionice()


class PipeRecordThread(threading.Thread):

    def __init__(self, file_r=None, text=False, blocksize=1024*8, target=None, **kwargs):
        if file_r is None:
            r, w = os.pipe()
            self.file_r = os.fdopen(r, mode='r' + ('t' if text else 'b'), closefd=True)
            self.file_w = os.fdopen(w, mode='w' + ('t' if text else 'b'), closefd=True)
        self.text = text
        if self.text:
            self.output = ''
        else:
            self.output = b''
            self.blocksize = blocksize
        super().__init__(**kwargs)

    def run(self):
        file_r = self.file_r
        target = self.target
        if self.text:
            for line in file_r:
                line = byte_decode(line)
                self.output += line
                if target:
                    target(line)
        else:
            blocksize = self.blocksize
            while True:
                out = file_r.read(blocksize)
                if not out:
                    break
                self.output += out
                if target:
                    target(out)

class SlurmError(Exception):

    def __init__(self, msg, *, cmd, out):
        self.cmd = cmd
        self.out = out
        super().__init__(msg)


def do_srun_cmd(cmd,
        fd=None,
        stdin=None, stdin_file=None,
        stdout=None, stdout_file=None,
        stderr=None, stderr_file=None,
        slurm_priority=100,
        slurm_cpus_per_task=None,
        slurm_mem=None,
        slurm_tmp=None,
        slurm_job_name=None,
        slurm_kill_on_bad_exit=True,
        chdir=None,
        uid=None,
        cwd=None,
        dry_run=None,
        encoding=None, errors=None, text=None,
        ):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    slurm_args = [
        'srun',
        ]

    assert fd is None

    gres_args = []
    if stdin_file is not None:
        assert stdin is None
        slurm_args += ['--input', stdin_file]
    if stdout_file is not None:
        assert stdout is None
        if False:
            slurm_args += ['--output', stdout_file]
        else:
            slurm_args = stdout_wrapper.build_cmd(stdout_file) + slurm_args
    if stderr_file is not None:
        assert stderr is None
        slurm_args += ['--error', stderr_file]
    if slurm_priority is not None:
        slurm_args += ['--priority', slurm_priority]
    if slurm_cpus_per_task is not None:
        slurm_args += ['--cpus-per-task', slurm_cpus_per_task]
    if slurm_mem is not None:
        slurm_args += ['--mem', slurm_mem]
    if slurm_tmp is not None:
        #slurm_args += ['--tmp', '%dK' % (slurm_tmp / 1024,)]
        gres_args.append('tmp:%d' % (slurm_tmp,))
    if slurm_job_name is not None:
        slurm_args += ['--job-name', slurm_job_name]
    if slurm_kill_on_bad_exit is not None:
        slurm_args += ['--kill-on-bad-exit=%d' % (1 if slurm_kill_on_bad_exit else 0,)]
    if chdir is not None:
        slurm_args += ['--chdir', chdir]
    if uid is not None:
        slurm_args += ['--uid', uid]
    if gres_args:
        slurm_args += ['--gres', ','.join(gres_args)]

    slurm_args.extend(cmd)
    slurm_args = list2cmdlist(slurm_args)
    thread = PipeRecordThread(text=True)
    assert stderr is None
    def stderr_copier(out):
        print(out, end='', file=sys.stderr, flush=True)
    thread.target = stderr_copier
    thread.start()
    try:
        run_out = do_exec_cmd(slurm_args,
                              cwd=cwd,
                              dry_run=dry_run,
                              stdin=stdin, stdout=stdout, stderr=thread.file_w,
                              encoding=encoding, errors=errors, text=text,
                              return_CompletedProcess=True)
    finally:
        thread.file_w.close()
        thread.join()
    run_out.stderr = thread.output
    err = byte_decode(run_out.stderr)
    m = re.search(r'srun: error: .*', err)
    if m:
        err_msg = m.group(0).strip()
        raise SlurmError(err_msg, cmd=slurm_args, out=run_out.stderr)
    return run_out.stdout

def do_sbatch_cmd(cmd,
        stdin=None, stdin_file=None,
        stdout=None, stdout_file=None,
        stderr=None, stderr_file=None,
        slurm_priority=100,
        slurm_cpus_per_task=None,
        slurm_mem=None,
        slurm_tmp=None,
        slurm_job_name=None,
        chdir=None,
        uid=None,
        wait=False,
        cwd=None,
        ):
    slurm_args = [
        'sbatch',
        ]

    gres_args = []
    if stdin_file is not None:
        assert stdin is None
        slurm_args += ['--input', stdin_file]
    if stdout_file is not None:
        assert stdout is None
        if False:
            slurm_args += ['--output', stdout_file]
        else:
            slurm_args = stdout_wrapper.build_cmd(stdout_file) + slurm_args
    if stderr_file is not None:
        assert stderr is None
        slurm_args += ['--error', stderr_file]
    if slurm_priority is not None:
        slurm_args += ['--priority', slurm_priority]
    if slurm_cpus_per_task is not None:
        slurm_args += ['--cpus-per-task', slurm_cpus_per_task]
    if slurm_mem is not None:
        slurm_args += ['--mem', slurm_mem]
    if slurm_tmp is not None:
        #slurm_args += ['--tmp', '%dK' % (slurm_tmp / 1024,)]
        gres_args.append('tmp:%d' % (slurm_tmp,))
    if slurm_job_name is not None:
        slurm_args += ['--job-name', slurm_job_name]
    if chdir is not None:
        slurm_args += ['--chdir', chdir]
    if uid is not None:
        slurm_args += ['--uid', uid]
    if gres_args:
        slurm_args += ['--gres', ','.join(gres_args)]

    if wait:
        slurm_args += ['--wait']

    slurm_args.extend(cmd)
    slurm_args = list2cmdlist(slurm_args)
    return do_exec_cmd(slurm_args,
                       cwd=cwd,
                       stdin=stdin, stdout=stdout, stderr=stderr)

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

class Difftool(Executable):

    _name = None
    @property
    def run_func(self):
        return do_system_cmd

    @property
    def name(self):
        difftool = self._name
        if not difftool:
            difftool = os.environ.get('DIFFTOOL', None)
        if not difftool:
            for e in (
                    'vimdiff',
                    # 'araxis',
                    # 'gvimdiff',
                    # 'gvimdiff2',
                    # 'gvimdiff3',
                    # 'vimdiff2',
                    # 'vimdiff3',
                    # 'bc',
                    # 'bc3',
                    # 'codecompare',
                    # 'deltawalker',
                    # 'diffmerge',
                    # 'diffuse',
                    # 'ecmerge',
                    # 'emerge',
                    # 'examdiff',
                    # 'guiffy',
                    # 'kdiff3',
                    # 'kompare',
                    # 'meld',
                    # 'opendiff',
                    # 'p4merge',
                    # 'smerge',
                    # 'tkdiff',
                    # 'winmerge',
                    # 'xxdiff',
            ):
                difftool = shutil.which(e)
                if difftool:
                    break
        if not difftool:
            raise Exception('No diff tool found; Please set \'DIFFTOOL\' environment variable.')
        return difftool

    @name.setter
    def name(self, value):
        self._name = value

DIFFTOOL = Difftool()

def edfile(file):
    file = Path(file)
    start_mtime = file.stat().st_mtime
    EDITOR(file)
    try:
        modified = file.stat().st_mtime != start_mtime
    except:
        # File removed?
        modified = True
    return modified

def edvar(value, *, json=None, suffix=None, encoding='utf-8',
          preserve_whitespace_tags=None):
    from qip.file import TempFile
    import tempfile
    orig_value = value

    xml = False
    if json is None:
        json = False
        if isinstance(value, str):
            suffix = suffix or '.txt'
        elif isinstance(value, ET.ElementTree):
            xml = True
            from qip.utils import prettyxml
            suffix = suffix or '.xml'
            value = prettyxml(value, preserve_whitespace_tags=preserve_whitespace_tags)
        else:
            json = True
            suffix = suffix or '.json'

    with TempFile.mkstemp(suffix=suffix, text=True, open=True) as tmp_file:

        if json:
            import qip.json
            qip.json.dump(value, tmp_file.fp, indent=2, sort_keys=True, ensure_ascii=False)
            print('', file=tmp_file.fp)
        else:
            tmp_file.write(value)

        tmp_file.close()

        if not edfile(tmp_file):
            return (False, orig_value)

        tmp_file.fp = tmp_file.open(mode='r', encoding=encoding)
        if json:
            new_value = qip.json.load(tmp_file.fp)
        else:
            new_value = tmp_file.read()

    if xml:
        new_value = ET.ElementTree(ET.fromstring(new_value))

    #if type(new_value) is not type(value):
    #    raise ValueError(new_value)
    return (True, new_value)

def eddiff(files):
    files = [Path(file) for file in files]
    start_mtimes = [file.stat().st_mtime for file in files]
    DIFFTOOL(*files)
    try:
        modified = [file.stat().st_mtime for file in files] != start_mtimes
    except:
        # File removed?
        modified = True
    return modified

class Stdout_wrapper(Executable):

    name = Path(__file__).parent / 'bin' / 'stdout-wrapper'

stdout_wrapper = Stdout_wrapper()

# vim: ft=python ts=8 sw=4 sts=4 ai et
