#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

import argparse
import collections
import functools
import logging
import os
import pexpect
import re
import shutil
import subprocess
import types
import time
import sys
logging.basicConfig(level=logging.DEBUG)

from qip.app import app
from qip.cdda import *
from qip.cdparanoia import *
from qip.cdrdao import *
from qip.exec import *
from qip.file import *
from qip.safecopy import *
from qip.snd import *
from qip.utils import byte_decode
import qip.cdda as cdda
import qip.snd

def dbg_spawn_cmd(cmd, hidden_args=[], no_status=False, yes=False, logfile=True):
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.verbose('CMD: %s', subprocess.list2cmdline(cmd))
    out = ''
    if logfile is True:
        logfile = sys.stdout.buffer
    elif logfile is False:
        logfile = None
    p = pexpect.spawn(cmd[0], args=cmd[1:] + hidden_args, timeout=None,
            logfile=logfile)
    while True:
        index = p.expect([
            r'Select match, 0 for none(?: \[0-\d+\]\?\r*\n)?',  # 0
            r'.*[\r\n]',  # 1
            pexpect.EOF,
            ])
        if index == 1:
            #app.log.debug('<<< %s%s', byte_decode(p.before), byte_decode(p.match.group(0)))
            out += byte_decode(p.before) + byte_decode(p.match.group(0))
        elif index == 0:
            #app.log.debug('<<< %s%s', byte_decode(p.before), p.match.group(0))
            #puts [list <<< $expect_out(buffer)]
            out += byte_decode(p.before) + byte_decode(p.match.group(0))
            logfile = p.logfile
            logfile_send = p.logfile_send
            try:
                if yes:
                    s = "0"
                else:
                    print('<interact>', end='', flush=True)
                    s = input()
                    print('</interact>', end='', flush=True)
                    p.logfile = None
                    p.logfile_send = None
                #app.log.debug('>>> sending %r', s)
                p.send(s)
                #puts [list >>> sending eol]
                p.send('\r')
            finally:
                p.logfile_send = logfile_send
                p.logfile = logfile
        elif index == 2:
            #app.log.debug('<<< %s%s', byte_decode(p.before))
            out += byte_decode(p.before)
            break
    try:
        p.wait()
    except pexpect.ExceptionPexpect as err:
        if err.value != 'Cannot wait for dead child process.':
            raise
    p.close()
    if p.signalstatus is not None:
        raise Exception('Command exited due to signal %r' % (p.signalstatus,))
    if not no_status and p.exitstatus:
        raise subprocess.CalledProcessError(
                returncode=p.exitstatus,
                cmd=subprocess.list2cmdline(cmd),
                output=out)
    return out

def do_spawn_cmd(cmd, **kwargs):
    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(cmd))
        return ''
    else:
        return dbg_spawn_cmd(cmd, **kwargs)

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='BIN/CUE Maker',
            contact='jst@qualipsoft.com',
            )

    in_tags = TrackTags()

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_argument('--continue', '-c', dest='_continue', action='store_true', help='continue creating RIP')
    #pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
    #pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')
    pgroup.add_argument('--device', default=os.environ.get('CDROM', '/dev/cdrom'), help='specify alternate cdrom device')
    # TODO pgroup.add_argument('--device-cache-size', dest='device_cache_size', default=None, help='cache size for your device (MB)')
    pgroup.add_argument('--device-sample-offset', dest='device_sample_offset', default=6, help='sample read offset for your device (http://www.accuraterip.com/driveoffsets.htm)')
    pgroup.add_argument('--eject', default=False, action='store_true', help='eject cdrom when done')
    pgroup.add_argument('--cddb', default=False, action='store_true', help='enable CDDB')
    pgroup.add_argument('--fast', default=False, action='store_true', help='fast mode')
    pgroup.add_argument('--ripper', default='cdparanoia', choices=['cdparanoia', 'safecopy'], help='ripper program to use')
    pgroup.add_argument('--force-read-speed', dest='force_read_speed', default=None, help='force CDROM read speed')
    pgroup.add_argument('--safecopy-timing', dest='safecopy_timing', default=False, action='store_true', help='write safecopy timing files')
    pgroup.add_argument('--cdparanoia-max-skip-retries', dest='cdparanoia_max_skip_retries', default=None, type=int, help='number of retries before cdparanoia is allowed to skip a sector')
    pgroup.add_argument('--no-disable-paranoia', dest='no_disable_paranoia', default=False, action='store_true', help='Do not use cdparanoia --disable-paranoia on first try')
    pgroup.add_argument('--max-track-retries', dest='max_track_retries', default=None, type=int, help='number of retries before giving up reading a track')
    pgroup.add_argument('--rebuild', default=False, action='store_true', help='rebuild tracks from best sectors if all else fails')
    pgroup.add_argument('--rebuild-unique-sectors', dest='rebuild_unique_sectors', default=False, action='store_true', help='rebuild tracks even from unique sectors')
    pgroup.add_argument('--save-temps', dest='save_temps', default=False, action='store_true', help='do not delete intermediate files')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

    pgroup = app.parser.add_argument_group('Tags')
    #pgroup.add_argument('--title', '--song', '-s', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--album', '-A', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    #pgroup.add_argument('--artist', '-a', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--albumartist', '-R', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--genre', '-g', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--writer', '-w', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--year', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--type', tags=in_tags, default='audiobook', action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--disk', '--disc', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--disks', '--discs', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    #pgroup.add_argument('--track', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    #pgroup.add_argument('--sort-title', '--sort-song', dest='sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-album', dest='sortalbum', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    #pgroup.add_argument('--sort-artist', dest='sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumartist', dest='sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-writer', dest='sortwriter', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)

    app.parser.add_argument('file_name_prefix', help='output file name prefix')

    app.parse_args()

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'mkbincue'
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)

    for prog in (
            'cdrdao',
            app.args.ripper,
            'cueconvert',  # cuetools
            ):
        if prog and not shutil.which(prog):
            raise Exception('%s: command not found' % (prog,))

    if app.args.action == 'mkbincue':
        if not app.args.file_name_prefix:
            raise Exception('No file name prefix provided')
        mkbincue(app.args.file_name_prefix, in_tags)
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

def consecutive_ranges(numbers):
    start = end = None
    for number in numbers:
        assert number is not None
        if start is not None:
            if number == end + 1:
                end = number
                continue
            yield (start, end)
        start = end = number
    if start is not None:
        yield (start, end)

def mkbincue(file_name_prefix, in_tags):
    file_name_prefix = in_tags.format(file_name_prefix)

    toc_file = CDTocFile(file_name_prefix + '.toc')
    cue_file = CDDACueSheetFile(file_name_prefix + '.cue')
    bin_file = BinaryFile(file_name_prefix + '.bin')
    retry_no_audio_cd = True

    def fix_cue_file(cue_file):
        assert len(cue_file.files) == 1
        cue_file.files[0].name = bin_file.file_name
        cue_file.files[0].format = CDDACueSheetFile.FileFormatEnum.BINARY

    if app.args.ripper == 'cdparanoia':
        app.log.info('Creating %s...', cue_file)
        if cue_file.exists():
            if app.args._continue:
                app.log.info('... CONTINUE: file exists.')
                print(cue_file.read())
            else:
                raise Exception('File exists: %s' % (cue_file,))
            if in_tags is not None:
                cue_file.tags.update(in_tags)
        else:
            want_retry_no_audio_cd = retry_no_audio_cd
            retry_no_audio_cd = False
            d = cdparanoia.query(
                    device=app.args.device,
                    verbose=True,
                    retry_no_audio_cd=want_retry_no_audio_cd,
                    run_func=do_spawn_cmd,
                    )
            cue_file.prepare_from_toc(d.toc,
                    file=bin_file.file_name,
                    file_format=CDDACueSheetFile.FileFormatEnum.BINARY,
                    track_type=CDDACueSheetFile.TrackTypeEnum.AUDIO,
                    )
            if in_tags is not None:
                cue_file.tags.update(in_tags)
            if not app.args.dry_run:
                # fix_cue_file(cue_file)
                cue_file.create()
                print(cue_file.read())
    else:
        if True:

            app.log.info('Creating %s...', toc_file)
            if toc_file.exists():
                if app.args._continue:
                    app.log.info('... CONTINUE: file exists.')
                    toc_file.read()
                else:
                    raise Exception('File exists: %s' % (toc_file,))
            else:
                d = cdrdao.read_toc(
                        device=app.args.device,
                        fast_toc=app.args.fast,
                        with_cddb=app.args.cddb,
                        datafile=bin_file,
                        toc_file=toc_file,
                        run_func=do_spawn_cmd)
                toc_file.read()

            app.log.info('Creating %s...', cue_file)
            if cue_file.exists():
                if app.args._continue:
                    app.log.info('... CONTINUE: file exists.')
                    cue_file.read()
                else:
                    raise Exception('File exists: %s' % (cue_file,))
                if in_tags is not None:
                    cue_file.tags.update(in_tags)
            else:
                cmd = [shutil.which('cueconvert')]
                cmd += [toc_file.file_name]
                if True:
                    out = do_spawn_cmd(cmd,
                            logfile=app.args.logging_level <= logging.DEBUG)
                    # out = clean_cmd_output(out)
                    if not app.args.dry_run:
                        cue_file.parse(out)
                else:
                    cmd += [cue_file.file_name]
                    out = do_spawn_cmd(cmd,
                            logfile=app.args.logging_level <= logging.DEBUG)
                    # out = clean_cmd_output(out)
                    if not app.args.dry_run:
                        cue_file.read()
                if in_tags is not None:
                    cue_file.tags.update(in_tags)
                if not app.args.dry_run:
                    fix_cue_file(cue_file)
                    cue_file.create()
                    print(cue_file.read())
            print('')

        else:

            app.log.info('Creating %s...', cue_file)
            if cue_file.exists():
                if app.args._continue:
                    app.log.info('... CONTINUE: file exists.')
                    cue_file.read()
                else:
                    raise Exception('File exists: %s' % (cue_file,))
                if in_tags is not None:
                    cue_file.tags.update(in_tags)
            else:
                cmd = [shutil.which('mkcue')]
                cmd += [app.args.device]
                out = do_spawn_cmd(cmd,
                        logfile=app.args.logging_level <= logging.DEBUG)
                if not app.args.dry_run:
                    cue_file.parse(out)
                if in_tags is not None:
                    cue_file.tags.update(in_tags)
                if not app.args.dry_run:
                    fix_cue_file(cue_file)
                    cue_file.create()
                    print(cue_file.read())
            print('')

    app.log.info('Creating %s...', bin_file)
    # TODO continue
    if app.args.ripper == 'safecopy':
        stage1_badblocks_file = TextFile(file_name_prefix + '.stage1.badblocks')
        stage2_badblocks_file = TextFile(file_name_prefix + '.stage2.badblocks')
        stage3_badblocks_file = TextFile(file_name_prefix + '.stage3.badblocks')
        stage3_old_badblocks_file = TextFile(file_name_prefix + '.stage3.old.badblocks')
        if not app.args.dry_run and not app.args._continue:
            stage1_badblocks_file.unlink(force=True)
            stage2_badblocks_file.unlink(force=True)
            stage3_badblocks_file.unlink(force=True)
            stage3_old_badblocks_file.unlink(force=True)
        run_func = functools.partial(do_spawn_cmd,
                no_status=True,
                )
        d1 = None
        d2 = None
        d3 = None
        dt = types.SimpleNamespace()
        dt.bytes_copied = 0
        dt.elapsed_time = 0.0
        in_badblocks_file = False
        out_badblocks_file = stage1_badblocks_file
        if app.args._continue and out_badblocks_file.exists():
            app.log.info('... CONTINUE: %s file exists.' % (out_badblocks_file,))
        else:
            d1 = safecopy(app.args.device, bin_file.file_name, stage=1,
                          I=in_badblocks_file, o=out_badblocks_file,
                          timing=app.args.safecopy_timing, run_func=run_func)  # TODO: dry-run
            try:
                dt.bytes_copied += d1.bytes_copied
                dt.elapsed_time += d1.elapsed_time
                if d1.bytes_copied:
                    app.log.info('Stage 1 Speed: %.1fx', d1.bytes_copied / d1.elapsed_time / cdda.CDDA_1X_SPEED)
            except:
                pass
        if out_badblocks_file.getsize():
            in_badblocks_file = out_badblocks_file
            out_badblocks_file = stage2_badblocks_file
            if app.args._continue and out_badblocks_file.exists():
                app.log.info('... CONTINUE: %s file exists.' % (out_badblocks_file,))
            else:
                d2 = safecopy(app.args.device, bin_file.file_name, stage=2,
                              I=in_badblocks_file, o=out_badblocks_file,
                              timing=app.args.safecopy_timing, run_func=run_func)  # TODO: dry-run
                try:
                    dt.bytes_copied += d2.bytes_copied
                    dt.elapsed_time += d2.elapsed_time
                    if d2.bytes_copied:
                        app.log.info('Stage 2 Speed: %.1fx', d2.bytes_copied / d2.elapsed_time / cdda.CDDA_1X_SPEED)
                except:
                    pass
            if out_badblocks_file.getsize():
                in_badblocks_file = out_badblocks_file
                out_badblocks_file = stage3_badblocks_file
                if app.args._continue and out_badblocks_file.exists():
                    app.log.info('... CONTINUE: %s file exists.' % (out_badblocks_file,))
                    in_badblocks_file = stage3_old_badblocks_file
                    out_badblocks_file.rename(in_badblocks_file, update_file_name=False)
                d3 = safecopy(app.args.device, bin_file.file_name, stage=3,
                              I=in_badblocks_file, o=out_badblocks_file,
                              timing=app.args.safecopy_timing, run_func=run_func)  # TODO: dry-run
                try:
                    dt.bytes_copied += d3.bytes_copied
                    dt.elapsed_time += d3.elapsed_time
                    if d3.bytes_copied:
                        app.log.info('Stage 3 Speed: %.1fx', d3.bytes_copied / d3.elapsed_time / cdda.CDDA_1X_SPEED)
                except:
                    pass
                if out_badblocks_file.getsize():
                    raise ValueError('%s size if not 0!', out_badblocks_file)
        try:
            app.log.info('Overall Speed: %.1fx', dt.bytes_copied / dt.elapsed_time / cdda.CDDA_1X_SPEED)
        except:
            pass
        if not app.args.dry_run and not app.args.save_temps:
            stage1_badblocks_file.unlink(force=True)
            stage2_badblocks_file.unlink(force=True)
            stage3_badblocks_file.unlink(force=True)
            stage3_old_badblocks_file.unlink(force=True)
        d0 = d1 or d2 or d3
        if d0.low_level_disk_size is not None:
            bin_file_size = bin_file.getsize()
            if bin_file_size < d0.low_level_disk_size:
                raise ValueError('%s (%r) is less than CDROM low level disk size (%r)!' % (bin_file, bin_file_size, d0.low_level_disk_size))
            if bin_file_size > d0.low_level_disk_size:
                app.log.info('Truncating %s to %r bytes...', bin_file, d0.low_level_disk_size)
                if not app.args.dry_run:
                    bin_file.truncate(d0.low_level_disk_size)
                print('')
    elif app.args.ripper == 'cdparanoia':
        run_func = functools.partial(do_spawn_cmd,
                #no_status=True,
                )
        if True:
            dt = types.SimpleNamespace()
            done_track_files = {}
            todo_track_files = {track_no: [] for track_no in range(1, len(cue_file.tracks) + 1)
                    #if track_no <= 3
                    }
            try_number = 0
            for track_no in sorted(todo_track_files.keys()):
                track_bin_file = BinaryFile('track%02d.%s.bin' % (track_no, file_name_prefix))
                if track_bin_file.exists():
                    if app.args._continue:
                        app.log.info('... CONTINUE: %s file exists.' % (track_bin_file,))
                        done_track_files[track_no] = track_bin_file
                        del todo_track_files[track_no]
                    else:
                        raise Exception('File exists: %s' % (track_bin_file,))
            while todo_track_files and (
                    app.args.max_track_retries is None or
                    try_number < app.args.max_track_retries):
                try_number += 1
                try_file_name_prefix = 'try%d.%s' % (try_number, file_name_prefix)
                try_rip_track_nos = sorted(todo_track_files.keys())
                if app.args._continue:
                    for track_no in list(try_rip_track_nos):
                        track_file_name_prefix = 'track%02d.%s' % (track_no, try_file_name_prefix)
                        track_bin_file = BinaryFile(track_file_name_prefix + '.bin')
                        if track_bin_file.exists():
                            app.log.info('... CONTINUE: %s file exists.' % (track_bin_file,))
                            try_rip_track_nos.remove(track_no)
                for start_track_no, end_track_no in consecutive_ranges(try_rip_track_nos):
                    app.log.info('Try %d. Ripping track%s %s...%s',
                            try_number,
                            's' if end_track_no > start_track_no else '',
                            '%d-%d' % (start_track_no, end_track_no) if end_track_no > start_track_no else start_track_no,
                            ' (limit with --max-track-retries option)' if try_number > 2 else '')
                    try:
                        with TempFile(try_file_name_prefix + '.cdparanoia.log', delete=not app.args.save_temps) as try_log_file:
                            want_retry_no_audio_cd = retry_no_audio_cd
                            retry_no_audio_cd = False
                            cmd = ['-d', app.args.device,
                                    '--verbose',
                                    #'--stderr-progress',
                                    '--never-skip' if app.args.cdparanoia_max_skip_retries is None else '--never-skip=%d' % (app.args.cdparanoia_max_skip_retries,),
                                    '--log-summary=%s' % (try_log_file.file_name,),
                                    '--sample-offset', '%+i' % (app.args.device_sample_offset),
                                    '--output-raw-little-endian',  # http://wiki.multimedia.cx/?title=PCM#Red_Book_CD_Audio
                                    '--batch',
                                    ]
                            if app.args.force_read_speed is not None:
                                cmd += ['--force-read-speed', app.args.force_read_speed]
                            if False:  # TODO gets stuck on last sector!
                                if not app.args.no_disable_paranoia:
                                    if try_number == 1:
                                        cmd += ['--disable-paranoia']
                            cmd += ['--', '%d-%d' % (start_track_no, end_track_no),
                                    try_file_name_prefix + '.bin']
                            t0 = time.time()
                            out = cdparanoia.run_wrapper(*cmd,
                                    retry_no_audio_cd=want_retry_no_audio_cd,
                                    run_func=do_spawn_cmd).out
                            t1 = time.time()
                    except:
                        exc_type, exc, exc_traceback = sys.exc_info()
                        app.log.error('Exception caught: %s', (exc or exc_type.__name__))
                        for track_no in reversed(range(start_track_no, end_track_no+1)):
                            track_file_name_prefix = 'track%02d.%s' % (track_no, try_file_name_prefix)
                            track_bin_file = BinaryFile(track_file_name_prefix + '.bin')
                            if track_bin_file.exists():
                                app.log.warning('%r: Possibly incomplete; Removing...', track_bin_file)
                                try:
                                    track_bin_file.unlink()
                                except Exception as e:
                                    app.log.error('%r: %s', track_bin_file)
                                break
                            else:
                                app.log.debug('%r: does not exist...', track_bin_file)
                        raise
                    dt.elapsed_time = t1 - t0
                    with open('cdparanoia.out', 'a') as f:
                        f.write(out)
                    out = clean_cmd_output(out)
                    dt.bytes_copied = 0
                    for track_no in range(start_track_no, end_track_no+1):
                        track_file_name_prefix = 'track%02d.%s' % (track_no, try_file_name_prefix)
                        track_bin_file = BinaryFile(track_file_name_prefix + '.bin')
                        dt.bytes_copied += track_bin_file.getsize()
                    app.log.info('Track(s) Speed: %.1fx', dt.bytes_copied / dt.elapsed_time / cdda.CDDA_1X_SPEED)
                for track_no, this_track_files in sorted(todo_track_files.items()):
                    track_file_name_prefix = 'track%02d.%s' % (track_no, try_file_name_prefix)
                    track_bin_file = BinaryFile(track_file_name_prefix + '.bin')
                    app.log.verbose('%r: MD5 = %s', track_bin_file, track_bin_file.md5.hexdigest())
                    if this_track_files:
                        for track_file2 in this_track_files:
                            if (
                                    track_file2 is not track_bin_file and
                                    track_file2.md5.hexdigest() == track_bin_file.md5.hexdigest()):
                                app.log.verbose('%r: same as %r. DONE', track_bin_file, track_file2)
                                assert track_file2.read() == track_bin_file.read()
                                done_track_files[track_no] = track_bin_file
                                if not app.args.save_temps:
                                    track_bin_file.rename('track%02d.%s.bin' % (track_no, file_name_prefix))
                                    for track_bin_file2 in this_track_files:
                                        track_bin_file2.unlink()
                                del todo_track_files[track_no]
                                break
                        else:
                            app.log.warning('%r: all other track files differ; Will retry.', track_bin_file)
                            this_track_files.append(track_bin_file)
                    else:
                        this_track_files.append(track_bin_file)
            if todo_track_files and app.args.rebuild:
                for track_no, this_track_files in sorted(todo_track_files.items()):
                    track_rebuild_bin_file = BinaryFile('track%02d.rebuild.%s.bin' % (track_no, file_name_prefix))
                    app.log.info('Rebuilding %s...', track_rebuild_bin_file)
                    track_size = this_track_files[0].getsize()
                    for track_bin_file2 in this_track_files[1:]:
                        track_size2 = track_bin_file2.getsize()
                        if track_size != track_size2:
                            raise Exception('File %s size (%d) does not match that of %s (%d)' % (
                                track_bin_file2, track_size2,
                                this_track_files[0], track_size))
                    if track_size % cdda.CDDA_BYTES_PER_SECTOR:
                        raise Exception('File %s size (%d) is not exactly divisible by a CD sector size (%d)' % (
                            this_track_files[0], track_size,
                            cdda.CDDA_BYTES_PER_SECTOR))

                    total_percent = 0.0
                    num_sectors = track_size // cdda.CDDA_BYTES_PER_SECTOR

                    if True:
                        data_counters = [collections.Counter()
                                for sector_no
                                in range(num_sectors)]
                        for track_bin_file in this_track_files:
                            app.log.debug('Reading %s...', track_bin_file)
                            with track_bin_file.open() as rfd:
                                for sector_no, data_counter in enumerate(data_counters):
                                    data = rfd.read(cdda.CDDA_BYTES_PER_SECTOR)
                                    data_counter[data] += 1
                        with track_rebuild_bin_file.open(mode='w') as wfd:
                            for sector_no, data_counter in enumerate(data_counters):
                                data, count = data_counter.most_common(1)[0]
                                percent = count / len(this_track_files)
                                total_percent += percent
                                if False and data == b'\0' * cdda.CDDA_BYTES_PER_SECTOR:
                                    app.log.warning('... sector {} is all 0\'s'.format(sector_no))
                                elif count <= 1 and not app.args.rebuild_unique_sectors:
                                    raise Exception('... sector {} is only certain at {:.1%} ({}/{}) (use --rebuild-unique-sectors option?)'.format(sector_no, percent, count, len(this_track_files)))
                                elif count < len(this_track_files)-1:
                                    app.log.warning('... sector {} is only certain at {:.1%} ({}/{})'.format(sector_no, percent, count, len(this_track_files)))
                                wfd.write(data)

                    else:
                        with track_rebuild_bin_file.open(mode='w') as wfd:
                            for sector_no in range(num_sectors):
                                offset = sector_no * cdda.CDDA_BYTES_PER_SECTOR
                                data_counter = collections.Counter()
                                for track_bin_file in this_track_files:
                                    with track_bin_file.open() as rfd:
                                        rfd.seek(offset, os.SEEK_SET)
                                        data = rfd.read(cdda.CDDA_BYTES_PER_SECTOR)
                                        data_counter[data] += 1
                                data, count = data_counter.most_common(1)[0]
                                percent = count / len(this_track_files)
                                total_percent += percent
                                if False and data == b'\0' * cdda.CDDA_BYTES_PER_SECTOR:
                                    app.log.warning('... sector {} is all 0\'s'.format(sector_no))
                                elif count <= 1:
                                    raise Exception('... sector {} is only certain at {:.1%} ({}/{})'.format(sector_no, percent, count, len(this_track_files)))
                                elif count < len(this_track_files)-1:
                                    app.log.warning('... sector {} is only certain at {:.1%} ({}/{})'.format(sector_no, percent, count, len(this_track_files)))
                                wfd.write(data)

                    app.log.warning('Final certainty is {:.2%}.'.format(total_percent / num_sectors))

                    done_track_files[track_no] = track_rebuild_bin_file
                    del todo_track_files[track_no]
                    track_rebuild_bin_file.rename('track%02d.%s.bin' % (track_no, file_name_prefix))
                    if not app.args.save_temps:
                        for track_bin_file2 in this_track_files:
                            track_bin_file2.unlink()
            if todo_track_files:
                raise Exception('Giving up; Still more tracks to retry: %s (use --rebuild option?)' % (
                    ', '.join(
                        '%d-%d' % (start_track_no, end_track_no) \
                                if start_track_no != end_track_no \
                                else '%d' % (start_track_no,)
                        for start_track_no, end_track_no
                        in consecutive_ranges(sorted(todo_track_files.keys()))),))
            app.log.info('%r: Combining tracks...', bin_file)
            bin_file.combine_from([
                track_bin_file
                for n, track_bin_file in sorted(done_track_files.items())])
            if not app.args.save_temps:
                for track_bin_file in done_track_files.values():
                    track_bin_file.unlink()

        else:
            with TempFile('cdparanoia.log', delete=not app.args.save_temps) as log_file:
                cmd = ['cdparanoia',
                        '-d', app.args.device,
                        '--verbose',
                        #'--stderr-progress',
                        '--never-skip',
                        '--log-summary=%s' % (log_file.file_name,),
                        '--sample-offset', '%+i' % (app.args.device_sample_offset),
                        '--output-raw-little-endian',
                        ]
                if app.args.force_read_speed is not None:
                    cmd += ['--force-read-speed', app.args.force_read_speed]
                cmd += ['--', '1-',
                        bin_file.file_name]
                t0 = time.time()
                out = run_func(cmd)
                t1 = time.time()
            dt.elapsed_time = t1 - t0
            with open('cdparanoia.out', 'w') as f: f.write(out)
            out = clean_cmd_output(out)
            dt.bytes_copied = bin_file.getsize()
            app.log.info('Overall Speed: %.1fx', dt.bytes_copied / dt.elapsed_time / cdda.CDDA_1X_SPEED)
    else:
        raise ValueError('Unsupported ripper %r' % (app.args.ripper,))
    print('')

    if app.args.eject:
        app.log.info('Ejecting...')
        cmd = [shutil.which('eject')]
        cmd += [app.args.device]
        out = do_spawn_cmd(cmd)
        # out = clean_cmd_output(out)
        print('')

    app.log.info('DONE!')

    return True

# strottie@vb-strottie-wp:~$ find /dev -type l | xargs ls -l | grep sr1
# ls: cannot access /dev/disk/by-label/x2fhome: No such file or directory
# ls: cannot access /dev/disk/by-label/x2f: No such file or directory
# lrwxrwxrwx 1 root root  6 Mar 29 02:26 /dev/block/11:1 -> ../sr1
# lrwxrwxrwx 1 root root  3 Mar 29 02:26 /dev/cdrom -> sr1
# lrwxrwxrwx 1 root root  3 Mar 29 02:26 /dev/cdrw -> sr1
# lrwxrwxrwx 1 root root  9 Mar 29 02:26 /dev/disk/by-id/usb-ASUS_BW-12B1ST_a_1234567895F2-0:0 -> ../../sr1
# lrwxrwxrwx 1 root root  9 Mar 29 02:26 /dev/disk/by-path/pci-0000:00:0c.0-usb-0:3:1.0-scsi-0:0:0:0 -> ../../sr1
# lrwxrwxrwx 1 root root  3 Mar 29 02:26 /dev/dvd -> sr1
# lrwxrwxrwx 1 root root  3 Mar 29 02:26 /dev/dvdrw -> sr1

# strottie@vb-strottie-wp:~$ cdparanoia -vQ
# cdparanoia III release 10.2 (September 11, 2008)
# 
# Using cdda library version: 10.2
# Using paranoia library version: 10.2
# Checking /dev/cdrom for cdrom...
#     Testing /dev/cdrom for SCSI/MMC interface
# 	SG_IO device: /dev/sr1
# 
# CDROM model sensed sensed: ASUS BW-12B1ST   a 1.00 
#  
# 
# Checking for SCSI emulation...
#     Drive is ATAPI (using SG_IO host adaptor emulation)
# 
# Checking for MMC style command set...
#     Drive is MMC style
#     DMA scatter/gather table entries: 1
#     table entry size: 122880 bytes
#     maximum theoretical transfer: 52 sectors
#     Setting default read size to 27 sectors (63504 bytes).
# 
# Verifying CDDA command set...
#     Expected command set reads OK.
# 
# Attempting to set cdrom to full speed... 
#     drive returned OK.
# 
# Table of contents (audio tracks only):
# track        length               begin        copy pre ch
# ===========================================================
#   1.    16503 [03:40.03]        0 [00:00.00]    no   no  2
#   2.    20492 [04:33.17]    16503 [03:40.03]    no   no  2
#   3.    21622 [04:48.22]    36995 [08:13.20]    no   no  2
#   4.    19665 [04:22.15]    58617 [13:01.42]    no   no  2
#   5.    19560 [04:20.60]    78282 [17:23.57]    no   no  2
#   6.    20691 [04:35.66]    97842 [21:44.42]    no   no  2
#   7.    24615 [05:28.15]   118533 [26:20.33]    no   no  2
#   8.    18325 [04:04.25]   143148 [31:48.48]    no   no  2
#   9.    17262 [03:50.12]   161473 [35:52.73]    no   no  2
#  10.    19912 [04:25.37]   178735 [39:43.10]    no   no  2
#  11.    18553 [04:07.28]   198647 [44:08.47]    no   no  2
#  12.    22819 [05:04.19]   217200 [48:16.00]    no   no  2
#  13.    20235 [04:29.60]   240019 [53:20.19]    no   no  2
#  14.    17908 [03:58.58]   260254 [57:50.04]    no   no  2
#  15.     9889 [02:11.64]   278162 [61:48.62]    no   no  2
#  16.    21176 [04:42.26]   288051 [64:00.51]    no   no  2
#  17.    19812 [04:24.12]   309227 [68:43.02]    no   no  2
# TOTAL  329039 [73:07.14]    (audio only)

# strottie@vb-strottie-wp:~$ cdparanoia -d /dev/sr1 -Q
# cdparanoia III release 10.2 (September 11, 2008)
# 
# 
# Table of contents (audio tracks only):
# track        length               begin        copy pre ch
# ===========================================================
#   1.    17102 [03:48.02]        0 [00:00.00]    no   no  2
#   2.    19769 [04:23.44]    17102 [03:48.02]    no   no  2
#   3.    19010 [04:13.35]    36871 [08:11.46]    no   no  2
#   4.    18186 [04:02.36]    55881 [12:25.06]    no   no  2
#   5.     8160 [01:48.60]    74067 [16:27.42]    no   no  2
#   6.    18740 [04:09.65]    82227 [18:16.27]    no   no  2
#   7.    20962 [04:39.37]   100967 [22:26.17]    no   no  2
#   8.    18516 [04:06.66]   121929 [27:05.54]    no   no  2
#   9.    20611 [04:34.61]   140445 [31:12.45]    no   no  2
#  10.    23264 [05:10.14]   161056 [35:47.31]    no   no  2
#  11.     7302 [01:37.27]   184320 [40:57.45]    no   no  2
#  12.    22406 [04:58.56]   191622 [42:34.72]    no   no  2
#  13.    18418 [04:05.43]   214028 [47:33.53]    no   no  2
#  14.    19656 [04:22.06]   232446 [51:39.21]    no   no  2
#  15.    19870 [04:24.70]   252102 [56:01.27]    no   no  2
#  16.    16994 [03:46.44]   271972 [60:26.22]    no   no  2
#  17.    18516 [04:06.66]   288966 [64:12.66]    no   no  2
#  18.    19757 [04:23.32]   307482 [68:19.57]    no   no  2
# TOTAL  327239 [72:43.14]    (audio only)

# strottie@vb-strottie-wp:~$ cdparanoia -d /dev/sr1 -A
# cdparanoia III release 10.2 (September 11, 2008)
# 
# Using cdda library version: 10.2
# Using paranoia library version: 10.2
# Checking /dev/sr1 for cdrom...
#     Testing /dev/sr1 for SCSI/MMC interface
# 	SG_IO device: /dev/sr1
# 
# CDROM model sensed sensed: ASUS BW-12B1ST   a 1.00 
# 
# Checking for SCSI emulation...
#     Drive is ATAPI (using SG_IO host adaptor emulation)
# 
# Checking for MMC style command set...
#     Drive is MMC style
#     DMA scatter/gather table entries: 1
#     table entry size: 122880 bytes
#     maximum theoretical transfer: 52 sectors
#     Setting default read size to 27 sectors (63504 bytes).
# 
# Verifying CDDA command set...
#     Expected command set reads OK.
# 
# Attempting to set cdrom to full speed... 
#     drive returned OK.
# 
# =================== Checking drive cache/timing behavior ===================
# 
# Seek/read timing:
#     [72:29.56]:   38ms seek, 0.74ms/sec read [18.0x]                 
#     [70:00.00]:   41ms seek, 1.63ms/sec read [8.2x]                 
#     [60:00.00]:   49ms seek, 1.52ms/sec read [8.8x]                 
#     [50:00.00]:   32ms seek, 1.63ms/sec read [8.2x]                 
#     [40:00.00]:   49ms seek, 1.78ms/sec read [7.5x]                 
#     [30:00.00]:   58ms seek, 1.96ms/sec read [6.8x]                 
#     [20:00.00]:   63ms seek, 2.22ms/sec read [6.0x]                 
#     [10:00.00]:   90ms seek, 2.59ms/sec read [5.1x]                 
#     [00:00.00]:   99ms seek, 3.29ms/sec read [4.1x]                 
# 
# Analyzing cache behavior...
#     Approximate random access cache size: 27 sector(s)               
#     Drive cache tests as contiguous                           
#     Drive readahead past read cursor: 1231 sector(s)                
#     Cache tail cursor tied to read cursor                      
#     Cache tail granularity: 27 sector(s)                      
#             Cache read speed: 0.19ms/sector [69x]
#             Access speed after backseek: 0.94ms/sector [14x]
#     WARNING: Read timing after backseek faster than expected!
#              It's possible/likely that this drive is not
#              flushing the readahead cache on backward seeks!
# 
# 
# WARNING! PARANOIA MAY NOT BE TRUSTWORTHY WITH THIS DRIVE!
# 
# The Paranoia library may not model this CDROM drive's cache
# correctly according to this analysis run. Analysis is not
# always accurate (it can be fooled by machine load or random
# kernel latencies), but if a failed result happens more often
# than one time in twenty on an unloaded machine, please mail
# the cdparanoia.log file produced by this failed analysis to
# paranoia-dev@xiph.org to assist developers in extending
# Paranoia to handle this CDROM properly.

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
