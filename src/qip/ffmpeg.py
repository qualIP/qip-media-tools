
__all__ = [
        'ffmpeg',
        'ffprobe',
        ]

import functools
from decimal import Decimal
from fractions import Fraction
import types
import re
import os
import subprocess
import logging
log = logging.getLogger(__name__)

from .perf import perfcontext
from .exec import *
from .parser import lines_parser
from .utils import byte_decode
from .utils import Timestamp as _BaseTimestamp, Ratio
from qip.file import *

class Timestamp(_BaseTimestamp):
    '''hh:mm:ss.sssssssss format'''

    def __init__(self, value):
        if isinstance(value, float):
            seconds = value
        elif isinstance(value, (int, Fraction)):
            seconds = float(value)
        elif isinstance(value, _BaseTimestamp):
            seconds = value.seconds
        elif isinstance(value, str):
            match = value and re.search(
                r'^'
                r'(?P<sign>-)?'
                r'(((?P<h>\d+):)?(?P<m>\d+):)?'
                r'(?P<s>\d+(?:\.\d+)?)'
                r'$', value)
            if match:
                h = match.group('h') or 0
                m = match.group('m') or 0
                s = match.group('s') or 0
                sign = bool(match.group('sign'))
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
        if s < 0.0:
            sign = '-'
            s = -s
        else:
            sign = ''
        m = s // 60
        s = s - m * 60
        h = m // 60
        m = m - h * 60
        return '%s%02d:%02d:%s' % (sign, h, m, ('%.8f' % (s + 100.0))[1:])

Timestamp.MAX = Timestamp('99:59:59.99999999')


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
            if log.isEnabledFor(logging.DEBUG):
                kwargs['loglevel'] = 'verbose'
            elif log.isEnabledFor(logging.VERBOSE):
                kwargs['loglevel'] = 'info'
            else:
                kwargs['loglevel'] = 'info'

        if 'hide_banner' not in kwargs and '-hide_banner' not in args:
            if not log.isEnabledFor(logging.VERBOSE):
                kwargs['hide_banner'] = True

        return super().build_cmd(*args, **kwargs) + out_file_args

class Ffmpeg(_Ffmpeg):

    name = 'ffmpeg'

    def _run(self, *args, run_func=None, dry_run=False,
            slurm=False, slurm_cpus_per_task=None,
            **kwargs):
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
            if slurm_cpus_per_task is None:
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
                    slurm_cpus_per_task = max(round(int(threads) * 0.75), 1)
            if slurm_cpus_per_task is not None:
                run_kwargs['slurm_cpus_per_task'] = slurm_cpus_per_task
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

    def cropdetect(self, input_file,
            skip_frame_nokey=True, cropdetect_seek=None, cropdetect_duration=300,
            video_filter_specs=None,
            dry_run=False):
        stream_crop = None
        with perfcontext('Cropdetect w/ ffmpeg'):
            ffmpeg_args = []
            if cropdetect_seek is not None:
                ffmpeg_args += [
                    '-ss', Timestamp(cropdetect_seek),
                ]
            if skip_frame_nokey:
                ffmpeg_args += [
                    '-skip_frame', 'nokey',
                ]
            video_filter_specs = list(video_filter_specs or [])
            video_filter_specs.append('cropdetect=24:2:0:0')  # Handbrake?
            #video_filter_specs.append('cropdetect=24:16:0:0')  # ffmpeg default
            ffmpeg_args += [
                '-i', input_file,
                '-t', Timestamp(cropdetect_duration),
                '-filter:v', ','.join(video_filter_specs),
                ]
            ffmpeg_args += [
                '-f', 'null', '-',
                ]
            out = self(*ffmpeg_args,
                       dry_run=dry_run)
        if not dry_run:
            frames_count = 0
            last_cropdetect_match = None
            parser = lines_parser(byte_decode(out.out).split('\n'))
            while parser.advance():
                parser.line = parser.line.strip()
                m = re.match(r'.*Parsed_cropdetect.* crop=(\d+):(\d+):(\d+):(\d+)$', parser.line)
                if m:
                    frames_count += 1
                    last_cropdetect_match = m
            if not last_cropdetect_match:
                raise ValueError('Crop detection failed')
            if skip_frame_nokey and frames_count < 2:
                return self.cropdetect(input_file,
                                       skip_frame_nokey=False,
                                       cropdetect_seek=cropdetect_seek,
                                       cropdetect_duration=cropdetect_duration,
                                       dry_run=dry_run)
            m = last_cropdetect_match
            w, h, l, t = stream_crop = (
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)))
            assert w > 0 and h > 0 and l >= 0 and t >= 0, (w, h, l, t)
        return stream_crop

ffmpeg = Ffmpeg()

class Ffmpeg2passPipe(_Ffmpeg, PipedPortableScript):

    name = os.path.join(os.path.dirname(__file__), 'bin', 'ffmpeg-2pass-pipe')

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

def NA_or_int(value):
    if value == 'N/A':
        return None
    return int(value)

def NA_or_Decimal(value):
    if value == 'N/A':
        return None
    return Decimal(value)

def str_to_bool(value):
    if value == '0':
        return False
    if value == '1':
        return True
    raise ValueError(value)

class Ffprobe(_Ffmpeg):

    name = 'ffprobe'

    run_func = staticmethod(dbg_exec_cmd)

    def build_cmd(self, *args, **kwargs):
        args = list(args)

        args.append('-')  # dummy output

        cmd = super().build_cmd(*args, **kwargs)
        assert cmd.pop(-1) == '-'
        return cmd

    def _run(self, *args, run_func=None, dry_run=False,
            **kwargs):
        args = list(args)

        run_kwargs = {}

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

    class Frame(types.SimpleNamespace):

        _attr_convs = {
            # 'channel_layout': TODO,  # 5.1(side)
            # 'chroma_location': TODO,  # left
            # 'color_primaries': TODO,  # unknown
            # 'color_range': TODO,  # tv
            # 'color_space': TODO,  # unknown
            # 'color_transfer': TODO,  # unknown
            # 'media_type': TODO,  # audio, video, subtitle
            # 'pict_type': TODO,  # I
            # 'pix_fmt': TODO,  # yuv420p
            # 'sample_fmt': TODO,  # fltp
            'best_effort_timestamp': NA_or_int,  # 0
            'best_effort_timestamp_time': NA_or_Decimal,  # 0.000000
            'channels': int,  # 6
            'coded_picture_number': int,  # 0
            'display_picture_number': int,  # 0
            'height': int,  # 480
            'interlaced_frame': str_to_bool,  # 0
            'key_frame': int,  # 1
            'nb_samples': int,  # 1536
            'pkt_dts': NA_or_int,  # 0
            'pkt_dts_time': NA_or_Decimal,  # 0.000000
            'pkt_duration': int,  # 32
            'pkt_duration_time': Decimal,  # 0.032000
            'pkt_pos': int,  # 13125
            'pkt_pts': NA_or_int,  # 0
            'pkt_pts_time': NA_or_Decimal,  # 0.000000
            'pkt_size': int,  # 1536
            'repeat_pict': str_to_bool,  # 0
            'sample_aspect_ratio': Ratio,  # 186:157
            'stream_index': int,  # 1
            'top_field_first': str_to_bool,  # 1
            'width': int,  # 720
        }

        def __init__(self, *, side_datas=None, **kwargs):
            super().__init__(side_datas=side_datas or [],
                           **kwargs)

    class SideData(types.SimpleNamespace):

        _attr_convs = {
            # 'side_data_type': TODO,  # AVMatrixEncoding
            # 'side_data_type': TODO,  # AVPanScan
            # 'side_data_type': TODO,  # GOP timecode
            # 'side_data_type': TODO,  # Metadata relevant to a downmix procedure
            # 'side_data_type': TODO,  # QP table data
            # 'side_data_type': TODO,  # QP table properties
            # 'timecode': TODO,  # 00:00:00:00
        }

    class Subtitle(types.SimpleNamespace):

        _attr_convs = {
            # 'media_type': TODO,  # subtitle
            'pts': int,  # 22272000
            'pts_time': Decimal,  # 22.272000
            'format': int,  # 1
            'start_display_time': int,  # 0
            'end_display_time': int,  # 2000
            'num_rects': int,  # 1
        }

    def iter_frames(self, file, *, dry_run=False):
        from qip.parser import lines_parser
        ffprobe_args = [
            '-loglevel', 'panic', '-hide_banner',
            '-i', str(file),
            '-show_frames',
        ]
        with self.popen(*ffprobe_args,
                        stdout=subprocess.PIPE, text=True,
                        dry_run=dry_run) as p:
            parser = lines_parser(p.stdout)
            for line in parser:
                line = line.strip()
                if line == '[FRAME]':
                    frame = Ffprobe.Frame()
                    for line in parser:
                        line = line.strip()
                        try:
                            attr, value = line.split('=', maxsplit=1)
                        except ValueError:
                            pass
                        else:
                            conv = frame._attr_convs.get(attr, None)
                            if conv:
                                value = conv(value)
                            setattr(frame, attr, value)
                            continue
                        if line == '[SIDE_DATA]':
                            side_data = Ffprobe.SideData()
                            for line in parser:
                                line = line.strip()
                                try:
                                    attr, value = line.split('=', maxsplit=1)
                                except ValueError:
                                    pass
                                else:
                                    setattr(side_data, attr, value)
                                    continue
                                if line == '[/SIDE_DATA]':
                                    break
                                raise ValueError('Unrecognized SIDE_DATA line %d: %s' % (parser.line_no, line))
                            else:
                                raise ValueError('Unclosed SIDE_DATA near line %d' % (parser.line_no,))
                            frame.side_datas.append(side_data)
                            continue
                        if line == '[/FRAME]':
                            break
                        raise ValueError('Unrecognized FRAME line %d: %s' % (parser.line_no, line))
                    else:
                        raise ValueError('Unclosed FRAME near line %d' % (parser.line_no,))
                    yield frame
                    continue
                if line == '[SUBTITLE]':
                    subtitle = Ffprobe.Subtitle()
                    for line in parser:
                        line = line.strip()
                        try:
                            attr, value = line.split('=', maxsplit=1)
                        except ValueError:
                            pass
                        else:
                            conv = subtitle._attr_convs.get(attr, None)
                            if conv:
                                value = conv(value)
                            setattr(subtitle, attr, value)
                            continue
                        if line == '[/SUBTITLE]':
                            break
                        raise ValueError('Unrecognized SUBTITLE line %d: %s' % (parser.line_no, line))
                    else:
                        raise ValueError('Unclosed SUBTITLE near line %d' % (parser.line_no,))
                    yield subtitle
                    continue
                raise ValueError('Unrecognized line %d: %s' % (parser.line_no, line))

ffprobe = Ffprobe()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
