#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

import argparse
import copy
import decimal
import errno
import functools
import html
import logging
import os
import pexpect
import re
import reprlib
import shutil
import subprocess
import sys
import types
import xml.etree.ElementTree as ET
reprlib.aRepr.maxdict = 100

from qip import json
from qip.app import app
from qip.exec import *
from qip.file import *
from qip.isolang import isolang
from qip.parser import *
from qip.perf import perfcontext
from qip.handbrake import *
import qip.snd
from qip.snd import *
from qip.mkv import *
from qip.m4a import *
from qip.utils import byte_decode
from qip.ffmpeg import ffmpeg
from qip.opusenc import opusenc
from qip.threading import *

# https://www.ffmpeg.org/ffmpeg.html


def MOD_ROUND(v, m):
    return v if m == 1 else m * ((v + (m >> 1)) // m)

def MOD_DOWN(v, m):
    return m * (v // m)

def MOD_UP(v, m):
    return m * ((v + m - 1) // m)

def isolang_or_None(v):
    return None if v == 'None' else isolang(v)

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='Multimedia [de]multiplexer',
            contact='jst@qualipsoft.com',
            )

    app.cache_dir = os.path.abspath('mmdemux-cache')

    in_tags = AlbumTags()

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
    pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')
    pgroup.add_argument('--continue', dest='_continue', action='store_true', help='continue mode')
    pgroup.add_argument('--batch', '-B', action='store_true', help='batch mode')

    pgroup = app.parser.add_argument_group('Video Control')
    pgroup.add_argument('--crop', default=True, action='store_true', help='enable cropping video (default)')
    pgroup.add_argument('--no-crop', dest='crop', default=argparse.SUPPRESS, action='store_false', help='disable cropping video')
    pgroup.add_argument('--parallel-chapters', dest='parallel_chapters', default=True, action='store_true', help='enable per-chapter parallel processing (default)')
    pgroup.add_argument('--no-parallel-chapters', dest='parallel_chapters', default=argparse.SUPPRESS, action='store_false', help='disable per-chapter parallel processing')
    pgroup.add_argument('--cropdetect-duration', dest='cropdetect_duration', type=int, default=60, help='cropdetect duration (seconds)')
    pgroup.add_argument('--video-language', '--vlang', dest='video_language', type=isolang_or_None, default=isolang('und'), help='Override video language (mux)')

    pgroup = app.parser.add_argument_group('Subtitle Control')
    pgroup.add_argument('--subrip-matrix', dest='subrip_matrix', default=None, help='SubRip OCR matrix file')

    pgroup = app.parser.add_argument_group('Files')
    pgroup.add_argument('--output', '-o', dest='output_file', default=None, help='specify the output (demuxed) file name')

    pgroup = app.parser.add_argument_group('Compatibility')

    pgroup = app.parser.add_argument_group('Encoding')
    pgroup.add_argument('--keyint', type=int, default=5, help='keyframe interval (seconds)')

    pgroup = app.parser.add_argument_group('Tags')
    pgroup.add_argument('--title', '--song', '-s', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--albumtitle', '--album', '-A', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--artist', '-a', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--albumartist', '-R', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--genre', '-g', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--writer', '--composer', '-w', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--date', '--year', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--type', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--contenttype', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction, help='Content Type (%s)' % (', '.join((str(e) for e in qip.snd.ContentType)),))
    pgroup.add_argument('--disk', '--disc', dest='disk_slash_disks', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--track', dest='track_slash_tracks', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--picture', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--tvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--season', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--episode', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--language', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--country', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--compilation', '-K', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-artist', dest='sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-title', '--sort-song', dest='sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumartist', dest='sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumtitle', '--sort-album', dest='sortalbumtitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-composer', '--sort-writer', dest='sortcomposer', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-tvshow', dest='sorttvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)

    pgroup = app.parser.add_argument_group('Options')
    pgroup.add_argument('--device', default=os.environ.get('CDROM', '/dev/cdrom'), help='specify alternate cdrom device')
    pgroup.add_argument('--project', default=None, help='project name')
    pgroup.add_argument('--chain', action='store_true', help='chain hb->mux->optimize->demux')
    pgroup.add_argument('--cleanup', action='store_true', help='cleanup when done')

    pgroup = app.parser.add_argument_group('Music extraction')
    pgroup.add_argument('--skip-chapters', dest='num_skip_chapters', type=int, default=0, help='number of chapters to skip')
    pgroup.add_argument('--bitrate', type=int, default=argparse.SUPPRESS, help='force the encoding bitrate')  # TODO support <int>k
    pgroup.add_argument('--target-bitrate', dest='target_bitrate', type=int, default=argparse.SUPPRESS, help='specify the resampling target bitrate')
    pgroup.add_argument('--channels', type=int, default=argparse.SUPPRESS, help='force the number of audio channels')

    pgroup = app.parser.add_argument_group('Actions')
    pgroup.add_argument('--rip', dest='rip_dir', help='directory to rip device to')
    pgroup.add_argument('--hb', dest='hb_files', nargs='+', default=(), help='files to run through HandBrake')
    pgroup.add_argument('--mux', dest='mux_files', nargs='+', default=(), help='files to mux')
    pgroup.add_argument('--update', dest='update_dirs', nargs='+', default=(), help='directories to update mux parameters for')
    pgroup.add_argument('--chop', dest='chop_dirs', nargs='+', default=(), help='directories to chop into chapters')
    pgroup.add_argument('--extract-music', dest='extract_music_dirs', nargs='+', default=(), help='directories to extract music from')
    pgroup.add_argument('--optimize', dest='optimize_dirs', nargs='+', default=(), help='directories to optimize')
    pgroup.add_argument('--demux', dest='demux_dirs', nargs='+', default=(), help='directories to demux')

    app.parse_args()

    # if getattr(app.args, 'action', None) is None:
    #     app.args.action = TODO
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    did_something = False
    if app.args.rip_dir:
        action_rip(app.args.rip_dir, app.args.device)
        did_something = True
    for inputfile in getattr(app.args, 'hb_files', ()):
        action_hb(inputfile, in_tags=in_tags)
        did_something = True
    for inputfile in getattr(app.args, 'mux_files', ()):
        action_mux(inputfile, in_tags=in_tags)
        did_something = True
    for inputdir in getattr(app.args, 'update_dirs', ()):
        action_update(inputdir, in_tags=in_tags)
        did_something = True
    for inputdir in getattr(app.args, 'chop_dirs', ()):
        action_chop(inputdir, in_tags=in_tags)
        did_something = True
    for inputdir in getattr(app.args, 'extract_music_dirs', ()):
        action_extract_music(inputdir, in_tags=in_tags)
        did_something = True
    for inputdir in getattr(app.args, 'optimize_dirs', ()):
        action_optimize(inputdir, in_tags=in_tags)
        did_something = True
    for inputdir in getattr(app.args, 'demux_dirs', ()):
        action_demux(inputdir, in_tags=in_tags)
        did_something = True
    if not did_something:
        raise ValueError('Nothing to do!')

def codec_name_to_ext(codec_name):
    try:
        codec_ext = {
            # video
            'mpeg2video': '.mpeg2',
            'msmpeg4v3': '.msmpeg4v3.avi',
            'mpeg4': '.mp4',
            'h264': '.h264',
            'h265': '.h265',
            'vp8': '.vp8',
            'vp9': '.vp9',
            # audio
            'ac3': '.ac3',
            'mp3': '.mp3',
            'dts': '.dts',
            'opus': '.opus',
            'aac': '.aac',
            'wav': '.wav',
            # subtitles
            'dvd_subtitle': '.sub',  # and .idx
            'hdmv_pgs_subtitle': '.sup',
            'subrip': '.srt',
            'webvtt': '.vtt',
        }[codec_name]
    except KeyError as err:
        raise ValueError('Unsupported codec %r' % (codec_name,)) from err
    return codec_ext

def ext_to_container(ext):
    try:
        ext_container = {
            # video
            '.mpeg2': 'mpeg2video',
            '.mpegts': 'mpegts',
            '.h264': 'h264',
            #'.h265': 'h265',
            #'.vp8': 'vp8',
            '.vp9': 'ivf',
            # audio
            #'.ac3': 'ac3',
            #'.dts': 'dts',
            #'.opus': 'opus',
            #'.aac': 'aac',
            '.wav': 'wav',
            # subtitles
            #'.sub': 'dvd_subtitle',
            #'.idx': 'dvd_subtitle',
            #'.sup': 'hdmv_pgs_subtitle',
            '.vtt': 'webvtt',
        }[ext]
    except KeyError as err:
        raise ValueError('Unsupported extension %r' % (ext,)) from err
    return ext_container

def float_ratio(frame_rate):
    if type(frame_rate) is str:
        m = re.match(r'^([0-9]+)/([1-9][0-9]*)$', frame_rate)
        if m:
            frame_rate = int(m.group(1)) / int(m.group(2))
        else:
            frame_rate = float(frame_rate)
    return frame_rate

def get_vp9_target_bitrate(width, height, frame_rate, mq=True):
    frame_rate = float_ratio(frame_rate)
    # https://sites.google.com/a/webmproject.org/wiki/ffmpeg/vp9-encoding-guide
    # https://headjack.io/blog/hevc-vp9-vp10-dalaa-thor-netvc-future-video-codecs/
    if False:
        # Youtube
        if height <= 144:
            # 8- Youtube compresses to 144p (256×144) with a bit rate  0.085 Mbps
            video_target_bit_rate = 85
        elif height <= 240:
            # 7- Youtube compresses 240p (426×240) with a bit rate  0.157 Mbps
            video_target_bit_rate = 157
        elif height <= 360:
            # 6- Youtube compresses to 360p  (640×360) with a bit rate  0.373 Mbps
            video_target_bit_rate = 373
        elif height <= 480:
            # 5- Youtube compresses to 480p (854×480) with a bit rate  0.727 Mbps
            video_target_bit_rate = 727
        elif height <= 720:
            # 4- Youtube compresses to 720p (1280×720) with a bit rate  1.468 Mbps
            video_target_bit_rate = 1468
        elif height <= 1080:
            # 3- Youtube compresses 1080p (1920×1080) with a bit rate  2.567 Mbps
            video_target_bit_rate = 2567
        elif height <= 1440:
            # 2- Youtube compresses to (2K) 1440p (2560×1440) with a bit rate  8.589 Mbps
            video_target_bit_rate = 8589
        elif height <= 2160:
            # 1- Youtube compresses to 2160p (4K) (3840×2160) with a bit rate  17.3 Mbps
            video_target_bit_rate = 17300
        elif height <= 4320 or True:
            # 0- Youtube compresses to 4320p (8K) (7680×4320) with a bit rate  21.2 Mbps
            video_target_bit_rate = 21200
        if frame_rate >= 30:
            video_target_bit_rate = video_target_bit_rate * 2
        video_target_bit_rate = video_target_bit_rate * 2
        # video_target_bit_rate = int(video_target_bit_rate * 1.2)  # +20%
        return video_target_bit_rate
    else:
        # Google
        #     Frame Size/Frame Rate   Target Bitrate (VOD, kbps)      Min Bitrate (50%)       Max Bitrate (145%)
        if height <= 240:
            # 320x240p @ 24,25,30     150                             75                      218
            return 150
        if height <= 360:
            # 640x360p @ 24,25,30     276                             138                     400
            return 276
        if height <= 480:
            # 640x480p @ 24,25,30     512 (LQ), 750 (MQ)              256 (LQ) 375 (MQ)       742 (LQ) 1088 (MQ)
            return 750 if mq else 512
        if height <= 720:
            # 1280x720p @ 24,25,30    1024                            512                     1485
            # 1280x720p @ 50,60       1800                            900                     2610
            if frame_rate <= 30:
                return 1024
            else:
                return 1800
        if height <= 1080:
            # 1920x1080p @ 24,25,30   1800                            900                     2610
            # 1920x1080p @ 50,60      3000                            1500                    4350
            if frame_rate <= 30:
                return 1800
            else:
                return 3000
        if height <= 1440:
            # 2560x1440p @ 24,25,30   6000                            3000                    8700
            # 2560x1440p @ 50,60      9000                            4500                    13050
            if frame_rate <= 30:
                return 6000
            else:
                return 9000
        elif height <= 2160 or True:
            # 3840x2160p @ 24,25,30   12000                           6000                    17400
            # 3840x2160p @ 50,60      18000                           9000                    26100
            if frame_rate <= 30:
                return 12000
            else:
                return 18000
    raise NotImplementedError

def get_vp9_target_quality(width, height, frame_rate):  # CQ
    if type(frame_rate) is str:
        m = re.match(r'^([0-9]+)/([1-9][0-9]*)$', frame_rate)
        if m:
            frame_rate = int(m.group(1)) / int(m.group(2))
        else:
            frame_rate = int(frame_rate)
    if True:
        # Google
        #     Frame Height      Target Quality (CQ)
        if height <= 240:
            # 240               37
            return 37
        elif height <= 360:
            # 360               36
            return 36
        elif height <= 480:
            # 480               34 (LQ) or 33 (MQ)
            return 33
        elif height <= 720:
            # 720               32
            return 32
        elif height <= 1080:
            # 1080              31
            return 31
        elif height <= 1440:
            # 1440              24
            return 24
        elif height <= 2160 or True:
            # 2160              15
            return 15
    raise NotImplementedError

def get_vp9_tile_columns_and_threads(width, height):
    if True:
        # Minimum tile width is 256...
        # Google
        #     Frame Size      Number of tile-columns  Number of threads
        if height <= 240:
            # 320x240         1 (-tile-columns 0)     2
            return 0, 2
        elif height <= 360:
            # 640x360         2 (-tile-columns 1)     4
            return 1, 4
        elif height <= 480:
            # 640x480         2 (-tile-columns 1)     4
            return 1, 4
        elif height <= 720:
            # 1280x720        4 (-tile-columns 2)     8
            return 2, 8
        elif height <= 1080:
            # 1920x1080       4 (-tile-columns 2)     8
            return 2, 8
        elif height <= 1440:
            # 2560x1440       8 (-tile-columns 3)     16
            return 3, 16
        elif height <= 2160 or True:
            # 3840x2160       16 (-tile-columns 4)    24
            return 4, 24
    raise NotImplementedError

def action_rip(rip_dir, device):
    device = os.path.realpath(device)  # makemkv is picky!
    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(['mkdir', rip_dir]))
    else:
        os.mkdir(rip_dir)
    cmd = [
        'makemkvcon',
        '--minlength=%d' % (3600,),
        'mkv', 'dev:%s' % (device,),
        'all',
        rip_dir,
    ]
    out = do_spawn_cmd(cmd)
    if app.args.chain:
        with os.scandir(rip_dir) as it:
            for entry in it:
                assert entry.name.endswith('.mkv')
                assert entry.is_file()
                app.args.mux_files += (os.path.join(rip_dir, entry.name),)

def action_hb(inputfile, in_tags):
    app.log.info('HandBrake %s...', inputfile)
    inputfile = SoundFile(inputfile)
    inputfile_base, inputfile_ext = os.path.splitext(inputfile.file_name)
    outputfile_name = "%s.hb.mkv" % (inputfile_base,)
    if app.args.chain:
        app.args.mux_files += (outputfile_name,)

    if inputfile_ext in (
            '.mkv',
            '.mpeg2',
            ):
        ffprobe_dict = inputfile.extract_ffprobe_json()

        for stream_dict in ffprobe_dict['streams']:
            if stream_dict.get('skip', False):
                continue
            stream_index = int(stream_dict['index'])
            stream_codec_type = stream_dict['codec_type']
            if stream_codec_type == 'video':
                break
        else:
            raise ValueError('No video stream found!')

        video_target_bit_rate = get_vp9_target_bitrate(
            width=stream_dict['width'],
            height=stream_dict['height'],
            frame_rate=stream_dict['r_frame_rate'],
            )
        video_target_quality = get_vp9_target_quality(
            width=stream_dict['width'],
            height=stream_dict['height'],
            frame_rate=stream_dict['r_frame_rate'],
            )

        with perfcontext('Convert w/ HandBrake'):
            out = HandBrake(
                   # Dimensions
                   # crop='<top:bottom:left:right>',
                   loose_crop=True,
                   auto_anamorphic=True,
                   modulus=2,
                   # Filters
                   deinterlace=True,
                   # Video
                   encoder='VP9',
                   encoder_preset='slow',
                   #vb=video_target_bit_rate, two_pass=True, turbo=True,
                   quality=video_target_quality,
                   vfr=True,
                   # Chapters
                   markers=True,
                   # Audio
                   all_audio=True,
                   aencoder='copy',
                   # Subtitles
                   all_subtitles=True,
                   subtitle_default='none',
                   # Files
                   input=inputfile.file_name,
                   output=outputfile_name,
                )

    else:
        raise ValueError('Unsupported extension %r' % (inputfile_ext,))

def action_mux(inputfile, in_tags):
    app.log.info('Muxing %s...', inputfile)
    inputfile = SoundFile(inputfile)
    inputfile_base, inputfile_ext = os.path.splitext(inputfile.file_name)
    outputdir = app.args.project or "%s" % (inputfile_base,)
    if app.args.chain:
        app.args.optimize_dirs += (outputdir,)

    if app.args._continue and os.path.isdir(outputdir):
        app.log.warning('Directory exists: %r: ignoring', outputdir)
        return True

    mux_dict = {
        'streams': [],
        'chapters': {},
        'tags': AlbumTags(),
    }

    name_scan_str = os.path.basename(inputfile_base)
    name_scan_str = re.sub(r'_t\d+$', '', name_scan_str)
    m = (
            re.match(r'^(?P<tvshow>.+) S(?P<season>\d\d)(?P<str_episodes>(?:E\d\d)+) (?P<title>.+)$', name_scan_str)
         or re.match(r'^(?P<title>.+)$', name_scan_str)
        )
    if m:
        d = m.groupdict()
        try:
            str_episodes = d.pop('str_episodes')
        except KeyError:
            pass
        else:
            d['episode'] = [int(e) for e in str_episodes.split('E') if e]
        mux_dict['tags'].update(d)
    mux_dict['tags'].update(in_tags)
    if app.args.interactive:
        # for tag in set(SoundTagEnum) - set(SoundTagEnum.iTunesInternalTags):
        for tag in (
                SoundTagEnum.artist,
                SoundTagEnum.contenttype,
                SoundTagEnum.episode,
                SoundTagEnum.genre,
                SoundTagEnum.title,
                SoundTagEnum.tvshow,
                SoundTagEnum.year,
            ):
            # Force None values to actually exist
            if mux_dict['tags'][tag] is None:
                mux_dict['tags'][tag] = None
        mux_dict['tags'] = edvar(mux_dict['tags'])[1]
        for tag, value in mux_dict['tags'].items():
            if value is None:
                del mux_dict['tags'][tag]

    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(['mkdir', outputdir]))
    else:
        os.mkdir(outputdir)

    if inputfile_ext in (
            '.mkv',
            ):
        ffprobe_dict = inputfile.extract_ffprobe_json()

        has_forced_subtitle = False
        subtitle_sizes = []

        for stream_dict in ffprobe_dict['streams']:
            if stream_dict.get('skip', False):
                continue
            stream_out_dict = {}
            stream_index = int(stream_dict['index'])
            stream_out_dict['index'] = stream_index
            stream_codec_type = stream_out_dict['codec_type'] = stream_dict['codec_type']
            if stream_codec_type in ('video', 'audio', 'subtitle'):
                stream_codec_name = stream_dict['codec_name']
                stream_ext = codec_name_to_ext(stream_codec_name)
                output_track_file_name = '%s/track-%02d-%s%s' % (
                        outputdir,
                        stream_index,
                        stream_codec_type,
                        stream_ext,
                        )
                stream_out_dict['file_name'] = os.path.basename(output_track_file_name)

                if stream_codec_type == 'video':

                    if False:
                        with perfcontext('Scan w/ HandBrake'):
                            out = HandBrake(
                                   # Dimensions
                                   # crop='<top:bottom:left:right>',
                                   loose_crop=True,
                                   # Filters
                                   deinterlace=True,
                                   input=inputfile.file_name,
                                   json=True,
                                   scan=True,
                                   run_func=do_exec_cmd,
                                )
                            if not app.args.dry_run:
                                (hb_sect, hb_sect_dict), = HandBrake.parse_json_output(out.out)
                                hb_title_dict, = hb_sect_dict['TitleList']
                                hb_crop = hb_title_dict['Crop']
                                t, b, l, r = hb_crop
                                hb_geometry = hb_title_dict['Geometry']
                                if (t, b, l, r) != (0, 0, 0, 0):
                                    w = hb_geometry['Width'] - l - r
                                    h = hb_geometry['Height'] - t - b
                                    stream_out_dict['crop'] = [w, h, l, t]

                                hb_InterlaceDetected = hb_title_dict['InterlaceDetected']
                                if hb_InterlaceDetected:
                                    raise NotImplementedError('Interlace detected')

                    if app.args.video_language:
                        stream_dict.setdefault('tags', {})
                        stream_dict['tags']['language'] = str(app.args.video_language)
                    stream_out_dict['sample_aspect_ratio'] = stream_dict['sample_aspect_ratio']
                    stream_out_dict['display_aspect_ratio'] = stream_dict['display_aspect_ratio']

                stream_disposition_dict = stream_out_dict['disposition'] = stream_dict['disposition']
                try:
                    stream_title = stream_out_dict['title'] = stream_dict['tags']['title']
                except KeyError:
                    pass
                try:
                    stream_language = stream_out_dict['language'] = stream_dict['tags']['language']
                except KeyError:
                    pass

                if stream_ext == '.vtt':
                    # Avoid mkvextract error: Extraction of track ID 3 with the CodecID 'D_WEBVTT/SUBTITLES' is not supported.
                    # (mkvextract expects S_TEXT/WEBVTT)
                    with perfcontext('extract track %d w/ ffmpeg' % (stream_index,)):
                        ffmpeg_args = [
                            '-i', inputfile.file_name,
                            '-map_metadata', '-1',
                            '-map_chapters', '-1',
                            '-map', '0:%d' % (stream_index,),
                            '-codec', 'copy',
                            output_track_file_name,
                            ]
                        ffmpeg(*ffmpeg_args,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                else:
                    with perfcontext('extract track %d w/ mkvextract' % (stream_index,)):
                        cmd = [
                            'mkvextract', 'tracks', inputfile.file_name,
                            '%d:%s' % (
                                stream_index,
                                output_track_file_name,
                            )]
                        do_spawn_cmd(cmd)

                if not app.args.dry_run:
                    if stream_codec_type == 'subtitle':
                        stream_forced = stream_disposition_dict.get('forced', None)
                        if stream_forced:
                            has_forced_subtitle = True
                        subtitle_sizes.append(
                            (stream_out_dict, os.path.getsize(output_track_file_name)))

                mux_dict['streams'].append(stream_out_dict)
            else:
                raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

        if not has_forced_subtitle and subtitle_sizes:
            max_subtitle_size = max(siz for stream_dict, siz in subtitle_sizes)
            for stream_dict, siz in subtitle_sizes:
                stream_index = stream_dict['index']
                if siz <= 0.10 * max_subtitle_size:
                    app.log.info('Detected subtitle stream #%d (%s) is forced',
                                 stream_index,
                                 stream_dict.get('language', 'und'))
                    stream_dict['disposition']['forced'] = True

        if ffprobe_dict['chapters']:
            output_chapters_file_name = '%s/chapters.xml' % (
                    outputdir,
                    )
            with perfcontext('mkvextract chapters'):
                cmd = [
                    'mkvextract', 'chapters', inputfile.file_name,
                    ]
                out = do_exec_cmd(cmd,
                                  log_append=' > %s' % (output_chapters_file_name,),
                                  #stderr=subprocess.STDOUT,
                                 )
            if not app.args.dry_run:
                safe_write_file(output_chapters_file_name, out)
            mux_dict['chapters']['file_name'] = os.path.basename(output_chapters_file_name)

    else:
        raise ValueError('Unsupported extension %r' % (inputfile_ext,))

    if not app.args.dry_run:
        output_mux_file_name = '%s/mux.json' % (outputdir,)
        with open(output_mux_file_name, 'w') as fp:
            json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

    return True

def load_mux_dict(input_mux_file_name, in_tags):
    with open(input_mux_file_name, 'r') as fp:
        mux_dict = json.load(fp)
    try:
        mux_tags = mux_dict['tags']
    except KeyError:
        mux_dict['tags'] = mux_tags = copy.copy(in_tags)
    else:
        if not isinstance(mux_tags, AlbumTags):
            mux_dict['tags'] = mux_tags = AlbumTags(mux_tags)
        mux_tags.update(in_tags)
    app.log.debug('1:mux_tags.keys(): %r', set(mux_tags.keys()))
    return mux_dict

def action_update(inputdir, in_tags):
    app.log.info('Updating %s...', inputdir)
    outputdir = inputdir

    input_mux_file_name = os.path.join(inputdir, 'mux.json')
    mux_dict = load_mux_dict(input_mux_file_name, in_tags)

    if not app.args.dry_run:
        output_mux_file_name = '%s/mux.json' % (outputdir,)
        with open(output_mux_file_name, 'w') as fp:
            json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

def get_chapters(inputdir, mux_dict):
    chapters_xml_file = mux_dict['chapters']['file_name']
    chapters_xml = ET.parse(os.path.join(inputdir, chapters_xml_file))
    chapters_root = chapters_xml.getroot()
    for eEditionEntry in chapters_root.findall('EditionEntry'):
        # TODO EditionFlagHidden ==? 0
        # TODO EditionFlagDefault ==? 1
        for chapter_no, eChapterAtom in enumerate(eEditionEntry.findall('ChapterAtom'), start=1):
            chap = types.SimpleNamespace()
            chap.no = chapter_no
            # <ChapterAtom>
            #   <ChapterUID>6524138974649683444</ChapterUID>
            #   <ChapterTimeStart>00:00:00.000000000</ChapterTimeStart>
            chap.time_start = ffmpeg.Timestamp(eChapterAtom.find('ChapterTimeStart').text)
            #   <ChapterFlagHidden>0</ChapterFlagHidden>
            #   <ChapterFlagEnabled>1</ChapterFlagEnabled>
            #   <ChapterTimeEnd>00:07:36.522733333</ChapterTimeEnd>
            chap.time_end = ffmpeg.Timestamp(eChapterAtom.find('ChapterTimeEnd').text)
            #   <ChapterDisplay>
            #     <ChapterString>Chapter 01</ChapterString>
            chap.string = eChapterAtom.find('ChapterDisplay').find('ChapterString').text
            #     <ChapterLanguage>eng</ChapterLanguage>
            #   </ChapterDisplay>
            # </ChapterAtom>
            if chap.no == 1 and chap.time_start > 0:
                chapX = types.SimpleNamespace()
                chapX.no = 0
                chapX.time_start = ffmpeg.Timestamp(0)
                chapX.time_end = ffmpeg.Timestamp(chap.time_start)
                chapX.string = 'pre-gap'
                yield chapX
            yield chap

def action_chop(inputdir, in_tags):
    app.log.info('Chopping %s...', inputdir)
    outputdir = inputdir
    if app.args.chain:
        app.args.optimize_dirs += (outputdir,)

    input_mux_file_name = os.path.join(inputdir, 'mux.json')
    mux_dict = load_mux_dict(input_mux_file_name, in_tags)

    for chap in get_chapters(inputdir, mux_dict):
        app.log.verbose('Chapter %d [%s..%s]',
                        chap.no,
                        chap.time_start,
                        chap.time_end)

        for stream_dict in mux_dict['streams']:
            if stream_dict.get('skip', False):
                continue
            stream_index = stream_dict['index']
            stream_codec_type = stream_dict['codec_type']
            orig_stream_file_name = stream_file_name = stream_dict['file_name']
            stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
            stream_language = stream_dict.get('language', 'und')

            snd_file = SoundFile(os.path.join(inputdir, stream_file_name))
            ffprobe_json = snd_file.extract_ffprobe_json()

            if (stream_codec_type == 'video'
                or stream_codec_type == 'audio'):

                force_format = None
                try:
                    force_format = ext_to_container(stream_file_ext)
                except ValueError:
                    pass

                stream_chapter_file_name = '%s-%02d%s' % (
                    stream_file_base,
                    chap.no,
                    stream_file_ext)

                with perfcontext('Chop w/ ffmpeg'):
                    ffmpeg_args = [
                        '-start_at_zero', '-copyts',
                        '-i', os.path.join(inputdir, stream_file_name),
                        '-codec', 'copy',
                        '-ss', chap.time_start,
                        '-to', chap.time_end,
                        ]
                    if force_format:
                        ffmpeg_args += [
                            '-f', force_format,
                            ]
                    ffmpeg_args += [
                        os.path.join(inputdir, stream_chapter_file_name),
                        ]
                    ffmpeg(*ffmpeg_args,
                           dry_run=app.args.dry_run,
                           y=app.args.yes)

            elif stream_codec_type == 'subtitle':
                pass
            else:
                raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

def action_optimize(inputdir, in_tags):
    app.log.info('Optimizing %s...', inputdir)
    outputdir = inputdir
    do_chain = app.args.chain

    input_mux_file_name = os.path.join(inputdir, 'mux.json')
    mux_dict = load_mux_dict(input_mux_file_name, in_tags)

    for stream_dict in mux_dict['streams']:
        if stream_dict.get('skip', False):
            continue
        stream_index = stream_dict['index']
        stream_codec_type = stream_dict['codec_type']
        orig_stream_file_name = stream_file_name = stream_dict['file_name']
        stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
        stream_language = stream_dict.get('language', 'und')

        if stream_codec_type == 'video':
            if stream_file_ext in ('.vp9', '.vp8'):
                app.log.verbose('Stream #%d %s OK', stream_index, stream_file_ext)
            else:
                new_stream_file_ext = '.vp9'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_ext)

                snd_file = SoundFile(os.path.join(inputdir, stream_file_name))
                ffprobe_json = snd_file.extract_ffprobe_json()
                ffprobe_stream_json = ffprobe_json['streams'][0]
                app.log.debug(ffprobe_stream_json)

                extra_args = []
                video_filter_specs = []

                if app.args.crop:
                    stream_crop = stream_dict.pop('crop', None)
                    if not stream_crop and 'original_crop' not in stream_dict:
                        stream_crop = ffmpeg.cropdetect(
                            input_file=os.path.join(inputdir, stream_file_name),
                            cropdetect_duration=app.args.cropdetect_duration,
                            dry_run=app.args.dry_run)
                    if stream_crop:
                        stream_dict.setdefault('original_crop', stream_crop)
                        w, h, l, t = stream_crop
                        video_filter_specs.append('crop={w}:{h}:{l}:{t}'.format(
                                    w=w, h=h, l=l, t=t))
                        # extra_args += ['-aspect', XXX]

                deint_filter_args = []
                field_order = ffprobe_stream_json.get('field_order', None)
                if field_order is not None:
                    if field_order == 'progressive':
                        # ‘progressive’ Progressive video
                        pass
                    elif field_order in ('tt', 'tb'):
                        # ‘tt’ Interlaced video, top field coded and displayed first
                        # ‘tb’ Interlaced video, top coded first, bottom displayed first
                        stream_dict.setdefault('original_field_order', field_order)
                        # https://ffmpeg.org/ffmpeg-filters.html#yadif
                        video_filter_specs.append('yadif=parity=tff')
                        stream_dict['field_order'] = field_order = 'progressive'
                    elif field_order in ('bb', 'bt'):
                        # ‘bb’ Interlaced video, bottom field coded and displayed first
                        # ‘bt’ Interlaced video, bottom coded first, top displayed first
                        stream_dict.setdefault('original_field_order', field_order)
                        # https://ffmpeg.org/ffmpeg-filters.html#yadif
                        video_filter_specs.append('yadif=parity=bff')
                        stream_dict['field_order'] = field_order = 'progressive'
                    else:
                        raise ValueError(field_order)

                if video_filter_specs:
                    extra_args += ['-filter:v', ','.join(video_filter_specs)]

                r_frame_rate = ffprobe_stream_json['r_frame_rate']

                # https://developers.google.com/media/vp9/settings/vod/
                video_target_bit_rate = get_vp9_target_bitrate(
                    width=ffprobe_stream_json['width'],
                    height=ffprobe_stream_json['height'],
                    frame_rate=r_frame_rate,
                    )
                # video_target_bit_rate = int(video_target_bit_rate * 1.2)  # 1800 * 1.2 = 2160
                video_target_bit_rate = int(video_target_bit_rate * 1.5)  # 1800 * 1.5 = 2700
                video_target_quality = get_vp9_target_quality(
                    width=ffprobe_stream_json['width'],
                    height=ffprobe_stream_json['height'],
                    frame_rate=r_frame_rate,
                    )
                vp9_tile_columns, vp9_threads = get_vp9_tile_columns_and_threads(
                    width=ffprobe_stream_json['width'],
                    height=ffprobe_stream_json['height'],
                    )

                ffmpeg_conv_args = [
                    '-b:v', '%dk' % (video_target_bit_rate,),
                    '-minrate', '%dk' % (video_target_bit_rate * 0.50,),
                    '-maxrate', '%dk' % (video_target_bit_rate * 1.45,),
                    '-tile-columns', str(vp9_tile_columns),
                    '-threads', str(vp9_threads),
                    '-row-mt', '1',
                    '-quality', 'good',
                    '-crf', str(video_target_quality),
                    '-c:v', 'libvpx-vp9',
                    '-g', str(int(app.args.keyint * float_ratio(r_frame_rate))),
                    '-speed', '1' if ffprobe_stream_json['height'] <= 480 else '2',
                    ] + extra_args + [
                    ]

                ffmpeg_concat_args = []

                chaps = list(get_chapters(inputdir, mux_dict))
                if (app.args.parallel_chapters
                        and len(chaps) > 1
                        and stream_file_ext == '.mpeg2'):  # Chopping using segment muxer is reliable (tested with mpeg2)
                    with perfcontext('Convert %s chapters to %s in parallel w/ ffmpeg' % (stream_file_name, new_stream_file_ext)):
                        chapter_stream_file_ext = {
                                '.mpeg2': '.mpegts',
                            }.get(stream_file_ext, stream_file_ext)
                        stream_chapter_file_name_pat = '%s-chap%%02d%s' % (stream_file_base, chapter_stream_file_ext)
                        new_stream_chapter_file_name_pat = '%s-chap%%02d%s' % (stream_file_base, new_stream_file_ext)

                        concat_list_file = TempFile.mkstemp(suffix='.concat.txt', open=True, text=True)
                        threads = []

                        def encode_chap():
                            app.log.verbose('Chapter %d [%s..%s]',
                                            chap.no,
                                            chap.time_start,
                                            chap.time_end)
                            stream_chapter_file_name = stream_chapter_file_name_pat % (chap.no,)
                            new_stream_chapter_file_name = new_stream_chapter_file_name_pat % (chap.no,)
                            print('file \'%s\'' % (os.path.abspath(os.path.join(inputdir, new_stream_chapter_file_name)),), file=concat_list_file.fp)

                            if app.args._continue and os.path.exists(new_stream_chapter_file_name):
                                app.log.warning('%s exists: continue...')
                            else:
                                ffmpeg_args = [
                                    '-i', os.path.join(inputdir, stream_chapter_file_name),
                                    ] + ffmpeg_conv_args + [
                                    '-f', ext_to_container(new_stream_file_ext), os.path.join(inputdir, new_stream_chapter_file_name),
                                    ]
                                thread = ExcThread(
                                        target=ffmpeg.run2pass,
                                        args=ffmpeg_args,
                                        kwargs={
                                            'slurm': True,
                                            'dry_run': app.args.dry_run,
                                            'y': app.args.yes,
                                            })
                                if shutil.which('srun') is None:
                                    thread.start()
                                    thread.join()
                                else:
                                    app.log.verbose('Start background processing of %s', stream_chapter_file_name)
                                    thread.start()
                                    threads.append(thread)

                        # Chop
                        if stream_file_ext in ('.h264',):
                            # "ffmpeg cannot always read correct timestamps from H264 streams"
                            # So split manually instead of using the segment muxer
                            assert NotImplementedError  # This is not an accurate split!!
                            ffmpeg_concat_args += [
                                '-vsync', 'drop',
                                ]
                            for chap in chaps:
                                app.log.verbose('Chapter %d [%s..%s]',
                                                chap.no,
                                                chap.time_start,
                                                chap.time_end)
                                stream_chapter_file_name = stream_chapter_file_name_pat % (chap.no,)
                                if app.args._continue and os.path.exists(stream_chapter_file_name):
                                    app.log.warning('%s exists: continue...')
                                else:
                                    with perfcontext('Chop w/ ffmpeg'):
                                        ffmpeg_args = [
                                            '-fflags', '+genpts',
                                            '-start_at_zero', '-copyts',
                                            '-i', os.path.join(inputdir, stream_file_name),
                                            '-codec', 'copy',
                                            '-ss', chap.time_start,
                                            '-to', chap.time_end,
                                            ]
                                        force_format = None
                                        try:
                                            force_format = ext_to_container(stream_file_ext)
                                        except ValueError:
                                            pass
                                        if force_format:
                                            ffmpeg_args += [
                                                '-f', force_format,
                                                ]
                                        ffmpeg_args += [
                                            os.path.join(inputdir, stream_chapter_file_name),
                                            ]
                                        ffmpeg(*ffmpeg_args,
                                               dry_run=app.args.dry_run,
                                               y=app.args.yes)
                                encode_chap()
                        else:
                            app.log.verbose('All chapters...')
                            with perfcontext('Chop w/ ffmpeg segment muxer'):
                                ffmpeg_args = [
                                    '-fflags', '+genpts',
                                    '-i', os.path.join(inputdir, stream_file_name),
                                    '-segment_times', ','.join(str(chap.time_end) for chap in chaps),
                                    '-segment_start_number', chaps[0].no,
                                    '-codec', 'copy',
                                    '-map', '0',
                                    ]
                                ffmpeg_args += [
                                    '-f', 'segment',
                                    '-segment_format', ext_to_container(chapter_stream_file_ext),
                                    os.path.join(inputdir, stream_chapter_file_name_pat),
                                    ]
                                ffmpeg(*ffmpeg_args,
                                       dry_run=app.args.dry_run,
                                       y=app.args.yes)

                            # Encode
                            for chap in chaps:
                                encode_chap()

                        # Join
                        concat_list_file.close()
                        print(concat_list_file.read())
                        exc = None
                        while threads:
                            thread = threads.pop()
                            try:
                                thread.join()
                            except BaseException as e:
                                exc = e
                        if exc:
                            raise exc

                    # Concat
                    with perfcontext('Concat %s w/ ffmpeg' % (new_stream_file_name,)):
                        ffmpeg_args = [
                            '-f', 'concat', '-safe', '0', '-i', concat_list_file,
                            '-codec', 'copy',
                            ] + ffmpeg_concat_args + [
                            '-f', 'ivf', os.path.join(inputdir, new_stream_file_name),
                            ]
                        ffmpeg(*ffmpeg_args,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                else:
                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_ext)):
                        ffmpeg_args = [
                            '-i', os.path.join(inputdir, stream_file_name),
                            ] + ffmpeg_conv_args + [
                            '-f', 'ivf', os.path.join(inputdir, new_stream_file_name),
                            ]
                        ffmpeg.run2pass(*ffmpeg_args,
                                        slurm=True,
                                        dry_run=app.args.dry_run,
                                        y=app.args.yes)

                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

        elif stream_codec_type == 'audio':

            ok_formats = (
                    '.opus',
                    #'.mp3',
                    )

            if stream_file_ext not in ok_formats:
                snd_file = SoundFile(os.path.join(inputdir, stream_file_name))
                ffprobe_json = snd_file.extract_ffprobe_json()
                app.log.debug(ffprobe_json['streams'][0])
                channels = ffprobe_json['streams'][0]['channels']
                channel_layout = ffprobe_json['streams'][0].get('channel_layout', None)
            else:
                ffprobe_json = {}

            # opusenc supports Wave, AIFF, FLAC, Ogg/FLAC, or raw PCM.
            opusenc_formats = ('.wav', '.aiff', '.flac', '.ogg', '.pcm')
            if stream_file_ext not in ok_formats + opusenc_formats:
                new_stream_file_ext = '.wav'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_ext)

                with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_ext)):
                    ffmpeg_args = [
                        '-i', os.path.join(inputdir, stream_file_name),
                        # '-channel_layout', channel_layout,
                        ]
                    ffmpeg_args += [
                        '-f', 'wav', os.path.join(inputdir, new_stream_file_name),
                        ]
                    ffmpeg(*ffmpeg_args,
                           slurm=True,
                           dry_run=app.args.dry_run,
                           y=app.args.yes)

                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

            if stream_file_ext not in ok_formats and stream_file_ext in opusenc_formats:
                # opusenc supports Wave, AIFF, FLAC, Ogg/FLAC, or raw PCM.
                new_stream_file_ext = '.opus'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_ext)

                audio_bitrate = 640000 if channels >= 4 else 384000
                audio_bitrate = min(audio_bitrate, int(ffprobe_json['streams'][0]['bit_rate']))
                audio_bitrate = audio_bitrate // 1000

                with perfcontext('Convert %s -> %s w/ opusenc' % (stream_file_ext, new_stream_file_ext)):
                    opusenc_args = [
                        '--vbr',
                        '--bitrate', str(audio_bitrate),
                        os.path.join(inputdir, stream_file_name),
                        os.path.join(inputdir, new_stream_file_name),
                        ]
                    opusenc(*opusenc_args,
                            slurm=True,
                            dry_run=app.args.dry_run)

                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

            if stream_file_ext in ok_formats:
                if stream_file_name == orig_stream_file_name:
                    app.log.verbose('Stream #%d %s OK', stream_index, stream_file_ext)
            else:
                new_stream_file_ext = '.opus'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_ext)

                audio_bitrate = 640000 if channels >= 4 else 384000
                audio_bitrate = min(audio_bitrate, int(ffprobe_json['streams'][0]['bit_rate']))
                audio_bitrate = audio_bitrate // 1000
                if channels > 2:
                    raise NotImplementedError('Conversion not supported as ffmpeg does not respect the number of channels and channel mapping')

                with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_ext)):
                    ffmpeg_args = [
                        '-i', os.path.join(inputdir, stream_file_name),
                        '-c:a', 'opus',
                        '-strict', 'experimental',  # for libopus
                        '-b:a', '%dk' % (audio_bitrate,),
                        # '-vbr', 'on', '-compression_level', '10',  # defaults
                        #'-channel', str(channels), '-channel_layout', channel_layout,
                        #'-channel', str(channels), '-mapping_family', '1', '-af', 'aformat=channel_layouts=%s' % (channel_layout,),
                        ]
                    ffmpeg_args += [
                        '-f', 'ogg', os.path.join(inputdir, new_stream_file_name),
                        ]
                    ffmpeg(*ffmpeg_args,
                           slurm=True,
                           dry_run=app.args.dry_run,
                           y=app.args.yes)

                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

        elif stream_codec_type == 'subtitle':
            if False and stream_file_ext in ('.sup',):
                new_stream_file_ext = '.sub'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_ext)

                if False:
                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_ext)):
                        ffmpeg_args = [
                            '-i', os.path.join(inputdir, stream_file_name),
                            '-scodec', 'dvdsub',
                            '-map', '0',
                            ]
                        ffmpeg_args += [
                            '-f', 'mpeg', os.path.join(inputdir, new_stream_file_name),
                            ]
                        ffmpeg(*ffmpeg_args,
                               slurm=True,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                else:
                    with perfcontext('Convert %s -> %s w/ bdsup2sub' % (stream_file_ext, new_stream_file_ext)):
                        # https://www.videohelp.com/software/BDSup2Sub
                        # https://github.com/mjuhasz/BDSup2Sub/wiki/Command-line-Interface
                        cmd = [
                            'bdsup2sub',
                            # TODO --forced-only
                            '--language', isolang(stream_language).code2,
                            '--output', os.path.join(inputdir, new_stream_file_name),
                            os.path.join(inputdir, stream_file_name),
                            ]
                        out = do_spawn_cmd(cmd)

                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

            if stream_file_ext in ('.sup', '.sub',):
                new_stream_file_ext = '.srt'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                if app.args.batch:
                    app.log.warning('BATCH MODE SKIP: Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_ext)
                    do_chain = False
                    continue
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_ext)

                if False:
                    subrip_matrix = app.args.subrip_matrix
                    if not subrip_matrix:
                        subrip_matrix_dir = os.path.expanduser('~/.cache/SubRip/Matrices')
                        if not app.args.dry_run:
                            os.makedirs(subrip_matrix_dir, exist_ok=True)

                        subrip_matrix = 'dry_run_matrix.sum' if app.args.dry_run else None
                        # ~/tools/installs/SubRip/CLI.txt
                        cmd = [
                            'SubRip', '/FINDMATRIX',
                            '--use-idx-file-offsets',
                            '--',
                            os.path.join(inputdir, stream_file_name),
                            subrip_matrix_dir,
                            ]
                        try:
                            with perfcontext('SubRip /FINDMATRIX'):
                                out = do_spawn_cmd(cmd)
                        except subprocess.CalledProcessError:
                            raise  # Seen errors before
                        else:
                            if not app.args.dry_run:
                                m = re.search(r'^([A-Z]:\\.*\.sum)\r*$', out, re.MULTILINE)
                                if m:
                                    subrip_matrix = m.group(1)
                                    cmd = [
                                        'winepath', '-u', subrip_matrix,
                                    ]
                                    subrip_matrix = do_exec_cmd(cmd)
                                    subrip_matrix = byte_decode(subrip_matrix)
                                    subrip_matrix = subrip_matrix.strip()
                                m = re.search(r'^FindMatrix: no \'good\' matrix files found\.', out, re.MULTILINE)
                                if m:
                                    pass  # Ok
                                else:
                                    raise ValueError(out)
                        if not subrip_matrix:
                            for i in range(1000):
                                subrip_matrix = os.path.join(subrip_matrix_dir, '%03d.sum' % (i,))
                                if not os.path.exists(subrip_matrix):
                                    break
                            else:
                                raise ValueError('Can\'t determine a new matrix name under %s' % (subrip_matrix_dir,))

                    with perfcontext('SubRip /AUTOTEXT'):
                        # ~/tools/installs/SubRip/CLI.txt
                        cmd = [
                            'SubRip', '/AUTOTEXT',
                            '--subtitle-language', isolang(stream_language).code3,
                            '--',
                            os.path.join(inputdir, stream_file_name),
                            os.path.join(inputdir, new_stream_file_name),
                            subrip_matrix,
                            ]
                        do_spawn_cmd(cmd)

                else:
                    with perfcontext('Convert %s -> %s w/ SubtitleEdit' % (stream_file_ext, new_stream_file_ext)):
                        if False:
                            cmd = [
                                'SubtitleEdit', '/convert',
                                os.path.join(inputdir, stream_file_name),
                                'subrip',  # format
                                ]
                            do_spawn_cmd(cmd)
                        else:
                            app.log.warn('Run OCR and save as SubRip (.srt) format: %s' % (
                                byte_decode(dbg_exec_cmd(['winepath', '-w', os.path.join(inputdir, new_stream_file_name)])).strip(),
                                ))
                            cmd = [
                                'SubtitleEdit',
                                os.path.join(inputdir, stream_file_name),
                                ]
                            do_spawn_cmd(cmd)
                            assert os.path.isfile(os.path.join(inputdir, new_stream_file_name)), \
                                    'File not found: %r' % (os.path.join(inputdir, new_stream_file_name),)
                if app.args.interactive:
                    edfile(os.path.join(inputdir, new_stream_file_name))

                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

            # NOTE:
            #  WebVTT format exported by SubtitleEdit is same as ffmpeg .srt->.vtt except ffmpeg's timestamps have more 0-padding
            if stream_file_ext in ('.srt',):
                new_stream_file_ext = '.vtt'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_ext)

                with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_ext)):
                    ffmpeg_args = [
                        '-i', os.path.join(inputdir, stream_file_name),
                        '-f', 'webvtt', os.path.join(inputdir, new_stream_file_name),
                        ]
                    ffmpeg(*ffmpeg_args,
                           #slurm=True,
                           dry_run=app.args.dry_run,
                           y=app.args.yes)

                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

            if stream_file_ext in ('.vtt',):
                if stream_file_name == orig_stream_file_name:
                    app.log.verbose('Stream #%d %s OK', stream_index, stream_file_ext)
            else:
                raise ValueError('Unsupported subtitle extension %r' % (stream_file_ext,))

        else:
            raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

    if do_chain:
        app.args.demux_dirs += (outputdir,)

def action_extract_music(inputdir, in_tags):
    app.log.info('Extracting music from %s...', inputdir)
    outputdir = inputdir

    input_mux_file_name = os.path.join(inputdir, 'mux.json')
    mux_dict = load_mux_dict(input_mux_file_name, in_tags)

    num_skip_chapters = app.args.num_skip_chapters

    chaps = list(get_chapters(inputdir, mux_dict))
    while chaps and chaps[0].no < num_skip_chapters:
        chaps.pop(0)
    tracks_total = len(chaps)

    for track_no, chap in enumerate(chaps, start=1):
        app.log.verbose('Chapter %d [%s..%s] %s -> track %d/%d',
                        chap.no,
                        chap.time_start,
                        chap.time_end,
                        chap.string,
                        track_no,
                        tracks_total)

        src_picture = None
        picture = None

        for stream_dict in mux_dict['streams']:
            if stream_dict.get('skip', False):
                continue
            stream_index = stream_dict['index']
            stream_codec_type = stream_dict['codec_type']
            orig_stream_file_name = stream_file_name = \
                    stream_dict.get('original_file_name', stream_dict['file_name'])
            stream_file_base, stream_file_ext = os.path.splitext(stream_file_name)
            stream_language = stream_dict.get('language', 'und')

            if stream_codec_type == 'video':
                pass
            elif stream_codec_type == 'audio':
                snd_file = SoundFile(os.path.join(inputdir, stream_file_name))
                ffprobe_json = snd_file.extract_ffprobe_json()
                app.log.debug(ffprobe_json['streams'][0])
                channels = ffprobe_json['streams'][0]['channels']
                channel_layout = ffprobe_json['streams'][0].get('channel_layout', None)

                force_format = None
                try:
                    force_format = ext_to_container(stream_file_ext)
                except ValueError:
                    pass

                stream_chapter_tmp_file = SoundFile(
                        os.path.join(inputdir, '%s-%02d%s' % (
                            stream_file_base,
                            chap.no,
                            stream_file_ext)))

                with perfcontext('Chop w/ ffmpeg'):
                    ffmpeg_args = [
                        '-start_at_zero', '-copyts',
                        '-i', os.path.join(inputdir, stream_file_name),
                        '-codec', 'copy',
                        '-ss', chap.time_start,
                        '-to', chap.time_end,
                        ]
                    if force_format:
                        ffmpeg_args += [
                            '-f', force_format,
                            ]
                    ffmpeg_args += [
                        stream_chapter_tmp_file.file_name,
                        ]
                    ffmpeg(*ffmpeg_args,
                           dry_run=app.args.dry_run,
                           y=app.args.yes)

                m4a = M4aFile(os.path.splitext(stream_chapter_tmp_file.file_name)[0] + '.m4a')
                m4a.tags = copy.copy(mux_dict['tags'].tracks_tags[track_no])
                m4a.tags.track = track_no  # Since a copy was taken and not fully connected to album_tags anymore
                m4a.tags.tracks = tracks_total
                m4a.tags.title = chap.string

                if src_picture != m4a.tags.picture:
                    src_picture = m4a.tags.picture
                    picture = m4a.prep_picture(src_picture,
                                               yes=app.args.yes)
                m4a.tags.picture = None  # Not supported by taged

                if stream_chapter_tmp_file.file_name != m4a.file_name:
                    audio_bitrate = 640000 if channels >= 4 else 384000
                    audio_bitrate = min(audio_bitrate, int(ffprobe_json['streams'][0]['bit_rate']))
                    audio_bitrate = audio_bitrate // 1000

                    with perfcontext('Convert %s -> %s w/ qip.m4a' % (stream_chapter_tmp_file.file_name, '.m4a')):
                        m4a.encode(inputfiles=[stream_chapter_tmp_file],
                                   target_bitrate=audio_bitrate,
                                   yes=app.args.yes,
                                   channels=getattr(app.args, 'channels', None),
                                   picture=picture,
                                   )
                else:
                    m4a.write_tags(
                            dry_run=app.args.dry_run,
                            run_func=do_exec_cmd)

            elif stream_codec_type == 'subtitle':
                pass
            else:
                raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

def action_demux(inputdir, in_tags):
    app.log.info('Demuxing %s...', inputdir)
    outputdir = inputdir

    input_mux_file_name = os.path.join(inputdir, 'mux.json')
    mux_dict = load_mux_dict(input_mux_file_name, in_tags)

    output_file = MkvFile(
            app.args.output_file or '%s.demux.mkv' % (inputdir.rstrip('/\\'),))

    post_process_subtitles = False
    cmd = ['mkvmerge',
        '-o', output_file.file_name,
        ]
    new_stream_index = -1
    for stream_index, stream_dict in sorted((stream_dict['index'], stream_dict)
                                            for stream_dict in mux_dict['streams']):
        if stream_dict.get('skip', False):
            continue
        stream_codec_type = stream_dict['codec_type']
        if stream_codec_type == 'subtitle':
            post_process_subtitles = True
            continue
        new_stream_index += 1
        stream_dict['index'] = new_stream_index
        if stream_codec_type == 'video':
            display_aspect_ratio = stream_dict.get('display_aspect_ratio', None)
            if display_aspect_ratio:
                cmd += ['--aspect-ratio', '%d:%s' % (0, re.sub(':', '/', display_aspect_ratio))]
        stream_default = stream_dict['disposition'].get('default', None)
        cmd += ['--default-track', '%d:%s' % (0, ('true' if stream_default else 'false'))]
        stream_language = stream_dict.get('language', None)
        if stream_language:
            cmd += ['--language', '0:%s' % (stream_language,)]
        stream_forced = stream_dict['disposition'].get('forced', None)
        cmd += ['--forced-track', '%d:%s' % (0, ('true' if stream_forced else 'false'))]
        # TODO --tags
        if stream_codec_type == 'subtitle' and os.path.splitext(stream_dict['file_name'])[1] == '.sub':
            cmd += [os.path.join(inputdir, '%s.idx' % (os.path.splitext(stream_dict['file_name'])[0],))]
        cmd += [os.path.join(inputdir, stream_dict['file_name'])]
    if mux_dict['chapters']:
        cmd += ['--chapters', os.path.join(inputdir, mux_dict['chapters']['file_name'])]
    with perfcontext('mkvmerge'):
        do_spawn_cmd(cmd)

    if post_process_subtitles:
        num_inputs = 0
        noss_file_name = output_file.file_name + '.noss.mkv'
        if not app.args.dry_run:
            shutil.move(output_file.file_name, noss_file_name)
        num_inputs += 1
        ffmpeg_args = [
            '-i', noss_file_name,
            ]
        option_args = [
            '-map', str(num_inputs-1),
            ]
        for stream_dict in mux_dict['streams']:
            if stream_dict.get('skip', False):
                continue
            stream_index = stream_dict['index']
            stream_codec_type = stream_dict['codec_type']
            if stream_codec_type != 'subtitle':
                continue
            new_stream_index += 1
            stream_dict['index'] = new_stream_index
            num_inputs += 1
            ffmpeg_args += [
                '-i', os.path.join(inputdir, stream_dict['file_name']),
                ]
            option_args += [
                '-map', str(num_inputs-1),
                ]
            stream_default = stream_dict['disposition'].get('default', None)
            if stream_default:
                option_args += ['-disposition:%d' % (new_stream_index,), 'default',]
            stream_language = stream_dict.get('language', None)
            if stream_language:
                #ffmpeg_args += ['--language', '%d:%s' % (track_id, stream_language)]
                option_args += ['-metadata:s:%d' % (new_stream_index,), 'language=%s' % (isolang(stream_language).code3,),]
            stream_forced = stream_dict['disposition'].get('forced', None)
            if stream_forced:
                option_args += ['-disposition:%d' % (new_stream_index,), 'forced',]
            # TODO --tags
        option_args += [
            '-codec', 'copy',
            ]
        ffmpeg_args += option_args
        ffmpeg_args += [
            output_file.file_name,
            ]
        with perfcontext('merge subtitles w/ ffmpeg'):
            ffmpeg(*ffmpeg_args,
                   dry_run=app.args.dry_run,
                   y=app.args.yes)
        if not app.args.dry_run:
            os.unlink(noss_file_name)

    output_file.write_tags(tags=mux_dict['tags'],
            dry_run=app.args.dry_run,
            run_func=do_exec_cmd)
    app.log.info('DONE writing %s', output_file.file_name)

    if app.args.cleanup:
        app.log.info('Cleaning up %s', inputdir)
        shutil.rmtree(inputdir)

    return True

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
