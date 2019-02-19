
__all__ = [
        'dbg_exec_cmd',
        'do_exec_cmd',
        'suggest_exec_cmd',
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
        ]

import abc
import errno
import functools
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
    if getattr(app.args, 'dry_run', False):
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
            run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
            t0 = time.time()
            d.out = run_func(cmd)
            t1 = time.time()
            d.elapsed_time = t1 - t0
        return d

    def _popen(self, *args, dry_run=False,
               stdin=None, stdout=None, stderr=None,
               text=None, encoding=None,
               **kwargs):
        """p1 = myexe1.popen([...], stdout=subprocess.PIPE)
           p2 = myexe2.popen([...], stdin=p1.stdout, stdout=myfile.fp)
        """
        cmd = self.build_cmd(*args, **kwargs)
        if dry_run:
            log.verbose('CMD (dry-run): %s',
                        subprocess.list2cmdline(cmd))
            d = types.SimpleNamespace()
            d.stdout = None
            return d
        else:
            return subprocess.Popen(
                cmd,
                stdin=stdin, stdout=stdout, stderr=stderr,
                universal_newlines=text,  # 3.7: text=text
                encoding=encoding,
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
        ):
    slurm_args = [
        'srun',
        ]

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
        slurm_args += ['--tmp', slurm_tmp]
    if slurm_job_name is not None:
        slurm_args += ['--job-name', slurm_job_name]
    if chdir is not None:
        slurm_args += ['--chdir', chdir]
    if uid is not None:
        slurm_args += ['--uid', uid]

    slurm_args.extend(cmd)
    slurm_args = [str(e) for e in slurm_args]
    do_exec_cmd(slurm_args)

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
        slurm_args += ['--tmp', slurm_tmp]
    if slurm_job_name is not None:
        slurm_args += ['--job-name', slurm_job_name]
    if chdir is not None:
        slurm_args += ['--chdir', chdir]
    if uid is not None:
        slurm_args += ['--uid', uid]
    if wait:
        slurm_args += ['--wait']

    slurm_args.extend(cmd)
    slurm_args = [str(e) for e in slurm_args]
    do_exec_cmd(slurm_args)

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

    if json is None:
        if isinstance(value, str):
            json = False
            suffix = suffix or '.txt'
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
            return (False, value)

        tmp_file.fp = tmp_file.open(mode='r', encoding=encoding)
        if json:
            new_value = qip.json.load(tmp_file.fp)
        else:
            new_value = qip.json.read()
        tmp_file.close()

        #if type(new_value) is not type(value):
        #    raise ValueError(new_value)
        return (True, new_value)

# }}}

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
