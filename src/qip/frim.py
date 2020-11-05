
__all__ = [
        'FRIMEncode',
        'FRIMDecode',
        'FRIMTranscode',
        ]

from pathlib import Path
import functools
import logging
log = logging.getLogger(__name__)

from .exec import Executable, do_spawn_cmd, do_srun_cmd

class _FRIMExecutable(Executable):

    run_func = staticmethod(do_spawn_cmd)

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    @classmethod
    def kwargs_to_cmdargs(cls, /, **kwargs):
        cmdargs = []
        for k, v in kwargs.items():
            if v in (None, False):
                # Dropped for ease of passing unused arguments
                continue
            k = {
                '_class': 'class',
                '_continue': 'continue',
            }.get(k, k)
            cmdargs.append('-' + k)
            if v is not True:
                cmdargs.append(arg2cmdarg(v))
        return cmdargs

    def _run(self, *args, run_func=None, dry_run=False,
            **kwargs):
        args = list(args)

        run_kwargs = {}

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

class _FRIMEncode(_FRIMExecutable):

    name = 'FRIMEncode'

FRIMEncode = _FRIMEncode()

class _FRIMDecode(_FRIMExecutable):

    name = 'FRIMDecode'

FRIMDecode = _FRIMDecode()

class _FRIMTranscode(_FRIMExecutable):

    name = 'FRIMTranscode'

FRIMTranscode = _FRIMTranscode()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
