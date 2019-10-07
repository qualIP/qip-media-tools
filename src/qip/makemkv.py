
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
        re_dot = r'[^\r\n]'  # To be used instead of r'.'
        re_eol = r'\r?\n'
        re_title_no = r'(?:[0-9/]+|\d+\.m2ts|\d+\.mpls(?:\(\d+\))?)'  # "1", "1/0/1", "00040.m2ts" "00081.mpls" "00081.mpls(1)"
        re_stream_no = r'(?:\d+(?:,\d+)*)'  # "1", "1,2"
        pattern_dict = collections.OrderedDict([
            (fr'^Current progress - *(?P<cur>\d+)% *, Total progress - *(?P<tot>\d+)% *{re_eol}', self.current_progress),
            (fr'^MakeMKV v[^\n]+ started{re_eol}', True),
            (fr'^Current (?P<task_type>action|operation): (?P<task>[^\r\n]+){re_eol}', self.current_task),
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
            (fr'^Cells (?P<cell_no1>\d+)-(?P<cell_no2>\d+|end) were skipped due to cell commands \(structure protection\?\){re_eol}', True),
            (fr'^Cells (?P<cell_no1>\d+)-(?P<cell_no2>\d+|end) were removed from (?P<from>title start|title end){re_eol}', True),
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
            (fr'^Failed to open disc{re_eol}', self.generic_error),
            (fr'^(?P<num_tiltes_saved>\d+) titles saved{re_eol}', self.parse_titles_saved),
            (fr'^(?P<num_tiltes_saved>\d+) titles saved, (?P<num_tiltes_failed>\d+) failed{re_eol}', self.parse_titles_saved),
            (fr'^Copy complete\. (?P<num_tiltes_saved>\d+) titles saved\.{re_eol}', self.parse_titles_saved),
            (fr'^Copy complete\. (?P<num_tiltes_saved>\d+) titles saved, (?P<num_tiltes_failed>\d+) failed\.{re_eol}', self.parse_titles_saved),
            (fr'^Track #(?P<track_no>\d+) turned out to be empty and was removed from output file{re_eol}', self.generic_warning),
            (fr'^Forced subtitles track #(?P<track_no>\d+) turned out to be empty and was removed from output file{re_eol}', self.generic_warning),
            (fr'^Title #(?P<title_no>\d+) declared length is (?P<declared_length>\S+) while its real length is (?P<real_length>\S+) - assuming fake title{re_eol}', self.generic_warning),
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
            (pexpect.EOF, False),
        ])
        return super().communicate(pattern_dict, *args, **kwargs)
    # TODO
    # 2019-05-29 02:12:36 ERROR UNKNOWN: 'Saved SD dump file as /home/qip/.MakeMKV/dump_SD_55BD8BB1EB43C4A0F126.tgz'
    # 2019-05-29 02:12:38 ERROR UNKNOWN: 'This functionality is shareware. You may evaluate it for 30 days after what you would need to purchase an activation key if you like the functionality. Do you want to start evaluation period now?'
    # 2019-05-29 02:12:38 ERROR UNKNOWN: 'Evaluation version, 30 day(s) out of 30 remaining'

    def close(self, *args, **kwargs):
        if self.progress_bar is not None:
            self.progress_bar.finish()
            self.progress_bar = None
        return super().close(*args, **kwargs)

class Makemkvcon(Executable):
    # http://www.makemkv.com/developers/usage.txt

    name = 'makemkvcon'

    ionice_level = 7  # lowest priority

    run_func = staticmethod(do_makemkvcon_spawn_cmd)

    spawn = MakemkvconSpawn

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def build_cmd(self, *args, **kwargs):
        args = list(args)

        if 'messages' not in kwargs and '--messages' not in args:
            kwargs['messages'] = '-stdout'
        if 'progress' not in kwargs and '--progress' not in args:
            kwargs['progress'] = '-stdout'

        return super().build_cmd(*args, **kwargs)

    def mkv(self, *, source, dest_dir, title_id='all', **kwargs):
        return self('mkv', source, title_id, dest_dir, **kwargs)

makemkvcon = Makemkvcon()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
