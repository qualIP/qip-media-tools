
__all__ = [
        'opusenc',
        ]

from pathlib import Path
import functools
import logging
import os
import re
log = logging.getLogger(__name__)

from .exec import *

class Opusenc(Executable):

    name = 'opusenc'

    run_func = staticmethod(do_spawn_cmd)

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def build_cmd(self, *args, **kwargs):
        args = list(args)

        # out_file is always last
        out_file = args.pop(-1)

        # in_file is previous to last
        in_file = args.pop(-1)

        return super().build_cmd(*args, **kwargs) + [in_file, out_file]

    def _run(self, *args, run_func=None, dry_run=False, slurm=False, **kwargs):
        args = list(args)

        if run_func or dry_run:
            slurm = False

        if slurm:
            if ('--picture' in args
                    or '--save-range' in args):
                slurm = False

        run_kwargs = {}

        if slurm:

            # out_file is always last
            out_file = Path(args[-1])
            args[-1] = '-'

            # in_file is previous to last
            in_file = Path(args[-2])
            args[-2] = '-'

            run_func = do_srun_cmd
            run_kwargs['chdir'] = '/'
            run_kwargs['stdin_file'] = in_file.resolve()
            run_kwargs['stdout_file'] = out_file.resolve()
            run_kwargs['stderr_file'] = '/dev/stderr'
            run_kwargs['slurm_cpus_per_task'] = 1
            run_kwargs['slurm_mem'] = '500M'
            run_kwargs.setdefault('slurm_job_name', re.sub(r'\W+', '_', out_file.name))

        else:
            run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
            #if not dry_run:
            #    run_kwargs['stdin'] = open(os.fspath(in_file), "rb")
            #    run_kwargs['stdout'] = open(os.fspath(out_file), "w")

        if run_kwargs:
            run_func = functools.partial(run_func, **run_kwargs)

        return super()._run(
                *args,
                dry_run=dry_run,
                run_func=run_func,
                **kwargs)

opusenc = Opusenc()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
