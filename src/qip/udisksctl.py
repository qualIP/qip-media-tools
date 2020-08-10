
__all__ = (
    'udiskctl',
)

from pathlib import Path
import contextlib
import logging
import os
import re
import subprocess
log = logging.getLogger(__name__)

from .file import BinaryFile
from .exec import Executable, byte_decode
from .lodev import LoopDevice


class Udisksctl(Executable):

    name = 'udisksctl'

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt_dash

    def build_cmd(self, *args, command=None, **kwargs):
        '''udisksctl [command] -options... args...'''

        cmd_args = []

        if command is not None:
            cmd_args.append(command)

        cmd_args += self.kwargs_to_cmdargs(**kwargs)
        cmd_args.extend(args)

        return super().build_cmd(*cmd_args)

    def loop_setup(self, *,
                   file,
                   read_only=False, offset=None, size=None,
                   no_user_interaction=True):

        assert file is not None

        out = self(
            command='loop-setup',
            file=file,
            read_only=read_only,
            offset=offset,
            size=size,
            no_user_interaction=no_user_interaction,
        )

        # Mapped file IMAGE.iso as /dev/loop0.
        m = re.search(r'^Mapped file (?P<source>.+) as (?P<lodev_name>/dev/\S+)\.$', byte_decode(out.out), re.MULTILINE)
        if not m:
            raise ValueError(f'{self}: Invalid loop device: {out.out!r}')
        lodev_name = m.group('lodev_name')

        return LoopDevice(lodev_name)

    def loop_delete(self, *,
                    object_path=None, block_device=None,
                    no_user_interaction=True):

        out = self(
            command='loop-delete',
            object_path=object_path,
            block_device=block_device,
            no_user_interaction=no_user_interaction,
        )

        # Nothing on output
        return

    def mount(self, *, object_path=None, block_device=None,
              filesystem_type=None,
              options=None,
              read_only=False,
              no_user_interaction=True):

        if options is None:
            options = []
        elif isinstance(options, str):
            options = options.split(',')
        else:
            options = list(options)
        if read_only:
            options.append('ro')
        options = ','.join(options) if options else None

        out = self(
            command='mount',
            object_path=object_path,
            block_device=block_device,
            filesystem_type=filesystem_type,
            options=options,
            no_user_interaction=no_user_interaction,
        )

        out.out = self.clean_cmd_output(out.out)
        # Mounted /dev/loop0 at /media/user/MOUNTPOINT.
        m = re.search(r'^Mounted (?P<source>.+) at (?P<mountpoint>/.+)\.+', byte_decode(out.out), re.MULTILINE)
        if not m:
            raise ValueError(f'{self}: Invalid mount point: {out.out!r}')
        mountpoint = m.group('mountpoint')

        return Path(mountpoint)

    def unmount(self, *, object_path=None, block_device=None,
                force=None,
                no_user_interaction=True):

        out = self(
            command='unmount',
            object_path=object_path,
            block_device=block_device,
            force=force,
            no_user_interaction=no_user_interaction,
        )

        out.out = self.clean_cmd_output(out.out)
        # Unmounted /dev/loop0.
        m = re.search(r'^Unmounted (?P<block_device>/.+)\.+', byte_decode(out.out), re.MULTILINE)
        if not m:
            raise ValueError(f'{self}: Invalid unmount: {out.out!r}')

        return

    @contextlib.contextmanager
    def loop_context(self, *,
                     file,                                    # setup
                     no_user_interaction=True,                # setup/delete
                     **kwargs):                               # setup
        import retrying
        lodev = self.loop_setup(
            file=file,
            no_user_interaction=no_user_interaction,
            **kwargs)
        try:
            yield lodev
        finally:
            retrying.retry(
                wait_fixed=100,
                stop_max_delay=5000,
                retry_on_exception=lambda e: isinstance(e, subprocess.CalledProcessError) and e.returncode == 1,\
            )(self.loop_delete)(
                block_device=lodev,
                no_user_interaction=no_user_interaction)

    @contextlib.contextmanager
    def mount_context(self, *,
                      object_path=None, block_device=None,  # mount/unmount
                      no_user_interaction=True,             # mount/unmount
                      force=None,                           # unmount
                      **kwargs):                            # mount
        mountpoint = self.mount(
            object_path=object_path,
            block_device=block_device,
            no_user_interaction=no_user_interaction,
            **kwargs)
        try:
            yield mountpoint
        finally:
            self.unmount(
                object_path=object_path,
                block_device=block_device,
                no_user_interaction=no_user_interaction)

udisksctl = Udisksctl()
