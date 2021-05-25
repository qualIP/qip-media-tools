# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'mplayer',
        ]

from pathlib import Path
import functools
import logging
import os
import re
log = logging.getLogger(__name__)

from .exec import Executable, do_spawn_cmd

class Mplayer(Executable):

    name = 'mplayer'

    run_func = staticmethod(do_spawn_cmd)

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    #def _run(self, *args, run_func=None, dry_run=False,
    #        slurm=False, slurm_cpus_per_task=None,
    #        **kwargs):
    #    args = list(args)
    #
    #    if run_func:
    #        slurm = False
    #
    #    if slurm:
    #        try:
    #            idx = args.index("-lavfopts")
    #        except ValueError:
    #            slurm = False
    #        else:
    #            lavfopts_arg = args[idx + 1]
    #            if not re.search('format=', lavfopts_arg):
    #                slurm = False
    #    if slurm:
    #        try:
    #            idx = args.index("-cache")
    #        except ValueError:
    #            # cache required to avoid seek errors with stdin
    #            args = ['-cache', 8192] + args
    #
    #    if slurm:
    #        try:
    #            from .slurm import do_srun_cmd
    #        except ImportError:
    #            slurm = False
    #
    #    run_kwargs = {}
    #
    #    if slurm:
    #
    #        idx_in_file = 0
    #        while str(args[idx_in_file]).startswith('-'):
    #            if '=' in args[idx_in_file]:
    #                # Skip: -option=value
    #                idx_in_file += 1
    #            else:
    #                # Skip: -option value
    #                idx_in_file += 2
    #        in_file = Path(args[idx_in_file])
    #
    #        idx_out_file = args.index('-o', idx_in_file + 1) + 1
    #        out_file = Path(args[idx_out_file])
    #
    #        args[idx_in_file] = '-'
    #        args[idx_out_file] = '-'
    #
    #        run_func = do_srun_cmd
    #        run_kwargs['stdin_file'] = in_file.resolve()
    #        run_kwargs['stdout_file'] = out_file.resolve()
    #        if slurm_cpus_per_task is not None:
    #            run_kwargs['slurm_cpus_per_task'] = slurm_cpus_per_task
    #        run_kwargs['slurm_mem'] = '500M'
    #
    #    else:
    #        run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
    #        #if not dry_run:
    #        #    run_kwargs['stdin'] = open(str(in_file), "rb")
    #        #    run_kwargs['stdout'] = open(str(out_file), "w")
    #
    #    if run_kwargs:
    #        run_func = functools.partial(run_func, **run_kwargs)
    #
    #    return super()._run(
    #            *args,
    #            dry_run=dry_run,
    #            run_func=run_func,
    #            **kwargs)

mplayer = Mplayer()
