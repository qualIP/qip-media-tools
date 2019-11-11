
__all__ = [
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
        'do_srun_cmd',
        'do_sbatch_cmd',
        'EDITOR',
        'edfile',
        'edvar',
        'nice',
        'renice',
        'ionice',
        ]

import abc
import enum
import errno
import functools
import logging
import os
import pexpect
import re
import shutil
import subprocess
import threading
import sys
import time
import types
import xml.etree.ElementTree as ET
log = logging.getLogger(__name__)

from qip.app import app  # Also setup log.verbose
from qip.utils import byte_decode

class spawn(pexpect.spawn):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

def dbg_exec_cmd(cmd, *, hidden_args=[], dry_run=None, log_append='', return_CompletedProcess=False, **kwargs):
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
    # return subprocess.check_output(cmd + hidden_args, **kwargs)
    if 'input' in kwargs and kwargs['input'] is None:
        # Explicitly passing input=None was previously equivalent to passing an
        # empty string. That is maintained here for backwards compatibility.
        kwargs['input'] = '' if kwargs.get('universal_newlines', False) else b''
    run_out = subprocess.run(cmd + hidden_args, stdout=subprocess.PIPE, check=True, **kwargs)
    if return_CompletedProcess:
        return run_out
    else:
        return run_out.stdout

def do_exec_cmd(cmd, *, dry_run=None, log_append='', return_CompletedProcess=False, **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        log.verbose('CMD (dry-run): %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
        if return_CompletedProcess:
            return subprocess.CompletedProcess(args=None, returncode=0, stdout='', stderr='')
        else:
            return ''
    else:
        return dbg_exec_cmd(cmd, log_append=log_append, return_CompletedProcess=return_CompletedProcess, **kwargs)

def suggest_exec_cmd(cmd, dry_run=None, **kwargs):
    log.info('SUGGEST: %s', subprocess.list2cmdline(cmd))

def dbg_system_cmd(cmd, *, hidden_args=[], dry_run=None, log_append='', **kwargs):
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
    return os.system(subprocess.list2cmdline(cmd + hidden_args), **kwargs)

def do_system_cmd(cmd, *, dry_run=None, log_append='', **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        log.verbose('CMD (dry-run): %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
        return ''
    else:
        return dbg_system_cmd(cmd, log_append=log_append, **kwargs)

def do_popen_cmd(cmd, *, dry_run=None, log_append='', **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        log.verbose('CMD (dry-run): %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
        import contextlib
        p = types.SimpleNamespace()
        pcm = contextlib.nullcontext(p)
        scm = contextlib.nullcontext(None)
        pcm.stdout = p.stdout = scm
        return pcm
    else:
        return dbg_popen_cmd(cmd, log_append=log_append, **kwargs)

def dbg_popen_cmd(cmd, *, hidden_args=[], dry_run=None, log_append='', **kwargs):
    if log.isEnabledFor(logging.DEBUG):
        log.verbose('CMD: %s%s',
                    subprocess.list2cmdline(cmd),
                    log_append)
    return subprocess.Popen(cmd + hidden_args, **kwargs)

def dbg_spawn_cmd(cmd, hidden_args=[], dry_run=None, no_status=False, yes=False, logfile=True):
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

def do_spawn_cmd(cmd, dry_run=None, **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
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

class IoniceClass(enum.IntEnum):
    # None = 0
    Realtime = 1
    BestEffort = 2
    Idle = 3


class Executable(metaclass=abc.ABCMeta):

    run_func = None

    nice_adjustment = None
    ionice_class = None
    ionice_level = None
    ionice_ignore = True

    @property
    @abc.abstractmethod
    def name(self):
        raise NotImplementedError

    def which(self, mode=os.F_OK | os.X_OK, path=None, assert_found=True):
        cmd = shutil.which(self.name, mode=mode, path=path)
        if cmd is None and assert_found:
            raise OSError(errno.ENOENT, 'Command not found', self.name)
        return cmd

    def clean_cmd_output(self, out):
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
                cmdargs.append(str(v))
        return cmdargs

    def build_cmd(self, *args, **kwargs):
        nice_adjustment = kwargs.pop('nice_adjustment', self.nice_adjustment)
        ionice_class = kwargs.pop('ionice_class', self.ionice_class)
        ionice_level = kwargs.pop('ionice_level', self.ionice_level)
        ionice_ignore = kwargs.pop('ionice_ignore', self.ionice_ignore)

        cmd = [self.which()] \
            + list(str(e) for e in args) \
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

    def _run(self, *args, run_func=None, dry_run=False, **kwargs):
        d = types.SimpleNamespace()
        cmd = self.build_cmd(*args, **kwargs)
        run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
        t0 = time.time()
        d.out = run_func(cmd, dry_run=dry_run)
        t1 = time.time()
        d.elapsed_time = t1 - t0
        return d

    def _popen(self, *args, dry_run=False,
               stdin=None, stdout=None, stderr=None,
               text=None, encoding=None, bufsize=-1,
               **kwargs):
        """p1 = myexe1.popen([...], stdout=subprocess.PIPE)
           p2 = myexe2.popen([...], stdin=p1.stdout, stdout=myfile.fp)
        """
        cmd = self.build_cmd(*args, **kwargs)
        return do_popen_cmd(
            cmd,
            dry_run=dry_run,
            stdin=stdin, stdout=stdout, stderr=stderr,
            universal_newlines=text,  # 3.7: text=text
            encoding=encoding,
            bufsize=bufsize,
            )

    def run(self, *args, **kwargs):
        return self._run(*args, **kwargs)

    __call__ = run

    def popen(self, *args, **kwargs):
        return self._popen(*args, **kwargs)

class PipedExecutable(Executable):
    pass

class PipedScript(PipedExecutable):
    pass

class PipedPortableScript(PipedScript):
    pass


class Nice(Executable):

    name = 'nice'

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def build_cmd(self, *args, **kwargs):
        cmd = [self.which()] \
            + self.kwargs_to_cmdargs(**kwargs) \
            + list(str(e) for e in args)
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
            + list(str(e) for e in args)
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
            + list(str(e) for e in args)
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
        dry_run=None,
        ):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    slurm_args = [
        'srun',
        ]

    gres_args = []
    if stdin_file is not None:
        slurm_args += ['--input', stdin_file]
    if stdout_file is not None:
        slurm_args += ['--output', stdout_file]
    if stderr_file is not None:
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

    slurm_args.extend(cmd)
    slurm_args = [str(e) for e in slurm_args]
    thread = PipeRecordThread(text=True)
    def stderr_copier(out):
        print(out, end='', file=sys.stderr, flush=True)
    thread.target = stderr_copier
    thread.start()
    try:
        run_out = do_exec_cmd(slurm_args, dry_run=dry_run,
                              return_CompletedProcess=True, stderr=thread.file_w)
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
        ):
    slurm_args = [
        'sbatch',
        ]

    gres_args = []
    if stdin_file is not None:
        slurm_args += ['--input', stdin_file]
    if stdout_file is not None:
        slurm_args += ['--output', stdout_file]
    if stderr_file is not None:
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
    slurm_args = [str(e) for e in slurm_args]
    return do_exec_cmd(slurm_args)

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

def edvar(value, *, json=None, suffix=None, encoding='utf-8'):
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
            value = prettyxml(value)
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

# }}}

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
