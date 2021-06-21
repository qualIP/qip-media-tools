# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'eject',
        ]

import os
import errno

from .exec import Executable

class Eject(Executable):

    name = None  # TBD
    tool = None  # TBD

    def which(self, mode=os.F_OK | os.X_OK, path=None, assert_found=True):

        if self.name is None:

            for (name, tool) in (
                    ('eject', 'util-linux'),
                    ('diskutil', 'bsd-diskutil'),
            ):
                self.name = name
                try:
                    cmd = super().which(mode=mode, path=path, assert_found=False)
                except:
                    self.name = None
                    raise
                if cmd is not None:
                    if path is not None:
                        self.name = cmd
                    self.tool = tool
                    return cmd

            self.name = None
            if assert_found:
                raise OSError(errno.ENOENT, f'Command not found: eject, diskutil')
            return None

        return super().which(mode=mode, path=path, assert_found=assert_found)

    def _run(self, device, **kwargs):
        if self.tool is None:
            self.which()  # Prime .name/.tool
        args = []
        if self.tool == 'bsd-diskutil':
            # diskutil [quiet] eject <device>
            args += [
                'eject',
            ]
        else:
            # eject [options...] <device>
            pass
        args.append(device)
        return super()._run(*args, **kwargs)

eject = Eject()
