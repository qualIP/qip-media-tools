
__all__ = [
        'mencoder',
        ]

from pathlib import Path
import functools
import logging
import os
import re
log = logging.getLogger(__name__)

from .exec import Executable, do_spawn_cmd, do_srun_cmd

class Mencoder(Executable):

    name = 'mencoder'

    run_func = staticmethod(do_spawn_cmd)

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def _run(self, *args, run_func=None, dry_run=False,
            slurm=False, slurm_cpus_per_task=None,
            **kwargs):
        args = list(args)

        if run_func or dry_run:
            slurm = False

        if slurm:
            try:
                idx = args.index("-lavfopts")
            except ValueError:
                slurm = False
            else:
                lavfopts_arg = args[idx + 1]
                if not re.search('format=', lavfopts_arg):
                    slurm = False
        if slurm:
            try:
                idx = args.index("-cache")
            except ValueError:
                # cache required to avoid seek errors with stdin
                args = ['-cache', 8192] + args

        run_kwargs = {}

        if slurm:

            idx_in_file = 0
            while str(args[idx_in_file]).startswith('-'):
                if '=' in args[idx_in_file]:
                    # Skip: -option=value
                    idx_in_file += 1
                else:
                    # Skip: -option value
                    idx_in_file += 2
            in_file = Path(args[idx_in_file])

            idx_out_file = args.index('-o', idx_in_file + 1) + 1
            out_file = Path(args[idx_out_file])

            args[idx_in_file] = '-'
            args[idx_out_file] = '-'

            run_func = do_srun_cmd
            run_kwargs['chdir'] = '/'
            run_kwargs['stdin_file'] = in_file.resolve()
            run_kwargs['stdout_file'] = out_file.resolve()
            run_kwargs['stderr_file'] = '/dev/stderr'
            if slurm_cpus_per_task is not None:
                run_kwargs['slurm_cpus_per_task'] = slurm_cpus_per_task
            run_kwargs['slurm_mem'] = '500M'
            run_kwargs.setdefault('slurm_job_name', re.sub(r'\W+', '_', out_file.name))

        else:
            run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
            #if not dry_run:
            #    run_kwargs['stdin'] = open(str(in_file), "rb")
            #    run_kwargs['stdout'] = open(str(out_file), "w")

        if run_kwargs:
            run_func = functools.partial(run_func, **run_kwargs)

        return super()._run(
                *args,
                dry_run=dry_run,
                run_func=run_func,
                **kwargs)

mencoder = Mencoder()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
