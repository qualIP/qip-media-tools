
__all__ = [
        'AudiobookFile',
        ]

import os
import subprocess
import logging
log = logging.getLogger(__name__)

from .m4a import M4aFile

class AudiobookFile(M4aFile):

    def __init__(self, file_name, *args, **kwargs):
        super().__init__(file_name=file_name, *args, **kwargs)

    def create_mkm4b(self, snd_files, out_dir=None, interactive=False, single=False):
        oldcwd = os.getcwd()
        try:
            if out_dir is not None:
                os.chdir(out_dir)
            cmd = [
                    'mkm4b',
                    ]
            if self.cover_file:
                cmd += [
                        '--cover', str(os.path.join(oldcwd, str(self.cover_file))),
                        ]
            if interactive:
                cmd += ['--interactive']
            if single:
                cmd += ['--single']
            cmd += ['--logging_level', str(logging.getLogger().level)]
            cmd += [os.path.join(oldcwd, str(e)) for e in snd_files]
            if log.isEnabledFor(logging.DEBUG):
                log.debug('CMD: %s', subprocess.list2cmdline(cmd))
            subprocess.check_call(cmd)
        finally:
            os.chdir(oldcwd)

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
