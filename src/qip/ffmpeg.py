
__all__ = [
        'ffmpeg',
        ]

import functools
import types
import re
import os
import logging
log = logging.getLogger(__name__)

from .perf import perfcontext
from .exec import *
from .parser import lines_parser
from .utils import byte_decode
from .utils import Timestamp as _BaseTimestamp
from qip.file import *

class Timestamp(_BaseTimestamp):
    '''hh:mm:ss.sssssssss format'''

    def __init__(self, value):
        if isinstance(value, float):
            seconds = value
        elif isinstance(value, int):
            seconds = float(value)
        elif isinstance(value, _BaseTimestamp):
            seconds = value.seconds
        elif isinstance(value, str):
            match = re.search(r'^(?P<sign>-)?(((?P<h>\d+):)?(?P<m>\d+):)?(?P<s>\d+(?:\.\d+)?)$', value)
            if match:
                h = match.group('h')
                m = match.group('m')
                s = match.group('s')
                sign = match.group('sign')
                seconds = int(h or 0) * 60 * 60 + int(m or 0) * 60 + float(s)
                if sign:
                    seconds = -seconds
            else:
                raise ValueError('Invalid hh:mm:ss.ss format: %r' % (value,))
        else:
            raise ValueError(value)
        super().__init__(seconds)

    def __str__(self):
        s = self.seconds
        m = s // 60
        s = s - m * 60
        h = m // 60
        m = m - h * 60
        return '%02d:%02d:%s' % (h, m, ('%.8f' % (s + 100.0))[1:])


class _Ffmpeg(Executable):

    run_func = staticmethod(do_spawn_cmd)

    Timestamp = Timestamp

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
        args = list(args)

        # out_file is always last
        out_file_args = [args.pop(-1)]
        if args and args[-1] == '--':
            out_file_args = [args.pop(-1)] + out_file_args

        if 'loglevel' not in kwargs and '-loglevel' not in args:
            if not log.isEnabledFor(logging.VERBOSE):
                kwargs['loglevel'] = 'info'

        return super().build_cmd(*args, **kwargs) + out_file_args

class Ffmpeg(_Ffmpeg):

    name = 'ffmpeg'

    run_func = staticmethod(do_spawn_cmd)

    Timestamp = Timestamp

    def _run(self, *args, run_func=None, dry_run=False, slurm=False, **kwargs):
        args = list(args)

        if run_func or dry_run:
            slurm = False

        if slurm:
            try:
                idx = args.index("-passlogfile")
            except ValueError:
                pass
            else:
                slurm = False
            try:
                idx = args.index("-f")
            except ValueError:
                slurm = False

        run_kwargs = {}

        if slurm:
            # args = <options...> [--] <out_file>
            # out_file is always last
            if args[-2] != '--':
                args.insert(-1, '--')
            out_file = args[-1]
            args[-1] = 'pipe:'
            # args = <options...> -- pipe:

            try:
                idx = args.index("-i")
            except ValueError:
                raise ValueError('no input file specified')
            else:
                # args = <options...> -i <in_file> <options...>
                in_file = args[idx + 1]
                args[idx + 1] = 'pipe:0'
                # args = <options...> -i pipe:0 <options...>

            run_func = do_srun_cmd
            run_kwargs['chdir'] = '/'
            run_kwargs['stdin_file'] = os.path.abspath(in_file)
            run_kwargs['stdout_file'] = os.path.abspath(out_file)
            run_kwargs['stderr_file'] = '/dev/stderr'
            threads = None
            try:
                threads = kwargs['threads']
            except KeyError:
                try:
                    idx = args.index("-threads")
                except ValueError:
                    pass
                else:
                    threads = args[idx + 1]
            if threads:
                run_kwargs['slurm_cpus_per_task'] = max(round(int(threads) * 0.75), 1)
            run_kwargs['slurm_mem'] = '500M'
            run_kwargs.setdefault('slurm_job_name', '_'.join(os.path.basename(out_file).split()))

        else:
            run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
            #if not dry_run:
            #    run_kwargs['stdin'] = open(str(in_file), "rb")
            #    run_kwargs['stdout'] = open(str(out_file), "w")

        if run_kwargs:
            run_func = functools.partial(run_func, **run_kwargs)

        return super()._run(
                *args,
                dry_run=dry_run,
                run_func=run_func,
                **kwargs)

    def run2pass(self, *args, **kwargs):
        args = list(args)

        # out_file is always last
        out_file = args.pop(-1)

        try:
            idx = args.index("-i")
        except ValueError:
            raise ValueError('no input file specified')
        else:
            args.pop(idx)
            in_file = args.pop(idx)

        pipe = True
        if in_file == '-':
            assert pipe, "input file is stdin but piping is not possible"

        if pipe:
            return ffmpeg_2pass_pipe(
                    *args,
                    stdin_file=in_file,
                    stdout_file=out_file,
                    **kwargs)

        try:
            idx = args.index("-passlogfile")
        except ValueError:
            passlogfile = None
        else:
            args.pop(idx)
            passlogfile = args.pop(idx)
        if not passlogfile:
            passlogfile = TempFile.mkstemp(suffix='.passlogfile')

        d = types.SimpleNamespace()
        with perfcontext('%s pass 1/2' % (self.name,)):
            d.pass1 = self.run(*args,
                    "-pass", 1, "-passlogfile", passlogfile,
                    "-speed", 4,
                    "-y", '/dev/null',
                    **kwargs)
        with perfcontext('%s pass 2/2' % (self.name,)):
            d.pass2 = self.run(*args,
                    "-pass", 2, "-passlogfile", passlogfile,
                    out_file,
                    **kwargs)
        d.out = d.pass2.out
        try:
            d.t0 = d.pass1.t0
            d.t1 = d.pass2.t1
            d.elapsed_time = d.t1 - d.t0
        except AttributeError:
            pass

    def cropdetect(self, input_file, cropdetect_duration=60, dry_run=False):
        stream_crop = None
        with perfcontext('Cropdetect w/ ffmpeg'):
            ffmpeg_args = [
                '-i', input_file,
                '-t', cropdetect_duration,
                '-filter:v', 'cropdetect=24:2:0:0',
                ]
            ffmpeg_args += [
                '-f', 'null', '-',
                ]
            out = self(*ffmpeg_args,
                       dry_run=dry_run)
        if not dry_run:
            parser = lines_parser(byte_decode(out.out).split('\n'))
            while parser.advance():
                parser.line = parser.line.strip()
                m = re.match(r'.*Parsed_cropdetect.* crop=(\d+):(\d+):(\d+):(\d+)$', parser.line)
                if m:
                    stream_crop = (int(m.group(1)),
                            int(m.group(2)),
                            int(m.group(3)),
                            int(m.group(4)))
            if not stream_crop:
                raise ValueError('Crop detection failed')
        return stream_crop

ffmpeg = Ffmpeg()

class Ffmpeg2passPipe(_Ffmpeg, PipedPortableScript):

    name = os.path.join(os.path.dirname(__file__), 'bin', 'ffmpeg-2pass-pipe')

    run_func = staticmethod(do_exec_cmd)

    def build_cmd(self, *args, **kwargs):
        args = list(args)

        args.append('-')  # dummy output

        cmd = super().build_cmd(*args, **kwargs)
        assert cmd.pop(-1) == '-'
        return cmd

    def _run(self, *args, stdin_file, stdout_file, run_func=None, dry_run=False, slurm=False, **kwargs):
        args = list(args)

        if run_func or dry_run:
            slurm = False

        try:
            idx = args.index("-passlogfile")
        except ValueError:
            pass
        else:
            slurm = False

        run_kwargs = {}
        if slurm:
            run_func = do_srun_cmd
            run_kwargs['chdir'] = '/'
            run_kwargs['stdin_file'] = os.path.abspath(stdin_file)
            run_kwargs['stdout_file'] = os.path.abspath(stdout_file)
            run_kwargs['stderr_file'] = '/dev/stderr'
            threads = None
            try:
                threads = kwargs['threads']
            except KeyError:
                try:
                    idx = args.index("-threads")
                except ValueError:
                    pass
                else:
                    threads = args[idx + 1]
            if threads:
                run_kwargs['slurm_cpus_per_task'] = max(round(int(threads) * 0.75), 1)
            run_kwargs['slurm_mem'] = '500M'
            if not dry_run:
                run_kwargs['slurm_tmp'] = '%dK' % (os.path.getsize(stdin_file) * 1.5 / 1024,)
            run_kwargs.setdefault('slurm_job_name', '_'.join(os.path.basename(stdout_file).split()))
        else:
            run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
            if not dry_run:
                run_kwargs['stdin'] = open(str(stdin_file), "rb")
                run_kwargs['stdout'] = open(str(stdout_file), "w")
        if run_kwargs:
            run_func = functools.partial(run_func, **run_kwargs)

        return super()._run(
                *args,
                dry_run=dry_run,
                run_func=run_func,
                **kwargs)


ffmpeg_2pass_pipe = Ffmpeg2passPipe()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
