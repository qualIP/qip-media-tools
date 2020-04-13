
__all__ = [
        'ddrescue',
        ]

import logging
log = logging.getLogger(__name__)

from .exec import Executable, do_spawn_cmd

class Ddrescue(Executable):

    name = 'ddrescue'

    run_func = staticmethod(do_spawn_cmd)

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

ddrescue = Ddrescue()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
