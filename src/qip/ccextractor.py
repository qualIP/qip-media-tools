# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'ccextractor',
        ]

from pathlib import Path
import functools
import logging
import os
import re
log = logging.getLogger(__name__)

from .exec import Executable, do_spawn_cmd

class Ccextractor(Executable):

    name = 'ccextractor'

    run_func = staticmethod(do_spawn_cmd)

    #kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

ccextractor = Ccextractor()
