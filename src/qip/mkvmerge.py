# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'mkvmerge',
        ]

import logging
log = logging.getLogger(__name__)

from .exec import Executable, do_spawn_cmd

class Mkvmerge(Executable):

    name = 'mkvmerge'

    run_func = staticmethod(do_spawn_cmd)

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

mkvmerge = Mkvmerge()
