# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'ffmpeg',
        'ffprobe',
        ]

from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import collections
import contextlib
import errno
import functools
import logging
import math
import os
import pexpect
import re
import subprocess
import sys
import types
log = logging.getLogger(__name__)

from .perf import perfcontext
from .exec import *
from .exec import _SpawnMixin, spawn as _exec_spawn, popen_spawn as _exec_popen_spawn, arg2cmdarg
from .parser import lines_parser
from .utils import byte_decode, Timestamp as _BaseTimestamp, Ratio, round_half_up, StreamTransform, Constants, grouper
from qip.file import *
from qip.collections import OrderedSet
from qip.app import app

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

class TimestampInterval(object):

    start = None
    end = None
    start_is_offset = False
    end_is_offset = False

    def __init__(self, start, end, start_is_offset=False, end_is_offset=False):
        self.start = start
        self.end = end
        self.start_is_offset = start_is_offset
        self.end_is_offset = end_is_offset
        super().__init__()

    def __str__(self):
        s = ''
        if self.start is not None:
            if self.start_is_offset:
                s += '+'
                s += str(self.start)
        if self.end is not None:
            s += '%'
            if self.end_is_offset:
                s += '+'
                s += str(self.end)
        return s

class MetadataFile(TextFile):
    # [ffmpeg-1]: https://ffmpeg.org/ffmpeg-formats.html#Metadata-1

    open_encoding = 'utf-8'

    version = 1
    section = None

    DEFAULT_CHAPTER_TIMEBASE = Fraction(1, 1000000000)  # nanoseconds
    DEFAULT_OUTPUT_CHAPTER_TIMEBASE = Fraction(1, 1000)  # milliseconds

    def __init__(self, *args, **kwargs):
        self.sections = []
        super().__init__(*args, **kwargs)

    def load(self):
        self.version = None
        self.sections = []
        from .parser import lines_parser
        with self.open('r') as fp:  # Could already be opened (temp file, write, load)
            parser = lines_parser(fp)

            # [ffmpeg-1] A file consists of a header and a number of metadata tags divided into sections, each on its own line.

            parser.advance()
            parser.line = (parser.line or '').rstrip('\r\n')
            if parser.re_match(r'^;FFMETADATA(?P<version>\d+)\s*$'):
                # [ffmpeg-1] The header is a ‘;FFMETADATA’ string, followed by a version number (now 1).
                self.version = int(parser.match.group('version'))
                if self.version == 1:
                    pass
                else:
                    raise ValueError(f'Unsupported ffmpeg metadata version: {self.version}')
            else:
                parser.raiseValueError('Invalid ffmpeg metadata header: {line!r}', input=self)

            # [ffmpeg-1] Immediately after header follows global metadata
            section = 'GLOBAL'
            section_tags = collections.OrderedDict()
            self.sections.append((section, section_tags))
            while parser.advance():
                parser.line = (parser.line or '').rstrip('\r\n')
                if parser.re_match(r'^\s*[;#]|^\s*$'):
                    # [ffmpeg-1] Empty lines and lines starting with ‘;’ or ‘#’ are ignored.
                    pass
                elif parser.re_match(r'^(?P<key>[^=]+)=(?P<value>.*)'):
                    # [ffmpeg-1] Metadata tags are of the form ‘key=value’
                    # [ffmpeg-1] Note that whitespace in metadata (e.g. ‘foo = bar’) is considered to be a part of the tag (in the example above key is ‘foo ’, value is ‘ bar’).
                    key = parser.match.group('key')
                    value = parser.match.group('value')
                    section_tags[key] = value
                elif parser.re_match(r'\[(?P<section>\w+)\]'):
                    # [ffmpeg-1] After global metadata there may be sections with per-stream/per-chapter metadata.
                    # [ffmpeg-1] A section starts with the section name in uppercase (i.e. STREAM or CHAPTER) in brackets (‘[’, ‘]’) and ends with next section or end of file.
                    section = parser.match.group('section')
                    section_tags = collections.OrderedDict()
                    if section in ('STREAM', 'CHAPTER'):
                        pass
                    else:
                        raise ValueError(f'Unsupported ffmpeg metadata section: {section}')
                    self.sections.append((section, section_tags))
                else:
                    parser.raiseValueError('Invalid ffmpeg metadata line: {line!r}', input=self)

            # TODO [ffmpeg-1] Metadata keys or values containing special characters (‘=’, ‘;’, ‘#’, ‘\’ and a newline) must be escaped with a backslash ‘\’.

    def create(self, file=None):
        if file is None:
            file = self.fp
        if file is None:
            with self.open('w') as file:
                return self.create(file=file)
        print(f';FFMETADATA{self.version}', file=file)
        for section, section_tags in self.sections:
            if section == 'GLOBAL':
                for key, value in section_tags.items():
                    print(f'{key}={value}', file=file)
        for section, section_tags in self.sections:
            if section == 'GLOBAL':
                pass
            else:
                print(f'[{section}]', file=file)
                for key, value in section_tags.items():
                    print(f'{key}={value}', file=file)

    @classmethod
    def NamedTemporaryFile(cls, *, suffix=None, **kwargs):
        if suffix is None:
            suffix = '.metadata.txt'
        return super().NamedTemporaryFile(suffix=suffix, **kwargs)

    @property
    def chapters(self):
        from qip.mm import Chapter, Chapters
        chaps = Chapters()
        no = 0
        for section, section_tags in self.sections:
            if section == 'CHAPTER':
                timebase = section_tags.get('TIMEBASE', None)
                timebase = self.DEFAULT_CHAPTER_TIMEBASE if self.DEFAULT_CHAPTER_TIMEBASE is None else Fraction(timebase)
                start = section_tags.get('START', None)
                start = None if start is None else int(start) * timebase
                end = section_tags.get('END', None)
                end = None if end is None else int(end) * timebase
                title = section_tags.get('title', None)
                no += 1
                chap = Chapter(start=start, end=end, title=title, no=no)
                chaps.chapters.append(chap)
        return chaps

    @chapters.setter
    def chapters(self, chaps):
        self.sections = [(section, section_tags)
                         for section, section_tags in self.sections
                         if section != 'CHAPTER']
        for chap in chaps:
            section = 'CHAPTER'
            section_tags = collections.OrderedDict()
            # [ffmpeg-1] At the beginning of a chapter section there may be an optional timebase to be used for start/end values. It must be in form ‘TIMEBASE=num/den’, where num and den are integers. If the timebase is missing then start/end times are assumed to be in nanoseconds.
            section_tags['TIMEBASE'] = timebase = self.DEFAULT_OUTPUT_CHAPTER_TIMEBASE
            # [ffmpeg-1] Next a chapter section must contain chapter start and end times in form ‘START=num’, ‘END=num’, where num is a positive integer.
            if chap.start is not None:
                section_tags['START'] = int(round_half_up(chap.start / timebase))
            if chap.end is not None:
                section_tags['END'] = int(round_half_up(chap.end / timebase))
            if chap.title is not None:
                section_tags['title'] = chap.title
            self.sections.append((section, section_tags))


class ConcatScriptFile(TextFile):

    ffconcat_version = 1.0
    files = None  # Array of ConcatScriptFile.File or qip.File (file_name attribute required)

    class File(object):

        file_name = None
        duration = None

        def __init__(self, file_name, duration=None):
            self.file_name = toPath(file_name)
            if '..' in os.fspath(self.file_name):
                raise ValueError(f'ffmpeg does not properly handle paths containing \'..\': {self.file_name}')
            self.duration = None if duration is None else Timestamp(duration)
            super().__init__()

        def __fspath__(self):
            return os.fspath(self.file_name)

    def __init__(self, file_name):
        self.files = []
        super().__init__(file_name)

    def create(self, file=None, absolute=False):
        if file is None:
            file = self.fp
        if file is None:
            with self.open('w') as file:
                return self.create(file=file, absolute=absolute)
        if self.ffconcat_version is not None:
            print(f'ffconcat version {self.ffconcat_version}', file=file)
        for file_entry in self.files:
            esc_file = file_entry
            if absolute:
                esc_file = Path(esc_file).resolve()
            esc_file = os.fspath(esc_file).replace(r'\\', '\\\\').replace("'", r"'\''")
            print(f'file \'{esc_file}\'', file=file)
            if getattr(file_entry, 'duration', None) is not None:
                print(f'duration {Timestamp(file_entry.duration)}', file=file)

    @classmethod
    def NamedTemporaryFile(cls, *, suffix=None, **kwargs):
        if suffix is None:
            suffix = '.concat.lst'
        return super().NamedTemporaryFile(suffix=suffix, **kwargs)

    def pprint(self, *, deep=True, heading='Files:', file=None):
        if file is None:
            file = sys.stdout
        files = self.files
        if heading:
            print(heading, file=file)
        from tabulate import tabulate
        files_table = [
            (i,
             os.fspath(f),
             f.duration.canonical_str(precision=3) if getattr(f, 'duration', None) is not None else '',
             )
            for i, f in enumerate(files, start=1)]
        print(
            tabulate(files_table,
                     headers=['No', 'Name', 'Duration'],
                     colalign=['right', 'left', 'right'],
                     tablefmt='simple'),
            file=StreamTransform.indenter(file))

class _FfmpegSpawnMixin(_SpawnMixin):

    invocation_purpose = None
    show_progress_bar = None
    progress_bar = None
    progress_start_pts_time = None
    progress_start_frame = None
    progress_bar_max = None
    progress_bar_title = None
    on_progress_bar_line = False
    num_errors = 0
    errors_seen = None
    current_info_section = None
    streams_info = None
    progress_match = None

    def __init__(self, *args, invocation_purpose=None,
                 show_progress_bar=None, progress_bar_max=None, progress_bar_title=None,
                 encoding=None, errors=None,
                 env=None, **kwargs):
        assert encoding is not None or errors is not None, 'text mode required for ffmpeg spawn parsing'
        self.invocation_purpose = invocation_purpose
        if show_progress_bar is None:
            show_progress_bar = progress_bar_max is not None
        self.show_progress_bar = show_progress_bar
        self.progress_bar_max = progress_bar_max
        self.progress_bar_title = progress_bar_title
        self.progress_start_pts_time = Timestamp(0)
        self.progress_start_frame = 0
        self.errors_seen = OrderedSet()
        self.streams_info = {
            'input': {},
            'output': {},
        }
        if self.invocation_purpose == 'cropdetect':
            self.cropdetect_result = None
            self.cropdetect_frames_count = 0
        env = dict(env or os.environ)
        env['AV_LOG_FORCE_NOCOLOR'] = '1'
        env['TERM'] = 'dumb'
        env.pop('TERMCAP', None)
        super().__init__(*args, env=env,
                         encoding=encoding, errors=errors,
                         **kwargs)

    def log_line(self, str, *, level=logging.INFO):
        if log.isEnabledFor(level):
            str = str.rstrip('\r\n')
            if str:
                if self.on_progress_bar_line:
                    print('')
                    self.on_progress_bar_line = False
                log.log(level, str)
        return True

    def print_line(self, str, *, level=logging.INFO, style=None):
        if log.isEnabledFor(level):
            str = str.rstrip('\r\n')
            if str:
                if self.on_progress_bar_line:
                    print('')
                    self.on_progress_bar_line = False
                if style:
                    from prompt_toolkit.formatted_text import FormattedText
                    app.print(FormattedText([(style, str)]))
                else:
                    app.print(str)
        return True

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
        self.print_line(str, level=logging.DEBUG)
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
        self.print_line(str, level=logging.DEBUG)
        print('', end='', flush=True)
        return True

    def start_segment_file(self, str):
        self.progress_start_pts_time += Timestamp(self.match.group('pts_time'))
        self.progress_start_frame += int(self.match.group('frame'))
        self.log_line(str)
        return True

    def progress_line(self, str):
        self.progress_match = self.match
        if self.progress_bar is not None:
            if self.progress_bar_max:
                if isinstance(self.progress_bar_max, _BaseTimestamp):
                    if Timestamp(byte_decode(self.match.group('time'))).seconds >= 0.0:
                        v = Timestamp(byte_decode(self.match.group('time'))).seconds + self.progress_start_pts_time.seconds
                        self.progress_bar.goto(v)
                else:
                    if int(self.match.group('frame')) >= 0:
                        self.progress_bar.goto(int(self.match.group('frame')) + self.progress_start_frame)
                fps = self.match.group('fps')
                if fps:
                    if Decimal(byte_decode(fps)) >= 0:
                        self.progress_bar.fps = Decimal(byte_decode(fps))
            else:
                self.progress_bar.next()
            self.on_progress_bar_line = True
        else:
            self.log_line(str, level=logging.DEBUG)
        return True

    def parsed_cropdetect_line(self, str):
        self.cropdetect_result = byte_decode(self.match.group('crop'))
        if self.invocation_purpose == 'cropdetect':
            self.cropdetect_frames_count += 1
        if self.progress_bar is not None:
            if self.progress_bar_max:
                if self.progress_bar.index == 0:
                    #self.progress_bar.message = f'{self.command} cropdetect'
                    self.progress_bar.message = 'Cropdetect'
                    self.progress_bar.suffix += ' crop=%(crop)s'
                self.progress_bar.crop = self.cropdetect_result
                if isinstance(self.progress_bar_max, _BaseTimestamp):
                    if Timestamp(byte_decode(self.match.group('time'))).seconds >= 0.0:
                        v = Timestamp(byte_decode(self.match.group('time'))).seconds
                        self.progress_bar.goto(v)
                else:
                    # self.progress_bar.goto(int(self.match.group('frame')))
                    self.progress_bar.next()
                # self.progress_bar.fps = Decimal(byte_decode(self.match.group('fps')))
            else:
                self.progress_bar.next()
            self.on_progress_bar_line = True
            try:
                stop_crop = self.invocation_purpose == 'cropdetect' \
                    and self.cropdetect_result == '{width}:{height}:0:0'.format_map(self.streams_info['input'][0]['streams']['0:0'])
            except KeyError as e:
                pass  # print('') ; print(f'e={e}')
            else:
                if stop_crop:
                    log.debug('No cropping possible; Quit!')
                    try:
                        self.send(b'q' if self.string_type is bytes else 'q')
                    except OSError:  # [Errno 5] Input/output error
                        return False
        else:
            str = byte_decode(str).rstrip('\r\n')
            if self.on_progress_bar_line:
                print('')
                self.on_progress_bar_line = False
            print(str)
        return True

    def progress_pass(self, str):
        if self.progress_bar is not None:
            pass_name = self.match.group('pass_name')
            self.progress_bar.message = f'{self.progress_bar_title or self.command} -- {pass_name}'
            self.progress_bar.reset()
            #self.progress_bar.update()
            self.on_progress_bar_line = True
        else:
            str = byte_decode(str).rstrip('\r\n')
            if self.on_progress_bar_line:
                print('')
                self.on_progress_bar_line = False
            print(str)
        return True

    def unknown_info_line(self, str):
        return self.unknown_line(str, level=logging.DEBUG, style='class:info')

    def unknown_verbose_line(self, str):
        return self.unknown_line(str, level=logging.DEBUG, style='class:verbose')

    def unknown_warning_line(self, str):
        return self.unknown_line(str, level=logging.WARNING, style='class:warning')

    def unknown_error_line(self, str):
        return self.unknown_line(str, level=logging.ERROR, style='class:error')

    def unknown_line(self, str, **kwargs):
        str = str.rstrip('\r\n')
        if str:
            self.print_line(f'UNKNOWN: {str!r}', **kwargs)
        return True

    def generic_error(self, str, level=logging.ERROR, error_tag=None):
        str = str.rstrip('\r\n')
        self.log_line(str, level=level)
        self.num_errors += 1
        self.errors_seen.add(error_tag or str)
        return True

    def generic_debug_line(self, str):
        self.log_line(str, level=logging.DEBUG)
        return True

    def prompt_file_overwrite(self, str):
        self.generic_error(str, error_tag='file-already-exists')
        file_name = byte_decode(self.match.group('file_name'))
        raise OSError(errno.EEXIST, f'File exists: {file_name}')

    def terminal_escape_sequence(self, str):
        return True

    def eof(self, _dummy):
        str = byte_decode(self.before).rstrip('\r\n')
        if str:
            self.log_line(f'EOF: {str!r}', level=logging.DEBUG)
        return True

    def get_pattern_dict(self):
        re_eol = r'(?:\r?\n|\r)'
        pattern_dict = collections.OrderedDict([

            # frame=   39 fps=0.0 q=-0.0 Lsize=    4266kB time=00:00:01.60 bitrate=21801.0kbits/s speed=6.98x
            # [info] frame=  776 fps=119 q=-0.0 size=  129161kB time=00:00:25.86 bitrate=40915.9kbits/s speed=3.95x
            # [info] frame= 1052 fps=149 q=-1.0 size=N/A time=00:00:43.62 bitrate=N/A speed=6.18x
            # size=       0kB time=01:03:00.94 bitrate=   0.0kbits/s speed=2.17e+07x
            # [info] size= 1408536kB time=00:20:52.03 bitrate=9216.0kbits/s speed=48.1x
            # frame= 2235 fps=221 q=-0.0 size= 1131482kB time=00:01:14.60 bitrate=124237.6kbits/s dup=447 drop=0 speed=7.37x
            # frame= 7068 fps=0.0 q=-1.0 q=-1.0 size=  126208kB time=00:04:58.13 bitrate=3467.9kbits/s speed= 595x    '
            # [info] frame=21054 fps=0.0 q=-1.0 size=  244736kB time=00:14:38.08 bitrate=2283.2kbits/s speed=1.75e+03x
            (fr'^(?:\[info\]\s)?(?:frame= *(?P<frame>\d+) +fps= *(?P<fps>\S+) +q= *(?P<q>\S+)(?: +q= *(?P<q2>\S+))? )?L?size= *(?:N/A|(?P<size>\S+)) +time= *(?P<time>\S+) +bitrate= *(?:N/A|(?P<bitrate>\S+))(?: +dup= *(?P<dup>\S+))?(?: +drop= *(?P<drop>\S+))? +speed= *(?P<speed>\S+) *{re_eol}', self.progress_line),

            # [Parsed_cropdetect_1 @ 0x56473433ba40] x1:0 x2:717 y1:0 y2:477 w:718 h:478 x:0 y:0 pts:504504000 t:210.210000 crop=718:478:0:0
            (fr'^\[Parsed_cropdetect\S* @ \S+\]\s(?:\[info\]\s)?x1:(?P<x1>\S+) x2:(?P<x2>\S+) y1:(?P<y1>\S+) y2:(?P<y2>\S+) w:(?P<w>\S+) h:(?P<h>\S+) x:(?P<x>\S+) y:(?P<y>\S+) pts:(?P<pts>\S+) t:(?P<time>\S+) crop=(?P<crop>\S+) *{re_eol}', self.parsed_cropdetect_line),

            (fr'^\[ffmpeg-2pass-pipe\]\s(?P<pass_name>PASS [12]){re_eol}', self.progress_pass),

            # [info] Input #0, h264, from 'test-movie3/track-00-video.h264':
            # [info] Input #0, h264, from 'pipe:':
            (fr'^(?:\[info\]\s)? *Input #(?P<index>\S+), (?P<format>\S+), from \'(?P<file_name>.+?)\':{re_eol}', self.start_input_info_section),
            # [info] Output #0, null, to 'pipe:':
            (fr'^(?:\[info\]\s)? *Output #(?P<index>\S+), (?P<format>\S+), to \'(?P<file_name>.+?)\':{re_eol}', self.start_output_info_section),
            # [info]     Stream #0:0: Video: h264 (High), yuv420p(progressive), 1920x1080 [SAR 1:1 DAR 16:9], 24.08 fps, 23.98 tbr, 1200k tbn, 47.95 tbc
            # [info]     Stream #0:0: Video: wrapped_avframe, yuv420p, 1920x1080 [SAR 1:1 DAR 16:9], q=2-31, 200 kb/s, 23.98 fps, 23.98 tbn, 23.98 tbc
            # [info]     Stream #0:0: Video: wrapped_avframe, 1 reference frame, yuv420p(left), 720x480 [SAR 8:9 DAR 4:3], q=2-31, 200 kb/s, 29.97 fps, 29.97 tbn, 29.97 tbc
            # [info]     Stream #0:0: Video: mpeg2video (Main), 1 reference frame, yuv420p(tv, top first, left), 720x480 [SAR 8:9 DAR 4:3], 29.97 fps, 29.97 tbr, 1200k tbn, 59.94 tbc
            # [info]     Stream #0:0: Video: h264 (High), 1 reference frame, yuv420p(progressive, left), 1920x1080 (1920x1088) [SAR 1:1 DAR 16:9], 24.08 fps, 23.98 tbr, 1200k tbn, 47.95 tbc
            # [info]     Stream #0:0: Video: vc1 (Advanced), 1 reference frame (WVC1 / 0x31435657), yuv420p(bt709, progressive, left), 1920x1080 [SAR 1:1 DAR 16:9], 23.98 fps, 23.98 tbr, 23.98 tbn, 47.95 tbc
            # [info]     Stream #0:0: Video: ffv1, 1 reference frame (FFV1 / 0x31564646), yuv420p(left), 720x480, SAR 8:9 DAR 4:3, 23.98 fps, 23.98 tbr, 1k tbn, 1k tbc (default)'
            (fr'^(?:\[info\]\s)? *Stream #(?P<stream_no>\S+)(?:\((?P<language>\w{3})\))?: (?P<stream_type>Video): (?P<format1>[^,]+)(?:, (?P<num_ref_frames>\d+) reference frame(?: \([^)]+\))?)?, (?P<format2>[^(,]+(?:\([^)]+\))?), (?P<width>\d+)x(?P<height>\d+)[, ][^\r\n]*{re_eol}', self.start_stream_info_section),
            # [info]     Stream #0:1(eng): Audio: opus ([255][255][255][255] / 0xFFFFFFFF), 48000 Hz, 5.1, fltp, delay 312 (default)
            # [info]     Stream #0:2(fra): Audio: opus ([255][255][255][255] / 0xFFFFFFFF), 48000 Hz, 5.1, fltp, delay 312
            (fr'^(?:\[info\]\s)? *Stream #(?P<stream_no>\S+)(?:\((?P<language>\w{3})\))?: (?P<stream_type>Audio): (?P<format1>[^,]+)(?: \(\[\d+\]\[\d+\]\[\d+\]\[\d+\] / 0x[0-9A-Fa-f]+\))?, (?P<sample_rate>\d+) Hz, (?P<channel_layout>\S+), (?P<sample_fmt>(?:[us]\d+|flt|dbl)p?), delay (?P<delay>\d+)(?: \((?P<disposition>default)\))?[^\r\n]*{re_eol}', self.start_stream_info_section),
            # [info]     Stream #0:3(eng): Subtitle: hdmv_pgs_subtitle ([255][255][255][255] / 0xFFFFFFFF), 1920x1080
            # [info]     Stream #0:4(fra): Subtitle: hdmv_pgs_subtitle ([255][255][255][255] / 0xFFFFFFFF), 1920x1080
            # [info]     Stream #0:5(fra): Subtitle: webvtt (forced)
            (fr'^(?:\[info\]\s)? *Stream #(?P<stream_no>\S+)(?:\((?P<language>\w{3})\))?: (?P<stream_type>Subtitle): (?P<format1>[^,]+)(?: \(\[\d+\]\[\d+\]\[\d+\]\[\d+\] / 0x[0-9A-Fa-f]+\))?(?:, (?P<width>\d+)x(?P<height>\d+))?(?: \((?P<disposition>forced)\))?[^\r\n]*{re_eol}', self.start_stream_info_section),

            (fr'^(?:\[warning\]\s)?Overriding aspect ratio with stream copy may produce invalid files{re_eol}', self.generic_debug_line),
            (fr'^(?:\[warning\]\s)?Output file is empty, nothing was encoded \(check -ss / -t / -frames parameters if used\){re_eol}', functools.partial(self.generic_error, level=logging.WARNING, error_tag='output-file-empty-nothing-encoded')),

            # File 'TheTruthAboutCatsAndDogs/title_t00.demux.mkv' already exists. Overwrite ? [y/N]
            (fr'^File \'(?P<file_name>.+?)\' already exists\. Overwrite ?\? \[y/N\] *$', self.prompt_file_overwrite),

            # PTS 21474840773, next:1417490188 invalid dropping st:0
            # DTS 21474840774, next:1417531896 st:0 invalid dropping
            (fr'^(?:\[warning\]\s)?(?P<dts_or_pts>DTS|PTS) \d+, next:\d+ ?(invalid dropping st:0|st:0 invalid dropping){re_eol}', self.generic_debug_line),

            # [h264 @ 0x55f98a7caa00] [error] sps_id 1 out of range
            # [NULL @ 0x55f98a7c3b80] [error] sps_id 1 out of range
            (fr'^\[\S+ @ 0x[0-9a-f]+\] (?:\[error\]\s)?sps_id 1 out of range{re_eol}', self.generic_debug_line),

            # [mp4 @ 0x55ce3d6c48c0] [warning] pts has no value
            (fr'^\[\S+ @ 0x[0-9a-f]+\] (?:\[warning\]\s)?pts has no value{re_eol}', self.generic_debug_line),

            #     Last message repeated 1604 times
            (fr'^\s*Last message repeated (?P<count>\d+) times{re_eol}', self.generic_debug_line),

            # [stream_segment,ssegment @ 0x55d20668d080] [warning] Non-monotonous DTS in output stream 0:0; previous: 75717, current: 75717; changing to 75718. This may result in incorrect timestamps in the output file.
            # [ipod @ 0x564125e0a940] Non-monotonous DTS in output stream 0:0; previous: 1554006132, current: 1554005644; changing to 1554006133. This may result in incorrect timestamps in the output file.
            # [ipod @ 0x55b1ace8a280] [warning] Non-monotonous DTS in output stream 0:0; previous: 1628578383, current: 1628577279; changing to 1628578384. This may result in incorrect timestamps in the output file.
            (fr'^(?:\[\S+ @ \w+\]\s)?(?:\[warning\]\s)? *Non-monotonous DTS in output stream (?P<stream>\S+); previous: (?P<previous_dts>\d+), current: (?P<current_dts>\d+); changing to (?P<changing_dts>\d+)\. This may result in incorrect timestamps in the output file\.{re_eol}', self.generic_debug_line),
            # [stream_segment,ssegment @ 0x55842aa56b40] [verbose] segment:'Labyrinth4K/Labyrinth (1986)/track-00-video-chap02.h265' starts with packet stream:0 pts:6000 pts_time:250.25 frame:6000
            (fr'^(?:\[\S+ @ \w+\]\s)?(?:\[verbose\]\s)? *segment:\'(?P<segment_file>.+)\' starts with packet stream:(?P<stream>\S+) pts:(?P<pts>\S+) pts_time:(?P<pts_time>\S+) frame:(?P<frame>\S+){re_eol}', self.start_segment_file),

            # [NULL @ 0x555ff5d3b1c0] sample/frame number mismatch in adjacent frames
            # TODO Re-open https://trac.ffmpeg.org/ticket/5937 ?
            (fr'^(?:\[\S+ @ \w+\]\s)?sample/frame number mismatch in adjacent frames{re_eol}', self.generic_debug_line),

            # [ac3 @ 0x563251c008c0] Estimating duration from bitrate, this may be inaccurate
            (fr'^(?:\[\S+ @ \w+\]\s)?Estimating duration from bitrate, this may be inaccurate{re_eol}', self.generic_debug_line),

            (fr'^\[info\]\s[^\r\n]*?{re_eol}', self.unknown_info_line),
            (fr'^\[verbose\]\s[^\r\n]*?{re_eol}', self.unknown_verbose_line),
            (fr'^\[warning\]\s[^\r\n]*?{re_eol}', self.unknown_warning_line),
            (fr'^\[error\]\s[^\r\n]*?{re_eol}', self.unknown_error_line),

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
                    if isinstance(self.progress_bar_max, _BaseTimestamp):
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

    def __init__(self, *args, logfile=None, **kwargs):
        # if logfile is None: import sys ; logfile = sys.stdout
        super().__init__(*args, logfile=logfile, **kwargs)
    pass

class FfmpegPopenSpawn(_FfmpegSpawnMixin, _exec_popen_spawn):
    pass

class FfmpegOptions(collections.UserList):

    colon_options = None

    def __init__(self, initlist=None):
        self.colon_options = set(
            initlist.colon_options if isinstance(initlist, FfmpegOptions)
            else ())
        super().__init__(initlist=initlist)

    def get_option(self, option, default=Constants.NotSet):
        try:
            idx = self.index(option)
        except ValueError:
            if default is Constants.NotSet:
                raise IndexError(f'Option {option} not set')
            return default
        else:
            return self[idx + 1]

    def set_option(self, option, value):
        try:
            idx = self.index(option)
        except ValueError:
            self += [option, value]
        else:
            self[idx + 1] = value

    def del_option(self, option, value):
        try:
            idx = self.index(option)
        except ValueError:
            raise IndexError(f'Option {option} not set')
        else:
            del self[idx:idx + 2]

    def pop_option(self, option, default=Constants.NotSet):
        try:
            idx = self.index(option)
        except ValueError:
            if default is Constants.NotSet:
                raise IndexError(f'Option {option} not set')
            return default
        else:
            value = self[idx + 1]
            del self[idx:idx + 2]
            return value

    def append_colon_option(self, option, value):
        try:
            idx = self.index(option)
        except ValueError:
            self += [option, value]
        else:
            old_value = self[idx + 1]
            if old_value:
                self[idx + 1] = f'{old_value}:{value}'
            else:
                self[idx + 1] = value
        self.colon_options.add(option)

    def __add__(self, other):
        if isinstance(other, FfmpegOptions):
            new = self.__class__(self)
            new += other
            return new
        else:
            return super().__add__(other)

    def __radd__(self, other):
        # Refuse to create a new object that has different semantics than `other`
        return other + self.data

    def __iadd__(self, other):
        if isinstance(other, FfmpegOptions):
            self.extend(other)
        else:
            super().__iadd__(other)
        return self

    def extend(self, other):
        if isinstance(other, FfmpegOptions):
            colon_options = self.colon_options
            colon_options.update(other.colon_options)
            for option, value in grouper(other.data, 2):
                if option in colon_options:
                    self.append_colon_option(option, value)
                else:
                    self.set_option(option, value)
        else:
            super().extend(other)

    def __repr__(self):
        s = f'{self.__class__.__name__}({self.data!r}'
        if self.colon_options:
            s += f', colon_options={self.colon_options!r}'
        s += ')'
        return s

class _Ffmpeg(Executable):

    Timestamp = Timestamp
    TimestampInterval = TimestampInterval
    ConcatScriptFile = ConcatScriptFile
    MetadataFile = MetadataFile
    Options = FfmpegOptions

    encoding = 'utf-8'
    encoding_errors = 'replace'

    run_func = Executable._spawn_run_func
    # TODO popen_func = Executable._spawn_popen_func
    run_func_options = Executable.run_func_options + (
        'invocation_purpose',
        'show_progress_bar',
        'progress_bar_max',
        'progress_bar_title',
        'encoding',
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
                cmdargs.append(arg2cmdarg(v))
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
                if 'ffmpeg' in os.fspath(self.name):
                    pass # kwargs.setdefault('stats', True)  # included in info
            else:
                kwargs['loglevel'] = 'warning'
                if 'ffmpeg' in os.fspath(self.name):
                    kwargs.setdefault('stats', True)

        if 'hide_banner' not in kwargs and '-hide_banner' not in args:
            if not log.isEnabledFor(logging.VERBOSE):
                kwargs['hide_banner'] = True

        return super().build_cmd(*args, **kwargs) + out_file_args

    def input_args(self, inputfile, attach=False):
        if not isinstance(inputfile, File):
            inputfile = File.new_by_file_name(inputfile)
        args = []
        kwargs = {}
        args += self.kwargs_to_cmdargs(**inputfile.decode_ffmpeg_args())
        args += [
            '-attach' if attach else '-i',
            inputfile,
        ]
        return args

class Ffmpeg(_Ffmpeg):

    name = 'ffmpeg'

    environ = {
        'TERM': 'dummy',
    }

    color_primaries_option_map = collections.OrderedDict((  # <int>        ED.V...... color primaries (from 1 to INT_MAX) (default unknown)
        ('bt709', 1),               # ED.V...... BT.709
        ('unknown', 2),             # ED.V...... Unspecified
        ('bt470m', 4),              # ED.V...... BT.470 M
        ('bt470bg', 5),             # ED.V...... BT.470 BG
        ('smpte170m', 6),           # ED.V...... SMPTE 170 M
        ('smpte240m', 7),           # ED.V...... SMPTE 240 M
        ('film', 8),                # ED.V...... Film
        ('bt2020', 9),              # ED.V...... BT.2020
        ('smpte428', 10),           # ED.V...... SMPTE 428-1
        ('smpte428_1', 10),         # ED.V...... SMPTE 428-1
        ('smpte431', 11),           # ED.V...... SMPTE 431-2
        ('smpte432', 12),           # ED.V...... SMPTE 422-1
        ('jedec-p22', 22),          # ED.V...... JEDEC P22
        ('ebu3213', 22),            # ED.V...... EBU 3213-E
        ('unspecified', 2),         # ED.V...... Unspecified
    ))

    color_trc_option_map = collections.OrderedDict((  # <int>        ED.V...... color transfer characteristics (from 1 to INT_MAX) (default unknown)
        ('bt709', 1),               # ED.V...... BT.709
        ('unknown', 2),             # ED.V...... Unspecified
        ('gamma22', 4),             # ED.V...... BT.470 M
        ('gamma28', 5),             # ED.V...... BT.470 BG
        ('smpte170m', 6),           # ED.V...... SMPTE 170 M
        ('smpte240m', 7),           # ED.V...... SMPTE 240 M
        ('linear', 8),              # ED.V...... Linear
        ('log100', 9),              # ED.V...... Log
        ('log316', 10),             # ED.V...... Log square root
        ('iec61966-2-4', 11),       # ED.V...... IEC 61966-2-4
        ('bt1361e', 12),            # ED.V...... BT.1361
        ('iec61966-2-1', 13),       # ED.V...... IEC 61966-2-1
        ('bt2020-10', 14),          # ED.V...... BT.2020 - 10 bit
        ('bt2020-12', 15),          # ED.V...... BT.2020 - 12 bit
        ('smpte2084', 16),          # ED.V...... SMPTE 2084
        ('smpte428', 17),           # ED.V...... SMPTE 428-1
        ('arib-std-b67', 18),       # ED.V...... ARIB STD-B67
        ('unspecified', 2),         # ED.V...... Unspecified
        ('log', 9),                 # ED.V...... Log
        ('log_sqrt', 10),           # ED.V...... Log square root
        ('iec61966_2_4', 11),       # ED.V...... IEC 61966-2-4
        ('bt1361', 12),             # ED.V...... BT.1361
        ('iec61966_2_1', 13),       # ED.V...... IEC 61966-2-1
        ('bt2020_10bit', 14),       # ED.V...... BT.2020 - 10 bit
        ('bt2020_12bit', 15),       # ED.V...... BT.2020 - 12 bit
        ('smpte428_1', 17),         # ED.V...... SMPTE 428-1
    ))

    colorspace_option_map = collections.OrderedDict((  # <int>        ED.V...... color space (from 0 to INT_MAX) (default unknown)
        ('rgb', 0),                 # ED.V...... RGB
        ('bt709', 1),               # ED.V...... BT.709
        ('unknown', 2),             # ED.V...... Unspecified
        ('fcc', 4),                 # ED.V...... FCC
        ('bt470bg', 5),             # ED.V...... BT.470 BG
        ('smpte170m', 6),           # ED.V...... SMPTE 170 M
        ('smpte240m', 7),           # ED.V...... SMPTE 240 M
        ('ycgco', 8),               # ED.V...... YCGCO
        ('bt2020nc', 9),            # ED.V...... BT.2020 NCL
        ('bt2020c', 10),            # ED.V...... BT.2020 CL
        ('smpte2085', 11),          # ED.V...... SMPTE 2085
        ('unspecified', 2),         # ED.V...... Unspecified
        ('ycocg', 8),               # ED.V...... YCGCO
        ('bt2020_ncl', 9),          # ED.V...... BT.2020 NCL
        ('bt2020_cl', 10),          # ED.V...... BT.2020 CL
    ))

    color_range_option_map = collections.OrderedDict((  # <int>        ED.V...... color range (from 0 to INT_MAX) (default unknown)
        ('unknown', 0),             # ED.V...... Unspecified
        ('tv', 1),                  # ED.V...... MPEG (219*2^(n-8))
        ('pc', 2),                  # ED.V...... JPEG (2^n-1)
        ('unspecified', 0),         # ED.V...... Unspecified
        ('mpeg', 1),                # ED.V...... MPEG (219*2^(n-8))
        ('jpeg', 2),                # ED.V...... JPEG (2^n-1)
    ))

    def get_option_value(cls, option, value):
        option_map = getattr(cls, f'{option}_option_map')
        if isinstance(value, int):
            for s, v in option_map.items():
                if v == value:
                    return s
        elif isinstance(value, str):
            if value in option_map:
                return value
        raise ValueError(f'Invalid {option} value: {value!r}')

    def get_option_value_int(cls, option, value):
        option_map = getattr(cls, f'{option}_option_map')
        if isinstance(value, int):
            for s, v in option_map.items():
                if v == value:
                    return v
        elif isinstance(value, str):
            if value in option_map:
                return option_map[value]
        raise ValueError(f'Invalid {option} value: {value!r}')

    def _run(self, *args, run_func=None, dry_run=False,
             slurm=False, slurm_cpus_per_task=None,
             progress_bar_max=None,
             progress_bar_title=None,
             **kwargs):
        args = list(args)

        if run_func:
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

        if slurm:
            try:
                from .slurm import do_srun_cmd
            except ImportError:
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
            run_kwargs['stdin_file'] = stdin_file.resolve()
            run_kwargs['stdout_file'] = stdout_file.resolve()
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
                    slurm_cpus_per_task = max(math.ceil(int(threads)/2), 1)
            if slurm_cpus_per_task is not None:
                run_kwargs['slurm_cpus_per_task'] = slurm_cpus_per_task
            run_kwargs['slurm_mem'] = '500M'

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
                   skip_frame_nokey=True,
                   cropdetect_seek=None, cropdetect_duration=300,
                   cropdetect_limit=24,  # default
                   cropdetect_round=2,  # Handbrake? ffmpeg default = 0
                   video_filter_specs=None,
                   show_progress_bar=True,
                   progress_bar_title=None,
                   default_ffmpeg_args=[],
                   dry_run=False):
        stream_crop = None
        ffmpeg_args = list(default_ffmpeg_args)
        if cropdetect_seek:
            ffmpeg_args += [
                '-ss', Timestamp(cropdetect_seek),
            ]
        if skip_frame_nokey:
            ffmpeg_args += [
                '-skip_frame', 'nokey',
            ]
        video_filter_specs = list(video_filter_specs or [])
        video_filter_specs.append(f'cropdetect={cropdetect_limit}:{cropdetect_round}:0:0')
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

        with perfcontext('Cropdetect w/ ffmpeg'):
            out = self(*ffmpeg_args,
                       show_progress_bar=show_progress_bar,
                       progress_bar_max=Timestamp(cropdetect_duration),
                       progress_bar_title=progress_bar_title or 'Cropdetect',
                       invocation_purpose='cropdetect',
                       dry_run=dry_run,
                       loglevel=loglevel)

        if not dry_run:
            retry = False
            if skip_frame_nokey and out.spawn.cropdetect_frames_count < 2:
                log.warning(f'Crop detection failed due to only {out.spawn.cropdetect_frames_count} key frames detected; Trying again with non-key frames.')
                skip_frame_nokey = False
                retry = True
            else:
                if not out.spawn.cropdetect_frames_count:
                    # Output file is empty, nothing was encoded (check -ss / -t / -frames parameters if used)
                    # -> skip_frame_nokey=False
                    raise ValueError('Crop detection failed')
                m = re.match(r'^(-?\d+):(-?\d+):(\d+):(\d+)$', out.spawn.cropdetect_result)
                assert m, f'Unrecognized cropdetect result: {out.spawn.cropdetect_result!r}'
                w, h, l, t = stream_crop = (
                    int(m.group(1)),
                    int(m.group(2)),
                    int(m.group(3)),
                    int(m.group(4)))
                if w < 0 or h < 0:
                    if skip_frame_nokey:
                        log.warning(f'Crop detection failed due to no key frames detected; Trying again with non-key frames.')
                        skip_frame_nokey = False
                        retry = True
                    else:
                        raise ValueError(f'Crop detection failed: {out.spawn.cropdetect_result!r}')
                if retry:
                    return self.cropdetect(input_file=input_file,
                                           skip_frame_nokey=skip_frame_nokey,
                                           cropdetect_seek=cropdetect_seek,
                                           cropdetect_duration=cropdetect_duration,
                                           cropdetect_limit=cropdetect_limit,
                                           cropdetect_round=cropdetect_round,
                                           video_filter_specs=video_filter_specs,
                                           show_progress_bar=show_progress_bar,
                                           progress_bar_title=progress_bar_title,
                                           default_ffmpeg_args=default_ffmpeg_args,
                                           dry_run=dry_run)
                assert w > 0 and h > 0 and l >= 0 and t >= 0, (w, h, l, t)
        return stream_crop

ffmpeg = Ffmpeg()

class Ffmpeg2passPipe(_Ffmpeg, PipedPortableScript):

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

        try:
            idx = args.index("-passlogfile")
        except ValueError:
            pass
        else:
            log.debug('-passlogfile provided; Disabling slurm.')
            slurm = False

        if slurm:
            try:
                from .slurm import do_srun_cmd
            except ImportError:
                slurm = False

        with contextlib.ExitStack() as stack:

            run_kwargs = {}
            if slurm:
                run_func = do_srun_cmd
                run_kwargs['stdin_file'] = stdin_file.resolve()
                run_kwargs['stdout_file'] = stdout_file.resolve()
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
                    run_kwargs['slurm_cpus_per_task'] = max(math.ceil(int(threads)/2), 1)
                run_kwargs['slurm_mem'] = '500M'
                if not dry_run:
                    run_kwargs['slurm_tmp'] = stdin_file.stat().st_size * 1.5
            else:
                run_func = run_func or self.run_func or functools.partial(do_exec_cmd, stderr=subprocess.STDOUT)
                args = [
                    '-i', stdin_file,
                    '-o', stdout_file,
                    '--',
                ] + args
                # if not dry_run:
                #     run_kwargs['stdin'] = stack.enter_context(stdin_file.open("rb"))
                #     run_kwargs['stdout'] = stack.enter_context(stdout_file.open("wb"))
                if progress_bar_max is not None:
                    run_kwargs['progress_bar_max'] = progress_bar_max
                if progress_bar_title is not None:
                    run_kwargs['progress_bar_title'] = progress_bar_title or 'Encode'
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

class unit_value(collections.namedtuple(
        'unit_value',
        (
            'val',
            'unit',
        ),
        )):
    pass


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
            'pkt_pos': NA_or_int,  # 13125
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
            '-i', file,
            '-show_frames',
        ]
        error_lines = []

        # [mpeg2video @ 0x55ea4143fe00] [error] end mismatch left=114 1370 at 0 30
        re_error_line = re.compile(r'\[(?P<type>error|panic)\] (?P<msg>.+)')
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
                    if m.group('msg') == 'sps_id 1 out of range':
                        # [h264 @ 0x55f98a7caa00] [error] sps_id 1 out of range
                        # [NULL @ 0x55f98a7c3b80] [error] sps_id 1 out of range
                        pass
                    elif m.group('msg').startswith('missing picture in access unit with size'):
                        # [NULL @ 0x555cde195b80] [error] missing picture in access unit with size 802
                        pass
                    elif m.group('msg') == 'no frame!':
                        # [h264 @ 0x555cde19ca00] [error] no frame!
                        pass
                    elif m.group('msg').endswith(' invalid dropping st:0') \
                        or m.group('msg').endswith(' st:0 invalid dropping'):
                        # PTS 21474840773, next:1417490188 invalid dropping st:0
                        # DTS 21474840774, next:1417531896 st:0 invalid dropping
                        pass
                    elif 'ac-tex damaged at' in m.group('msg') \
                        or 'Warning MVs not available'in m.group('msg'):
                        # [mpeg2video @ 0x55610c7ca940] [error] ac-tex damaged at 8 2
                        # [mpeg2video @ 0x55610c7ca940] [error] Warning MVs not available
                        pass
                    else:
                        error_lines.append(line)
                    continue
                raise ValueError('Unrecognized line %d: %s' % (parser.line_no, line))
            if error_lines or p.returncode:
                print(f'error_lines={error_lines!r}')
                raise subprocess.CalledProcessError(
                        returncode=p.returncode or 0,
                        cmd=subprocess.list2cmdline(ffprobe_args),
                        output='\n'.join(error_lines))

    def iter_packets(self, file, *, dry_run=False):
        from qip.parser import lines_parser
        ffprobe_args = [
            '-loglevel', 'panic', '-hide_banner',
            '-i', file,
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

    class PrintContext(object):

        file = None
        display_optional_fields = True
        section_str = ''
        section_unique_name = ''
        nokey = False
        show_all_entries = True
        entries_to_show = None
        show_value_unit = False
        use_value_prefix = False
        use_byte_value_binary_prefix = False
        use_value_sexagesimal_format = False

        unit_second_str = "s"
        unit_hertz_str = "Hz"
        unit_byte_str = "byte"
        unit_bit_per_second_str = "bit/s"

        def __init__(self, file=None, pretty=False):
            self.file = file
            self.entries_to_show = set()
            if pretty:
                self.show_value_unit = True
                self.use_value_prefix = True
                self.use_byte_value_binary_prefix = True
                self.use_value_sexagesimal_format = True

        def get_file(self):
            file = self.file
            if file is None:
                file = sys.stdout
            return file

        def print_fmt(self, k, f, *args):
            return self.writer_print_string(k, f % args)

        def print_int(self, k, v):
            return self.writer_print_integer(k, v)

        def print_q(self, k, v, s):
            return self.writer_print_rational(k, v, s)

        def print_str(self, k, v):
            return self.writer_print_string(k, v)

        def print_str_opt(self, k, v):
            return self.writer_print_string(k, v, optional=True)

        def print_str_validate(self, k, v):
            return self.writer_print_string(k, v, validate=True)

        def print_time(self, k, v, tb):
            return self.writer_print_time(k, v, tb, is_duration=False)

        def print_ts(self, k, v):
            return self.writer_print_ts(k, v, is_duration=False)

        def print_duration_time(self, k, v, tb):
            return self.writer_print_time(k, v, tb, is_duration=True)

        def print_duration_ts(self, k, v):
            return self.writer_print_ts(k, v, is_duration=True)

        def print_val(self, k, v, u):
            uv = unit_value(v, u)
            return self.writer_print_string(k, self.value_string(uv))

        def print_color_range(self, color_range):
            if color_range is None:
                self.print_str_opt("color_range", "unknown")
            else:
                self.print_str("color_range", color_range)

        def print_color_space(self, color_space):
            if color_space is None:
                self.print_str_opt("color_space", "unknown")
            else:
                self.print_str("color_space", color_space)

        def print_primaries(self, color_primaries):
            if color_primaries is None:
                self.print_str_opt("color_primaries", "unknown")
            else:
                self.print_str("color_primaries", color_primaries)

        def print_color_trc(self, color_trc):
            if color_trc is None:
                self.print_str_opt("color_transfer", "unknown")
            else:
                self.print_str("color_transfer", color_trc)

        def print_chroma_location(self, chroma_location):
            if chroma_location is None:
                self.print_str_opt("chroma_location", "unknown")
            else:
                self.print_str("chroma_location", chroma_location)

        def value_string(self, uv):
            show_float = 0

            if uv.unit == self.unit_second_str:
                vald = uv.val
                show_float = 1
            else:
                vald = vali = uv.val

            if uv.unit == self.unit_second_str and self.use_value_sexagesimal_format:
                secs  = vald
                mins  = int(secs / 60)
                secs  = int(secs - mins * 60)
                hours = int(mins / 60)
                mins %= 60
                buf = '%d:%02d:%09.6f' % (hours, mins, secs)
            else:
                prefix_string = ""

                if self.use_value_prefix and vald > 1:
                    if uv.unit == self.unit_byte_str and self.use_byte_value_binary_prefix:
                        index = int(math.log2(vald)) // 10
                        index = self.av_clip(index, 0, len(self.si_prefixes) - 1)
                        vald /= self.si_prefixes[index].bin_val
                        prefix_string = self.si_prefixes[index].bin_str
                    else:
                        index = int(math.log10(vald)) // 3
                        index = self.av_clip(index, 0, len(self.si_prefixes) - 1)
                        vald /= self.si_prefixes[index].dec_val
                        prefix_string = self.si_prefixes[index].dec_str
                    vali = vald

                if show_float or (self.use_value_prefix and vald != int(vald)):
                    buf = '%f' % (vald,)
                else:
                    buf = '%d' % (vali,)
                buf += '%s%s%s' % (
                    ' ' if (prefix_string or self.show_value_unit) else '',
                    prefix_string,
                    uv.unit if self.show_value_unit else '')

            return buf

        def writer_print_time(self, key, ts, time_base, *, is_duration):
            if (not is_duration and ts is None) or (is_duration and ts == 0):
                self.writer_print_string(key, "N/A", optional=True)
            else:
                d = ts * float(time_base)
                uv = unit_value(d, self.unit_second_str)
                buf = self.value_string(uv)
                self.writer_print_string(key, buf)

        def writer_print_ts(self, key, ts, is_duration):
            if (not is_duration and ts is None) or (is_duration and ts == 0):
                self.writer_print_string(key, 'N/A', optional=True)
            else:
                self.writer_print_integer(key, ts)

        def writer_print_string(self, key, val, *, optional=False, validate=False):
            ret = 0

            if optional and not self.display_optional_fields:
                return 0

            if self.show_all_entries or key in entries_to_show:
                if validate:
                    ret, key1 = validate_string(key)
                    assert ret >= 0, f'Invalid key=value string combination {key}={val!r} in section {self.section_unique_name}'
                    ret, val1 = validate_string(val)
                    assert ret >= 0, f'Invalid key=value string combination {key}={val!r} in section {self.section_unique_name}'
                    self._print_string(key1, val1)
                else:
                    self._print_string(key, val)
                # wctx->nb_item[wctx->level]++

            return ret

        def writer_print_integer(self, key, val):
            if self.show_all_entries or key in self.entries_to_show:
                self._print_integer(key, val)
                # wctx->nb_item[wctx->level]++

        def writer_print_rational(self, key, q, sep):
            buf = "%d%s%d" % (q.numerator, sep, q.denominator)
            self.writer_print_string(key, buf)

        def _default_print_str(self, key, value):
            file = self.get_file()
            if not self.nokey:
                print('%s%s=' % (self.section_str, key), end='', file=file)
            print(value, file=file)

        _print_string = _default_print_str

        def _default_print_int(self, key, value):
            file = self.get_file()
            if not self.nokey:
                print('%s%s=' % (self.section_str, key), end='', file=file)
            print("%d" % (value,), file=file)

        _print_integer = _default_print_int

        @staticmethod
        def av_clip(a, amin, amax):
            """
            Clip a signed integer value into the amin-amax range.
            @param a value to clip
            @param amin minimum value of the clip range
            @param amax maximum value of the clip range
            @return clipped value
            """
            assert amin <= amax, f'Invalid amin({amin}) > amax({amax})'
            if a < amin:
                return amin
            elif a > amax:
                return amax
            else:
                return a

        class SIPrefix(collections.namedtuple(
                'SIPrefix',
                (
                    'bin_val',
                    'dec_val',
                    'bin_str',
                    'dec_str',
                ),
        )):
            pass

        si_prefixes = [
            SIPrefix(1.0, 1.0, "", ""),
            SIPrefix(1.024e3, 1e3, "Ki", "K"),
            SIPrefix(1.048576e6, 1e6, "Mi", "M"),
            SIPrefix(1.073741824e9, 1e9, "Gi", "G"),
            SIPrefix(1.099511627776e12, 1e12, "Ti", "T"),
            SIPrefix(1.125899906842624e15, 1e15, "Pi", "P"),
        ]

        @classmethod
        def get_si_prefix_index(cls, v):
            index = cls.av_clip(v, 0, ord('z') - ord('E') + 1 - 1)
            print(f'get_si_prefix_index({v}) -> {index}')
            return index

ffprobe = Ffprobe()

MetadataFile._build_extension_to_class_map()
ConcatScriptFile._build_extension_to_class_map()
