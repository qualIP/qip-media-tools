
__all__ = [
        'safecopy',
        ]

from qip.parser import *
from qip.exec import *

class Safecopy(Executable):

    name = 'safecopy'

    @classmethod
    def kwargs_to_cmdargs(cls, **kwargs):
        cmdargs = []
        for k, v in kwargs.items():
            if v is False:
                continue
            if len(k) == 1:
                cmdargs.append('-' + k)
            else:
                cmdargs.append('--' + k)
            if v is not True:
                cmdargs.append(str(v))
        return cmdargs

    def __call__(self, source, destination, *extra_args, stage=None, timing=False, **kwargs):
        args = []
        if stage is not None:
            args += ['--stage%d' % (stage,)]
        if timing:
            if timing is True:
                if stage is not None:
                    timing = 'stage%d.timing' % (stage,)
                else :
                    timing = 'safecopy.timing'
            args += ['-T', timing]
        args += extra_args
        args += [str(source), str(destination)]
        d = self._run(*args, **kwargs)
        out = self.clean_cmd_output(d.out)
        parser = lines_parser(out.splitlines())
        while parser.advance():
            if parser.line == '':
                pass
            elif parser.re_search(r'^CDROM low level disk size: (\d+)$'):
                d.low_level_disk_size = int(parser.match.group(1))
            elif parser.re_search(r'^Blocks \(bytes\) copied: (\d+) \((\d+)\)$'):
                d.blocks_copied = int(parser.match.group(1))
                d.bytes_copied = int(parser.match.group(2))
            elif parser.re_search(r'^Low level device calls enabled mode: (.+)$'):
                d.low_level_device_calls_enabled_mode = parser.match.group(1)
            elif parser.re_search(r'^Reported hw blocksize: (\d+)$'):
                d.reported_hw_block_size = int(parser.match.group(1))
            elif parser.re_search(r'^CDROM audio - low level access: (.+)$'):
                d.cdrom_audio_low_level_access = parser.match.group(1)
            elif parser.re_search(r'^CDROM low level disk size: (\d+)$'):
                d.cdrom_low_level_disk_size = int(parser.match.group(1))
            elif parser.re_search(r'^CDROM low level block size: (\d+)$'):
                d.cdrom_low_level_block_size = int(parser.match.group(1))
            elif parser.re_search(r'^Reported low level blocksize: (\d+)$'):
                d.reported_low_level_block_size = int(parser.match.group(1))
            elif parser.re_search(r'^File size: (\d+)$'):
                d.file_size = int(parser.match.group(1))
            elif parser.re_search(r'^Blocksize: (\d+)$'):
                d.block_size = int(parser.match.group(1))
            elif parser.re_search(r'^Fault skip blocksize: (\d+)$'):
                d.fault_skip_block_size = int(parser.match.group(1))
            elif parser.re_search(r'^Resolution: (\d+)$'):
                d.resolution = int(parser.match.group(1))
            elif parser.re_search(r'^Min read attempts: (\d+)$'):
                d.min_read_attempts = int(parser.match.group(1))
            elif parser.re_search(r'^Head moves on read error: (\d+)$'):
                d.head_moves_on_read_error = int(parser.match.group(1))
            elif parser.re_search(r'^Incremental mode file: (.+)$'):
                d.incremental_mode_file = parser.match.group(1)
            elif parser.re_search(r'^Incremental mode blocksize: (\d+)$'):
                d.incremental_mode_block_size = int(parser.match.group(1))
            elif parser.re_search(r'^Badblocks output: (.+)$'):
                d.badblocks_output_file = parser.match.group(1)
            elif parser.re_search(r'^Starting block: (\d+)$'):
                d.starting_block = int(parser.match.group(1))
            elif parser.re_search(r'^Source: (.+)$'):
                d.source_file = parser.match.group(1)
            elif parser.re_search(r'^Destination: (.+)$'):
                d.destination_file = parser.match.group(1)
            elif parser.re_search(r'^Current destination size: (\d+)$'):
                d.current_destination_size = int(parser.match.group(1))
        return d

safecopy = Safecopy()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
