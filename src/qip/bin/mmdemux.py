#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

# Aspect Ratios
###############
# https://blog.ampedsoftware.com/2016/03/17/aspect-ratio-understanding-the-information-and-using-the-filter/
#
# SAR:  Storage Aspect Ratio (W/H ratio of the encoded digital video)
# DAR:  Display Aspect Ratio (W/H ratio of the data as it is supposed to be displayed)
# PAR:  Pixel Aspect Ratio   (W/H ratio of pixels with respect to the original source. Like Sample Aspect ratio but calculated)
# SAR*: Sample Aspect Ratio  (W/H ratio of pixels with respect to the original source. Like Pixel Aspect Ratio but stored within Mpeg4 streams), the "Shape" of the pixels
#       "The stretching factore; How much each stored pixel must be scaled to achieve the desired display aspect ratio"
#
# DAR = PAR * SAR (Display = Pixel(Sample) * Storage)
# SAR = DAR / PAR (Storage = Display / Pixel(Sample))
# PAR = DAR / SAR (Pixel(Sample) = Display / Storage)
# PAR = StorageW / StorageH (Pixel(Sample) = Stored Width / Height)

# PTS: Presentation timestamp
# DTS: Decoding timestamp

# http://ffmpeg-users.933282.n4.nabble.com/What-does-the-output-of-ffmpeg-mean-tbr-tbn-tbc-etc-td941538.html
# tbn = the time base in AVStream that has come from the container
# tbc = the time base in AVCodecContext for the codec used for a particular stream
# tbr = tbr is guessed from the video stream and is the value users want to see when they look for the video frame rate, except sometimes it is twice what one would expect because of field rate versus frame rate.

from decimal import Decimal
from fractions import Fraction
import argparse
import collections
import copy
import decimal
import errno
import functools
import html
import io
import logging
import os
import pexpect
import pprint
import re
import reprlib
import shutil
import subprocess
import sys
import types
import xml.etree.ElementTree as ET
reprlib.aRepr.maxdict = 100

HAVE_PROGRESS_BAR = False
try:
    import progress.bar
    HAVE_PROGRESS_BAR = True
except ImportError:
    pass

from qip import json
from qip.app import app
from qip.exec import *
from qip.ffmpeg import ffmpeg, ffprobe
from qip.mencoder import mencoder
from qip.file import *
from qip.handbrake import *
from qip.isolang import isolang
from qip.mp4 import M4aFile
from qip.mediainfo import *
from qip.matroska import *
from qip.mm import MediaFile, Chapters, FrameRate
from qip.opusenc import opusenc
from qip.perf import perfcontext
from qip.mm import *
from qip.threading import *
from qip.utils import byte_decode, Ratio, round_half_away_from_zero
import qip.mm
import qip.utils

#map_RatioConverter = {
#    Ratio("186:157"):
#    Ratio("279:157"):
#}
#def RatioConverter(ratio)
#    ratio = Ratio(ratio)
#    ratio = map_RatioConverter.get(ratio, ratio)
#    return ratio


# https://www.ffmpeg.org/ffmpeg.html

class FieldOrderUnknownError(NotImplementedError):

    def __init__(self, mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order):
        self.mediainfo_scantype = mediainfo_scantype
        self.mediainfo_scanorder = mediainfo_scanorder
        self.ffprobe_field_order = ffprobe_field_order
        super().__init__((mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order))

common_aspect_ratios = {
    Ratio(4, 3),
    Ratio(16, 9),   # 1.78:1 1920x1080 "FHD"
    Ratio(40, 17),  # 2.35:1 1920x816  "CinemaScope"
    Ratio(12, 5),   # 2.40:1 1920x800  "CinemaScope"
}

def MOD_ROUND(v, m):
    return v if m == 1 else m * ((v + (m >> 1)) // m)

def MOD_DOWN(v, m):
    return m * (v // m)

def MOD_UP(v, m):
    return m * ((v + m - 1) // m)

def isolang_or_None(v):
    return None if v == 'None' else isolang(v)

def analyze_field_order_and_framerate(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict):
    field_order = app.args.force_field_order
    framerate = app.args.force_framerate

    video_frames = []

    if field_order is None:
        with perfcontext('analyze field_order'):

            mediainfo_scantype = mediainfo_track_dict.get('ScanType', None)
            mediainfo_scanorder = mediainfo_track_dict.get('ScanOrder', None)
            ffprobe_field_order = ffprobe_stream_json.get('field_order', 'progressive')
            time_base = Fraction(ffprobe_stream_json['time_base'])

            video_frames = []
            prev_frame = ffprobe.Frame()
            prev_frame.pkt_dts_time = Decimal('0.000000')
            prev_frame.pkt_pts_time = Decimal('0.000000')
            prev_frame.pkt_duration_time = Decimal('0.000000')
            prev_frame.pkt_dts = 0
            prev_frame.pkt_pts = 0
            prev_frame.pkt_duration = 0
            with perfcontext('frames iteration'):
                if HAVE_PROGRESS_BAR:
                    bar = progress.bar.Bar('iterate frames', max=float(app.args.video_analyze_duration))
                for frame in ffprobe.iter_frames(stream_file_name):
                    if frame.media_type != 'video':
                        continue
                    assert frame.stream_index == 0

                    if frame.pkt_pts_time is None:
                        frame.pkt_pts_time = frame.pkt_dts_time
                    if frame.pkt_pts_time is None:
                        frame.pkt_pts_time = prev_frame.pkt_pts_time + prev_frame.pkt_duration_time
                    if frame.pkt_dts_time is None:
                        frame.pkt_dts_time = frame.pkt_pts_time

                    if frame.pkt_pts is None:
                        frame.pkt_pts = frame.pkt_dts
                    if frame.pkt_pts is None:
                        frame.pkt_pts = prev_frame.pkt_pts + prev_frame.pkt_duration
                    if frame.pkt_dts is None:
                        frame.pkt_dts = frame.pkt_pts

                    video_frames.append(frame)
                    if HAVE_PROGRESS_BAR:
                        bar.goto(float(frame.pkt_dts_time))
                    if float(frame.pkt_dts_time) >= app.args.video_analyze_duration:
                        break
                    prev_frame = frame
                #video_frames = sorted(video_frames, key=lambda frame: frame.pkt_pts_time)
                #video_frames = sorted(video_frames, key=lambda frame: frame.coded_picture_number)
                if HAVE_PROGRESS_BAR:
                    bar.finish()

            app.log.debug('Analyzing %d video frames...', len(video_frames))

            video_frames = video_frames[10:]  # Skip first frames; Seen need for 1-9

            # video_frames_by_dts = sorted(video_frames, key=lambda frame: frame.pkt_dts_time)
            # XXXJST:
            # Based on libmediainfo-18.12/Source/MediaInfo/Video/File_Mpegv.cpp
            # though getting the proper TemporalReference is more complex and may
            # be different than pkt_dts_time ordering.
            temporal_string = ''.join([
                ('T' if frame.top_field_first else 'B') + ('3' if frame.repeat_pict else '2')
                for frame in video_frames])
            #app.log.debug('temporal_string: %r', temporal_string)

            if field_order is None and '3' in temporal_string:
                # libmediainfo-18.12/Source/MediaInfo/Video/File_Mpegv.cpp
                for temporal_pattern, result_field_order, result_interlacement, result_framerate_ratio in (
                        ('T2T3B2B3T2T3B2B3', '23pulldown', 'ppf', Ratio(24, 30)),
                        ('B2B3T2T3B2B3T2T3', '23pulldown', 'ppf', Ratio(24, 30)),
                        ('T2T2T2T2T2T2T2T2T2T2T2T3B2B2B2B2B2B2B2B2B2B2B2B3', '222222222223pulldown', 'ppf', Ratio(24, 25)),
                        ('B2B2B2B2B2B2B2B2B2B2B2B3T2T2T2T2T2T2T2T2T2T2T2T3', '222222222223pulldown', 'ppf', Ratio(24, 25)),
                        ):
                    temporal_pattern_offset = temporal_string.find(temporal_pattern)
                    if temporal_pattern_offset == -1:
                        continue
                    found_frame_offset = temporal_pattern_offset // 2
                    found_frame_count = len(temporal_pattern) // 2
                    found_frames = video_frames[found_frame_offset:found_frame_offset + found_frame_count]
                    if app.log.isEnabledFor(logging.DEBUG):
                        app.log.debug('found_frames: \n%s', pprint.pformat(found_frames))
                    field_order = result_field_order
                    interlacement = result_interlacement
                    # framerate = FrameRate(1 / (
                    #     time_base
                    #     * sum(frame.pkt_duration for frame in found_frames)
                    #     / len(found_frames)))
                    #calc_framerate = framerate = FrameRate(1 / (Fraction(
                    #    found_frames[-1].pkt_pts - found_frames[0].pkt_pts
                    #    + found_frames[-1].pkt_duration,
                    #    len(found_frames)) * time_base))
                    #framerate = framerate.round_common()
                    found_pkt_duration_times = [
                            frame.pkt_duration_time
                            for frame in found_frames]
                    found_pkt_duration_times = sorted(found_pkt_duration_times)
                    if found_pkt_duration_times in (
                            sorted([Decimal('0.033000'), Decimal('0.050000')] * 4),
                            sorted([Decimal('0.033367'), Decimal('0.050050')] * 4),
                            ):
                        framerate = FrameRate(24000, 1001)
                    else:
                        raise NotImplementedError(found_pkt_duration_times)
                    app.log.warning('Detected field order is %s at %s (%.3f) fps based on temporal pattern %r', field_order, framerate, framerate, temporal_pattern)
                    assert framerate == FrameRate(24000, 1001)  # Only verified case so far
                    # assert framerate == original_framerate * result_framerate_ratio
                    break

            if field_order is None:
                frame0 = video_frames[0]
                constant_framerate = all(
                        frame.pkt_duration == frame0.pkt_duration
                        for frame in video_frames)
                if constant_framerate:
                    if False:
                        if frame0.pkt_duration_time in (
                                    Decimal('0.033367'),
                                    Decimal('0.033000'),
                                ):
                            framerate = FrameRate(30000, 1001)
                        elif frame0.pkt_duration_time in (
                                    Decimal('0.041000'),
                                ):
                            framerate = FrameRate(24000, 1001)
                        else:
                            raise NotImplementedError(frame0.pkt_duration_time)
                    elif False:
                        pts_sum = sum(
                            frameB.pkt_pts - frameA.pkt_pts
                            for frameA, frameB in zip(video_frames[0:-2], video_frames[1:-1]))  # Last frame may not have either dts and pts
                        framerate = FrameRate(1 / (time_base * pts_sum / (len(video_frames) - 2)), 1)
                        app.log.debug('framerate = 1 / (%r * %r / (%r - 2)) = %r = %r', time_base, pts_sum, len(video_frames), framerate, float(framerate))
                        # framerate = FrameRate(1 / (frame0.pkt_duration * time_base))
                        framerate = framerate.round_common()
                        app.log.debug('framerate.round_common() = %r = %r', framerate, float(framerate))
                    else:
                        assert len(video_frames) > 1000  # To make sure there's enough precision
                        pts_diff = (
                            video_frames[-2].pkt_pts  # Last frame may not have either dts and pts
                            - video_frames[0].pkt_pts)
                        framerate = FrameRate(1 / (time_base * pts_diff / (len(video_frames) - 2)), 1)
                        app.log.debug('framerate = 1 / (%r * %r) / (%r - 2) = %r = %r', time_base, pts_diff, len(video_frames), framerate, float(framerate))
                        framerate = framerate.round_common()
                        app.log.debug('framerate.round_common() = %r = %r', framerate, float(framerate))

                    app.log.debug('Constant %s (%.3f) fps found...', framerate, framerate)
                    all_same_interlaced_frame = all(
                            frame.interlaced_frame == frame0.interlaced_frame
                            for frame in video_frames)
                    if all_same_interlaced_frame:
                        if frame0.interlaced_frame:
                            all_same_top_field_first = all(
                                    frame.top_field_first == frame0.top_field_first
                                    for frame in video_frames)
                            if all_same_top_field_first:
                                if frame0.top_field_first:
                                    field_order = 'tt'
                                    app.log.warning('Detected field order is %s at %s (%.3f) fps', field_order, framerate, framerate)
                                else:
                                    field_order = 'bb'
                                    app.log.warning('Detected field order is %s at %s (%.3f) fps', field_order, framerate, framerate)
                            else:
                                raise NotImplementedError('Mix of top field first and bottom field first Interlaced frames detected')
                        else:
                            field_order = 'progressive'
                            app.log.warning('Detected field order is %s at %s (%.3f) fps', field_order, framerate, framerate)
                    else:
                        app.log.debug('Mix of interlaced and non-interlaced frames found.')
                    assert framerate == pick_framerate(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict, field_order=field_order)
                else:
                    app.log.debug('Variable fps found.')

            if False and field_order is None:
                for time_long, time_short, result_framerate in (
                        (Decimal('0.050050'), Decimal('0.033367'), FrameRate(24000, 1001)),
                        (Decimal('0.050000'), Decimal('0.033000'), FrameRate(24000, 1001)),
                ):
                    i = 0
                    while i < len(video_frames) and video_frames[i].pkt_duration_time == time_short:
                        i += 1
                    for c in range(3):
                        if i < len(video_frames) and video_frames[i].pkt_duration_time == time_long:
                            i += 1
                    while i < len(video_frames) and video_frames[i].pkt_duration_time == time_short:
                        i += 1
                    # pts_time=1.668333 duration_time=0.050050
                    # pts_time=N/A      duration_time=0.050050
                    # pts_time=1.751750 duration_time=0.050050
                    # pts_time=1.801800 duration_time=0.033367
                    # pts_time=N/A      duration_time=0.033367
                    # pts_time=1.885217 duration_time=0.033367
                    is_pulldown = None
                    duration_time_pattern1 = (
                        time_long, time_long, time_long,
                        time_short, time_short, time_short,
                    )
                    duration_time_pattern2 = (
                        time_long, time_short,
                        time_long, time_short,
                        time_long, time_short,
                    )
                    while i < len(video_frames) - 6:
                        duration_time_found = (
                            video_frames[i+0].pkt_duration_time,
                            video_frames[i+1].pkt_duration_time,
                            video_frames[i+2].pkt_duration_time,
                            video_frames[i+3].pkt_duration_time,
                            video_frames[i+4].pkt_duration_time,
                            video_frames[i+5].pkt_duration_time,
                        )
                        if (
                                duration_time_found == duration_time_pattern1
                                or duration_time_found == duration_time_pattern2
                        ):
                            is_pulldown = True
                        else:
                            is_pulldown = False
                            app.log.debug('not 23pulldown @ frame %d: %r', i, duration_time_found)
                            break
                        i += 6
                    if is_pulldown:
                        field_order = '23pulldown'
                        framerate = result_framerate
                        app.log.warning('Detected field order is %s at %s fps', field_order, framerate)
                        break

            if False and field_order is None:
                #for i in range(0, len(video_frames)):
                #    print('pkt_duration_time=%r, interlaced_frame=%r' % (video_frames[i].pkt_duration_time, video_frames[i].interlaced_frame))
                # pkt_duration_time=0.033000|interlaced_frame=1|top_field_first=1 = tt @ 30000/1001 ?
                # pkt_duration_time=0.041000|interlaced_frame=0|top_field_first=0 = progressive @ 24000/1001 ?
                field_order = pick_field_order(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict)

    if field_order is None:
        raise NotImplementedError('field_order unknown')

    if framerate is None:
        framerate = pick_framerate(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict, field_order=field_order)

    return field_order, framerate

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
    pgroup.add_argument('--save-temps', dest='save_temps', default=True, action='store_true', help='do not delete intermediate files')
    pgroup.add_argument('--no-save-temps', dest='save_temps', default=argparse.SUPPRESS, action='store_true', help='do not delete intermediate files')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')
    pgroup.add_argument('--continue', dest='_continue', action='store_true', help='continue mode')
    pgroup.add_argument('--batch', '-B', action='store_true', help='batch mode')
    pgroup.add_argument('--step', action='store_true', help='step mode')

    pgroup = app.parser.add_argument_group('Tools Control')
    pgroup.add_argument('--track-extract-tool', dest='track_extract_tool', default=None, choices=('ffmpeg', 'mkvextract'), help='tool to extract tracks')

    pgroup = app.parser.add_argument_group('Ripping Control')
    pgroup.add_argument('--device', default=os.environ.get('CDROM', '/dev/cdrom'), help='specify alternate cdrom device')
    pgroup.add_argument('--minlength', default=None, type=qip.utils.Timestamp, help='minimum title length for ripping (default 60m (movie), 20m (tvshow))')

    pgroup = app.parser.add_argument_group('Video Control')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--crop', default=None, action='store_true', help='enable cropping video (default)')
    xgroup.add_argument('--no-crop', dest='crop', default=argparse.SUPPRESS, action='store_false', help='disable cropping video')
    xgroup.add_argument('--crop-wh', dest="crop_wh", default=None, type=int, nargs=2, help='force cropping dimensions (centered)')
    xgroup.add_argument('--crop-whlt', dest="crop_whlt", default=None, type=int, nargs=4, help='force cropping dimensions')
    pgroup.add_argument('--parallel-chapters', dest='parallel_chapters', default=False, action='store_true', help='enable per-chapter parallel processing (default)')
    pgroup.add_argument('--no-parallel-chapters', dest='parallel_chapters', default=argparse.SUPPRESS, action='store_false', help='disable per-chapter parallel processing')
    pgroup.add_argument('--cropdetect-duration', dest='cropdetect_duration', type=qip.utils.Timestamp, default=qip.utils.Timestamp(300), help='cropdetect duration (seconds)')
    pgroup.add_argument('--video-language', '--vlang', dest='video_language', type=isolang_or_None, default=isolang('und'), help='Override video language (mux)')
    pgroup.add_argument('--video-rate-control-mode', dest='video_rate_control_mode', default='CQ', choices=('Q', 'CQ', 'CBR', 'VBR', 'lossless'), help='Rate control mode: Constant Quality (Q), Constrained Quality (CQ), Constant Bit Rate (CBR), Variable Bit Rate (VBR), lossless')
    pgroup.add_argument('--force-framerate', dest='force_framerate', default=None, type=FrameRate, help='Ignore heuristics and force framerate')
    pgroup.add_argument('--force-field-order', dest='force_field_order', default=None, choices=('progressive', 'tt', 'tb', 'bb', 'bt', '23pulldown'), help='Ignore heuristics and force input field order')
    pgroup.add_argument('--video-analyze-duration', dest='video_analyze_duration', type=qip.utils.Timestamp, default=qip.utils.Timestamp(60), help='video analysis duration (seconds)')

    pgroup = app.parser.add_argument_group('Subtitle Control')
    pgroup.add_argument('--subrip-matrix', dest='subrip_matrix', default=None, help='SubRip OCR matrix file')
    pgroup.add_argument('--external-subtitles', dest='external_subtitles', action='store_true', help='Keep unoptimized subtitles as external files')

    pgroup = app.parser.add_argument_group('Files')
    pgroup.add_argument('--output', '-o', dest='output_file', default=None, help='specify the output (demuxed) file name')

    pgroup = app.parser.add_argument_group('Compatibility')
    xgroup.add_argument('--webm', default=True, action='store_true', help='enable webm output format (default)')
    xgroup.add_argument('--no-webm', dest='webm', default=argparse.SUPPRESS, action='store_false', help='disable webm output format (plain Matroska)')

    pgroup = app.parser.add_argument_group('Encoding')
    pgroup.add_argument('--keyint', type=int, default=5, help='keyframe interval (seconds)')

    pgroup = app.parser.add_argument_group('Tags')
    pgroup.add_argument('--grouping', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--albumartist', '-R', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--albumtitle', '--album', '-A', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--artist', '-a', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--title', '--song', '-s', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--subtitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--genre', '-g', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--writer', '--composer', '-w', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--date', '--year', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--type', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--mediatype', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction, help='Physical Media Type (%s)' % (', '.join((str(e) for e in qip.mm.MediaType)),))
    pgroup.add_argument('--contenttype', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction, help='Content Type (%s)' % (', '.join((str(e) for e in qip.mm.ContentType)),))
    pgroup.add_argument('--disk', '--disc', dest='disk_slash_disks', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--track', dest='track_slash_tracks', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--picture', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--tvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--season', dest='season_slash_seasons', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--episode', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--language', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--country', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--compilation', '-K', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-artist', dest='sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-title', '--sort-song', dest='sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumartist', dest='sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumtitle', '--sort-album', dest='sortalbumtitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-composer', '--sort-writer', dest='sortcomposer', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-tvshow', dest='sorttvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)

    pgroup = app.parser.add_argument_group('Options')
    pgroup.add_argument('--eject', default=False, action='store_true', help='eject cdrom when done')
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

    if in_tags.type is None:
        try:
            in_tags.type = in_tags.deduce_type()
        except qip.mm.MissingMediaTagError:
            pass

    # if getattr(app.args, 'action', None) is None:
    #     app.args.action = TODO
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    did_something = False
    if app.args.rip_dir:
        action_rip(app.args.rip_dir, app.args.device, in_tags=in_tags)
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

def get_codec_encoding_delay(file_name, *, mediainfo_track_dict=None, ffprobe_stream_dict=None):
    if mediainfo_track_dict:
        if mediainfo_track_dict['Format'] == 'Opus':
            # default encoding delay of 312 samples
            return ffmpeg.Timestamp(Fraction(1, int(mediainfo_track_dict['SamplingRate'])) * 312)
        return 0
    if ffprobe_stream_dict:
        if ffprobe_stream_dict['codec_name'] == 'opus':
            # default encoding delay of 312 samples
            return ffmpeg.Timestamp(Fraction(1, int(ffprobe_stream_dict['sample_rate'])) * 312)
        return 0
    file_ext = my_splitext(file_name)[1]
    if file_ext in (
            '.y4m',
            '.mpeg2.mp2v',
            '.mjpeg',
            '.msmpeg4v3.avi',
            '.mp4',
            '.vc1',
            '.h264',
            '.h265',
            '.vp8',
            '.vp8.ivf',
            '.vp9',
            '.vp9.ivf',
            '.ac3',
            '.mp3',
            '.dts',
            '.aac',
            '.wav',
            '.sub',
            '.sup',
            '.srt',
            '.vtt',
    ):
        return 0
    mediainfo_dict = MediaFile.new_by_file_name(file_name).extract_mediainfo_dict()
    assert len(mediainfo_dict['media']['track']) == 2
    mediainfo_track_dict = mediainfo_dict['media']['track'][1]
    return get_codec_encoding_delay(file_name, mediainfo_track_dict=mediainfo_track_dict)

def codec_name_to_ext(codec_name):
    try:
        codec_ext = {
            # video
            'rawvideo': '.y4m',
            'mpeg2video': '.mpeg2.mp2v',
            'mp2': '.mpeg2.mp2v',
            #'mjpeg': '.mjpeg',
            'msmpeg4v3': '.msmpeg4v3.avi',
            'mpeg4': '.mp4',
            'vc1': '.vc1',
            'h264': '.h264',
            'h265': '.h265',
            'vp8': '.vp8.ivf',
            'vp9': '.vp9.ivf',
            # audio
            'ac3': '.ac3',
            'mp3': '.mp3',
            'dts': '.dts',
            'opus': '.opus.ogg',
            'aac': '.aac',
            'pcm_s16le': '.wav',
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
    ext = os.path.splitext('x' + ext)[1]
    try:
        ext_container = {
            '.mkv': 'matroska',
            '.webm': 'webm',
            # video
            '.y4m': 'yuv4mpegpipe',
            '.mpeg2': 'mpeg2video',
            '.mp2v': 'mpeg2video',
            '.mpegts': 'mpegts',
            '.h264': 'h264',  # raw H.264 video
            #'.h265': 'h265',
            '.vp8': 'ivf',
            '.vp9': 'ivf',
            '.ivf': 'ivf',
            # audio
            #'.ac3': 'ac3',
            #'.dts': 'dts',
            '.opus': 'ogg',
            '.ogg': 'ogg',
            '.mka': 'matroska',
            #'.aac': 'aac',
            '.wav': 'wav',
            # subtitles
            'sub': 'vobsub',
            #'.idx': 'dvd_subtitle',
            #'.sup': 'hdmv_pgs_subtitle',
            '.vtt': 'webvtt',
        }[ext]
    except KeyError as err:
        raise ValueError('Unsupported extension %r' % (ext,)) from err
    return ext_container

def ext_to_mencoder_libavcodec_format(ext):
    ext = os.path.splitext('x' + ext)[1]
    try:
        libavcodec_format = {
            # video
            '.avi': 'avi',
            '.mkv': 'matroska',
        }[ext]
    except KeyError as err:
        raise ValueError('Unsupported extension %r' % (ext,)) from err
    return libavcodec_format

def get_vp9_target_bitrate(width, height, frame_rate, mq=True):
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

def get_vp9_target_quality(width, height, frame_rate, mq=True):  # CQ
    # https://developers.google.com/media/vp9/settings/vod/
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
            return 33 if mq else 34
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

def init_inputfile_tags(inputfile, in_tags, ffprobe_dict=None, mediainfo_dict=None):

    inputfile_base, inputfile_ext = my_splitext(inputfile.file_name)

    name_scan_str = os.path.basename(inputfile_base)
    name_scan_str = re.sub(r'_t\d+$', '', name_scan_str)
    m = (
            re.match(r'^(?P<tvshow>.+) S(?P<season>\d\d)(?P<str_episodes>(?:E\d\d)+) (?P<title>.+)$', name_scan_str)
         or re.match(r'^(?P<title>.+)$', name_scan_str)
        )
    if m:
        d = m.groupdict()
        if d.get('title', None) == 'title':
            del d['title']
        try:
            str_episodes = d.pop('str_episodes')
        except KeyError:
            pass
        else:
            d['episode'] = [int(e) for e in str_episodes.split('E') if e]
        inputfile.tags.update(d)

    if inputfile.exists():
        inputfile.tags.update(inputfile.load_tags())
        if inputfile_ext in (
                '.mkv',
                '.webm',
                ):
            if mediainfo_dict is None:
                mediainfo_dict = inputfile.extract_mediainfo_dict()
            mediainfo_track_dict, = (mediainfo_track_dict
                    for mediainfo_track_dict in mediainfo_dict['media']['track']
                    if mediainfo_track_dict['@type'] == 'Video') or ({},)
            mediainfo_mediatype = mediainfo_track_dict.get('OriginalSourceMedium', None)
            if mediainfo_mediatype is None:
                pass
            elif mediainfo_mediatype == 'DVD-Video':
                inputfile.tags.mediatype = 'DVD'
            elif mediainfo_mediatype == 'Blu-ray':
                inputfile.tags.mediatype = 'BD'
            else:
                raise NotImplementedError(mediainfo_mediatype)

    inputfile.tags.pop('type', None)
    inputfile.tags.update(in_tags)
    inputfile.tags.type = inputfile.deduce_type()

def do_edit_tags(tags):

    # for tag in set(MediaTagEnum) - set(MediaTagEnum.iTunesInternalTags):
    for tag in (
            MediaTagEnum.grouping,
            MediaTagEnum.artist,
            MediaTagEnum.contenttype,
            MediaTagEnum.episode,
            MediaTagEnum.genre,
            MediaTagEnum.mediatype,
            MediaTagEnum.season,
            MediaTagEnum.subtitle,
            MediaTagEnum.title,
            MediaTagEnum.tvshow,
            MediaTagEnum.year,
        ):
        # Force None values to actually exist
        if tags[tag] is None:
            tags[tag] = None
    tags = edvar(tags)[1]
    for tag, value in tags.items():
        if value is None:
            del tags[tag]
    return tags

def action_rip(rip_dir, device, in_tags):
    device = os.path.realpath(device)  # makemkv is picky!

    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(['mkdir', rip_dir]))
    else:
        os.mkdir(rip_dir)

    minlength = app.args.minlength
    if minlength is None:
        if in_tags.type == 'tvshow':
            minlength = qip.utils.Timestamp('20m')
        else:
            minlength = qip.utils.Timestamp('60m')

    from qip.makemkv import makemkvcon
    try:
        makemkvcon.mkv(
            source='dev:%s' % (device,),
            dest_dir=rip_dir,
            minlength=int(minlength),
        )
    except:
        if app.args.dry_run:
            app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(['rmdir', rip_dir]))
        else:
            try:
                os.rmdir(rip_dir)
            except OSError:
                pass
        raise

    if app.args.eject:
        app.log.info('Ejecting...')
        cmd = [
            shutil.which('eject'),
            device,
        ]
        out = do_spawn_cmd(cmd)

    if app.args.chain:
        with os.scandir(rip_dir) as it:
            for entry in it:
                assert os.path.splitext(entry.name)[1] in ('.mkv', '.webm')
                assert entry.is_file()
                app.args.mux_files += (os.path.join(rip_dir, entry.name),)

def pick_field_order(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict):
    if app.args.force_field_order is not None:
        return app.args.force_field_order

    mediainfo_scantype = mediainfo_track_dict.get('ScanType', None)
    mediainfo_scanorder = mediainfo_track_dict.get('ScanOrder', None)
    ffprobe_field_order = ffprobe_stream_json.get('field_order', 'progressive')

    if mediainfo_scanorder is None:
        stream_file_base, stream_file_ext = my_splitext(stream_file_name)
        if '23pulldown' in stream_file_base.split('.'):
            mediainfo_scanorder = '2:3 Pulldown'

    if (mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order) in(
            (None, None, 'progressive'),
            ('Progressive', None, 'progressive'),
    ):
        return ffprobe_field_order

    elif (mediainfo_scantype, mediainfo_scanorder) == ('Interlaced', 'Top Field First'):
        assert ffprobe_field_order in ('tt', 'tb'), (mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order)
        # ‘tt’ Interlaced video, top field coded and displayed first
        # ‘tb’ Interlaced video, top coded first, bottom displayed first
        # https://ffmpeg.org/ffmpeg-filters.html#yadif
        return ffprobe_field_order

    elif (mediainfo_scantype, mediainfo_scanorder) == ('Interlaced', 'Bottom Field First'):
        assert ffprobe_field_order in ('bb', 'bt'), (mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order)
        # ‘bb’ Interlaced video, bottom field coded and displayed first
        # ‘bt’ Interlaced video, bottom coded first, top displayed first
        # https://ffmpeg.org/ffmpeg-filters.html#yadif
        return ffprobe_field_order

    elif (mediainfo_scantype, mediainfo_scanorder) == ('Progressive', '2:3 Pulldown'):
        assert ffprobe_field_order == 'progressive', (mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order)
        return '23pulldown'

    else:
        raise FieldOrderUnknownError(mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order)


def pick_framerate(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict, *, field_order=None):
    if app.args.force_framerate is not None:
        return app.args.force_framerate

    ffprobe_r_framerate = FrameRate(ffprobe_stream_json['r_frame_rate'])
    ffprobe_avg_framerate = FrameRate(ffprobe_stream_json['avg_frame_rate'])
    mediainfo_format = mediainfo_track_dict['Format']
    mediainfo_framerate = FrameRate(mediainfo_track_dict['FrameRate'])
    mediainfo_original_framerate = mediainfo_track_dict.get('OriginalFrameRate', None)
    if mediainfo_original_framerate is not None:
        mediainfo_original_framerate = FrameRate(mediainfo_original_framerate)

    try:
        field_order = field_order or pick_field_order(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict)
    except FieldOrderUnknownError:
        field_order = None

    mediainfo_scantype = mediainfo_track_dict.get('ScanType', None)
    mediainfo_scanorder = mediainfo_track_dict.get('ScanOrder', None)
    ffprobe_field_order = ffprobe_stream_json.get('field_order', 'progressive')

    #if mediainfo_scanorder is None:
    #    stream_file_base, stream_file_ext = my_splitext(stream_file_name)
    #    if '23pulldown' in stream_file_base.split('.'):
    #        mediainfo_scanorder = '2:3 Pulldown'

    if (
            ffprobe_r_framerate == FrameRate(60000, 1001)
            and (26.75 <= ffprobe_avg_framerate <= 31.0)
            and mediainfo_format == 'MPEG Video'
            and field_order == '23pulldown'
            and mediainfo_framerate == FrameRate(24000, 1001)):
        # Common 2:3 Pulldown cases; mediainfo is right.
        return mediainfo_framerate

    assert (
        ffprobe_r_framerate == ffprobe_avg_framerate
        or ffprobe_r_framerate == ffprobe_avg_framerate * 2), \
        (ffprobe_r_framerate, ffprobe_avg_framerate, mediainfo_framerate, mediainfo_original_framerate)
    framerate = ffprobe_avg_framerate

    if mediainfo_format in ('FFV1',):
        # mediainfo's ffv1 framerate is all over the place (24 instead of 23.976 for .ffv1.mkv and total number of frames for .ffv1.avi)
        pass
    else:
        assert mediainfo_original_framerate is None \
            or mediainfo_framerate == mediainfo_original_framerate, \
            (ffprobe_r_framerate, ffprobe_avg_framerate, mediainfo_framerate, mediainfo_original_framerate)
        if framerate != mediainfo_framerate:
            if field_order == 'progressive':
                pass
            elif field_order == '23pulldown':
                assert (mediainfo_scantype, mediainfo_scanorder) == ('Progressive', '2:3 Pulldown')
                # Rely on mediainfo's framerate
                return mediainfo_framerate
            else:
                raise ValueError('Inconsistent %s framerate: %s vs mediainfo=%s' % (field_order, framerate, mediainfo_framerate))
    return framerate

def action_hb(inputfile, in_tags):
    app.log.info('HandBrake %s...', inputfile)
    inputfile = SoundFile.new_by_file_name(inputfile)
    inputfile_base, inputfile_ext = my_splitext(inputfile.file_name)
    outputfile_name = "%s.hb.mkv" % (inputfile_base,)
    if app.args.chain:
        app.args.mux_files += (outputfile_name,)

    if inputfile_ext in (
            '.mkv',
            '.webm',
            '.mpeg2',
            '.mpeg2.mp2v',
            ):
        ffprobe_dict = inputfile.extract_ffprobe_json()

        for stream_dict in ffprobe_dict['streams']:
            if stream_dict.get('skip', False):
                continue
            stream_codec_type = stream_dict['codec_type']
            if stream_codec_type == 'video':
                break
        else:
            raise ValueError('No video stream found!')

        mediainfo_dict = inputfile.extract_mediainfo_dict()
        assert len(mediainfo_dict['media']['track']) >= 2
        mediainfo_track_dict = mediainfo_dict['media']['track'][1]
        assert mediainfo_track_dict['@type'] == 'Video'

        #framerate = pick_framerate(inputfile.file_name, ffprobe_dict, stream_dict, mediainfo_track_dict)
        field_order, framerate = analyze_field_order_and_framerate(
            inputfile.file_name,
            ffprobe_dict, stream_dict, mediainfo_track_dict)

        video_target_bit_rate = get_vp9_target_bitrate(
            width=stream_dict['width'],
            height=stream_dict['height'],
            frame_rate=framerate,
            )
        video_target_quality = get_vp9_target_quality(
            width=stream_dict['width'],
            height=stream_dict['height'],
            frame_rate=framerate,
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
                   scan=True if app.args.dry_run else False,
                   json=True if app.args.dry_run else False,
                   dry_run=False,
                )

    else:
        raise ValueError('Unsupported extension %r' % (inputfile_ext,))

def action_mux(inputfile, in_tags):
    app.log.info('Muxing %s...', inputfile)
    inputfile = SoundFile.new_by_file_name(inputfile)
    inputfile_base, inputfile_ext = my_splitext(inputfile.file_name)
    outputdir = app.args.project or "%s" % (inputfile_base,)
    if app.args.chain:
        app.args.optimize_dirs += (outputdir,)

    if os.path.isdir(outputdir):
        if app.args._continue:
            app.log.warning('Directory exists: %r: ignoring', outputdir)
            return True
        raise OSError(errno.EEXIST, outputdir)

    mux_dict = {
        'streams': [],
        'chapters': {},
        #'tags': ...,
    }

    ffprobe_dict = None
    mediainfo_dict = None
    if inputfile_ext in (
            '.mkv',
            '.webm',
            ):
        ffprobe_dict = inputfile.extract_ffprobe_json()
        mediainfo_dict = inputfile.extract_mediainfo_dict()

    init_inputfile_tags(inputfile,
                        in_tags=in_tags,
                        ffprobe_dict=ffprobe_dict,
                        mediainfo_dict=mediainfo_dict)
    mux_dict['tags'] = inputfile.tags

    if app.args.interactive and not (app.args.rip_dir and outputdir in app.args.rip_dir):
        mux_dict['tags'] = do_edit_tags(mux_dict['tags'])

    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(['mkdir', outputdir]))
    else:
        os.mkdir(outputdir)

    if inputfile_ext in (
            '.mkv',
            '.webm',
            ):

        has_forced_subtitle = False
        subtitle_counts = []

        iter_frames = None
        first_pts_time_per_stream = {}

        mkvextract_tracks_args = []
        mkvextract_attachments_args = []

        attachment_index = 0  # First attachment is index 1
        for stream_dict in ffprobe_dict['streams']:
            stream_out_dict = {}
            stream_index = stream_out_dict['index'] = int(stream_dict['index'])
            stream_codec_type = stream_out_dict['codec_type'] = stream_dict['codec_type']

            if stream_codec_type in ('video', 'audio', 'subtitle'):
                stream_codec_name = stream_dict['codec_name']
                if (
                        stream_codec_type == 'video'
                        and stream_codec_name == 'mjpeg'
                        and stream_dict.get('tags', {}).get('mimetype', None) == 'image/jpeg'):
                    stream_codec_type = stream_out_dict['codec_type'] = 'image'
                    stream_file_ext = '.jpg'
                    stream_out_dict['attachment_type'] = my_splitext(stream_dict['tags']['filename'])[0]
                else:
                    stream_file_ext = codec_name_to_ext(stream_codec_name)

                if stream_codec_type == 'video':
                    if app.args.video_language:
                        stream_dict.setdefault('tags', {})
                        stream_dict['tags']['language'] = app.args.video_language.code3
                    # stream_out_dict['pixel_aspect_ratio'] = stream_dict['pixel_aspect_ratio']
                    # stream_out_dict['display_aspect_ratio'] = stream_dict['display_aspect_ratio']

                stream_time_base = Fraction(stream_dict['time_base'])

                stream_start_time = ffmpeg.Timestamp(stream_dict['start_time'])
                codec_encoding_delay = get_codec_encoding_delay(inputfile, ffprobe_stream_dict=stream_dict)
                if stream_start_time < 0 \
                        and stream_start_time == (stream_time_base * round_half_away_from_zero(-codec_encoding_delay / stream_time_base)):
                    stream_start_time = ffmpeg.Timestamp(0)
                else:
                    stream_start_time += codec_encoding_delay
                if stream_start_time and stream_codec_type == 'video':
                    if stream_index not in first_pts_time_per_stream:
                        if iter_frames is None:
                            iter_frames = ffprobe.iter_frames(inputfile)
                        for frame in iter_frames:
                            if frame.stream_index in first_pts_time_per_stream:
                                continue
                            if frame.pkt_pts_time is None:
                                continue
                            first_pts_time_per_stream[frame.stream_index] = frame.pkt_pts_time
                            if frame.stream_index == stream_index:
                                break
                    if first_pts_time_per_stream[stream_index] == 0.0:
                        app.log.warning('Correcting %s stream #%d start time %s to 0 based on first frame PTS', stream_codec_type, stream_index, stream_start_time)
                        stream_start_time = ffmpeg.Timestamp(0)
                if stream_start_time and stream_codec_type == 'subtitle':
                    # ffmpeg estimates the start_time if it is low enough but the actual time indices will be correct
                    app.log.warning('Correcting %s stream #%d start time %s to 0 based on experience', stream_codec_type, stream_index, stream_start_time)
                    stream_start_time = ffmpeg.Timestamp(0)
                if stream_start_time:
                    app.log.warning('%s stream #%d start time is %s', stream_codec_type.title(), stream_index, stream_start_time)
                stream_out_dict['start_time'] = str(stream_start_time)

                stream_disposition_dict = stream_out_dict['disposition'] = stream_dict['disposition']

                try:
                    stream_title = stream_out_dict['title'] = stream_dict['tags']['title']
                except KeyError:
                    pass

                try:
                    stream_language = stream_dict['tags']['language']
                except KeyError:
                    stream_language = None
                else:
                    stream_language = isolang(stream_language)
                    if stream_language is isolang('und'):
                        stream_language = None
                if stream_language:
                    stream_out_dict['language'] = str(stream_language)

                stream_file_name_language_suffix = '.%s' % (stream_language,) if stream_language is not None else ''
                if stream_disposition_dict['attached_pic']:
                    attachment_index += 1
                    output_track_file_name = 'attachment-%02d-%s%s%s' % (
                            attachment_index,
                            stream_codec_type,
                            stream_file_name_language_suffix,
                            stream_file_ext,
                            )
                else:
                    output_track_file_name = 'track-%02d-%s%s%s' % (
                            stream_index,
                            stream_codec_type,
                            stream_file_name_language_suffix,
                            stream_file_ext,
                            )
                stream_out_dict['file_name'] = output_track_file_name

                if stream_file_ext == '.vtt':
                    app.log.info('Extract %s stream %d: %s', stream_codec_type, stream_index, output_track_file_name)
                    # Avoid mkvextract error: Extraction of track ID 3 with the CodecID 'D_WEBVTT/SUBTITLES' is not supported.
                    # (mkvextract expects S_TEXT/WEBVTT)
                    with perfcontext('extract track %d w/ ffmpeg' % (stream_index,)):
                        ffmpeg_args = [
                            '-i', inputfile.file_name,
                            '-map_metadata', '-1',
                            '-map_chapters', '-1',
                            '-map', '0:%d' % (stream_index,),
                            '-codec', 'copy',
                            os.path.join(outputdir, output_track_file_name),
                            ]
                        ffmpeg(*ffmpeg_args,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                elif stream_disposition_dict['attached_pic']:
                    app.log.info('Will extract %s stream %d w/ mkvextract: %s', stream_codec_type, stream_index, output_track_file_name)
                    mkvextract_attachments_args += [
                        '%d:%s' % (
                            attachment_index,
                            os.path.join(outputdir, output_track_file_name),
                        )]
                elif app.args.track_extract_tool == 'ffmpeg' \
                    or (app.args.track_extract_tool is None
                        and stream_codec_name in (
                            'vp8',
                            'vp9',
                        )):
                    # For some codecs, mkvextract is not reliable and may encode the wrong frame rate; Use ffmpeg.
                    app.log.info('Extract %s stream %d: %s', stream_codec_type, stream_index, output_track_file_name)
                    with perfcontext('extract track %d w/ ffmpeg' % (stream_index,)):
                        force_format = None
                        try:
                            force_format = ext_to_container(stream_file_ext)
                        except ValueError:
                            pass
                        ffmpeg_args = [
                            '-i', inputfile.file_name,
                            '-map_metadata', '-1',
                            '-map_chapters', '-1',
                            '-map', '0:%d' % (stream_index,),
                            '-codec', 'copy',
                            '-start_at_zero',
                            ]
                        if force_format:
                            ffmpeg_args += [
                                '-f', force_format,
                                ]
                        ffmpeg_args += [
                            os.path.join(outputdir, output_track_file_name),
                            ]
                        ffmpeg(*ffmpeg_args,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                elif app.args.track_extract_tool in ('mkvextract', None):
                    app.log.info('Will extract %s stream %d w/ mkvextract: %s', stream_codec_type, stream_index, output_track_file_name)
                    mkvextract_tracks_args += [
                        '%d:%s' % (
                            stream_index,
                            os.path.join(outputdir, output_track_file_name),
                        )]
                    # raise NotImplementedError('extracted tracks from mkvextract must be reset to start at 0 PTS')
                else:
                    raise NotImplementedError('unsupported track extract tool: %r' % (app.args.track_extract_tool,))

                mux_dict['streams'].append(stream_out_dict)
            else:
                raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

        if mkvextract_tracks_args:
            with perfcontext('extract tracks w/ mkvextract'):
                cmd = [
                    'mkvextract', 'tracks', inputfile.file_name,
                    ] + mkvextract_tracks_args
                do_spawn_cmd(cmd)
        if mkvextract_attachments_args:
            with perfcontext('extract attachments w/ mkvextract'):
                cmd = [
                    'mkvextract', 'attachments', inputfile.file_name,
                    ] + mkvextract_attachments_args

        # Pre-stream post-processing
        if not app.args.dry_run:

            for stream_dict in mux_dict['streams']:
                if stream_dict.get('skip', False):
                    continue
                stream_index = stream_dict['index']
                stream_codec_type = stream_dict['codec_type']
                stream_file_name = stream_dict['file_name']
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                stream_disposition_dict = stream_dict['disposition']

                if stream_codec_type == 'video':
                    mediainfo_track_dict, = (mediainfo_track_dict
                            for mediainfo_track_dict in mediainfo_dict['media']['track']
                            if int(mediainfo_track_dict.get('ID', 0)) == stream_index + 1)
                    assert mediainfo_track_dict['@type'] == 'Video'
                    storage_aspect_ratio = Ratio(mediainfo_track_dict['Width'], mediainfo_track_dict['Height'])
                    display_aspect_ratio = Ratio(mediainfo_track_dict['DisplayAspectRatio'])
                    pixel_aspect_ratio = display_aspect_ratio / storage_aspect_ratio
                    stream_dict['display_aspect_ratio'] = str(display_aspect_ratio)
                    stream_dict['pixel_aspect_ratio'] = str(pixel_aspect_ratio)  # invariable

                elif stream_codec_type == 'subtitle':
                    stream_forced = stream_disposition_dict.get('forced', None)
                    if stream_forced:
                        has_forced_subtitle = True
                    if stream_file_ext in ('.sub', '.sup'):
                        d = ffprobe(i=os.path.join(outputdir, stream_file_name), show_frames=True)
                        out = d.out
                        subtitle_count = out.count(
                            b'[SUBTITLE]' if type(out) is bytes else '[SUBTITLE]')
                        if stream_file_ext in ('.sup',):
                            # TODO count only those frames with num_rect != 0
                            subtitle_count = subtitle_count // 2
                    elif stream_file_ext in ('.idx',):
                        out = open(os.path.join(outputdir, stream_file_name), 'rb').read()
                        subtitle_count = out.count(b'timestamp:')
                    elif stream_file_ext in ('.srt', '.vtt'):
                        out = open(os.path.join(outputdir, stream_file_name), 'rb').read()
                        subtitle_count = out.count(b'\n\n') + out.count(b'\n\r\n')
                    else:
                        raise NotImplementedError(stream_file_ext)
                    stream_dict['subtitle_count'] = subtitle_count
                    if not subtitle_count:
                        app.log.warning('Detected empty subtitle stream #%d (%s); Skipping.',
                                        stream_index,
                                        stream_dict.get('language', 'und'))
                        stream_dict['skip'] = True
                    subtitle_counts.append(
                        (stream_dict, subtitle_count))

        if not has_forced_subtitle and subtitle_counts:
            max_subtitle_size = max(subtitle_count
                                    for stream_dict, subtitle_count in subtitle_counts)
            for stream_dict, subtitle_count in subtitle_counts:
                stream_index = stream_dict['index']
                if subtitle_count <= 0.10 * max_subtitle_size:
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
                chapters_out = do_exec_cmd(cmd,
                                  log_append=' > %s' % (output_chapters_file_name,),
                                  #stderr=subprocess.STDOUT,
                                 )
            if not app.args.dry_run:
                chapters_xml = ET.parse(io.StringIO(byte_decode(chapters_out)))
                chapters_root = chapters_xml.getroot()
                for eEditionEntry in chapters_root.findall('EditionEntry'):
                    for chapter_no, eChapterAtom in enumerate(eEditionEntry.findall('ChapterAtom'), start=1):
                        e = eChapterAtom.find('ChapterTimeStart')
                        v = ffmpeg.Timestamp(e.text)
                        if v != 0.0:
                            # In case initial frame is a I frame to be displayed after
                            # subqequent P or B frames, the start time will be
                            # incorrect.
                            app.log.warning('Fixing first chapter start time %s to 0', v)
                            if False:
                                # mkvpropedit doesn't like unknown elements
                                e.tag = 'orig_ChapterTimeStart'
                                e = ET.SubElement(eChapterAtom, 'ChapterTimeStart')
                            e.text = str(ffmpeg.Timestamp(0))
                            chapters_xml_io = io.StringIO()
                            chapters_xml.write(chapters_xml_io,
                                               xml_declaration=True,
                                               encoding='unicode',  # Force string
                                               )
                            chapters_out = chapters_xml_io.getvalue()
                        break
                safe_write_file(output_chapters_file_name, byte_decode(chapters_out), text=True)
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

def action_chop(inputdir, in_tags):
    app.log.info('Chopping %s...', inputdir)
    outputdir = inputdir
    if app.args.chain:
        app.args.optimize_dirs += (outputdir,)

    input_mux_file_name = os.path.join(inputdir, 'mux.json')
    mux_dict = load_mux_dict(input_mux_file_name, in_tags)

    for chap in Chapters.from_mkv_xml(os.path.join(inputdir, mux_dict['chapters']['file_name']), add_pre_gap=True):
        app.log.verbose('Chapter %s', chap)

        for stream_dict in mux_dict['streams']:
            if stream_dict.get('skip', False):
                continue
            stream_index = stream_dict['index']
            stream_codec_type = stream_dict['codec_type']
            orig_stream_file_name = stream_file_name = stream_dict['file_name']
            stream_file_base, stream_file_ext = my_splitext(stream_file_name)
            stream_language = isolang(stream_dict.get('language', 'und'))

            snd_file = SoundFile.new_by_file_name(os.path.join(inputdir, stream_file_name))
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
                        '-ss', chap.start,
                        '-to', chap.end,
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
            elif stream_codec_type == 'image':
                pass
            else:
                raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

def my_splitext(file_name):
    file_name = str(file_name)
    base, ext = os.path.splitext(file_name)
    if ext in (
            '.mkv',
            '.ivf',
            '.mp2v',
            '.avi',
            '.ogg',
    ):
        base2, ext2 = os.path.splitext(base)
        if ext2 in (
                '.vp8',
                '.vp9',
                '.ffv1',
                '.mpeg2',
                '.h264',
                '.opus',
        ):
            base = base2
            ext = ext2 + ext
    return base, ext

def action_optimize(inputdir, in_tags):
    app.log.info('Optimizing %s...', inputdir)
    outputdir = inputdir
    do_chain = app.args.chain

    target_codec_names = set((
        'vp8', 'vp9',
        'opus',
        'webvtt',
        # 'mjpeg',
    ))

    temp_files = []

    input_mux_file_name = os.path.join(inputdir, 'mux.json')
    mux_dict = load_mux_dict(input_mux_file_name, in_tags)

    def done_optimize_iter():
        nonlocal temp_files
        nonlocal inputdir
        nonlocal stream_dict
        nonlocal stream_file_name
        nonlocal stream_file_base
        nonlocal stream_file_ext
        nonlocal new_stream_file_name
        nonlocal outputdir
        nonlocal mux_dict

        temp_files.append(os.path.join(inputdir, stream_file_name))
        stream_dict.setdefault('original_file_name', stream_file_name)
        stream_dict['file_name'] = stream_file_name = new_stream_file_name
        stream_file_base, stream_file_ext = my_splitext(stream_file_name)
        if not app.args.dry_run:
            output_mux_file_name = '%s/mux.json' % (outputdir,)
            with open(output_mux_file_name, 'w') as fp:
                json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
            if not app.args.save_temps:
                for file_name in temp_files:
                    os.unlink(file_name)
                temp_files = []
        if app.args.step:
            app.log.warning('Step done; Exit.')
            exit(0)

    for stream_dict in mux_dict['streams']:
        if stream_dict.get('skip', False):
            continue
        stream_index = stream_dict['index']
        stream_codec_type = stream_dict['codec_type']
        orig_stream_file_name = stream_file_name = stream_dict['file_name']
        stream_file_base, stream_file_ext = my_splitext(stream_file_name)
        stream_language = isolang(stream_dict.get('language', 'und'))

        if stream_codec_type == 'video':

            expected_framerate = None
            while True:

                stream_file = MediaFile.new_by_file_name(os.path.join(inputdir, stream_file_name))
                ffprobe_json = stream_file.extract_ffprobe_json()
                ffprobe_stream_json, = ffprobe_json['streams']
                stream_codec_name = ffprobe_stream_json['codec_name']

                if stream_codec_name in target_codec_names:
                    app.log.verbose('Stream #%d %s OK', stream_index, stream_codec_name)
                    break

                mediainfo_dict = stream_file.extract_mediainfo_dict()
                mediainfo_general_dict, mediainfo_track_dict = mediainfo_dict['media']['track']
                assert mediainfo_track_dict['@type'] == 'Video'

                field_order, framerate = analyze_field_order_and_framerate(
                    os.path.join(inputdir, stream_file_name),
                    ffprobe_json, ffprobe_stream_json, mediainfo_track_dict)

                if expected_framerate is not None:
                    assert framerate == expected_framerate, (framerate, expected_framerate)
                display_aspect_ratio = Ratio(stream_dict['display_aspect_ratio'])

                if field_order == '23pulldown':

                    if True:

                        new_stream_file_ext = '.ffv1.mkv'
                        new_stream_file_name = '.'.join(e for e in stream_file_base.split('.')
                                                        if e not in ('23pulldown',)) \
                            + '.pullup' + new_stream_file_ext
                        new_stream_file = MediaFile.new_by_file_name(os.path.join(inputdir, new_stream_file_name))
                        app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                        if stream_file_ext == '.y4m':
                            assert framerate == FrameRate(30000, 1001)
                            framerate = FrameRate(24000, 1001)
                            app.log.verbose('23pulldown y4m framerate correction: %s', framerate)
                            ffmpeg_dec_args = None
                        else:
                            ffmpeg_dec_args = [
                                '-i', os.path.join(inputdir, stream_file_name),
                                '-vf', 'fieldmatch,yadif=deint=interlaced',
                                '-pix_fmt', 'yuv420p',
                                '-nostats',  # will expect progress on output
                                # '-vcodec', 'yuv4',  # yuv4mpegpipe ERROR: Codec not supported.
                                '-f', ext_to_container('.y4m'),
                                '--', 'pipe:',
                            ]

                        app.log.verbose('pullup framerate: %s', framerate)

                        yuvkineco_cmd = [
                            'yuvkineco',
                        ]
                        if framerate == FrameRate(24000, 1001):
                            yuvkineco_cmd += ['-F', '1']
                        elif framerate == FrameRate(30000, 1001):
                            yuvkineco_cmd += ['-F', '4']
                        else:
                            raise NotImplementedError(framerate)
                        yuvkineco_cmd += ['-n', '2']  # Noise level (default: 10)
                        yuvkineco_cmd += ['-i', '-1']  # Disable deinterlacing

                        ffmpeg_enc_args = [
                            '-i', 'pipe:0',
                            '-vcodec', 'ffv1',
                            '-slices', 12, '-threads', 4,
                            '-f', ext_to_container(new_stream_file_ext),
                            os.path.join(inputdir, new_stream_file_name),
                        ]

                        with perfcontext('Pullup w/ -> .y4m -> yuvkineco -> .ffv1'):
                            if ffmpeg_dec_args:
                                p1 = ffmpeg.popen(*ffmpeg_dec_args,
                                                  stdout=subprocess.PIPE,
                                                  dry_run=app.args.dry_run)
                                p1_out = p1.stdout
                            elif not app.args.dry_run:
                                p1_out = stream_file.fp = stream_file.pvopen(mode='r')
                            else:
                                p1_out = None
                            try:
                                p2 = do_popen_cmd(yuvkineco_cmd,
                                                  stdin=p1_out,
                                                  stdout=subprocess.PIPE)
                                try:
                                    p3 = ffmpeg.popen(*ffmpeg_enc_args,
                                                      stdin=p2.stdout,
                                                      dry_run=app.args.dry_run,
                                                      y=app.args.yes)
                                finally:
                                    if not app.args.dry_run:
                                        p2.stdout.close()
                            finally:
                                if not app.args.dry_run:
                                    if ffmpeg_dec_args:
                                        p1.stdout.close()
                                    else:
                                        stream_file.close()
                            if not app.args.dry_run:
                                p3.communicate()
                                assert p3.returncode == 0

                        expected_framerate = framerate

                        done_optimize_iter()
                        continue

                        # ffmpeg -i input.1080i.ts -vf fieldmatch,yadif=deint=interlaced -f yuv4mpegpipe -pix_fmt yuv420p - | yuvkineco -F 1 -n 2 -i -1 | x264 --demuxer y4m -o out.mp4 -

                    else:
                        # -> mencoder -> .ffv1

                        if True:
                            # ffprobe and mediainfo don't agree on resulting frame rate.
                            new_stream_file_ext = '.ffv1.mkv'
                        else:
                            # mencoder seems to mess up the encoder frame rate in avi (total-frames/1), ffmpeg's r_frame_rate seems accurate.
                            new_stream_file_ext = '.ffv1.avi'
                        new_stream_file_name = stream_file_base + '.pullup' + new_stream_file_ext
                        new_stream_file = MediaFile.new_by_file_name(os.path.join(inputdir, new_stream_file_name))
                        app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                        mencoder_args = [
                            '-aspect', display_aspect_ratio,
                            stream_file,
                            '-ofps', framerate,
                            '-vf', 'pullup,softskip,harddup',
                            '-ovc', 'lavc', '-lavcopts', 'vcodec=ffv1:slices=12:threads=4',
                            '-of', 'lavf', '-lavfopts', 'format=%s' % (ext_to_mencoder_libavcodec_format(new_stream_file_ext),),
                            '-o', new_stream_file,
                        ]
                        expected_framerate = framerate
                        with perfcontext('Pullup w/ mencoder'):
                            mencoder(*mencoder_args,
                                     #slurm=True,
                                     dry_run=app.args.dry_run)

                        done_optimize_iter()
                        continue

                new_stream_file_ext = '.vp9.ivf'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                ffprobe_stream_json = ffprobe_json['streams'][0]
                app.log.debug(ffprobe_stream_json)

                #mediainfo_duration = qip.utils.Timestamp(mediainfo_track_dict['Duration'])
                mediainfo_width = int(mediainfo_track_dict['Width'])
                mediainfo_height = int(mediainfo_track_dict['Height'])

                extra_args = []
                video_filter_specs = []

                if field_order == 'progressive':
                    pass
                elif field_order in ('tt', 'tb'):
                    # ‘tt’ Interlaced video, top field coded and displayed first
                    # ‘tb’ Interlaced video, top coded first, bottom displayed first
                    # https://ffmpeg.org/ffmpeg-filters.html#yadif
                    video_filter_specs.append('yadif=parity=tff')
                elif field_order in ('bb', 'bt'):
                    # ‘bb’ Interlaced video, bottom field coded and displayed first
                    # ‘bt’ Interlaced video, bottom coded first, top displayed first
                    # https://ffmpeg.org/ffmpeg-filters.html#yadif
                    video_filter_specs.append('yadif=parity=bff')
                elif filters == '23pulldown':
                    raise NotImplementedError('pulldown should have been corrected already using yuvkineco or mencoder!')
                    video_filter_specs.append('pullup,fps=%s' % (framerate,))
                else:
                    raise NotImplementedError(field_order)

                if app.args.crop in (None, True):
                    if app.args.crop_wh:
                        w, h = app.args.crop_wh
                        l, t = (mediainfo_width - w) // 2, (mediainfo_height - h) // 2
                        stream_crop_whlt = w, h, l, t
                        stream_crop = True
                    elif app.args.crop_whlt:
                        stream_crop_whlt = app.args.crop_whlt
                        stream_crop = True
                    else:
                        stream_crop_whlt = None
                        stream_crop = getattr(app.args, 'crop', None)
                    if stream_crop is not False:
                        if not stream_crop_whlt and 'original_crop' not in stream_dict:
                            stream_crop_whlt = ffmpeg.cropdetect(
                                input_file=os.path.join(inputdir, stream_file_name),
                                # Seek 5 minutes in
                                #cropdetect_seek=max(0.0, min(300.0, float(mediainfo_duration) - 300.0)),
                                cropdetect_duration=app.args.cropdetect_duration,
                                video_filter_specs=video_filter_specs,
                                dry_run=app.args.dry_run)
                        if stream_crop_whlt and (stream_crop_whlt[0], stream_crop_whlt[1]) == (mediainfo_width, mediainfo_height):
                            stream_crop_whlt = None
                        stream_dict.setdefault('original_crop', stream_crop_whlt)
                        if stream_crop_whlt:
                            w, h, l, t = stream_crop_whlt
                            video_filter_specs.append('crop={w}:{h}:{l}:{t}'.format(
                                        w=w, h=h, l=l, t=t))
                            # extra_args += ['-aspect', XXX]
                            stream_dict.setdefault('original_display_aspect_ratio', stream_dict['display_aspect_ratio'])
                            storage_aspect_ratio = Ratio(w, h)
                            pixel_aspect_ratio = Ratio(stream_dict['pixel_aspect_ratio'])  # invariable
                            display_aspect_ratio = pixel_aspect_ratio * storage_aspect_ratio
                            if stream_crop is None:
                                if display_aspect_ratio in common_aspect_ratios:
                                    app.log.warning('Crop detection result accepted: --crop-whlt %s w/ common DAR %s',
                                                    ' '.join(str(e) for e in stream_crop_whlt),
                                                    display_aspect_ratio)
                                else:
                                    app.log.error('Crop detection! --crop or --no-crop or --crop-whlt %s w/ DAR %s',
                                                  ' '.join(str(e) for e in stream_crop_whlt),
                                                  display_aspect_ratio)
                                    raise RuntimeError
                            stream_dict['display_aspect_ratio'] = str(display_aspect_ratio)

                if video_filter_specs:
                    extra_args += ['-filter:v', ','.join(video_filter_specs)]

                if stream_file_ext in ('.mpeg2', '.mpeg2.mp2v'):
                    # In case initial frame is a I frame to be displayed after
                    # subqequent P or B frames, the start time will be
                    # incorrect.
                    # -start_at_zero, -dropts and various -vsync options don't
                    # seem to work, only -vsync drop.
                    # XXXJST assumes constant frame rate (at least after pullup)
                    extra_args += ['-vsync', 'drop']

                # https://trac.ffmpeg.org/wiki/Encode/VP9
                # https://developers.google.com/media/vp9/settings/vod/
                video_target_bit_rate = get_vp9_target_bitrate(
                    width=mediainfo_width, height=mediainfo_height,
                    frame_rate=framerate,
                    )
                video_target_bit_rate = int(video_target_bit_rate * 1.5)  # 1800 * 1.5 = 2700
                video_target_quality = get_vp9_target_quality(
                    width=mediainfo_width, height=mediainfo_height,
                    frame_rate=framerate,
                    )
                vp9_tile_columns, vp9_threads = get_vp9_tile_columns_and_threads(
                    width=mediainfo_width, height=mediainfo_height,
                    )

                ffmpeg_conv_args = []

                ffmpeg_conv_args += [
                    '-c:v', 'libvpx-vp9',
                ]
                if app.args.video_rate_control_mode == 'Q':
                    ffmpeg_conv_args += [
                        '-b:v', 0,
                        '-crf', str(video_target_quality),
                        '-quality', 'good',
                        '-speed', '1' if ffprobe_stream_json['height'] <= 480 else '2',
                    ]
                elif app.args.video_rate_control_mode == 'CQ':
                    ffmpeg_conv_args += [
                        '-b:v', '%dk' % (video_target_bit_rate,),
                        '-minrate', '%dk' % (video_target_bit_rate * 0.50,),
                        '-maxrate', '%dk' % (video_target_bit_rate * 1.45,),
                        '-crf', str(video_target_quality),
                        '-quality', 'good',
                        '-speed', '1' if ffprobe_stream_json['height'] <= 480 else '2',
                    ]
                elif app.args.video_rate_control_mode == 'CBR':
                    ffmpeg_conv_args += [
                        '-b:v', '%dk' % (video_target_bit_rate,),
                        '-minrate', '%dk' % (video_target_bit_rate,),
                        '-maxrate', '%dk' % (video_target_bit_rate,),
                    ]
                elif app.args.video_rate_control_mode == 'VBR':
                    ffmpeg_conv_args += [
                        '-b:v', '%dk' % (video_target_bit_rate,),
                        '-minrate', '%dk' % (video_target_bit_rate * 0.50,),
                        '-maxrate', '%dk' % (video_target_bit_rate * 1.45,),
                        '-quality', 'good',
                        '-speed', '1' if ffprobe_stream_json['height'] <= 480 else '2',
                    ]
                elif app.args.video_rate_control_mode == 'lossless':
                    ffmpeg_conv_args += [
                        '-lossless', 1,
                    ]
                else:
                    raise NotImplementedError(app.args.video_rate_control_mode)
                ffmpeg_conv_args += [
                    '-tile-columns', str(vp9_tile_columns),
                    '-row-mt', '1',
                    '-threads', str(vp9_threads),
                ]
                ffmpeg_conv_args += [
                    '-g', int(app.args.keyint * framerate),
                    ] + extra_args + [
                    ]

                ffmpeg_concat_args = []

                if mux_dict['chapters']:
                    chaps = list(Chapters.from_mkv_xml(os.path.join(inputdir, mux_dict['chapters']['file_name']), add_pre_gap=True))
                else:
                    chaps = []
                if (app.args.parallel_chapters
                        and len(chaps) > 1
                        and chaps[0].start == 0
                        and stream_file_ext in ('.mpeg2', '.mpeg2.mp2v')):  # Chopping using segment muxer is reliable (tested with mpeg2)
                    with perfcontext('Convert %s chapters to %s in parallel w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                        chapter_stream_file_ext = {
                                '.mpeg2': '.mpegts',
                                '.mpeg2.mp2v': '.mpegts',
                            }.get(stream_file_ext, stream_file_ext)
                        stream_chapter_file_name_pat = '%s-chap%%02d%s' % (stream_file_base, chapter_stream_file_ext)
                        new_stream_chapter_file_name_pat = '%s-chap%%02d%s' % (stream_file_base, new_stream_file_ext)

                        concat_list_file = TempFile.mkstemp(suffix='.concat.txt', open=True, text=True)
                        threads = []

                        def encode_chap():
                            app.log.verbose('Chapter %s', chap)
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
                                app.log.verbose('Chapter %s', chap)
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
                                            '-ss', chap.start,
                                            '-to', chap.end,
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
                                temp_files.append(os.path.join(inputdir, stream_chapter_file_name))
                        else:
                            app.log.verbose('All chapters...')
                            with perfcontext('Chop w/ ffmpeg segment muxer'):
                                chaps[-1].end = ffmpeg.Timestamp.MAX  # Make sure whole movie is captured
                                ffmpeg_args = [
                                    '-fflags', '+genpts',
                                    '-i', os.path.join(inputdir, stream_file_name),
                                    '-segment_times', ','.join(str(chap.end) for chap in chaps),
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
                                stream_chapter_file_name = stream_chapter_file_name_pat % (chap.no,)
                                encode_chap()
                                temp_files.append(os.path.join(inputdir, stream_chapter_file_name))

                        # Join
                        concat_list_file.close()
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
                            '-start_at_zero',
                            '-f', 'ivf', os.path.join(inputdir, new_stream_file_name),
                            ]
                        ffmpeg(*ffmpeg_args,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                        for chap in chaps:
                            new_stream_chapter_file_name = new_stream_chapter_file_name_pat % (chap.no,)
                            temp_files.append(os.path.join(inputdir, new_stream_chapter_file_name))
                else:
                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                        ffmpeg_args = [
                            '-i', os.path.join(inputdir, stream_file_name),
                            ] + ffmpeg_conv_args + [
                            '-f', 'ivf', os.path.join(inputdir, new_stream_file_name),
                            ]
                        ffmpeg.run2pass(*ffmpeg_args,
                                        slurm=True,
                                        dry_run=app.args.dry_run,
                                        y=app.args.yes)

                temp_files.append(os.path.join(inputdir, stream_file_name))
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []

        elif stream_codec_type == 'audio':

            ok_formats = (
                    '.opus',
                    '.opus.ogg',
                    #'.mp3',
                    )

            if stream_file_ext not in ok_formats:
                snd_file = SoundFile.new_by_file_name(os.path.join(inputdir, stream_file_name))
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
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                    ffmpeg_args = [
                        '-i', os.path.join(inputdir, stream_file_name),
                        # '-channel_layout', channel_layout,
                        ]
                    ffmpeg_args += [
                        '-start_at_zero',
                        #'-codec', 'pcm_s16le',
                    ]
                    if False:
                        # opusenc doesn't like RF64 headers!
                        # Other option is to pipe wav from ffmpeg to opusenc
                        ffmpeg_args += [
                            '-rf64', 'auto',  # Use RF64 header rather than RIFF for large files
                        ]
                    ffmpeg_args += [
                        '-f', 'wav', os.path.join(inputdir, new_stream_file_name),
                        ]
                    ffmpeg(*ffmpeg_args,
                           slurm=True,
                           slurm_cpus_per_task=2, # ~230-240%
                           dry_run=app.args.dry_run,
                           y=app.args.yes)

                temp_files.append(os.path.join(inputdir, stream_file_name))
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []

            if stream_file_ext not in ok_formats and stream_file_ext in opusenc_formats:
                # opusenc supports Wave, AIFF, FLAC, Ogg/FLAC, or raw PCM.
                new_stream_file_ext = '.opus.ogg'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                audio_bitrate = 640000 if channels >= 4 else 384000
                audio_bitrate = min(audio_bitrate, int(ffprobe_json['streams'][0]['bit_rate']))
                audio_bitrate = audio_bitrate // 1000

                with perfcontext('Convert %s -> %s w/ opusenc' % (stream_file_ext, new_stream_file_name)):
                    opusenc_args = [
                        '--vbr',
                        '--bitrate', str(audio_bitrate),
                        os.path.join(inputdir, stream_file_name),
                        os.path.join(inputdir, new_stream_file_name),
                        ]
                    opusenc(*opusenc_args,
                            slurm=True,
                            dry_run=app.args.dry_run)

                temp_files.append(os.path.join(inputdir, stream_file_name))
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []

            if stream_file_ext in ok_formats:
                if stream_file_name == orig_stream_file_name:
                    app.log.verbose('Stream #%d %s OK', stream_index, stream_file_ext)
            else:
                new_stream_file_ext = '.opus.ogg'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                audio_bitrate = 640000 if channels >= 4 else 384000
                audio_bitrate = min(audio_bitrate, int(ffprobe_json['streams'][0]['bit_rate']))
                audio_bitrate = audio_bitrate // 1000
                if channels > 2:
                    raise NotImplementedError('Conversion not supported as ffmpeg does not respect the number of channels and channel mapping')

                with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
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

                temp_files.append(os.path.join(inputdir, stream_file_name))
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []

        elif stream_codec_type == 'subtitle':
            if False and stream_file_ext in ('.sup',):
                new_stream_file_ext = '.sub'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                if False:
                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
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
                    with perfcontext('Convert %s -> %s w/ bdsup2sub' % (stream_file_ext, new_stream_file_name)):
                        # https://www.videohelp.com/software/BDSup2Sub
                        # https://github.com/mjuhasz/BDSup2Sub/wiki/Command-line-Interface
                        cmd = [
                            'bdsup2sub',
                            # TODO --forced-only
                            '--language', stream_language.code2,
                            '--output', os.path.join(inputdir, new_stream_file_name),
                            os.path.join(inputdir, stream_file_name),
                            ]
                        out = do_spawn_cmd(cmd)

                temp_files.append(os.path.join(inputdir, stream_file_name))
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []

            if stream_file_ext in ('.sup', '.sub',):
                if app.args.external_subtitles and not stream_dict['disposition'].get('forced', None):
                    app.log.warning('Stream #%d %s -> [external]', stream_index, stream_file_ext)
                    continue

                new_stream_file_ext = '.srt'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                if app.args.batch:
                    app.log.warning('BATCH MODE SKIP: Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)
                    do_chain = False
                    continue
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

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
                            '--subtitle-language', stream_language.code3,
                            '--',
                            os.path.join(inputdir, stream_file_name),
                            os.path.join(inputdir, new_stream_file_name),
                            subrip_matrix,
                            ]
                        do_spawn_cmd(cmd)

                else:
                    with perfcontext('Convert %s -> %s w/ SubtitleEdit' % (stream_file_ext, new_stream_file_name)):
                        if False:
                            cmd = [
                                'SubtitleEdit', '/convert',
                                os.path.join(inputdir, stream_file_name),
                                'subrip',  # format
                                ]
                            do_spawn_cmd(cmd)
                        else:
                            if False:
                                app.log.warning('Run OCR and save as SubRip (.srt) format: %s' % (
                                    byte_decode(dbg_exec_cmd(['winepath', '-w', os.path.join(inputdir, new_stream_file_name)])).strip(),
                                    ))
                            cmd = [
                                'SubtitleEdit',
                                os.path.join(inputdir, stream_file_name),
                                ]
                            do_spawn_cmd(cmd)
                            assert os.path.isfile(os.path.join(inputdir, new_stream_file_name)), \
                                    'File not found: %r' % (os.path.join(inputdir, new_stream_file_name),)
                cmd = [
                    os.path.join(os.path.dirname(__file__), 'fix-subtitles'),
                    os.path.join(inputdir, new_stream_file_name),
                    ]
                out = dbg_exec_cmd(cmd)
                if not app.args.dry_run:
                    out = clean_cmd_output(out)
                    File.new_by_file_name(os.path.join(inputdir, new_stream_file_name)) \
                            .write(out)
                    if app.args.interactive:
                        edfile(os.path.join(inputdir, new_stream_file_name))

                temp_files.append(os.path.join(inputdir, stream_file_name))
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []

            # NOTE:
            #  WebVTT format exported by SubtitleEdit is same as ffmpeg .srt->.vtt except ffmpeg's timestamps have more 0-padding
            if stream_file_ext in ('.srt',):
                new_stream_file_ext = '.vtt'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                    ffmpeg_args = [
                        '-i', os.path.join(inputdir, stream_file_name),
                        '-f', 'webvtt', os.path.join(inputdir, new_stream_file_name),
                        ]
                    ffmpeg(*ffmpeg_args,
                           #slurm=True,
                           dry_run=app.args.dry_run,
                           y=app.args.yes)

                temp_files.append(os.path.join(inputdir, stream_file_name))
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []

            if stream_file_ext in ('.vtt',):
                if stream_file_name == orig_stream_file_name:
                    app.log.verbose('Stream #%d %s OK', stream_index, stream_file_ext)
            else:
                raise ValueError('Unsupported subtitle extension %r' % (stream_file_ext,))

        elif stream_codec_type == 'image':

            # https://matroska.org/technical/cover_art/index.html
            ok_formats = (
                    '.png',
                    '.jpg',
                    )

            if stream_file_ext in ok_formats:
                if stream_file_name == orig_stream_file_name:
                    app.log.verbose('Stream #%d %s OK', stream_index, stream_file_ext)
            else:
                new_stream_file_ext = '.png'
                new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%d %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                    ffmpeg_args = [
                        '-i', os.path.join(inputdir, stream_file_name),
                        ]
                    ffmpeg_args += [
                        '-f', 'png', os.path.join(inputdir, new_stream_file_name),
                        ]
                    ffmpeg(*ffmpeg_args,
                           #slurm=True,
                           dry_run=app.args.dry_run,
                           y=app.args.yes)

                temp_files.append(os.path.join(inputdir, stream_file_name))
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                if not app.args.dry_run:
                    output_mux_file_name = '%s/mux.json' % (outputdir,)
                    with open(output_mux_file_name, 'w') as fp:
                        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []

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

    chaps = list(Chapters.from_mkv_xml(os.path.join(inputdir, mux_dict['chapters']['file_name']), add_pre_gap=False))
    while chaps and chaps[0].no < num_skip_chapters:
        chaps.pop(0)
    tracks_total = len(chaps)

    for track_no, chap in enumerate(chaps, start=1):
        app.log.verbose('Chapter %s -> track %d/%d',
                        chap,
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
            stream_file_base, stream_file_ext = my_splitext(stream_file_name)
            stream_language = isolang(stream_dict.get('language', 'und'))

            if stream_codec_type == 'video':
                pass
            elif stream_codec_type == 'audio':
                snd_file = SoundFile.new_by_file_name(os.path.join(inputdir, stream_file_name))
                ffprobe_json = snd_file.extract_ffprobe_json()
                app.log.debug(ffprobe_json['streams'][0])
                channels = ffprobe_json['streams'][0]['channels']
                channel_layout = ffprobe_json['streams'][0].get('channel_layout', None)

                force_format = None
                try:
                    force_format = ext_to_container(stream_file_ext)
                except ValueError:
                    pass

                stream_chapter_tmp_file = SoundFile.new_by_file_name(
                        os.path.join(inputdir, '%s-%02d%s' % (
                            stream_file_base,
                            chap.no,
                            stream_file_ext)))

                with perfcontext('Chop w/ ffmpeg'):
                    ffmpeg_args = [
                        '-start_at_zero', '-copyts',
                        '-i', os.path.join(inputdir, stream_file_name),
                        '-codec', 'copy',
                        '-ss', chap.start,
                        '-to', chap.end,
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

                m4a = M4aFile(my_splitext(stream_chapter_tmp_file.file_name)[0] + '.m4a')
                m4a.tags = copy.copy(mux_dict['tags'].tracks_tags[track_no])
                m4a.tags.track = track_no  # Since a copy was taken and not fully connected to album_tags anymore
                m4a.tags.tracks = tracks_total
                m4a.tags.title = chap.title

                if src_picture != m4a.tags.picture:
                    src_picture = m4a.tags.picture
                    picture = m4a.prep_picture(src_picture,
                                               yes=app.args.yes)
                m4a.tags.picture = None  # Not supported by taged TODO

                if stream_chapter_tmp_file.file_name != m4a.file_name:
                    audio_bitrate = 640000 if channels >= 4 else 384000
                    audio_bitrate = min(audio_bitrate, int(ffprobe_json['streams'][0]['bit_rate']))
                    audio_bitrate = audio_bitrate // 1000

                    with perfcontext('Convert %s -> %s w/ M4aFile.encode' % (stream_chapter_tmp_file.file_name, '.m4a')):
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
            elif stream_codec_type == 'image':
                # TODO image -> picture
                pass
            else:
                raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

def action_demux(inputdir, in_tags):
    app.log.info('Demuxing %s...', inputdir)
    outputdir = inputdir

    input_mux_file_name = os.path.join(inputdir, 'mux.json')
    mux_dict = load_mux_dict(input_mux_file_name, in_tags)

    # ffmpeg messes up timestamps, mkvmerge doesn't support WebVTT yet
    # https://trac.ffmpeg.org/ticket/7736#ticket
    use_mkvmerge = False
    webm = app.args.webm

    output_file = MkvFile(
            app.args.output_file or '%s.demux%s' % (inputdir.rstrip('/\\'), '.webm' if webm else '.mkv'))
    attachment_counts = collections.defaultdict(lambda: 0)

    external_stream_file_names_seen = set()
    stream_characteristics_seen = set()

    if use_mkvmerge:
        post_process_subtitles = []
        cmd = [
            'mkvmerge',
            ]
        if webm:
            cmd += [
                '--webm',
            ]
        cmd += [
            '-o', output_file.file_name,
            '--no-track-tags',
            '--no-global-tags',
            ]
        # --title handled with write_tags
        new_stream_index = -1
        for stream_index, stream_dict in sorted((stream_dict['index'], stream_dict)
                                                for stream_dict in mux_dict['streams']):
            if stream_dict.get('skip', False):
                continue
            stream_file_name = stream_dict['file_name']
            stream_codec_type = stream_dict['codec_type']
            stream_language = isolang(stream_dict.get('language', 'und'))
            stream_characteristics = (stream_codec_type, stream_language)
            if stream_codec_type == 'subtitle':
                stream_characteristics += (
                    'forced' if stream_dict['disposition'].get('forced', None) else '',
                    'hearing_impaired' if stream_dict['disposition'].get('hearing_impaired', None) else '',
                )
            if stream_characteristics in stream_characteristics_seen:
                raise ValueError(f'Stream #{stream_index} characteristics already seen: {stream_characteristics!r}')
            stream_characteristics_seen.add(stream_characteristics)
            if stream_codec_type == 'subtitle':
                if app.args.external_subtitles and my_splitext(stream_dict['file_name'])[1] != '.vtt':
                    stream_file_names = [stream_file_name]
                    if my_splitext(stream_dict['file_name'])[1] == '.sub':
                        stream_file_names.append(my_splitext(stream_file_name)[0] + '.idx')
                    for stream_file_name in stream_file_names:
                        external_stream_file_name = '{base}{language}{forced}{ext}'.format(
                            base=my_splitext(output_file.file_name)[0],
                            language='.%s' % (stream_language.code3,),
                            forced='.forced' if stream_dict['disposition'].get('forced', None) else '',
                            ext=my_splitext(stream_file_name)[1],
                        )
                        app.log.warning('Stream #%d %s -> %s', stream_index, stream_file_name, external_stream_file_name)
                        if external_stream_file_name in external_stream_file_names_seen:
                            raise ValueError(f'Stream {stream_index} External subtitle file already created: {external_stream_file_name}')
                        external_stream_file_names_seen.add(external_stream_file_name)
                        shutil.copyfile(os.path.join(inputdir, stream_file_name),
                                        external_stream_file_name,
                                        follow_symlinks=True)
                    continue
                if webm:
                    # mkvmerge does not yet support subtitles of webm files due to standard not being finalized
                    post_process_subtitles.append(stream_dict)
                    continue
            new_stream_index += 1
            stream_dict['index'] = new_stream_index
            if stream_codec_type == 'image':
                attachment_type = stream_dict['attachment_type']
                if webm:
                    # attachments not supported
                    attachment_counts[attachment_type] += 1
                    external_stream_file_name = '{type}{num_suffix}{ext}'.format(
                        type=attachment_type,
                        num_suffix='' if attachment_counts[attachment_type] == 1 else '-%d' % (attachment_counts[attachment_type],),
                        ext=my_splitext(stream_file_name)[1],
                    )
                    app.log.warning('Stream #%d %s -> %s', stream_index, stream_file_name, external_stream_file_name)
                    shutil.copyfile(os.path.join(inputdir, stream_file_name),
                                    external_stream_file_name,
                                    follow_symlinks=True)
                    continue
                else:
                    cmd += [
                        # '--attachment-description', <desc>
                        '--attachment-mime-type', byte_decode(dbg_exec_cmd(['file', '--brief', '--mime-type', os.path.join(inputdir, stream_file_name)])).strip(),
                        '--attachment-name', '%s%s' % (attachment_type, my_splitext(stream_file_name)[1]),
                        '--attach-file', os.path.join(inputdir, stream_file_name),
                        ]
            else:
                if stream_codec_type == 'video':
                    display_aspect_ratio = Ratio(stream_dict.get('display_aspect_ratio', None))
                    if display_aspect_ratio:
                        cmd += ['--aspect-ratio', '%d:%s' % (0, display_aspect_ratio)]
                stream_default = stream_dict['disposition'].get('default', None)
                cmd += ['--default-track', '%d:%s' % (0, ('true' if stream_default else 'false'))]
                if stream_language is not isolang('und'):
                    cmd += ['--language', '0:%s' % (stream_language.code3,)]
                stream_forced = stream_dict['disposition'].get('forced', None)
                cmd += ['--forced-track', '%d:%s' % (0, ('true' if stream_forced else 'false'))]
                # TODO --tags
                if stream_codec_type == 'subtitle' and my_splitext(stream_file_name)[1] == '.sub':
                    cmd += [os.path.join(inputdir, '%s.idx' % (my_splitext(stream_file_name)[0],))]
                cmd += [os.path.join(inputdir, stream_file_name)]
        if mux_dict['chapters']:
            cmd += ['--chapters', os.path.join(inputdir, mux_dict['chapters']['file_name'])]
        else:
            cmd += ['--no-chapters']
        with perfcontext('mkvmerge'):
            do_spawn_cmd(cmd)

        if post_process_subtitles:
            num_inputs = 0
            noss_file_name = output_file.file_name + '.noss%s' % ('.webm' if webm else '.mkv',)
            if not app.args.dry_run:
                shutil.move(output_file.file_name, noss_file_name)
            num_inputs += 1
            ffmpeg_args = [
                '-i', noss_file_name,
                ]
            option_args = [
                '-map', str(num_inputs-1),
                ]
            for stream_dict in post_process_subtitles:
                assert not stream_dict.get('skip', False)
                stream_file_name = stream_dict['file_name']
                stream_index = stream_dict['index']
                stream_codec_type = stream_dict['codec_type']
                assert stream_codec_type == 'subtitle'
                new_stream_index += 1
                stream_dict['index'] = new_stream_index
                num_inputs += 1
                ffmpeg_args += [
                    '-i', os.path.join(inputdir, stream_file_name),
                    ]
                option_args += [
                    '-map', str(num_inputs-1),
                    ]
                stream_language = isolang(stream_dict.get('language', 'und'))
                if stream_language is not isolang('und'):
                    #ffmpeg_args += ['--language', '%d:%s' % (track_id, stream_language.code3)]
                    option_args += ['-metadata:s:%d' % (new_stream_index,), 'language=%s' % (stream_language.code3,),]

                disposition_flags = []
                if stream_dict['disposition'].get('default', None):
                    disposition_flags.append('default')
                if stream_dict['disposition'].get('forced', None):
                    disposition_flags.append('forced')
                ffmpeg_output_args += [
                    '-disposition:%d' % (new_stream_index,),
                    '+'.join(disposition_flags or ['0']),
                    ]

                # TODO --tags
            option_args += [
                '-codec', 'copy',
                ]
            ffmpeg_args += option_args
            # Note on -f webm:
            #  By forcing webm format, encoding of target display width/height will
            #  be used instead of of aspect ratio with DisplayUnits=3 in mkv
            #  headers (see mkvinfo). Some players, like VLC, exhibit playback
            #  issues with images stretched vertically, a lot.
            ffmpeg_args += [
                '-f', ext_to_container(my_splitext(output_file.file_name)[1]),
                output_file.file_name,
                ]
            with perfcontext('merge subtitles w/ ffmpeg'):
                ffmpeg(*ffmpeg_args,
                       dry_run=app.args.dry_run,
                       y=app.args.yes)
            raise NotImplementedError('BUG: unable to synchronize timestamps before and after adding subtitles, ffmpeg shifts video by 7ms (due to pre-skip of opus streams) and of vtts')
            if not app.args.dry_run:
                os.unlink(noss_file_name)
    else:
        ffmpeg_input_args = []
        ffmpeg_output_args = []
        ffmpeg_output_args += [
            '-map_metadata', '-1',
            '-map_chapters', '-1',
            '-codec', 'copy',
            #'-copyts', '-start_at_zero',
            #'-avoid_negative_ts', 1,
            #'-vsync', 'drop',
            ]
        time_offset = 0  # ffmpeg.Timestamp(-0.007)
        new_stream_index = -1
        has_opus_streams = any(
                my_splitext(stream_dict['file_name'])[1] in ('.opus', '.opus.ogg')
                for stream_dict in mux_dict['streams'])
        for stream_dict in sorted(mux_dict['streams'], key=lambda stream_dict: stream_dict['index']):
            if stream_dict.get('skip', False):
                continue
            stream_index = stream_dict['index']
            stream_file_name = stream_dict['file_name']
            stream_file_base, stream_file_ext = my_splitext(stream_file_name)
            stream_codec_type = stream_dict['codec_type']
            stream_language = isolang(stream_dict.get('language', 'und'))
            stream_characteristics = (stream_codec_type, stream_language)
            if stream_codec_type == 'subtitle':
                stream_characteristics += (
                    'forced' if stream_dict['disposition'].get('forced', None) else '',
                    'hearing_impaired' if stream_dict['disposition'].get('hearing_impaired', None) else '',
                )
            if stream_codec_type == 'subtitle':
                if app.args.external_subtitles and my_splitext(stream_dict['file_name'])[1] != '.vtt':
                    stream_characteristics += ('external',)
                    stream_file_names = [stream_file_name]
                    if my_splitext(stream_dict['file_name'])[1] == '.sub':
                        stream_file_names.append(my_splitext(stream_file_name)[0] + '.idx')
                    for stream_file_name in stream_file_names:
                        external_stream_file_name = '{base}{language}{forced}{ext}'.format(
                            base=my_splitext(str(output_file))[0],
                            language='.%s' % (isolang(stream_dict['language']).code3,),
                            forced='.forced' if stream_dict['disposition'].get('forced', None) else '',
                            ext=my_splitext(stream_file_name)[1],
                        )
                        app.log.warning('Stream #%d %s -> %s', stream_index, stream_file_name, external_stream_file_name)
                        if external_stream_file_name in external_stream_file_names_seen:
                            raise ValueError(f'Stream {stream_index} External subtitle file already created: {external_stream_file_name}')
                        external_stream_file_names_seen.add(external_stream_file_name)
                        shutil.copyfile(os.path.join(inputdir, stream_file_name),
                                        external_stream_file_name,
                                        follow_symlinks=True)
                    continue
                if my_splitext(stream_dict['file_name'])[1] == '.sub':
                    # ffmpeg doesn't read the .idx file?? Embed .sub/.idx into a .mkv first
                    tmp_stream_file_name = stream_file_name + '.mkv'
                    mkvmerge_cmd = [
                        'mkvmerge',
                        '-o', os.path.join(inputdir, tmp_stream_file_name),
                        os.path.join(inputdir, stream_file_name),
                        '%s.idx' % (my_splitext(os.path.join(inputdir, stream_file_name))[0],),
                    ]
                    do_spawn_cmd(mkvmerge_cmd)
                    stream_file_name = tmp_stream_file_name
                    stream_file_base, stream_file_ext = my_splitext(stream_file_name)
            if stream_characteristics in stream_characteristics_seen:
                raise ValueError(f'Stream #{stream_index} characteristics already seen: {stream_characteristics!r}')
            stream_characteristics_seen.add(stream_characteristics)
            if stream_codec_type == 'image':
                attachment_type = stream_dict['attachment_type']
                if webm:
                    # attachments not supported
                    attachment_counts[attachment_type] += 1
                    external_stream_file_name = '{type}{num_suffix}{ext}'.format(
                        type=attachment_type,
                        num_suffix='' if attachment_counts[attachment_type] == 1 else '-%d' % (attachment_counts[attachment_type],),
                        ext=my_splitext(stream_file_name)[1],
                    )
                    app.log.warning('Stream #%d %s -> %s', stream_index, stream_file_name, external_stream_file_name)
                    shutil.copyfile(os.path.join(inputdir, stream_file_name),
                                    external_stream_file_name,
                                    follow_symlinks=True)
                    continue
            new_stream_index += 1
            disposition_flags = []
            for k, v in stream_dict['disposition'].items():
                if v:
                    disposition_flags.append(k)
            ffmpeg_output_args += [
                '-disposition:%d' % (new_stream_index,),
                '+'.join(disposition_flags or ['0']),
                ]
            stream_language = isolang(stream_dict.get('language', 'und'))
            if stream_language is not isolang('und'):
                ffmpeg_output_args += ['-metadata:s:%d' % (new_stream_index,), 'language=%s' % (stream_language.code3,),]
            display_aspect_ratio = stream_dict.get('display_aspect_ratio', None)
            if display_aspect_ratio:
                ffmpeg_output_args += ['-aspect:%d' % (new_stream_index,), display_aspect_ratio]

            stream_start_time = ffmpeg.Timestamp(stream_dict.get('start_time', 0))
            if stream_start_time:
                codec_encoding_delay = get_codec_encoding_delay(os.path.join(inputdir, stream_file_name))
                stream_start_time += codec_encoding_delay
            elif has_opus_streams and stream_file_ext in ('.opus', '.opus.ogg'):
                # Note that this is not needed if the audio track is wrapped in a mkv container
                stream_start_time = -ffmpeg.Timestamp.MAX
            if stream_start_time:
                ffmpeg_input_args += [
                    '-itsoffset', stream_start_time,
                    ]

            if stream_codec_type == 'video':
                if stream_file_ext in ('.vp9', '.vp9.ivf',):
                    # ffmpeg does not generate packet durations from ivf -> mkv, causing some hickups at play time. But it does from .mkv -> .mkv, so create an intermediate
                    tmp_stream_file_name = stream_file_name + '.mkv'
                    ffmpeg(*[
                        '-i', os.path.join(inputdir, stream_file_name),
                        '-codec', 'copy',
                        '-y',
                        os.path.join(inputdir, tmp_stream_file_name),
                        ])
                    stream_file_name = tmp_stream_file_name
                    stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                elif stream_file_ext.endswith('.mkv'):
                    pass
                else:
                    raise NotImplementedError(stream_file_ext)
            ffmpeg_input_args += [
                '-i',
                os.path.join(inputdir, stream_file_name),
                ]
            # Include all streams from this input file:
            ffmpeg_output_args += [
                '-map', new_stream_index,
                ]
        ffmpeg_output_args += [
            '-f', ext_to_container(my_splitext(output_file.file_name)[1]),
            output_file.file_name,
            ]
        ffmpeg_args = ffmpeg_input_args + ffmpeg_output_args
        with perfcontext('merge w/ ffmpeg'):
            ffmpeg(*ffmpeg_args,
                   dry_run=app.args.dry_run,
                   y=app.args.yes)
        if mux_dict['chapters']:
            chapters_xml_file = TextFile(os.path.join(inputdir, mux_dict['chapters']['file_name']))
            if time_offset:
                chapters_xml = ET.parse(chapters_xml_file.file_name)
                chapters_root = chapters_xml.getroot()
                for eEditionEntry in chapters_root.findall('EditionEntry'):
                    for chapter_no, eChapterAtom in enumerate(eEditionEntry.findall('ChapterAtom'), start=1):
                        for tag in ('ChapterTimeStart', 'ChapterTimeEnd'):
                            e = eChapterAtom.find(tag)
                            e.text = str(ffmpeg.Timestamp(e.text) + time_offset)
                chapters_xml_file = TempFile.mkstemp(suffix='.chapters.xml', open=True, text=True)
                chapters_xml.write(chapters_xml_file.fp,
                                   xml_declaration=True,
                                   encoding='unicode',  # Force string
                                   )
                chapters_xml_file.close()
            cmd = [
                'mkvpropedit',
                output_file.file_name,
                '--chapters', chapters_xml_file.file_name,
            ]
            with perfcontext('add chapters w/ mkvpropedit'):
                do_spawn_cmd(cmd)

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
