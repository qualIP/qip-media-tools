
__all__ = [
        'makemkvcon',
        ]

import collections
import contextlib
import logging
import pexpect
import progress
import subprocess
import sys
import time
log = logging.getLogger(__name__)

from qip.app import app  # Also setup log.verbose
from .perf import perfcontext
from .exec import *
from .exec import spawn as _exec_spawn
from qip.utils import byte_decode, compile_pattern_list
from qip.collections import OrderedSet

def dbg_makemkvcon_spawn_cmd(cmd, hidden_args=[], dry_run=None, no_status=False, yes=False, logfile=None, ignore_failed_to_open_disc=False):
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.verbose('CMD: %s', subprocess.list2cmdline(cmd))
    if logfile is True:
        logfile = sys.stdout.buffer
    elif logfile is False:
        logfile = None
    p = makemkvcon.spawn(cmd[0], args=cmd[1:] + hidden_args, logfile=logfile,
                         ignore_failed_to_open_disc=ignore_failed_to_open_disc)
    try:
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
        try:
            p.wait()
        except pexpect.ExceptionPexpect as err:
            if err.value != 'Cannot wait for dead child process.':
                raise
    finally:
        p.close()
    if p.signalstatus is not None:
        raise Exception('Command exited due to signal %r' % (p.signalstatus,))
    if not no_status and p.exitstatus:
        raise SpawnedProcessError(
            returncode=p.exitstatus,
            cmd=subprocess.list2cmdline(cmd),
            output=out,
            spawn=p)

    assert p.num_errors == 0, 'makemkvcon errors found'
    assert p.num_tiltes_saved not in (0, None), 'No tiles saved!'
    assert p.num_tiltes_failed in (0, None), 'Some tiles failed!'

    app.log.info('No errors. %d titles saved', p.num_tiltes_saved)

    return out

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

class MakemkvconSpawn(_exec_spawn):

    num_tiltes_saved = None
    num_tiltes_failed = None
    num_errors = 0
    progress_bar = None
    makemkv_operation = None
    makemkv_action = None
    operations_performed = None
    errors_seen = None
    drives = None

    def __init__(self, *args, timeout=60 * 60, ignore_failed_to_open_disc=False, **kwargs):
        self.operations_performed = OrderedSet()
        self.errors_seen = OrderedSet()
        self.ignore_failed_to_open_disc = ignore_failed_to_open_disc
        self.drives = []
        super().__init__(*args, timeout=timeout, **kwargs)

    def current_progress(self, str):
        current_percent = int(byte_decode(self.match.group('cur')))
        total_percent = int(byte_decode(self.match.group('tot')))
        self.set_current_progress(current_percent=current_percent, total_percent=total_percent)

    def set_current_progress(self, current_percent, total_percent):
        #print('') ; app.log.debug(byte_decode(str))
        if self.progress_bar is not None:
            old_makemkv_action_percent = self.progress_bar.current_percent
            old_makemkv_operation_percent = self.progress_bar.total_percent
            self.progress_bar.current_percent = current_percent
            self.progress_bar.total_percent = total_percent
            if current_percent == old_makemkv_action_percent and total_percent < old_makemkv_operation_percent:
                pass
            elif current_percent < old_makemkv_action_percent and total_percent == old_makemkv_operation_percent:
                pass
            else:
                self.progress_bar.goto(self.progress_bar.current_percent)
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
                need_update = False
            if self.makemkv_operation is not None:
                print('')
            self.makemkv_operation = task
            self.makemkv_action = None
        else:
            if 0 < self.progress_bar.current_percent < 100:
                self.progress_bar.current_percent = 100
                need_update = True
            if need_update:
                self.progress_bar.goto(self.progress_bar.current_percent)
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
            self.progress_bar.goto(self.progress_bar.current_percent)
        return True

    def saving_titles_count(self, str):
        if self.progress_bar is not None:
            print('')
        str = byte_decode(str).rstrip('\r\n')
        log.info(str)
        return True

    def generic_error(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.progress_bar is not None:
            print('')
        log.error(str)
        self.num_errors += 1
        self.errors_seen.add(str)
        return True

    def generic_info(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.progress_bar is not None:
            print('')
        log.info(str)
        return True

    def generic_warning(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.progress_bar is not None:
            print('')
        log.warning(str)
        return True

    def failed_to_open_disc_error(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if not self.ignore_failed_to_open_disc:
            if self.progress_bar is not None:
                print('')
            log.error(str)
        self.num_errors += 1
        self.errors_seen.add(str)
        return True

    def parse_titles_saved(self, str):
        if self.progress_bar is not None:
            print('')
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

    def unknown_line(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if str:
            self.generic_error('UNKNOWN: ' + repr(str))
        return True

    def is_robot_mode(self):
        return '--robot' in self.args or '-r' in self.args

    def communicate(self, *args, **kwargs):
        if self.progress_bar is None:
            HAVE_PROGRESS_BAR = False
            try:
                import progress.bar
                HAVE_PROGRESS_BAR = True
            except ImportError:
                pass
            if HAVE_PROGRESS_BAR:
                self.progress_bar = progress.bar.Bar('makemkvcon', max=100)
                self.progress_bar.makemkv_operation = None
                self.progress_bar.makemkv_action = None
                self.progress_bar.total_percent = 0
                self.progress_bar.current_percent = 0
                self.progress_bar.suffix = '%(current_percent)d%% of %(makemkv_action)s, %(total_percent)d%% of %(makemkv_operation)s'
                self.progress_bar.goto(self.progress_bar.current_percent)
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
            (fr'^MakeMKV v[^\n]+ started{re_eol}', True),
            (fr'^Operation successfully completed{re_eol}', True),
            (fr'^Saving (?P<title_count>\d+) titles into directory (?P<dest_dir>[^\r\n]+){re_eol}', self.saving_titles_count),
            (fr'^Title #(?P<title_no>{re_title_no}) has length of (?P<length>\d+) seconds which is less than minimum title length of (?P<min_length>\d+) seconds and was therefore skipped{re_eol}', True),
            (fr'^Title (?P<title_no1>{re_title_no})(?: in VTS (?P<vts_no>\d+))? is equal to title (?P<title_no2>{re_title_no}) and was skipped{re_eol}', True),
            (fr'^(?P<stream_type>Audio|Subtitle) stream #(?P<stream_no>{re_stream_no}) is identical to stream #(?P<stream_no2>{re_stream_no}) and was skipped{re_eol}', True),
            (fr'^(?P<stream_type>Audio|Subtitle) stream #(?P<stream_no>{re_stream_no}) looks empty and was skipped{re_eol}', True),
            (fr'^Using direct disc access mode{re_eol}', True),
            (fr'^Downloading latest SDF to (?P<dest_dir>[^\n]+) \.\.\.{re_eol}', True),
            (fr'^Using LibreDrive mode \(v(?P<version>\d+) id=(?P<id>[0-9a-fA-F]+)\){re_eol}', True),
            (fr'^Loaded content hash table, will verify integrity of M2TS files\.{re_eol}', True),
            (fr'^Loop detected\. Possibly due to unknown structure protection\.{re_eol}', self.generic_warning),
            (fr'^Cells (?P<cell_no1>\d+)-(?P<cell_no2>\d+|end) were skipped due to cell commands \(structure protection\?\){re_eol}', True),
            (fr'^Cells (?P<cell_no1>\d+)-(?P<cell_no2>\d+|end) were removed from (?P<from>title start|title end){re_eol}', True),
            (fr'^Jumped to cell (?P<cell_no1>\d+) from cell (?P<cell_no2>\d+) due to cell commands \(structure protection\?\){re_eol}', True),
            (fr'^CellWalk algorithm failed \(structure protection is too tough\?\), trying CellTrim algorithm{re_eol}', self.generic_warning),
            (fr'^Complex multiplex encountered - (?P<num_cells>\d+) cells and (?P<num_vobus>\d+) VOBUs have to be scanned\. This may take some time, please be patient - it can\'t be avoided\.{re_eol}', True),
            (fr'^Region setting of drive (?P<drive_label>[^\n]+) does not match the region of currently inserted disc, trying to work around\.\.\.{re_eol}', True),
            (fr'^Title #(?P<title_no>{re_title_no}) was added \((?P<num_cells>\d+) cell\(s\), (?P<time>[0-9:]+)\){re_eol}', True),
            (fr'^File (?P<file_name>\S+) was added as title #(?P<title_no>\d+){re_eol}', True),
            (fr'^Unable to open file \'(?P<file_in>[^\']+)\' in OS mode due to a bug in OS Kernel\. This can be worked around, but read speed may be very slow\.{re_eol}', True),
            (fr'^Encountered (?P<num_errors>\d+) errors of type \'Read Error\' - see http://www\.makemkv\.com/errors/dvdread/{re_eol}', self.generic_error),
            (fr'^Error \'Posix error - Input/output error\' occurred while reading \'(?P<device_path>[^\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', self.generic_error),
            (fr'^Error \'Scsi error - MEDIUM ERROR:L-EC UNCORRECTABLE ERROR\' occurred while reading \'(?P<input_name>[^\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', self.generic_error),
            (fr'^Error \'Scsi error - ILLEGAL REQUEST:READ OF SCRAMBLED SECTOR WITHOUT AUTHENTICATION\' occurred while reading \'(?P<input_name>[^\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', True),
            (fr'^Error \'Scsi error - ILLEGAL REQUEST:MEDIA REGION CODE IS MISMATCHED TO LOGICAL UNIT REGION\' occurred while reading \'(?P<input_name>[^\n]+?)\' at offset \'(?P<offset>\d+)\'{re_eol}', self.generic_error),
            (fr'^Error \'Scsi error - ILLEGAL REQUEST:ILLEGAL MODE FOR THIS TRACK\' occurred while reading \'(?P<input_name>[^\n]+?)\' at offset \'(?P<offset>\d+)\'', True),
            (fr'^LIBMKV_TRACE: Exception: (?P<exception>[^\n]+){re_eol}', self.generic_error),
            (fr'^Device \'(?P<device_path>[^\n]+?)\' is partially inaccessible due to a bug in Linux kernel \(it reports invalid block device size\)\. This can be worked around, but read speed may be very slow\.{re_eol}', True),
            (fr'^Failed to save title (?P<title_no>{re_title_no}) to file (?P<file_out>[^\n]+){re_eol}', self.generic_error),
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
            (fr'^AV synchronization issues were found in file \'(?P<file_name>[^\n]+)\' \(title #(?P<title_no>{re_title_no})\){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: audio gap - (?P<missing_frames>\S+) missing frame\(s\){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: (?P<action>encountered overlapping frame|short audio gap was removed), audio skew is (?P<audio_skew>\S+){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: (?P<dropped_frames>\d+) frame\(s\) dropped to reduce audio skew to (?P<audio_skew>\S+){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: (?P<overlapping_frames>\d+) overlapping frame\(s\) dropped at segment boundary{re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) *: (?P<num_frames>\d+) frame\(?s?\)? dropped to reduce audio skew to (?P<audio_skew>\S+){re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) *: video stream has (?P<num_frames>\d+) frame\(?s?\)? with invalid timecodes{re_eol}', self.generic_warning),
            (fr'^AV sync issue in stream (?P<stream_no>{re_stream_no}) at (?P<timestamp>\S+) *: video frame timecode differs by (?P<video_timecode_skew>\S+){re_eol}', self.generic_warning),
            (fr'^Too many AV synchronization issues in file \'(?P<file_out>[^\n]+)\' \(title #(?P<title_no>{re_title_no})\) ?, future messages will be printed only to log file{re_eol}', self.generic_warning),
            (fr'^Angle #(?P<angle_no>\d+) was added for title #(?P<title_no>{re_title_no}){re_eol}', self.generic_info),
            (fr'^Calculated BUP offset for VTS #(?P<vts_no>\d+) does not match one in IFO header\.{re_eol}', self.generic_warning),
            (fr'^LibreDrive firmware support is not yet available for this drive \(id=(?P<drive_id>[A-Fa-f0-9]+)\){re_eol}', self.generic_warning),
            (fr'^Using Java runtime from (?P<path>{re_dot}+){re_eol}', self.generic_warning),
            (fr'^Loaded (?P<num_svq_files>\d+) SVQ file\(s\){re_eol}', self.generic_warning),
            (fr'^Processing BD\+ code, please be patient - this may take up to few minutes{re_eol}', self.generic_warning),
            (fr'^Processing BD\+ code using generic SVQ from (?P<svq_source_file>\S+){re_eol}', self.generic_warning),
            (fr'^Processing BD\+ code using disc-specific SVQ from (?P<svq_source_file>\S+){re_eol}', self.generic_warning),
            (fr'^BD\+ code processed, got (?P<num_futs>\d+) FUT\(s\) for (?P<num_clips>\d+) clip\(s\){re_eol}', self.generic_warning),
            (fr'^BD\+ code processed, got (?P<num_futs>\d+) FUT\(s\) for (?P<num_clips>\d+) clip\(s\){re_eol}', self.generic_warning),
            (fr'^Program reads data faster than it can write to disk, consider upgrading your hard drive if you see many of these messages\.{re_eol}', self.generic_warning),
            (fr'^(?P<exec>{re_dot}+): (?P<lib>{re_dot}+): no version information available \(required by (?P<req_by>{re_dot}+)\){re_eol}', self.generic_warning),
            (fr'[^\n]*?{re_eol}', self.unknown_line),
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
                (fr'^DRV:(?P<index>\d+),(?P<flag1>\d+),(?P<flag2>\d+),(?P<flag3>\d+),(?P<drive_name>{re_dot}*),(?P<disc_name>{re_dot}*),(?P<device_name>{re_dot}*){re_eol}', self.robot_drive_scan),
                (fr'^TCOUT:(?P<count>\d+){re_eol}', self.robot_titles_count),
                (fr'^CINFO:(?P<id>\d+),(?P<code>\d+),"(?P<value>{re_dot}*)"{re_eol}', self.robot_disc_info),
                (fr'^TINFO:(?P<id>\d+),(?P<code>\d+),"(?P<value>{re_dot}*)"{re_eol}', self.robot_title_info),
                (fr'^SINFO:(?P<id>\d+),(?P<code>\d+),"(?P<value>{re_dot}*)"{re_eol}', self.robot_stream_info),
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
        self.set_current_progress(cur_pos / max, tot_pos / max)
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
        #print(f'\nrobot_drive_scan: {str!r}')
        #   DRV:index,flag1,flag2,flag3,drive_name,disc_name,device_name
        device_name = self.match.group('device_name')
        if device_name:
            self.drives.append(DriveInfo(
                index=self.match.group('index'),
                flag1=self.match.group('flag1'),
                flag2=self.match.group('flag2'),
                flag3=self.match.group('flag3'),
                drive_name=self.match.group('drive_name'),
                disc_name=self.match.group('disc_name'),
                device_name=self.match.group('device_name'),
            ))
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
        print(f'\nrobot_disc_info: {str!r}')
        return True

    def robot_title_info(self, str):
        # Disc, title and stream information
        # CINFO:id,code,value
        # TINFO:id,code,value
        # SINFO:id,code,value
        # id - attribute id, see AP_ItemAttributeId in apdefs.h
        # code - message code if attribute value is a constant string
        # value - attribute value
        print(f'\nrobot_title_info: {str!r}')
        return True

    def robot_stream_info(self, str):
        # Disc, title and stream information
        # CINFO:id,code,value
        # TINFO:id,code,value
        # SINFO:id,code,value
        # id - attribute id, see AP_ItemAttributeId in apdefs.h
        # code - message code if attribute value is a constant string
        # value - attribute value
        print(f'\nrobot_stream_info: {str!r}')
        return True

class Makemkvcon(Executable):
    # http://www.makemkv.com/developers/usage.txt

    name = 'makemkvcon'

    nice_adjustment = 19  # the nicest
    ionice_level = 7      # lowest priority

    run_func = staticmethod(do_makemkvcon_spawn_cmd)

    spawn = MakemkvconSpawn

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    DriveInfo = DriveInfo

    def build_cmd(self, *args, **kwargs):
        args = list(args)

        if 'messages' not in kwargs and '--messages' not in args:
            kwargs['messages'] = '-stdout'
        if 'progress' not in kwargs and '--progress' not in args:
            kwargs['progress'] = '-stdout'

        return super().build_cmd(*args, **kwargs)

    def mkv(self, *, source, dest_dir, title_id='all', **kwargs):
        return self('mkv', source, title_id, dest_dir, **kwargs)

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

makemkvcon = Makemkvcon()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
