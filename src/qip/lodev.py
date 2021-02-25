# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'LoopDevice',
    'losetup',
)

from pathlib import Path
import contextlib
import logging
import os
import re
log = logging.getLogger(__name__)

from .file import BinaryFile
from .exec import SystemExecutable, Executable, byte_decode

class LoopDevice(BinaryFile):

    @classmethod
    def new_from_file(cls, file, **kwargs):
        return losetup.setup(file=file, **kwargs)

    def setup(self, *, file, **kwargs):
        if not self.name:
            raise ValueError('Loop device name not set!')
        losetup.setup(loopdev=self,
                      file=file,
                      **kwargs)

    def detach(self):
        losetup.detach(self)

    @classmethod
    @contextlib.contextmanager
    def context_from_file(cls, file, **kwargs):
        lodev = cls.new_from_file(file, **kwargs)
        try:
            yield lodev
        finally:
            lodev.detach()


class Losetup(SystemExecutable):

    name = 'losetup'

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt_dash

    def setup(self, *,
              loopdev=None, file,
              offset=None, sizelimit=None, sector_size=None,
              partscan=False, read_only=False):
        assert file is not None
        show = False
        find = False
        if loopdev is None:
            show = True
            find = True

        cmd_args = []
        cmd_args += self.kwargs_to_cmdargs(
            offset=offset,
            sizelimit=sizelimit,
            sector_size=sector_size,
            partscan=partscan,
            read_only=read_only,
            show=show,
            find=find,
        )
        if loopdev is not None:
            cmd_args.append(loopdev)
        cmd_args.append(file)

        out = self(*cmd_args)
        # out = namespace(elapsed_time=..., out=b'/dev/loopX\b')

        if show:
            lodev_name = re.sub(r'\n$', '', byte_decode(out.out))
            if not lodev_name:
                raise ValueError(f'{self}: Invalid loop device: {out.out!r}')
            return LoopDevice(lodev_name)

    def detach(self, *files):
        assert files

        cmd_args = []
        cmd_args.append('--detach')
        cmd_args += files
        out = self(*cmd_args)

        return

losetup = Losetup()
