# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
    'SlurmError',
    'do_srun_cmd',
    'do_sbatch_cmd',
    'srun',
    'sbatch',
]

import os
import collections
import re
import sys
import time
import types

from .exec import Executable, stdout_wrapper, do_exec_cmd, PipeRecordThread, list2cmdlist
from .utils import byte_decode


class SlurmError(Exception):

    def __init__(self, msg, *, cmd, out):
        self.cmd = cmd
        self.out = out
        super().__init__(msg)


class Srun(Executable):

    name = 'srun'

    def do_wrap_cmd(self, cmd,
                    stdin=None, stdin_file=None,
                    stdout=None, stdout_file=None,
                    stderr=None, stderr_file=None,
                    encoding=None, errors=None,
                    slurm_priority=100,
                    slurm_cpus_per_task=None,
                    slurm_mem=None,
                    slurm_tmp=None,
                    slurm_job_name=None,
                    slurm_kill_on_bad_exit=True,
                    slurm_chdir='/',
                    slurm_uid=None,
                    **kwargs):
        d = types.SimpleNamespace()
        slurm_tmp = None  # TODO srun: Invalid generic resource (gres) specification

        text, encoding, errors = self.get_text_mode_info(
            cmd=cmd, encoding=encoding, errors=errors)

        do_wrap = True
        slurm_cmd = self.build_cmd()
        slurm_args = []
        for once in range(1):
            gres_args = []

            if kwargs.get('fd', None) is not None:
                log.debug('Not wrapping with %s: fd used', self.name)
                do_wrap = False
                break

            if stdin_file is not None:
                if stdin is not None:
                    raise TypeError('stdin used with stdin_file')
                slurm_args += ['--input', stdin_file]
            if stdout_file is not None:
                if stdout is not None:
                    raise TypeError('stdout used with stdout_file')
                if False:
                    slurm_args += ['--output', stdout_file]
                else:
                    slurm_cmd = stdout_wrapper.build_cmd(stdout_file, *slurm_cmd)
            if stderr_file is None:
                # By default in interactive mode, srun redirects stderr to the same file as stdout.
                # Split them apart...
                stderr_file = '/dev/stderr'
            if stderr_file is not None:
                if stderr is not None:
                    if stderr_file == '/dev/stderr':
                        # Ok, slurm sends to its stderr which gets redirected to the caller's stderr fd
                        pass
                    else:
                        raise TypeError('stderr used with stderr_file')
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
            if slurm_job_name is None:
                if stdout_file is not None:
                    slurm_job_name = re.sub(r'\W+', '_', os.fspath(stdout_file))
            if slurm_job_name:
                slurm_args += ['--job-name', slurm_job_name]
            if slurm_kill_on_bad_exit is not None:
                slurm_args += ['--kill-on-bad-exit=%d' % (1 if slurm_kill_on_bad_exit else 0,)]
            if slurm_chdir is not None:
                slurm_args += ['--chdir', slurm_chdir]
            if slurm_uid is not None:
                slurm_args += ['--uid', slurm_uid]
            if gres_args:
                slurm_args += ['--gres', ','.join(gres_args)]

            slurm_args.extend(cmd)
            slurm_cmd += list2cmdlist(slurm_args)

        run_func = kwargs.pop('run_func', None)

        if do_wrap:

            run_func = run_func or self.run_func or do_exec_cmd  # functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)

            # We need to grab stderr to test for slurm errors
            # By default in interactive mode, srun redirects stderr to the same file as stdout.
            thread = PipeRecordThread(text=True)
            def stderr_copier(out, file=sys.stderr if stderr is None else stderr):
                print(out, end='', file=file, flush=True)
            thread.target = stderr_copier
            stderr = thread.file_w

            thread.start()
            try:
                t0 = time.time()
                out = run_func(slurm_cmd,
                               # TODO return_CompletedProcess=True,
                               stdin=stdin, stdout=stdout, stderr=stderr,
                               encoding=encoding, errors=errors,
                               **kwargs)
                t1 = time.time()
            finally:
                thread.file_w.close()
                thread.join()

            err = byte_decode(thread.output)
            m = re.search(r'srun: error: .*', err)
            if m:
                err_msg = m.group(0).strip()
                raise SlurmError(err_msg, cmd=slurm_cmd, out=err)

        else:

            run_func = run_func or do_exec_cmd

            with contextlib.ExitStack() as exit_stack:

                if stdin_file is not None:
                    stdin = exit_stack.enter_context(
                        open(stdin_file, 'rb'))
                if stdout_file is not None:
                    stdout = exit_stack.enter_context(
                        open(stdout_file, 'w', encoding=encoding, errors=errors))
                if stderr_file is not None:
                    if stderr_file == stdout_file:
                        stderr = stdout
                    else:
                        stderr = exit_stack.enter_context(
                            open(stderr_file, 'w', encoding=encoding, errors=errors))

                t0 = time.time()
                out = run_func(cmd,
                               stdin=stdin, stdout=stdout, stderr=stderr,
                               encoding=encoding, errors=errors,
                               **kwargs)
                t1 = time.time()

        if isinstance(out, collections.abc.Mapping):
            for k, v in out.items():
                setattr(d, k, v)
        else:
            d.out = out
        d.elapsed_time = t1 - t0

        return d


srun = Srun()
do_srun_cmd = srun.do_wrap_cmd


class Sbatch(Executable):

    name = 'sbatch'

sbatch = Sbatch()


def do_sbatch_cmd(cmd,
                  stdin=None, stdin_file=None,
                  stdout=None, stdout_file=None,
                  stderr=None, stderr_file=None,
                  slurm_priority=100,
                  slurm_cpus_per_task=None,
                  slurm_mem=None,
                  slurm_tmp=None,
                  slurm_job_name=None,
                  slurm_chdir='/',
                  slurm_uid=None,
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
    if slurm_chdir is not None:
        slurm_args += ['--chdir', slurm_chdir]
    if slurm_uid is not None:
        slurm_args += ['--uid', slurm_uid]
    if gres_args:
        slurm_args += ['--gres', ','.join(gres_args)]

    if wait:
        slurm_args += ['--wait']

    slurm_args.extend(cmd)
    slurm_args = list2cmdlist(slurm_args)
    return do_exec_cmd(slurm_args,
                       cwd=cwd,
                       stdin=stdin, stdout=stdout, stderr=stderr)
