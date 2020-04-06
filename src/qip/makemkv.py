
__all__ = [
        'makemkvcon',
        ]

from pathlib import Path
import collections
import configobj
import contextlib
import enum
import functools
import logging
import os
import pexpect
import progress
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
log = logging.getLogger(__name__)

from qip.app import app  # Also setup log.verbose
from .perf import perfcontext
from .exec import *
from .exec import _SpawnMixin, spawn as _exec_spawn, fdspawn as _exec_fdspawn
from qip.utils import byte_decode, compile_pattern_list, KwVarsObject
from qip.collections import OrderedSet
from qip.isolang import isolang
from qip.ffmpeg import ffmpeg

def dbg_makemkvcon_spawn_cmd(cmd, hidden_args=[],
                             fd=None,
                             dry_run=None, no_status=False, logfile=None,
                             cwd=None,
                             encoding=None, errors=None,
                             ignore_failed_to_open_disc=False,
                             ):
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.verbose('CMD: %s', subprocess.list2cmdline(cmd))
    if logfile is True:
        logfile = sys.stdout.buffer
    elif logfile is False:
        logfile = None
    spawn_func = functools.partial(makemkvcon.fdspawn, fd=fd) if fd is not None else makemkvcon.spawn
    p = spawn_func(command=cmd[0], args=cmd[1:] + hidden_args, logfile=logfile,
                   cwd=cwd,
                   encoding=encoding, errors=errors,
                   ignore_failed_to_open_disc=ignore_failed_to_open_disc)
    with p:
        out = ''
        for v in p.communicate():
            out += byte_decode(p.before)
            if p.match and p.match is not pexpect.EOF:
                out += byte_decode(p.match.group(0))
            if callable(v):
                if not v(p.match.group(0)):
                    break
            if p.after is pexpect.exceptions.EOF:
                break
    if p.signalstatus is not None:
        raise Exception('Command exited due to signal %r' % (p.signalstatus,))
    if not no_status and p.exitstatus:
        raise SpawnedProcessError(
            returncode=p.exitstatus,
            cmd=subprocess.list2cmdline(cmd),
            output=out,
            spawn=p)

    if ignore_failed_to_open_disc \
            and p.num_errors == 1 \
            and list(p.errors_seen) == ['Failed to open disc'] \
            and 'Reading Disc information' not in p.operations_performed:
        pass  # Ok
    else:
        assert p.num_errors == 0, 'makemkvcon errors found'
    if 'info' in cmd:
        pass  # Ok
    else:
        assert p.backup_done or p.num_tiltes_saved not in (0, None), 'No tiles saved!'
        assert p.num_tiltes_failed in (0, None), 'Some tiles failed!'

        s = 'No errors.'
        if p.backup_done:
            s += ' Backup done.'
        if p.num_tiltes_saved is not None:
            s += f' {p.num_tiltes_saved} titles saved'
        app.log.info(s)

    return {
        'spawn': p,
        'out': out,
    }

def do_makemkvcon_spawn_cmd(cmd, dry_run=None, **kwargs):
    if dry_run is None:
         dry_run = getattr(app.args, 'dry_run', False)
    if dry_run:
        app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(cmd))
        return ''
    else:
        return dbg_makemkvcon_spawn_cmd(cmd, **kwargs)

re_dot = r'[^\r\n]'  # To be used instead of r'.'
re_eol = r'\r?\n'
re_title_no = r'(?:[0-9/]+|\d+\.m2ts|\d+\.mpls(?:\(\d+\))?)'  # "1", "1/0/1", "00040.m2ts" "00081.mpls" "00081.mpls(1)"
re_stream_no = r'(?:\d+(?:,\d+)*)'  # "1", "1,2"

class DriveInfo(collections.namedtuple(
        'DriveInfo',
        (
            'index',
            'flag1',
            'flag2',
            'flag3',
            'drive_name',
            'disc_name',
            'device_name',
        ),
)):
    __slots__ = ()

class TitleInfo(KwVarsObject):

    class AttributeCode(enum.IntEnum):
        title = 2
        attribute8 = 8
        duration = 9
        size = 10
        attribute11 = 11
        in_file_name = 16
        attribute25 = 25
        stream_nos = 26
        out_file_name = 27
        language = 28
        language_desc = 29
        info_str = 30
        dummy_title_header_str = 31
        attribute33 = 33

    class Attribute(KwVarsObject):

        def __init__(self, code, flag, value):
            code = TitleInfo.AttributeCode(code)
            flag = int(flag)
            if code is TitleInfo.AttributeCode.duration:
                value = ffmpeg.Timestamp(value)
            elif code is TitleInfo.AttributeCode.stream_nos:
                value = tuple(int(e)
                              for e in value.split(','))
            elif code is TitleInfo.AttributeCode.language:
                value = isolang(value)
            self.code = code
            self.flag = flag
            self.value = value

    def __init__(self, id):
        self.id = id
        self.attributes = dict()

    @property
    def title(self):
        return self.attributes[TitleInfo.AttributeCode.title].value

    @property
    def duration(self):
        return self.attributes[TitleInfo.AttributeCode.duration].value

    @property
    def size(self):
        return self.attributes[TitleInfo.AttributeCode.size].value

    @property
    def stream_nos(self):
        return self.attributes[TitleInfo.AttributeCode.stream_nos].value

    @property
    def stream_nos_str(self):
        return ','.join(str(e) for e in self.stream_nos)

    @property
    def language(self):
        return self.attributes[TitleInfo.AttributeCode.language].value

    @property
    def info_str(self):
        return self.attributes[TitleInfo.AttributeCode.info_str].value

    def __str__(self):
        return self.info_str

class StreamInfo(collections.namedtuple(
        'StreamInfo',
        (
            'id',
            'flag1',
            'flag2',
            'flag3',
            'value',
        ),
)):
    __slots__ = ()

class MakemkvconSpawnBase(_SpawnMixin):

    num_tiltes_saved = None
    num_tiltes_failed = None
    num_errors = 0
    progress_bar = None
    on_progress_bar_line = False
    makemkv_operation = None
    makemkv_action = None
    operations_performed = None
    errors_seen = None
    drives = None
    titles = None
    angles = None
    backup_done = None

    def __init__(self, *args, timeout=60 * 60, ignore_failed_to_open_disc=False, **kwargs):
        self.operations_performed = OrderedSet()
        self.errors_seen = OrderedSet()
        self.ignore_failed_to_open_disc = ignore_failed_to_open_disc
        self.drives = collections.OrderedDict()
        self.titles = collections.OrderedDict()
        self.angles = []
        self.streams = collections.OrderedDict()
        super().__init__(*args, timeout=timeout, **kwargs)

    def current_progress(self, str):
        current_percent = int(byte_decode(self.match.group('cur')))
        total_percent = int(byte_decode(self.match.group('tot')))
        self.set_current_progress(current_percent=current_percent, total_percent=total_percent)

    def set_current_progress(self, current_percent, total_percent):
        #print('') ; app.log.debug(byte_decode(str))
        if self.progress_bar is not None:
            current_percent = int(current_percent)
            total_percent = int(total_percent)
            old_makemkv_current_percent = self.progress_bar.current_percent
            old_makemkv_total_percent = self.progress_bar.total_percent
            self.progress_bar.current_percent = current_percent
            self.progress_bar.total_percent = total_percent
            if current_percent == old_makemkv_current_percent and total_percent < old_makemkv_total_percent:
                pass
            elif current_percent < old_makemkv_current_percent and total_percent == old_makemkv_total_percent:
                pass
            else:
                self.progress_bar.goto(self.progress_bar.current_percent)
                self.on_progress_bar_line = True
        return True

    def current_task(self, str):
        #print('') ; app.log.debug(byte_decode(str))
        task = byte_decode(self.match.group('task'))
        task_type = byte_decode(self.match.group('task_type'))
        self.set_current_task(task_type=task_type, task=task)

    def set_current_task(self, task_type, task):
        need_update = False
        if task_type == 'operation':
            self.operations_performed.add(task)
            if 0 < self.progress_bar.current_percent < 100:
                self.progress_bar.current_percent = 100
                need_update = True
            if 0 < self.progress_bar.total_percent < 100:
                self.progress_bar.total_percent = 100
                need_update = True
            if need_update:
                self.progress_bar.goto(self.progress_bar.current_percent)
                self.on_progress_bar_line = True
                need_update = False
            if self.makemkv_operation is not None:
                print('')
            self.makemkv_operation = task
            self.makemkv_action = None
        else:  # task_type == 'action'
            if 0 < self.progress_bar.current_percent < 100:
                self.progress_bar.current_percent = 100
                need_update = True
            if need_update:
                self.progress_bar.goto(self.progress_bar.current_percent)
                self.on_progress_bar_line = True
                need_update = False
            if self.makemkv_action is not None:
                print('')
            self.makemkv_action = task
        if self.progress_bar is None:
            log.info('makemkvcon: %s / %s...', self.makemkv_operation, self.makemkv_action)
        else:
            self.progress_bar.makemkv_operation = self.makemkv_operation
            self.progress_bar.makemkv_action = self.makemkv_action
            if task_type == 'operation':
                self.progress_bar.total_percent = 0
                self.progress_bar.current_percent = 0
            if task_type == 'action':
                self.progress_bar.current_percent = 0
                self.progress_bar.reset()
            self.progress_bar.goto(self.progress_bar.current_percent)
            self.on_progress_bar_line = True
        return True

    def saving_titles_count(self, str):
        if self.on_progress_bar_line:
            print('')
            self.on_progress_bar_line = False
        str = byte_decode(str).rstrip('\r\n')
        log.info(str)
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

    def generic_info(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.on_progress_bar_line:
            print('')
            self.on_progress_bar_line = False
        log.info(str)
        return True

    def generic_warning(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.on_progress_bar_line:
            print('')
            self.on_progress_bar_line = False
        log.warning(str)
        return True

    def new_version_warning(self, str):
        return self.generic_warning(str)

    def backup_done_line(self, str):
        self.backup_done = True
        return self.generic_info(str)

    def failed_to_open_disc_error(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if not self.ignore_failed_to_open_disc:
            if self.on_progress_bar_line:
                print('')
                self.on_progress_bar_line = False
            log.error(str)
        self.num_errors += 1
        self.errors_seen.add(str)
        return True

    def parse_titles_saved(self, str):
        if self.on_progress_bar_line:
            print('')
            self.on_progress_bar_line = False
        app.log.info(byte_decode(str))
        v = int(self.match.group('num_tiltes_saved'))
        assert self.num_tiltes_saved in (v, None)
        self.num_tiltes_saved = v
        try:
            v = int(self.match.group('num_tiltes_failed'))
        except IndexError:
            pass
        else:
            assert self.num_tiltes_failed in (v, None)
            self.num_tiltes_failed = v
            if self.num_tiltes_failed:
                return self.generic_error(str)
        return True

    def parse_angle_added(self, str):
        title_no = int(self.match.group('title_no'))
        angle_no = int(self.match.group('angle_no'))
        self.angles.append((title_no, angle_no))
        return self.generic_info(str)

    def unknown_line(self, str):
        #str = byte_decode(str).rstrip('\r\n')
        if str:
            self.generic_error('UNKNOWN: ' + repr(str))
        return True

    def is_robot_mode(self):
        return '--robot' in (self.args or ()) or '-r' in (self.args or ())

    def communicate(self, *args, **kwargs):
        if self.progress_bar is None:
            try:
                from qip.utils import ProgressBar
            except ImportError:
                pass
            else:
                self.progress_bar = ProgressBar('makemkvcon', max=100)
                self.progress_bar.makemkv_operation = None
                self.progress_bar.makemkv_action = None
                self.progress_bar.total_percent = 0
                self.progress_bar.current_percent = 0
                self.progress_bar.suffix = '%(current_percent)d%% of %(makemkv_action)s [remaining %(eta_td)s / %(end_td)s], %(total_percent)d%% of %(makemkv_operation)s'
                self.progress_bar.goto(self.progress_bar.current_percent)
                self.on_progress_bar_line = True
        if self.is_robot_mode():
            pattern_dict = self.get_robot_pattern_dict()
            self._messages_pattern_dict_cache = self.get_messages_pattern_dict()
            self._messages_pattern_kv_list = list(self._messages_pattern_dict_cache.items())
            _messages_pattern_list = [k for k, v in self._messages_pattern_kv_list]
            self._messages_compiled_pattern_list = compile_pattern_list(_messages_pattern_list)
        else:
            pattern_dict = self.get_pattern_dict()
        return super().communicate(pattern_dict, *args, **kwargs)

    def get_progress_pattern_dict(self):
        pattern_dict = collections.OrderedDict([
            (fr'^Current progress - *(?P<cur>\d+)% *, Total progress - *(?P<tot>\d+)% *{re_eol}', self.current_progress),
            (fr'^Current (?P<task_type>action|operation): (?P<task>[^\r\n]+){re_eol}', self.current_task),
        ])
        return pattern_dict

    def get_messages_pattern_dict(self):
        pattern_dict = collections.OrderedDict([
            (fr'^MakeMKV v[^\r\n]+ started{re_eol}', True),
            (fr'^Operation successfully completed{re_eol}', True),
            (fr'^Saving (?P<title_count>\d+) titles into directory (?P<dest_dir>[^\r\n]+){re_eol}', self.saving_titles_count),
            (fr'^Title #(?P<title_no>{re_title_no}) has length of (?P<length>\d+) seconds which is less than minimum title length of (?P<min_length>\d+) seconds and was therefore skipped{re_eol}', True),
            (fr'^Title (?P<title_no1>{re_title_no})(?: in VTS (?P<vts_no>\d+))? is equal to title (?P<title_no2>{re_title_no}) and was skipped{re_eol}', True),
            (fr'^(?P<stream_type>Audio|Subtitle) stream #(?P<stream_no>{re_stream_no}) is identical to stream #(?P<stream_no2>{re_stream_no}) and was skipped{re_eol}', True),
            (fr'^(?P<stream_type>Audio|Subtitle) stream #(?P<stream_no>{re_stream_no}) looks empty and was skipped{re_eol}', True),
            (fr'^Using direct disc access mode{re_eol}', True),
            (fr'^Downloading latest SDF to (?P<dest_dir>[^\r\n]+) \.\.\.{re_eol}', True),
            (fr'^Using LibreDrive mode \(v(?P<version>\d+) id=(?P<id>[0-9a-fA-F]+)\){re_eol}', self.generic_info),
            (fr'^LibreDrive firmware support is not yet available for this drive \(id=(?P<drive_id>[A-Fa-f0-9]+)\){re_eol}', self.generic_info),
            (fr'^LibreDrive mode for this drive is only possible with firmware upgrade \(id=(?P<drive_id>[A-Fa-f0-9]+)\){re_eol}', self.generic_warning),
            (fr'^Loaded content hash table, will verify integrity of M2TS files\.{re_eol}', True),
            (fr'^Loop detected\. Possibly due to unknown structure protection\.{re_eol}', self.generic_warning),
            (fr'^Title #(?P<title_no>{re_title_no}) in broken titleset was skipped{re_eol}', True),
            (fr'^Cells (?P<cell_no1>\d+)-(?P<cell_no2>\d+|end) were skipped due to cell commands \(structure protection\?\){re_eol}', True),
            (fr'^Cells (?P<cell_no1>\d+)-(?P<cell_no2>\d+|end) were removed from (?P<from>title start|title end){re_eol}', True),
            (fr'^Title #(?P<title_no>{re_title_no}) \((?P<time>[0-9:]+)\) was skipped due to navigation error{re_eol}', True),
            (fr'^Jumped to cell (?P<cell_no1>\d+) from cell (?P<cell_no2>\d+) due to cell commands \(structure protection\?\){re_eol}', True),
            (fr'^CellWalk algorithm failed \(structure protection is too tough\?\), trying CellTrim algorithm{re_eol}', self.generic_warning),
            (fr'^CellTrim algorithm failed since title has only (?P<num_chapters>\d+) chapters{re_eol}', self.generic_warning),
            (fr'^Complex multiplex encountered - (?P<num_cells>\d+) cells and (?P<num_vobus>\d+) VOBUs have to be scanned\. This may take some time, please be patient - it can\'t be avoided\.{re_eol}', self.generic_warning),
            # IFO file for VTS #20 is corrupt, VOB file must be scanned. This may take very long time, please be patient.
            (fr'^Region setting of drive (?P<drive_label>[^\r\n]+) does not match the region of currently inserted disc, trying to work around\.\.\.{re_eol}', True),
            (fr'^Title #(?P<title_no>{re_title_no}) was added \((?P<num_cells>\d+) cell\(s\), (?P<time>[0-9:]+)\){re_eol}', True),
            (fr'^File (?P<file_name>\S+) was added as title #(?P<title_no>\d+){re_eol}', True),
            (fr'^Unable to open file \'(?P<file_in>[^\']+)\' in OS mode due to a bug in OS Kernel\. This can be worked around, but read speed may be very slow\.{re_eol}', True),
            (fr'^Encountered (?P<num_errors>\d+) errors of type \'Read Error\' - see http://www\.makemkv\.com/errors/dvdread/{re_eol}', self.generic_error),
            (fr'^Error \'Posix error - Input/output error\' occurred while reading \'(?P<device_path>[^\r\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', self.generic_error),
            (fr'^Error \'Scsi error - MEDIUM ERROR:L-EC UNCORRECTABLE ERROR\' occurred while reading \'(?P<input_name>[^\r\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', self.generic_error),
            (fr'^Error \'Scsi error - MEDIUM ERROR:NO SEEK COMPLETE\' occurred while reading \'(?P<input_name>[^\r\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', self.generic_error),
            (fr'^Error \'Scsi error - ILLEGAL REQUEST:MEDIA REGION CODE IS MISMATCHED TO LOGICAL UNIT REGION\' occurred while reading \'(?P<input_name>[^\r\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', self.generic_error),
            (fr'^Error \'Scsi error - ILLEGAL REQUEST:INVALID COMMAND OPERATION CODE\' occurred while issuing SCSI command 46020\.\.00140 to device \'(?P<device_path>[^\r\n]+?)\'{re_eol}', self.generic_warning),
            (fr'^Error \'Scsi error - ILLEGAL REQUEST:READ OF SCRAMBLED SECTOR WITHOUT AUTHENTICATION\' occurred while reading \'(?P<input_name>[^\r\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', True),
            (fr'^Error \'Scsi error - ILLEGAL REQUEST:ILLEGAL MODE FOR THIS TRACK\' occurred while reading \'(?P<input_name>[^\r\n]+?)\' at offset \'(?P<offset>\d+)\'', True),
            (fr'^LIBMKV_TRACE: Exception: (?P<exception>[^\r\n]+){re_eol}', self.generic_error),
            (fr'^Device \'(?P<device_path>[^\r\n]+?)\' is partially inaccessible due to a bug in Linux kernel \(it reports invalid block device size\)\. This can be worked around, but read speed may be very slow\.{re_eol}', True),
            (fr'^Failed to save title (?P<title_no>{re_title_no}) to file (?P<file_out>[^\r\n]+){re_eol}', self.generic_error),
            (fr'^Failed to open disc{re_eol}', self.failed_to_open_disc_error),
            (fr'^(?P<num_tiltes_saved>\d+) titles saved{re_eol}', self.parse_titles_saved),
            (fr'^(?P<num_tiltes_saved>\d+) titles saved, (?P<num_tiltes_failed>\d+) failed{re_eol}', self.parse_titles_saved),
            (fr'^Copy complete\. (?P<num_tiltes_saved>\d+) titles saved\.{re_eol}', self.parse_titles_saved),
            (fr'^Copy complete\. (?P<num_tiltes_saved>\d+) titles saved, (?P<num_tiltes_failed>\d+) failed\.{re_eol}', self.parse_titles_saved),
            (fr'^Track #(?P<track_no>\d+) turned out to be empty and was removed from output file{re_eol}', self.generic_warning),
            (fr'^Forced subtitles track #(?P<track_no>\d+) turned out to be empty and was removed from output file{re_eol}', self.generic_warning),
            (fr'^Title #(?P<title_no>\d+) declared length is (?P<declared_length>\S+) while its real length is (?P<real_length>\S+) - assuming fake title{re_eol}', self.generic_warning),
            (fr'^Fake cells occupy (?P<percent>\d+)% of the title - assuming fake title{re_eol}', self.generic_warning),
            (fr'^Can\'t locate a cell for VTS (?P<vts>\d+) TTN (?P<ttn>\d+) PGCN (?P<pgcn>\d+) PGN (?P<pgn>\d+){re_eol}', self.generic_warning),
            (fr'^AV synchronization issues were found in file \'(?P<file_name>[^\r\n]+)\' \(title #(?P<title_no>{re_title_no})\){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: audio gap - (?P<missing_frames>\S+) missing frame\(s\){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: (?P<action>encountered overlapping frame|short audio gap was removed), audio skew is (?P<audio_skew>\S+){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: (?P<dropped_frames>\d+) frame\(s\) dropped to reduce audio skew to (?P<audio_skew>\S+){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: (?P<overlapping_frames>\d+) overlapping frame\(s\) dropped at segment boundary{re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) *: (?P<num_frames>\d+) frame\(?s?\)? dropped to reduce audio skew to (?P<audio_skew>\S+){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) *: video stream has (?P<num_frames>\d+) frame\(?s?\)? with invalid timecodes{re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) *: video frame timecode differs by (?P<video_timecode_skew>\S+){re_eol}', self.generic_warning),
            (fr'^Too many AV synchronization issues in file \'(?P<file_out>[^\r\n]+)\' \(title #(?P<title_no>{re_title_no})\) ?, future messages will be printed only to log file{re_eol}', self.generic_warning),
            (fr'^Angle #(?P<angle_no>\d+) was added for title #(?P<title_no>{re_title_no}){re_eol}', self.parse_angle_added),
            (fr'^Calculated BUP offset for VTS #(?P<vts_no>\d+) does not match one in IFO header\.{re_eol}', self.generic_warning),
            (fr'^Using Java runtime from (?P<path>{re_dot}+){re_eol}', self.generic_warning),
            (fr'^Loaded (?P<num_svq_files>\d+) SVQ file\(s\){re_eol}', self.generic_warning),
            (fr'^Processing BD\+ code, please be patient - this may take up to few minutes{re_eol}', self.generic_warning),
            (fr'^Processing BD\+ code using generic SVQ from (?P<svq_source_file>\S+){re_eol}', self.generic_warning),
            (fr'^Processing BD\+ code using disc-specific SVQ from (?P<svq_source_file>\S+){re_eol}', self.generic_warning),
            (fr'^BD\+ code processed, got (?P<num_futs>\d+) FUT\(s\) for (?P<num_clips>\d+) clip\(s\){re_eol}', self.generic_warning),
            (fr'^BD\+ code processed, got (?P<num_futs>\d+) FUT\(s\) for (?P<num_clips>\d+) clip\(s\){re_eol}', self.generic_warning),
            (fr'^Program reads data faster than it can write to disk, consider upgrading your hard drive if you see many of these messages\.{re_eol}', self.generic_warning),
            (fr'^(?P<exec>{re_dot}+): (?P<lib>{re_dot}+): no version information available \(required by (?P<req_by>{re_dot}+)\){re_eol}', self.generic_warning),
            (fr'^It appears that you are opening the disc processed by DvdFab/MacTheRipper which is known to produce damaged VOB files\. Errors may follow - please use original disc instead\.{re_eol}', self.generic_warning),
            (fr'^The new version (?P<version>\S+) is available for download at (?P<url>\S+){re_eol}', self.new_version_warning),
            (fr'^Opening files on harddrive at (?P<dir_in>[^\r\n]+){re_eol}', True),
            (fr'^Backing up disc into folder \\"(?P<file_out>[^\r\n]+)\\"{re_eol}', True),
            (fr'^Backup done\.?{re_eol}', self.backup_done_line),
            (fr'^Backup failed\.?{re_eol}', self.generic_error),
            (fr'[^\r\n]*?{re_eol}', self.unknown_line),
        ])
        # TODO
        # 2019-05-29 02:12:36 ERROR UNKNOWN: 'Saved SD dump file as /home/qip/.MakeMKV/dump_SD_55BD8BB1EB43C4A0F126.tgz'
        # 2019-05-29 02:12:38 ERROR UNKNOWN: 'This functionality is shareware. You may evaluate it for 30 days after what you would need to purchase an activation key if you like the functionality. Do you want to start evaluation period now?'
        # 2019-05-29 02:12:38 ERROR UNKNOWN: 'Evaluation version, 30 day(s) out of 30 remaining'
        return pattern_dict

    def get_robot_pattern_dict(self):
        pattern_dict = collections.OrderedDict([
                (fr'^PRGV:(?P<current>\d+),(?P<total>\d+),(?P<max>\d+){re_eol}', self.robot_progress_values),
                (fr'^PRGC:(?P<code>\d+),(?P<id>\d+),"(?P<name>{re_dot}*)"{re_eol}', self.robot_progress_current_title),
                (fr'^PRGT:(?P<code>\d+),(?P<id>\d+),"(?P<name>{re_dot}*)"{re_eol}', self.robot_progress_total_title),
                (fr'^MSG:(?P<code>\d+),(?P<flags>\d+),(?P<count>\d+),"(?P<message>{re_dot}*?)","(?P<format>{re_dot}*?)"(?P<params>,"{re_dot}*")*{re_eol}', self.robot_message),
                # DRV:1,2,999,12,"BD-ROM ASUS SBC-06D2X-U D201","MOCKINJAY_PT1","/dev/sr2"
                (fr'^DRV:(?P<index>\d+),(?P<flag1>\d+),(?P<flag2>\d+),(?P<flag3>\d+),"(?P<drive_name>{re_dot}*)","(?P<disc_name>{re_dot}*)","(?P<device_name>{re_dot}*)"{re_eol}', self.robot_drive_scan),
                (fr'^TCOUNT:(?P<count>\d+){re_eol}', self.robot_titles_count),
                (fr'^CINFO:(?P<id>\d+),(?P<code>\d+),"(?P<value>{re_dot}*)"{re_eol}', self.robot_disc_info),
                (fr'^TINFO:(?P<id>\d+),(?P<code>\d+),(?P<flag>\d+),"(?P<value>{re_dot}*)"{re_eol}', self.robot_title_info),
                (fr'^SINFO:(?P<id>\d+),(?P<flag1>\d+),(?P<flag2>\d+),(?P<flag3>\d+),"(?P<value>{re_dot}*)"{re_eol}', self.robot_stream_info),
                (fr'[^\n]*?{re_eol}', self.unknown_line),
                (pexpect.EOF, False),
        ])
        return pattern_dict

    def get_pattern_dict(self):
        pattern_dict = self.get_progress_pattern_dict()
        pattern_dict.update(self.get_messages_pattern_dict())
        pattern_dict.update(collections.OrderedDict([
            (pexpect.EOF, False),
        ]))
        return pattern_dict

    def close(self, *args, **kwargs):
        if self.progress_bar is not None:
            self.progress_bar.finish()
            self.progress_bar = None
            self.on_progress_bar_line = False
        return super().close(*args, **kwargs)

    def robot_progress_values(self, str):
        # Progress bar values for current and total progress
        # PRGV:current,total,max
        # current - current progress value
        # total - total progress value
        # max - maximum possible value for a progress bar, constant
        cur_pos = int(self.match.group('current'))
        tot_pos = int(self.match.group('total'))
        max = int(self.match.group('max'))
        self.set_current_progress(cur_pos / max * 100, tot_pos / max * 100)
        return True

    def robot_progress_current_title(self, str):
        # Current and total progress title
        # PRGC:code,id,name
        # PRGT:code,id,name
        # code - unique message code
        # id - operation sub-id
        # name - name string
        name = byte_decode(self.match.group('name'))
        self.set_current_task('operation', name)
        return True

    def robot_progress_total_title(self, str):
        # Current and total progress title
        # PRGC:code,id,name
        # PRGT:code,id,name
        # code - unique message code
        # id - operation sub-id
        # name - name string
        name = byte_decode(self.match.group('name'))
        self.set_current_task('action', name)
        return True

    def robot_message(self, str):
        # MSG:code,flags,count,message,format,param0,param1,...
        # code - unique message code, should be used to identify particular string in language-neutral way.
        # flags - message flags, see AP_UIMSG_xxx flags in apdefs.h
        # count - number of parameters
        # message - raw message string suitable for output
        # format - format string used for message. This string is localized and subject to change, unlike message code.
        # paramX - parameter for message
        message = byte_decode(self.match.group('message')) + '\n'
        pattern_dict = self._messages_pattern_dict_cache
        compiled_patter_list = self._messages_compiled_pattern_list
        old_match = self.match
        try:
            for idx, pattern in enumerate(compiled_patter_list):
                m = pattern.search(message)
                if m:
                    self.match = m
                    break
            else:
                return self.unknown_line(message)
            pattern_kv_list = self._messages_pattern_kv_list
            k, v = pattern_kv_list[idx]
            if callable(v):
                if not v(message):
                    return False
        finally:
            self.match = old_match
        return True

    def robot_drive_scan(self, str):
        # Drive scan messages
        # XXXJST OLD:
        #   DRV:index,visible,enabled,flags,drive name,disc name
        #   index - drive index
        #   visible - set to 1 if drive is present
        #   enabled - set to 1 if drive is accessible
        #   flags - media flags, see AP_DskFsFlagXXX in apdefs.h
        #   drive name - drive name string
        #   disc name - disc name string

        #   DRV:index,flag1,flag2,flag3,drive_name,disc_name,device_name
        device_name = self.match.group('device_name')
        if device_name:
            drive = DriveInfo(
                index=int(byte_decode(self.match.group('index'))),
                flag1=int(byte_decode(self.match.group('flag1'))),
                flag2=int(byte_decode(self.match.group('flag2'))),
                flag3=int(byte_decode(self.match.group('flag3'))),
                drive_name=byte_decode(self.match.group('drive_name')),
                disc_name=byte_decode(self.match.group('disc_name')),
                device_name=Path(byte_decode(device_name)),
            )
            self.drives[drive.index] = drive
        return True

    def robot_titles_count(self, str):
        # Disc information output messages
        # TCOUT:count
        # count - titles count
        print(f'\nrobot_titles_count: {str!r}')
        return True

    def robot_disc_info(self, str):
        # Disc, title and stream information
        # CINFO:id,code,value
        # TINFO:id,code,value
        # SINFO:id,code,value
        # id - attribute id, see AP_ItemAttributeId in apdefs.h
        # code - message code if attribute value is a constant string
        # value - attribute value
        # TODO
        # print(f'\nrobot_disc_info: {str!r}')
        # robot_disc_info: b'CINFO:1,6209,"Blu-ray disc"\r\n'
        # robot_disc_info: b'CINFO:2,0,"The Expendables"\r\n'
        # robot_disc_info: b'CINFO:28,0,"eng"\r\n'
        # robot_disc_info: b'CINFO:29,0,"English"\r\n'
        # robot_disc_info: b'CINFO:30,0,"The Expendables"\r\n'
        # robot_disc_info: b'CINFO:31,6119,"<b>Source information</b><br>"\r\n'
        # robot_disc_info: b'CINFO:33,0,"0"\r\n'
        return True

    def robot_title_info(self, str):
        # Disc, title and stream information
        # CINFO:id,code,value
        # TINFO:id,code,value
        # SINFO:id,code,value
        # id - attribute id, see AP_ItemAttributeId in apdefs.h
        # code - message code if attribute value is a constant string
        # value - attribute value
        id = int(byte_decode(self.match.group('id')))
        try:
            title = self.titles[id]
        except KeyError:
            title = self.titles[id] = TitleInfo(id=id)
        code=int(byte_decode(self.match.group('code')))
        code = TitleInfo.AttributeCode(code)
        title.attributes[code] = TitleInfo.Attribute(
            code=code,
            flag=int(byte_decode(self.match.group('flag'))),
            value=byte_decode(self.match.group('value')))
        return True

    def robot_stream_info(self, str):
        # Disc, title and stream information
        # CINFO:id,code,value
        # TINFO:id,code,value
        # SINFO:id,code,value
        # id - attribute id, see AP_ItemAttributeId in apdefs.h
        # code - message code if attribute value is a constant string
        # value - attribute value
        if False:
            # TODO
            stream = StreamInfo(
                id=int(byte_decode(self.match.group('id'))),
                flag1=int(byte_decode(self.match.group('flag1'))),
                flag2=int(byte_decode(self.match.group('flag2'))),
                flag3=int(byte_decode(self.match.group('flag3'))),
                value=byte_decode(self.match.group('value')),
            )
            self.streams[stream.id] = stream
        return True

class MakemkvconSpawn(MakemkvconSpawnBase, _exec_spawn):

    pass

class MakemkvconFdspawn(MakemkvconSpawnBase, _exec_fdspawn):

    def __init__(self, fd, *_args, **kwargs):
        print(f'MakemkvconFdspawn.__init__(fd={fd!r}, _args={_args!r}, kwargs={kwargs!r}')
        super().__init__(fd=fd, *_args, **kwargs)

class Makemkvcon(Executable):
    # http://www.makemkv.com/developers/usage.txt

    name = 'makemkvcon'

    nice_adjustment = 19  # the nicest
    ionice_level = 7      # lowest priority

    run_func = staticmethod(do_makemkvcon_spawn_cmd)

    spawn = MakemkvconSpawn

    fdspawn = MakemkvconFdspawn

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    DriveInfo = DriveInfo

    TitleInfo = TitleInfo

    StreamInfo = StreamInfo

    @property
    def config_dir(self):
        config_home = Path.home()
        return config_home / '.MakeMKV'

    @property
    def share_dir(self):
        return Path('/usr/share/MakeMKV')

    @property
    def settings_file_name(self):
        return self.config_dir / 'settings.conf'

    @property
    def appdata_tar_file_name(self):
        return self.share_dir / 'appdata.tar'

    def read_settings_conf(self):
        settings_file_name = self.settings_file_name
        settings = configobj.ConfigObj(os.fspath(settings_file_name))
        return settings

    def write_settings_conf(self, settings):
        if settings.filename is None:
            settings.filename = os.fspath(self.settings_file_name)
        from qip.file import write_to_temp_context
        with write_to_temp_context(settings.filename, text=False) as tmp_file:
            return settings.write(tmp_file.fp)

    def build_cmd(self, *args, **kwargs):
        args = list(args)

        if 'messages' not in kwargs and '--messages' not in args:
            kwargs['messages'] = '-stdout'
        if 'progress' not in kwargs and '--progress' not in args:
            kwargs['progress'] = '-stdout'

        return super().build_cmd(*args, **kwargs)

    def mkv(self, *, source, dest_dir, title_id='all', **kwargs):
        return self('mkv', source, title_id, dest_dir, **kwargs)

    def backup(self, *, source, dest_dir, **kwargs):
        return self('backup', source, dest_dir, **kwargs)

    def info(self, *, source, ignore_failed_to_open_disc=False, run_func=None, **kwargs):
        if ignore_failed_to_open_disc:
            run_func = run_func or self.run_func
            run_func = functools.partial(run_func, ignore_failed_to_open_disc=ignore_failed_to_open_disc)
        return self('info', source, run_func=run_func, **kwargs)

    def _run(self, *args, retry_no_cd=False, **kwargs):
        if retry_no_cd is True:
            retry_no_cd = 8
        while True:
            try:
                return super()._run(*args, **kwargs)
            except SpawnedProcessError as e:
                if retry_no_cd and e.returncode == 11 \
                        and e.spawn.num_errors == 1 and list(e.spawn.errors_seen) == ['Failed to open disc'] \
                        and 'Reading Disc information' not in e.spawn.operations_performed:
                    time.sleep(2)
                    retry_no_cd -= 1
                    continue
                raise
            break

    def get_profile_xml(self, profile_file_name='default.mmcp.xml'):
        cmd = [
            'tar', '-x', '-O',
            '-f', self.appdata_tar_file_name,
            profile_file_name,
        ]
        profile_xml = dbg_exec_cmd(cmd, encoding='utf-8')
        profile_xml = ET.ElementTree(ET.fromstring(profile_xml))
        return profile_xml

makemkvcon = Makemkvcon()
