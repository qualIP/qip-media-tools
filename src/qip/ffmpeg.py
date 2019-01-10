
__all__ = [
        'ffmpeg',
        ]

import types
import logging
log = logging.getLogger(__name__)

from .perf import perfcontext
from .exec import *
from qip.file import *

class Ffmpeg(Executable):

    name = 'ffmpeg'

    run_func = classmethod(do_spawn_cmd)

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
        # out_file is always last
        args = list(args)
        out_file = args.pop(-1)
        return super().build_cmd(*args, **kwargs) + [out_file]

    def run2pass(self, *args, run_func=None, dry_run=False, distribute=False, **kwargs):
        # out_file is always last
        args = list(args)
        out_file = args.pop(-1)

        try:
            idx = args.find("-passlogfile")
        except IndexError:
            passlogfile = None
        else:
            args.pop(idx)
            passlogfile = args.pop(idx)

        if distribute and not dry_run and not passlogfile:
            pass

        passlogfile = passlogfile or TempFile.mkstemp(suffix='.passlogfile')

        if 'loglevel' not in kwargs and '-loglevel' not in args:
            if not log.isEnabledFor(logging.VERBOSE):
                kwargs['loglevel'] = 'info'

        d = types.SimpleNamespace()
        with perfcontext('%s pass 1/2' % (self.name,)):
            d.pass1 = self.run(*args,
                    "-pass", 1, "-passlogfile", passlogfile,
                    "-speed", 4,
                    "-y", '/dev/null',
                    run_func=run_func, dry_run=dry_run,
                    **kwargs)
        with perfcontext('%s pass 2/2' % (self.name,)):
            d.pass2 = self.run(*args,
                    "-pass", 2, "-passlogfile", passlogfile,
                    out_file,
                    run_func=run_func, dry_run=dry_run,
                    **kwargs)
        d.out = d.pass2.out
        try:
            d.t0 = d.pass1.t0
            d.t1 = d.pass2.t1
            d.elapsed_time = d.t1 - d.t0
        except AttributeError:
            pass

ffmpeg = Ffmpeg()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
