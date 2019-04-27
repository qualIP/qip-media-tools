
__all__ = [
        'makemkvcon',
        ]

import collections
import logging
import pexpect
import progress
import subprocess
import sys
log = logging.getLogger(__name__)

from qip.app import app  # Also setup log.verbose
from .perf import perfcontext
from .exec import *
from .exec import spawn as _exec_spawn
from qip.utils import byte_decode

def dbg_makemkvcon_spawn_cmd(cmd, hidden_args=[], dry_run=None, no_status=False, yes=False, logfile=None):
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.verbose('CMD: %s', subprocess.list2cmdline(cmd))
    if logfile is True:
        logfile = sys.stdout.buffer
    elif logfile is False:
        logfile = None
    p = makemkvcon.spawn(cmd[0], args=cmd[1:] + hidden_args, logfile=logfile)
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
        raise subprocess.CalledProcessError(
            returncode=p.exitstatus,
            cmd=subprocess.list2cmdline(cmd),
            output=out)

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

class MakemkvconSpawn(_exec_spawn):

    num_tiltes_saved = None
    num_tiltes_failed = None
    num_errors = 0
    progress_bar = None
    makemkv_operation = None
    makemkv_action = None

    def __init__(self, *args, timeout=60 * 60, **kwargs):
        super().__init__(*args, timeout=timeout, **kwargs)

    def current_progress(self, str):
        #print('') ; app.log.debug(byte_decode(str))
        if self.progress_bar is not None:
            makemkv_action_percent = int(byte_decode(self.match.group('cur')))
            makemkv_operation_percent = int(byte_decode(self.match.group('tot')))
            old_makemkv_action_percent = self.progress_bar.makemkv_action_percent
            old_makemkv_operation_percent = self.progress_bar.makemkv_operation_percent
            self.progress_bar.makemkv_action_percent = makemkv_action_percent
            self.progress_bar.makemkv_operation_percent = makemkv_operation_percent
            if makemkv_action_percent == old_makemkv_action_percent and makemkv_operation_percent < old_makemkv_operation_percent:
                pass
            elif makemkv_action_percent < old_makemkv_action_percent and makemkv_operation_percent == old_makemkv_operation_percent:
                pass
            else:
                self.progress_bar.goto(self.progress_bar.makemkv_action_percent)
        return True

    def current_task(self, str):
        #print('') ; app.log.debug(byte_decode(str))
        task = byte_decode(self.match.group('task'))
        task_type = byte_decode(self.match.group('task_type'))
        need_update = False
        if task_type == 'operation':
            if 0 < self.progress_bar.makemkv_action_percent < 100:
                self.progress_bar.makemkv_action_percent = 100
                need_update = True
            if 0 < self.progress_bar.makemkv_operation_percent < 100:
                self.progress_bar.makemkv_operation_percent = 100
                need_update = True
            if need_update:
                self.progress_bar.goto(self.progress_bar.makemkv_action_percent)
                need_update = False
            if self.makemkv_operation is not None:
                print('')
            self.makemkv_operation = task
            self.makemkv_action = None
        else:
            if 0 < self.progress_bar.makemkv_action_percent < 100:
                self.progress_bar.makemkv_action_percent = 100
                need_update = True
            if need_update:
                self.progress_bar.goto(self.progress_bar.makemkv_action_percent)
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
                self.progress_bar.makemkv_operation_percent = 0
                self.progress_bar.makemkv_action_percent = 0
            if task_type == 'action':
                self.progress_bar.makemkv_action_percent = 0
            self.progress_bar.goto(self.progress_bar.makemkv_action_percent)
        return True

    def saving_titles_count(self, str):
        if self.progress_bar is not None:
            print('')
        str = byte_decode(str)
        log.info(str.strip('\r\n'))
        return True

    def generic_error(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.progress_bar is not None:
            print('')
        log.error(str.strip('\r\n'))
        self.num_errors += 1
        return True

    def generic_info(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.progress_bar is not None:
            print('')
        log.info(str.strip('\r\n'))
        return True

    def generic_warning(self, str):
        str = byte_decode(str).rstrip('\r\n')
        if self.progress_bar is not None:
            print('')
        log.warning(str.strip('\r\n'))
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
                self.progress_bar.makemkv_operation_percent = 0
                self.progress_bar.makemkv_action_percent = 0
                self.progress_bar.suffix = '%(makemkv_action_percent)d%% of %(makemkv_action)s, %(makemkv_operation_percent)d%% of %(makemkv_operation)s'
                self.progress_bar.goto(self.progress_bar.makemkv_action_percent)
        re_eol = r'\r?\n'
        re_title_no = r'(?:[0-9/]+|\d+\.m2ts)'  # "1", "1/0/1", "00040.m2ts"
        re_stream_no = r'(?:\d+(?:,\d+)*)'  # "1", "1,2"
        pattern_dict = collections.OrderedDict([
            (r'^Current progress - *(?P<cur>\d+)% *, Total progress - *(?P<tot>\d+)% *' + re_eol, self.current_progress),
            (r'^MakeMKV v[^\n]+ started' + re_eol, True),
            (r'^Current (?P<task_type>action|operation): (?P<task>[^\r\n]+)' + re_eol, self.current_task),
            (r'^Operation successfully completed' + re_eol, True),
            (r'^Saving (?P<title_count>\d+) titles into directory (?P<dest_dir>[^\r\n]+)' + re_eol, self.saving_titles_count),
            (r'^Title #(?P<title_no>' + re_title_no + r') has length of (?P<length>\d+) seconds which is less than minimum title length of (?P<min_length>\d+) seconds and was therefore skipped' + re_eol, True),
            (r'^Title (?P<title_no1>\d+) in VTS (?P<vts_no>\d+) is equal to title (?P<title_no2>\d+) and was skipped' + re_eol, True),
            (r'^Using direct disc access mode' + re_eol, True),
            (r'^Downloading latest SDF to (?P<dest_dir>[^\n]+) \.\.\.' + re_eol, True),
            (r'^Using LibreDrive mode \(v(?P<version>\d+) id=(?P<id>[0-9a-fA-F]+)\)' + re_eol, True),
            (r'^Loaded content hash table, will verify integrity of M2TS files\.' + re_eol, True),
            (r'^Cells (?P<num_cells>\d+)-end were skipped due to cell commands \(structure protection\?\)' + re_eol, True),
            (r'^Complex multiplex encountered - (?P<num_cells>\d+) cells and (?P<num_vobus>\d+) VOBUs have to be scanned\. This may take some time, please be patient - it can\'t be avoided\.' + re_eol, True),
            (r'^Region setting of drive (?P<drive_label>[^\n]+) does not match the region of currently inserted disc, trying to work around\.\.\.' + re_eol, True),
            (r'^Title #(?P<title_no>' + re_title_no + r') was added \((?P<num_cells>\d+) cell\(s\), (?P<time>[0-9:]+)\)' + re_eol, True),
            (r'^File (?P<file_name>\S+) was added as title #(?P<title_no>\d+)' + re_eol, True),
            (r'^Unable to open file \'(?P<file_in>[^\']+)\' in OS mode due to a bug in OS Kernel\. This can be worked around, but read speed may be very slow\.' + re_eol, True),
            (r'^Encountered (?P<num_errors>\d+) errors of type \'Read Error\' - see http://www\.makemkv\.com/errors/dvdread/' + re_eol, self.generic_error),
            (r'^Error \'Posix error - Input/output error\' occurred while reading \'(?P<device_path>[^\n]+?)\' at offset \'(?P<offset>\d+)\'' + re_eol, self.generic_error),
            (r'^Error \'Scsi error - MEDIUM ERROR:L-EC UNCORRECTABLE ERROR\' occurred while reading \'(?P<input_name>[^\n]+?)\' at offset \'(?P<offset>\d+)\'' + re_eol, self.generic_error),
            (r'^Error \'Scsi error - ILLEGAL REQUEST:READ OF SCRAMBLED SECTOR WITHOUT AUTHENTICATION\' occurred while reading \'(?P<input_name>[^\n]+?)\' at offset \'(?P<offset>\d+)\'' + re_eol, True),
            (r'^Error \'Scsi error - ILLEGAL REQUEST:MEDIA REGION CODE IS MISMATCHED TO LOGICAL UNIT REGION\' occurred while reading \'(?P<input_name>[^\n]+?)\' at offset \'(?P<offset>\d+)\'' + re_eol, self.generic_error),
            (r'^Error \'Scsi error - ILLEGAL REQUEST:ILLEGAL MODE FOR THIS TRACK\' occurred while reading \'(?P<input_name>[^\n]+?)\' at offset \'(?P<offset>\d+)\'', True),
            (r'^LIBMKV_TRACE: Exception: (?P<exception>[^\n]+)' + re_eol, self.generic_error),
            (r'^Device \'(?P<device_path>[^\n]+?)\' is partially inaccessible due to a bug in Linux kernel \(it reports invalid block device size\)\. This can be worked around, but read speed may be very slow\.' + re_eol, True),
            (r'^Failed to save title (?P<title_no>' + re_title_no + r') to file (?P<file_out>[^\n]+)' + re_eol, self.generic_error),
            (r'^Failed to open disc' + re_eol, self.generic_error),
            (r'^(?P<num_tiltes_saved>\d+) titles saved' + re_eol, self.parse_titles_saved),
            (r'^(?P<num_tiltes_saved>\d+) titles saved, (?P<num_tiltes_failed>\d+) failed' + re_eol, self.parse_titles_saved),
            (r'^Copy complete\. (?P<num_tiltes_saved>\d+) titles saved\.' + re_eol, self.parse_titles_saved),
            (r'^Copy complete\. (?P<num_tiltes_saved>\d+) titles saved, (?P<num_tiltes_failed>\d+) failed\.' + re_eol, self.parse_titles_saved),
            (r'^Track #(?P<track_no>\d+) turned out to be empty and was removed from output file' + re_eol, self.generic_warning),
            (r'^Forced subtitles track #(?P<track_no>\d+) turned out to be empty and was removed from output file' + re_eol, self.generic_warning),
            (r'^AV synchronization issues were found in file \'(?P<file_name>[^\n]+)\' \(title #(?P<title_no>' + re_title_no + r')\)' + re_eol, self.generic_warning),
            (r'^AV sync issue in stream (?P<stream_no>' + re_stream_no + ') at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: audio gap - (?P<missing_frames>\S+) missing frame\(s\)' + re_eol, self.generic_warning),
            (r'^AV sync issue in stream (?P<stream_no>' + re_stream_no + ') at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: (?P<action>encountered overlapping frame|short audio gap was removed), audio skew is (?P<audio_skew>\S+)' + re_eol, self.generic_warning),
            (r'^AV sync issue in stream (?P<stream_no>' + re_stream_no + ') at (?P<timestamp>\S+) with duration of (?P<duration>\S+) *: (?P<dropped_frames>\d+) frame\(s\) dropped to reduce audio skew to (?P<audio_skew>\S+)' + re_eol, self.generic_warning),
            (r'^AV sync issue in stream (?P<stream_no>' + re_stream_no + ') at (?P<timestamp>\S+) *: (?P<num_frames>\d+) frame\(s\) dropped to reduce audio skew to (?P<audio_skew>\S+)' + re_eol, self.generic_warning),
            (r'^Angle #(?P<angle_no>\d+) was added for title #(?P<title_no>' + re_title_no + ')' + re_eol, self.generic_info),
            (r'[^\n]*?' + re_eol, self.unknown_line),
            (pexpect.EOF, False),
        ])
        return super().communicate(pattern_dict, *args, **kwargs)

    def close(self, *args, **kwargs):
        if self.progress_bar is not None:
            self.progress_bar.finish()
            self.progress_bar = None
        return super().close(*args, **kwargs)

class Makemkvcon(Executable):
    # http://www.makemkv.com/developers/usage.txt

    run_func = staticmethod(do_makemkvcon_spawn_cmd)

    name = 'makemkvcon'

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

    def build_cmd(self, *args, **kwargs):
        args = list(args)

        if 'messages' not in kwargs and '--messages' not in args:
            kwargs['messages'] = '-stdout'
        if 'progress' not in kwargs and '--progress' not in args:
            kwargs['progress'] = '-stdout'

        return super().build_cmd(*args, **kwargs)

    spawn = MakemkvconSpawn

    def mkv(self, *, source, dest_dir, title_id='all', **kwargs):
        return self('mkv', source, title_id, dest_dir, **kwargs)

makemkvcon = Makemkvcon()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
