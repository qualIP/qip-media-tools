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

# [h264 @ 0x5589459c73c0] error while decoding MB 42 65, bytestream -11
# /tmp/ffmpeg-2pass-pipe.27225.tmp/input: corrupt decoded frame in stream 0

# Changing Default Track Selection
##################################
# https://makemkv.com/forum/viewtopic.php?f=10&t=4386
# Default:
#   -sel:all,+sel:(favlang|nolang),-sel:(havemulti|havecore),=100:all,-10:favlang
# Old:
#   -sel:all,+sel:(nolang|eng|fra|fre),-sel:(havemulti|havecore),-sel:mvcvideo,=100:all,-10:favlang
# Get the HD sound tracks instead of core and get all versions to make sure to get all comments
#   -sel:all,+sel:(nolang|eng|fra|fre),-sel:mvcvideo,=100:all,-10:favlang
# Force selecting attachments:
#   +sel:all,-sel:(audio|subtitle),+sel:(nolang|eng|fra|fre),-sel:core,-sel:mvcvideo,=100:all,-10:favlang

# Conversion Profiles
#####################
# https://www.makemkv.com/forum/viewtopic.php?f=10&t=4385

# General Info
##############
# https://en.wikipedia.org/wiki/Glossary_of_digital_audio

from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import collections
import concurrent.futures
import contextlib
import copy
import decimal
import errno
import functools
import glob
import html
import io
import itertools
import logging
import operator
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

try:
    from qip.utils import ProgressBar
except ImportError:
    ProgressBar = None

from qip import argparse
from qip import json
from qip.app import app
from qip.avi import *
from qip.cdrom import cdrom_ready
from qip.ddrescue import ddrescue
from qip.exec import *
from qip.ffmpeg import ffmpeg, ffprobe
from qip.file import *
from qip.handbrake import *
from qip.isolang import isolang
from qip.matroska import *
from qip.mediainfo import *
from qip.mencoder import mencoder
from qip.mm import *
from qip.mm import MediaFile, MovieFile, Chapter, Chapters, FrameRate
from qip.mp2 import *
from qip.mp4 import *
from qip.opusenc import opusenc
from qip.perf import perfcontext
from qip.threading import *
from qip.udisksctl import udisksctl
from qip.utils import byte_decode, Ratio, round_half_away_from_zero
import qip.mm
import qip.utils
Auto = qip.utils.Constants.Auto

tmdb = None
tvdb = None

thread_executor = None
slurm_executor = None

default_minlength_tvshow = qip.utils.Timestamp('15m')
default_minlength_movie = qip.utils.Timestamp('60m')

default_ffmpeg_args = []

#map_RatioConverter = {
#    Ratio("186:157"):
#    Ratio("279:157"):
#}
#def RatioConverter(ratio)
#    ratio = Ratio(ratio)
#    ratio = map_RatioConverter.get(ratio, ratio)
#    return ratio


# https://www.ffmpeg.org/ffmpeg.html

def describe_stream_dict(stream_dict):
    orig_stream_file_name = stream_dict.get('original_file_name', stream_dict['file_name'])
    desc = '{codec_type} stream #{index}: title={title!r}, language={language}, disposition=({disposition}), ext={orig_ext}'.format(
        codec_type=stream_dict['codec_type'],
        index=stream_dict['index'],
        title=stream_dict.get('title', None),
        language=isolang(stream_dict.get('language', 'und')),
        disposition=', '.join(k for k, v in stream_dict['disposition'].items() if v),
        orig_ext=my_splitext(orig_stream_file_name)[1],
    )
    return desc

def stream_dict_key(stream_dict):
    return (
        ('video', 'audio', 'subtitle', 'image').index(stream_dict['codec_type']),
        not bool(stream_dict.get('disposition', {}).get('default', False)),  # default then non-default
        stream_dict['index'],
        bool(stream_dict.get('disposition', {}).get('forced', False)),       # non-forced, then forced
        bool(stream_dict.get('disposition', {}).get('comment', False)),      # non-comment, then comment
    )

def sorted_stream_dicts(stream_dicts):
    return sorted(
        stream_dicts,
        key=stream_dict_key)

def print_streams_summary(mux_dict, current_stream_index=None):
    print(' index |   type   |       extension       | language | disposition + title')
    print('-------+----------+-----------------------+----------+---------------------')
    for stream_dict in sorted_stream_dicts(mux_dict['streams']):
        print('{skip_marker:<1s}{current_marker:<1s}{stream_index:>4d} | {codec_type:<8s} | {extension:<21s} | {language:^8s} | {disposition_title}'.format(
            skip_marker='S' if stream_dict.get('skip', False) else '',
            current_marker='*' if stream_dict['index'] == current_stream_index else '',
            stream_index=stream_dict['index'],
            codec_type=stream_dict['codec_type'],
            extension=
            '->'.join([e for e in [
                my_splitext(stream_dict.get('original_file_name', ''))[1],
                my_splitext(stream_dict['file_name'])[1],]
                       if e]),
            language=isolang(stream_dict.get('language', 'und')).code3,
            disposition_title=', '.join([k for k, v in stream_dict['disposition'].items() if v]
                                        + ([repr(stream_dict['title'])]
                                           if stream_dict.get('title', None)
                                           else [])
                                        + (['suffix=' + repr(stream_dict['external_stream_file_name_suffix'])]
                                           if stream_dict.get('external_stream_file_name_suffix', None)
                                           else [])
                                        + ([f'''*{stream_dict['subtitle_count']}''']
                                           if stream_dict.get('subtitle_count', None)
                                           else [])
                                        ),
        ))
        try:
            original_source_description = stream_dict['original_source_description']
        except KeyError:
            pass
        else:
            print(f'       |          | source: {original_source_description}')

    print('-------+----------+-----------------------+----------+---------------------')

class FieldOrderUnknownError(NotImplementedError):

    def __init__(self, mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order):
        self.mediainfo_scantype = mediainfo_scantype
        self.mediainfo_scanorder = mediainfo_scanorder
        self.ffprobe_field_order = ffprobe_field_order
        super().__init__((mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order))

class StreamCharacteristicsSeenError(ValueError):

    def __init__(self, stream_index, stream_characteristics):
        self.stream_index = stream_index
        self.stream_characteristics = stream_characteristics
        super().__init__(f'Stream #{stream_index} characteristics already seen: {stream_characteristics!r}')

class StreamExternalSubtitleAlreadyCreated(ValueError):

    def __init__(self, stream_index, external_stream_file_name):
        self.stream_index = stream_index
        self.external_stream_file_name = external_stream_file_name
        super().__init__(f'Stream {stream_index} External subtitle file already created: {external_stream_file_name}')

class LargeDiscrepancyInStreamDurationsError(ValueError):

    def __init__(self, *, inputdir):
        self.inputdir = inputdir
        super().__init__(f'{inputdir}: Large discrepancy in stream durations!')

common_aspect_ratios = {
    # Ratio(4, 3),
    # Ratio(16, 9),   # 1.78:1 1920x1080 "FHD"
    # Ratio(40, 17),  # 2.35:1 1920x816  "CinemaScope"
    # Ratio(12, 5),   # 2.40:1 1920x800  "CinemaScope"
}

common_resolutions = {
    # SD (https://en.wikipedia.org/wiki/Standard-definition_television)
    (704, 480),   # 480i (horizontal blanking cropped)  DAR  4:3 / PAR 10:11 -> 640×480
    (720, 480),   # 480i (full frame)                   DAR  4:3 / PAR 10:11 -> 654×480
    (704, 480),   # 480i (horizontal blanking cropped)  DAR 16:9 / PAR 40:33 -> 854×480
    (720, 480),   # 480i (full frame)                   DAR 16:9 / PAR 40:33 -> 872×480
    (704, 576),   # 576i (horizontal blanking cropped)  DAR  4:3 / PAR 12:11 -> 768×576
    (720, 576),   # 576i (full frame)                   DAR  4:3 / PAR 12:11 -> 786×576
    (704, 576),   # 576i (horizontal blanking cropped)  DAR 16:9 / PAR 16:11 -> 1024×576
    (720, 576),   # 576i (full frame)                   DAR 16:9 / PAR 16:11 -> 1048×576
    # Other
    (720, 360),   # Anamorphic Widescreen
    (720, 362),   # Common Anamorphic Widescreen
    (720, 368),   # Common Anamorphic Widescreen  DAR 160:69
    # HD (https://en.wikipedia.org/wiki/High-definition_video)
    (1280, 720),  # HD Ready
    (1920, 816),  # 2.35:1 "CinemaScope"
    (1920, 800),  # 2.40:1 "CinemaScope"
    # 2K (https://en.wikipedia.org/wiki/2K_resolution)
    (2048, 1080), # DCI 2K (native resolution)     1.90:1 (256:135, ~17:9)
    (1998, 1080), # DCI 2K (flat cropped)          1.85:1
    (2048, 858),  # DCI 2K (CinemaScope cropped)   2.39:1
    # 4K (https://en.wikipedia.org/wiki/4K_resolution)
    (4096, 2160), # (full frame)       256∶135 or ≈1.90∶1
    (3996, 2160), # (flat crop)                    1.85∶1
    (4096, 1716), # (CinemaScope crop)            ≈2.39∶1
}

cropdetect_autocorrect_whlt = {
    (1920, 804, 0, 138): (1920, 800, 0, 140),  # 2.40:1 "CinemaScope"
}

def MOD_ROUND(v, m):
    return v if m == 1 else m * ((v + (m >> 1)) // m)

def MOD_DOWN(v, m):
    return m * (v // m)

def MOD_UP(v, m):
    return m * ((v + m - 1) // m)

def isolang_or_None(v):
    return None if v == 'None' else isolang(v)

def unmangle_search_string(initial_text):
    initial_text = initial_text.strip()                                #  ABC   -> ABC
    initial_text = re.sub(r'(?=[A-Z][a-z])', r' ', initial_text)       # AbCDef ->  AbC Def
    initial_text = re.sub(r'[a-z](?=[A-Z])', r'\g<0> ', initial_text)  # AbC Def -> Ab C Def
    initial_text = re.sub(r'[A-Za-z](?=\d)', r'\g<0> ', initial_text)  # ABC123 -> ABC 123
    p = None
    while initial_text != p:
        p = initial_text
        initial_text = re.sub(r'(.+),\s*(The|A|An|Le|La|Les)$', r'\2 \1', initial_text, flags=re.IGNORECASE)  # ABC, The -> The ABC
        initial_text = re.sub(r'[^A-Za-z0-9\']+', r' ', initial_text)      # AB$_12 -> AB 12
        initial_text = initial_text.strip()                                #  ABC   -> ABC
        initial_text = re.sub(r'(?:DVD\|Blu[- ]?ray)$', r'', initial_text, flags=re.IGNORECASE)  # ABC Blu Ray -> ABC
        initial_text = re.sub(r'(?: the)? \w+(?:\'s)? (?:edition|cut)$', r'', initial_text, flags=re.IGNORECASE)  # ABC special edition -> ABC
        initial_text = re.sub(r' dis[ck] [0-9]+$', r'', initial_text, flags=re.IGNORECASE)  # ABC disc 1 -> ABC
    return initial_text

def analyze_field_order_and_framerate(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict):
    field_order = getattr(app.args, 'force_field_order', None)
    input_framerate = None
    framerate = getattr(app.args, 'force_framerate', None)

    video_frames = []

    if mediainfo_track_dict['@type'] == 'Image':
        if field_order is None:
            field_order = 'progressive'
        if framerate is None:
            framerate = FrameRate(1, 1)

    if field_order is None:
        if '-pullup.' in stream_file_name.name:
            field_order = 'progressive'
        elif '.progressive.' in stream_file_name.name:
            field_order = 'progressive'

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
            prev_frame.interlaced_frame = False
            video_analyze_duration = app.args.video_analyze_duration
            try:
                mediainfo_duration = qip.utils.Timestamp(mediainfo_track_dict['Duration'])
            except KeyError:
                pass
            else:
                # Sometimes mediainfo'd Duration is just the first frame duration
                if False and mediainfo_duration >= 1.0:
                    video_analyze_duration = min(mediainfo_duration, video_analyze_duration)
            with perfcontext('frames iteration'):
                progress_bar = None
                if ProgressBar is not None:
                    progress_bar = ProgressBar('iterate frames',
                                           max=float(video_analyze_duration),
                                           suffix='%(index)d/%(max)d (%(eta_td)s remaining)')
                try:
                    for frame in ffprobe.iter_frames(stream_file_name,
                                                     # [error] Failed to set value 'nvdec' for option 'hwaccel': Option not found
                                                     # TODO default_ffmpeg_args=default_ffmpeg_args,
                                                     ):
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
                        if progress_bar is not None:
                            if int(progress_bar.index) != int(float(frame.pkt_dts_time)):
                                progress_bar.goto(float(frame.pkt_dts_time))
                        if float(frame.pkt_dts_time) >= video_analyze_duration:
                            break
                        prev_frame = frame
                    #video_frames = sorted(video_frames, key=lambda frame: frame.pkt_pts_time)
                    #video_frames = sorted(video_frames, key=lambda frame: frame.coded_picture_number)
                finally:
                    if progress_bar is not None:
                        progress_bar.finish()

            app.log.debug('Analyzing %d video frames...', len(video_frames))

            video_frames = video_frames[app.args.video_analyze_skip_frames:]  # Skip first frames; Often padded with different field order
            assert video_frames, "No video frames found to analyze!"

            field_order_diags = []

            # video_frames_by_dts = sorted(video_frames, key=lambda frame: frame.pkt_dts_time)
            # XXXJST:
            # Based on libmediainfo-18.12/Source/MediaInfo/Video/File_Mpegv.cpp
            # though getting the proper TemporalReference is more complex and may
            # be different than pkt_dts_time ordering.
            temporal_string = ''.join([
                ('T' if frame.top_field_first else 'B') + ('3' if frame.repeat_pict else '2')
                for frame in video_frames])
            app.log.debug('temporal_string: %r', temporal_string)

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
                        input_framerate = FrameRate(30000, 1001)
                        framerate = FrameRate(24000, 1001)
                    else:
                        raise NotImplementedError(found_pkt_duration_times)
                    if temporal_pattern_offset <= 24:
                        # starts with pulldown
                        app.log.warning('Detected field order %s at %s (%.3f) fps based on temporal pattern near start of analysis section %r', field_order, framerate, framerate, temporal_pattern)
                        last_frame = video_frames[-1]
                        if temporal_string.endswith('T2' * 12):
                            if last_frame.pkt_duration_time in (
                                        Decimal('0.033367'),
                                    ):
                                input_framerate = framerate = FrameRate(30000, 1001)
                            elif last_frame.pkt_duration_time in (
                                        Decimal('0.041708'),
                                    ):
                                input_framerate = framerate = FrameRate(24000, 1001)
                            else:
                                raise ValueError(f'last_frame.pkt_duration_time = {last_frame.pkt_duration_time}')
                            app.log.warning('Also detected field order progressive or tt at %s (%.3f) fps based on temporal pattern at end of analysis section', framerate, framerate)
                        elif temporal_string.endswith('B2' * 12):
                            if last_frame.pkt_duration_time in (
                                        Decimal('0.033367'),
                                    ):
                                input_framerate = framerate = FrameRate(30000, 1001)
                            elif last_frame.pkt_duration_time in (
                                        Decimal('0.041708'),
                                    ):
                                input_framerate = framerate = FrameRate(24000, 1001)
                            else:
                                raise ValueError(f'last_frame.pkt_duration_time = {last_frame.pkt_duration_time}')
                            app.log.warning('Also detected field order progressive or bb at %s (%.3f) fps based on temporal pattern at end of analysis section', framerate, framerate)
                    else:
                        # ends with pulldown
                        app.log.warning('Detected field order %s at %s (%.3f) fps based on temporal pattern near end of analysis section %r', field_order, framerate, framerate, temporal_pattern)
                        assert input_framerate == FrameRate(30000, 1001)  # Only verified case so far
                        assert framerate == FrameRate(24000, 1001)  # Only verified case so far
                        # assert framerate == original_framerate * result_framerate_ratio
                    break

            if field_order is None:
                frame0 = video_frames[0]
                if framerate is not None:
                    constant_framerate = True
                else:
                    constant_framerate = all(
                            frame.pkt_duration == frame0.pkt_duration
                            for frame in video_frames)
                if constant_framerate:
                    if framerate is None:
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
                            assert len(video_frames) > 5, f'Not enough precision, only {len(video_frames)} frames analyzed.'
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
                                if False:
                                    raise NotImplementedError('Mix of top field first and bottom field first interlaced frames detected')
                                field_order = 'auto-interlaced'
                                app.log.warning('Detected field order is mix of top and bottom field first (%s) at %s (%.3f) fps',
                                                field_order, framerate, framerate)
                        else:
                            field_order = 'progressive'
                            app.log.warning('Detected field order is %s at %s (%.3f) fps', field_order, framerate, framerate)
                    else:
                        if False:
                            field_order_diags.append('Mix of interlaced and non-interlaced frames found.')
                            app.log.debug(field_order_diags[-1])
                        else:
                            field_order = 'auto-interlaced'
                            app.log.warning('Detected field order is mix of top and bottom field first (%s) at %s (%.3f) fps',
                                            field_order, framerate, framerate)
                    # v_pick_framerate = pick_framerate(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict, field_order=field_order)
                    # assert framerate == v_pick_framerate, f'constant framerate ({framerate}) does not match picked framerate ({v_pick_framerate})'
                else:
                    field_order_diags.append('Variable fps found.')
                    app.log.debug(field_order_diags[-1])

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
        raise NotImplementedError('field_order unknown' \
                                  + (': ' + ' '.join(field_order_diags)
                                     if field_order_diags else ''))

    if framerate is None:
        framerate = pick_framerate(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict, field_order=field_order)

    return field_order, input_framerate, framerate

num_batch_skips = 0

def _resolved_Path(path):
    return Path(path).resolve()

@app.main_wrapper
def main():
    global num_batch_skips
    global default_ffmpeg_args

    app.init(
            version='1.0',
            description='Multimedia [de]multiplexer',
            contact='jst@qualipsoft.com',
            )

    app.cache_dir = 'mmdemux-cache'  # in current directory!

    in_tags = AlbumTags()

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_bool_argument('--interactive', '-i', help='interactive mode')
    pgroup.add_bool_argument('--dry-run', '-n', help='dry-run mode')
    pgroup.add_bool_argument('--yes', '-y',
                             help='answer "yes" to all prompts',
                             neg_help='do not answer prompts')
    pgroup.add_bool_argument('--save-temps', default=False,
                             help='do not delete intermediate files',
                             neg_help='delete intermediate files')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')
    pgroup.add_bool_argument('--continue', dest='_continue', help='continue mode')
    pgroup.add_bool_argument('--force', '-f', help='force mode (bypass some checks)')
    pgroup.add_bool_argument('--batch', '-B', help='batch mode')
    pgroup.add_bool_argument('--step', help='step mode')
    pgroup.add_bool_argument('--cuda', help='enable CUDA')
    pgroup.add_bool_argument('--alpha', help='enable alpha features')
    pgroup.add_bool_argument('--slurm', default=False, help='enable slurm')
    pgroup.add_argument('--jobs', '-j', type=int, nargs='?', default=1, const=Auto, help='Specifies the number of jobs (threads) to run simultaneously')

    pgroup = app.parser.add_argument_group('Tools Control')
    pgroup.add_argument('--track-extract-tool', default=Auto, choices=('ffmpeg', 'mkvextract'), help='tool to extract tracks')
    pgroup.add_argument('--pullup-tool', default=Auto, choices=('yuvkineco', 'ffmpeg', 'mencoder'), help='tool to pullup any 23pulldown video tracks')
    pgroup.add_argument('--ionice', default=None, type=int, help='ionice process level')
    pgroup.add_argument('--nice', default=None, type=int, help='nice process adjustment')
    pgroup.add_bool_argument('--check-cdrom-ready', default=True, help='check CDROM readiness')
    pgroup.add_argument('--cdrom-ready-timeout', default=24, type=int, help='CDROM readiness timeout')

    pgroup = app.parser.add_argument_group('Ripping Control')
    pgroup.add_argument('--device', default=Path(os.environ.get('CDROM', '/dev/cdrom')), type=_resolved_Path, help='specify alternate cdrom device')
    pgroup.add_argument('--minlength', default=Auto, type=qip.utils.Timestamp, help='minimum title length for ripping (default: ' + default_minlength_movie.friendly_str() + ' (movie), ' + default_minlength_tvshow.friendly_str() + ' (tvshow))')
    pgroup.add_argument('--sp-remove-method', default='auto', choices=('auto', 'CellWalk', 'CellTrim'), help='DVD structure protection removal method')
    pgroup.add_bool_argument('--check-start-time', default=Auto, help='check start time of tracks')
    pgroup.add_argument('--stage', default=Auto, type=int, choices=range(1, 3 + 1), help='specify ripping stage')
    pgroup.add_bool_argument('--decrypt', default=True, help='create decrypted backup')

    pgroup = app.parser.add_argument_group('Video Control')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_bool_argument('--crop', default=Auto, help='cropping video')
    xgroup.add_argument('--crop-wh', default=argparse.SUPPRESS, type=int, nargs=2, help='force cropping dimensions (centered)')
    xgroup.add_argument('--crop-whlt', default=argparse.SUPPRESS, type=int, nargs=4, help='force cropping dimensions')
    pgroup.add_bool_argument('--parallel-chapters', default=False, help='per-chapter parallel processing')
    pgroup.add_argument('--cropdetect-duration', type=qip.utils.Timestamp, default=qip.utils.Timestamp(300), help='cropdetect duration (seconds)')
    pgroup.add_bool_argument('--cropdetect-skip-frame-nokey', default=True, help='cropdetect skipping of frames w/o keys')
    pgroup.add_argument('--video-language', '--vlang', type=isolang_or_None, default=isolang('und'), help='Override video language (mux)')
    pgroup.add_argument('--video-rate-control-mode', default='CQ', choices=('Q', 'CQ', 'CBR', 'VBR', 'lossless'), help='Rate control mode: Constant Quality (Q), Constrained Quality (CQ), Constant Bit Rate (CBR), Variable Bit Rate (VBR), lossless')
    pgroup.add_argument('--force-framerate', default=argparse.SUPPRESS, type=FrameRate, help='Ignore heuristics and force framerate')
    pgroup.add_argument('--force-input-framerate', default=argparse.SUPPRESS, type=FrameRate, help='Force input framerate')
    pgroup.add_argument('--force-output-framerate', default=argparse.SUPPRESS, type=FrameRate, help='Force output framerate')
    pgroup.add_argument('--force-field-order', default=argparse.SUPPRESS, choices=('progressive', 'tt', 'tb', 'bb', 'bt', '23pulldown', 'auto-interlaced'), help='Ignore heuristics and force input field order')
    pgroup.add_argument('--video-analyze-duration', type=qip.utils.Timestamp, default=qip.utils.Timestamp(60), help='video analysis duration (seconds)')
    pgroup.add_argument('--video-analyze-skip-frames', type=int, default=10, help='number of frames to skip from video analysis')
    pgroup.add_argument('--limit-duration', type=qip.utils.Timestamp, default=argparse.SUPPRESS, help='limit conversion duration (for testing purposes)')
    pgroup.add_bool_argument('--force-still-video', default=False, help='Force still image video (single frame)')

    pgroup = app.parser.add_argument_group('Subtitle Control')
    pgroup.add_argument('--subrip-matrix', default=Auto, type=_resolved_Path, help='SubRip OCR matrix file')
    pgroup.add_bool_argument('--external-subtitles', help='exporting unoptimized subtitles as external files')

    pgroup = app.parser.add_argument_group('Files')
    pgroup.add_argument('--output', '-o', dest='output_file', default=Auto, type=Path, help='specify the output (demuxed) file name')
    pgroup.add_bool_argument('--remux', help='remux original files')
    pgroup.add_bool_argument('--auto-verify', help='Auto-verify created files')

    pgroup = app.parser.add_argument_group('Compatibility')
    pgroup.add_bool_argument('--webm', default=Auto, help='webm output format')
    pgroup.add_bool_argument('--ffv1', default=False, help='lossless ffv1 video codec')
    pgroup.add_argument('--media-library-app', '--app', default='plex', choices=['emby', 'plex'], help='App compatibility mode')

    pgroup = app.parser.add_argument_group('Encoding')
    pgroup.add_argument('--keyint', type=int, default=5, help='keyframe interval (seconds)')
    pgroup.add_bool_argument('--audio-track-titles', default=False, help='Include titles for all audio tracks')

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
    pgroup.add_argument('--comment', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--part', dest='part_slash_parts', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--parttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--disk', '--disc', dest='disk_slash_disks', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--track', dest='track_slash_tracks', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--picture', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--tvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--season', dest='season_slash_seasons', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--episode', dest='episode_slash_episodes', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--language', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--country', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--compilation', '-K', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-grouping', dest='sortgrouping', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumartist', dest='sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumtitle', '--sort-album', dest='sortalbumtitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-artist', dest='sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-title', '--sort-song', dest='sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-composer', '--sort-writer', dest='sortcomposer', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-tvshow', dest='sorttvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--xid', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)

    pgroup = app.parser.add_argument_group('Options')
    pgroup.add_bool_argument('--beep', default=False, help='beep when done')
    pgroup.add_bool_argument('--eject', default=False, help='ejecting cdrom when done')
    pgroup.add_argument('--project', default=Auto, help='project name')
    pgroup.add_bool_argument('--chain', help='chaining actions toward demux')
    pgroup.add_bool_argument('--cleanup', help='cleaning up when done')
    pgroup.add_bool_argument('--rename', default=True, help='rename files (such as when tagging episode files)')
    pgroup.add_argument('--chop-chapters', dest='chop_chaps', nargs='+', default=argparse.SUPPRESS, type=int, help='List of chapters to chop at')

    pgroup = app.parser.add_argument_group('Music extraction')
    pgroup.add_argument('--skip-chapters', dest='num_skip_chapters', type=int, default=0, help='number of chapters to skip')
    pgroup.add_argument('--bitrate', type=int, default=argparse.SUPPRESS, help='force the encoding bitrate')  # TODO support <int>k
    pgroup.add_argument('--target-bitrate', type=int, default=argparse.SUPPRESS, help='specify the resampling target bitrate')
    pgroup.add_argument('--channels', type=int, default=argparse.SUPPRESS, help='force the number of audio channels')

    pgroup = app.parser.add_argument_group('Actions')
    pgroup.add_argument('--rip-iso', dest='rip_iso', nargs='+', default=(), type=Path, help='iso file to rip device to')
    pgroup.add_argument('--rip', dest='rip_dir', nargs='+', default=(), type=Path, help='directory to rip device to')
    pgroup.add_argument('--backup', dest='backup_dir', nargs='+', default=(), type=Path, help='directory to backup device to')
    pgroup.add_argument('--hb', dest='hb_files', nargs='+', default=(), type=Path, help='files to run through HandBrake')
    pgroup.add_argument('--mux', dest='mux_files', nargs='+', default=(), type=Path, help='files to mux')
    pgroup.add_argument('--verify', dest='verify_files', nargs='+', default=(), type=Path, help='files to verify')
    pgroup.add_argument('--update', dest='update_dirs', nargs='+', default=(), type=Path, help='directories to update mux parameters for')
    pgroup.add_argument('--chop', dest='chop_dirs', nargs='+', default=(), type=Path, help='files/directories to chop into chapters')
    pgroup.add_argument('--extract-music', dest='extract_music_dirs', nargs='+', default=(), type=Path, help='directories to extract music from')
    pgroup.add_argument('--optimize', dest='optimize_dirs', nargs='+', default=(), type=Path, help='directories to optimize')
    pgroup.add_argument('--demux', dest='demux_dirs', nargs='+', default=(), type=Path, help='directories to demux')
    pgroup.add_argument('--merge', dest='merge_files', nargs='+', default=(), type=Path, help='files to merge')
    pgroup.add_argument('--tag-episodes', dest='tag_episodes_files', nargs='+', default=(), type=Path, help='files to tag based on tvshow episodes')
    pgroup.add_argument('--pick-title-streams', dest='pick_title_streams_dirs', nargs='+', default=(), type=Path, help='directories to pick title streams from')
    pgroup.add_argument('--status', '--print', dest='status_dirs', nargs='+', default=(), type=Path, help='directories to print the status of')

    app.parse_args()

    if in_tags.type is None:
        try:
            in_tags.type = in_tags.deduce_type()
        except qip.mm.MissingMediaTagError:
            pass

    if app.args.webm is Auto:
        if app.args.ffv1:
            app.args.webm = False
        else:
            app.args.webm = True

    # if getattr(app.args, 'action', None) is None:
    #     app.args.action = TODO
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    if False and app.args.cuda:
        default_ffmpeg_args += [
            '-hwaccel', 'nvdec',
        ]

    global thread_executor
    global slurm_executor
    with contextlib.ExitStack() as exit_stack:
        thread_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=None if app.args.jobs is Auto else app.args.jobs)
        exit_stack.enter_context(thread_executor)
        if app.args.slurm and app.args.jobs == 1:
            slurm_executor = concurrent.futures.ThreadPoolExecutor(max_workers=float("inf"))
            exit_stack.enter_context(slurm_executor)
        else:
            slurm_executor = thread_executor

        did_something = False
        for rip_iso in  app.args.rip_iso:
            action_rip_iso(rip_iso, app.args.device, in_tags=in_tags)
            did_something = True
        for backup_dir in  app.args.backup_dir:
            action_backup(backup_dir, app.args.device, in_tags=in_tags)
            did_something = True
        for rip_dir in  app.args.rip_dir:
            action_rip(rip_dir, app.args.device, in_tags=in_tags)
            did_something = True
        for backup_dir in  app.args.pick_title_streams_dirs:
            action_pick_title_streams(backup_dir, in_tags=in_tags)
            did_something = True
        for inputfile in getattr(app.args, 'hb_files', ()):
            action_hb(inputfile, in_tags=in_tags)
            did_something = True
        for inputfile in getattr(app.args, 'mux_files', ()):
            action_mux(inputfile, in_tags=in_tags)
            did_something = True
        for inputfile in getattr(app.args, 'verify_files', ()):
            action_verify(inputfile, in_tags=in_tags)
            did_something = True
        for inputdir in getattr(app.args, 'update_dirs', ()):
            action_update(inputdir, in_tags=in_tags)
            did_something = True
        for inputdir in getattr(app.args, 'chop_dirs', ()):
            action_chop(inputdir, in_tags=in_tags, chop_chaps=getattr(app.args, 'chop_chaps', None))
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
        if getattr(app.args, 'merge_files', ()):
            action_merge(app.args.merge_files, in_tags=in_tags)
            did_something = True
        if getattr(app.args, 'tag_episodes_files', ()):
            action_tag_episodes(app.args.tag_episodes_files, in_tags=in_tags)
            did_something = True
        for inputdir in getattr(app.args, 'status_dirs', ()):
            action_status(inputdir)
            did_something = True
        if not did_something:
            raise ValueError('Nothing to do!')
        if num_batch_skips:
            raise Exception(f'BATCH MODE SKIP: {num_batch_skips} actions skipped.')

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
            '.vc1.avi',
            '.h264',
            '.h265',
            '.vp8',
            '.vp8.ivf',
            '.vp9',
            '.vp9.ivf',
            '.ac3',
            '.mp3',
            '.dts',
            '.truehd',
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

still_image_exts = {
    '.png',
    '.jpg', '.jepg',
}

def codec_name_to_ext(codec_name):
    try:
        codec_ext = {
            # video
            'rawvideo': '.y4m',
            'mpeg2video': '.mpeg2.mp2v',
            'mp2': '.mpeg2.mp2v',
            'ffv1': '.ffv1.mkv',
            #'mjpeg': '.mjpeg',
            'msmpeg4v3': '.msmpeg4v3.avi',
            'mpeg4': '.mp4',
            'vc1': '.vc1.avi',
            'h264': '.h264',
            'h265': '.h265',
            'vp8': '.vp8.ivf',
            'vp9': '.vp9.ivf',
            # image
            'png': '.png',
            # audio
            'ac3': '.ac3',
            'mp3': '.mp3',
            'dts': '.dts',
            'truehd': '.truehd',
            'opus': '.opus.ogg',
            'aac': '.aac',
            'pcm_s16le': '.wav',
            'pcm_s24le': '.wav',
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
    ext = (Path('x' + ext) if isinstance(ext, str) else toPath(ext)).suffix
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
            #'.truehd': 'truehd',
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

def ext_to_codec(ext, lossless=False):
    ext = my_splitext('x' + ext, strip_container=True)[1]
    try:
        ext_container = {
            # video
            '.ffv1': 'ffv1',
            '.h264': ('h264_nvenc' if app.args.cuda and lossless
                      else 'libx264'),  # better quality
            '.vp9': 'libvpx-vp9',
            '.y4m': 'yuv4',
            '.mpeg2': 'mpeg2video',
            '.mpegts': 'mpeg2video',
            '.vc1': 'vc1',
        }[ext]
    except KeyError as err:
        raise ValueError('Unsupported extension %r' % (ext,)) from err
    return ext_container

def ext_to_codec_args(ext, lossless=False):
    codec = ext_to_codec(ext, lossless=lossless)
    codec_args = []
    if codec == 'ffv1':
        codec_args += [
            '-slices', 24,
            '-threads', 8,
        ]
    if codec in ('h264_nvenc',):
        if lossless:
            codec_args += [
                '-surfaces', 8,  # https://github.com/keylase/nvidia-patch -- Avoid CreateBitstreamBuffer failed: out of memory (10)
            ]
    if codec in ('h264_nvenc', 'libx264'):
        if lossless:
            codec_args += [
                '-preset', 'lossless',
            ]
    return codec_args

def codec_to_input_args(codec):
    codec_args = []
    if codec in ('h264_nvenc',):
        codec_args += [
            '-hwaccel', 'nvdec',
        ]
    return codec_args

def ext_to_mencoder_libavcodec_format(ext):
    ext = (Path('x' + ext) if isinstance(ext, str) else toPath(ext)).suffix
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
            #return 33 if mq else 34
            return 32 if mq else 33
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

def adjust_start_time(start_time, *, codec_encoding_delay, stream_time_base):
    start_time = ffmpeg.Timestamp(start_time)
    if start_time < 0 and start_time == (
            stream_time_base * round_half_away_from_zero(-codec_encoding_delay / stream_time_base)
    ):
        start_time = ffmpeg.Timestamp(0)
    else:
        start_time += codec_encoding_delay
    return start_time

def estimate_stream_duration(ffprobe_json):
    try:
        ffprobe_format_json = ffprobe_json['format']
    except KeyError:
        pass
    else:
        try:
            estimated_duration = ffmpeg.Timestamp(ffprobe_format_json['duration'])
            if estimated_duration >= 0.0:
                return estimated_duration
        except KeyError:
            pass
    try:
        ffprobe_stream_json, = ffprobe_json['streams']
    except ValueError:
        pass
    else:
        try:
            estimated_duration = ffmpeg.Timestamp(ffprobe_stream_json['duration'])
            if estimated_duration >= 0.0:
                return estimated_duration
        except KeyError:
            pass
        try:
            estimated_duration = int(ffprobe_stream_json['tags']['NUMBER_OF_FRAMES'])
            if estimated_duration > 0:
                return estimated_duration
        except KeyError:
            pass
        try:
            estimated_duration = int(ffprobe_stream_json['tags']['NUMBER_OF_FRAMES-eng'])
            if estimated_duration > 0:
                return estimated_duration
        except KeyError:
            pass
    return None

def init_inputfile_tags(inputfile, in_tags, ffprobe_dict=None, mediainfo_dict=None):

    inputfile_base, inputfile_ext = my_splitext(inputfile)
    inputfile.tags.update(inputfile.load_tags())
    inputfile.tags.pop('type', None)

    name_scan_str = Path(inputfile_base).name
    name_scan_str = name_scan_str.strip()
    # title_t00 -> 0
    name_scan_str = re.sub(r'_t0\d+$', '', name_scan_str)
    # FILE_NAME -> FILE NAME
    name_scan_str = re.sub(r'_', ' ', name_scan_str)
    # FILE   NAME -> FILE NAME
    name_scan_str = re.sub(r'\s+', ' ', name_scan_str)
    # FILE NAME ALL CAPS -> File Name All Caps
    if re.match(r'^[A-Z0-9]+( [A-Z0-9]+)*$', name_scan_str):
        name_scan_str = name_scan_str.title()
    done = False
    m = not done and (
        # music video: ARTIST -- TITLE
        re.match(r'^(?:musicvideo|music video): (?P<artist>.+?) -- (?P<title>.+)$', name_scan_str)
    )
    if m:
        d = m.groupdict()
        d = {k: v and v.strip() for k, v in d.items()}
        inputfile.tags.type = 'musicvideo'
        inputfile.tags.update(d)
        name_scan_str = inputfile.tags.title
        # done = False
    m = not done and (
        # TVSHOW S01E02 TITLE
        # TVSHOW S01E02-03 TITLE
        # TVSHOW S01E02
        # TVSHOW S01E02-03
        re.match(r'^(?P<tvshow>.+) S(?P<season>\d+)E(?P<str_episodes>\d+(?:-?E\d+)*)(?: (?P<title>.+))?$', name_scan_str)
        # TVSHOW 1x2 TITLE
        # TVSHOW 1x2-3 TITLE
        # TVSHOW -- 1x2 TITLE
        # TVSHOW 1x2
        # TVSHOW -- 1x2
        or re.match(r'^(?P<tvshow>.+) (?:-- )?(?P<season>\d+)x(?P<str_episodes>\d+(?:-?\d+)*)(?: (?P<title>.+))?$', name_scan_str)
        # TVSHOW -- TITLE 1x2
        # TVSHOW -- TITLE 1x2-3
        or re.match(r'^(?P<tvshow>.+) -- (?P<title>.+) (?P<season>\d+)x(?P<str_episodes>\d+(?:-?\d+)*)$', name_scan_str)
        # TITLE
        or re.match(r'^(?P<title>.+)$', name_scan_str)
    )
    if m:
        d = m.groupdict()
        d = {k: v and v.strip() for k, v in d.items()}
        try:
            if d['title'] in (None, 'title'):
                del d['title']
        except KeyError:
            pass
        try:
            str_episodes = d.pop('str_episodes')
        except KeyError:
            pass
        else:
            d['episode'] = [int(e) for e in str_episodes.replace('-', '').split('E') if e]
        try:
            if d['episode'] == [0]:
                d['episode'] = None
        except KeyError:
            pass
        if 'title' in d:
            # TITLE -- CONTENTTYPE: COMMENT
            # TITLE -- CONTENTTYPE
            # CONTENTTYPE: COMMENT
            # CONTENTTYPE
            m = re.match(r'^(?:(?P<title>.+) -- )?(?P<contenttype>[^:]+)(?:: (?P<comment>.+))?$', d['title'])
            if m:
                try:
                    d['contenttype'] = ContentType(m.group('contenttype').strip())
                except ValueError as err:
                    app.log.debug('err=%r', err)
                    pass
                else:
                    d['comment'] = (m.group('comment') or '').strip() or None
                    d['title'] = (m.group('title') or '').strip() or None
                    if not d['title']:
                        del d['title']
        if 'title' in d:
            # TITLE - part 1
            m = re.match('^(?P<title>.+) *- *part *(?P<part>\d+)$', d['title'])
            if m:
                d.update(m.groupdict())
        if 'title' in d:
            # TITLE (1987)
            m = re.match('^(?P<title>.+) \((?P<date>\d{4})\)$', d['title'])
            if m:
                d.update(m.groupdict())
        for tag in (
                'title',
                'tvshow',
                'comment',
        ):
            try:
                v1, v2 = d[tag] or '', inputfile.tags[tag] or ''
            except KeyError:
                continue
            if type(v2) is tuple:
                v2 = v2[0]
            if clean_file_name(v1, keep_ext=False) == clean_file_name(v2, keep_ext=False):
                del d[tag]
        inputfile.tags.update(d)
        done = True

    if inputfile.exists():
        inputfile.tags.update(inputfile.load_tags())
        if inputfile_ext in (
                '.mkv',
                '.webm',
                ):
            if mediainfo_dict is None:
                mediainfo_dict = inputfile.extract_mediainfo_dict()
            mediainfo_video_track_dicts = [mediainfo_track_dict
                    for mediainfo_track_dict in mediainfo_dict['media']['track']
                    if mediainfo_track_dict['@type'] == 'Video']
            if len(mediainfo_video_track_dicts) > 1:
                # TODO support angles!
                mediainfo_video_track_dicts = mediainfo_video_track_dicts[:1]
            assert len(mediainfo_video_track_dicts) == 1, "%d video tracks found" % (len(mediainfo_video_track_dicts),)
            mediainfo_track_dict, = mediainfo_video_track_dicts
            mediainfo_mediatype = mediainfo_track_dict.get('OriginalSourceMedium', None)
            if mediainfo_mediatype is None:
                pass
            elif mediainfo_mediatype == 'DVD-Video':
                inputfile.tags.mediatype = 'DVD'
            elif mediainfo_mediatype == 'Blu-ray':
                inputfile.tags.mediatype = 'BD'
            else:
                raise NotImplementedError(mediainfo_mediatype)

    inputfile.tags.update(in_tags)
    inputfile.tags.type = inputfile.deduce_type()

def do_edit_tags(tags):

    # for tag in set(MediaTagEnum) - set(MediaTagEnum.iTunesInternalTags):
    for tag in (
            MediaTagEnum.grouping,
            MediaTagEnum.language,
            MediaTagEnum.artist,
            MediaTagEnum.contenttype,
            MediaTagEnum.comment,
            MediaTagEnum.episode,
            MediaTagEnum.episodes,
            MediaTagEnum.genre,
            MediaTagEnum.mediatype,
            MediaTagEnum.season,
            MediaTagEnum.seasons,
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

def action_rip_iso(rip_iso, device, in_tags):
    app.log.info('Ripping %s from %s...', rip_iso, device)

    if rip_iso.suffix != '.iso':
        raise ValueError(f'File is not a .iso: {rip_iso}')

    iso_file = BinaryFile(rip_iso)
    log_file = TextFile(rip_iso.with_suffix('.log'))

    if app.args.check_cdrom_ready:
        if not cdrom_ready(device, timeout=app.args.cdrom_ready_timeout, progress_bar=True):
            raise Exception("CDROM not ready")

    app.log.info('Identifying mounted media type...')
    out = dbg_exec_cmd(['dvd+rw-mediainfo', app.args.device], dry_run=False)
    out = clean_cmd_output(out)
    m = re.search(r'Mounted Media: .*(BD|DVD)', out)
    if not m:
        raise ValueError('Unable to identify mounted media type')
    media_type = MediaType(m.group(1))

    if media_type is MediaType.DVD:
        app.log.info('Decrypting DVD...')
        cmd = [
            'mplayer',
            f'dvd://1/{device.resolve()}',
            '-endpos', 1,
            '-vo', 'null',
            '-ao', 'null',
        ]
        dbg_exec_cmd(cmd)

    stage = app.args.stage
    if stage is Auto:
        if not iso_file.exists():
            stage = 1
        else:
            # TODO
            stage = 2

    # See `info ddrescue`
    if stage == 1:
        ddrescue_args = [
            # Sector size of input device
            '-b', 2048,
            # Skip the scraping phase
            '-n',
            device,
            iso_file, log_file,
        ]
    elif stage == 2:
        ddrescue_args = [
            # Sector size of input device
            '-b', 2048,
        ]
        if not app.args._continue:
            ddrescue_args += [
                # Mark all failed blocks as non-trimmed
                '-M',
                # Start from 0
                '-i', 0,
            ]
        ddrescue_args += [
            device,
            iso_file, log_file,
        ]
    elif stage == 3:
        ddrescue_args = [
            # Sector size of input device
            '-b', 2048,
            # Use direct disc access for input file; This requires correct sector size
            '-d',
            # Exit after 3 retry passes
            '-r', 3,
            device,
            iso_file, log_file,
        ]
    else:
        raise NotImplementedError(f'Unsupported ripping stage {stage}')

    ddrescue(*ddrescue_args)

def action_rip(rip_dir, device, in_tags):
    app.log.info('Ripping %s from %s...', rip_dir, device)

    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', list2cmdline(['mkdir', rip_dir]))
    else:
        os.mkdir(rip_dir)

    minlength = app.args.minlength
    if minlength is Auto:
        if in_tags.type == 'tvshow':
            minlength = default_minlength_tvshow
        else:
            minlength = default_minlength_movie

    from qip.makemkv import makemkvcon

    # See ~/.MakeMKV/settings.conf
    profile_xml = makemkvcon.get_profile_xml()
    eMkvSettings = profile_xml.find('mkvSettings')
    eMkvSettings.set('ignoreForcedSubtitlesFlag', 'false')
    eProfileSettings = profile_xml.find('profileSettings')
    eProfileSettings.set('app_DefaultSelectionString', '+sel:all,-sel:(audio|subtitle),+sel:(nolang|eng|fra|fre),-sel:core,-sel:mvcvideo,=100:all,-10:favlang')

    settings_changed = False
    makemkvcon_settings = makemkvcon.read_settings_conf()
    orig_makemkvcon_settings = makemkvcon.read_settings_conf()

    dvd_SPRemoveMethod = {
        'auto': (None, '0'),
        'CellWalk': ('1',),
        'CellTrim': ('2',),
    }[app.args.sp_remove_method]
    if makemkvcon_settings.get('dvd_SPRemoveMethod', None) not in dvd_SPRemoveMethod:
        if dvd_SPRemoveMethod[0] is None:
            del makemkvcon_settings['dvd_SPRemoveMethod']
        else:
            makemkvcon_settings['dvd_SPRemoveMethod'] = dvd_SPRemoveMethod[0]
        settings_changed = True

    if device.is_block_device():
        if app.args.check_cdrom_ready:
            if not cdrom_ready(device, timeout=app.args.cdrom_ready_timeout, progress_bar=True):
                raise Exception("CDROM not ready")
        source = f'dev:{device.resolve()}'  # makemkv is picky
    else:
        if device.suffix != '.iso':
            raise ValueError(f'File is not a .iso: {device}')
        source = f'iso:{os.fspath(device)}'

    if not app.args.dry_run and settings_changed:
        app.log.warning('Changing makemkv settings!')
        makemkvcon.write_settings_conf(makemkvcon_settings)
    try:

        with TempFile.mkstemp(text=True, suffix='.profile.xml') as tmp_profile_xml_file:
            profile_xml.write(tmp_profile_xml_file.file_name,
                #encoding='unicode',
                xml_declaration=True,
                )

            try:
                rip_info = makemkvcon.mkv(
                    source=source,
                    dest_dir=rip_dir,
                    minlength=int(minlength),
                    profile=tmp_profile_xml_file,
                    #retry_no_cd=device.is_block_device(),
                    noscan=True,
                    robot=True,
                )
            except:
                if app.args.dry_run:
                    app.log.verbose('CMD (dry-run): %s', list2cmdline(['rmdir', rip_dir]))
                else:
                    try:
                        os.rmdir(rip_dir)
                    except OSError:
                        pass
                    else:
                        app.log.info('Ripping failed; Removed %s.', rip_dir)
                raise

    finally:
        if not app.args.dry_run and settings_changed:
            app.log.warning('Restoring makemkv settings!')
            makemkvcon.write_settings_conf(orig_makemkvcon_settings)

    if not app.args.dry_run:
        for title_no, angle_no in rip_info.spawn.angles:
            pass
        app.log.debug('rip_info.spawn.angles=%r', rip_info.spawn.angles)

    if app.args.eject and device.is_block_device():
        app.log.info('Ejecting...')
        cmd = [
            shutil.which('eject'),
            device,
        ]
        out = do_spawn_cmd(cmd)

    if app.args.chain:
        with os.scandir(rip_dir) as it:
            for entry in it:
                entry_path = rip_dir / entry_path
                assert entry_path.suffix in ('.mkv', '.webm')
                assert entry.is_file()
                app.args.mux_files += (entry_path,)

def action_pick_title_streams(backup_dir, in_tags):

    makemkvcon_info_file = TextFile(backup_dir / 'makemkvcon.info.txt')
    makemkvcon_orders_file = TextFile(backup_dir / 'makemkvcon.orders.txt')

    from qip.makemkv import makemkvcon
    makemkvcon_info_func = functools.partial(
        makemkvcon.info,
        source=f'file:{os.fspath(backup_dir)}',
        noscan=True,
        robot=True,
    )
    if not makemkvcon_info_file.exists():
        disc_info = makemkvcon_info_func()
        with makemkvcon_info_file.open('w') as fp:
            fp.write(disc_info.out)
    else:
        disc_info = makemkvcon_info_func(
            fd=makemkvcon_info_file.open('rt'))

    time_offset = qip.utils.Timestamp(0)
    titles = sorted(disc_info.spawn.titles.values(),
                    key=operator.attrgetter('stream_nos', 'id'))
    assert len(titles) > 0
    stream_nos = ()

    def pick_a_title(titles):
        i = app.radiolist_dialog(
            title='Pick a title',
            values=[(i, f'{title.title}: {title.stream_nos_str} ({title.duration}, {title.info_str})')
                    for i, title in enumerate(titles)],
        )
        if i is None:
            raise ValueError('Cancelled by user!')
        return titles[i]

    def is_the_right_stream(stream_file, time_offset):
        from prompt_toolkit.completion import WordCompleter
        completer = WordCompleter([
            'help',
            'yes',
            'no',
            'open',
        ])
        print('')
        for i in itertools.count():
            app.print(f'Is {stream_file} the right stream at offset {time_offset}?')
            if i == 0:
                try:
                    xdg_open(stream_file)
                except Exception as e:
                    app.log.error(e)
            c = app.prompt(completer=completer)
            if c in ('help', 'h', '?'):
                print('')
                print('List of commands:')
                print('')
                print('help -- Print this help')
                print('yes -- Yes, this is the right stream')
                print('no -- No, this is not the right stream')
                print('open -- Open this stream -- done')
                print('quit -- quit')
                print('')
            elif c in ('yes', 'y'):
                return True
            elif c in ('no', 'n'):
                return False
            elif c in ('open',):
                try:
                    xdg_open(stream_file)
                except Exception as e:
                    app.log.error(e)
            elif c in ('quit', 'q'):
                raise ValueError('Quit by user')
            else:
                app.log.error('Invalid input')

    with app.need_user_attention():
        while True:
            picked_title = pick_a_title(titles)
            if picked_title.stream_nos == stream_nos:
                break
            next_stream_no = picked_title.stream_nos[len(stream_nos)]
            stream_file = MediaFile.new_by_file_name(backup_dir / 'BDMV' / 'STREAM' / '{:05d}.m2ts'.format(next_stream_no))
            if is_the_right_stream(stream_file, time_offset):
                ffprobe_dict = stream_file.extract_ffprobe_json()
                time_offset += ffmpeg.Timestamp(ffprobe_dict['format']['duration'])
                stream_nos += (next_stream_no,)
                titles = [title
                          for title in titles
                          if title.stream_nos[:len(stream_nos)] == stream_nos]

    app.log.info('Picked title: %s', picked_title)
    app.log.info('Picked title attributes: %r', picked_title.attributes)
    return True

def action_backup(backup_dir, device, in_tags):
    app.log.info('Backing up %s from %s...', backup_dir, device)

    if backup_dir.is_dir():
        raise OSError(errno.EEXIST, backup_dir)

    from qip.makemkv import makemkvcon
    decrypt = app.args.decrypt
    discatt_dat_file = None

    try:

        if device.is_block_device():

            if app.args.check_cdrom_ready:
                if not cdrom_ready(device, timeout=app.args.cdrom_ready_timeout, progress_bar=True):
                    raise Exception("CDROM not ready")
            try:
                drive_info = makemkvcon.device_to_drive_info(device)
            except ValueError:
                if not app.args.dry_run:
                    raise
                drive_info = types.SimpleNamespace(index=0)
            source = f'disc:{drive_info.index}'

            makemkvcon.backup(
                source=source,
                dest_dir=backup_dir,
                decrypt=decrypt,
                retry_no_cd=True,
                noscan=True,
                robot=True,
            )

        else:

            if device.suffix != '.iso':
                raise ValueError(f'File is not a .iso: {device}')

            discatt_dat_file = device.with_suffix('.discatt.dat')
            if discatt_dat_file.exists():
                app.log.info('%s file found.', discatt_dat_file)
                # decrypt = True
            else:
                app.log.warning('%s file not found.', discatt_dat_file)
                discatt_dat_file = None
                # decrypt = False

            app.log.info('Mounting %s.', device)
            from qip.lodev import LoopDevice
            #with LoopDevice.context_from_file(device) as lodev:
            with udisksctl.loop_context(file=device) as lodev:
                with udisksctl.mount_context(block_device=lodev) as mountpoint:

                    app.log.info('Copying %s to %s...', mountpoint, backup_dir)
                    shutil.copytree(src=mountpoint, dst=backup_dir,
                                    dirs_exist_ok=False)

            app.log.info('Setting write permissions...')
            do_exec_cmd(['chmod', '-R', 'u+w', backup_dir])

            if discatt_dat_file is not None:
                app.log.info('Copying %s...', backup_dir / 'discatt.dat')
                shutil.copyfile(src=discatt_dat_file, dst=backup_dir / 'discatt.dat')

    except:
        if app.args.dry_run:
            app.log.verbose('CMD (dry-run): %s', list2cmdline(['rmdir', backup_dir]))
        else:
            try:
                os.rmdir(backup_dir)
            except OSError:
                pass
            else:
                app.log.info('Ripping failed; Removed %s.', backup_dir)
        raise

    if app.args.eject and device.is_block_device():
        app.log.info('Ejecting...')
        cmd = [
            shutil.which('eject'),
            device,
        ]
        out = do_spawn_cmd(cmd)

    if app.args.chain:
        with os.scandir(backup_dir) as it:
            for entry in it:
                entry_path = backup_dir / entry.name
                assert entry_path.suffix in ('.mkv', '.webm')
                assert entry.is_file()
                app.args.mux_files += (entry_path,)

def pick_field_order(stream_file_name, ffprobe_json, ffprobe_stream_json, mediainfo_track_dict):
    if getattr(app.args, 'force_field_order', None) is not None:
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
    if getattr(app.args, 'force_framerate', None) is not None:
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

    rounded_ffprobe_avg_framerate = ffprobe_avg_framerate  # ffprobe_avg_framerate.round_common(delta=0.002)
    assert (
        ffprobe_r_framerate == rounded_ffprobe_avg_framerate
        or ffprobe_r_framerate == rounded_ffprobe_avg_framerate * 2), \
        f'ffprobe says r_frame_rate is {ffprobe_r_framerate} after interlace adjustment avg_frame_rate is {ffprobe_avg_framerate} (~{rounded_ffprobe_avg_framerate}); Which is it? (Use --force-framerate)'
    framerate = rounded_ffprobe_avg_framerate

    if mediainfo_format in ('FFV1',):
        # mediainfo's ffv1 framerate is all over the place (24 instead of 23.976 for .ffv1.mkv and total number of frames for .ffv1.avi)
        pass
    else:
        assert mediainfo_original_framerate is None \
            or mediainfo_framerate == mediainfo_original_framerate, \
            (ffprobe_r_framerate, rounded_ffprobe_avg_framerate, mediainfo_framerate, mediainfo_original_framerate)
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

def chop_chapters(chaps,
                  inputfile,
                  chapter_file_ext=None,
                  chapter_lossless=True,
                  reset_timestamps=True,
                  chop_chaps=None):
    if not isinstance(inputfile, MediaFile):
        inputfile = MediaFile.new_by_file_name(inputfile)
    inputfile_base, inputfile_ext = my_splitext(inputfile)
    if chapter_file_ext is None:
        chapter_file_ext = inputfile_ext

    chapter_file_name_pat = '%s-chap%%02d%s' % (inputfile_base.replace('%', '%%'),
                                                chapter_file_ext.replace('%', '%%'))

    if chop_chaps is not None:
        chaps_list = []
        todo_chaps = list(chaps)
        for chop_chap_no in sorted(chop_chaps):
            sub_chaps = []
            while todo_chaps and todo_chaps[0].no < chop_chap_no:
                # < chap_no
                sub_chaps.append(todo_chaps.pop(0))
            if sub_chaps:
                chaps_list.append(Chapters(chapters=sub_chaps))
        if todo_chaps:
            # >= chap_no
            chaps_list.append(Chapters(chapters=todo_chaps))
    else:
        chaps_list = [Chapters(chapters=[chap]) for chap in chaps]

    ffmpeg_input_args = []
    codec_args = []

    if (
            (chapter_file_ext == inputfile_ext
             or ext_to_codec(chapter_file_ext) == ext_to_codec(inputfile_ext))
            and not (chapter_lossless and inputfile_ext in ('.h264',))):  # h264 copy just spits out a single empty chapter
        codec = 'copy'
    else:
        codec = ext_to_codec(chapter_file_ext, lossless=chapter_lossless)
    ffmpeg_input_args += codec_to_input_args(codec)
    codec_args += [
        '-codec', codec,
    ]
    if codec != 'copy':
        codec_args += ext_to_codec_args(chapter_file_ext, lossless=chapter_lossless)

    chaps_list_copy = copy.deepcopy(chaps_list)
    chaps_list_copy[-1].chapters[-1].end = ffmpeg.Timestamp.MAX  # Make sure whole movie is captured
    ffmpeg_args = default_ffmpeg_args + ffmpeg_input_args + [
        '-fflags', '+genpts',
        '-i', inputfile,
        '-segment_times', ','.join(str(ffmpeg.Timestamp(sub_chaps.chapters[-1].end))
                                   for sub_chaps in chaps_list_copy),
        '-segment_start_number', chaps_list_copy[0].chapters[0].no,
        '-map', '0',
        '-map_chapters', '-1',
    ] + codec_args + [
        '-f', 'ssegment',
        '-segment_format', ext_to_container(chapter_file_ext),
    ]
    if reset_timestamps:
        ffmpeg_args += [
            '-reset_timestamps', 1,
        ]
    ffmpeg_args += [
        chapter_file_name_pat,
    ]
    with perfcontext('Chop w/ ffmpeg segment muxer'):
        ffmpeg(*ffmpeg_args,
               dry_run=app.args.dry_run,
               y=app.args.yes)

    for segment_number_offset, sub_chaps in reversed(list(enumerate(chaps_list))):
        segment_number = chaps_list[0].chapters[0].no + segment_number_offset
        chopped_file = MediaFile.new_by_file_name(chapter_file_name_pat % (segment_number,))
        if segment_number != sub_chaps.chapters[0].no:
            chopped_file.move(chapter_file_name_pat % (sub_chaps.chapters[0].no,))
        if len(sub_chaps.chapters) > 1:
            sub_chaps -= Chapter(
                start=sub_chaps.chapters[0].start, end=None,
                no=sub_chaps.chapters[0].no - 1)
            chapters_xml = sub_chaps.to_mkv_xml()
            if False and app.args.interactive:
                chapters_xml = edvar(chapters_xml,
                                     preserve_whitespace_tags=Chapters.MKV_XML_VALUE_TAGS)[1]
            chapters_xml_file = TempFile.mkstemp(suffix='.chapters.xml', open=True, text=True)
            chapters_xml.write(chapters_xml_file.fp,
                               xml_declaration=True,
                               encoding='unicode',  # Force string
                               )
            chapters_xml_file.close()

            cmd = [
                'mkvpropedit',
                chopped_file,
                '--chapters', chapters_xml_file,
            ]
            with perfcontext('add chapters w/ mkvpropedit'):
                do_spawn_cmd(cmd)

    return chapter_file_name_pat

    if False:
        for chap in chaps:
            app.log.verbose('Chapter %s', chap)

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
                ffmpeg_args = default_ffmpeg_args + [
                    '-start_at_zero', '-copyts',
                    '-i', inputdir / stream_file_name,
                    '-codec', 'copy',
                    '-ss', ffmpeg.Timestamp(chap.start),
                    '-to', ffmpeg.Timestamp(chap.end),
                    ]
                if force_format:
                    ffmpeg_args += [
                        '-f', force_format,
                        ]
                ffmpeg_args += [
                    inputdir / stream_chapter_file_name,
                    ]
                ffmpeg(*ffmpeg_args,
                       progress_bar_max=chap.end - chap.start,
                       progress_bar_title=f'Chop chapter {chap} w/ ffmpeg',
                       dry_run=app.args.dry_run,
                       y=app.args.yes)

def action_hb(inputfile, in_tags):
    app.log.info('HandBrake %s...', inputfile)
    inputfile = MediaFile.new_by_file_name(inputfile)
    inputfile_base, inputfile_ext = my_splitext(inputfile)
    outputfile_name = Path(inputfile_base + ".hb.mkv")
    if app.args.chain:
        app.args.mux_files += (outputfile_name,)

    if inputfile_ext in (
            '.mkv',
            '.webm',
            '.mpeg2',
            '.mpeg2.mp2v',
            ):
        ffprobe_dict = inputfile.extract_ffprobe_json()

        for stream_dict in sorted_stream_dicts(ffprobe_dict['streams']):
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

        #framerate = pick_framerate(inputfile, ffprobe_dict, stream_dict, mediainfo_track_dict)
        field_order, input_framerate, framerate = analyze_field_order_and_framerate(
            inputfile,
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
                   input=inputfile,
                   output=outputfile_name,
                   scan=True if app.args.dry_run else False,
                   json=True if app.args.dry_run else False,
                   dry_run=False,
                )

    else:
        raise ValueError('Unsupported extension %r' % (inputfile_ext,))

def action_mux(inputfile, in_tags,
               mux_attached_pic=True,
               mux_subtitles=True):
    app.log.info('Muxing %s...', inputfile)
    if not isinstance(inputfile, MediaFile):
        inputfile = MediaFile.new_by_file_name(inputfile)
    inputfile_base, inputfile_ext = my_splitext(inputfile)
    outputdir = Path(inputfile_base if app.args.project is Auto
                     else app.args.project)
    if app.args.chain:
        app.args.optimize_dirs += (outputdir,)

    remux = False
    if outputdir.is_dir():
        if app.args.remux:
            app.log.warning('Directory exists: %r; Just remuxing', outputdir)
            remux = True
        else:
            if app.args.chain:
                app.log.warning('Directory exists: %r; Just chaining', outputdir)
                return True
            elif app.args._continue:
                app.log.warning('Directory exists: %r; Ignoring', outputdir)
                return True
            else:
                raise OSError(errno.EEXIST, outputdir)

    mux_dict = {
        'streams': [],
        'chapters': {},
        #'tags': ...,
    }

    ffprobe_dict = None
    mediainfo_dict = None
    if inputfile_ext in (
            '.ffv1.mkv',
    ) \
            + Mp4File._common_extensions \
            + MkvFile._common_extensions \
            + WebmFile._common_extensions \
            :
        ffprobe_dict = inputfile.extract_ffprobe_json()
        mediainfo_dict = inputfile.extract_mediainfo_dict()

    init_inputfile_tags(inputfile,
                        in_tags=in_tags,
                        ffprobe_dict=ffprobe_dict,
                        mediainfo_dict=mediainfo_dict)
    mux_dict['tags'] = inputfile.tags

    if app.args.interactive and not remux and not (app.args.rip_dir and outputdir in app.args.rip_dir):
        with app.need_user_attention():
            from prompt_toolkit.formatted_text import FormattedText
            from prompt_toolkit.completion import WordCompleter
            completer = WordCompleter([
                'help',
                'edit',
                'search',
                'continue',
                'quit',
            ])
            print('')
            while True:
                print('Initial tags setup')
                c = app.prompt(completer=completer)
                if c in ('help', 'h', '?'):
                    print('')
                    print('List of commands:')
                    print('')
                    print('help -- Print this help')
                    print('edit -- Edit tags')
                    print('search -- Search The Movie DB')
                    print('continue -- Continue processing')
                    print('quit -- Quit')
                elif c in ('continue', 'c'):
                    break
                elif c in ('quit', 'q'):
                    exit(1)
                elif c in ('edit',):
                    mux_dict['tags'] = do_edit_tags(mux_dict['tags'])
                elif c in ('search',):
                    initial_text = mux_dict['tags'].title or inputfile.file_name.parent.name
                    initial_text = unmangle_search_string(initial_text)
                    if in_tags.language:
                        initial_text += f' [{in_tags.language}]'
                    search_query = app.input_dialog(
                        title=str(inputfile),
                        text='Please input search query:',
                        initial_text=initial_text)
                    if search_query is None:
                        print('Cancelled by user!')
                        continue
                    language = in_tags.language
                    m = re.match(r'^(?P<search_query>.+) \[(?P<language>\w+)\]', search_query)
                    if m:
                        try:
                            language = isolang(m.group('language'))
                        except ValueError:
                            pass
                        else:
                            search_query = m.group('search_query').strip()
                    if search_query:
                        global tmdb
                        global qip
                        import qip.tmdb
                        if tmdb is None:
                            tmdb = qip.tmdb.TMDb(
                                apikey='3f8dc1c8cf6cb292c267b3c10179ae84',  # mmdemux
                                interactive=app.args.interactive,
                                debug=app.log.isEnabledFor(logging.DEBUG),
                            )
                        tmdb.language = language
                        movie_api = qip.tmdb.Movie()
                        l_movies = movie_api.search(search_query)
                        i = 0
                        app.log.debug('l_movies=(%r)%r', type(l_movies), l_movies)
                        if not l_movies:
                            app.log.error('No movies found matching %r!', search_query)
                            continue
                        for o_movie in l_movies:
                            o_movie.__dict__.setdefault('release_date', None)
                        if (True or len(l_movies) > 1) and app.args.interactive:
                            def help_handler(radio_list):
                                i = radio_list._selected_index
                                app.message_dialog(title='Details',
                                                   text=f'i={i}')
                            i = app.radiolist_dialog(
                                title='Please select a movie',
                                values=[(i, '{title}, {release_date} (#{id}) -- {overview}'.format_map(vars(o_movie)))
                                        for i, o_movie in enumerate(l_movies)],
                                help_handler=help_handler)
                            if i is None:
                                print('Cancelled by user!')
                                continue
                        o_movie = l_movies[i]

                        #app.log.debug('o_movie=%r:\n%s', o_movie, pprint.pformat(vars(o_movie)))
                        #{'adult': False,
                        # 'backdrop_path': '/eHUoB8NbvrvKp7KQMNgvc7yLpzM.jpg',
                        # 'entries': {'adult': False,
                        #             'backdrop_path': '/eHUoB8NbvrvKp7KQMNgvc7yLpzM.jpg',
                        #             'genre_ids': [12, 18, 53],
                        #             'id': 44115,
                        #             'original_language': 'en',
                        #             'original_title': '127 Hours',
                        #             'overview': "The true story of mountain climber Aron Ralston's "
                        #                         'remarkable adventure to save himself after a fallen '
                        #                         'boulder crashes on his arm and traps him in an '
                        #                         'isolated canyon in Utah.',
                        #             'popularity': 11.822,
                        #             'poster_path': '/c6Nu7UjhGCQtV16WXabqOQfikK6.jpg',
                        #             'release_date': '2010-11-05',
                        #             'title': '127 Hours',
                        #             'video': False,
                        #             'vote_average': 7,
                        #             'vote_count': 4828},
                        # 'genre_ids': [12, 18, 53],
                        # 'id': 44115,
                        # 'original_language': 'en',
                        # 'original_title': '127 Hours',
                        # 'overview': "The true story of mountain climber Aron Ralston's remarkable "
                        #             'adventure to save himself after a fallen boulder crashes on his '
                        #             'arm and traps him in an isolated canyon in Utah.',
                        # 'popularity': 11.822,
                        # 'poster_path': '/c6Nu7UjhGCQtV16WXabqOQfikK6.jpg',
                        # 'release_date': '2010-11-05',
                        # 'title': '127 Hours',
                        # 'video': False,
                        # 'vote_average': 7,
                        # 'vote_count': 4828}
                        mux_dict['tags'].title = o_movie.title
                        mux_dict['tags'].date = o_movie.release_date
                        app.log.info('%s: %s', inputfile, mux_dict['tags'].short_str())

                else:
                    app.log.error('Invalid input')

    if not remux:
        if app.args.dry_run:
            app.log.verbose('CMD (dry-run): %s', list2cmdline(['mkdir', outputdir]))
        else:
            os.mkdir(outputdir)

    num_extract_errors = 0

    if inputfile_ext in (
            '.ffv1.mkv',
    ) \
            + Mp4File._common_extensions \
            + MkvFile._common_extensions \
            + WebmFile._common_extensions \
            :

        has_forced_subtitle = False
        subtitle_counts = []

        first_pts_time_per_stream = {}

        mkvextract_tracks_args = []
        mkvextract_attachments_args = []

        stream_dict_cache = []
        attachment_index = 0  # First attachment is index 1
        iter_mediainfo_track_dicts = iter(mediainfo_track_dict
                                          for mediainfo_track_dict in mediainfo_dict['media']['track']
                                          if 'ID' in mediainfo_track_dict)

        with contextlib.ExitStack() as stream_dict_loop_exit_stack:
            iter_frames = None

            for stream_dict in sorted_stream_dicts(ffprobe_dict['streams']):
                stream_out_dict = {}
                stream_index = stream_out_dict['index'] = int(stream_dict['index'])
                stream_codec_type = stream_out_dict['codec_type'] = stream_dict['codec_type']

                if (
                        stream_codec_type == 'video'
                        and stream_dict['codec_name'] == 'mjpeg'
                        and stream_dict.get('tags', {}).get('mimetype', None) == 'image/jpeg'):
                    stream_codec_type = stream_out_dict['codec_type'] = 'image'
                    stream_file_ext = '.jpg'
                    stream_out_dict['attachment_type'] = my_splitext(stream_dict['tags']['filename'])[0]
                    #app.log.debug('stream #%d: video -> %s %s [%s]', stream_index, stream_codec_type, stream_file_ext, stream_out_dict['attachment_type'])

                if stream_codec_type == 'video':
                    mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                    assert mediainfo_track_dict['@type'] == 'Video', f'mediainfo_track_dict={mediainfo_track_dict!r}'
                elif stream_codec_type == 'audio':
                    mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                    assert mediainfo_track_dict['@type'] == 'Audio', f'mediainfo_track_dict={mediainfo_track_dict!r}'
                elif stream_codec_type == 'subtitle':
                    mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                    assert mediainfo_track_dict['@type'] == 'Text', f'mediainfo_track_dict={mediainfo_track_dict!r}'
                elif stream_codec_type == 'image':
                    mediainfo_track_dict = None  # Not its own track
                    # General
                    # ...
                    # Cover                                    : Yes
                    # Attachments                              : cover.jpg
                else:
                    raise NotImplementedError(stream_codec_type)

                if stream_codec_type in ('video', 'audio', 'subtitle', 'image'):
                    stream_codec_name = stream_dict['codec_name']
                    EstimatedFrameCount = None
                    if stream_codec_type == 'video':
                        if app.args.force_still_video:
                            EstimatedFrameCount = 1
                        elif 'Duration' in mediainfo_track_dict:
                            # Test using mediainfo's Duration as ffmpeg's can be the whole length of the movie
                            try:
                                EstimatedFrameCount = int(round_half_away_from_zero(
                                    qip.utils.Timestamp(mediainfo_track_dict['Duration'])
                                    * Fraction(mediainfo_track_dict['FrameRate'])))
                            except KeyError:
                                EstimatedFrameCount = int(round_half_away_from_zero(
                                    qip.utils.Timestamp(mediainfo_track_dict['Duration'])
                                    * Fraction(mediainfo_track_dict['OriginalFrameRate'])))
                        elif stream_codec_name in still_image_exts:
                            EstimatedFrameCount = 1
                    app.log.debug('EstimatedFrameCount=%r', EstimatedFrameCount)
                    if (
                            stream_codec_type in ('video', 'image')
                            and stream_codec_name == 'mjpeg'
                            and stream_dict.get('tags', {}).get('mimetype', None) == 'image/jpeg'):
                        stream_codec_type = stream_out_dict['codec_type'] = 'image'
                        stream_file_ext = '.jpg'
                        stream_out_dict['attachment_type'] = my_splitext(stream_dict['tags']['filename'])[0]
                    elif (
                        stream_codec_type == 'video'
                        and EstimatedFrameCount == 1):
                        stream_file_ext = '.png'
                        app.log.warning('Detected %s stream #%d is still image', stream_codec_type, stream_index)
                    else:
                        stream_file_ext = codec_name_to_ext(stream_codec_name)

                    if stream_codec_type == 'video':
                        if app.args.video_language:
                            stream_dict.setdefault('tags', {})
                            stream_dict['tags']['language'] = app.args.video_language.code3
                        # stream_out_dict['pixel_aspect_ratio'] = stream_dict['pixel_aspect_ratio']
                        # stream_out_dict['display_aspect_ratio'] = stream_dict['display_aspect_ratio']

                    if stream_codec_type == 'audio':
                        try:
                            stream_out_dict['original_bit_rate'] = stream_dict['bit_rate']
                        except KeyError:
                            pass
                        # TODO
                        # opusinfo TheTruthAboutCatsAndDogs/title_t00/track-02-audio.fra.opus.ogg
                        # Processing file "TheTruthAboutCatsAndDogs/title_t00/track-02-audio.fra.opus.ogg"...
                        #
                        # New logical stream (#1, serial: 00385013): type opus
                        # Encoded with libopus 1.3
                        # User comments section follows...
                        #         ENCODER=opusenc from opus-tools 0.1.10
                        #         ENCODER_OPTIONS=--vbr --bitrate 192
                        # Opus stream 1:
                        #         Pre-skip: 312
                        #         Playback gain: 0 dB
                        #         Channels: 2
                        #         Original sample rate: 48000Hz
                        #         Packet duration:   20.0ms (max),   20.0ms (avg),   20.0ms (min)
                        #         Page duration:   1000.0ms (max),  999.9ms (avg),  160.0ms (min)
                        #         Total data length: 132228830 bytes (overhead: 0.595%)
                        #         Playback length: 97m:00.139s
                        #         Average bitrate: 181.8 kb/s, w/o overhead: 180.7 kb/s
                        # Logical stream 1 ended

                    stream_time_base = Fraction(stream_dict['time_base'])

                    codec_encoding_delay = get_codec_encoding_delay(inputfile, ffprobe_stream_dict=stream_dict)
                    stream_start_time = adjust_start_time(
                        ffmpeg.Timestamp(stream_dict['start_time']),
                        codec_encoding_delay=codec_encoding_delay,
                        stream_time_base=stream_time_base)

                    check_start_time = app.args.check_start_time
                    if stream_codec_type == 'subtitle':
                        check_start_time = False
                    if check_start_time is Auto and stream_start_time == 0.0:
                        # Sometimes ffprobe reports start_time=0 but mediainfo reports Delay (with low accuracy)
                        Delay = (mediainfo_track_dict or {}).get('Delay', None)
                        Delay = qip.utils.Timestamp(Delay) if Delay is not None else None
                        if Delay:
                            check_start_time = True
                    if check_start_time is Auto and stream_start_time and stream_codec_type == 'video':
                        check_start_time = True
                    if check_start_time is Auto:
                        check_start_time = False
                    if check_start_time:
                        if stream_index not in first_pts_time_per_stream:
                            if iter_frames is None:
                                iter_frames = ffprobe.iter_frames(inputfile)
                                stream_dict_loop_exit_stack.push(contextlib.closing(iter_frames))
                            for frame in iter_frames:
                                if frame.stream_index in first_pts_time_per_stream:
                                    continue
                                if frame.pkt_pts_time is None:
                                    continue
                                first_pts_time_per_stream[frame.stream_index] = frame.pkt_pts_time
                                if frame.stream_index == stream_index:
                                    break
                        stream_start_time_pts = adjust_start_time(
                            first_pts_time_per_stream[stream_index],
                            codec_encoding_delay=codec_encoding_delay,
                            stream_time_base=stream_time_base)
                        if stream_start_time != stream_start_time_pts:
                            app.log.warning('Correcting %s stream #%d start time %s to %s based on first frame PTS', stream_codec_type, stream_index, stream_start_time, stream_start_time_pts)
                            stream_start_time = stream_start_time_pts

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
                    else:
                        if stream_codec_type == 'audio' \
                                and re.match(r'^(Stereo|Mono|Surround [0-9.]+)$', stream_title):
                            del stream_out_dict['title']

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

                    if (
                            (not mux_attached_pic and stream_disposition_dict['attached_pic']) or
                            (not mux_subtitles and stream_codec_type == 'subtitle')):
                        app.log.warning('Not muxing %s stream #%d...', stream_codec_type, stream_index)
                    else:

                        if stream_disposition_dict['attached_pic']:
                            app.log.info('Will extract %s stream %d w/ mkvextract: %s', stream_codec_type, stream_index, output_track_file_name)
                            mkvextract_attachments_args += [
                                '%d:%s' % (
                                    attachment_index,
                                    outputdir / output_track_file_name,
                                )]
                        elif (
                                app.args.track_extract_tool == 'ffmpeg'
                                # Avoid mkvextract error: Extraction of track ID 3 with the CodecID 'D_WEBVTT/SUBTITLES' is not supported.
                                # (mkvextract expects S_TEXT/WEBVTT)
                                or stream_file_ext == '.vtt'
                                # Avoid mkvextract error: Extraction of track ID 1 with the CodecID 'A_MS/ACM' is not supported.
                                # https://www.makemkv.com/forum/viewtopic.php?t=2530
                                or stream_codec_name in ('pcm_s16le', 'pcm_s24le')
                                # Avoid mkvextract error: Track 0 with the CodecID 'V_MS/VFW/FOURCC' is missing the "default duration" element and cannot be extracted.
                                or stream_file_ext in still_image_exts
                                or (app.args.track_extract_tool is Auto
                                    # For some codecs, mkvextract is not reliable and may encode the wrong frame rate; Use ffmpeg.
                                    and stream_codec_name in (
                                        'vp8',
                                        'vp9',
                                        ))):
                            app.log.info('Extract %s stream %d: %s', stream_codec_type, stream_index, output_track_file_name)
                            with perfcontext('extract track %d w/ ffmpeg' % (stream_index,)):
                                force_format = None
                                try:
                                    force_format = ext_to_container(stream_file_ext)
                                except ValueError:
                                    pass
                                ffmpeg_args = default_ffmpeg_args + [
                                    '-i', inputfile,
                                    '-map_metadata', '-1',
                                    '-map_chapters', '-1',
                                    '-map', '0:%d' % (stream_index,),
                                    ]
                                if stream_file_ext in still_image_exts:
                                    ffmpeg_args += [
                                        '-frames:v', 1,
                                        ]
                                else:
                                    ffmpeg_args += [
                                        '-codec', 'copy',
                                        ]
                                ffmpeg_args += [
                                    '-start_at_zero',
                                    ]
                                if force_format:
                                    ffmpeg_args += [
                                        '-f', force_format,
                                        ]
                                ffmpeg_args += [
                                    outputdir / output_track_file_name,
                                    ]
                                ffmpeg(*ffmpeg_args,
                                       progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_dict),
                                       progress_bar_title=f'Extract {stream_codec_type} track {stream_index} w/ ffmpeg',
                                       dry_run=app.args.dry_run,
                                       y=app.args.yes)
                        elif app.args.track_extract_tool in ('mkvextract', Auto):
                            app.log.info('Will extract %s stream %d w/ mkvextract: %s', stream_codec_type, stream_index, output_track_file_name)
                            mkvextract_tracks_args += [
                                '%d:%s' % (
                                    stream_index,
                                    outputdir / output_track_file_name,
                                )]
                            # raise NotImplementedError('extracted tracks from mkvextract must be reset to start at 0 PTS')
                        else:
                            raise NotImplementedError('unsupported track extract tool: %r' % (app.args.track_extract_tool,))

                else:
                    raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

                original_source_description = []
                original_source_description.append(stream_dict['codec_name'])
                if stream_codec_type == 'video':
                    try:
                        original_source_description.append(stream_dict['profile'])
                    except KeyError:
                        pass
                    original_source_description.append('%sx%s' % (stream_dict['width'], stream_dict['height']))
                    original_source_description.append(stream_dict['display_aspect_ratio'])
                elif stream_codec_type == 'audio':
                    try:
                        original_source_description.append(stream_dict['profile'])
                    except KeyError:
                        pass
                    try:
                        original_source_description.append(stream_dict['channel_layout'])
                    except KeyError:
                        pass
                    try:
                        audio_bitrate = int(stream_dict['bit_rate'])
                    except KeyError:
                        pass
                    else:
                        original_source_description.append(f'{audio_bitrate // 1000}kbps')
                    try:
                        audio_samplerate = int(stream_dict['sample_rate'])
                    except KeyError:
                        pass
                    else:
                        original_source_description.append(f'{audio_samplerate // 1000}kHz')
                    try:
                        audio_samplefmt = stream_dict['sample_fmt']
                    except KeyError:
                        pass
                    else:
                        try:
                            bits_per_raw_sample = int(stream_dict['bits_per_raw_sample'])
                        except KeyError:
                            original_source_description.append(f'{audio_samplefmt}')
                        else:
                            original_source_description.append(f'{audio_samplefmt}({bits_per_raw_sample}b)')
                elif stream_codec_type == 'subtitle':
                    pass
                elif stream_codec_type == 'image':
                    try:
                        original_source_description.append(stream_out_dict['attachment_type'])
                    except KeyError:
                        pass
                    original_source_description.append('%sx%s' % (stream_dict['width'], stream_dict['height']))
                else:
                    raise ValueError('Unsupported codec type %r' % (stream_codec_type,))
                if original_source_description:
                    stream_out_dict['original_source_description'] = ', '.join(original_source_description)

                stream_dict_cache.append({
                    'stream_dict': stream_out_dict,
                    'file': File.new_by_file_name(outputdir / output_track_file_name),
                })
                mux_dict['streams'].append(stream_out_dict)

        if mkvextract_tracks_args:
            with perfcontext('extract tracks w/ mkvextract'):
                cmd = [
                    'mkvextract', 'tracks', inputfile,
                    ] + mkvextract_tracks_args
                do_spawn_cmd(cmd)
        if mkvextract_attachments_args:
            with perfcontext('extract attachments w/ mkvextract'):
                cmd = [
                    'mkvextract', 'attachments', inputfile,
                    ] + mkvextract_attachments_args
                do_spawn_cmd(cmd)

        # Detect duplicates
        if not app.args.dry_run:
            for cache_dict_i, cache_dict1 in enumerate(stream_dict_cache):
                stream_dict1 = cache_dict1['stream_dict']
                if stream_dict1.get('skip', False):
                    continue
                stream_codec_type1 = stream_dict1['codec_type']
                if stream_codec_type1 == 'video' and stream_dict1['disposition']['attached_pic'] and not mux_attached_pic:
                    continue
                if stream_codec_type1 == 'subtitle' and not mux_subtitles:
                    continue
                stream_language1 = isolang(stream_dict1.get('language', 'und'))
                stream_file1 = cache_dict1['file']
                for cache_dict2 in stream_dict_cache[cache_dict_i + 1:]:
                    stream_dict2 = cache_dict2['stream_dict']
                    if stream_dict2.get('skip', False):
                        continue
                    stream_codec_type2 = stream_dict2['codec_type']
                    if stream_codec_type2 != stream_codec_type1:
                        continue
                    if stream_codec_type2 == 'video' and stream_dict2['disposition']['attached_pic'] and not mux_attached_pic:
                        continue
                    if stream_codec_type2 == 'subtitle' and not mux_subtitles:
                        continue
                    stream_language2 = isolang(stream_dict2.get('language', 'und'))
                    if stream_language2 != stream_language1:
                        continue
                    stream_file2 = cache_dict2['file']
                    if stream_file2.getsize() != stream_file1.getsize():
                        continue
                    if stream_file2.md5.hexdigest() != stream_file1.md5.hexdigest():
                        continue
                    app.log.warning('%s identical to %s; Marking as skip',
                                    stream_dict2['file_name'],
                                    stream_dict1['file_name'],
                                    )
                    stream_dict2['skip'] = True

        # Pre-stream post-processing
        if not app.args.dry_run:

            iter_mediainfo_track_dicts = iter(mediainfo_track_dict
                                              for mediainfo_track_dict in mediainfo_dict['media']['track']
                                              if 'ID' in mediainfo_track_dict)
            for stream_dict in sorted_stream_dicts(mux_dict['streams']):
                stream_index = stream_dict['index']
                stream_codec_type = stream_dict['codec_type']

                if stream_codec_type == 'video':
                    mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                    assert mediainfo_track_dict['@type'] == 'Video'
                elif stream_codec_type == 'audio':
                    mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                    assert mediainfo_track_dict['@type'] == 'Audio'
                elif stream_codec_type == 'subtitle':
                    mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                    assert mediainfo_track_dict['@type'] == 'Text'
                elif stream_codec_type == 'image':
                    mediainfo_track_dict = None  # Not its own track
                else:
                    raise NotImplementedError(stream_codec_type)

                if stream_dict.get('skip', False):
                    continue

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

                if mux_subtitles and stream_codec_type == 'subtitle':
                    stream_forced = stream_disposition_dict.get('forced', None)
                    if stream_forced:
                        has_forced_subtitle = True
                    # TODO Detect closed_caption
					# TODO ffprobe -show_frames -i IceAgeContinentalDrift/Ice\ Age\:\ Continental\ Drift\ \(2012\)/track-05-subtitle.eng.sup | grep 'num_rects=[^0]' | wc -l
                    if stream_file_ext in ('.sub', '.sup'):
                        try:
                            d = ffprobe(i=outputdir / stream_file_name, show_packets=True)
                        except subprocess.CalledProcessError as e:
                            app.log.error(e)
                            num_extract_errors += 1
                            subtitle_count = 0
                        else:
                            out = d.out
                            subtitle_count = out.count(
                                b'[PACKET]' if type(out) is bytes else '[PACKET]')
                            if stream_file_ext in ('.sup',):
                                # TODO count only those frames with num_rect != 0
                                subtitle_count = subtitle_count // 2
                    elif stream_file_ext in ('.idx',):
                        out = open(outputdir / stream_file_name, 'rb').read()
                        subtitle_count = out.count(b'timestamp:')
                    elif stream_file_ext in ('.srt', '.vtt'):
                        out = open(outputdir / stream_file_name, 'rb').read()
                        subtitle_count = out.count(b'\n\n') + out.count(b'\n\r\n')
                    else:
                        raise NotImplementedError(stream_file_ext)
                    if subtitle_count == 1 \
                            and File(outputdir / stream_file_name).getsize() == 2048:
                        app.log.warning('Detected empty single-frame subtitle stream #%d (%s); Skipping.',
                                        stream_index,
                                        stream_dict.get('language', 'und'))
                        stream_dict['skip'] = True
                    elif not subtitle_count:
                        app.log.warning('Detected empty subtitle stream #%d (%s); Skipping.',
                                        stream_index,
                                        stream_dict.get('language', 'und'))
                        stream_dict['skip'] = True
                    else:
                        stream_dict['subtitle_count'] = subtitle_count
                        subtitle_counts.append(
                            (stream_dict, subtitle_count))

        if mux_subtitles and not has_forced_subtitle and subtitle_counts:
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
            output_chapters_file_name = outputdir / 'chapters.xml'
            if not remux:
                chapters_out = inputfile.load_chapters(return_raw_xml=True)
                if not app.args.dry_run:
                    safe_write_file(output_chapters_file_name, byte_decode(chapters_out), text=True)
            mux_dict['chapters']['file_name'] = os.fspath(output_chapters_file_name.relative_to(outputdir))

    else:
        raise ValueError('Unsupported extension %r' % (inputfile_ext,))

    if not app.args.dry_run:
        output_mux_file_name = '%s/mux%s.json' % (outputdir,
                                                  '.remux' if remux else '')
        save_mux_dict(output_mux_file_name, mux_dict)

        if remux and app.args.interactive:
            eddiff([
                '%s/mux%s.json' % (outputdir, ''),
                '%s/mux%s.json' % (outputdir, '.remux'),
            ])

    print_streams_summary(mux_dict=mux_dict)

    if num_extract_errors:
        raise Exception(f'EXTRACT ERRORS: {num_extract_errors} extract errors.')

    return True

def action_verify(inputfile, in_tags):
    app.log.info('Verifying %s...', inputfile)

    dir_existed = False
    if not isinstance(inputfile, MediaFile) and inputfile.is_dir():
        outputdir = inputfile
        dir_existed = True
    else:
        if not isinstance(inputfile, MediaFile):
            inputfile = MediaFile.new_by_file_name(inputfile)
        inputfile_base, inputfile_ext = my_splitext(inputfile)
        outputdir = Path("%s" % (inputfile_base,) \
                         if app.args.project is Auto else app.args.project)

        if outputdir.is_dir():
            if False and app.args._continue:
                app.log.warning('Directory exists: %r; Just verifying', outputdir)
                dir_existed = True
            else:
                raise OSError(errno.EEXIST, outputdir)

    if not dir_existed:
        assert action_mux(inputfile, in_tags=in_tags,
                          mux_attached_pic=False,
                          mux_subtitles=False)
    inputdir = outputdir

    input_mux_file_name = inputdir / 'mux.json'
    mux_dict = load_mux_dict(input_mux_file_name, in_tags=in_tags)

    stream_file_durations = []

    for stream_dict in sorted_stream_dicts(mux_dict['streams']):
        if stream_dict.get('skip', False):
            continue
        stream_index = stream_dict['index']
        stream_codec_type = stream_dict['codec_type']
        stream_file_name = stream_dict['file_name']
        stream_file_base, stream_file_ext = my_splitext(stream_file_name)
        if stream_codec_type == 'video' and stream_file_ext in still_image_exts:
            continue
        if stream_codec_type in ('video', 'audio'):

            stream_file = MediaFile.new_by_file_name(inputdir / stream_file_name)

            if True:
                ffprobe_json = stream_file.extract_ffprobe_json()
                ffprobe_stream_json, = ffprobe_json['streams']
                app.log.debug('ffprobe_stream_json=%r', ffprobe_stream_json)
                stream_duration = qip.utils.Timestamp(ffprobe_stream_json['duration'])

            if False:
                mediainfo_dict = stream_file.extract_mediainfo_dict()
                mediainfo_general_dict = None
                mediainfo_track_dict = None
                mediainfo_text_dict = None
                for d in mediainfo_dict['media']['track']:
                    if d['@type'] == 'General':
                        assert mediainfo_general_dict is None
                        mediainfo_general_dict = d
                    elif d['@type'] == 'Audio':
                        assert mediainfo_track_dict is None
                        mediainfo_track_dict = d
                    elif d['@type'] == 'Video':
                        assert mediainfo_track_dict is None
                        mediainfo_track_dict = d
                    elif d['@type'] == 'Text':
                        assert mediainfo_text_dict is None
                        mediainfo_text_dict = d
                    else:
                        raise ValueError(d['@type'])
                assert mediainfo_general_dict
                assert mediainfo_track_dict
                # ffprobe -f lavfi -i movie=Sentinel/title_t00/track-00-video.mpeg2.mp2v,readeia608 -show_entries frame=pkt_pts_time:frame_tags=lavfi.readeia608.0.cc,lavfi.readeia608.1.cc -of csv > Sentinel/title_t00/track-00-video.cc.csv
                #assert not mediainfo_text_dict
                app.log.debug('mediainfo_track_dict=%r', mediainfo_track_dict)
                stream_duration = qip.utils.Timestamp(mediainfo_track_dict['Duration'])

            stream_start_time = ffmpeg.Timestamp(stream_dict['start_time'])
            stream_total_time = stream_start_time + stream_duration
            app.log.info('%s: start_time %s + duration %s = %s',
                         stream_file,
                         stream_start_time,
                         stream_duration,
                         stream_total_time)
            stream_file_durations.append((stream_file, stream_total_time))

    min_stream_duration = min(stream_duration
                              for stream_file, stream_duration in stream_file_durations)
    max_stream_duration = max(stream_duration
                              for stream_file, stream_duration in stream_file_durations)
    if max_stream_duration - min_stream_duration > 5:
        raise LargeDiscrepancyInStreamDurationsError(inputdir=inputdir)

    if not dir_existed:
        app.log.info('Cleaning up %s', inputdir)
        shutil.rmtree(inputdir)

    return True

def load_mux_dict(input_mux_file_name, *, in_tags=None):
    with open(input_mux_file_name, 'r') as fp:
        mux_dict = json.load(fp)

    # Add _temp
    for stream_dict in mux_dict['streams']:
        stream_dict['_temp'] = {}

    try:
        mux_tags = mux_dict['tags']
    except KeyError:
        if in_tags is not None:
            mux_dict['tags'] = mux_tags = copy.copy(in_tags)
    else:
        if not isinstance(mux_tags, AlbumTags):
            mux_dict['tags'] = mux_tags = AlbumTags(mux_tags)
        if in_tags is not None:
            mux_tags.update(in_tags)
    return mux_dict

def save_mux_dict(output_mux_file_name, mux_dict):

    # Remove _temp
    mux_dict = copy.copy(mux_dict)
    mux_dict['streams'] = [copy.copy(stream_dict) for stream_dict in mux_dict['streams']]
    for stream_dict in mux_dict['streams']:
        stream_dict.pop('_temp', None)

    with open(output_mux_file_name, 'w') as fp:
        json.dump(mux_dict, fp, indent=2, sort_keys=True, ensure_ascii=False)

def action_status(inputdir):
    app.log.info('Status of %s...', inputdir)

    input_mux_file_name = inputdir / 'mux.json'
    mux_dict = load_mux_dict(input_mux_file_name)

    print_streams_summary(mux_dict=mux_dict)

def action_update(inputdir, in_tags):
    app.log.info('Updating %s...', inputdir)
    outputdir = inputdir

    input_mux_file_name = inputdir / 'mux.json'
    mux_dict = load_mux_dict(input_mux_file_name, in_tags=in_tags)

    if not app.args.dry_run:
        output_mux_file_name = '%s/mux.json' % (outputdir,)
        save_mux_dict(output_mux_file_name, mux_dict)

def action_chop(inputfile, *, in_tags=None, chaps=None, chop_chaps=None):

    if isinstance(inputfile, str):
        inputfile = Path(inputfile)
    if isinstance(inputfile, os.PathLike):
        if inputfile.is_dir():
            inputdir = inputfile

            input_mux_file_name = inputdir / 'mux.json'
            mux_dict = load_mux_dict(input_mux_file_name, in_tags=in_tags)
            chaps = Chapters.from_mkv_xml(inputdir / mux_dict['chapters']['file_name'], add_pre_gap=True)

            for stream_dict in sorted_stream_dicts(mux_dict['streams']):
                if stream_dict.get('skip', False):
                    continue
                stream_index = stream_dict['index']
                stream_codec_type = stream_dict['codec_type']
                stream_file_name = stream_dict['file_name']
                inputfile = inputdir / stream_file_name

                stream_file_base, stream_file_ext = my_splitext(stream_file_name)

                if (stream_codec_type == 'video'
                    or stream_codec_type == 'audio'):

                    action_chop(inputfile=inputfile,
                                in_tags=in_tags,
                                chaps=chaps, chop_chaps=chop_chaps)

                elif stream_codec_type == 'subtitle':
                    pass
                elif stream_codec_type == 'image':
                    pass
                else:
                    raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

            return True

    app.log.info('Splitting %s...', inputfile)
    if not isinstance(inputfile, MediaFile):
        inputfile = MediaFile.new_by_file_name(inputfile)
    inputfile_base, inputfile_ext = my_splitext(inputfile)
    outputdir = Path(inputfile.file_name.parent if app.args.project is Auto
                     else app.args.project)

    if chaps is None:
        chaps = inputfile.load_chapters()
    chaps = list(chaps)
    assert len(chaps) > 1
    assert chaps[0].start == 0

    chapter_stream_file_ext = inputfile_ext

    chapter_file_name_pat = chop_chapters(chaps=chaps,
                                          inputfile=inputfile,
                                          chop_chaps=chop_chaps)

    return True

def my_splitext(file_name, strip_container=False):
    file_name = toPath(file_name)
    base, ext = os.path.splitext(os.fspath(file_name))
    if ext in {
            '.avi',
            '.ivf',
            '.mkv',
            '.mp2v',
            '.ogg',
    }:
        base2, ext2 = os.path.splitext(os.fspath(base))
        if ext2 in {
                '.ffv1',
                '.h264',
                '.mpeg2',
                '.opus',
                '.vc1',
                '.vp8',
                '.vp9',
        }:
            base = base2
            if strip_container:
                ext = ext2
            else:
                ext = ext2 + ext
    return base, ext

def test_out_file(out_file):
    if not app.args.dry_run:
        if not out_file.exists():
            raise OSError(errno.ENOENT,
                          'File not found: %r' % (out_file,),
                          out_file)
        siz = out_file.stat().st_size
        app.log.debug(f'{out_file} has size {siz}')
        if siz == 0:
            raise OSError(errno.ENOENT,
                          'File empty: %r' % (out_file,),
                          out_file)

def action_optimize(inputdir, in_tags):
    global num_batch_skips
    this_num_batch_skips = 0
    app.log.info('Optimizing %s...', inputdir)
    outputdir = inputdir
    do_chain = app.args.chain

    target_codec_names = set((
        'png', 'mjpeg',
        'vp8', 'vp9',
        'opus',
        'webvtt',
    ))
    if app.args.ffv1:
        target_codec_names.add('ffv1')

    input_mux_file_name = inputdir / 'mux.json'
    mux_dict = load_mux_dict(input_mux_file_name, in_tags=in_tags)

    def optimize_stream(stream_dict, stream_index, is_sub_stream=False):
        global num_batch_skips
        nonlocal this_num_batch_skips
        nonlocal inputdir
        nonlocal outputdir

        temp_files = []

        def done_optimize_iter(do_skip=False):
            nonlocal temp_files
            nonlocal inputdir
            nonlocal outputdir
            nonlocal stream_dict
            nonlocal stream_index
            nonlocal stream_file_name
            nonlocal stream_file_base
            nonlocal stream_file_ext
            nonlocal new_stream_file_name
            nonlocal mux_dict
            nonlocal is_sub_stream

            if do_skip:
                stream_dict['skip'] = True
                app.log.info('Stream #%s %s: setting to be skipped', stream_index, stream_file_name)
            else:
                test_out_file(inputdir / new_stream_file_name)
                if not is_sub_stream:
                    temp_files.append(inputdir / stream_file_name)
                stream_dict.setdefault('original_file_name', stream_file_name)
                stream_dict['file_name'] = stream_file_name = new_stream_file_name
                stream_file_base, stream_file_ext = my_splitext(stream_file_name)
            if not app.args.dry_run:
                output_mux_file_name = '%s/mux.json' % (outputdir,)
                save_mux_dict(output_mux_file_name, mux_dict)
                if not app.args.save_temps:
                    for file_name in temp_files:
                        os.unlink(file_name)
                    temp_files = []
            if app.args.step:
                app.log.warning('Step done; Exit.')
                exit(0)

        if stream_dict.get('skip', False):
            return
        do_skip = False
        stream_codec_type = stream_dict['codec_type']
        orig_stream_file_name = stream_file_name = stream_dict['file_name']
        stream_file_base, stream_file_ext = my_splitext(stream_file_name)
        stream_language = isolang(stream_dict.get('language', 'und'))

        if stream_codec_type == 'video':

            expected_framerate = None
            while True:
                limit_duration = getattr(app.args, 'limit_duration', None)

                stream_file = MediaFile.new_by_file_name(inputdir / stream_file_name)
                ffprobe_json = stream_file.extract_ffprobe_json()
                ffprobe_stream_json, = ffprobe_json['streams']
                stream_codec_name = ffprobe_stream_json['codec_name']
                app.log.debug('stream_codec_name=%r', stream_codec_name)

                if stream_codec_name in target_codec_names:
                    app.log.verbose('Stream #%s %s [%s] OK', stream_index, stream_file_ext, stream_language)
                    break

                if 'concat_streams' in stream_dict:
                    new_stream_file_ext = '.ffv1.mkv'
                    if stream_file_ext == new_stream_file_ext:
                        pass
                    else:
                        for sub_stream_dict in stream_dict['concat_streams']:
                            sub_stream_index = sub_stream_dict['index']
                            optimize_stream(sub_stream_dict,
                                            f'{stream_index}.{sub_stream_dict}',
                                            is_sub_stream=True)

                        new_stream_file_name = stream_file_base + new_stream_file_ext
                        app.log.verbose('Stream #%s concat -> %s', stream_index, new_stream_file_name)

                        stream_file_concat_file_name = f'{stream_file_base}.concat.lst'
                        stream_file_concat_file = ffmpeg.ConcatScriptFile(stream_file_concat_file_name)
                        stream_file_concat_file.files += [
                            stream_file_concat_file.File(sub_stream_dict['file_name'])  # relative
                            for sub_stream_dict in stream_dict['concat_streams']]
                        if not app.args.dry_run:
                            stream_file_concat_file.create()

                        ffmpeg_args = default_ffmpeg_args + [
                            '-f', 'concat', '-safe', 0,
                            '-i', stream_file_concat_file_name,
                            '-codec', 'copy',
                            inputdir / new_stream_file_name,
                        ]

                        with perfcontext('Concat w/ ffmpeg'):
                            ffmpeg(*ffmpeg_args,
                                   progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                                   progress_bar_title=f'Concat {stream_codec_type} stream {stream_index} w/ ffmpeg',
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)

                        done_optimize_iter()
                        continue

                mediainfo_dict = stream_file.extract_mediainfo_dict()
                mediainfo_general_dict = None
                mediainfo_track_dict = None
                mediainfo_text_dict = None
                for d in mediainfo_dict['media']['track']:
                    if d['@type'] == 'General':
                        assert mediainfo_general_dict is None
                        mediainfo_general_dict = d
                    elif d['@type'] in ('Video', 'Image'):
                        assert mediainfo_track_dict is None
                        mediainfo_track_dict = d
                    elif d['@type'] == 'Text':
                        assert mediainfo_text_dict is None
                        mediainfo_text_dict = d
                    else:
                        raise ValueError(d['@type'])
                assert mediainfo_general_dict
                assert mediainfo_track_dict
                # ffprobe -f lavfi -i movie=Sentinel/title_t00/track-00-video.mpeg2.mp2v,readeia608 -show_entries frame=pkt_pts_time:frame_tags=lavfi.readeia608.0.cc,lavfi.readeia608.1.cc -of csv > Sentinel/title_t00/track-00-video.cc.csv
                #assert not mediainfo_text_dict

                field_order, input_framerate, framerate = analyze_field_order_and_framerate(
                    inputdir / stream_file_name,
                    ffprobe_json, ffprobe_stream_json, mediainfo_track_dict)

                if expected_framerate is not None:
                    assert framerate == expected_framerate, (framerate, expected_framerate)
                display_aspect_ratio = Ratio(stream_dict['display_aspect_ratio'])

                lossless = False

                if field_order == '23pulldown':

                    pullup_tool = app.args.pullup_tool
                    if pullup_tool is Auto:
                        pullup_tool = 'yuvkineco'

                    if pullup_tool == 'yuvkineco':
                        # -> ffmpeg+yuvkineco -> .ffv1

                        deinterlace_using_ffmpeg = True
                        fieldmatch_using_ffmpeg = False

                        new_stream_file_ext = '.ffv1.mkv'
                        lossless = True
                        new_stream_file_name_base = '.'.join(e for e in stream_file_base.split('.')
                                                             if e not in ('23pulldown',)) \
                            + '.yuvkineco-pullup'
                        new_stream_file_name = new_stream_file_name_base + new_stream_file_ext
                        new_stream_file = MediaFile.new_by_file_name(inputdir / new_stream_file_name)
                        app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                        if stream_file_ext == '.y4m':
                            assert framerate == FrameRate(30000, 1001)
                            framerate = FrameRate(24000, 1001)
                            app.log.verbose('23pulldown y4m framerate correction: %s', framerate)

                        ffmpeg_dec_args = []
                        if stream_file_ext == '.y4m':
                            pass # Ok; No decode.
                        else:
                            if False and input_framerate:
                                ffmpeg_dec_args += [
                                    # Avoid [yuvkineco] unsupported input fps
                                    '-r', input_framerate,  # Because sometimes the mpeg2 header doesn't show the right framerate
                                    ]
                            elif False and framerate:
                                ffmpeg_dec_args += [
                                    # Avoid [yuvkineco] unsupported input fps
                                    '-r', framerate,  # Because sometimes the mpeg2 header doesn't show the right framerate
                                    ]
                            else:
                                force_input_framerate = getattr(app.args, 'force_input_framerate', None)
                                if force_input_framerate:
                                    ffmpeg_dec_args += [
                                        '-r', force_input_framerate,
                                        ]
                            ffmpeg_dec_args += [
                                '-i', inputdir / stream_file_name,
                                ]
                            ffmpeg_video_filter_args = []
                            if fieldmatch_using_ffmpeg:
                                ffmpeg_video_filter_args += [
                                    'fieldmatch',
                                    ]
                            if deinterlace_using_ffmpeg:
                                ffmpeg_video_filter_args += [
                                    'yadif=deint=interlaced',
                                    ]
                            if ffmpeg_video_filter_args:
                                ffmpeg_dec_args += [
                                    '-vf', ','.join(ffmpeg_video_filter_args),
                                    ]
                            ffmpeg_dec_args += [
                                '-pix_fmt', 'yuv420p',
                                '-nostats',  # will expect progress on output
                                # '-codec:v', ext_to_condec('.y4m'),  # yuv4mpegpipe ERROR: Codec not supported.
                                ]
                            if limit_duration:
                                ffmpeg_dec_args += ['-t', ffmpeg.Timestamp(limit_duration)]
                            ffmpeg_dec_args += [
                                '-f', ext_to_container('.y4m'),
                                '--', 'pipe:',
                            ]

                        framerate = getattr(app.args, 'force_output_framerate', framerate)
                        app.log.verbose('pullup with final framerate %s (%.3f)', framerate, framerate)

                        use_yuvcorrect = False
                        yuvcorrect_cmd = [
                            'yuvcorrect',
                            '-T', 'LINE_SWITCH',
                            '-T', 'INTERLACED_TOP_FIRST',
                        ]

                        yuvkineco_cmd = [
                            'yuvkineco',
                        ]
                        if framerate == FrameRate(24000, 1001):
                            yuvkineco_cmd += ['-F', '1']
                        elif framerate == FrameRate(30000, 1001):
                            yuvkineco_cmd += ['-F', '4']
                        else:
                            raise NotImplementedError(framerate)
                        #yuvkineco_cmd += ['-n', '2']  # Noise level (default: 10)
                        if deinterlace_using_ffmpeg:
                            yuvkineco_cmd += ['-i', '-1']  # Disable deinterlacing
                        yuvkineco_cmd += ['-C', inputdir / (new_stream_file_name_base + '.23c')]  # pull down cycle list file

                        ffmpeg_enc_args = [
                            '-i', 'pipe:0',
                            '-codec:v', ext_to_codec(new_stream_file_ext, lossless=lossless),
                        ] + ext_to_codec_args(new_stream_file_ext, lossless=lossless) + [
                            '-f', ext_to_container(new_stream_file_ext),
                            inputdir / new_stream_file_name,
                        ]

                        with perfcontext('Pullup w/ -> .y4m' + (' -> yuvcorrect' if use_yuvcorrect else '') + ' -> yuvkineco -> .ffv1'):
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
                                p2 = do_popen_cmd(yuvcorrect_cmd,
                                                  stdin=p1_out,
                                                  stdout=subprocess.PIPE) \
                                    if use_yuvcorrect else p1
                                try:
                                    p3 = do_popen_cmd(yuvkineco_cmd,
                                                      stdin=p2.stdout,
                                                      stdout=subprocess.PIPE)
                                    try:
                                        p4 = ffmpeg.popen(*ffmpeg_enc_args,
                                                          stdin=p3.stdout,
                                                          # TODO progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                                                          # TODO progress_bar_title=,
                                                          dry_run=app.args.dry_run,
                                                          y=app.args.yes)
                                    finally:
                                        if not app.args.dry_run:
                                            p3.stdout.close()
                                finally:
                                    if use_yuvcorrect:
                                        if not app.args.dry_run:
                                            p2.stdout.close()
                            finally:
                                if not app.args.dry_run:
                                    if ffmpeg_dec_args:
                                        p1.stdout.close()
                                    else:
                                        stream_file.close()
                            if not app.args.dry_run:
                                p4.communicate()
                                assert p4.returncode == 0

                        expected_framerate = framerate

                        done_optimize_iter()
                        continue

                    elif pullup_tool == 'ffmpeg':
                        # -> ffmpeg -> .ffv1

                        new_stream_file_ext = '.ffv1.mkv'
                        lossless = True
                        new_stream_file_name = '.'.join(e for e in stream_file_base.split('.')
                                                        if e not in ('23pulldown',)) \
                            + '.ffmpeg-pullup' + new_stream_file_ext
                        new_stream_file = MediaFile.new_by_file_name(inputdir / new_stream_file_name)
                        app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                        if stream_file_ext == '.y4m':
                            assert framerate == FrameRate(30000, 1001)
                            framerate = FrameRate(24000, 1001)
                            app.log.verbose('23pulldown y4m framerate correction: %s', framerate)

                        orig_framerate = framerate * 30 / 24

                        ffmpeg_args = [] + default_ffmpeg_args
                        force_input_framerate = getattr(app.args, 'force_input_framerate', None)
                        if force_input_framerate:
                            ffmpeg_args += [
                                '-r', force_input_framerate,
                                ]
                        ffmpeg_args += [
                            '-i', inputdir / stream_file_name,
                            '-vf', f'pullup,fps={framerate}',
                            '-r', framerate,
                            '-codec:v', ext_to_codec(new_stream_file_ext, lossless=lossless),
                            ] + ext_to_codec_args(new_stream_file_ext, lossless=lossless)
                        if limit_duration:
                            ffmpeg_args += ['-t', ffmpeg.Timestamp(limit_duration)]
                        ffmpeg_args += [
                            '-f', ext_to_container(new_stream_file_ext),
                            inputdir / new_stream_file_name,
                        ]

                        with perfcontext('Pullup w/ -> ffmpeg -> .ffv1'):
                            ffmpeg(*ffmpeg_args,
                                   slurm=app.args.slurm,
                                   #slurm_cpus_per_task=2, # ~230-240%
                                   progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                                   progress_bar_title=f'Pullup {stream_codec_type} stream {stream_index} w/ ffmpeg',
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)

                        expected_framerate = framerate

                        done_optimize_iter()
                        continue

                    elif pullup_tool == 'mencoder':
                        # -> mencoder -> .ffv1

                        if True:
                            # ffprobe and mediainfo don't agree on resulting frame rate.
                            new_stream_file_ext = '.ffv1.mkv'
                        else:
                            # mencoder seems to mess up the encoder frame rate in avi (total-frames/1), ffmpeg's r_frame_rate seems accurate.
                            new_stream_file_ext = '.ffv1.avi'
                        new_stream_file_name = '.'.join(e for e in stream_file_base.split('.')
                                                        if e not in ('23pulldown',)) \
                            + '.mencoder-pullup' + new_stream_file_ext
                        new_stream_file = MediaFile.new_by_file_name(inputdir / new_stream_file_name)
                        app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                        mencoder_args = [
                            '-aspect', display_aspect_ratio,
                            stream_file,
                            '-ofps', framerate,
                            '-vf', 'pullup,softskip,harddup',
                            #'-ovc', 'lavc', '-lavcopts', 'vcodec=ffv1:slices=12:threads=4',
                            '-ovc', 'lavc', '-lavcopts', 'vcodec=ffv1:threads=4',
                            '-of', 'lavf', '-lavfopts', 'format=%s' % (ext_to_mencoder_libavcodec_format(new_stream_file_ext),),
                            '-o', new_stream_file,
                        ]
                        expected_framerate = framerate
                        with perfcontext('Pullup w/ mencoder'):
                            mencoder(*mencoder_args,
                                     #slurm=app.args.slurm,
                                     dry_run=app.args.dry_run)

                        done_optimize_iter()
                        continue

                    else:
                        raise NotImplementedError(pullup_tool)

                ffprobe_stream_json = ffprobe_json['streams'][0]
                app.log.debug(ffprobe_stream_json)

                #mediainfo_duration = qip.utils.Timestamp(mediainfo_track_dict['Duration'])
                mediainfo_width = int(mediainfo_track_dict['Width'])
                mediainfo_height = int(mediainfo_track_dict['Height'])

                if mux_dict.get('chapters', None):
                    chaps = list(Chapters.from_mkv_xml(inputdir / mux_dict['chapters']['file_name'], add_pre_gap=True))
                else:
                    chaps = []
                parallel_chapters = app.args.parallel_chapters \
                    and len(chaps) > 1 \
                    and chaps[0].start == 0

                extra_args = []
                video_filter_specs = []

                if field_order == 'progressive':
                    pass
                elif field_order in ('auto-interlaced',):
                    video_filter_specs.append('yadif=mode=send_frame:parity=auto:deint=interlaced')
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

                if not is_sub_stream and app.args.crop in (Auto, True):
                    if getattr(app.args, 'crop_wh', None) is not None:
                        w, h = app.args.crop_wh
                        l, t = (mediainfo_width - w) // 2, (mediainfo_height - h) // 2
                        stream_crop_whlt = w, h, l, t
                        stream_crop = True
                    elif getattr(app.args, 'crop_whlt', None) is not None:
                        stream_crop_whlt = app.args.crop_whlt
                        stream_crop = True
                    else:
                        stream_crop_whlt = None
                        stream_crop = app.args.crop
                    if stream_crop is not False:
                        if not stream_crop_whlt and 'original_crop' not in stream_dict:
                            if mediainfo_track_dict['@type'] == 'Image':
                                pass  # Not supported
                            else:
                                stream_crop_whlt = ffmpeg.cropdetect(
                                    default_ffmpeg_args=default_ffmpeg_args,
                                    input_file=inputdir / stream_file_name,
                                    skip_frame_nokey=app.args.cropdetect_skip_frame_nokey,
                                    # Seek 5 minutes in
                                    #cropdetect_seek=max(0.0, min(300.0, float(mediainfo_duration) - 300.0)),
                                    cropdetect_duration=app.args.cropdetect_duration,
                                    video_filter_specs=video_filter_specs,
                                    dry_run=app.args.dry_run)
                        if stream_crop_whlt and (stream_crop_whlt[0], stream_crop_whlt[1]) == (mediainfo_width, mediainfo_height):
                            stream_crop_whlt = None
                        stream_dict.setdefault('original_crop', stream_crop_whlt)
                        if stream_crop_whlt:
                            stream_dict.setdefault('original_display_aspect_ratio', stream_dict['display_aspect_ratio'])
                            pixel_aspect_ratio = Ratio(stream_dict['pixel_aspect_ratio'])  # invariable
                            w, h, l, t = stream_crop_whlt
                            storage_aspect_ratio = Ratio(w, h)
                            display_aspect_ratio = pixel_aspect_ratio * storage_aspect_ratio
                            orig_stream_crop_whlt = stream_crop_whlt
                            orig_storage_aspect_ratio = storage_aspect_ratio
                            orig_display_aspect_ratio = display_aspect_ratio
                            if stream_crop is Auto:
                                try:
                                    stream_crop_whlt = cropdetect_autocorrect_whlt[stream_crop_whlt]
                                except KeyError:
                                    pass
                                else:
                                    w, h, l, t = stream_crop_whlt
                                    storage_aspect_ratio = Ratio(w, h)
                                    display_aspect_ratio = pixel_aspect_ratio * storage_aspect_ratio
                                    app.log.warning('Crop detection result accepted: --crop-whlt %s w/ DAR %s, auto-corrected from %s w/ DAR %s',
                                                    ' '.join(str(e) for e in display_aspect_ratio),
                                                    display_aspect_ratio,
                                                    ' '.join(str(e) for e in orig_display_aspect_ratio),
                                                    orig_display_aspect_ratio)
                                    stream_crop = True
                            if stream_crop is Auto:
                                if display_aspect_ratio in common_aspect_ratios or \
                                        (w, h) in common_resolutions:
                                    app.log.warning('Crop detection result accepted: --crop-whlt %s w/ DAR %s, common',
                                                    ' '.join(str(e) for e in stream_crop_whlt),
                                                    display_aspect_ratio)
                                    stream_crop = True
                            if stream_crop is Auto:
                                raise RuntimeError('Crop detection! --crop or --no-crop or --crop-whlt %s w/ DAR %s' % (
                                              ' '.join(str(e) for e in stream_crop_whlt),
                                              display_aspect_ratio))
                            video_filter_specs.append('crop={w}:{h}:{l}:{t}'.format(
                                        w=w, h=h, l=l, t=t))
                            # extra_args += ['-aspect', XXX]
                            stream_dict['display_aspect_ratio'] = str(display_aspect_ratio)

                if video_filter_specs:
                    extra_args += ['-filter:v', ','.join(video_filter_specs)]

                lossless = False

                if is_sub_stream:
                    new_stream_file_ext = '.ffv1.mkv'
                    if field_order == 'progressive':
                        app.log.verbose('Stream #%s %s [%s] OK', stream_index, stream_file_ext, stream_language)
                        break
                    new_stream_file_name = stream_file_base + '.progressive' + new_stream_file_ext
                else:
                    new_stream_file_ext = '.ffv1.mkv' if app.args.ffv1 else '.vp9.ivf'
                    new_stream_file_name = stream_file_base + new_stream_file_ext
                app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                if stream_file_ext in ('.mpeg2', '.mpeg2.mp2v'):
                    # In case initial frame is a I frame to be displayed after
                    # subqequent P or B frames, the start time will be
                    # incorrect.
                    # -start_at_zero, -dropts and various -vsync options don't
                    # seem to work, only -vsync drop.
                    # XXXJST assumes constant frame rate (at least after pullup)
                    if new_stream_file_ext in ('.ffv1.mkv',):
                        # -vsync drop would lose timestamps and just apply the 1/1000 timebase!
                        pass
                    else:
                        extra_args += ['-vsync', 'drop']

                ffmpeg_conv_args = []
                ffmpeg_conv_args += [
                    '-codec:v', ext_to_codec(new_stream_file_ext, lossless=lossless),
                ]

                if new_stream_file_ext == '.vp9.ivf':
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
                            '-minrate', '%dk' % (video_target_bit_rate * (1.00 if ffprobe_stream_json['height'] <= 480 else 0.50),),
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
                        ]
                else:
                    ffmpeg_conv_args += ext_to_codec_args(new_stream_file_ext, lossless=lossless)

                ffmpeg_conv_args += extra_args

                if (parallel_chapters
                        and stream_file_ext in (
                            '.mpeg2', '.mpeg2.mp2v',  # Chopping using segment muxer is reliable (tested with mpeg2)
                            '.ffv1.mkv',
                            # '.vc1.avi',  # Stupidly slow (vc1 -> ffv1 @ 0.9x)
                            '.h264',
                        )):
                    concat_list_file = ffmpeg.ConcatScriptFile(inputdir / f'{new_stream_file_name}.concat.txt')
                    ffmpeg_concat_args = []
                    with perfcontext('Convert %s chapters to %s in parallel w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                        chapter_stream_file_ext = {
                                '.mpeg2': '.mpegts',
                                '.mpeg2.mp2v': '.mpegts',
                                '.h264': (
                                    '.h264' if app.args.cuda  # Fast lossless
                                    else '.ffv1.mkv'),  # Slow lossless
                                '.vc1.avi': '.ffv1.mkv',
                                '.ffv1.mkv': '.ffv1.mkv',
                            }.get(stream_file_ext, stream_file_ext)
                        stream_chapter_file_name_pat = '%s-chap%%02d%s' % (stream_file_base.replace('%', '%%'),
                                                                           chapter_stream_file_ext.replace('%', '%%'))
                        new_stream_chapter_file_name_pat = '%s-chap%%02d%s' % (stream_file_base.replace('%', '%%'),
                                                                               new_stream_file_ext.replace('%', '%%'))

                        threads = []

                        def encode_chap():
                            app.log.verbose('Chapter %s', chap)
                            stream_chapter_file_name = stream_chapter_file_name_pat % (chap.no,)
                            new_stream_chapter_file_name = new_stream_chapter_file_name_pat % (chap.no,)
                            # https://ffmpeg.org/ffmpeg-all.html#concat-1
                            concat_list_file.files.append(concat_list_file.File(new_stream_chapter_file_name))  # relative

                            if False and app.args._continue \
                                    and (inputdir / new_stream_chapter_file_name).exists() \
                                    and (inputdir / new_stream_chapter_file_name).stat().st_size:
                                app.log.warning('%s exists: continue...', inputdir / new_stream_chapter_file_name)
                            else:
                                ffmpeg_args = default_ffmpeg_args + [
                                    '-i', inputdir / stream_chapter_file_name,
                                    ] + ffmpeg_conv_args + [
                                    '-f', ext_to_container(new_stream_file_ext), inputdir / new_stream_chapter_file_name,
                                    ]
                                future = slurm_executor.submit(
                                        ffmpeg.run2pass,
                                        *ffmpeg_args,
                                        **{
                                            'slurm': app.args.slurm,
                                            'progress_bar_max': chap.end - chap.start,
                                            'progress_bar_title': f'Encode {stream_codec_type} stream {stream_index} chapter {chap} w/ ffmpeg',
                                            'dry_run': app.args.dry_run,
                                            'y': app.args.yes,
                                            })
                                threads.append(future)

                        chapter_lossless = True

                        # Chop
                        if False and stream_file_ext in ('.h264',):
                            # "ffmpeg cannot always read correct timestamps from H264 streams"
                            # So split manually instead of using the segment muxer
                            raise NotImplementedError  # This is not an accurate split!!
                            ffmpeg_concat_args += [
                                '-vsync', 'drop',
                                ]
                            for chap in chaps:
                                app.log.verbose('Chapter %s', chap)
                                stream_chapter_file_name = stream_chapter_file_name_pat % (chap.no,)
                                if False and app.args._continue \
                                        and (inputdir / stream_chapter_file_name).exists() \
                                        and (inputdir / stream_chapter_file_name).stat().st_size:
                                    app.log.warning('%s exists: continue...')
                                else:
                                    with perfcontext('Chop w/ ffmpeg'):
                                        ffmpeg_args = default_ffmpeg_args + [
                                            '-fflags', '+genpts',
                                            '-start_at_zero', '-copyts',
                                        ]
                                        force_input_framerate = getattr(app.args, 'force_input_framerate', None)
                                        if force_input_framerate:
                                            ffmpeg_args += [
                                                '-r', force_input_framerate,
                                                ]
                                        codec = ('copy' if (ext_to_codec(chapter_stream_file_ext) == ext_to_codec(stream_file_ext)
                                                            and not (chapter_lossless and stream_file_ext in ('.h264',)))  # h264 copy just spits out a single empty chapter
                                                 else ext_to_codec(chapter_stream_file_ext, lossless=chapter_lossless))
                                        ffmpeg_args += codec_to_input_args(codec) + [
                                            '-i', inputdir / stream_file_name,
                                            '-codec', codec,
                                            '-ss', ffmpeg.Timestamp(chap.start),
                                            '-to', ffmpeg.Timestamp(chap.end),
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
                                            inputdir / stream_chapter_file_name,
                                            ]
                                        ffmpeg(*ffmpeg_args,
                                               progress_bar_max=chap.end - chap.start,
                                               progress_bar_title=f'Chop {stream_codec_type} stream {stream_index} chapter {chap} w/ ffmpeg',
                                               dry_run=app.args.dry_run,
                                               y=app.args.yes)
                                encode_chap()
                                temp_files.append(inputdir / stream_chapter_file_name)
                        else:
                            app.log.verbose('All chapters...')
                            stream_chapter_file_name_pat = \
                                chop_chapters(chaps=chaps,
                                              inputfile=inputdir / stream_file_name,
                                              chapter_file_ext=chapter_stream_file_ext,
                                              chapter_lossless=chapter_lossless)
                            stream_chapter_file_name_pat = os.fspath(
                                Path(stream_chapter_file_name_pat).relative_to(
                                    os.fspath(inputdir).replace('%', '%%')))

                            # Encode
                            for chap in chaps:
                                stream_chapter_file_name = stream_chapter_file_name_pat % (chap.no,)
                                encode_chap()
                                temp_files.append(inputdir / stream_chapter_file_name)

                        # Join
                        concat_list_file.create()
                        exc = None
                        for future in concurrent.futures.as_completed(threads):
                            try:
                                future.result()
                            except BaseException as e:
                                exc = e
                        if exc:
                            raise exc

                    # Concat
                    with perfcontext('Concat %s w/ ffmpeg' % (new_stream_file_name,)):
                        cwd = concat_list_file.file_name.parent  # Certain characters (like '?') confuse the concat protocol
                        ffmpeg_args = default_ffmpeg_args + [
                            '-f', 'concat', '-safe', '0', '-i', concat_list_file.file_name.relative_to(cwd),
                            '-codec', 'copy',
                            ] + ffmpeg_concat_args + [
                            '-start_at_zero',
                            '-f', ext_to_container(new_stream_file_name), (inputdir / new_stream_file_name).relative_to(cwd),
                            ]
                        ffmpeg(*ffmpeg_args,
                               cwd=cwd,
                               progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                               progress_bar_title=f'Concat {stream_codec_type} stream {stream_index} w/ ffmpeg',
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                        for chap in chaps:
                            new_stream_chapter_file_name = new_stream_chapter_file_name_pat % (chap.no,)
                            temp_files.append(inputdir / new_stream_chapter_file_name)
                else:
                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                        ffmpeg_args = [] + default_ffmpeg_args
                        force_input_framerate = getattr(app.args, 'force_input_framerate', None)
                        if force_input_framerate:
                            ffmpeg_args += [
                                '-r', force_input_framerate,
                                ]
                        ffmpeg_args += [
                            '-i', inputdir / stream_file_name,
                            ] + ffmpeg_conv_args + [
                            '-f', ext_to_container(new_stream_file_name), inputdir / new_stream_file_name,
                            ]
                        if new_stream_file_ext in (
                                '.vp8.ivf',
                                '.vp9.ivf',
                                '.av1.ivf',
                                # '.ffv1.mkv',  # no need for better compression
                        ):
                            ffmpeg.run2pass(*ffmpeg_args,
                                            slurm=app.args.slurm,
                                            progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                                            progress_bar_title=f'Convert {stream_codec_type} stream {stream_index} {stream_file_ext} -> {new_stream_file_ext} w/ ffmpeg',
                                            dry_run=app.args.dry_run,
                                            y=app.args.yes)
                        else:
                            ffmpeg(*ffmpeg_args,
                                   progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                                   progress_bar_title=f'Convert {stream_codec_type} stream {stream_index} {stream_file_ext} -> {new_stream_file_ext} w/ ffmpeg',
                                   slurm=app.args.slurm,
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)
                        test_out_file(inputdir / new_stream_file_name)

                done_optimize_iter()

        elif stream_codec_type == 'audio':

            ok_exts = (
                    '.opus',
                    '.opus.ogg',
                    #'.mp3',
                    )

            while True:
                stream_start_time = ffmpeg.Timestamp(stream_dict.get('start_time', 0))

                if stream_file_ext in ok_exts \
                        and not stream_start_time:
                    app.log.verbose('Stream #%s %s [%s] OK', stream_index, stream_file_ext, stream_language)
                    break

                if True:
                    snd_file = SoundFile.new_by_file_name(inputdir / stream_file_name)
                    ffprobe_json = snd_file.extract_ffprobe_json()
                    app.log.debug(ffprobe_json['streams'][0])
                    channels = ffprobe_json['streams'][0]['channels']
                    channel_layout = ffprobe_json['streams'][0].get('channel_layout', None)
                else:
                    ffprobe_json = {}

                # opusenc supports Wave, AIFF, FLAC, Ogg/FLAC, or raw PCM.
                opusenc_formats = ('.wav', '.aiff', '.flac', '.ogg', '.pcm')
                if stream_file_ext not in ok_exts + opusenc_formats \
                        or stream_start_time:
                    new_stream_file_ext = '.wav'
                    new_stream_file_name = stream_file_base + new_stream_file_ext
                    app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                        ffmpeg_args = default_ffmpeg_args + [
                            '-i', inputdir / stream_file_name,
                            # '-channel_layout', channel_layout,
                            ]
                        ffmpeg_args += [
                            '-start_at_zero',
                            #'-codec', 'pcm_s16le',
                        ]
                        # See ffmpeg -sample_fmts
                        audio_samplefmt = ffprobe_json['streams'][0]['sample_fmt']
                        if audio_samplefmt in ('s16', 's16p'):
                            ffmpeg_args += [
                                '-codec', 'pcm_s16le',
                            ]
                        elif audio_samplefmt in ('s32', 's32p'):
                            bits_per_raw_sample = int(ffprobe_json['streams'][0]['bits_per_raw_sample'])
                            if bits_per_raw_sample == 24:
                                ffmpeg_args += [
                                    '-codec', 'pcm_s24le',
                                ]
                            elif bits_per_raw_sample == 32:
                                ffmpeg_args += [
                                    '-codec', 'pcm_s32le',
                                ]
                            else:
                                raise NotImplementedError('Unsupported sample format %r with %d bits per raw sample' % (audio_samplefmt, bits_per_raw_sample))
                        elif audio_samplefmt in ('fltp',):
                            try:
                                bits_per_raw_sample = int(ffprobe_json['streams'][0]['bits_per_raw_sample'])
                            except KeyError:
                                bits_per_raw_sample = 0
                            if bits_per_raw_sample == 0:
                                # Compressed bits vs raw bits... AC-3 says 16 bits max... not sure this would be the correct way. Just assume 32.
                                bits_per_raw_sample = 32
                            if bits_per_raw_sample < 32:
                                # ffmpeg does not support encoding pcm_f16le and pcm_f24le
                                bits_per_raw_sample = 32
                            ffmpeg_args += [
                                '-codec', f'pcm_f{bits_per_raw_sample}le',
                            ]
                        else:
                            raise NotImplementedError('Unsupported sample format %r' % (audio_samplefmt,))
                        if stream_start_time:
                            ffmpeg_args += [
                                '-af', 'adelay=delays=%s' % (
                                    # Looks like "s" suffix doesn't work: '|'.join(['%fs' % (stream_start_time.seconds,)] * channels),
                                    '|'.join(['%f' % (stream_start_time.seconds * 1000.0,)] * channels),
                                )
                            ]
                            stream_start_time = ffmpeg.Timestamp(0)
                            stream_dict.setdefault('original_start_time', stream_dict['start_time'])
                            stream_dict['start_time'] = str(stream_start_time)
                        if False:
                            # opusenc doesn't like RF64 headers!
                            # Other option is to pipe wav from ffmpeg to opusenc
                            ffmpeg_args += [
                                '-rf64', 'auto',  # Use RF64 header rather than RIFF for large files
                            ]
                        ffmpeg_args += [
                            '-f', 'wav', inputdir / new_stream_file_name,
                            ]
                        ffmpeg(*ffmpeg_args,
                               progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                               progress_bar_title=f'Convert {stream_codec_type} stream {stream_index} {stream_file_ext} -> {new_stream_file_ext} w/ ffmpeg',
                               slurm=app.args.slurm,
                               slurm_cpus_per_task=2, # ~230-240%
                               dry_run=app.args.dry_run,
                               y=app.args.yes)

                    done_optimize_iter()
                    continue

                if stream_file_ext in opusenc_formats:
                    # opusenc supports Wave, AIFF, FLAC, Ogg/FLAC, or raw PCM.
                    new_stream_file_ext = '.opus.ogg'
                    new_stream_file_name = stream_file_base + new_stream_file_ext
                    app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                    audio_bitrate = 640000 if channels >= 4 else 384000
                    audio_bitrate = min(audio_bitrate, int(ffprobe_json['streams'][0]['bit_rate']))
                    try:
                        audio_bitrate = min(audio_bitrate, int(stream_dict['original_bit_rate']))
                    except KeyError:
                        pass
                    audio_bitrate = audio_bitrate // 1000

                    with perfcontext('Convert %s -> %s w/ opusenc' % (stream_file_ext, new_stream_file_name)):
                        opusenc_args = [
                            '--vbr',
                            '--bitrate', str(audio_bitrate),
                            inputdir / stream_file_name,
                            inputdir / new_stream_file_name,
                            ]
                        opusenc(*opusenc_args,
                                slurm=app.args.slurm,
                                dry_run=app.args.dry_run)

                    done_optimize_iter()
                    continue

                if True:
                    assert stream_file_ext not in ok_exts
                    # Hopefully ffmpeg supports it!
                    new_stream_file_ext = '.opus.ogg'
                    new_stream_file_name = stream_file_base + new_stream_file_ext
                    app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                    audio_bitrate = 640000 if channels >= 4 else 384000
                    audio_bitrate = min(audio_bitrate, int(ffprobe_json['streams'][0]['bit_rate']))
                    audio_bitrate = audio_bitrate // 1000
                    if channels > 2:
                        raise NotImplementedError('Conversion not supported as ffmpeg does not respect the number of channels and channel mapping')

                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                        ffmpeg_args = default_ffmpeg_args + [
                            '-i', inputdir / stream_file_name,
                            '-c:a', 'opus',
                            '-strict', 'experimental',  # for libopus
                            '-b:a', '%dk' % (audio_bitrate,),
                            # '-vbr', 'on', '-compression_level', '10',  # defaults
                            #'-channel', str(channels), '-channel_layout', channel_layout,
                            #'-channel', str(channels), '-mapping_family', '1', '-af', 'aformat=channel_layouts=%s' % (channel_layout,),
                            ]
                        ffmpeg_args += [
                            '-f', 'ogg', inputdir / new_stream_file_name,
                            ]
                        ffmpeg(*ffmpeg_args,
                               progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                               progress_bar_title=f'Convert {stream_codec_type} stream {stream_index} {stream_file_ext} -> {new_stream_file_ext} w/ ffmpeg',
                               slurm=app.args.slurm,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)

                    done_optimize_iter()
                    continue

                raise ValueError('Unsupported audio extension %r' % (stream_file_ext,))

        elif stream_codec_type == 'subtitle':

            ok_exts = (
                    '.vtt',
                    )

            while True:

                if stream_file_ext in ('.vtt',):
                    app.log.verbose('Stream #%s %s (%s) [%s] OK', stream_index, stream_file_ext, stream_dict.get('subtitle_count', '?'), stream_language)
                    break

                if False and stream_file_ext in ('.sup',):
                    new_stream_file_ext = '.sub'
                    new_stream_file_name = stream_file_base + new_stream_file_ext
                    app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                    if False:
                        with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                            ffmpeg_args = default_ffmpeg_args + [
                                '-i', inputdir / stream_file_name,
                                '-scodec', 'dvdsub',
                                '-map', '0',
                                ]
                            ffmpeg_args += [
                                '-f', 'mpeg', inputdir / new_stream_file_name,
                                ]
                            ffmpeg(*ffmpeg_args,
                                   # TODO progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                                   # TODO progress_bar_title=,
                                   slurm=app.args.slurm,
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
                                '--output', inputdir / new_stream_file_name,
                                inputdir / stream_file_name,
                                ]
                            out = do_spawn_cmd(cmd)

                    done_optimize_iter()

                if stream_file_ext in ('.sup', '.sub',):
                    if app.args.external_subtitles and not stream_dict['disposition'].get('forced', None):
                        app.log.verbose('Stream #%s %s (%s) [%s] -> EXTERNAL', stream_index, stream_file_ext, stream_dict.get('subtitle_count', '?'), stream_language)
                        return

                    new_stream_file_ext = '.srt'
                    new_stream_file_name = stream_file_base + new_stream_file_ext
                    if app.args.batch:
                        app.log.warning('BATCH MODE SKIP: Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)
                        do_chain = False
                        num_batch_skips += 1
                        this_num_batch_skips += 1
                        return
                    app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                    if False:
                        subrip_matrix = app.args.subrip_matrix
                        if subrip_matrix is Auto:
                            subrip_matrix_dir = Path.home() / '.cache/SubRip/Matrices'
                            if not app.args.dry_run:
                                os.makedirs(subrip_matrix_dir, exist_ok=True)

                            subrip_matrix = 'dry_run_matrix.sum' if app.args.dry_run else None
                            # ~/tools/installs/SubRip/CLI.txt
                            cmd = [
                                'SubRip', '/FINDMATRIX',
                                '--use-idx-file-offsets',
                                '--',
                                inputdir / stream_file_name,
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
                                    subrip_matrix = subrip_matrix_dir / '%03d.sum' % (i,)
                                    if not subrip_matrix.exists():
                                        break
                                else:
                                    raise ValueError('Can\'t determine a new matrix name under %s' % (subrip_matrix_dir,))

                        with perfcontext('SubRip /AUTOTEXT'):
                            # ~/tools/installs/SubRip/CLI.txt
                            cmd = [
                                'SubRip', '/AUTOTEXT',
                                '--subtitle-language', stream_language.code3,
                                '--',
                                inputdir / stream_file_name,
                                inputdir / new_stream_file_name,
                                subrip_matrix,
                                ]
                            do_spawn_cmd(cmd)

                    else:
                        while True:
                            from qip.subtitleedit import SubtitleEdit
                            subtitleedit_args = []
                            if False:
                                subtitleedit_args += [
                                    '/convert',
                                    inputdir / stream_file_name,
                                    'subrip',  # format
                                ]
                            else:
                                subtitleedit_args += [
                                    inputdir / stream_file_name,
                                ]
                                if True:
                                    app.log.warning('Invoking %s: Please run OCR and save as SubRip (.srt) format: %s',
                                                    SubtitleEdit.name,
                                                    inputdir / new_stream_file_name)
                            with perfcontext('Convert %s -> %s w/ SubtitleEdit' % (stream_file_ext, new_stream_file_name)):
                                SubtitleEdit(*subtitleedit_args,
                                             language=stream_language,
                                             seed_file_name=inputdir / new_stream_file_name,
                                             dry_run=app.args.dry_run,
                                             )
                            if not (inputdir / new_stream_file_name).is_file():
                                try:
                                    raise OSError(errno.ENOENT,
                                                  'File not found: %r' % (inputdir / new_stream_file_name,),
                                                  inputdir / new_stream_file_name)
                                except OSError as e:
                                    if not app.args.interactive:
                                        raise

                                    do_retry = False

                                    with app.need_user_attention():
                                        from prompt_toolkit.formatted_text import FormattedText
                                        from prompt_toolkit.completion import WordCompleter
                                        completer = WordCompleter([
                                            'help',
                                            'skip',
                                            'continue',
                                            'retry',
                                            'quit',
                                        ])
                                        print('')
                                        app.print(
                                            FormattedText([
                                                ('class:error', str(e)),
                                            ]))
                                        while True:
                                            print(describe_stream_dict(stream_dict))
                                            c = app.prompt(completer=completer)
                                            if c in ('help', 'h', '?'):
                                                print('')
                                                print('List of commands:')
                                                print('')
                                                print('help -- Print this help')
                                                print('skip -- Skip this stream -- done')
                                                print('continue -- Continue/retry processing this stream -- done')
                                                print('quit -- Quit')
                                            elif c in ('skip', 's'):
                                                do_skip = True
                                                break
                                            elif c in ('continue', 'c', 'retry'):
                                                do_retry = True
                                                break
                                            elif c in ('quit', 'q'):
                                                raise
                                            else:
                                                app.log.error('Invalid input')

                                    if do_retry:
                                        continue
                            break

                    if not do_skip:
                        cmd = [
                            Path(__file__).with_name('fix-subtitles'),
                            inputdir / new_stream_file_name,
                            ]
                        out = dbg_exec_cmd(cmd)
                        if not app.args.dry_run:
                            out = clean_cmd_output(out)
                            File.new_by_file_name(inputdir / new_stream_file_name) \
                                    .write(out)
                            if False and app.args.interactive:
                                edfile(inputdir / new_stream_file_name)

                    done_optimize_iter(do_skip=do_skip)
                    if do_skip:
                        return
                    else:
                        continue

                # NOTE:
                #  WebVTT format exported by SubtitleEdit is same as ffmpeg .srt->.vtt except ffmpeg's timestamps have more 0-padding
                if stream_file_ext in ('.srt',):
                    new_stream_file_ext = '.vtt'
                    new_stream_file_name = stream_file_base + new_stream_file_ext
                    app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                        ffmpeg_args = default_ffmpeg_args + [
                            '-i', inputdir / stream_file_name,
                            '-f', 'webvtt', inputdir / new_stream_file_name,
                            ]
                        ffmpeg(*ffmpeg_args,
                               # TODO progress_bar_max=estimate_stream_duration(ffprobe_json=ffprobe_json),
                               # TODO progress_bar_title=,
                               #slurm=app.args.slurm,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)

                    done_optimize_iter()
                    continue

                raise ValueError('Unsupported subtitle extension %r' % (stream_file_ext,))

        elif stream_codec_type == 'image':

            # https://matroska.org/technical/cover_art/index.html
            ok_exts = (
                    '.png',
                    '.jpg', '.jpeg',
                    )

            while True:

                if stream_file_ext in ok_exts:
                    app.log.verbose('Stream #%s %s OK', stream_index, stream_file_ext)
                    app.log.verbose('Stream #%s %s [%s] OK', stream_index, stream_file_ext, stream_language)
                    break

                if stream_file_ext not in ok_exts:
                    new_stream_file_ext = '.png'
                    new_stream_file_name = stream_file_base + new_stream_file_ext
                    app.log.verbose('Stream #%s %s -> %s', stream_index, stream_file_ext, new_stream_file_name)

                    with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream_file_name)):
                        ffmpeg_args = default_ffmpeg_args + [
                            '-i', inputdir / stream_file_name,
                            ]
                        ffmpeg_args += [
                            '-f', 'png', inputdir / new_stream_file_name,
                            ]
                        ffmpeg(*ffmpeg_args,
                               #slurm=app.args.slurm,
                               dry_run=app.args.dry_run,
                               y=app.args.yes)

                    done_optimize_iter()
                    continue

                raise ValueError('Unsupported image extension %r' % (stream_file_ext,))

        else:
            raise ValueError('Unsupported codec type %r' % (stream_codec_type,))

    for stream_dict in sorted_stream_dicts(mux_dict['streams']):
        stream_index = stream_dict['index']
        optimize_stream(stream_dict, stream_index)

    if not this_num_batch_skips and do_chain:
        app.args.demux_dirs += (outputdir,)

def action_extract_music(inputdir, in_tags):
    app.log.info('Extracting music from %s...', inputdir)
    outputdir = inputdir

    input_mux_file_name = inputdir / 'mux.json'
    mux_dict = load_mux_dict(input_mux_file_name, in_tags=in_tags)

    num_skip_chapters = app.args.num_skip_chapters

    try:
        chapters_file_name = mux_dict['chapters']['file_name']
    except KeyError:
        has_chapters = False
        chap = Chapter(start=0, end=0,
                       title=mux_dict['tags'].title,
                       no=1)
        chaps = [chap]
    else:
        has_chapters = True
        chaps = list(Chapters.from_mkv_xml(inputdir / chapters_file_name, add_pre_gap=False))
        while chaps and chaps[0].no < num_skip_chapters:
            chaps.pop(0)
        chaps = [chap for chap in chaps if chap.title]
    tracks_total = len(chaps)

    for track_no, chap in enumerate(chaps, start=1):
        app.log.verbose('Chapter %s -> track %d/%d',
                        chap,
                        track_no,
                        tracks_total)

        src_picture = None
        picture = None

        for stream_dict in sorted_stream_dicts(mux_dict['streams']):
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
                snd_file = SoundFile.new_by_file_name(inputdir / stream_file_name)
                ffprobe_json = snd_file.extract_ffprobe_json()
                app.log.debug(ffprobe_json['streams'][0])
                channels = ffprobe_json['streams'][0]['channels']
                channel_layout = ffprobe_json['streams'][0].get('channel_layout', None)

                force_format = None
                try:
                    force_format = ext_to_container(stream_file_ext)
                except ValueError:
                    pass

                if has_chapters:
                    stream_chapter_tmp_file = SoundFile.new_by_file_name(
                            inputdir / ('%s-%02d%s' % (
                                stream_file_base,
                                chap.no,
                                stream_file_ext)))

                    with perfcontext('Chop w/ ffmpeg'):
                        ffmpeg_args = default_ffmpeg_args + [
                            '-start_at_zero', '-copyts',
                            '-i', inputdir / stream_file_name,
                            '-codec', 'copy',
                            '-ss', ffmpeg.Timestamp(chap.start),
                            '-to', ffmpeg.Timestamp(chap.end),
                            ]
                        if force_format:
                            ffmpeg_args += [
                                '-f', force_format,
                                ]
                        ffmpeg_args += [
                            stream_chapter_tmp_file,
                            ]
                        ffmpeg(*ffmpeg_args,
                               progress_bar_max=chap.end - chap.start,
                               progress_bar_title=f'Chop {stream_codec_type} stream {stream_index} chapter {chap} w/ ffmpeg',
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                else:
                    stream_chapter_tmp_file = snd_file

                m4a = M4aFile(my_splitext(stream_chapter_tmp_file)[0] + '.m4a')
                m4a.tags = copy.copy(mux_dict['tags'].tracks_tags[track_no])
                m4a.album_tags = copy.copy(mux_dict['tags'])
                m4a.tags.track = track_no  # Since a copy was taken and not fully connected to album_tags anymore
                m4a.tags.tracks = tracks_total
                m4a.tags.title = chap.title
                m4a.tags.type = 'normal'
                try:
                    del m4a.tags.album_tags.recording_location
                except AttributeError:
                    pass
                if m4a.tags.date is None and m4a.tags.recording_date is not None:
                    m4a.tags.date = m4a.tags.recording_date
                try:
                    del m4a.tags.album_tags.recording_date
                except AttributeError:
                    pass

                if src_picture != m4a.tags.picture:
                    src_picture = m4a.tags.picture
                    picture = m4a.prep_picture(src_picture,
                                               yes=app.args.yes)
                m4a.tags.picture = None  # Not supported by taged TODO

                if stream_chapter_tmp_file.file_name.resolve() != m4a.file_name.resolve():
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

def external_subtitle_file_name(output_file, stream_file_name, stream_dict):
    try:
        return stream_dict['external_stream_file_name']
    except KeyError:
        pass
    # stream_file_name = stream_dict['file_name']
    stream_language = isolang(stream_dict.get('language', 'und'))
    external_stream_file_name = my_splitext(output_file)[0]
    external_stream_file_name += "." + stream_language.code3
    if stream_dict['disposition'].get('hearing_impaired', None):
        external_stream_file_name += '.hearing_impaired'
    if stream_dict['disposition'].get('visual_impaired', None):
        external_stream_file_name += '.visual_impaired'
    if stream_dict['disposition'].get('karaoke', None):
        external_stream_file_name += '.karaoke'
    if stream_dict['disposition'].get('original', None):
        external_stream_file_name += '.original'
    if stream_dict['disposition'].get('dub', None):
        external_stream_file_name += '.dub'
    if stream_dict['disposition'].get('lyrics', None):
        external_stream_file_name += '.lyrics'
    if stream_dict['disposition'].get('comment', None):
        external_stream_file_name += '.comment'
    if stream_dict['disposition'].get('forced', None):
        external_stream_file_name += '.forced'
    elif stream_dict['disposition'].get('closed_caption', None):
        external_stream_file_name += '.cc'
    try:
        external_stream_file_name += stream_dict['external_stream_file_name_suffix']
    except KeyError:
        pass
    external_stream_file_name += my_splitext(stream_file_name)[1]
    return external_stream_file_name

def action_demux(inputdir, in_tags):
    app.log.info('Demuxing %s...', inputdir)
    outputdir = inputdir

    input_mux_file_name = inputdir / 'mux.json'
    mux_dict = load_mux_dict(input_mux_file_name, in_tags=in_tags)

    # ffmpeg messes up timestamps, mkvmerge doesn't support WebVTT yet
    # https://trac.ffmpeg.org/ticket/7736#ticket
    use_mkvmerge = False
    webm = app.args.webm

    output_file = MkvFile(
        inputdir.with_suffix(inputdir.suffix + '.demux' + ('.webm' if webm else '.mkv'))
        if app.args.output_file is Auto else app.args.output_file)
    attachment_counts = collections.defaultdict(lambda: 0)

    external_stream_file_names_seen = set()
    estimated_duration = None

    def handle_StreamCharacteristicsSeenError(e):
        nonlocal mux_dict
        nonlocal stream_dict
        nonlocal sorted_streams
        nonlocal enumerated_sorted_streams
        update_mux_conf = False

        if not app.args.interactive:
            raise

        stream_codec_type = stream_dict['codec_type']

        with app.need_user_attention():
            from prompt_toolkit.formatted_text import FormattedText
            from prompt_toolkit.completion import WordCompleter
            completer = WordCompleter([
                'help',
                'skip',
                'open',
                'goto',
                'continue',
                'retry',
                'quit',
                'print',
                'forced',
                'hearing_impaired',
                'comment',
                'karaoke',
                'lyrics',
                'original',
                'title',
            ] + (['suffix'] if isinstance(e, StreamExternalSubtitleAlreadyCreated) else []))
            print('')
            app.print(
                FormattedText([
                    ('class:error', str(e)),
                ]))
            while True:
                print(describe_stream_dict(stream_dict))
                c = app.prompt(completer=completer)
                if c in ('help', 'h', '?'):
                    print('')
                    print('List of commands:')
                    print('')
                    print('help -- Print this help')
                    print('skip -- Skip this stream -- done')
                    print('print -- Print streams summary')
                    if stream_codec_type in ('subtitle',):
                        print('forced -- Toggle forced disposition (%r)' % (True if stream_dict['disposition'].get('forced', None) else False,))
                        print('hearing_impaired -- Toggle hearing_impaired disposition (%r)' % (True if stream_dict['disposition'].get('hearing_impaired', None) else False,))
                    if stream_codec_type in ('audio', 'subtitle'):
                        print('comment -- Toggle comment disposition (%r)' % (True if stream_dict['disposition'].get('comment', None) else False,))
                    if stream_codec_type in ('audio',):
                        print('karaoke -- Toggle karaoke disposition (%r)' % (True if stream_dict['disposition'].get('karaoke', None) else False,))
                    if stream_codec_type in ('subtitle',):
                        print('lyrics -- Toggle lyrics disposition (%r)' % (True if stream_dict['disposition'].get('lyrics', None) else False,))
                    if stream_codec_type in ('audio',):
                        print('original -- Toggle original disposition (%r)' % (True if stream_dict['disposition'].get('original', None) else False,))
                    if stream_codec_type in ('audio',):
                        print('title -- Edit title (%s)' % (stream_dict.get('title', None),))
                    if isinstance(e, StreamExternalSubtitleAlreadyCreated):
                        print('suffix -- Edit external stream file name suffix ()' % (stream_dict.get('external_stream_file_name_suffix', None)))
                    print('open -- Open this stream')
                    print('goto -- Jump to another past stream')
                    print('continue -- Continue/retry processing this stream -- done')
                    print('quit -- quit')
                    print('')
                elif c in ('skip', 's'):
                    stream_dict['skip'] = True
                    update_mux_conf = True
                    break
                elif c in ('open',):
                    try:
                        if stream_codec_type in ('subtitle',):
                            from qip.subtitleedit import SubtitleEdit
                            stream_language = isolang(stream_dict.get('language', 'und'))
                            subtitleedit_args = [
                                inputdir / stream_file_name,
                                ]
                            SubtitleEdit(*subtitleedit_args,
                                         language=stream_language,
                                         #seed_file_name=inputdir / new_stream_file_name,
                                         dry_run=app.args.dry_run,
                                         )
                        else:
                            xdg_open(inputdir / stream_dict['file_name'])
                    except Exception as e:
                        app.log.error(e)
                elif c in ('continue', 'c', 'retry'):
                    i = next(i for i, d in enumerate(sorted_streams) if d is stream_dict)
                    enumerated_sorted_streams.send(i)
                    break
                elif c in ('goto', 'g'):
                    goto_index = app.prompt('goto stream index: ')
                    if goto_index:
                        goto_index = int(goto_index)
                        forward = False
                        for i, d in enumerate(sorted_streams):
                            if d['index'] == goto_index:
                                break
                            if d is stream_dict:
                                forward = True
                        else:
                            app.log.error('Stream index %r not found', goto_index)
                            continue
                        if forward:
                            app.log.error('Can\'t jump forward to stream index %r', goto_index)
                            continue
                        if stream_dict is not d:
                            if update_mux_conf:
                                save_mux_dict(input_mux_file_name, mux_dict)
                                update_mux_conf = False
                            sorted_stream_index = i
                            stream_dict = d
                            enumerated_sorted_streams.send(sorted_stream_index)
                            if stream_dict.get('skip', False):
                                app.log.warning('Stream index %r skip cancelled', stream_dict['index'])
                                del stream_dict['skip']
                                update_mux_conf = True
                elif c in ('quit', 'q'):
                    raise
                elif c in ('print', 'p'):
                    print_streams_summary(mux_dict=mux_dict, current_stream_index=stream_dict['index'])
                elif c == 'forced':
                    stream_dict['disposition']['forced'] = not stream_dict['disposition'].get('forced', None)
                    update_mux_conf = True
                elif c == 'hearing_impaired':
                    stream_dict['disposition']['hearing_impaired'] = not stream_dict['disposition'].get('hearing_impaired', None)
                    update_mux_conf = True
                elif c == 'comment':
                    stream_dict['disposition']['comment'] = not stream_dict['disposition'].get('comment', None)
                    update_mux_conf = True
                elif c == 'karaoke':
                    stream_dict['disposition']['karaoke'] = not stream_dict['disposition'].get('karaoke', None)
                    update_mux_conf = True
                elif c == 'lyrics':
                    stream_dict['disposition']['lyrics'] = not stream_dict['disposition'].get('lyrics', None)
                    update_mux_conf = True
                elif c == 'original':
                    stream_dict['disposition']['original'] = not stream_dict['disposition'].get('original', None)
                    update_mux_conf = True
                elif c == 'title':
                    stream_title = app.input_dialog(
                        title=describe_stream_dict(stream_dict),
                        text='Please input stream title:',
                        initial_text=stream_dict.get('title', None) or '')
                    if stream_title is None:
                        print('Cancelled by user!')
                    else:
                        if stream_title == '':
                            stream_dict.pop('title', None)
                        else:
                            stream_dict['title'] = stream_title
                        update_mux_conf = True
                elif c == 'suffix':
                    external_stream_file_name_suffix = app.input_dialog(
                        title=describe_stream_dict(stream_dict),
                        text='Please input external stream file name suffix:',
                        initial_text=stream_dict.get('external_stream_file_name_suffix', None) or '')
                    if external_stream_file_name_suffix is None:
                        print('Cancelled by user!')
                    else:
                        if external_stream_file_name_suffix == '':
                            stream_dict.pop('external_stream_file_name_suffix', None)
                        else:
                            stream_dict['external_stream_file_name_suffix'] = external_stream_file_name_suffix
                        update_mux_conf = True
                else:
                    app.log.error('Invalid input')

        if update_mux_conf:
            save_mux_dict(input_mux_file_name, mux_dict)

    if use_mkvmerge:
        cmd = [
            'mkvmerge',
            ]
        if webm:
            cmd += [
                '--webm',
            ]
        cmd += [
            '-o', output_file,
            '--no-track-tags',
            '--no-global-tags',
            ]
        # --title handled with write_tags
        video_angle = 0

        for stream_dict in mux_dict['streams']:
            stream_dict['_temp'] = types.SimpleNamespace(
                stream_characteristics=None,
                post_process_subtitle=False,
                out_index=-1,
            )

        sorted_streams = sorted_stream_dicts(mux_dict['streams'])
        enumerated_sorted_streams = qip.utils.advenumerate(sorted_streams)
        for sorted_stream_index, stream_dict in enumerated_sorted_streams:
            if stream_dict.get('skip', False):
                continue
            stream_index = stream_dict['index']
            stream_file_name = stream_dict['file_name']
            stream_codec_type = stream_dict['codec_type']
            stream_language = isolang(stream_dict.get('language', 'und'))
            stream_title = stream_dict.get('title', None)

            stream_characteristics = (stream_codec_type, stream_language)
            if stream_codec_type == 'video':
                video_angle += 1
                if video_angle > 1:
                    stream_characteristics += (('angle', video_angle),)
                if stream_title is not None:
                    stream_characteristics += (('title', stream_title),)
            if stream_codec_type == 'subtitle':
                stream_characteristics += (
                    'hearing_impaired' if stream_dict['disposition'].get('hearing_impaired', None) else '',
                    'visual_impaired' if stream_dict['disposition'].get('visual_impaired', None) else '',
                    'karaoke' if stream_dict['disposition'].get('karaoke', None) else '',
                    'dub' if stream_dict['disposition'].get('dub', None) else '',
                    'lyrics' if stream_dict['disposition'].get('lyrics', None) else '',
                    'comment' if stream_dict['disposition'].get('comment', None) else '',
                    'forced' if stream_dict['disposition'].get('forced', None) else '',
                    'closed_caption' if stream_dict['disposition'].get('closed_caption', None) else '',
                )

            if stream_characteristics in (
                    stream_dict2['_temp'].stream_characteristics
                    for stream_dict2 in sorted_streams[:sorted_stream_index]
                    if not stream_dict2.get('skip', False)):
                try:
                    raise StreamCharacteristicsSeenError(stream_index=stream_index,
                                                         stream_characteristics=stream_characteristics)
                except StreamCharacteristicsSeenError as e:
                    handle_StreamCharacteristicsSeenError(e)
                    continue
            stream_dict['_temp'].stream_characteristics = stream_characteristics

            if stream_codec_type == 'subtitle':
                if app.args.external_subtitles and my_splitext(stream_dict['file_name'])[1] != '.vtt':
                    stream_file_names = [stream_file_name]
                    if my_splitext(stream_dict['file_name'])[1] == '.sub':
                        stream_file_names.append(my_splitext(stream_file_name)[0] + '.idx')
                    for stream_file_name in stream_file_names:
                        external_stream_file_name = external_subtitle_file_name(
                            output_file=output_file,
                            stream_file_name=stream_file_name,
                            stream_dict=stream_dict)
                        app.log.warning('Stream #%d %s -> %s', stream_index, stream_file_name, external_stream_file_name)
                        if external_stream_file_name in external_stream_file_names_seen:
                            raise ValueError(f'Stream {stream_index} External subtitle file already created: {external_stream_file_name}')
                        external_stream_file_names_seen.add(external_stream_file_name)
                        shutil.copyfile(inputdir / stream_file_name,
                                        external_stream_file_name,
                                        follow_symlinks=True)
                    continue
                if webm:
                    # mkvmerge does not yet support subtitles of webm files due to standard not being finalized
                    stream_dict['_temp'].post_process_subtitle = True
                    continue

        sorted_streams = sorted_stream_dicts(mux_dict['streams'])
        enumerated_sorted_streams = qip.utils.advenumerate(sorted_streams)
        for sorted_stream_index, stream_dict in enumerated_sorted_streams:
            if stream_dict.get('skip', False):
                continue
            stream_index = stream_dict['index']
            stream_file_name = stream_dict['file_name']
            stream_codec_type = stream_dict['codec_type']
            stream_language = isolang(stream_dict.get('language', 'und'))
            stream_title = stream_dict.get('title', None)

            stream_dict['_temp'].out_index = max(
                (stream_index2['_temp'].out_index
                 for stream_index2 in sorted_streams[:sorted_stream_index]),
                default=-1) + 1

            if stream_codec_type == 'image':
                attachment_type = stream_dict['attachment_type']
                if webm:
                    # attachments not supported
                    stream_dict['_temp'].out_index = -1
                    attachment_counts[attachment_type] += 1
                    external_stream_file_name = output_file.file_name.parent / '{type}{num_suffix}{ext}'.format(
                        type=attachment_type,
                        num_suffix='' if attachment_counts[attachment_type] == 1 else '-%d' % (attachment_counts[attachment_type],),
                        ext=my_splitext(stream_file_name)[1],
                    )
                    app.log.warning('Stream #%d %s -> %s', stream_index, stream_file_name, external_stream_file_name)
                    shutil.copyfile(inputdir / stream_file_name,
                                    external_stream_file_name,
                                    follow_symlinks=True)
                    continue
                else:
                    cmd += [
                        # '--attachment-description', <desc>
                        '--attachment-mime-type', byte_decode(dbg_exec_cmd(['file', '--brief', '--mime-type', inputdir / stream_file_name])).strip(),
                        '--attachment-name', '%s%s' % (attachment_type, my_splitext(stream_file_name)[1]),
                        '--attach-file', inputdir / stream_file_name,
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
                if stream_title is not None:
                    cmd += ['--track-name', '%d:%s' % (0, stream_title)]
                # TODO --tags
                if stream_codec_type == 'subtitle' and my_splitext(stream_file_name)[1] == '.sub':
                    cmd += [inputdir / '%s.idx' % (my_splitext(stream_file_name)[0],)]
                cmd += [inputdir / stream_file_name]
        if mux_dict.get('chapters', None):
            cmd += ['--chapters', inputdir / mux_dict['chapters']['file_name']]
        else:
            cmd += ['--no-chapters']
        with perfcontext('mkvmerge'):
            do_spawn_cmd(cmd)

        if any(stream_dict['_temp'].post_process_subtitle
               for stream_dict in sorted_streams):
            num_inputs = 0
            noss_file_name = output_file.file_name + '.noss%s' % ('.webm' if webm else '.mkv',)
            if not app.args.dry_run:
                shutil.move(output_file.file_name, noss_file_name)
            num_inputs += 1
            ffmpeg_args = default_ffmpeg_args + [
                '-i', noss_file_name,
                ]
            option_args = [
                '-map', str(num_inputs-1),
                ]
            for stream_dict in sorted_streams:
                if not stream_dict['_temp'].post_process_subtitle:
                    continue
                if stream_dict.get('skip', False):
                    continue
                stream_index = stream_dict['index']
                stream_file_name = stream_dict['file_name']
                stream_codec_type = stream_dict['codec_type']
                stream_language = isolang(stream_dict.get('language', 'und'))
                stream_title = stream_dict.get('title', None)

                stream_dict['_temp'].out_index = max(
                    (stream_index2['_temp'].out_index
                     for stream_index2 in sorted_streams),
                    default=-1) + 1

                num_inputs += 1
                ffmpeg_args += [
                    '-i', inputdir / stream_file_name,
                    ]
                option_args += [
                    '-map', str(num_inputs-1),
                    ]
                stream_language = isolang(stream_dict.get('language', 'und'))
                if stream_language is not isolang('und'):
                    #ffmpeg_args += ['--language', '%d:%s' % (track_id, stream_language.code3)]
                    option_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), 'language=%s' % (stream_language.code3,),]

                disposition_flags = []
                if stream_dict['disposition'].get('default', None):
                    disposition_flags.append('default')
                if stream_dict['disposition'].get('forced', None):
                    disposition_flags.append('forced')
                ffmpeg_output_args += [
                    '-disposition:%d' % (stream_dict['_temp'].out_index,),
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
                '-f', ext_to_container(my_splitext(output_file)[1]),
                output_file,
                ]
            with perfcontext('merge subtitles w/ ffmpeg'):
                ffmpeg(*ffmpeg_args,
                       progress_bar_max=estimated_duration,
                       progress_bar_title=f'Merge subtitles w/ ffmpeg',
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
        has_opus_streams = any(
                my_splitext(stream_dict['file_name'])[1] in ('.opus', '.opus.ogg')
                for stream_dict in mux_dict['streams'])
        video_angle = 0

        for stream_dict in mux_dict['streams']:
            stream_dict['_temp'] = types.SimpleNamespace(
                stream_characteristics=None,
                out_index=-1,
                external=False,
            )

        sorted_streams = sorted_stream_dicts(mux_dict['streams'])
        enumerated_sorted_streams = qip.utils.advenumerate(sorted_streams)
        for sorted_stream_index, stream_dict in enumerated_sorted_streams:
            if stream_dict.get('skip', False):
                continue
            stream_index = stream_dict['index']
            stream_file_name = stream_dict['file_name']
            stream_file_base, stream_file_ext = my_splitext(stream_file_name)
            stream_codec_type = stream_dict['codec_type']
            stream_language = isolang(stream_dict.get('language', 'und'))
            stream_title = stream_dict.get('title', None)

            stream_characteristics = (stream_codec_type, stream_language)
            if stream_codec_type == 'video':
                video_angle += 1
                if video_angle > 1:
                    stream_characteristics += (
                        ('angle', video_angle),
                    )
                if stream_title is not None:
                    stream_characteristics += (
                        ('title', stream_title),
                    )
            if stream_codec_type == 'subtitle':
                stream_characteristics += (
                    'hearing_impaired' if stream_dict['disposition'].get('hearing_impaired', None) else '',
                    'visual_impaired' if stream_dict['disposition'].get('visual_impaired', None) else '',
                    'karaoke' if stream_dict['disposition'].get('karaoke', None) else '',
                    'dub' if stream_dict['disposition'].get('dub', None) else '',
                    'lyrics' if stream_dict['disposition'].get('lyrics', None) else '',
                    'comment' if stream_dict['disposition'].get('comment', None) else '',
                    'forced' if stream_dict['disposition'].get('forced', None) else '',
                    'closed_caption' if stream_dict['disposition'].get('closed_caption', None) else '',
                )
            if stream_codec_type == 'audio':
                if stream_dict['disposition'].get('comment', None):
                    if stream_title is None:
                        stream_title = 'Commentary'
                    stream_characteristics += (
                        ('comment', stream_title),
                    )
                elif stream_dict['disposition'].get('karaoke', None):
                    if stream_title is None:
                        stream_title = 'Karaoke'
                    stream_characteristics += (
                        ('karaoke', stream_title),
                    )
                elif stream_dict['disposition'].get('original', None):
                    if stream_title is None:
                        stream_title = 'Original'
                    stream_characteristics += (
                        ('title', stream_title),
                    )
                elif app.args.audio_track_titles:
                    if stream_title is None:
                        stream_title = stream_language.name
                    stream_characteristics += (
                        ('title', stream_title),
                    )
                else:
                    if stream_title is not None:
                        stream_characteristics += (
                            ('title', stream_title),
                        )
            if stream_codec_type == 'subtitle':
                if app.args.external_subtitles and my_splitext(stream_dict['file_name'])[1] != '.vtt':
                    stream_characteristics += ('external',)
                    try:
                        stream_characteristics += (
                            ('suffix', stream_dict['external_stream_file_name_suffix']),
                        )
                    except KeyError:
                        pass
                    stream_file_names = [stream_file_name]
                    if my_splitext(stream_dict['file_name'])[1] == '.sub':
                        stream_file_names.append(my_splitext(stream_file_name)[0] + '.idx')
                    try:
                        for stream_file_name in stream_file_names:
                            external_stream_file_name = external_subtitle_file_name(
                                output_file=output_file,
                                stream_file_name=stream_file_name,
                                stream_dict=stream_dict)
                            app.log.warning('Stream #%d %s -> %s', stream_index, stream_file_name, external_stream_file_name)
                            if external_stream_file_name in external_stream_file_names_seen:
                                raise StreamExternalSubtitleAlreadyCreated(stream_index=stream_index,
                                                                           external_stream_file_name=external_stream_file_name)
                            external_stream_file_names_seen.add(external_stream_file_name)
                            shutil.copyfile(inputdir / stream_file_name,
                                            external_stream_file_name,
                                            follow_symlinks=True)
                    except StreamExternalSubtitleAlreadyCreated as e:
                        handle_StreamCharacteristicsSeenError(e)
                        continue
                    stream_dict['_temp'].external = True
                    continue

            if stream_characteristics in (
                    stream_dict2['_temp'].stream_characteristics
                    for stream_dict2 in sorted_streams[:sorted_stream_index]
                    if not stream_dict2.get('skip', False)):
                try:
                    raise StreamCharacteristicsSeenError(stream_index=stream_index,
                                                         stream_characteristics=stream_characteristics)
                except StreamCharacteristicsSeenError as e:
                    handle_StreamCharacteristicsSeenError(e)
                    continue
            stream_dict['_temp'].stream_characteristics = stream_characteristics

        sorted_streams = sorted_stream_dicts(mux_dict['streams'])
        enumerated_sorted_streams = qip.utils.advenumerate(sorted_streams)
        for sorted_stream_index, stream_dict in enumerated_sorted_streams:
            if stream_dict.get('skip', False):
                continue
            if stream_dict['_temp'].external:
                # Already processed
                continue
            stream_index = stream_dict['index']
            stream_file_name = stream_dict['file_name']
            stream_file_base, stream_file_ext = my_splitext(stream_file_name)
            stream_codec_type = stream_dict['codec_type']
            stream_language = isolang(stream_dict.get('language', 'und'))
            stream_title = stream_dict.get('title', None)

            if stream_codec_type == 'image':
                attachment_type = stream_dict['attachment_type']
                if webm:
                    # attachments not supported
                    attachment_counts[attachment_type] += 1
                    external_stream_file_name = output_file.file_name.parent / '{type}{num_suffix}{ext}'.format(
                        type=attachment_type,
                        num_suffix='' if attachment_counts[attachment_type] == 1 else '-%d' % (attachment_counts[attachment_type],),
                        ext=my_splitext(stream_file_name)[1],
                    )
                    app.log.warning('Stream #%d %s -> %s', stream_index, stream_file_name, external_stream_file_name)
                    shutil.copyfile(inputdir / stream_file_name,
                                    external_stream_file_name,
                                    follow_symlinks=True)
                    continue

            stream_dict['_temp'].out_index = max(
                (stream_index2['_temp'].out_index
                 for stream_index2 in sorted_streams[:sorted_stream_index]),
                default=-1) + 1

            if stream_codec_type == 'subtitle':
                if my_splitext(stream_dict['file_name'])[1] == '.sub':
                    # ffmpeg doesn't read the .idx file?? Embed .sub/.idx into a .mkv first
                    tmp_stream_file_name = stream_file_name + '.mkv'
                    mkvmerge_cmd = [
                        'mkvmerge',
                        '-o', inputdir / tmp_stream_file_name,
                        inputdir / stream_file_name,
                        '%s.idx' % (my_splitext(inputdir / stream_file_name)[0],),
                    ]
                    do_spawn_cmd(mkvmerge_cmd)
                    stream_file_name = tmp_stream_file_name
                    stream_file_base, stream_file_ext = my_splitext(stream_file_name)

            disposition_flags = []
            for k, v in stream_dict['disposition'].items():
                if k in (
                        'closed_caption',
                ):
                    continue
                if v:
                    disposition_flags.append(k)
            ffmpeg_output_args += [
                '-disposition:%d' % (stream_dict['_temp'].out_index,),
                '+'.join(disposition_flags or ['0']),
                ]
            stream_language = isolang(stream_dict.get('language', 'und'))
            if stream_language is not isolang('und'):
                ffmpeg_output_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), 'language=%s' % (stream_language.code3,),]
            if stream_title:
                ffmpeg_output_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), 'title=%s' % (stream_title,),]
            display_aspect_ratio = stream_dict.get('display_aspect_ratio', None)
            if display_aspect_ratio:
                ffmpeg_output_args += ['-aspect:%d' % (stream_dict['_temp'].out_index,), display_aspect_ratio]

            stream_start_time = ffmpeg.Timestamp(stream_dict.get('start_time', 0))
            if stream_start_time:
                codec_encoding_delay = get_codec_encoding_delay(inputdir / stream_file_name)
                stream_start_time += codec_encoding_delay
            elif has_opus_streams and stream_file_ext in ('.opus', '.opus.ogg'):
                # Note that this is not needed if the audio track is wrapped in a mkv container
                stream_start_time = -ffmpeg.Timestamp.MAX
            if stream_start_time:
                ffmpeg_input_args += [
                    '-itsoffset', stream_start_time,
                    ]

            if stream_codec_type == 'video':
                if stream_file_ext in {'.vp9', '.vp9.ivf',}:
                    # ffmpeg does not generate packet durations from ivf -> mkv, causing some hickups at play time. But it does from .mkv -> .mkv, so create an intermediate
                    estimated_duration = estimated_duration or estimate_stream_duration(
                        ffprobe_json=MovieFile.new_by_file_name(inputdir / stream_file_name).extract_ffprobe_json())
                    tmp_stream_file_name = stream_file_name + '.mkv'
                    ffmpeg_args = default_ffmpeg_args + [
                            '-i', inputdir / stream_file_name,
                            '-codec', 'copy',
                            inputdir / tmp_stream_file_name,
                        ]
                    assert estimated_duration is None or float(estimated_duration) > 0.0
                    ffmpeg(
                        *ffmpeg_args,
                        progress_bar_max=estimated_duration,
                        progress_bar_title=f'Encap {stream_codec_type} stream {stream_index} w/ ffmpeg',
                        dry_run=app.args.dry_run,
                        y=True,  # TODO temp file
                    )
                    stream_file_name = tmp_stream_file_name
                    stream_file_base, stream_file_ext = my_splitext(stream_file_name)
                elif stream_file_ext.endswith('.mkv'):
                    pass
                elif stream_file_ext in still_image_exts:
                    pass
                else:
                    raise NotImplementedError(stream_file_ext)
            ffmpeg_input_args += [
                '-i',
                inputdir / stream_file_name,
                ]
            # Include all streams from this input file:
            ffmpeg_output_args += [
                '-map', stream_dict['_temp'].out_index,
                ]
        ffmpeg_output_args += [
            '-f', ext_to_container(output_file),
            output_file,
            ]
        ffmpeg_args = default_ffmpeg_args + ffmpeg_input_args + ffmpeg_output_args
        with perfcontext('merge w/ ffmpeg'):
            ffmpeg(*ffmpeg_args,
                   progress_bar_max=estimated_duration,
                   progress_bar_title='Merge w/ ffmpeg',
                   dry_run=app.args.dry_run,
                   y=app.args.yes)
        if mux_dict.get('chapters', None):
            chapters_xml_file = TextFile(inputdir / mux_dict['chapters']['file_name'])
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
                output_file,
                '--chapters', chapters_xml_file,
            ]
            with perfcontext('add chapters w/ mkvpropedit'):
                do_spawn_cmd(cmd)

    output_file.write_tags(tags=mux_dict['tags'],
            dry_run=app.args.dry_run,
            run_func=do_exec_cmd)
    app.log.info('DONE writing %s%s',
                 output_file.file_name,
                 ' (dry-run)' if app.args.dry_run else '')

    if app.args.auto_verify:
        try:
            old_interactive, app.args.interactive = app.args.interactive, False
            try:
                action_verify(output_file, in_tags=AlbumTags())
            finally:
                app.args.interactive = old_interactive
        except LargeDiscrepancyInStreamDurationsError as e:
            if not app.args.interactive:
                raise

            with app.need_user_attention():
                from prompt_toolkit.formatted_text import FormattedText
                from prompt_toolkit.completion import WordCompleter
                completer = WordCompleter([
                    'help',
                    'continue',
                    'retry',
                    'remux',
                    'open',
                    'quit',
                    'print',
                ])
                print('')
                app.print(
                    FormattedText([
                        ('class:error', str(e)),
                    ]))
                while True:
                    c = app.prompt(completer=completer)
                    if c in ('help', 'h', '?'):
                        print('')
                        print('List of commands:')
                        print('')
                        print('help -- Print this help')
                        print('continue -- Continue processing next action -- done')
                        print('retry -- Retry verification')
                        print('remux -- Remux from original media file')
                        print('open -- Open the output media file')
                        print('print -- Print streams summary')
                        print('quit -- Quit')
                    elif c in ('continue', 'c'):
                        break
                    elif c in ('quit', 'q'):
                        raise
                    elif c in ('remux',):
                        for original_inputfile_ext in ('.mkv', '.webm'):
                            original_inputfile = inputdir.with_name(inputdir.name + original_inputfile_ext)
                            if original_inputfile.exists():
                                break
                        else:
                            app.log.error('Original mux input file not found!')
                            continue
                        if e.inputdir.exists():
                            shutil.rmtree(e.inputdir)
                        old_remux, app.args.remux = app.args.remux, True
                        old_chain, app.args.chain = app.args.chain, False
                        try:
                            action_mux(original_inputfile, in_tags=in_tags)
                        finally:
                            app.args.chain = old_chain
                            app.args.remux = old_remux
                        if app.args.chain:
                            action_optimize(inputdir, in_tags=in_tags)
                            action_demux(inputdir, in_tags=in_tags)
                            return True
                    elif c in ('open',):
                        try:
                            xdg_open(output_file)
                        except Exception as e:
                            app.log.error(e)
                    elif c in ('print', 'p'):
                        print_streams_summary(mux_dict=mux_dict)
                    else:
                        app.log.error('Invalid input')

        app.log.info('DONE writing & verifying %s%s',
                     output_file.file_name,
                     ' (dry-run)' if app.args.dry_run else '')

    if app.args.cleanup:
        app.log.info('Cleaning up %s', inputdir)
        shutil.rmtree(inputdir)

    return True

def action_merge(merge_files, in_tags):
    tags = copy.copy(in_tags)

    merged_file_name = 'merged.mkv'
    merged_file = MediaFile.new_by_file_name(merged_file_name)

    merge_files = [
        inputfile if isinstance(inputfile, MediaFile) else MediaFile.new_by_file_name(inputfile)
        for inputfile in merge_files]

    chaps = Chapters()
    prev_chap = Chapter(0, 0)
    for inputfile in merge_files:
        ffprobe_json = inputfile.extract_ffprobe_json()
        inputfile.duration = float(ffmpeg.Timestamp(ffprobe_json['format']['duration']))
        # inputfile.extract_info(need_actual_duration=True)
        chap = Chapter(start=prev_chap.end,
                       end=prev_chap.end + inputfile.duration,
                       title=re.sub(r'\.demux$', '', my_splitext(inputfile.file_name.name)[0]),
                       )
        chaps.append(chap)
    chapters_xml = chaps.to_mkv_xml()
    if app.args.interactive:
        chapters_xml = edvar(chapters_xml,
                             preserve_whitespace_tags=Chapters.MKV_XML_VALUE_TAGS)[1]
    chapters_xml_file = TempFile.mkstemp(suffix='.chapters.xml', open=True, text=True)
    chapters_xml.write(chapters_xml_file.fp,
                       xml_declaration=True,
                       encoding='unicode',  # Force string
                       )
    chapters_xml_file.close()

    concat_list_temp_file = TempFile.mkstemp(suffix='.concat.lst', open=True, text=True)
    concat_list_file = ffmpeg.ConcatScriptFile(concat_list_temp_file)
    concat_list_file.files += [
        concat_list_file.File(inputfile.file_name.resolve())  # absolute
        for inputfile in merge_files]
    concat_list_file.create()

    ffmpeg_concat_args = []
    ffmpeg_args = default_ffmpeg_args + [
        '-f', 'concat', '-safe', '0', '-i', concat_list_file,
        '-codec', 'copy',
    ] + ffmpeg_concat_args + [
        '-start_at_zero',
        '-f', ext_to_container(merged_file), merged_file,
    ]
    with perfcontext('Merge w/ ffmpeg'):
        ffmpeg(*ffmpeg_args,
               progress_bar_max=chaps.chapters[-1].end,
               progress_bar_title=f'Merge w/ ffmpeg',
               dry_run=app.args.dry_run,
               y=app.args.yes)

    cmd = [
        'mkvpropedit',
        merged_file,
        '--chapters', chapters_xml_file,
    ]
    with perfcontext('add chapters w/ mkvpropedit'):
        do_spawn_cmd(cmd)

    return True

def action_tag_episodes(episode_file_names, in_tags):
    tags = copy.copy(in_tags)

    t = [os.fspath(e) for e in episode_file_names]
    if t != sorted(t):
        m = 'Episode file names not sorted; This is likely a mistake.'
        if app.args.force:
            app.log.warning(m + ' (--force used; Bypassing)')
        else:
            raise ValueError(m + ' (use --force to bypass)')

    if episode_file_names[0].is_dir():
        seed_initial_text = episode_file_names[0].name
    else:
        seed_initial_text = episode_file_names[0].parent.name

    if app.args.interactive:

        if tags.tvshow is None:
            tvshow_initial_text = ''
            m = re.search(r'^(.*?)(?:S(\d+))?$', seed_initial_text)
            if m:
                tvshow_initial_text = m.group(1)
                tvshow_initial_text = unmangle_search_string(tvshow_initial_text)
        else:
            tvshow_initial_text = tags.tvshow

        if tags.season is None:
            season_initial_text = ''
            m = re.search(r'^(.*)S(\d+)$', seed_initial_text)
            if m:
                season_initial_text = m.group(2)
        else:
            season_initial_text = str(tags.season)

        from prompt_toolkit.application.current import get_app
        from prompt_toolkit.layout.dimension import Dimension as D
        from prompt_toolkit.layout.containers import HSplit, VSplit
        from prompt_toolkit.widgets import (
            Box,
            Button,
            TextArea,
            Dialog,
            Label,
        )
        from prompt_toolkit.shortcuts.dialogs import (
            _return_none,
        )

        def tvshow_accept(buf):
            get_app().layout.focus(season_textarea)
            return True  # Keep text.
        tvshow_textarea = TextArea(
            text=tvshow_initial_text,
            multiline=False,
            accept_handler=tvshow_accept)

        def season_accept(buf):
            get_app().layout.focus(language_textarea)
            return True  # Keep text.
        season_textarea = TextArea(
            text=season_initial_text,
            multiline=False,
            accept_handler=season_accept)

        def language_accept(buf):
            get_app().layout.focus(ok_button)
            return True  # Keep text.
        language_textarea = TextArea(
            text=str(tags.language or ''),
            multiline=False,
            accept_handler=language_accept)

        def ok_handler():
            get_app().exit(result=(
                tvshow_textarea.text,
                season_textarea.text,
                language_textarea.text,
            ))
        ok_button = Button(text='Ok', handler=ok_handler)

        cancel_button = Button(text='Cancel', handler=_return_none)

        dialog = Dialog(
            title='Episode tagging',
            body=HSplit([
                VSplit([
                    Box(Label(text='TV Show:'), padding_left=0, width=10),
                    tvshow_textarea,
                ]),
                VSplit([
                    Box(Label(text='Season:'), padding_left=0, width=10),
                    season_textarea,
                ]),
                VSplit([
                    Box(Label(text='Language:'), padding_left=0, width=10),
                    language_textarea,
                ]),
            ], padding=D(preferred=1, max=1)),
            buttons=[ok_button, cancel_button],
            with_background=True)

        result = app.run_dialog(dialog)
        if result is None:
            raise ValueError('Cancelled by user!')
        tags.tvshow, tags.season, tags.language = result

    if not tags.tvshow:
        raise ValueError('Missing tvshow')
    if tags.season is None:
        raise ValueError('Missing season number')

    tags.type = tags.deduce_type()
    assert str(tags.type) == 'tvshow'

    global tvdb
    if tvdb is None:
        global qip
        import qip.thetvdb
        tvdb = qip.thetvdb.Tvdb(
            apikey='d38d1a8df34d030f1be077798db952bc',  # mmdemux
            interactive=app.args.interactive,
        )
    tvdb.language = tags.language

    l_series = tvdb.search(tags.tvshow)
    app.log.debug('l_series=%r', l_series)
    assert l_series, "No series!"
    i = 0
    if len(l_series) > 1 and app.args.interactive:
        from prompt_toolkit.shortcuts.dialogs import radiolist_dialog
        i = radiolist_dialog(
            title='Please select a series',
            values=[(i, '{seriesName} [{language}], {network}, {firstAired}, {status} (#{id})'.format_map(d_series))
                    for i, d_series in enumerate(l_series)],
            style=app.prompt_style)
        if i is None:
            raise ValueError('Cancelled by user!')
    d_series = l_series[i]
    tags.tvshow = d_series['seriesName']

    o_show = tvdb[d_series['id']]
    app.log.debug('o_show=%r', o_show)
    o_season = o_show[tags.season]
    app.log.debug('o_season=%r', o_season)

    if len(episode_file_names) == 1 and episode_file_names[0].is_dir():
        episode_file_names = sorted(episode_file_names[0].glob('*.mkv'))
    app.log.debug('episode_file_names=%r', episode_file_names)

    if len(episode_file_names) != len(o_season):
        raise ValueError(f'Number of files ({len(episode_file_names)}) does not match number of season {tags.season} episodes ({len(o_season)})')

    episode_files = [
        MovieFile.new_by_file_name(episode_file_name)
        for episode_file_name in episode_file_names]
    for episode_file, i_episode in zip(episode_files, o_season.keys()):
        o_episode = o_season[i_episode]
        app.log.debug('episode_file=%r, o_episode=%r:\n%s', episode_file, o_episode, pprint.pformat(dict(o_episode)))
        # {'absoluteNumber': 125,
        #  'airedEpisodeNumber': 21,
        #  'airedSeason': 6,
        #  'airedSeasonID': 13744,
        #  'airsAfterSeason': None,
        #  'airsBeforeEpisode': None,
        #  'airsBeforeSeason': None,
        #  'contentRating': 'TV-PG',
        #  'directors': ['Michael Preece'],
        #  'dvdChapter': None,
        #  'dvdDiscid': '',
        #  'dvdEpisodeNumber': 21,
        #  'dvdSeason': 6,
        #  'episodeName': 'Hind-Sight',
        #  'filename': 'http://thetvdb.com/banners/episodes/77847/261278.jpg',
        #  'firstAired': '1991-05-06',
        #  'guestStars': ['Barbara E. Russell',
        #                 'Bruce Harwood',
        #                 'Bruce McGill',
        #                 'Linda Darlow',
        #                 'Michael Des Barres',
        #                 'Michele Chan'],
        #  'id': 261278,
        #  'imdbId': 'tt0638724',
        #  'isMovie': 0,
        #  'language': {'episodeName': 'en', 'overview': 'en'},
        #  'lastUpdated': 1555583455,
        #  'lastUpdatedBy': 1,
        #  'overview': 'As Pete waits for glaucoma surgery, he and MacGyver reminisce '
        #              'about their past adventures and try to figure out who has been '
        #              'sending some vaguely threatening messages to Pete.',
        #  'productionCode': '126',
        #  'seriesId': 77847,
        #  'showUrl': '',
        #  'siteRating': 0,
        #  'siteRatingCount': 0,
        #  'thumbAdded': '',
        #  'thumbAuthor': None,
        #  'thumbHeight': '360',
        #  'thumbWidth': '640',
        #  'writers': ['Rick Mittleman']}
        episode_file.tags.update(episode_file.load_tags(file_type='tvshow'))
        episode_file.tags.update(tags)
        episode_file.tags.episode = o_episode['airedEpisodeNumber']
        episode_file.tags.title = o_episode['episodeName']
        episode_file.tags.date = o_episode['firstAired']
        app.log.info('%s: %s', episode_file, episode_file.tags.short_str())
        episode_file.write_tags(tags=episode_file.tags,
                                dry_run=app.args.dry_run)
        if app.args.rename:
            from qip.bin.organize_media import organize_tvshow
            opath = organize_tvshow(episode_file, suggest_tags=TrackTags())
            opath = episode_file.file_name.with_name(opath.name)
            if opath != episode_file.file_name:
                if opath.exists():
                    raise OSError(errno.EEXIST, opath)
                if app.args.dry_run:
                    app.log.info('  Rename to %s. (dry-run)', opath)
                else:
                    app.log.info('  Rename to %s.', opath)
                    episode_file.rename(opath)
                    episode_file.file_name = opath

if __name__ == "__main__":
    main()
