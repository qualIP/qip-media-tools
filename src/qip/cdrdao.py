# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'cdrdao',
        ]

from qip.parser import *
from qip.exec import *

class Cdrdao(Executable):

    name = 'cdrdao'

    def read_toc(self,
            toc_file,
            device=None,
            datafile=None,
            fast_toc=False,
            with_cddb=False,
            **kwargs):
        args = ['read-toc']
        assert isinstance(fast_toc, bool)
        if fast_toc:
            args += ['--fast-toc']
        if device:
            args += ['--device', device]
        assert isinstance(with_cddb, bool)
        if with_cddb:
            args += ['--with-cddb']
        if datafile:
            args += ['--datafile', str(datafile)]
        args += [str(toc_file)]
        return self._run(*args, **kwargs)

cdrdao = Cdrdao()
