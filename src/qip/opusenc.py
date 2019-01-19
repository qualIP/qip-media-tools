
__all__ = [
        'opusenc',
        ]

import functools
import os
import logging
log = logging.getLogger(__name__)

from .exec import *

class Opusenc(Executable):

    name = 'opusenc'

    run_func = staticmethod(do_spawn_cmd)

    @classmethod
    def kwargs_to_cmdargs(cls, **kwargs):
        cmdargs = []
        for k, v in kwargs.items():
            if v is False:
                continue
            if True or len(k) == 1:
                cmdargs.append('-' + k)
            else:
                cmdargs.append('--' + k)
            if v is not True:
                cmdargs.append(str(v))
        return cmdargs

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
            out_file = args[-1]
            args[-1] = '-'

            # in_file is previous to last
            in_file = args[-2]
            args[-2] = '-'

            run_func = do_srun_cmd
            run_kwargs['chdir'] = '/'
            run_kwargs['stdin_file'] = os.path.abspath(in_file)
            run_kwargs['stdout_file'] = os.path.abspath(out_file)
            run_kwargs['stderr_file'] = '/dev/stderr'
            run_kwargs['slurm_cpus_per_task'] = 1
            run_kwargs['slurm_mem'] = '500M'
            run_kwargs.setdefault('slurm_job_name', '_'.join(os.path.basename(out_file).split()))

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

opusenc = Opusenc()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
