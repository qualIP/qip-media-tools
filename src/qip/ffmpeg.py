
__all__ = [
        'ffmpeg',
        'ffprobe',
        ]

from decimal import Decimal
from pathlib import Path
import collections
import contextlib
import copy
import functools
import logging
import os
import pexpect
import re
import subprocess
import types
log = logging.getLogger(__name__)

from .perf import perfcontext
from .exec import *
from .exec import _SpawnMixin, spawn as _exec_spawn, popen_spawn as _exec_popen_spawn
from .parser import lines_parser
from .utils import byte_decode
from .utils import Timestamp as _BaseTimestamp, Ratio
from qip.file import *
from qip.collections import OrderedSet

class Timestamp(_BaseTimestamp):
    '''hh:mm:ss.sssssssss format'''

    def __init__(self, value):
        if isinstance(value, Timestamp._SECONDS_COMPATIBLE_TYPES):
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
            raise ValueError(repr(value))
        super().__init__(seconds)

    def canonical_str(self):
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

class ConcatScriptFile(TextFile):

    ffconcat_version = 1.0
    files = None

    class File(object):

        def __init__(self, name, duration=None):
            self.name = toPath(name)
            self.duration = None if duration is None else Timestamp(duration)

    def __init__(self, file_name):
        self.files = []
        super().__init__(file_name)

    def create(self, file=None):
        if file is None:
            with self.open('w', encoding='utf-8') as file:
                return self.create(file=file)
        if self.ffconcat_version is not None:
            print(f'ffconcat version {self.ffconcat_version}', file=file)
        for file_entry in self.files:
            esc_file = os.fspath(file_entry.name).replace(r"'", r"'\''")
            print(f'file \'{esc_file}\'', file=file)
            if file_entry.duration is not None:
                print(f'duration {file_entry.duration}', file=file)

class _FfmpegSpawnMixin(_SpawnMixin):

    invocation_purpose = None
    show_progress_bar = None
    progress_bar = None
    progress_bar_max = None
    progress_bar_title = None
    on_progress_bar_line = False
    num_errors = 0
    errors_seen = None
    current_info_section = None
    streams_info = None

    def __init__(self, cmd, invocation_purpose=None,
                 show_progress_bar=None, progress_bar_max=None, progress_bar_title=None,
                 env=None, **kwargs):
        self.invocation_purpose = invocation_purpose
        if show_progress_bar is None:
            show_progress_bar = progress_bar_max is not None
        self.show_progress_bar = show_progress_bar
        self.progress_bar_max = progress_bar_max
        self.progress_bar_title = progress_bar_title
        self.errors_seen = OrderedSet()
        self.streams_info = {
            'input': {},
            'output': {},
        }
        env = dict(env or os.environ)
        env['AV_LOG_FORCE_NOCOLOR'] = '1'
        env['TERM'] = 'dumb'
        env.pop('TERMCAP', None)
        super().__init__(cmd, env=env, **kwargs)

    def generic_info(self, str):
        if not log.isEnabledFor(logging.DEBUG):
            return True
        return self.unknown_line(str)

    def start_file_info_section(self, str, inout):
        file_index = int(byte_decode(self.match.group('index')))
        self.current_info_section = (inout, file_index, None)
        self.streams_info[inout][file_index] = d = self.match.groupdict()
        d.update({
            'streams': {},
        })
        for k in ('index',):
            try:
                d[k] = None if d[k] is None else int(byte_decode(d[k]))
            except KeyError:
                pass
        log.debug('streams_info=%r', self.streams_info)
        self.generic_info(str)
        return True

    start_input_info_section = functools.partialmethod(start_file_info_section, inout='input')
    start_output_info_section = functools.partialmethod(start_file_info_section, inout='output')

    def start_stream_info_section(self, str):
        inout, file_index, _ = self.current_info_section
        stream_no = byte_decode(self.match.group('stream_no'))
        self.current_info_section = (inout, file_index, stream_no)
        self.streams_info[inout][file_index]['streams'][stream_no] = d = self.match.groupdict()
        for k in ('num_ref_frames', 'width', 'height'):
            try:
                d[k] = None if d[k] is None else int(byte_decode(d[k]))
            except KeyError:
                pass
        log.debug('streams_info=%r', self.streams_info)
        self.generic_info(str)
        return True

    def progress_line(self, str):
        if self.progress_bar is not None:
            if self.progress_bar_max:
                if isinstance(self.progress_bar_max, Timestamp):
                    self.progress_bar.goto(Timestamp(byte_decode(self.match.group('time'))).seconds)
                else:
                    self.progress_bar.goto(int(self.match.group('frame')))
                fps = self.match.group('fps')
                if fps:
                    self.progress_bar.fps = Decimal(byte_decode(fps))
            else:
                self.progress_bar.next()
            self.on_progress_bar_line = True
        else:
            str = byte_decode(str).rstrip('\r\n')
            if self.on_progress_bar_line:
                print('')
                self.on_progress_bar_line = False
            print(str)
        return True

    def parsed_cropdetect_line(self, str):
        if self.progress_bar is not None:
            crop = None
            if self.progress_bar_max:
                if self.progress_bar.index == 0:
                    #self.progress_bar.message = f'{self.command} cropdetect'
                    self.progress_bar.message = 'cropdetect'
                    self.progress_bar.suffix += ' crop=%(crop)s'
                self.progress_bar.crop = crop = byte_decode(self.match.group('crop'))
                if isinstance(self.progress_bar_max, Timestamp):
                    self.progress_bar.goto(Timestamp(byte_decode(self.match.group('time'))).seconds)
                else:
                    # self.progress_bar.goto(int(self.match.group('frame')))
                    self.progress_bar.next()
                # self.progress_bar.fps = Decimal(byte_decode(self.match.group('fps')))
            else:
                self.progress_bar.next()
            self.on_progress_bar_line = True
            try:
                stop_crop = self.invocation_purpose == 'cropdetect' \
                    and crop and crop == '{width}:{height}:0:0'.format_map(self.streams_info['input'][0]['streams']['0:0'])
            except KeyError as e:
                pass  # print('') ; print(f'e={e}')
            else:
                if stop_crop:
                    log.debug('No cropping possible; Quit!')
                    self.send(b'q')
                    return False
        else:
            str = byte_decode(str).rstrip('\r\n')
            if self.on_progress_bar_line:
                print('')
                self.on_progress_bar_line = False
            print(str)
        return True

    def progress_pass(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.progress_bar is not None:
            self.progress_bar.message = f'{self.command} -- {str}'
            self.progress_bar.reset()
            #self.progress_bar.update()
            self.on_progress_bar_line = True
        else:
            if self.on_progress_bar_line:
                print('')
                self.on_progress_bar_line = False
            print(str)
        return True

    def unknown_info_line(self, str):
        if not log.isEnabledFor(logging.DEBUG):
            return True
        return self.unknown_line(str)

    def unknown_verbose_line(self, str):
        if not log.isEnabledFor(logging.DEBUG):
            return True
        return self.unknown_line(str)

    def unknown_error_line(self, str):
        return self.generic_error(str)

    def unknown_line(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if str:
            if self.on_progress_bar_line:
                print('')
                self.on_progress_bar_line = False
            print(f'UNKNOWN: {str!r}')
        return True

    def generic_error(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.on_progress_bar_line:
            print('')
            self.on_progress_bar_line = False
        log.error(str)
        self.num_errors += 1
        self.errors_seen.add(str)
        return True

    def terminal_escape_sequence(self, str):
        return True

    def eof(self, _dummy):
        str = byte_decode(self.before).rstrip('\r\n')
        if str:
            if self.on_progress_bar_line:
                print('')
                self.on_progress_bar_line = False
            print(f'EOF: {str!r}')
        return True

    def get_pattern_dict(self):
        re_eol = r'(?:\r?\n|\r)'
        pattern_dict = collections.OrderedDict([

            # frame=   39 fps=0.0 q=-0.0 Lsize=    4266kB time=00:00:01.60 bitrate=21801.0kbits/s speed=6.98x
            # [info] frame=  776 fps=119 q=-0.0 size=  129161kB time=00:00:25.86 bitrate=40915.9kbits/s speed=3.95x
            # size=       0kB time=01:03:00.94 bitrate=   0.0kbits/s speed=2.17e+07x
            # frame= 2235 fps=221 q=-0.0 size= 1131482kB time=00:01:14.60 bitrate=124237.6kbits/s dup=447 drop=0 speed=7.37x
            (fr'^(?:\[info\] )?(?:frame= *(?P<frame>\d+) +fps= *(?P<fps>\S+) +q= *(?P<q>\S+) )?L?size= *(?P<size>\S+) +time= *(?P<time>\S+) +bitrate= *(?P<bitrate>\S+)(?: +dup= *(?P<dup>\S+))?(?: +drop= *(?P<drop>\S+))? +speed= *(?P<speed>\S+) *{re_eol}', self.progress_line),

            # [Parsed_cropdetect_1 @ 0x56473433ba40] x1:0 x2:717 y1:0 y2:477 w:718 h:478 x:0 y:0 pts:504504000 t:210.210000 crop=718:478:0:0
            (fr'^\[Parsed_cropdetect\S* @ \S+\] (?:\[info\] )?x1:(?P<x1>\S+) x2:(?P<x2>\S+) y1:(?P<y1>\S+) y2:(?P<y2>\S+) w:(?P<w>\S+) h:(?P<h>\S+) x:(?P<x>\S+) y:(?P<y>\S+) pts:(?P<pts>\S+) t:(?P<time>\S+) crop=(?P<crop>\S+) *{re_eol}', self.parsed_cropdetect_line),

            (fr'^\[ffmpeg-2pass-pipe\] (?P<pass>PASS [12]){re_eol}', self.progress_pass),

            # [info] Input #0, h264, from 'test-movie3/track-00-video.h264':
            # [info] Input #0, h264, from 'pipe:':
            (fr'^(?:\[info\] )? *Input #(?P<index>\S+), (?P<format>\S+), from \'(?P<file_name>.+)\':{re_eol}', self.start_input_info_section),
            # [info] Output #0, null, to 'pipe:':
            (fr'^(?:\[info\] )? *Output #(?P<index>\S+), (?P<format>\S+), to \'(?P<file_name>.+)\':{re_eol}', self.start_output_info_section),
            # [info]     Stream #0:0: Video: h264 (High), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 24.08 fps, 23.98 tbr, 1200k tbn, 47.95 tbc
            # [info]     Stream #0:0: Video: wrapped_avframe, yuv420p, 1920x1080 [SAR 1:1 DAR 16:9], q=2-31, 200 kb/s, 23.98 fps, 23.98 tbn, 23.98 tbc
            # [info]     Stream #0:0: Video: wrapped_avframe, 1 reference frame, yuv420p(left), 720x480 [SAR 8:9 DAR 4:3], q=2-31, 200 kb/s, 29.97 fps, 29.97 tbn, 29.97 tbc
            # [info]     Stream #0:0: Video: mpeg2video (Main), 1 reference frame, yuv420p(tv, top first, left), 720x480 [SAR 8:9 DAR 4:3], 29.97 fps, 29.97 tbr, 1200k tbn, 59.94 tbc
            # [info]     Stream #0:0: Video: h264 (High), 1 reference frame, yuv420p(progressive, left), 1920x1080 (1920x1088) [SAR 1:1 DAR 16:9], 24.08 fps, 23.98 tbr, 1200k tbn, 47.95 tbc
            # [info]     Stream #0:0: Video: vc1 (Advanced), 1 reference frame (WVC1 / 0x31435657), yuv420p(bt709, progressive, left), 1920x1080 [SAR 1:1 DAR 16:9], 23.98 fps, 23.98 tbr, 23.98 tbn, 47.95 tbc
            (fr'^(?:\[info\] )? *Stream #(?P<stream_no>\S+): (?P<stream_type>Video): (?P<format1>[^,]+)(?:, (?P<num_ref_frames>\d+) reference frame(?: \([^)]+\))?)?, (?P<format2>[^(,]+(?:\([^)]+\))?), (?P<width>\d+)x(?P<height>\d+) .*{re_eol}', self.start_stream_info_section),

            (fr'^\[info\] [^\r\n]*?{re_eol}', self.unknown_info_line),
            (fr'^\[verbose\] [^\r\n]*?{re_eol}', self.unknown_verbose_line),
            (fr'^\[error\] [^\r\n]*?{re_eol}', self.unknown_error_line),

            # \x1b[48;5;0m
            # \x1b[38;5;226m
            (fr'^\x1b\[[0-9;]+m', self.terminal_escape_sequence),  # Should not happen with AV_LOG_FORCE_NOCOLOR

            (fr'[^\n]*?{re_eol}', self.unknown_line),
            (pexpect.EOF, self.eof),
        ])
        return pattern_dict

    def __enter__(self):
        ret = super().__enter__()
        if self.show_progress_bar:
            if self.progress_bar_max:
                try:
                    from qip.utils import ProgressBar
                except ImportError:
                    pass
                else:
                    if isinstance(self.progress_bar_max, Timestamp):
                        self.progress_bar = ProgressBar(self.progress_bar_title or self.command,
                                                        max=self.progress_bar_max.seconds)
                        self.progress_bar.suffix = '%(percent).1f%% time=%(index).1f/%(max).1f fps=%(fps).2f remaining=%(eta)ds'
                    else:
                        self.progress_bar = ProgressBar(self.progress_bar_title or self.command,
                                                        max=self.progress_bar_max)
                        self.progress_bar.suffix = '%(percent).1f%% frame=%(index)s/%(max)s fps=%(fps).2f remaining=%(eta)ds'
                    self.progress_bar.fps = 0
                    self.progress_bar.crop = None
                    self.on_progress_bar_line = True
            else:
                try:
                    from qip.utils import ProgressSpinner
                except ImportError:
                    pass
                else:
                    self.progress_bar = ProgressSpinner(self.progress_bar_title or self.command)
                    self.on_progress_bar_line = True
        return ret

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.progress_bar is not None:
            progress_bar = self.progress_bar
            self.progress_bar = None
            progress_bar.finish()
            self.on_progress_bar_line = False
        return super().__exit__(exc_type, exc_value, exc_traceback)

class FfmpegSpawn(_FfmpegSpawnMixin, _exec_spawn):
    pass

class FfmpegPopenSpawn(_FfmpegSpawnMixin, _exec_popen_spawn):
    pass

class _Ffmpeg(Executable):

    Timestamp = Timestamp
    ConcatScriptFile = ConcatScriptFile

    run_func = Executable._spawn_run_func
    # TODO popen_func = Executable._spawn_popen_func
    run_func_options = Executable.run_func_options + (
        'invocation_purpose',
        'show_progress_bar',
        'progress_bar_max',
        'progress_bar_title',
    )

    spawn = FfmpegSpawn
    popen_spawn = FfmpegPopenSpawn

    @classmethod
    def kwargs_to_cmdargs(cls, **kwargs):
        cmdargs = []
        for k, v in kwargs.items():
            if v in (None, False):
                # Dropped for ease of passing unused arguments
                continue
            k = {
                '_class': 'class',
                '_continue': 'continue',
            }.get(k, k)
            if True or len(k) == 1:  # Always a single dash
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
                kwargs['loglevel'] = 'level+verbose'
            elif log.isEnabledFor(logging.VERBOSE):
                kwargs['loglevel'] = 'info'
                # kwargs.setdefault('stats', True)  # included in info
            else:
                kwargs['loglevel'] = 'warning'
                kwargs.setdefault('stats', True)

        if 'hide_banner' not in kwargs and '-hide_banner' not in args:
            if not log.isEnabledFor(logging.VERBOSE):
                kwargs['hide_banner'] = True

        return super().build_cmd(*args, **kwargs) + out_file_args

class Ffmpeg(_Ffmpeg):

    name = 'ffmpeg'

    environ = {
        'TERM': 'dummy',
    }

    def _run(self, *args, run_func=None, dry_run=False,
             slurm=False, slurm_cpus_per_task=None,
             progress_bar_max=None,
             progress_bar_title=None,
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
            # args = <options...> [--] <stdout_file>
            # stdout_file is always last
            if args[-2] != '--':
                args.insert(-1, '--')
            stdout_file = Path(args[-1])
            args[-1] = 'pipe:'
            # args = <options...> -- pipe:

            try:
                idx = args.index("-i")
            except ValueError:
                raise ValueError('no input file specified')
            # args = <options...> -i <stdin_file> <options...>
            stdin_file = Path(args[idx + 1])
            args[idx + 1] = 'pipe:0'
            # args = <options...> -i pipe:0 <options...>

            run_func = do_srun_cmd
            run_kwargs['chdir'] = '/'
            run_kwargs['stdin_file'] = stdin_file.resolve()
            run_kwargs['stdout_file'] = stdout_file.resolve()
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
            run_kwargs.setdefault('slurm_job_name', re.sub(r'\W+', '_', stdout_file.name))

        else:
            run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
            #if not dry_run:
            #    run_kwargs['stdin'] = open(os.fspath(stdin_file), "rb")
            #    run_kwargs['stdout'] = open(os.fspath(stdout_file), "w")
            run_kwargs['progress_bar_max'] = progress_bar_max
            run_kwargs['progress_bar_title'] = progress_bar_title

        if run_kwargs:
            run_func = functools.partial(run_func, **run_kwargs)

        return super()._run(
            *args,
            dry_run=dry_run,
            run_func=run_func,
            **kwargs)

    def run2pass(self, *args, **kwargs):
        args = list(args)

        # stdout_file is always last
        stdout_file = args.pop(-1)

        try:
            idx = args.index("-i")
        except ValueError:
            raise ValueError('no input file specified')
        else:
            args.pop(idx)
            stdin_file = args.pop(idx)

        pipe = True
        if os.fspath(stdin_file) == '-':
            assert pipe, "input file is stdin but piping is not possible"

        if pipe:
            return ffmpeg_2pass_pipe(
                    *args,
                    stdin_file=stdin_file,
                    stdout_file=stdout_file,
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
                    stdout_file,
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
                   show_progress_bar=True,
                   progress_bar_title=None,
                   default_ffmpeg_args=[],
                   dry_run=False):
        stream_crop = None
        with perfcontext('Cropdetect w/ ffmpeg'):
            ffmpeg_args = list(default_ffmpeg_args)
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

            if log.isEnabledFor(logging.DEBUG):
                loglevel = 'level+verbose'
            elif log.isEnabledFor(logging.VERBOSE):
                loglevel = 'info'
                loglevel = 'level+' + loglevel
                # kwargs.setdefault('stats', True)  # included in info
            else:
                loglevel = 'info'  # 'warning'
                loglevel = 'level+' + loglevel
                # kwargs.setdefault('stats', True)  # included in info

            out = self(*ffmpeg_args,
                       show_progress_bar=show_progress_bar,
                       progress_bar_max=Timestamp(cropdetect_duration),
                       progress_bar_title=progress_bar_title or 'cropdetect',
                       invocation_purpose='cropdetect',
                       dry_run=dry_run,
                       loglevel=loglevel)
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
                # Output file is empty, nothing was encoded (check -ss / -t / -frames parameters if used)
                # -> skip_frame_nokey=False
                raise ValueError('Crop detection failed')
            if skip_frame_nokey and frames_count < 2:
                return self.cropdetect(input_file,
                                       skip_frame_nokey=False,
                                       cropdetect_seek=cropdetect_seek,
                                       cropdetect_duration=cropdetect_duration,
                                       default_ffmpeg_args=default_ffmpeg_args,
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

    ## TODO -- fix popen_func support above
    run_func = None
    def run(self, *args, **kwargs):
        for k in self.run_func_options:
            kwargs.pop(k, None)
        return super().run(*args, **kwargs)
    __call__ = run
    def popen(self, *args, **kwargs):
        for k in self.run_func_options:
            kwargs.pop(k, None)
        return super().popen(*args, **kwargs)

    name = Path(__file__).parent / 'bin' / 'ffmpeg-2pass-pipe'

    def build_cmd(self, *args, **kwargs):
        args = list(args)

        args.append('-')  # dummy output

        cmd = super().build_cmd(*args, **kwargs)
        assert os.fspath(cmd.pop(-1)) == '-'
        return cmd

    def _run(self, *args, stdin_file, stdout_file, run_func=None, dry_run=False, slurm=False,
             progress_bar_max=None, progress_bar_title=None,
             **kwargs):
        args = list(args)
        stdin_file = Path(stdin_file)
        stdout_file = Path(stdout_file)

        if not slurm:
            log.debug('slurm disabled.')
        elif run_func:
            log.debug('Custom run_func provided; Disabling slurm.')
            slurm = False
        elif dry_run:
            log.debug('Dry-run; Disabling slurm.')
            slurm = False

        try:
            idx = args.index("-passlogfile")
        except ValueError:
            pass
        else:
            log.debug('-passlogfile provided; Disabling slurm.')
            slurm = False

        with contextlib.ExitStack() as stack:

            run_kwargs = {}
            if slurm:
                run_func = do_srun_cmd
                run_kwargs['chdir'] = '/'
                run_kwargs['stdin_file'] = stdin_file.resolve()
                run_kwargs['stdout_file'] = stdout_file.resolve()
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
                    run_kwargs['slurm_tmp'] = stdin_file.stat().st_size * 1.5
                run_kwargs.setdefault('slurm_job_name', re.sub(r'\W+', '_', stdout_file.name))
            else:
                run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
                if not dry_run:
                    run_kwargs['stdin'] = stack.enter_context(stdin_file.open("rb"))
                    run_kwargs['stdout'] = stack.enter_context(stdout_file.open("wb"))
                if progress_bar_max is not None:
                    run_kwargs['progress_bar_max'] = progress_bar_max
                if progress_bar_title is not None:
                    run_kwargs['progress_bar_title'] = progress_bar_title
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

def NA_or_Ratio(value):
    if value == 'N/A':
        return None
    return Ratio(value)

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
        assert os.fspath(cmd.pop(-1)) == '-'
        return cmd

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
            'pkt_duration': NA_or_int,  # 32
            'pkt_duration_time': NA_or_Decimal,  # 0.032000
            'pkt_pos': int,  # 13125
            'pkt_pts': NA_or_int,  # 0
            'pkt_pts_time': NA_or_Decimal,  # 0.000000
            'pkt_size': int,  # 1536
            'repeat_pict': int,  # 0
            'sample_aspect_ratio': NA_or_Ratio,  # 186:157
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

    class Timecode(types.SimpleNamespace):

        _attr_convs = {
            # 'value': TODO,  # 00:00:00:00
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

    class Packet(types.SimpleNamespace):

        _attr_convs = {
            # 'codec_type': TODO,  # video
            'stream_index': int,  # 0
            'pts': NA_or_int,  # 33
            'pts_time': NA_or_Decimal,  # 0.033000
            'dts': NA_or_int,  # -33
            'dts_time': NA_or_Decimal,  # -0.033000
            'duration': NA_or_int,  # 33
            'duration_time': NA_or_Decimal,  # 0.033000
            'convergence_duration': NA_or_int,  # N/A
            'convergence_duration_time': NA_or_Decimal,  # N/A
            'size': int,  # 67192
            'pos': int,  # 4033
            # 'flags': TODO,  # K_
            }

    def iter_frames(self, file, *, default_ffmpeg_args=[], dry_run=False):
        from qip.parser import lines_parser
        ffprobe_args = list(default_ffmpeg_args) + [
            '-loglevel', 'level+error', '-hide_banner',
            '-i', str(file),
            '-show_frames',
        ]
        error_lines = []

        # [mpeg2video @ 0x55ea4143fe00] [error] end mismatch left=114 1370 at 0 30
        re_error_line = re.compile(r'\[(error|panic)\] .+')
        with self.popen(*ffprobe_args,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        popen_func=do_popen_cmd,  # XXXJST TODO
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
                                try:
                                    value = conv(value)
                                except Exception as err:
                                    raise ValueError('%s = %s: (%s) %s' % (attr, value, err.__class__.__name__, err))
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
                                if line == '[TIMECODE]':
                                    for line in parser:
                                        line = line.strip()
                                        try:
                                            attr, value = line.split('=', maxsplit=1)
                                        except ValueError:
                                            pass
                                        else:
                                            if attr == 'value':
                                                side_data.timecode = value
                                            else:
                                                raise ValueError('Unrecognized TIMECODE attribute line %d: %s' % (parser.line_no, line))
                                            continue
                                        if line == '[/TIMECODE]':
                                            break
                                        raise ValueError('Unrecognized TIMECODE line %d: %s' % (parser.line_no, line))
                                    else:
                                        raise ValueError('Unclosed TIMECODE near line %d' % (parser.line_no,))
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
                m = re_error_line.search(line)
                if m:
                    error_lines.append(line)
                    continue
                raise ValueError('Unrecognized line %d: %s' % (parser.line_no, line))
            if error_lines or p.returncode:
                raise subprocess.CalledProcessError(
                        returncode=p.returncode,
                        cmd=subprocess.list2cmdline(ffprobe_args),
                        output='\n'.join(error_lines))


    def iter_packets(self, file, *, dry_run=False):
        from qip.parser import lines_parser
        ffprobe_args = [
            '-loglevel', 'panic', '-hide_banner',
            '-i', str(file),
            '-show_packets',
        ]
        with self.popen(*ffprobe_args,
                        stdout=subprocess.PIPE, text=True,
                        dry_run=dry_run) as p:
            parser = lines_parser(p.stdout)
            for line in parser:
                line = line.strip()
                if line == '[PACKET]':
                    packet = Ffprobe.Packet()
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
                        if line == '[/PACKET]':
                            break
                        raise ValueError('Unrecognized PACKET line %d: %s' % (parser.line_no, line))
                    else:
                        raise ValueError('Unclosed PACKET near line %d' % (parser.line_no,))
                    yield frame
                    continue
                raise ValueError('Unrecognized line %d: %s' % (parser.line_no, line))

ffprobe = Ffprobe()

# vim: ft=python ts=8 sw=4 sts=4 ai et
