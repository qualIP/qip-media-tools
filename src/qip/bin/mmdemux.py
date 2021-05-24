#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :
# PYTHON_ARGCOMPLETE_OK

#if __name__ == '__main__':
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, 'lib', 'python'))

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
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

import unidecode
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.widgets import TextArea
from tabulate import tabulate

from qip import argparse
from qip import json
from qip import threading
from qip.app import app
from qip.ccextractor import ccextractor
from qip.cdrom import cdrom_ready
from qip.ddrescue import ddrescue
from qip.exec import SpawnedProcessError, dbg_exec_cmd, do_exec_cmd, do_popen_cmd, do_spawn_cmd, clean_cmd_output, edfile, edvar, eddiff, xdg_open, list2cmdline, clean_file_name
from qip.ffmpeg import ffmpeg, ffprobe
from qip.file import toPath
from qip.frim import FRIMDecode
from qip.handbrake import HandBrake
from qip.isolang import isolang
from qip.matroska import mkvextract
from qip.mediainfo import mediainfo
from qip.mencoder import mencoder
from qip.mkvmerge import mkvmerge
from qip.mm import Chapter, Chapters, FrameRate, CodecType, BroadcastFormat, MediaTagEnum, TrackTags, AlbumTags, MediaType, ContentType, Stereo3DMode
from qip.mplayer import mplayer
from qip.opusenc import opusenc
from qip.perf import perfcontext
from qip.propex import propex
from qip.utils import byte_decode, Ratio, round_half_away_from_zero, dict_from_swig_obj, Auto
import qip.file
import qip.mm
import qip.utils

qip.file.load_all_file_types()

from qip.file import BinaryFile
from qip.file import File
from qip.file import TextFile
from qip.file import XmlFile
from qip.img import ImageFile
from qip.json import JsonFile
from qip.matroska import MatroskaChaptersFile
from qip.matroska import MatroskaFile
from qip.matroska import MkvFile
from qip.mm import BinarySubtitleFile
from qip.mm import MediaFile
from qip.mm import MovieFile
from qip.mm import SoundFile
from qip.mm import SubtitleFile
from qip.mm import TextSubtitleFile
from qip.mp2 import Mpeg2ContainerFile
from qip.mp2 import VobFile
from qip.mp4 import M4aFile
from qip.mp4 import Mpeg4ContainerFile
from qip.pgs import PgsFile

try:
    from qip.utils import ProgressBar
except ImportError:
    ProgressBar = None

tmdb = None
tvdb = None

thread_executor = None
slurm_executor = None

default_minlength_tvshow = qip.utils.Timestamp('15m')
default_minlength_movie = qip.utils.Timestamp('60m')

def AnyTimestamp(value):
    try:
        return qip.utils.Timestamp(value)
    except ValueError:
        return qip.utils.Timestamp(ffmpeg.Timestamp(value))

default_ffmpeg_args = []

#map_RatioConverter = {
#    Ratio('186:157'):
#    Ratio('279:157'):
#}
#def RatioConverter(ratio)
#    ratio = Ratio(ratio)
#    ratio = map_RatioConverter.get(ratio, ratio)
#    return ratio

def round_packet_time(duration, exp=Decimal('0.000001'), rounding=decimal.ROUND_HALF_UP):
    return Decimal(duration).quantize(exp, rounding)

def calc_packet_time(value, time_base):
    if value is not None:
        return Decimal(value) * time_base.numerator / time_base.denominator

# https://www.ffmpeg.org/ffmpeg.html

class FieldOrderUnknownError(NotImplementedError):

    def __init__(self, mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order):
        self.mediainfo_scantype = mediainfo_scantype
        self.mediainfo_scanorder = mediainfo_scanorder
        self.ffprobe_field_order = ffprobe_field_order
        super().__init__((mediainfo_scantype, mediainfo_scanorder, ffprobe_field_order))

class StreamCharacteristicsSeenError(ValueError):

    def __init__(self, stream, stream_characteristics):
        self.stream = stream
        self.stream_characteristics = stream_characteristics
        s = ', '.join(f'{k}: {v}' for k, v in stream_characteristics.items())
        super().__init__(f'Stream #{stream.pprint_index} characteristics already seen: {s}')

class StreamLanguageUnknownError(ValueError):

    def __init__(self, stream):
        self.stream = stream
        super().__init__(f'Stream #{stream.pprint_index} language is unknown')

class StreamExternalSubtitleAlreadyCreated(ValueError):

    def __init__(self, stream, external_stream_file_name):
        self.stream = stream
        self.external_stream_file_name = external_stream_file_name
        super().__init__(f'Stream {stream.pprint_index} External subtitle file already created: {external_stream_file_name}')

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

def parse_Enum_or_None(e):

    def f(v):
        if v == 'None':
            return None
        return e(v)

    f.__name__ = f'{e.__name__}_or_None'

    f.ArgumentError_msg = \
        'invalid choice: %%(value)r (choose from %s)' % (
            ', '.join(sorted(repr(v)
                             for v in (
                                     'None',
                             ) + tuple(member.name for member in e))
                      ).replace('%', '%%'),
        )

    return f

Stereo3DMode_or_None = parse_Enum_or_None(Stereo3DMode)
BroadcastFormat_or_None = parse_Enum_or_None(BroadcastFormat)

def unmangle_search_string(initial_text):
    initial_text = unidecode.unidecode(initial_text)
    initial_text = initial_text.strip()                                #  ABC   -> ABC
    initial_text = re.sub(r'(?=[A-Z][a-z])(?<!Mc)(?<!Mac)', r' ', initial_text)       # AbCDef ->  AbC Def (not Mc Donald)
    initial_text = re.sub(r'[a-z](?=[A-Z])(?<!Mc)(?<!Mac)', r'\g<0> ', initial_text)  # AbC Def -> Ab C Def (not Mc Donald)
    initial_text = re.sub(r'[A-Za-z](?=\d)', r'\g<0> ', initial_text)  # ABC123 -> ABC 123
    p = None
    while initial_text != p:
        p = initial_text
        initial_text = re.sub(r'(.+),\s*(The|A|An|Le|La|Les)$', r'\2 \1', initial_text, flags=re.IGNORECASE)  # ABC, The -> The ABC
        initial_text = re.sub(r'[^A-Za-z0-9\']+', r' ', initial_text)      # AB$_12 -> AB 12
        initial_text = initial_text.strip()                                #  ABC   -> ABC
        initial_text = re.sub(r'(?:DVD\|Blu[- ]?ray)$', r'', initial_text, flags=re.IGNORECASE)  # ABC Blu Ray -> ABC
        initial_text = re.sub(r'(?: the)? (?:\w+(?:\'s)?|\d+[a-z]+ anniversary) (?:edition|cut)$', r'', initial_text, flags=re.IGNORECASE)  # ABC special edition -> ABC
        initial_text = re.sub(r' dis[ck] [0-9]+$', r'', initial_text, flags=re.IGNORECASE)  # ABC disc 1 -> ABC
    return initial_text

webm_codec_names = {
    # video
    'vp8',
    'vp9',
    # audio
    'opus',
    # subtitle
    'webvtt',
}

mkv_codec_names = webm_codec_names | {
    # image
    'png', 'mjpeg',
    # subtitle
    'dvd_subtitle',
    'hdmv_pgs_subtitle',
}

ffv1_codec_names = {
    # video
    'ffv1',
}

def get_target_codec_names(webm):
    if webm is True:  # not Auto
        target_codec_names = set(webm_codec_names)
    else:
        target_codec_names = set(mkv_codec_names)
        if app.args.ffv1:
            target_codec_names |= ffv1_codec_names
    return target_codec_names

def av_stream_frame_timing_str(av_stream, av_frame):
    return f'stream_index={av_stream.index}, pkt_pos={av_frame.pkt_pos}, dts={getattr(av_frame, "dts", "<notset>")}, pts={av_frame.pts}, pkt_duration={av_frame.pkt_duration}, I?{int(av_frame.interlaced_frame)}, R?{int(av_frame.repeat_pict)}, T?{int(av_frame.top_field_first)}'


class ObjectWrapper(object):

    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name, getattr=getattr):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._obj, name)


def fixup_iter_av_frames(av_stream_frames):

    # TODO support multi-stream
    prev_av_frame = types.SimpleNamespace(
        dts=0,
        pts=0,
        pkt_pos=0,
        pkt_duration=0,
    )

    for av_stream, av_frame in av_stream_frames:

        pts = av_frame.pts
        dts = av_frame.dts
        if pts is None or dts is None:
            if pts is None:
                pts = dts
                if pts is None:
                    pts = prev_av_frame.pts + prev_av_frame.pkt_duration
            if dts is None:
                dts = pts
            av_frame = ObjectWrapper(av_frame)
            av_frame.dts = dts
            av_frame.pts = pts

        yield av_stream, av_frame

        prev_av_frame = av_frame

def sync_iter_av_frames(av_stream_frames):

    # See http://dranger.com/ffmpeg/tutorial05.html

    # TODO support multi-stream
    video_clock = 0.0  # seconds

    for av_stream, av_frame in av_stream_frames:
        time_base = av_stream.time_base

        pts = av_frame.pts
        if pts is not None:
            # if we have pts, set video clock to it
            video_clock = pts * time_base
        else:
            # if we aren't given a pts, set it to the clock
            pts = int(video_clock / time_base)
            av_frame = ObjectWrapper(av_frame)
            av_frame.pts = pts

        # TODO
        # # update the video clock (seconds)
        # frame_delay = av_stream.codec_context.time_base
        # # if we are repeating a frame, adjust clock accordingly
        # frame_delay += av_frame.repeat_pict * (frame_delay * 0.5)  # extra_delay = repeat_pict / (2*fps)
        # video_clock += frame_delay
        video_clock += av_frame.pkt_duration * time_base

        yield av_stream, av_frame

def ffprobe_iter_av_frames(file, stream_index=0):

    for ff_frame in ffprobe.iter_frames(file,
                                        # [error] Failed to set value 'nvdec' for option 'hwaccel': Option not found
                                        # TODO default_ffmpeg_args=default_ffmpeg_args,
                                        ):
        if ff_frame.stream_index != stream_index:
            continue
        # assert frame.media_type == 'video'

        av_stream = types.SimpleNamespace(
            index=ff_frame.stream_index,
        )

        av_frame = types.SimpleNamespace(
            pkt_pos=ff_frame.pkt_pos,
            dts=ff_frame.pkt_dts,
            pts=ff_frame.pkt_pts,
            pkt_duration=ff_frame.pkt_duration,
            interlaced_frame=ff_frame.interlaced_frame,
            repeat_pict=ff_frame.repeat_pict,
            top_field_first=ff_frame.top_field_first,
        )

        yield av_stream, av_frame

def iter_av_frames(file, stream_index=0, max_analyze_duration=100 * 1000000):
    with av.open(os.fspath(file)) as av_file:
        av_file.flags = 0
        av_file.auto_bsf = app.args.autobsf
        av_file.gen_pts = app.args.genpts
        av_file.ign_dts = app.args.igndts
        av_file.discard_corrupt = app.args.discardcorrupt
        av_file.sort_dts = app.args.sortdts
        av_file.max_analyze_duration = max_analyze_duration
        for av_stream in av_file.streams:
            if av_stream.index != stream_index:
                continue
            # assert av_stream.type == 'video'
            av_packets = av_file.demux(av_stream)
            for av_packet in av_packets:
                for av_frame in av_packet.decode():
                    yield av_stream, av_frame

try:
    import av
except ImportError as e:
    app.log.warning(f'PyAV not found: {e}')
    app.log.warning(f'Will use slower analysis using ffprobe.')
    iter_av_frames = ffprobe_iter_av_frames

def analyze_field_order_and_framerate(
        *,
        stream_file,
        ffprobe_stream_json,
        mediainfo_track_dict,
        stream_dict=None,
):
    field_order = getattr(app.args, 'force_field_order', None)
    input_framerate = None
    framerate = getattr(app.args, 'force_framerate', None)

    video_frames = []

    if stream_dict:
        if framerate is None:
            framerate = getattr(stream_dict, 'framerate', None)
        if field_order is None:
            field_order = getattr(stream_dict, 'field_order', None)

    if mediainfo_track_dict['@type'] == 'Image':
        if field_order is None:
            field_order = 'progressive'
        if framerate is None:
            framerate = FrameRate(1, 1)

    if field_order is None:
        if '-pullup.' in stream_file.file_name.name:
            field_order = 'progressive'
        elif '.progressive.' in stream_file.file_name.name:
            field_order = 'progressive'

    if field_order is None:
        with perfcontext('Analyze field order', log=True):

            mediainfo_scantype = mediainfo_track_dict.get('ScanType', None)
            mediainfo_scanorder = mediainfo_track_dict.get('ScanOrder', None)
            ffprobe_field_order = ffprobe_stream_json.get('field_order', 'progressive')
            time_base = Fraction(ffprobe_stream_json['time_base'])

            video_analyze_duration = app.args.video_analyze_duration
            try:
                mediainfo_duration = AnyTimestamp(mediainfo_track_dict['Duration'])
            except KeyError:
                pass
            else:
                # Sometimes mediainfo'd Duration is just the first frame duration
                if False and mediainfo_duration >= 1.0:
                    video_analyze_duration = min(mediainfo_duration, video_analyze_duration)
            with perfcontext('Frames iteration'):
                progress_bar = None
                if ProgressBar is not None:
                    progress_bar = ProgressBar('iterate frames',
                                           max=float(video_analyze_duration),
                                           suffix='%(index)d/%(max)d (%(eta_td)s remaining)')
                try:

                    video_frames = []

                    av_stream_frames = iter_av_frames(stream_file)
                    av_stream_frames = sync_iter_av_frames(av_stream_frames)
                    for av_stream, av_frame in av_stream_frames:
                        video_frames.append((av_stream, av_frame))

                        float_pts_time = float(calc_packet_time(av_frame.pts, time_base))
                        if progress_bar is not None:
                            if int(progress_bar.index) != int(float_pts_time):
                                progress_bar.goto(float_pts_time)
                        if float_pts_time >= video_analyze_duration:
                            break

                finally:
                    if progress_bar is not None:
                        progress_bar.finish()

            app.log.debug('Analyzing %d video frames...', len(video_frames))

            video_frames = video_frames[app.args.video_analyze_skip_frames:]  # Skip first frames; Often padded with different field order
            assert video_frames, f'No video frames found to analyze! (--video-analyze-skip-frames {app.args.video_analyze_skip_frames!r})'

            field_order_diags = []

            # XXXJST:
            # Based on libmediainfo-18.12/Source/MediaInfo/Video/File_Mpegv.cpp
            # though getting the proper TemporalReference is more complex and may
            # be different than dts_time ordering.
            temporal_string = ''.join([
                ('T' if av_frame.top_field_first else 'B') + ('3' if av_frame.repeat_pict else '2')
                for av_stream, av_frame in video_frames])
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
                        app.log.debug('found_frames: \n%s', pprint.pformat([av_stream_frame_timing_str(av_stream, av_frame) for av_stream, av_frame in found_frames]))
                    field_order = result_field_order
                    interlacement = result_interlacement
                    # framerate = FrameRate(1 / (
                    #     time_base
                    #     * sum(av_frame.pkt_duration for av_stream, av_frame in found_frames)
                    #     / len(found_frames)))
                    #calc_framerate = framerate = FrameRate(1 / (Fraction(
                    #    found_frames[-1][1].pts - found_frames[0][1].pts
                    #    + found_frames[-1][0].duration,
                    #    len(found_frames)) * time_base))
                    #framerate = framerate.round_common()
                    found_pkt_duration_times = [
                            round_packet_time(calc_packet_time(av_frame.pkt_duration, time_base))
                            for av_stream, av_frame in found_frames]
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
                        last_av_stream, last_av_frame = video_frames[-1]
                        last_av_frame_pkt_duration_time = round_packet_time(calc_packet_time(last_av_frame.pkt_duration, time_base))
                        if temporal_string.endswith('T2' * 12):
                            if last_av_frame_pkt_duration_time in (
                                        Decimal('0.033367'),
                                    ):
                                input_framerate = framerate = FrameRate(30000, 1001)
                            elif last_av_frame_pkt_duration_time in (
                                        Decimal('0.041708'),
                                    ):
                                input_framerate = framerate = FrameRate(24000, 1001)
                            else:
                                raise ValueError(f'Unexpected last AV packet duration: {last_av_frame_pkt_duration_time}')
                            app.log.warning('Also detected field order progressive or tt at %s (%.3f) fps based on temporal pattern at end of analysis section', framerate, framerate)
                        elif temporal_string.endswith('B2' * 12):
                            if last_av_frame_pkt_duration_time in (
                                        Decimal('0.033367'),
                                    ):
                                input_framerate = framerate = FrameRate(30000, 1001)
                            elif last_av_frame_pkt_duration_time in (
                                        Decimal('0.041708'),
                                    ):
                                input_framerate = framerate = FrameRate(24000, 1001)
                            else:
                                raise ValueError(f'Unexpected last AV packet duration: {last_av_frame_pkt_duration_time}')
                            app.log.warning('Also detected field order progressive or bb at %s (%.3f) fps based on temporal pattern at end of analysis section', framerate, framerate)
                    else:
                        # ends with pulldown
                        app.log.warning('Detected field order %s at %s (%.3f) fps based on temporal pattern near end of analysis section %r', field_order, framerate, framerate, temporal_pattern)
                        assert input_framerate == FrameRate(30000, 1001)  # Only verified case so far
                        assert framerate == FrameRate(24000, 1001)  # Only verified case so far
                        # assert framerate == original_framerate * result_framerate_ratio
                    break

            if field_order is None:
                av_stream0, av_frame0 = video_frames[0]
                if framerate is not None:
                    constant_framerate = True
                else:
                    constant_framerate = all(
                            av_frame.pkt_duration == av_frame0.pkt_duration
                            for av_stream, av_frame in video_frames)
                if constant_framerate:
                    if framerate is None:
                        if False:
                            av_frame0_pkt_duration_time = round_packet_time(calc_packet_time(av_frame0.pkt_duration, time_base))
                            if av_frame0_pkt_duration_time in (
                                        Decimal('0.033367'),
                                        Decimal('0.033000'),
                                    ):
                                framerate = FrameRate(30000, 1001)
                            elif av_frame0_pkt_duration_time in (
                                        Decimal('0.041000'),
                                    ):
                                framerate = FrameRate(24000, 1001)
                            else:
                                raise NotImplementedError(av_frame0_pkt_duration_time)
                        elif False:
                            pts_sum = sum(
                                frameB.pts - frameA.pts
                                for frameA, frameB in zip(video_frames[0:-2], video_frames[1:-1]))  # Last frame may not have either dts and pts
                            framerate = FrameRate(1 / (time_base * pts_sum / (len(video_frames) - 2)), 1)
                            app.log.debug('framerate = 1 / (%r * %r / (%r - 2)) = %r = %r', time_base, pts_sum, len(video_frames), framerate, float(framerate))
                            # framerate = FrameRate(1 / (calc_packet_time(av_frame0.pkt_duration, time_base)))
                            framerate = framerate.round_common()
                            app.log.debug('framerate.round_common() = %r = %r', framerate, float(framerate))
                        else:
                            assert len(video_frames) > 5, f'Not enough precision, only {len(video_frames)} frames analyzed. (Use --force-framerate and --force-field-order?)'
                            pts_diff = (
                                video_frames[-2][1].pts  # Last frame may not have either dts and pts
                                - video_frames[0][1].pts)
                            framerate = FrameRate(1 / (time_base * pts_diff / (len(video_frames) - 2)), 1)
                            app.log.debug('framerate = 1 / (%r * %r) / (%r - 2) = %r = %r', time_base, pts_diff, len(video_frames), framerate, float(framerate))
                            framerate = framerate.round_common()
                            app.log.debug('framerate.round_common() = %r = %r', framerate, float(framerate))
                        app.log.debug('Constant %s (%.3f) fps found...', framerate, framerate)

                    all_same_interlaced_frame = all(
                            av_frame.interlaced_frame == av_frame0.interlaced_frame
                            for av_stream, av_frame in video_frames)
                    if all_same_interlaced_frame:
                        if av_frame0.interlaced_frame:
                            all_same_top_field_first = all(
                                    av_frame.top_field_first == av_frame0.top_field_first
                                    for av_stream, av_frame in video_frames)
                            if all_same_top_field_first:
                                if av_frame0.top_field_first:
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
                    # v_pick_framerate = pick_framerate(stream_file.file_name, stream_file.ffprobe_dict, ffprobe_stream_json, mediainfo_track_dict, field_order=field_order)
                    # assert framerate == v_pick_framerate, f'constant framerate ({framerate}) does not match picked framerate ({v_pick_framerate})'
                else:
                    field_order_diags.append('Variable fps found.')
                    if app.log.isEnabledFor(logging.DEBUG):
                        fps_stats = collections.Counter([av_frame.pkt_duration
                                                         for av_stream, av_frame in video_frames])
                        app.log.debug('field_order_diags: %r', field_order_diags)
                        app.log.debug('Fps stats: %s',
                                      ', '.join(
                                          '{:.2f}({:.2%})'.format(1 / (calc_packet_time(duration, time_base)), fps_stats_count / len(video_frames))
                                          for duration, fps_stats_count in fps_stats.most_common()))


            if False and field_order is None:
                for time_long, time_short, result_framerate in (
                        (Decimal('0.050050'), Decimal('0.033367'), FrameRate(24000, 1001)),
                        (Decimal('0.050000'), Decimal('0.033000'), FrameRate(24000, 1001)),
                ):
                    i = 0
                    while i < len(video_frames) and round_packet_time(calc_packet_time(video_frames[i][0].duration, time_base)) == time_short:
                        i += 1
                    for c in range(3):
                        if i < len(video_frames) and round_packet_time(calc_packet_time(video_frames[i][0].duration, time_base)) == time_long:
                            i += 1
                    while i < len(video_frames) and round_packet_time(calc_packet_time(video_frames[i][0].duration, time_base)) == time_short:
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
                            round_packet_time(calc_packet_time(video_frames[i+0][0].duration, time_base)),
                            round_packet_time(calc_packet_time(video_frames[i+1][0].duration, time_base)),
                            round_packet_time(calc_packet_time(video_frames[i+2][0].duration, time_base)),
                            round_packet_time(calc_packet_time(video_frames[i+3][0].duration, time_base)),
                            round_packet_time(calc_packet_time(video_frames[i+4][0].duration, time_base)),
                            round_packet_time(calc_packet_time(video_frames[i+5][0].duration, time_base)),
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
                #    print('pkt_duration_time=%r, interlaced_frame=%r' % (calc_packet_time(video_frames[i][0].duration, time_base), video_frames[i][1].interlaced_frame))
                # pkt_duration_time=0.033000|interlaced_frame=1|top_field_first=1 = tt @ 30000/1001 ?
                # pkt_duration_time=0.041000|interlaced_frame=0|top_field_first=0 = progressive @ 24000/1001 ?
                field_order = pick_field_order(stream_file.file_name, stream_file.ffprobe_dict, ffprobe_stream_json, mediainfo_track_dict)

    if field_order is None:
        raise NotImplementedError('field_order unknown' \
                                  + (': ' + ' '.join(field_order_diags)
                                     if field_order_diags else ''))

    if framerate is None:
        framerate = pick_framerate(stream_file.file_name, stream_file.ffprobe_dict, ffprobe_stream_json, mediainfo_track_dict, field_order=field_order)

    return field_order, input_framerate, framerate

global_stats = types.SimpleNamespace(
    num_batch_skips=0,
)

def _resolved_Path(path):
    return Path(path).resolve()

def _mux_dir_Path(path):
    path = Path(path)
    mux_file = path / 'mux.json'
    if mux_file.exists():
        return path
    if path.is_file():
        if path.name == 'mux.json':
            return path.parent
        inputfile_base, inputfile_ext = my_splitext(path)
        path2 = Path(inputfile_base)
        mux_file2 = path2 / 'mux.json'
        if mux_file2.exists():
            return path2
    raise OSError(errno.EEXIST, f'No such file: {mux_file}')

class NumericTextArea(TextArea):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.control.key_bindings is None:
            from prompt_toolkit.key_binding.key_bindings import KeyBindings
            self.control.key_bindings = KeyBindings()
        self.control.key_bindings.add('c-a')(self.numeric_text_area_incr)
        self.control.key_bindings.add('c-x')(self.numeric_text_area_decr)

    def numeric_text_area_incr(self, event):
        try:
            self.text = str(int(self.text) + 1)
        except ValueError:
            pass

    def numeric_text_area_decr(self, event):
        try:
            self.text = str(int(self.text) - 1)
        except ValueError:
            pass

@app.main_wrapper
def main():
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
    pgroup.add_bool_argument('--interactive', '-i', help='enable interactive mode')
    pgroup.add_bool_argument('--dry-run', '-n', help='enable dry-run mode')
    pgroup.add_bool_argument('--yes', '-y', help='answer "yes" to all prompts', neg_help='do not answer prompts')
    pgroup.add_bool_argument('--save-temps', default=False, help='do not delete intermediate files')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')
    pgroup.add_bool_argument('--continue', dest='_continue', help='enable continue mode')
    pgroup.add_bool_argument('--force', '-f', help='enable force mode')
    pgroup.add_bool_argument('--batch', '-B', help='enable batch mode')
    pgroup.add_bool_argument('--step', help='enable step mode')
    pgroup.add_bool_argument('--cuda', help='enable CUDA')
    pgroup.add_bool_argument('--alpha', help='enable alpha features')
    pgroup.add_bool_argument('--slurm', help='enable slurm')
    pgroup.add_argument('--jobs', '-j', type=int, nargs=argparse.OPTIONAL, default=1, const=Auto, help='specifies the number of jobs (threads) to run simultaneously')

    pgroup = app.parser.add_argument_group('Tools Control')
    pgroup.add_argument('--rip-tool', default=Auto, choices=('makemkv', 'mplayer'), help='tool to rip tracks')
    pgroup.add_argument('--track-extract-tool', default=Auto, choices=('ffmpeg', 'mkvextract'), help='tool to extract tracks')
    pgroup.add_argument('--pullup-tool', default=Auto, choices=('yuvkineco', 'ffmpeg', 'mencoder'), help='tool to pullup any 23pulldown video tracks')
    pgroup.add_argument('--ionice', default=None, type=int, help='ionice process level')
    pgroup.add_argument('--nice', default=None, type=int, help='nice process adjustment')
    pgroup.add_bool_argument('--check-cdrom-ready', default=True, help='check CDROM readiness')
    pgroup.add_argument('--cdrom-ready-timeout', default=24, type=int, help='CDROM readiness timeout')

    pgroup = app.parser.add_argument_group('Ripping Control')
    pgroup.add_argument('--device', default=Path(os.environ.get('CDROM', '/dev/cdrom')), type=_resolved_Path, help='specify alternate cdrom device')
    pgroup.add_argument('--minlength', default=Auto, type=AnyTimestamp, help='minimum title length for ripping (default: ' + default_minlength_movie.friendly_str() + ' (movie), ' + default_minlength_tvshow.friendly_str() + ' (tvshow))')
    pgroup.add_bool_argument('--check-start-time', default=Auto, help='check start time of tracks')
    pgroup.add_argument('--stage', default=Auto, type=int, choices=range(1, 3 + 1), help='specify ripping stage (--rip-iso)')
    # For argument compatibility with safecopy
    pgroup.add_argument('--stage1', dest='stage', default=argparse.SUPPRESS, action='store_const', const=1, help=argparse.SUPPRESS)
    pgroup.add_argument('--stage2', dest='stage', default=argparse.SUPPRESS, action='store_const', const=2, help=argparse.SUPPRESS)
    pgroup.add_argument('--stage3', dest='stage', default=argparse.SUPPRESS, action='store_const', const=3, help=argparse.SUPPRESS)
    pgroup.add_bool_argument('--decrypt', default=True, help='create decrypted backup')
    pgroup.add_argument('--rip-languages', default=[], nargs=argparse.ONE_OR_MORE, type=isolang, help='list of audio/subtitle languages to rip')
    pgroup.add_argument('--makemkv-sp-remove-method', default='auto', choices=('auto', 'CellWalk', 'CellTrim'), help='MakeMKV DVD structure protection removal method')
    pgroup.add_argument('--makemkv-profile', default='default', type=str, help='MakeMKV profile name (e.g.: default, flac, wdtv, aac-st)')

    pgroup = app.parser.add_argument_group('Video Control')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_bool_argument('--crop', default=True, help='enable cropping video')
    xgroup.add_argument('--crop-wh', default=argparse.SUPPRESS, type=int, nargs=2, help='force cropping dimensions (centered)')
    xgroup.add_argument('--crop-whlt', default=argparse.SUPPRESS, type=int, nargs=4, help='force cropping dimensions')
    pgroup.add_bool_argument('--parallel-chapters', default=False, help='enable per-chapter parallel processing')
    pgroup.add_argument('--cropdetect-duration', type=AnyTimestamp, default=qip.utils.Timestamp(300), help='cropdetect duration (seconds)')
    pgroup.add_bool_argument('--cropdetect-skip-frame-nokey', default=False, help='skip non-key frames (faster but less accurate)', neg_help='do not skip non-key frames')
    pgroup.add_argument('--cropdetect-seek', type=AnyTimestamp, default=qip.utils.Timestamp(0), help='cropdetect seek / skip (seconds)')
    pgroup.add_argument('--cropdetect-limit', type=int, choices=range(0,256), default=24, help='cropdetect higher black value threshold / limit')
    pgroup.add_argument('--cropdetect-round', type=int, choices=range(0,1000), default=2, help='cropdetect width/height rouding factor')
    pgroup.add_argument('--video-language', '--vlang', type=isolang_or_None, default=isolang('und'), help='override video language (mux)')
    pgroup.add_argument('--video-rate-control-mode', default='CQ', choices=('Q', 'CQ', 'CBR', 'VBR', 'lossless'), help='rate control mode: Constant Quality (Q), Constrained Quality (CQ), Constant Bit Rate (CBR), Variable Bit Rate (VBR), lossless')
    pgroup.add_argument('--force-framerate', default=argparse.SUPPRESS, type=FrameRate, help='ignore heuristics and force framerate')
    pgroup.add_argument('--force-input-framerate', default=argparse.SUPPRESS, type=FrameRate, help='force input framerate')
    pgroup.add_argument('--force-output-framerate', default=argparse.SUPPRESS, type=FrameRate, help='force output framerate')
    pgroup.add_argument('--force-field-order', default=argparse.SUPPRESS, choices=('progressive', 'tt', 'tb', 'bb', 'bt', '23pulldown', 'auto-interlaced'), help='ignore heuristics and force input field order')
    pgroup.add_argument('--video-analyze-duration', type=AnyTimestamp, default=qip.utils.Timestamp(60), help='video analysis duration (seconds)')
    pgroup.add_argument('--video-analyze-skip-frames', type=int, default=10, help='number of frames to skip from video analysis')
    pgroup.add_argument('--limit-duration', type=AnyTimestamp, default=argparse.SUPPRESS, help='limit conversion duration (for testing purposes)')
    pgroup.add_bool_argument('--force-still-video', default=False, help='force still image video (single frame)')
    pgroup.add_argument('--seek-video', type=AnyTimestamp, default=qip.utils.Timestamp(0), help='seek some time past the start of the video')
    pgroup.add_bool_argument('--force-constant-framerate', '--force-cfr', default=False, help='force creating a constant framerate video')
    pgroup.add_argument('--pad-video', default=None, choices=('None', 'clone', 'black'), help='pad video stream')

    pgroup = app.parser.add_argument_group('Format context flags')
    pgroup.add_bool_argument('--autobsf', default=True, help='fflags: Automatically apply bitstream filters as required by the output format')
    pgroup.add_bool_argument('--genpts', default=True, help='fflags: generate pts')
    pgroup.add_bool_argument('--discardcorrupt', help='fflags: discard corrupted frames')
    pgroup.add_bool_argument('--igndts', help='fflags: ignore dts')
    pgroup.add_bool_argument('--sortdts', help='fflags: try to interleave outputted packets by dts')

    pgroup = app.parser.add_argument_group('Subtitle Control')
    pgroup.add_argument('--subrip-matrix', default=Auto, type=_resolved_Path, help='SubRip OCR matrix file')
    pgroup.add_bool_argument('--external-subtitles', choices=(True, False, '.sup', '.sub', '.srt', '.vtt', 'forced', 'non-forced'), nargs=argparse.ZERO_OR_MORE, help='enable exporting unoptimized subtitles as external files')
    pgroup.add_bool_argument('--ocr-subtitles', choices=(True, False, 'forced', 'non-forced'), nargs=argparse.ZERO_OR_MORE, help='enable optical character recognition of graphical subtitles')

    pgroup = app.parser.add_argument_group('Files')
    pgroup.add_argument('--output', '-o', dest='output_file', default=Auto, type=Path, help='specify the output (demuxed) file name')
    pgroup.add_bool_argument('--remux', help='remux original files')
    pgroup.add_bool_argument('--auto-verify', default=True, help='auto-verify created files')

    pgroup = app.parser.add_argument_group('Compatibility')
    pgroup.add_bool_argument('--webm', default=Auto, choices=(True, False, Auto), help='enable webm output format')
    pgroup.add_bool_argument('--ffv1', default=False, help='enable lossless ffv1 video codec')
    pgroup.add_argument('--media-library-app', '--app', default='plex', choices=['emby', 'plex'], help='app compatibility mode')
    pgroup.add_argument('--preferred-broadcast-format', type=BroadcastFormat_or_None, default=None, help='preferred broadcast format')

    pgroup = app.parser.add_argument_group('Encoding')
    pgroup.add_argument('--keyint', type=int, default=5, help='keyframe interval (seconds)')
    pgroup.add_bool_argument('--audio-track-titles', default=False, help='include titles for all audio tracks')
    pgroup.add_argument('--stereo-3d-mode', '--3d-mode', type=Stereo3DMode_or_None, default=Stereo3DMode.full_side_by_side, help='stereo 3D mode')

    pgroup = app.parser.add_argument_group('Tags')
    qip.mm.argparse_add_tags_arguments(pgroup, in_tags)

    pgroup = app.parser.add_argument_group('Options')
    pgroup.add_bool_argument('--beep', default=False, help='beep when done')
    pgroup.add_bool_argument('--eject', default=False, help='eject cdrom when done')
    pgroup.add_argument('--project', default=Auto, help='project name')
    pgroup.add_bool_argument('--chain', help='chain actions toward demux')
    pgroup.add_bool_argument('--cleanup', help='clean up when done')
    pgroup.add_bool_argument('--rename', default=True, help='enable renaming files (such as when tagging episode files)', neg_help='disable renaming files')
    pgroup.add_argument('--chop-chapters', dest='chop_chaps', nargs=argparse.ONE_OR_MORE, default=argparse.SUPPRESS, type=int, help='list of chapters to chop at')
    pgroup.add_bool_argument('--rip-menus', default=False, help='rip menus from device')
    pgroup.add_bool_argument('--rip-titles', default=True, help='rip titles from device')
    pgroup.add_argument('--rip-titles-list', type=int, nargs=argparse.ONE_OR_MORE, default=(), help='list of titles to rip (from lsdvd output)')

    pgroup = app.parser.add_argument_group('Music extraction')
    pgroup.add_argument('--skip-chapters', dest='num_skip_chapters', type=int, default=0, help='number of chapters to skip')
    pgroup.add_argument('--bitrate', type=int, default=argparse.SUPPRESS, help='force the encoding bitrate')  # TODO support <int>k
    pgroup.add_argument('--target-bitrate', type=int, default=argparse.SUPPRESS, help='specify the resampling target bitrate')
    pgroup.add_argument('--channels', type=int, default=argparse.SUPPRESS, help='force the number of audio channels')

    pgroup = app.parser.add_argument_group('Actions')
    pgroup.add_argument('--rip-iso', dest='rip_iso', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='ISO file to rip device to')
    pgroup.add_argument('--rip', dest='rip_dir', nargs=1, default=(), type=Path, help='directory to rip device to')
    pgroup.add_argument('--backup', dest='backup_dir', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='directory to backup device to')
    pgroup.add_argument('--hb', dest='hb_files', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='files to run through HandBrake')
    pgroup.add_argument('--mux', dest='mux_files', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='files to mux')
    pgroup.add_argument('--verify', dest='verify_files', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='files to verify')
    pgroup.add_argument('--update', dest='update_dirs', nargs=argparse.ONE_OR_MORE, default=(), type=_mux_dir_Path, help='directories to update mux parameters for')
    pgroup.add_argument('--combine', dest='combine_dirs', nargs=argparse.ONE_OR_MORE, default=(), type=_mux_dir_Path, help='directories to combine')
    pgroup.add_argument('--chop', dest='chop_dirs', nargs=argparse.ONE_OR_MORE, default=(), type=_mux_dir_Path, help='files/directories to chop into chapters')
    pgroup.add_argument('--extract-music', dest='extract_music_dirs', nargs=argparse.ONE_OR_MORE, default=(), type=_mux_dir_Path, help='directories to extract music from')
    pgroup.add_argument('--optimize', dest='optimize_dirs', nargs=argparse.ONE_OR_MORE, default=(), type=_mux_dir_Path, help='directories to optimize')
    pgroup.add_argument('--demux', dest='demux_dirs', nargs=argparse.ONE_OR_MORE, default=(), type=_mux_dir_Path, help='directories to demux')
    pgroup.add_argument('--concat', dest='concat_files', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='files to concat')
    pgroup.add_argument('--tag-episodes', dest='tag_episodes_files', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='files to tag based on tvshow episodes')
    pgroup.add_argument('--identify', dest='identify_files', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='identify files')
    pgroup.add_argument('--pick-title-streams', dest='pick_title_streams_dirs', nargs=argparse.ONE_OR_MORE, default=(), type=_mux_dir_Path, help='directories to pick title streams from')
    pgroup.add_argument('--status', '--print', dest='status_args', nargs=argparse.ONE_OR_MORE, default=(), type=Path, help='files or mux directories to print the status of')

    app.parse_args()

    app.args.external_subtitles = set(app.args.external_subtitles)
    if len({True, False, Auto} & app.args.external_subtitles) > 1:
        raise argparse.ArgumentError(argument=app.parser._option_string_actions['--external-subtitles'], message='''True, False and Auto are mutually exclusive''')

    app.args.ocr_subtitles = set(app.args.ocr_subtitles)

    if in_tags.type is None:
        try:
            in_tags.type = in_tags.deduce_type()
        except qip.mm.MissingMediaTagError:
            pass

    if app.args.step:
        app.args.jobs = 1

    if app.args.webm is Auto:
        if app.args.ffv1:
            app.args.webm = False

    if app.args.pad_video == 'None':
        app.args.pad_video = None

    # if getattr(app.args, 'action', None) is None:
    #     app.args.action = TODO

    if False and app.args.cuda:
        default_ffmpeg_args += [
            '-hwaccel', 'nvdec',
        ]

    global thread_executor
    global slurm_executor
    with contextlib.ExitStack() as exit_stack:
        thread_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=(1 if app.args.step
                         else (None if app.args.jobs is Auto
                               else app.args.jobs)))
        exit_stack.enter_context(thread_executor)
        if app.args.slurm and app.args.jobs == 1:
            slurm_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=(1 if app.args.step
                             else float('inf')))
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
        if getattr(app.args, 'combine_dirs', ()):
            action_combine(app.args.combine_dirs, in_tags=in_tags)
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
        if getattr(app.args, 'concat_files', ()):
            action_concat(app.args.concat_files, in_tags=in_tags)
            did_something = True
        if getattr(app.args, 'tag_episodes_files', ()):
            action_tag_episodes(app.args.tag_episodes_files, in_tags=in_tags)
            did_something = True
        if getattr(app.args, 'identify_files', ()):
            action_identify_files(app.args.identify_files, in_tags=in_tags)
            did_something = True
        for inputfile in getattr(app.args, 'status_args', ()):
            action_status(inputfile)
            did_something = True
        if not did_something:
            raise ValueError('Nothing to do!')
        if global_stats.num_batch_skips:
            raise Exception(f'BATCH MODE SKIP: {global_stats.num_batch_skips} task(s) skipped.')

def get_codec_encoding_delay(file, *, mediainfo_track_dict=None, ffprobe_stream_dict=None):
    if mediainfo_track_dict:
        if mediainfo_track_dict['Format'] == 'Opus':
            # default encoding delay of 312 samples
            return qip.utils.Timestamp(Fraction(1, int(mediainfo_track_dict['SamplingRate'])) * 312)
        return 0
    if ffprobe_stream_dict:
        if ffprobe_stream_dict['codec_name'] == 'opus':
            # default encoding delay of 312 samples
            return qip.utils.Timestamp(Fraction(1, int(ffprobe_stream_dict['sample_rate'])) * 312)
        return 0
    file_ext = my_splitext(file)[1]
    if file_ext in (
            '.y4m',
            '.yuv',
            '.m2p',
            '.mpeg2',
            '.mp2v',
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
            '.eac3',
            '.mp3',
            # TODO '.flac',
            '.dts',
            '.truehd',
            '.aac',
            '.wav',
            '.sub',
            '.sup',
            '.srt',
            '.ass',
            '.vtt',
    ):
        return 0
    if not isinstance(MediaFile, file):
        file = MediaFile.new_by_file_name(file)
    # Try again with mediainfo_track_dict
    try:
        mediainfo_track_dict, = [e
                                 for e in file.mediainfo_dict['media']['track']
                                 if e['@type'] != 'General']
    except ValueError:
        raise AssertionError('Expected a single mediainfo track: {!r}'.format(file.mediainfo_dict['media']['track']))
    return get_codec_encoding_delay(file, mediainfo_track_dict=mediainfo_track_dict)

still_image_exts = {
    '.png',
    '.jpg', '.jpeg',
}

iso_image_exts = {
    '.iso',
    '.img',
}

text_subtitle_exts = TextSubtitleFile.get_common_extensions()

# For now, all binary subtitle files are graphical
graphic_subtitle_exts = BinarySubtitleFile.get_common_extensions()

def codec_name_to_ext(codec_name):
    try:
        codec_ext = {
            # video
            'rawvideo': '.y4m',  # '.yuv'
            'mpeg2video': '.mp2v',
            'ffv1': '.ffv1.mkv',
            'msmpeg4v3': '.msmpeg4v3.avi',
            'mpeg4': '.mp4',
            'vc1': '.vc1.avi',
            'h264': '.h264',
            'hevc': '.h265',
            'h265': '.h265',
            'vp8': '.vp8.ivf',
            'vp9': '.vp9.ivf',
            # image
            'png': '.png',
            'mjpeg': '.jpg',
            # audio
            'ac3': '.ac3',
            'eac3': '.eac3',
            'mp2': '.mp2',
            'mp3': '.mp3',
            'dts': '.dts',
            'truehd': '.truehd',
            'vorbis': '.vorbis.ogg',
            'opus': '.opus.ogg',
            'flac': '.flac',
            'aac': '.aac',
            'pcm_s16le': '.wav',
            'pcm_s24le': '.wav',
            # subtitles
            'dvd_subtitle': '.sub',  # and .idx
            'hdmv_pgs_subtitle': '.sup',
            'subrip': '.srt',
            'ass': '.ass',
            'webvtt': '.vtt',
            'eia-608': '.srt',  # Closed Caption: because ccextractor supports srt
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
            '.yuv': 'rawvideo',
            '.mpeg2': 'mpeg2video',
            '.mp2v': 'mpeg2video',
            '.mpegts': 'mpegts',
            '.h264': 'h264',  # raw H.264 video
            '.h265': 'hevc',  # raw HEVC/H.265 video
            '.vp8': 'ivf',
            '.vp9': 'ivf',
            '.ivf': 'ivf',
            # audio
            #'.ac3': 'ac3',
            #'.eac3': 'eac3',
            #'.dts': 'dts',
            #'.truehd': 'truehd',
            '.vorbis': 'ogg',
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

def ext_to_codec(ext, lossless=False, hdr=None):
    ext = my_splitext('x' + ext, strip_container=True)[1]
    try:
        ext_container = {
            # video
            '.ffv1': 'ffv1',
            '.h264': ('h264_nvenc' if app.args.cuda and lossless and hdr is not True  # fast lossless
                      else ('libx264' if not lossless  # better quality
                            else NotImplementedError(f'No codec for {ext} (lossless={lossless}, hdr={hdr}, cuda={app.args.cuda})'))),
            '.h265': ('hevc_nvenc' if app.args.cuda and lossless and hdr is not True  # fast lossless
                      else ('libx265' if True  # better quality, lossless possible
                            else NotImplementedError(f'No codec for {ext} (lossless={lossless}, hdr={hdr}, cuda={app.args.cuda})'))),
            '.vp9': 'libvpx-vp9',
            '.y4m': 'yuv4',
            '.mpeg2': 'mpeg2video',
            '.mpegts': 'mpeg2video',
            '.vc1': 'vc1',
            # subtitle
            '.sub': 'dvd_subtitle',  # and .idx
            '.sup': 'hdmv_pgs_subtitle',
            '.srt': 'subrip',
            '.ass': 'ass',
            '.vtt': 'webvtt',
        }[ext]
    except KeyError as err:
        raise ValueError('Unsupported extension %r' % (ext,)) from err
    if isinstance(ext_container, Exception):
        raise ext_container
    return ext_container

def ext_to_codec_args(ext, codec, lossless=False):
    codec_args = ffmpeg.Options()

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

    if codec in (
            'libx265',
    ):
        if lossless:
            codec_args.append_colon_option('-x265-params', 'lossless=1')
            codec_args.set_option('-preset', 'faster')  # lossless is used for temp files, prefer speed over size
    if codec in (
            'h264_nvenc', 'libx264',
            'hevc_nvenc',
    ):
        if lossless:
            codec_args += [
                '-preset', 'lossless',
            ]

    if ext in (
            '.h265',
    ):
        codec_args += [
            '-tag:v', 'hvc1',  # QuickTime compatibility
        ]

    return codec_args

class ColorSpaceParams(collections.namedtuple(
        'ColorSpaceParams',
        (
            'xR', 'yR', 'xG', 'yG', 'xB', 'yB',  # Primary colors
            'xW', 'yW',                          # White point
            'K',                                 # CCT
        ),
)):
    __slots__ = ()

    # Unit of 0.00002

    @property
    def uxW(self):
        return int(self.xW / 0.00002)

    @property
    def uyW(self):
        return int(self.yW / 0.00002)

    @property
    def uxR(self):
        return int(self.xR / 0.00002)

    @property
    def uyR(self):
        return int(self.yR / 0.00002)

    @property
    def uxG(self):
        return int(self.xG / 0.00002)

    @property
    def uyG(self):
        return int(self.yG / 0.00002)

    @property
    def uxB(self):
        return int(self.xB / 0.00002)

    @property
    def uyB(self):
        return int(self.yB / 0.00002)

    def master_display_str(self):
        return f'G({self.uxG},{self.uyG})B({self.uxB},{self.uyB})R({self.uxR},{self.uyR})WP({self.uxW},{self.uyW})'

    @classmethod
    def from_mediainfo_track_dict(cls, mediainfo_track_dict):
        color_primaries = mediainfo_track_dict.get('MasteringDisplay_ColorPrimaries', None)
        if color_primaries is not None:
            try:
                # Display P3
                color_primaries = color_space_params[color_primaries]
            except KeyError:
                # R: x=0.680000 y=0.320000, G: x=0.265000 y=0.690000, B: x=0.150000 y=0.060000, White point: x=0.312700 y=0.329000
                m = re.match(r'^R: x=(?P<xR>\d+\.\d+) y=(?P<yR>\d+\.\d+), G: x=(?P<xG>\d+\.\d+) y=(?P<yG>\d+\.\d+), B: x=(?P<xB>\d+\.\d+) y=(?P<yB>\d+\.\d+), White point: x=(?P<xW>\d+\.\d+) y=(?P<yW>\d+\.\d+)$', color_primaries)
                if m:
                    color_primaries = cls(
                        xR=float(m.group('xR')),
                        yR=float(m.group('yR')),
                        xG=float(m.group('xG')),
                        yG=float(m.group('yG')),
                        xB=float(m.group('xB')),
                        yB=float(m.group('yB')),
                        xW=float(m.group('xW')),
                        yW=float(m.group('yW')),
                        K=None)
                else:
                    raise ValueError(f'Unrecognized mediainfo MasteringDisplay_ColorPrimaries: {color_primaries!r}')
        return color_primaries

class LuminanceParams(collections.namedtuple(
        'LuminanceParams',
        (
            'min', 'max',
        ),
)):
    __slots__ = ()

    # Unit of 0.0001 cd/m2

    @property
    def umin(self):
        return int(self.min / 0.0001)

    @property
    def umax(self):
        return int(self.max / 0.0001)

    def master_display_str(self):
        return f'L({self.umin},{self.umax})'

    @classmethod
    def from_mediainfo_track_dict(cls, mediainfo_track_dict):
        luminance = mediainfo_track_dict.get('MasteringDisplay_Luminance', None)
        if luminance is not None:
            # min: 0.0200 cd/m2, max: 1200.0000 cd/m2
            m = re.match(r'^min: (?P<min>\d+(?:\.\d+)?) cd/m2, max: (?P<max>\d+(?:\.\d+)?) cd/m2$', luminance)
            if m:
                luminance = cls(min=float(m.group('min')), max=float(m.group('max')))
            else:
                raise ValueError(f'Unrecognized mediainfo MasteringDisplay_Luminance: {luminance!r}')
        return luminance

def parse_master_display_str(master_display):
    m = re.match(r'^G\((?P<uxG>\d+),(?P<uyG>\d+)\)B\((?P<uxB>\d+),(?P<uyB>\d+)\)R\((?P<uxR>\d+),(?P<uyR>\d+)\)WP\((?P<uxW>\d+),(?P<uyW>\d+)\)L\((?P<uminL>\d+),(?P<umaxL>\d+)\)$', master_display)
    if m:
        return types.SimpleNamespace(
            uxG=int(m.group('uxG')),
            uyG=int(m.group('uyG')),
            uxB=int(m.group('uxB')),
            uyB=int(m.group('uyB')),
            uxR=int(m.group('uxR')),
            uyR=int(m.group('uyR')),
            uxW=int(m.group('uxW')),
            uyW=int(m.group('uyW')),
            uminL=int(m.group('uminL')),
            umaxL=int(m.group('umaxL')),
        )
    raise ValueError(f'Invalid master_display: {master_display!r}')

color_space_params = {
    # https://en.wikipedia.org/wiki/DCI-P3
    'P3-D65 (Display)':     ColorSpaceParams(0.680, 0.320, 0.265, 0.690, 0.150, 0.060, 0.3127, 0.3290, 6504),
    'P3-DCI (Theater)':     ColorSpaceParams(0.680, 0.320, 0.265, 0.690, 0.150, 0.060, 0.314, 0.351, 6300),
    'P3-D60 (ACES Cinema)': ColorSpaceParams(0.680, 0.320, 0.265, 0.690, 0.150, 0.060, 0.32168, 0.33767, 6000),
    'BT.2020':              ColorSpaceParams(0.708, 0.292, 0.170, 0.797, 0.131, 0.046, 0.3127, 0.3290, None),  # TODO Verify -- Rec. ITU-R BT.2020-2
}
color_space_params['Display P3'] = color_space_params['P3-D65 (Display)']
color_space_params['DCI-P3'] = color_space_params['P3-DCI (Theater)']

hdr_color_transfer_stems = {
    # Perceptual Quantizers (PQ)
    'smpte2084',  # HDR10 & DolbyVision
    'smpte2094',  # HDR10+
}
# 'smpte2085',  # ??
# 'smpte2086',  # Metadata format, used in HDR10 & DolbyVision

def sorted_ffprobe_streams(streams):
    def ffprobe_stream_key(ffprobe_stream_dict):
        return (
            CodecType(ffprobe_stream_dict['codec_type']),
            int(ffprobe_stream_dict.get('index', 0)),
        )
    return sorted(streams, key=ffprobe_stream_key)

def sorted_mediainfo_tracks(tracks):
    def mediainto_track_key(mediainto_track_dict):
        return (
            CodecType(mediainto_track_dict['@type']),
            int(mediainto_track_dict.get('ID', 0)),
        )
    return sorted(tracks, key=mediainto_track_key)

def get_hdr_codec_args(*, inputfile, codec, ffprobe_stream_json=None, mediainfo_track_dict=None):
    ffmpeg_hdr_args = ffmpeg.Options()
    assert codec
    if ffprobe_stream_json is None:
        ffprobe_stream_json, = sorted_ffprobe_streams(inputfile.ffprobe_dict['streams'])
    if mediainfo_track_dict is None:
        try:
            mediainfo_track_dict, = [e
                                     for e in inputfile.mediainfo_dict['media']['track']
                                     if e['@type'] != 'General']
        except ValueError:
            raise AssertionError('Expected a single mediainfo track: {!r}'.format(inputfile.mediainfo_dict['media']['track']))
    # NOTE: mediainfo does not distinguish between SMPTE ST 2087 and SMPTE ST 2084; It always displays 'SMPTE ST 2086'.
    color_transfer = ffprobe_stream_json.get('color_transfer', '')
    if any(v in color_transfer
           for v in hdr_color_transfer_stems):
        # HDR-10, HDR-10+ and Dolby Vision should all have some flavour of smpte2084, smpte2086, smpte2094

        if codec in (
                'libvpx-vp9',
        ):
            # https://developers.google.com/media/vp9/hdr-encoding
            need_2pass = True
            assert mediainfo_track_dict['BitDepth'] == 10 # avc @ profile High, hevc @ profile Main 10, ??
            assert ffprobe_stream_json['pix_fmt'] == 'yuv420p10le'
            ffmpeg_hdr_args.set_option('-pix_fmt', 'yuv420p10le')
            ffmpeg_hdr_args.set_option('-color_primaries', ffmpeg.get_option_value('color_primaries', ffprobe_stream_json['color_primaries']))
            ffmpeg_hdr_args.set_option('-color_trc', ffmpeg.get_option_value('color_trc', ffprobe_stream_json['color_transfer']))
            ffmpeg_hdr_args.set_option('-colorspace', ffmpeg.get_option_value('colorspace', ffprobe_stream_json['color_space']))
            ffmpeg_hdr_args.set_option('-color_range', ffmpeg.get_option_value('color_range', ffprobe_stream_json['color_range']))
            # https://www.webmproject.org/vp9/profiles/
            if 'yuv420' in ffprobe_stream_json['pix_fmt']:
                ffmpeg_hdr_args.set_option('-profile:v', 2)  # 10 or 12 bit, 4:2:0
            elif 'yuv422' in ffprobe_stream_json['pix_fmt']:
                ffmpeg_hdr_args.set_option('-profile:v', 3)  # 10 or 12 bit, 4:2:2 or 4:4:4
            else:
                raise NotImplementedError('VP9 HDR {color_range} profile for {pix_fmt}'.format_map(ffprobe_stream_json))

        elif codec in (
                'libx265',
        ):
            # https://x265.readthedocs.io
            assert mediainfo_track_dict['BitDepth'] == 10
            assert ffprobe_stream_json['pix_fmt'] == 'yuv420p10le'
            ffmpeg_hdr_args.set_option('-pix_fmt', 'yuv420p10le')
            ffmpeg_hdr_args.append_colon_option('-x265-params', 'hdr-opt=1')
            ffmpeg_hdr_args.append_colon_option('-x265-params', 'colorprim={}'.format(ffmpeg.get_option_value('color_primaries', ffprobe_stream_json['color_primaries'])))
            ffmpeg_hdr_args.append_colon_option('-x265-params', 'transfer={}'.format(ffmpeg.get_option_value('color_trc', ffprobe_stream_json['color_transfer'])))
            ffmpeg_hdr_args.append_colon_option('-x265-params', 'colormatrix={}'.format(ffmpeg.get_option_value('colorspace', ffprobe_stream_json['color_space'])))
            color_primaries = ColorSpaceParams.from_mediainfo_track_dict(mediainfo_track_dict=mediainfo_track_dict)
            master_display = ''
            master_display += color_primaries.master_display_str()
            luminance = LuminanceParams.from_mediainfo_track_dict(mediainfo_track_dict=mediainfo_track_dict)
            master_display += luminance.master_display_str()
            ffmpeg_hdr_args.append_colon_option('-x265-params', 'master-display={}'.format(master_display))
            # https://x265.readthedocs.io/en/master/cli.html?highlight=--profile#profile-level-tier
            if 'yuv420' in ffprobe_stream_json['pix_fmt']:
                ffmpeg_hdr_args.set_option('-profile:v', 'main10')
            elif 'yuv422' in ffprobe_stream_json['pix_fmt']:
                ffmpeg_hdr_args.set_option('-profile:v', 'main422-10')
            else:
                raise NotImplementedError('libx265 HDR {color_range} profile for {pix_fmt}'.format_map(ffprobe_stream_json))

        else:
            raise NotImplementedError(f'HDR support not implemented (HDR {color_transfer} using {codec})')
    else:
        pass  # Not SMPTE color transfer; Assume not HDR
    return ffmpeg_hdr_args

def codec_to_input_args(codec):
    codec_args = []
    if codec in (
            'h264_nvenc',
            'hevc_nvenc',
    ):
        codec_args += [
            '-hwaccel', 'nvdec',
        ]
    return codec_args

def pick_lossless_codec_ext(stream):
    stream_file_base, stream_file_ext = my_splitext(stream.file_name)
    # copy
    try:
        return {
            '.mpeg2': '.mpegts',
            '.mpeg2.mp2v': '.mpegts',
        }[stream_file_ext]
    except KeyError:
        pass
    # encode -- GPU
    if app.args.cuda:
        try:
            mediainfo_track_dict, = [e
                                     for e in stream.file.mediainfo_dict['media']['track']
                                     if e['@type'] != 'General']
        except ValueError:
            raise AssertionError('Expected a single mediainfo track: {!r}'.format(stream.file.mediainfo_dict['media']['track']))
        if True:
            return '.h265'  # Fast lossless (4K @ 50fps)
        if mediainfo_track_dict['BitDepth'] <= 8:
            return '.h264'  # Fast lossless (4K @ 20fps)
    # encode -- CPU
    return '.ffv1.mkv'  # Slow lossless

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
    start_time = AnyTimestamp(start_time)
    if start_time < 0 and start_time == (
            stream_time_base * round_half_away_from_zero(-codec_encoding_delay / stream_time_base)
    ):
        start_time = qip.utils.Timestamp(0)
    else:
        start_time += codec_encoding_delay
    return start_time

def estimate_stream_duration(inputfile=None, ffprobe_json=None):
    ffprobe_json = ffprobe_json or inputfile.ffprobe_dict
    try:
        ffprobe_format_json = ffprobe_json['format']
    except KeyError:
        pass
    else:

        try:
            estimated_duration = ffprobe_format_json['duration']
        except KeyError:
            pass
        else:
            estimated_duration = ffmpeg.Timestamp(estimated_duration)
            if estimated_duration >= 4294967295 / 120:
                # video stream duration_ts = 4294967295 (-1), assuming worst case 120fps
                pass
            elif estimated_duration >= 0.0:
                return estimated_duration

    try:
        ffprobe_stream_json, = ffprobe_json['streams']
    except ValueError:
        pass
    else:

        if ffprobe_stream_json.get('duration_ts', None) != '4294967295':
            try:
                estimated_duration = ffprobe_stream_json['duration']
            except KeyError:
                pass
            else:
                estimated_duration = AnyTimestamp(estimated_duration)
                if estimated_duration >= 4294967295 / 120:
                    # video stream duration_ts = 4294967295 (-1), assuming worst case 120fps
                    pass
                elif estimated_duration >= 0.0:
                    return estimated_duration

        try:
            estimated_duration = ffprobe_stream_json['tags']['NUMBER_OF_FRAMES']
        except KeyError:
            pass
        else:
            estimated_duration = int(estimated_duration)
            if estimated_duration > 0:
                return estimated_duration

        try:
            estimated_duration = ffprobe_stream_json['tags']['NUMBER_OF_FRAMES-eng']
        except KeyError:
            pass
        else:
            estimated_duration = int(estimated_duration)
            if estimated_duration > 0:
                return estimated_duration

    if inputfile is not None:

        try:
            estimated_duration = inputfile.duration
        except AttributeError:
            pass
        else:
            if estimated_duration is not None:
                estimated_duration = AnyTimestamp(estimated_duration)
                if estimated_duration >= 0.0:
                    return estimated_duration

    return None

def init_inputfile_tags(inputfile, in_tags, ffprobe_dict=None):

    inputfile_base, inputfile_ext = my_splitext(inputfile)
    try:
        loaded_tags = inputfile.load_tags()
    except NotImplementedError as e:
        app.log.warning(e)
    else:
        inputfile.tags.update(loaded_tags)
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
        re.match(r'^(?P<name>.+)\.(?P<language>[a-z]{2,3})$', name_scan_str)
    )
    if m:
        d = m.groupdict()
        d = {k: v and v.strip() for k, v in d.items()}
        try:
            inputfile.tags.language = d['language']
        except TypeError:
            pass
        else:
            name_scan_str = d['name']
    m = not done and (
        # TVSHOW S01E02 TITLE
        # TVSHOW S01E02-03 TITLE
        # TVSHOW S01E02
        # TVSHOW S01E02-03
        re.match(r'^(?P<tvshow>.+) S(?P<season>\d+)E(?P<str_episodes>\d+(?:-?E\d+)*)(?: (?P<title>.+))?$', name_scan_str)
        # TVSHOW SPECIAL 0x1 TITLE
        or re.match(r'^(?P<tvshow>.+) (?:-- )?(?i:SPECIAL) (?P<season>0)x(?P<str_episodes>\d+(?:-?\d+)*)(?: (?P<title>.+))?$', name_scan_str)
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
            m = re.match('^(?P<title>.+?) *- *part *(?P<part>\d+)$', d['title'])
            if m:
                d.update(m.groupdict())
        if 'title' in d:
            # TITLE (1987)
            m = re.match(r'^(?P<title>.+) \((?P<date>\d{4})\)$', d['title'])
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
        try:
            loaded_tags = inputfile.load_tags()
        except NotImplementedError as e:
            app.log.warning(e)
        else:
            inputfile.tags.update(inputfile.load_tags())
        if inputfile_ext in (
                '.mkv',
                '.webm',
                ):
            mediainfo_video_track_dicts = [mediainfo_track_dict
                                           for mediainfo_track_dict in inputfile.mediainfo_dict['media']['track']
                                           if mediainfo_track_dict['@type'] == 'Video']
            if len(mediainfo_video_track_dicts) > 1:
                # TODO support angles!
                mediainfo_video_track_dicts = mediainfo_video_track_dicts[:1]
            try:
                mediainfo_track_dict, = mediainfo_video_track_dicts
            except ValueError:
                e = 'Expected a single mediainfo Video track: {!r}'.format(inputfile.mediainfo_dict['media']['track'])
                if app.args.force:
                    app.log.warning(e)
                    mediainfo_track_dict = {
                        '@type': 'Video',
                    }
                else:
                    raise ValueError(f'{e} (try --force)')
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

    if rip_iso.suffix not in iso_image_exts:
        raise ValueError(f'File is not a {"|".join(sorted(iso_image_exts))}: {rip_iso}')

    iso_file = BinaryFile(rip_iso)
    map_file = ddrescue.MapFile(rip_iso.with_suffix('.map'))
    if not map_file.exists():
        # Backward compatibility check
        log_file = ddrescue.MapFile(rip_iso.with_suffix('.log'))
        assert not log_file.exists(), f'{log_file} exists! Please rename to {map_file}.'

    if app.args.check_cdrom_ready:
        if not cdrom_ready(device, timeout=app.args.cdrom_ready_timeout, progress_bar=True):
            raise Exception('CDROM not ready')

    app.log.info('Identifying mounted media type...')
    out = dbg_exec_cmd(['dvd+rw-mediainfo', app.args.device], dry_run=False)
    out = clean_cmd_output(out)
    m = re.search(r'Mounted Media: .*(BD|DVD)', out)
    if not m:
        raise ValueError('Unable to identify mounted media type')
    media_type = MediaType(m.group(1))

    decrypt = app.args.decrypt

    if media_type is MediaType.DVD:
        app.log.info('Decrypting DVD... (please ignore error messages from mplayer)')
        cmd = [
            'mplayer',
            f'dvd://1/{device.resolve()}',
            '-endpos', 1,
            '-vo', 'null',
            '-ao', 'null',
        ]
        dbg_exec_cmd(cmd)

    if media_type is MediaType.BD:
        discatt_dat_file = BinaryFile(iso_file.file_name.with_suffix('.discatt.dat'))

        # TODO dry_run?
        if decrypt:
            if discatt_dat_file.exists():
                app.log.info('Decryption key already exists: %s', discatt_dat_file)
            else:
                with perfcontext(f'Extracting decryption keys from {device}: {discatt_dat_file}', log=True):

                    from qip.makemkv import makemkvcon

                    try:
                        drive_info = makemkvcon.device_to_drive_info(device)
                    except ValueError:
                        if not app.args.dry_run:
                            raise
                        drive_info = types.SimpleNamespace(index=0)
                    source = f'disc:{drive_info.index}'

                    with tempfile.TemporaryDirectory(prefix=f'mmdemux-{iso_file.file_name.stem}', suffix='temp-backup') as temp_backup_dir:
                        temp_backup_dir = Path(temp_backup_dir)
                        temp_discattd_dat_file = temp_backup_dir / 'MAKEMKV/discattd.dat'  # Not a typo!
                        try:
                            makemkvcon.backup(
                                source=source,
                                dest_dir=temp_backup_dir,
                                decrypt=True,
                                #retry_no_cd=False,
                                noscan=True,
                                robot=True,
                                stop_before_copying_files=True,
                            )
                        except SpawnedProcessError:
                            if not temp_discattd_dat_file.exists():
                                raise
                        shutil.copyfile(src=temp_discattd_dat_file, dst=discatt_dat_file)

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
            iso_file, map_file,
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
            iso_file, map_file,
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
            iso_file, map_file,
        ]
    else:
        raise NotImplementedError(f'Unsupported ripping stage {stage}')

    with perfcontext(f'Extracting {iso_file}... (stage {stage})', log=True):
        ddrescue(*ddrescue_args)

    map_file.load()
    map_file.compact_sblocks()
    if map_file.is_finished():
        if app.args.eject and device.is_block_device():
            app.log.info('Ejecting...')
            cmd = [
                shutil.which('eject'),
                device,
            ]
            out = do_spawn_cmd(cmd)

def action_rip(rip_dir, device, in_tags):
    app.log.info('Ripping %s from %s...', rip_dir, device)

    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', list2cmdline(['mkdir', rip_dir]))
    else:
        os.mkdir(rip_dir)

    try:

        if not app.args.rip_menus and not app.args.rip_titles:
            raise ValueError('Nothing to do; Please enable --rip-menus or --rip-titles.')

        if app.args.rip_titles and not app.args.rip_languages:
            raise ValueError('No rip languages specified; Please provide --rip-languages. Example: --rip-languages eng fra und')

        if app.args.rip_menus:
            import qip.libdvdread as libdvdread

            app.log.info('Ripping menus...')

            dvd_reader = libdvdread.dvd_reader(device)
            ifo_zero = dvd_reader.open_ifo(0)

            ifos = [ifo_zero] + list(itertools.repeat(None, ifo_zero.vts_atrt.nr_of_vtss))

            for i in range(1, ifo_zero.vts_atrt.nr_of_vtss + 1):
                ifos[i] = dvd_ifo = dvd_reader.open_ifo(i)

            for ivts, ifo in enumerate(ifos):
                app.log.debug('ivts=%d, ifo.pgci_ut.nr_of_lus=%d', ivts, ifo.pgci_ut.nr_of_lus)
                vob_file = dvd_reader.OpenFile(
                    ivts,
                    libdvdread.DVD_READ_MENU_VOBS)
                for ilu in range(ifo.pgci_ut.nr_of_lus):
                    lu = ifo.pgci_ut.get_lu(ilu)
                    app.log.debug('  ilu=%d, lu: %r', ilu, dict_from_swig_obj(lu))
                    app.log.debug('    lu.pgcit: %r', dict_from_swig_obj(lu.pgcit))
                    for isrp in range(lu.pgcit.nr_of_pgci_srp):
                        pgci_srp = lu.pgcit.get_pgci_srp(isrp)
                        app.log.debug('    isrp=%d, pgci_srp: %r', isrp, dict_from_swig_obj(pgci_srp))
                        app.log.debug('    pgci_srp.pgc: %r', dict_from_swig_obj(pgci_srp.pgc))
                        with MediaFile.new_by_file_name(
                            rip_dir / 'ifo{ifo:02d}-lu{lu:02d}-srp{srp:02d}.m2p'.format(
                                ifo=ivts,
                                lu=ilu,
                                srp=isrp,
                            )) as movie_file:
                            cell_playback_time = qip.utils.Timestamp(0)
                            total_sector_count = 0
                            for l in range(pgci_srp.pgc.nr_of_cells):
                                cell_playback = pgci_srp.pgc.get_cell_playback(l)
                                cell_playback_time += libdvdread.dvd_time_to_Timestamp(cell_playback.playback_time)
                                app.log.debug('      l=%d, cell_playback: %r', l, dict_from_swig_obj(cell_playback))
                                sector_count = cell_playback.last_sector - cell_playback.first_sector + 1
                                total_sector_count += sector_count
                                if sector_count:
                                    if not app.args.dry_run:
                                        if movie_file.closed:
                                            movie_file.fp = movie_file.open('wb')
                                    blocks = vob_file.ReadBlocks(cell_playback.first_sector,
                                                                 sector_count)
                                    if not app.args.dry_run:
                                        movie_file.write(blocks)
                            app.log.info('  VTS %d, LU %d, SRP %d, %d cells, %d sectors, playback time %s',
                                         ivts, ilu, isrp, pgci_srp.pgc.nr_of_cells, total_sector_count, cell_playback_time)

        if app.args.rip_titles:

            minlength = app.args.minlength
            if minlength is Auto:
                if in_tags.type == 'tvshow':
                    minlength = default_minlength_tvshow
                else:
                    minlength = default_minlength_movie

            rip_titles_done = False

            if not rip_titles_done \
                    and app.args.rip_tool in ('makemkv', Auto) \
                    and not app.args.rip_titles_list:
                from qip.makemkv import makemkvcon

                # See ~/.MakeMKV/settings.conf
                profile_xml = makemkvcon.get_profile_xml(f'{app.args.makemkv_profile}.mmcp.xml')
                eMkvSettings = profile_xml.find('mkvSettings')
                eMkvSettings.set('ignoreForcedSubtitlesFlag', 'false')
                eProfileSettings = profile_xml.find('profileSettings')
                makemkv_languages_s = []
                for lang in app.args.rip_languages:
                    if lang.name == 'und':
                        makemkv_languages_s.append('nolang')
                    else:
                        makemkv_languages_s.append(lang.synonim_iso639_2)
                        makemkv_languages_s.append(lang.code3)
                makemkv_languages_s = [lang for lang in makemkv_languages_s if lang]
                eProfileSettings.set('app_PreferredLanguage', makemkv_languages_s[0])
                eProfileSettings.set('app_DefaultSelectionString',
                                     '+sel:all,-sel:(audio|subtitle),+sel:({rip_languages}),-sel:core,=100:all,-10:favlang'.format(
                                         rip_languages='|'.join(makemkv_languages_s),
                                     ))

                settings_changed = False
                makemkvcon_settings = makemkvcon.read_settings_conf()
                orig_makemkvcon_settings = makemkvcon.read_settings_conf()

                dvd_SPRemoveMethod = {
                    'auto': (None, '0'),
                    'CellWalk': ('1',),
                    'CellTrim': ('2',),
                }[app.args.makemkv_sp_remove_method]
                if makemkvcon_settings.get('dvd_SPRemoveMethod', None) not in dvd_SPRemoveMethod:
                    if dvd_SPRemoveMethod[0] is None:
                        del makemkvcon_settings['dvd_SPRemoveMethod']
                    else:
                        makemkvcon_settings['dvd_SPRemoveMethod'] = dvd_SPRemoveMethod[0]
                    settings_changed = True

                if device.is_block_device():
                    if app.args.check_cdrom_ready:
                        if not cdrom_ready(device, timeout=app.args.cdrom_ready_timeout, progress_bar=True):
                            raise Exception('CDROM not ready')
                    source = f'dev:{device.resolve()}'  # makemkv is picky
                elif device.is_dir():
                    source = f'file:{os.fspath(device)}'
                elif device.suffix in iso_image_exts:
                    source = f'iso:{os.fspath(device)}'
                    discatt_dat_file = device.with_suffix('.discatt.dat')
                    if discatt_dat_file.exists():
                        app.log.warning('%s exists. Perhaps you meant to create a decrypted backup using --backup and then --rip the backup?', discatt_dat_file)
                else:
                    raise ValueError(f'File is not a device or {"|".join(sorted(iso_image_exts))}: {device}')

                if not app.args.dry_run and settings_changed:
                    app.log.warning('Changing makemkv settings!')
                    makemkvcon.write_settings_conf(makemkvcon_settings)
                try:

                    with XmlFile.NamedTemporaryFile(suffix='.profile.xml') as tmp_profile_xml_file:
                        tmp_profile_xml_file.write_xml(profile_xml)
                        # write -> read
                        tmp_profile_xml_file.flush()
                        tmp_profile_xml_file.seek(0)

                        with perfcontext('Ripping w/ makemkvcon', log=True):
                            rip_info = makemkvcon.mkv(
                                source=source,
                                dest_dir=rip_dir,
                                minlength=int(minlength),
                                profile=tmp_profile_xml_file,
                                #retry_no_cd=device.is_block_device(),
                                noscan=True,
                                robot=True,
                            )

                finally:
                    if not app.args.dry_run and settings_changed:
                        app.log.warning('Restoring makemkv settings!')
                        makemkvcon.write_settings_conf(orig_makemkvcon_settings)

                # TODO
                if not app.args.dry_run:
                    for title_no, angle_no in rip_info.spawn.angles:
                        pass
                    app.log.debug('rip_info.spawn.angles=%r', rip_info.spawn.angles)

                rip_titles_done = True

            if not rip_titles_done and app.args.rip_tool in ('mplayer', Auto):
                from qip.mplayer import mplayer
                from qip.bin.lsdvd import lsdvd

                dvd_info = lsdvd(device=app.args.device,
                                 show_chapters=True)
                rip_titles = filter(None, dvd_info.titles)
                rip_titles = list(rip_titles) ; app.log.debug('1:rip_titles=%r', rip_titles)
                if app.args.rip_titles_list and isinstance(app.args.rip_titles_list, collections.abc.Sequence):
                    app.log.debug('4:rip_titles_list=%r', app.args.rip_titles_list)
                    def _filter(dvd_title):
                        if dvd_title.title_no in app.args.rip_titles_list:
                            return True
                        else:
                            app.log.verbose('Dropping Title: %d, Length: %s, Not in --rip-titles-list.', dvd_title.title_no, dvd_title.general.playback_time)
                            return False
                    rip_titles = filter(_filter, rip_titles)
                else:
                    if minlength:
                        def _filter(dvd_title):
                            if dvd_title.general.playback_time >= minlength:
                                return True
                            else:
                                app.log.info('Dropping Title: %d, Length: %s, Too short.', dvd_title.title_no, dvd_title.general.playback_time)
                                return False
                        rip_titles = filter(_filter, rip_titles)
                    rip_titles = list(rip_titles) ; app.log.debug('2:rip_titles=%r', rip_titles)
                rip_titles = list(rip_titles)
                app.log.debug('4:rip_titles=%r', rip_titles)
                app.log.debug('4:rip_titles no=%r', [dvd_title.title_no for dvd_title in rip_titles])
                rip_titles = list(rip_titles) ; app.log.debug('5:rip_titles=%r', rip_titles)

                if not rip_titles:
                    raise ValueError('Rip titles list empty!')

                if device.is_block_device():
                    pass
                else:
                    if not re.match('^[A-Za-z0-9_.]+$', device.name):
                        app.log.warning('If mplayer doesn\'t like the device name, try using only letters, number underscores `_`, and dots `.`')
                for dvd_title in rip_titles:
                    output_file = VobFile(rip_dir / 'title_t{:02d}.vob'.format(dvd_title.title_no))
                    with perfcontext(f'Ripping title #{dvd_title.title_no} w/ mplayer: {output_file}', log=True):
                        mplayer_args = []
                        mplayer_args += [
                            f'dvd://{dvd_title.title_no}/{device}',
                            '-dumpstream',
                            '-dumpfile', output_file,
                        ]
                        mplayer(*mplayer_args)
                        if not output_file.exists():
                            raise Exception(f'Output file does not exist: {output_file}')

                    if dvd_title.chapters:
                        chapters_xml_file = MatroskaChaptersFile(rip_dir / 'title_t{:02d}.chapters.xml'.format(dvd_title.title_no))
                        with perfcontext(f'Extracting chapters from title #{dvd_title.title_no}: {chapters_xml_file}', log=True):
                            chaps = Chapters()
                            for chap_idx, dvd_chapter in enumerate(dvd_title.chapters):
                                start = chaps[chap_idx - 1].end if chap_idx else qip.utils.Timestamp(0)
                                chap = Chapter(
                                    start=start,
                                    end=start + dvd_chapter.playback_time,
                                    title='Chapter {:02d}'.format(chap_idx + 1),  # Same format as MakeMKV
                                )
                                chaps.append(chap)
                            chapters_xml_file.chapters = chaps
                            chapters_xml_file.create()
                    else:
                        app.log.info('No chapters for title #{dvd_title.title_no}')

                rip_titles_done = True

            if not rip_titles_done:
                raise NotImplementedError('unsupported rip tool: %r' % (app.args.mplayer,))

    except:
        if app.args.dry_run:
            app.log.verbose('CMD (dry-run): %s', list2cmdline(['rmdir', rip_dir]))
        else:
            try:
                os.rmdir(rip_dir)
            except OSError:
                pass
            else:
                app.log.info('Ripping failed; Removed %s/.', rip_dir)
        raise

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
                entry_path = rip_dir / entry.name
                assert entry_path.suffix in ('.mkv', '.webm', '.m2p')
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
            title=f'Pick a title for offset {time_offset}',
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
            while True:
                c = app.prompt(completer=completer, prompt_mode='pick')
                if c.strip():
                    break
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
                time_offset += ffmpeg.Timestamp(stream_file.ffprobe_dict['format']['duration'])
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
        raise OSError(errno.EEXIST, f'Directory exists: {backup_dir}')

    from qip.makemkv import makemkvcon
    decrypt = app.args.decrypt
    discatt_dat_file = None

    try:

        if device.is_block_device():

            if app.args.check_cdrom_ready:
                if not cdrom_ready(device, timeout=app.args.cdrom_ready_timeout, progress_bar=True):
                    raise Exception('CDROM not ready')
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
                #retry_no_cd=False,
                noscan=True,
                robot=True,
            )

        else:

            if device.suffix not in iso_image_exts:
                raise ValueError(f'File is not a device {"|".join(sorted(iso_image_exts))}: {device}')

            discatt_dat_file = device.with_suffix('.discatt.dat')
            if discatt_dat_file.exists():
                app.log.info('%s file found.', discatt_dat_file)
                # decrypt = True
            else:
                app.log.warning('%s file not found.', discatt_dat_file)
                discatt_dat_file = None
                # decrypt = False

            app.log.info('Copying %s.', device)
            from qip.libudfread import udf_reader
            with udf_reader(device) as udf:
                def cp_dir(dsrc):
                    path_dst = Path(os.fspath(backup_dir) + '/' + os.fspath(dsrc.path))
                    if not app.args.dry_run:
                        path_dst.mkdir(exist_ok=True)
                    for dirent in dsrc.readdir():
                        if dirent.name in ('.', '..'):
                            continue
                        if dirent.is_dir():
                            with dsrc.opendir_at(dirent.name) as child_d:
                                cp_dir(child_d)
                        else:
                            with dsrc.open_at(dirent.name) as fsrc:
                                if not app.args.dry_run:
                                    with open(path_dst / dirent.name, 'wb') as fdst:
                                        qip.utils.progress_copyfileobj(fsrc=fsrc, fdst=fdst)
                with udf.opendir('/') as root:
                    cp_dir(root)

            if discatt_dat_file is not None:
                app.log.info('Copying %s...%s', backup_dir / 'discatt.dat', ' (dry-run)' if app.args.dry_run else '')
                if not app.args.dry_run:
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
                app.log.info('Ripping failed; Removed %s/.', backup_dir)
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
                assert entry_path.suffix in ('.mkv', '.webm', '.m2p')
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
                  chop_chaps=None,
                  ffprobe_dict=None,
                  hdr=None):
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
    codec_args = ffmpeg.Options()

    if (
            (chapter_file_ext == inputfile_ext
             or ext_to_codec(chapter_file_ext) == ext_to_codec(inputfile_ext))
            and not (chapter_lossless and inputfile_ext in (
                '.h264', # h264 copy just spits out a single empty chapter
                '.h265', # hevc/h265 copy just spits out a single empty chapter
            ))):
        codec = 'copy'
    else:
        codec = ext_to_codec(chapter_file_ext,
                             lossless=chapter_lossless,
                             hdr=hdr)
    ffmpeg_input_args += codec_to_input_args(codec)
    codec_args.set_option('-codec', codec)
    if codec != 'copy':
        codec_args += ext_to_codec_args(chapter_file_ext,
                                        codec=codec,
                                        lossless=chapter_lossless)
    codec_args += get_hdr_codec_args(inputfile=inputfile,
                                     codec=codec)

    chaps_list_copy = copy.deepcopy(chaps_list)
    chaps_list_copy[-1].chapters[-1].end = ffmpeg.Timestamp.MAX  # Make sure whole movie is captured
    ffmpeg_args = default_ffmpeg_args + ffmpeg_input_args + [
        '-fflags', '+genpts',
    ] + ffmpeg.input_args(inputfile) + [
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
    with perfcontext('Chop w/ ffmpeg segment muxer', log=True):
        ffmpeg(*ffmpeg_args,
               progress_bar_max=estimate_stream_duration(inputfile=inputfile),
               progress_bar_title=f'Split {inputfile} into {len(chaps)} chapters w/ ffmpeg',
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
            chopped_file.write_chapters(sub_chaps, log=True)

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

            with perfcontext('Chop w/ ffmpeg', log=True):
                ffmpeg_args = default_ffmpeg_args + [
                    '-start_at_zero', '-copyts',
                ] + ffmpeg.input_args(inputdir / stream_file_name) + [
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

def skip_duplicate_streams(streams, mux_subtitles=True):
    for stream1_i, stream1 in enumerate(streams):
        if stream1.skip:
            continue
        if stream1.codec_type is CodecType.video and stream1['disposition'].get('attached_pic', False) and not mux_attached_pic:
            continue
        if stream1.codec_type is CodecType.subtitle and not mux_subtitles:
            continue
        stream_language1 = stream1.language
        for stream2 in streams[stream1_i + 1:]:
            if stream2.skip:
                continue
            if stream2.codec_type is not stream1.codec_type:
                continue
            if stream2.codec_type is CodecType.video and stream2['disposition'].get('attached_pic', False) and not mux_attached_pic:
                continue
            if stream2.codec_type is CodecType.subtitle and not mux_subtitles:
                continue
            if stream2.language != stream_language1:
                continue
            if stream2.file.getsize() != stream1.file.getsize():
                continue
            app.log.info('Hash-comparing %s to %s; Please wait...', stream1.file, stream2.file)
            if stream2.file.md5_ex(show_progress_bar=True).hexdigest() != stream1.file.md5_ex(show_progress_bar=True).hexdigest():
                continue
            app.log.warning('%s identical to %s; Marking as skip',
                            stream2.file_name,
                            stream1.file_name,
                            )
            stream2['skip'] = f'Identical to stream #{stream1.pprint_index}'

def action_hb(inputfile, in_tags):
    app.log.info('HandBrake %s...', inputfile)
    inputfile = MediaFile.new_by_file_name(inputfile)
    inputfile_base, inputfile_ext = my_splitext(inputfile)
    outputfile_name = Path(inputfile_base + '.hb.mkv')
    if app.args.chain:
        app.args.mux_files += (outputfile_name,)

    if inputfile_ext in (
            '.mkv',
            '.webm',
            '.m2p',
            '.mpeg2',
            '.mp2v',
            ):
        for ffprobe_stream_dict in sorted_stream_dicts(inputfile.ffprobe_dict['streams']):
            if ffprobe_stream_dict.get('skip', False):
                continue
            if ffprobe_stream_dict.codec_type is CodecType.video:
                break
        else:
            raise ValueError('No video stream found!')

        try:
            mediainfo_track_dict, = [e
                                     for e in inputfile.mediainfo_dict['media']['track']
                                     if e['@type'] == 'Video']
        except ValueError:
            raise AssertionError('Expected a single Video mediainfo track: {!r}'.format(inputfile.mediainfo_dict['media']['track']))

        #framerate = pick_framerate(inputfile, inputfile.ffprobe_dict, ffprobe_stream_dict, mediainfo_track_dict)
        field_order, input_framerate, framerate = analyze_field_order_and_framerate(
            stream_file=inputfile,
            ffprobe_stream_json=ffprobe_stream_dict,
            mediainfo_track_dict=mediainfo_track_dict)

        real_width, real_height = qwidth, qheight = ffprobe_stream_dict['width'], ffprobe_stream_dict['height']
        if any(m.upper()[1:] in stream_file_name.upper().split('.')[1:]
               for m in Stereo3DMode.full_side_by_side.exts + Stereo3DMode.half_side_by_side.exts):
            real_width = qwidth // 2
        elif any(m.upper()[1:] in stream_file_name.upper().split('.')[1:]
                 for m in Stereo3DMode.full_top_and_bottom.exts + Stereo3DMode.half_top_and_bottom.exts):
            real_height = qheight // 2
        elif any(m.upper()[1:] in stream_file_name.upper().split('.')[1:]
                 for m in Stereo3DMode.hdmi_frame_packing.exts):
            if qheight == 2205:
                real_height = 1080
            elif qheight == 1470:
                real_height = 720

        video_target_bit_rate = get_vp9_target_bitrate(
            width=qwidth, height=qheight,
            frame_rate=framerate,
            )
        video_target_quality = get_vp9_target_quality(
            width=real_width, height=real_height,
            frame_rate=framerate,
            )

        with perfcontext('Convert w/ HandBrake', log=True):
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

def mux_dict_from_file(inputfile, outputdir):
    if not isinstance(inputfile, MediaFile):
        inputfile = MediaFile.new_by_file_name(inputfile)
        app.log.debug('inputfile=%r', inputfile)

    inputfile_base, inputfile_ext = my_splitext(inputfile.file_name)

    mux_dict = MmdemuxTask(outputdir / 'mux.json' if outputdir is not None else None,
                           load=False)

    first_pts_time_per_stream = {}

    if inputfile_ext in {
            '.ffv1.mkv',
    } \
            | Mpeg4ContainerFile.get_common_extensions() \
            | MatroskaFile.get_common_extensions() \
            :
        # NOT | Mpeg2ContainerFile.get_common_extensions()
        try:
            mux_dict['estimated_duration'] = str(ffmpeg.Timestamp(inputfile.ffprobe_dict['format']['duration']))
        except KeyError:
            pass

    if inputfile_ext in {
            '.ffv1.mkv',
    } \
            | Mpeg2ContainerFile.get_common_extensions() \
            | Mpeg4ContainerFile.get_common_extensions() \
            | MatroskaFile.get_common_extensions() \
            | SubtitleFile.get_common_extensions() \
            :

        attachment_index = 0  # First attachment is index 1

        iter_ffprobe_stream_dicts = iter(sorted_ffprobe_streams(
            inputfile.ffprobe_dict['streams']))
        iter_mediainfo_track_dicts = iter(sorted_mediainfo_tracks(
            mediainfo_track_dict
            for mediainfo_track_dict in inputfile.mediainfo_dict['media']['track']
            if mediainfo_track_dict['@type'] != 'General'))

        with contextlib.ExitStack() as stream_dict_loop_exit_stack:
            iter_frames = None

            while True:  # Iterate all iter_ffprobe_stream_dicts and iter_mediainfo_track_dicts
                stream = MmdemuxStream({}, parent=mux_dict)
                stream['index'] = max((stream2.index
                                       for stream2 in mux_dict['streams']),
                                      default=-1) + 1

                ffprobe_stream_dict = None
                mediainfo_track_dict = None
                stream_codec_name = None

                if ffprobe_stream_dict is None:
                    try:
                        ffprobe_stream_dict = next(iter_ffprobe_stream_dicts)
                    except StopIteration:
                        pass
                    else:
                        app.log.debug('1:ffprobe_stream_dict = %r', ffprobe_stream_dict)
                        stream['index'] = int(ffprobe_stream_dict['index'])

                        try:
                            stream_codec_name = ffprobe_stream_dict['codec_name']
                        except KeyError:
                            e = AssertionError('Stream codec name missing')
                            if app.args.force:
                                app.log.warning(e)
                                continue  # skip stream!
                            else:
                                raise ValueError(f'{e} (try --force to skip)')

                        try:
                            stream['original_id'] = int(ffprobe_stream_dict['id'],
                                                        16 if ffprobe_stream_dict['id'].startswith('0x') else 10)
                        except KeyError:
                            pass
                        stream['codec_type'] = ffprobe_stream_dict['codec_type']

                        # Confirm codec_type (temporary/local)
                        if (
                                stream.codec_type is CodecType.video
                                and stream_codec_name == 'mjpeg'
                                and ffprobe_stream_dict.get('tags', {}).get('mimetype', None) == 'image/jpeg'):
                            stream['codec_type'] = 'image'

                        if stream.codec_type is CodecType.video:
                            try:
                                mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                            except StopIteration:
                                e = AssertionError('Expected a mediainfo Video track')
                                if app.args.force:
                                    app.log.warning(e)
                                    mediainfo_track_dict = {
                                        '@type': 'Video',
                                    }
                                    mediainfo_track_dict = None  # TODO
                                else:
                                    raise ValueError(f'{e} (try --force)')
                            else:
                                assert CodecType(mediainfo_track_dict['@type']) is stream.codec_type, f'Stream #{stream.pprint_index} has codec type {stream.codec_type} but mediainfo track has {mediainfo_track_dict["@type"]}'
                        elif stream.codec_type is CodecType.audio:
                            try:
                                mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                            except StopIteration:
                                e = AssertionError('Expected a mediainfo Audio track')
                                if app.args.force:
                                    app.log.warning(e)
                                    mediainfo_track_dict = {
                                        '@type': 'Audio',
                                    }
                                    mediainfo_track_dict = None  # TODO
                                else:
                                    raise ValueError(f'{e} (try --force)')
                            else:
                                assert CodecType(mediainfo_track_dict['@type']) is stream.codec_type, f'Stream #{stream.pprint_index} has codec type {stream.codec_type} but mediainfo track has {mediainfo_track_dict["@type"]}'
                        elif stream.codec_type is CodecType.subtitle:
                            try:
                                mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                            except StopIteration:
                                # Example: ffprobe with large probeduration picks up a subtitle but not mediainfo
                                e = AssertionError('Expected a mediainfo Text track')
                                if True or app.args.force:
                                    app.log.warning(e)
                                    mediainfo_track_dict = {
                                        '@type': 'Text',
                                    }
                                    mediainfo_track_dict = None  # TODO
                                else:
                                    raise ValueError(f'{e} (try --force)')
                            else:
                                assert CodecType(mediainfo_track_dict['@type']) is stream.codec_type, f'Stream #{stream.pprint_index} has codec type {stream.codec_type} but mediainfo track has {mediainfo_track_dict["@type"]}'
                        elif stream.codec_type is CodecType.image:
                            mediainfo_track_dict = None  # Not its own track
                            # General
                            # ...
                            # Cover                                    : Yes
                            # Attachments                              : cover.jpg
                        elif stream.codec_type is CodecType.data:
                            if stream_codec_name == 'dvd_nav_packet':
                                mediainfo_track_dict = None
                            else:
                                raise NotImplementedError(f'{stream.codec_type}/{stream_codec_name}')
                        else:
                            raise NotImplementedError(stream.codec_type)
                        app.log.debug('1:mediainfo_track_dict = %r', mediainfo_track_dict)

                if ffprobe_stream_dict is None:
                    # No more ffprobe streams, try mediainfo tracks
                    try:
                        mediainfo_track_dict = next(iter_mediainfo_track_dicts)
                    except StopIteration:
                        pass
                    else:
                        app.log.debug('2:mediainfo_track_dict = %r', mediainfo_track_dict)
                        ffprobe_stream_dict = {
                            'disposition': {},
                        }
                        if mediainfo_track_dict['@type'] == 'Text':
                            # Closed Caption
                            ffprobe_stream_dict['original_id'] = mediainfo_track_dict['ID']
                            stream['codec_type'] = 'subtitle'
                            stream['caption_service_name'] = mediainfo_track_dict['extra']['CaptionServiceName'].lower()
                            if stream['caption_service_name'] in {'cc1', 'cc2', 'cc3', 'cc4'}:
                                stream_codec_name = mediainfo_track_dict['Format'].lower()
                                # CCs are embedded in the video stream
                                video_stream, = (stream2
                                                 for stream2 in mux_dict['streams']
                                                 if stream2.codec_type is CodecType.video)
                                stream['start_time'] = video_stream.start_time
                            else:
                                raise NotImplementedError(f'Caption Service Name: {stream["caption_service_name"]}')
                        elif mediainfo_track_dict['@type'] == 'Menu':
                            continue  # See also ffprobe_stream_dict['chapters']
                        else:
                            raise ValueError(mediainfo_track_dict['@type'])
                        ffprobe_stream_dict['codec_name'] = stream_codec_name

                if ffprobe_stream_dict is None and mediainfo_track_dict is None:
                    break

                if stream.codec_type in (
                        CodecType.video,
                        CodecType.audio,
                        CodecType.subtitle,
                        CodecType.image
                ):
                    EstimatedFrameCount = None
                    if stream.codec_type is CodecType.video:
                        if app.args.force_still_video:
                            EstimatedFrameCount = 1
                        elif mediainfo_track_dict is not None and 'Duration' in mediainfo_track_dict:
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

                    # Confirm codec_type (final) and stream_file_ext
                    if (
                            stream.codec_type in (
                                CodecType.video,
                                CodecType.image,
                            )
                            and stream_codec_name == 'mjpeg'
                            and ffprobe_stream_dict.get('tags', {}).get('mimetype', None) == 'image/jpeg'):
                        stream['codec_type'] = 'image'
                        stream_file_ext = '.jpg'
                        stream['attachment_type'] = my_splitext(ffprobe_stream_dict['tags']['filename'])[0]
                    elif (
                        stream.codec_type is CodecType.video
                        and EstimatedFrameCount == 1):
                        stream_file_ext = '.png'
                        app.log.warning('Detected %s stream #%s is still image', stream.codec_type, stream.pprint_index)
                    else:
                        stream_file_ext = codec_name_to_ext(stream_codec_name)

                    if stream.codec_type is CodecType.video:
                        if app.args.video_language:
                            ffprobe_stream_dict.setdefault('tags', {})
                            ffprobe_stream_dict['tags']['language'] = app.args.video_language.code3
                        # stream['pixel_aspect_ratio'] = ffprobe_stream_dict['pixel_aspect_ratio']
                        # stream['display_aspect_ratio'] = ffprobe_stream_dict['display_aspect_ratio']

                    if stream.codec_type is CodecType.audio:
                        try:
                            stream['original_bit_rate'] = ffprobe_stream_dict['bit_rate']
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

                    try:
                        stream_time_base = Fraction(ffprobe_stream_dict['time_base'])
                    except:
                        stream_time_base = None

                    codec_encoding_delay = get_codec_encoding_delay(inputfile, ffprobe_stream_dict=ffprobe_stream_dict)
                    try:
                        stream_start_time = ffprobe_stream_dict['start_time']
                    except KeyError:
                        stream_start_time = None
                    else:
                        stream_start_time = adjust_start_time(
                            ffmpeg.Timestamp(stream_start_time),
                            codec_encoding_delay=codec_encoding_delay,
                            stream_time_base=stream_time_base)

                    check_start_time = app.args.check_start_time
                    if stream.codec_type is CodecType.subtitle:
                        check_start_time = False
                    if check_start_time is Auto and stream_start_time == 0.0:
                        # Sometimes ffprobe reports start_time=0 but mediainfo reports Delay (with low accuracy)
                        Delay = (mediainfo_track_dict or {}).get('Delay', None)
                        Delay = qip.utils.Timestamp(Delay) if Delay is not None else None
                        if Delay:
                            check_start_time = True
                    if check_start_time is Auto and stream_start_time and stream.codec_type is CodecType.video:
                        check_start_time = True
                    if check_start_time is Auto:
                        check_start_time = False
                    if check_start_time:
                        if stream.index not in first_pts_time_per_stream:
                            if iter_frames is None:
                                iter_frames = iter_av_frames(inputfile)
                                iter_frames = sync_iter_av_frames(iter_frames)
                            for av_stream, av_frame in iter_frames:
                                try:
                                    if av_stream.index in first_pts_time_per_stream:
                                        continue
                                except AttributeError:
                                    # no stream_index!
                                    continue
                                if av_frame.pts is None:
                                    continue
                                first_pts_time_per_stream[av_stream.index] = calc_packet_time(av_frame.pts, av_frame.time_base)
                                if av_stream.index == stream.index:
                                    break
                        if stream.index in first_pts_time_per_stream:
                            stream_start_time_pts = adjust_start_time(
                                first_pts_time_per_stream[stream.index],
                                codec_encoding_delay=codec_encoding_delay,
                                stream_time_base=stream_time_base)
                        else:
                            stream_start_time_pts = AnyTimestamp(0)  # TODO
                        if stream_start_time != stream_start_time_pts:
                            app.log.warning('Correcting %s stream #%s start time %s to %s based on first frame PTS', stream.codec_type, stream.pprint_index, stream_start_time, stream_start_time_pts)
                            stream_start_time = stream_start_time_pts

                    if stream_start_time and stream.codec_type is CodecType.subtitle:
                        # ffmpeg estimates the start_time if it is low enough but the actual time indices will be correct
                        app.log.warning('Correcting %s stream #%s start time %s to 0 based on experience', stream.codec_type, stream.pprint_index, stream_start_time)
                        stream_start_time = qip.utils.Timestamp(0)
                    if stream_start_time:
                        app.log.warning('%s stream #%s start time is %s', stream.codec_type.title(), stream.pprint_index, stream_start_time)
                    if stream_start_time is None:
                        stream.pop('start_time', None)
                    else:
                        stream['start_time'] = None if stream_start_time is None else str(stream_start_time)

                    stream['disposition'] = ffprobe_stream_dict['disposition']

                    try:
                        stream['3d-plane'] = int(ffprobe_stream_dict['tags']['3d-plane'])
                    except KeyError:
                        try:
                            stream['3d-plane'] = int(ffprobe_stream_dict['tags']['3d-plane-eng'])
                        except KeyError:
                            pass

                    try:
                        stream_title = stream['title'] = ffprobe_stream_dict['tags']['title']
                    except KeyError:
                        pass
                    else:
                        if stream.codec_type is CodecType.audio \
                                and re.match(r'^(Stereo|Mono|Surround [0-9.]+)$', stream_title):
                            del stream['title']

                    try:
                        stream['language'] = str(isolang(ffprobe_stream_dict['tags']['language']))
                    except KeyError:
                        pass
                    else:
                        if stream['language'] == 'und':
                            del stream['language']

                    master_display = ''  # SMPTE 2086 mastering data
                    if stream.codec_type is CodecType.video:
                        color_primaries = ColorSpaceParams.from_mediainfo_track_dict(mediainfo_track_dict=mediainfo_track_dict)
                        if color_primaries:
                            master_display += color_primaries.master_display_str()
                        luminance = LuminanceParams.from_mediainfo_track_dict(mediainfo_track_dict=mediainfo_track_dict)
                        if luminance:
                            master_display += luminance.master_display_str()
                        if master_display:
                            stream['master_display'] = master_display
                        try:
                            stream['max_cll'] = int(mediainfo_track_dict['MaxCLL'])
                        except KeyError:
                            pass
                        try:
                            stream['max_fall'] = int(mediainfo_track_dict['MaxFALL'])
                        except KeyError:
                            pass
                        try:
                            stream['color_transfer'] = ffprobe_stream_dict['color_transfer']
                        except KeyError:
                            pass
                        try:
                            stream['color_primaries'] = ffprobe_stream_dict['color_primaries']
                        except KeyError:
                            pass

                    stream_file_format_ext = ''
                    if stream.codec_type is CodecType.video \
                            and stream_codec_name == 'h264' \
                            and ffprobe_stream_dict.get('profile', '') == 'High' \
                            and ffprobe_stream_dict.get('tags', {}).get('stereo_mode', '') == 'block_lr' \
                            and {
                                'side_data_type': 'Stereo 3D',
                                'type': 'frame alternate',
                                'inverted': 0,
                            } in ffprobe_stream_dict.get('side_data_list', []) \
                            and mediainfo_track_dict.get('Format', '') == 'AVC' \
                            and mediainfo_track_dict.get('Format_Profile', '').startswith('Stereo High') \
                            and int(mediainfo_track_dict.get('MultiView_Count', 1)) == 2 \
                            and mediainfo_track_dict.get('MultiView_Layout', '') == 'Both Eyes laced in one block (left eye first)':
                        # 3D Video from MakeMKV, h264+MVC
                        # and inputfile.mediainfo_dict['media'].get('Encoded_Application', '').startswith('MakeMKV')
                        stream_file_format_ext += '.3D.MVC'

                    stream_file_name_language_suffix = '.%s' % (stream.language,) if stream.language is not isolang('und') else ''
                    if stream['disposition'].get('attached_pic', False):
                        attachment_index += 1
                        output_track_file_name = 'attachment-%02d-%s%s%s%s' % (
                                attachment_index,
                                stream.codec_type,
                                stream_file_name_language_suffix,
                                stream_file_format_ext,
                                stream_file_ext,
                                )
                    else:
                        output_track_file_name = 'track-%02d-%s%s%s%s' % (
                                stream.index,
                                stream.codec_type,
                                stream_file_name_language_suffix,
                                stream_file_format_ext,
                                stream_file_ext,
                                )
                    stream['file_name'] = output_track_file_name


                elif stream.codec_type is CodecType.data:
                    if stream_codec_name == 'dvd_nav_packet':
                        app.log.warning('Skipping %s/%s stream.', stream.codec_type, stream_codec_name)
                        stream['skip'] = f'Skipping {stream_codec_name}'
                    else:
                        raise NotImplementedError(f'{stream.codec_type}/{stream_codec_name}')
                else:
                    raise ValueError('Unsupported codec type %r' % (stream.codec_type,))

                original_source_description = []
                original_source_description.append(stream_codec_name)
                if stream.codec_type is CodecType.video:
                    try:
                        original_source_description.append(ffprobe_stream_dict['profile'])
                    except KeyError:
                        pass
                    try:
                        original_source_description.append(f'%dbits' % (mediainfo_track_dict['BitDepth'],))
                    except KeyError:
                        pass
                    try:
                        original_source_description.append(mediainfo_track_dict['HDR_Format'])
                    except KeyError:
                        pass
                    original_source_description.append('%sx%s' % (ffprobe_stream_dict['width'], ffprobe_stream_dict['height']))
                    original_source_description.append(ffprobe_stream_dict['display_aspect_ratio'])
                elif stream.codec_type is CodecType.audio:
                    try:
                        original_source_description.append(ffprobe_stream_dict['profile'])
                    except KeyError:
                        pass
                    try:
                        original_source_description.append(ffprobe_stream_dict['channel_layout'])
                    except KeyError:
                        try:
                            original_source_description.append('%sch' % (ffprobe_stream_dict['channels'],))
                        except KeyError:
                            pass
                    try:
                        audio_bitrate = int(ffprobe_stream_dict['bit_rate'])
                    except KeyError:
                        pass
                    else:
                        original_source_description.append(f'{audio_bitrate // 1000}kbps')
                    try:
                        audio_samplerate = int(ffprobe_stream_dict['sample_rate'])
                    except KeyError:
                        pass
                    else:
                        original_source_description.append(f'{audio_samplerate // 1000}kHz')
                    try:
                        audio_samplefmt = ffprobe_stream_dict['sample_fmt']
                    except KeyError:
                        pass
                    else:
                        try:
                            bits_per_raw_sample = int(ffprobe_stream_dict['bits_per_raw_sample'])
                        except KeyError:
                            original_source_description.append(f'{audio_samplefmt}')
                        else:
                            original_source_description.append(f'{audio_samplefmt}({bits_per_raw_sample}b)')
                elif stream.codec_type is CodecType.subtitle:
                    try:
                        original_source_description.append(stream['caption_service_name'])
                    except KeyError:
                        pass
                elif stream.codec_type is CodecType.image:
                    try:
                        original_source_description.append(stream['attachment_type'])
                    except KeyError:
                        pass
                    original_source_description.append('%sx%s' % (ffprobe_stream_dict['width'], ffprobe_stream_dict['height']))
                elif stream.codec_type is CodecType.data:
                    pass
                else:
                    raise ValueError('Unsupported codec type %r' % (stream.codec_type,))
                if original_source_description:
                    stream['original_source_description'] = ', '.join(original_source_description)

                mux_dict['streams'].append(stream)

    else:
        raise ValueError(f'Unsupported extension: {inputfile_ext}')

    return mux_dict

def action_mux(inputfile, in_tags,
               mux_attached_pic=True,
               mux_subtitles=True):
    app.log.info('Muxing %s...', inputfile)
    if not isinstance(inputfile, MediaFile):
        inputfile = MediaFile.new_by_file_name(inputfile)
        app.log.debug('inputfile=%r', inputfile)
    inputfile_base, inputfile_ext = my_splitext(inputfile)
    outputdir = Path(inputfile_base if app.args.project is Auto
                     else app.args.project)
    if app.args.chain:
        app.args.optimize_dirs += (outputdir,)

    remux = False
    if outputdir.is_dir():
        if app.args.remux:
            app.log.warning('Directory exists: %s; Just remuxing', outputdir)
            remux = True
        else:
            if app.args.chain:
                app.log.warning('Directory exists: %s; Just chaining', outputdir)
                return True
            elif app.args._continue:
                app.log.warning('Directory exists: %s; Ignoring', outputdir)
                return True
            else:
                raise OSError(errno.EEXIST, f'Directory exists: {outputdir}')

    init_inputfile_tags(inputfile, in_tags=in_tags)

    mux_dict = mux_dict_from_file(inputfile, outputdir)
    mux_dict['tags'] = inputfile.tags

    if app.args.interactive and not remux and not (app.args.rip_dir and outputdir in app.args.rip_dir):
        with app.need_user_attention():
            from prompt_toolkit.formatted_text import FormattedText
            from prompt_toolkit.completion import WordCompleter

            parser = argparse.ArgumentParser(
                formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                description='Initial tags setup',
                add_help=False, usage=argparse.SUPPRESS,
                exit_on_error=False,
                )
            subparsers = parser.add_subparsers(dest='action', required=True, help='Commands')
            subparser = subparsers.add_parser('help', aliases=('h', '?'), help='print this help')
            subparser = subparsers.add_parser('edit', help='edit tags')
            subparser = subparsers.add_parser('search', help='search The Movie DB')
            subparser = subparsers.add_parser('continue', aliases=('c',), help='continue the muxing action -- done')
            subparser = subparsers.add_parser('quit', aliases=('q',), help='quit')

            completer = WordCompleter([name for name in subparsers._name_parser_map.keys() if len(name) > 1])

            print('')
            while True:
                print('Initial tags setup')
                print(mux_dict['tags'].cite())
                while True:
                    c = app.prompt(completer=completer, prompt_mode='init')
                    if c.strip():
                        break
                try:
                    ns = parser.parse_args(args=shlex.split(c, posix=os.name == 'posix'))
                except (argparse.ArgumentError, ValueError) as e:
                    if isinstance(e, argparse.ParserExitException) and e.status == 0:
                        # help?
                        pass
                    else:
                        app.log.error(e)
                        print('')
                    continue
                if ns.action == 'help':
                    print(parser.format_help())
                elif ns.action == 'continue':
                    break
                elif ns.action == 'quit':
                    exit(1)
                elif ns.action == 'edit':
                    mux_dict['tags'] = do_edit_tags(mux_dict['tags'])
                elif ns.action == 'search':
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
                            movie_tags = tmdb.movie_to_tags(o_movie)
                            i = app.radiolist_dialog(
                                title='Please select a movie',
                                values=[(i, '{cite} (#{id}) -- {overview}'.format(
                                             cite=tmdb.cite_movie(o_movie),
                                             id=o_movie.id,
                                             overview=o_movie.overview,
                                         ))
                                         for i, o_movie in enumerate(l_movies)],
                                help_handler=help_handler)
                            if i is None:
                                print('Cancelled by user!')
                                continue
                        o_movie = l_movies[i]

                        mux_dict['tags'].title = o_movie.title
                        mux_dict['tags'].date = o_movie.release_date
                        #if mux_dict['tags'].language is None:
                        #    mux_dict['tags'].language = language
                        app.log.info('%s: %s', inputfile, mux_dict['tags'].cite())

                else:
                    app.log.error('Invalid input: %r' % (ns.action,))

    if not remux:
        if app.args.dry_run:
            app.log.verbose('CMD (dry-run): %s', list2cmdline(['mkdir', outputdir]))
        else:
            os.mkdir(outputdir)

    num_extract_errors = 0
    has_forced_subtitle = False
    attachment_index = 0  # First attachment is index 1

    def extract_streams(inputfile, streams):
        nonlocal num_extract_errors
        nonlocal has_forced_subtitle
        nonlocal attachment_index

        mkvextract_tracks_args = []
        mkvextract_attachments_args = []

        for stream in streams:

            stream_file_name = stream['file_name']
            stream_file_base, stream_file_ext = my_splitext(stream_file_name)

            if stream.codec_type is CodecType.video:
                pass

            elif stream.codec_type is CodecType.audio:
                pass

            elif stream.codec_type is CodecType.subtitle:

                if stream['disposition'].get('forced', None):
                    has_forced_subtitle = True

            elif stream.codec_type is CodecType.image:
                pass

            elif stream.codec_type is CodecType.data:
                pass

            else:
                raise NotImplementedError(stream.codec_type)

            if stream.codec_type in (
                    CodecType.video,
                    CodecType.audio,
                    CodecType.subtitle,
                    CodecType.image,
            ):

                if (
                        (not mux_attached_pic and stream['disposition'].get('attached_pic', False)) or
                        (not mux_subtitles and stream.codec_type is CodecType.subtitle)):
                    app.log.warning('Not muxing %s stream #%s...', stream.codec_type, stream.pprint_index)
                    continue

                if stream.codec_type is CodecType.subtitle \
                        and stream_file_ext in (
                            '.sub',
                        ) and not isinstance(inputfile, MatroskaFile):
                    with perfcontext('Extract %s stream #%s w/ mencoder' % (stream.codec_type, stream.pprint_index,), log=True):
                        mencoder_args = []
                        mencoder_args += [
                            inputfile,
                        ]
                        assert stream_file_name.endswith('.sub')
                        mencoder_args += [
                            '-nosound',
                            '-ovc', 'frameno',
                            '-o', '/dev/null',
                            '-vobsuboutindex', 0,
                            '-sid', stream['original_id'],
                            '-vobsubout', outputdir / stream_file_name[:-4],  # strip '.sub'
                        ]
                        mencoder(*mencoder_args,
                                 dry_run=app.args.dry_run)
                                 # TODO y=app.args.yes or app.args.remux)
                    continue

                if stream.codec_type is CodecType.subtitle \
                        and stream.get('caption_service_name', None) \
                        and stream_file_ext in (
                            '.srt',     # SubRip (default, so not actually needed).
                            '.sami',    # MS Synchronized Accesible Media Interface.
                            #'.bin',     # CC data in CCExtractor's own binary format.
                            #'.raw',     # CC data in McPoodle's Broadcast format.
                            #'.dvdraw',  # CC data in McPoodle's DVD format.
                            '.txt',     # Transcript (no time codes, no roll-up captions, just the plain transcription.
                        ):
                    with perfcontext('Extract %s stream #%s w/ ccextractor' % (stream.codec_type, stream.pprint_index,), log=True):
                        ccextractor_args = []
                        if stream['caption_service_name'] == 'cc1':
                            ccextractor_args += [
                                '-1',  # '-cc1',
                            ]
                        elif stream['caption_service_name'] == 'cc2':
                            ccextractor_args += [
                                '-2',  # '-cc1',
                            ]
                        elif stream['caption_service_name'] == 'cc3':
                            ccextractor_args += [
                                '-1', '-cc2',
                            ]
                        elif stream['caption_service_name'] == 'cc4':
                            ccextractor_args += [
                                '-2', '-cc2',
                            ]
                        else:
                            raise NotImplementedError(stream['caption_service_name'])
                        ccextractor_args += [
                            f'-out={stream_file_ext[1:]}',
                            '-utf8',
                            inputfile,
                            '-o', outputdir / stream_file_name,
                        ]
                        ccextractor(*ccextractor_args,
                                    dry_run=app.args.dry_run)
                                    # TODO y=app.args.yes or app.args.remux)
                    continue

                if stream['disposition'].get('attached_pic', False):
                    attachment_index += 1  # TODO inherit from mux_dict_from_file
                    app.log.info('Will extract %s stream #%s w/ mkvextract: %s', stream.codec_type, stream.pprint_index, stream_file_name)
                    mkvextract_attachments_args += [
                        '%d:%s' % (
                            attachment_index,
                            outputdir / stream_file_name,
                        )]
                    continue

                if (
                        app.args.track_extract_tool == 'ffmpeg'
                        or not isinstance(inputfile, MatroskaFile)
                        # Avoid mkvextract error: Extraction of track ID 3 with the CodecID 'D_WEBVTT/SUBTITLES' is not supported.
                        # (mkvextract expects S_TEXT/WEBVTT)
                        or stream_file_ext == '.vtt'
                        # Avoid mkvextract error: Extraction of track ID 1 with the CodecID 'A_MS/ACM' is not supported.
                        # https://www.makemkv.com/forum/viewtopic.php?t=2530
                        or stream_file_ext == '.wav'  # stream_codec_name in ('pcm_s16le', 'pcm_s24le')
                        # Avoid mkvextract error: Track 0 with the CodecID 'V_MS/VFW/FOURCC' is missing the "default duration" element and cannot be extracted.
                        or stream_file_ext in still_image_exts
                        or (app.args.track_extract_tool is Auto
                            # For some codecs, mkvextract is not reliable and may encode the wrong frame rate; Use ffmpeg.
                            and stream_file_ext in (  # stream_codec_name in ('vp8', 'vp9')
                                '.vp8.ivf',
                                '.vp9.ivf',
                                ))):
                    with perfcontext('Extract %s stream #%s w/ ffmpeg' % (stream.codec_type, stream.pprint_index,), log=True):
                        force_format = None
                        try:
                            force_format = ext_to_container(stream_file_ext)
                        except ValueError:
                            pass
                        ffmpeg_args = [] + default_ffmpeg_args
                        if app.args.seek_video:
                            ffmpeg_args += [
                                '-ss', ffmpeg.Timestamp(app.args.seek_video),
                                ]
                        ffmpeg_args += ffmpeg.input_args(inputfile)
                        ffmpeg_args += [
                            '-map_metadata', '-1',
                            '-map_chapters', '-1',
                            '-map', '0:%d' % (stream.index,),
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
                            outputdir / stream_file_name,
                            ]
                        ffmpeg(*ffmpeg_args,
                            progress_bar_max=estimate_stream_duration(inputfile=inputfile),
                            progress_bar_title=f'Extract {stream.codec_type} track {stream.pprint_index} w/ ffmpeg',
                            dry_run=app.args.dry_run,
                            y=app.args.yes or app.args.remux)
                    continue

                if app.args.track_extract_tool in ('mkvextract', Auto):
                    app.log.info('Will extract %s stream #%s w/ mkvextract: %s', stream.codec_type, stream.pprint_index, stream_file_name)
                    mkvextract_tracks_args += [
                        '%d:%s' % (
                            stream.index,
                            outputdir / stream_file_name,
                        )]
                    # raise NotImplementedError('extracted tracks from mkvextract must be reset to start at 0 PTS')
                    continue

                raise NotImplementedError('unsupported track extract tool: %r' % (app.args.track_extract_tool,))

        if mkvextract_tracks_args:
            with perfcontext('Extract tracks w/ mkvextract', log=True):
                cmd = [
                    'mkvextract', 'tracks', inputfile,
                ] + mkvextract_tracks_args
                do_spawn_cmd(cmd)
        if mkvextract_attachments_args:
            with perfcontext('Extract attachments w/ mkvextract', log=True):
                cmd = [
                    'mkvextract', 'attachments', inputfile,
                ] + mkvextract_attachments_args
                do_spawn_cmd(cmd)

    with perfcontext('Extract tracks', log=True):
        extract_streams(inputfile=inputfile, streams=mux_dict['streams'])

    # Detect duplicates
    if not app.args.dry_run:
        skip_duplicate_streams(mux_dict['streams'],
                               mux_subtitles=mux_subtitles)

    # Pre-stream post-processing

    subtitle_counts = []

    iter_mediainfo_track_dicts = iter(sorted_mediainfo_tracks(
        mediainfo_track_dict
        for mediainfo_track_dict in inputfile.mediainfo_dict['media']['track']
        if mediainfo_track_dict['@type'] != 'General'))
    for stream in sorted_stream_dicts(mux_dict['streams']):
        if app.args.dry_run and not stream.file.exists():
            app.log.warning('Stream #%s file does not exist: %s (ignoring due to dry-run but information may be incomplete)', stream.pprint_index, stream.file)
            continue

        if stream.codec_type is CodecType.video:
            try:
                mediainfo_track_dict = next(iter_mediainfo_track_dicts)
            except StopIteration:
                e = AssertionError('Expected a mediainfo Video track')
                if app.args.force:
                    app.log.warning(e)
                    mediainfo_track_dict = {
                        '@type': 'Video',
                    }
                else:
                    raise ValueError(f'{e} (try --force)')
            assert CodecType(mediainfo_track_dict['@type']) is stream.codec_type, f'Stream #{stream.pprint_index} has codec type {stream.codec_type} but mediainfo track has {mediainfo_track_dict["@type"]}'
        elif stream.codec_type is CodecType.audio:
            try:
                mediainfo_track_dict = next(iter_mediainfo_track_dicts)
            except StopIteration:
                e = AssertionError('Expected a mediainfo Audio track')
                if app.args.force:
                    app.log.warning(e)
                    mediainfo_track_dict = {
                        '@type': 'Audio',
                    }
                else:
                    raise ValueError(f'{e} (try --force)')
            assert CodecType(mediainfo_track_dict['@type']) is stream.codec_type, f'Stream #{stream.pprint_index} has codec type {stream.codec_type} but mediainfo track has {mediainfo_track_dict["@type"]}'
        elif stream.codec_type is CodecType.subtitle:
            try:
                mediainfo_track_dict = next(iter_mediainfo_track_dicts)
            except StopIteration:
                # Example: ffprobe with large probeduration picks up a subtitle but not mediainfo
                if True or app.args.force:
                    app.log.warning(e)
                    mediainfo_track_dict = {
                        '@type': 'Text',
                    }
                    mediainfo_track_dict = None  # TODO
                else:
                    raise ValueError(f'{e} (try --force)')
            else:
                assert CodecType(mediainfo_track_dict['@type']) is stream.codec_type, f'Stream #{stream.pprint_index} has codec type {stream.codec_type} but mediainfo track has {mediainfo_track_dict["@type"]}'
        elif stream.codec_type is CodecType.image:
            mediainfo_track_dict = None  # Not its own track
        elif stream.codec_type is CodecType.data:
            mediainfo_track_dict = None  # Not its own track
            assert stream.skip
        else:
            raise NotImplementedError(stream.codec_type)

        if stream.skip:
            continue

        stream_file_name = stream['file_name']
        stream_file_base, stream_file_ext = my_splitext(stream_file_name)

        if stream.codec_type is CodecType.video:

            def try_int(v):
                try:
                    return int(v)
                except ValueError:
                    return v

            try:
                mediainfo_stream_id = stream['original_id'] & 0xff
            except KeyError:
                mediainfo_stream_id = stream.index + 1
            try:
                mediainfo_track_dict, = (
                    mediainfo_track_dict
                    for mediainfo_track_dict in inputfile.mediainfo_dict['media']['track']
                    if mediainfo_stream_id == mediainfo_track_dict.get('ID', 0))
            except ValueError:
                e = 'Expected a single mediainfo track with ID {}: {!r}'.format(mediainfo_stream_id, inputfile.mediainfo_dict['media']['track'])
                if app.args.force:
                    app.log.warning(e)
                    mediainfo_track_dict = {
                        '@type': 'Video',
                    }
                    mediainfo_track_dict = None  # TODO
                else:
                    raise ValueError(f'{e} (try --force)')
            if mediainfo_track_dict is not None:
                assert CodecType(mediainfo_track_dict['@type']) is stream.codec_type, f'Stream #{stream.pprint_index} has codec type {stream.codec_type} but mediainfo track has {mediainfo_track_dict["@type"]}'
                storage_aspect_ratio = Ratio(mediainfo_track_dict['Width'], mediainfo_track_dict['Height'])
                display_aspect_ratio = Ratio(mediainfo_track_dict['DisplayAspectRatio'])
                pixel_aspect_ratio = display_aspect_ratio / storage_aspect_ratio
                stream['display_aspect_ratio'] = str(display_aspect_ratio)
                stream['pixel_aspect_ratio'] = str(pixel_aspect_ratio)  # invariable

        if mux_subtitles and stream.codec_type is CodecType.subtitle:
            stream_forced = stream['disposition'].get('forced', None)
            # TODO Detect closed_caption
            if isinstance(stream.file, PgsFile):
                palette = qip.pgs.pgs_segment_to_YCbCr_palette(pgs_segment=None)
                def is_pgs_valid_ods_segment(pgs_segment):
                    nonlocal palette
                    if pgs_segment.segment_type is PgsFile.SegmentType.ODS:
                        object_data = qip.pgs.rle_decode(pgs_segment.object_data,
                                                         pgs_segment.width,
                                                         pgs_segment.height,
                                                         palette=palette)
                        object_data = list(object_data)
                        if not object_data or all(e == object_data[0] for e in object_data):
                            return False  # Empty
                        return True
                    elif pgs_segment.segment_type is PgsFile.SegmentType.PDS:
                        palette = qip.pgs.pgs_segment_to_YCbCr_palette(pgs_segment)
                    return False
                subtitle_count = sum(
                    is_pgs_valid_ods_segment(pgs_segment)
                    for pgs_segment in stream.file.iter_pgs_segments())
            elif stream_file_ext in ('.sub', '.sup'):
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
            elif stream_file_ext in ('.srt', '.ass', '.vtt'):
                out = open(outputdir / stream_file_name, 'rb').read()
                subtitle_count = out.count(b'\n\n') + out.count(b'\n\r\n')
            else:
                raise NotImplementedError(stream_file_ext)
            if subtitle_count == 1 \
                    and File(outputdir / stream_file_name).getsize() == 2048:
                app.log.warning('Detected empty single-frame subtitle stream #%s (%s); Skipping.',
                                stream.pprint_index,
                                stream.language)
                stream['skip'] = f'Empty single-frame subtitle stream'
            elif not subtitle_count:
                app.log.warning('Detected empty subtitle stream #%s (%s); Skipping.',
                                stream.pprint_index,
                                stream.language)
                stream['skip'] = 'Empty subtitle stream'
            else:
                stream['subtitle_count'] = subtitle_count
                subtitle_counts.append(
                    (stream, subtitle_count))

    if mux_subtitles and not has_forced_subtitle and subtitle_counts:
        max_subtitle_size = max(subtitle_count
                                for stream, subtitle_count in subtitle_counts)
        for stream, subtitle_count in subtitle_counts:
            if subtitle_count <= 0.10 * max_subtitle_size:
                app.log.info('Detected subtitle stream #%s (%s) is forced',
                             stream.pprint_index,
                             stream.language)
                stream['disposition']['forced'] = True

    chapters_aux_file = MatroskaChaptersFile(inputfile.file_name.with_suffix('.chapters.xml'))
    if chapters_aux_file.exists():
        chapters_xml_file = MatroskaChaptersFile(outputdir / 'chapters.xml')
        if not remux:
            if not app.args.dry_run:
                shutil.copyfile(chapters_aux_file,
                                chapters_xml_file,
                                follow_symlinks=True)
        mux_dict['chapters']['file_name'] = os.fspath(chapters_xml_file.file_name.relative_to(outputdir))
    if inputfile.ffprobe_dict['chapters']:
        chapters_xml_file = MatroskaChaptersFile(outputdir / 'chapters.xml')
        if not remux:
            chapters_xml_file.chapters = inputfile.load_chapters()
            if not app.args.dry_run:
                chapters_xml_file.create()
        mux_dict['chapters']['file_name'] = os.fspath(chapters_xml_file.file_name.relative_to(outputdir))

    if not app.args.dry_run or remux:
        mux_dict.save(mux_file_name=outputdir / ('mux%s.json' % ('.remux' if remux else '',)))

        if remux and app.args.interactive:
            eddiff([
                '%s/mux%s.json' % (outputdir, ''),
                '%s/mux%s.json' % (outputdir, '.remux'),
            ])

    mux_dict.print_streams_summary()

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
        outputdir = Path('%s' % (inputfile_base,) \
                         if app.args.project is Auto else app.args.project)

        if outputdir.is_dir():
            if False and app.args._continue:
                app.log.warning('Directory exists: %r; Just verifying', outputdir)
                dir_existed = True
            else:
                raise OSError(errno.EEXIST, f'Directory exists: {outputdir}')

    if not dir_existed:
        assert action_mux(inputfile, in_tags=in_tags,
                          mux_attached_pic=False,
                          mux_subtitles=False)
    inputdir = outputdir

    mux_dict = MmdemuxTask(inputdir / 'mux.json', in_tags=in_tags)

    stream_duration_table = []
    for stream_dict in sorted_stream_dicts(mux_dict['streams']):
        if stream_dict.skip:
            continue
        stream_file_name = stream_dict['file_name']
        stream_file_base, stream_file_ext = my_splitext(stream_file_name)
        if stream_dict.codec_type in (
                CodecType.video,
                CodecType.image,
        ) and stream_file_ext in still_image_exts:
            continue
        if stream_dict.codec_type in (
                CodecType.video,
                CodecType.audio,
        ):

            if True:
                try:
                    stream_dict.file.duration = float(ffmpeg.Timestamp(stream_dict.file.ffprobe_dict['format']['duration']))
                except KeyError:
                    pass
                ffprobe_stream_json, = stream_dict.file.ffprobe_dict['streams']
                app.log.debug('ffprobe_stream_json=%r', ffprobe_stream_json)
                try:
                    stream_duration = ffprobe_stream_json['duration']
                except KeyError:
                    stream_duration = None
                else:
                    stream_duration = AnyTimestamp(stream_duration)

            stream_start_time = AnyTimestamp(stream_dict['start_time'])
            stream_total_time = None if stream_duration is None else stream_start_time + stream_duration
            stream_duration_table.append([stream_dict.file, stream_start_time, stream_duration, stream_total_time])
    print('')
    print(tabulate(stream_duration_table,
                   headers=[
                       'File',
                       'Start time',
                       'Duration',
                       'Total time',
                   ],
                   colalign=[
                       'left',
                       'right',
                       'right',
                       'right',
                   ],
                   tablefmt='simple',
                   ))

    min_stream_duration = min(stream_duration
                              for stream_file, stream_start_time, stream_duration, stream_total_time in stream_duration_table
                              if stream_duration is not None)
    max_stream_duration = max(stream_duration
                              for stream_file, stream_start_time, stream_duration, stream_total_time in stream_duration_table
                              if stream_duration is not None)
    if max_stream_duration - min_stream_duration > 5:
        raise LargeDiscrepancyInStreamDurationsError(inputdir=inputdir)

    if not dir_existed:
        app.log.info('Cleaning up %s', inputdir)
        shutil.rmtree(inputdir)

    return True

def action_status(inputfile):
    app.log.info('Status of %s...', inputfile)

    if inputfile.is_file():
        mux_dict = mux_dict_from_file(inputfile, outputdir=None)

    elif inputfile.is_dir():
        inputdir = inputfile
        mux_dict = MmdemuxTask(inputdir / 'mux.json')

    else:
        raise ValueError(f'Not a file or directory: {inputfile}')

    mux_dict.print_streams_summary()

def action_update(inputdir, in_tags):
    app.log.info('Updating %s...', inputdir)

    mux_dict = MmdemuxTask(inputdir / 'mux.json', in_tags=in_tags)

    if not app.args.dry_run:
        mux_dict.save()

def action_combine(inputdirs, in_tags):
    outputdir = inputdirs[0]
    app.log.info('Combining %s...', outputdir)

    for i_inputdir, inputdir in enumerate(inputdirs):
        if i_inputdir:
            app.log.info('... Adding %s...', inputdir)
        mux_dict = MmdemuxTask(inputdir / 'mux.json', in_tags=in_tags)

        mux_dict['streams'] = sorted_stream_dicts(mux_dict['streams'])

        if i_inputdir:
            def set_streams_relative_file_name(streams):
                nonlocal inputdir
                nonlocal outputdir
                for stream in streams:
                    stream['file_name'] = os.path.relpath(
                        inputdir.resolve() / stream['file_name'],
                        outputdir)
                    try:
                        concat_streams = stream['concat_streams']
                    except KeyError:
                        pass
                    else:
                        set_streams_relative_file_name(concat_streams)
            set_streams_relative_file_name(mux_dict['streams'])

        if i_inputdir:
            combined_mux_dict['streams'] += mux_dict['streams']
            try:
                combined_mux_dict['chapters'].setdefault(
                    'file_name',
                    os.path.relpath(
                        inputdir.resolve() / mux_dict['chapters']['file_name'],
                        outputdir))
            except KeyError:
                pass
        else:
            combined_mux_dict = mux_dict

    for i, stream in enumerate(combined_mux_dict['streams']):
        stream['index'] = i

    skip_duplicate_streams(combined_mux_dict['streams'])

    combined_mux_dict.print_streams_summary()

    if not app.args.dry_run:
        combined_mux_dict.save()

    for i_inputdir, inputdir in enumerate(inputdirs):
        if i_inputdir:
            mux_dict = MmdemuxTask(inputdir / 'mux.json', in_tags=in_tags)
            if not mux_dict.skip:
                mux_dict['skip'] = f'Combined into {outputdir}'
                mux_dict.save()

def action_chop(inputfile, *, in_tags=None, chaps=None, chop_chaps=None):

    if isinstance(inputfile, str):
        inputfile = Path(inputfile)
    if isinstance(inputfile, os.PathLike):
        if inputfile.is_dir():
            inputdir = inputfile

            mux_dict = MmdemuxTask(inputdir / 'mux.json', in_tags=in_tags)
            chaps = Chapters.from_mkv_xml(inputdir / mux_dict['chapters']['file_name'], add_pre_gap=True)

            for stream_dict in sorted_stream_dicts(mux_dict['streams']):
                if stream_dict.skip:
                    continue
                stream_file_name = stream_dict['file_name']
                inputfile = inputdir / stream_file_name

                stream_file_base, stream_file_ext = my_splitext(stream_file_name)

                if (stream_dict.codec_type is CodecType.video
                    or stream_dict.codec_type is CodecType.audio):

                    action_chop(inputfile=inputfile,
                                in_tags=in_tags,
                                chaps=chaps, chop_chaps=chop_chaps)

                elif stream_dict.codec_type is CodecType.subtitle:
                    pass
                elif stream_dict.codec_type is CodecType.image:
                    pass
                else:
                    raise ValueError('Unsupported codec type %r' % (stream_dict.codec_type,))

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
            '.ogg',
    }:
        base2, ext2 = os.path.splitext(os.fspath(base))
        if ext2 in {
                '.ffv1',
                '.h264',
                '.h265',
                '.mpeg2',
                '.vorbis',
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
            raise OSError(errno.ENOENT, f'No such file: {out_file}')
        siz = out_file.stat().st_size
        app.log.debug(f'{out_file} has size {siz}')
        if siz == 0:
            raise OSError(errno.ENOENT, f'File empty: {out_file}')

class MmdemuxTask(collections.UserDict, json.JSONEncodable):

    mux_file_lock = None

    def __init__(self, /, mux_file_name, *, in_tags=None, load=True):
        self.mux_file_lock = threading.RLock()
        if mux_file_name is None:
            self.mux_file_name = None
            self.inputdir = Path('.')
        else:
            self.mux_file_name = Path(mux_file_name) if mux_file_name is not None else None
            self.inputdir = mux_file_name.parent

        if load:
            super().__init__()
            self.load(in_tags=in_tags)
        else:
            super().__init__({
                'streams': [],
                'chapters': {},
                #'tags': ...,
            })

    def __json_encode__(self):
        return self.data

    @property
    def skip(self):
        try:
            skip = self['skip']
        except KeyError:
            return False
        return skip or False


    def load(self, /, *, in_tags=None):
        mux_file = JsonFile.new_by_file_name(self.mux_file_name)
        self.data = mux_file.read_json()

        self.data['streams'] = [MmdemuxStream(e, parent=self) for e in self.data['streams']]

        stream_indexes = set([stream.get('index', None)
                              for stream in self.data['streams']])
        if None in stream_indexes and len(stream_indexes) == 1:
            # No indices; Populated them.
            for i, stream in enumerate(self.data['streams']):
                stream['index'] = i
        elif None in stream_indexes or len(stream_indexes) != len(self.data['streams']):
            raise ValueError('Not all stream\'s index is set. Please set all or none.')

        try:
            mux_tags = self['tags']
        except KeyError:
            if in_tags is not None:
                self['tags'] = mux_tags = copy.copy(in_tags)
        else:
            if not isinstance(mux_tags, AlbumTags):
                self['tags'] = mux_tags = AlbumTags(mux_tags)
            if in_tags is not None:
                mux_tags.update(in_tags)

    def save(self, /, *, mux_file_name=None):
        mux_file = JsonFile.new_by_file_name(mux_file_name or self.mux_file_name)

        with self.mux_file_lock:
            # Remove _temp
            mux_dict = copy.copy(self)
            mux_dict['streams'] = [copy.copy(stream_dict) for stream_dict in mux_dict['streams']]
            for stream_dict in mux_dict['streams']:
                stream_dict.pop('_temp', None)

            with mux_file.rename_temporarily(replace_ok=True):
                mux_file.write_json(mux_dict)

    def print_streams_summary(self, /, *, current_stream=None, current_stream_index=None):
        table = []
        if self.skip:
            print('NOTE: Globally set as skipped.')
        for stream_dict in sorted_stream_dicts(self['streams']):
            stream_index = stream_dict.pprint_index
            if stream_dict.skip:
                stream_index = f'(S){stream_index}'
            if stream_dict is current_stream or stream_dict.index == current_stream_index:
                stream_index = f'*{stream_index}'
            codec_type = stream_dict.codec_type
            extension = '->'.join([e for e in [
                my_splitext(stream_dict.get('original_file_name', ''))[1],
                my_splitext(stream_dict.get('file_name', ''))[1],]
                                   if e])
            language = isolang(stream_dict.get('language', 'und')).code3
            title = stream_dict.get('title', None)
            disposition = ', '.join(
                [k for k, v in stream_dict.get('disposition', {}).items() if v]
                + (['suffix=' + repr(stream_dict['external_stream_file_name_suffix'])]
                   if stream_dict.get('external_stream_file_name_suffix', None)
                   else [])
                + ([f'''*{stream_dict['subtitle_count']}''']
                   if stream_dict.get('subtitle_count', None)
                   else [])
            )
            original_source_description = stream_dict.get('original_source_description', None)
            try:
                size = stream_dict.file.getsize()
            except Exception as e:
                app.log.debug('Failed to get size from %s: %s', stream_dict, e)
                size = None
            table.append([stream_index, codec_type, original_source_description, size, extension, language, title, disposition])
        if table:
            print('')
            print(tabulate(table,
                           headers=[
                               'Index',
                               'Type',
                               'Original',
                               'Size',
                               'Extension',
                               'Language',
                               'Title',
                               'Disposition',
                           ],
                           colalign=[
                               'right',
                               'ĺeft',
                               'ĺeft',
                               'right',
                               'ĺeft',
                               'ĺeft',
                               'ĺeft',
                           ],
                           tablefmt='simple',
                           ))

def stream_dict_key(stream_dict):
    return (
        CodecType(stream_dict['codec_type']),
        not bool(stream_dict.get('disposition', {}).get('default', False)),  # default then non-default
        bool(stream_dict.get('disposition', {}).get('forced', False)),       # non-forced, then forced
        bool(stream_dict.get('disposition', {}).get('comment', False)),      # non-comment, then comment
        stream_dict.get('index', None),
    )

def sorted_stream_dicts(stream_dicts):
    return sorted(
        stream_dicts,
        key=stream_dict_key)

@functools.total_ordering
class MmdemuxStream(collections.UserDict, json.JSONEncodable):

    def __init__(self, /, stream_dict, parent):
        self.parent = parent
        super().__init__(stream_dict)

        self.setdefault('_temp', {})

        try:
            concat_streams = self['concat_streams']
        except KeyError:
            pass
        else:
            if concat_streams and not isinstance(concat_streams[0], MmdemuxStream):
                self['concat_streams'] = concat_streams = \
                    [MmdemuxStream(e, parent=self) for e in (concat_streams)]

    def new_sub_stream(self, sub_stream_index, sub_stream_file_name):
        sub_stream_dict = {k: v
                           for k, v in self.items()
                           if not (
                                   k.startswith('original_')
                                   or k in (
                                       'disposition',
                                       'start_time',
                                       'concat_streams',
                                       'estimated_duration',
                                   )
                           )}
        sub_stream_dict['index'] = sub_stream_index
        sub_stream_dict['file_name'] = os.fspath(sub_stream_file_name)
        return MmdemuxStream(sub_stream_dict, self)

    def replace_data(self, new_stream):
        self.data = copy.copy(new_stream.data)
        try:
            concat_streams = self['concat_streams']
        except KeyError:
            pass
        else:
            for sub_stream in concat_streams:
                sub_stream.parent = self
        self.on_data_changed()
        for attr in (
                'file',
        ):
            try:
                setattr(self, '_' + attr, getattr(new_stream, '_' + attr))
            except AttributeError:
                pass

    def on_data_changed(self):
        self.on_file_name_changed()

    def on_file_name_changed(self):
        for attr in (
                'file',
        ):
            try:
                delattr(self, attr)
            except AttributeError:
                pass

    def __setitem__(self, name, value):
        if name in {'file_name'}:
            try:
                if type(value) is str and self.get('file_name', None) == value:
                    return
            except AttributeError:
                pass
            ret = super().__setitem__(name, value)
            self.on_file_name_changed()
        else:
            ret = super().__setitem__(name, value)
        return ret

    def __delitem__(self, name):
        ret = super().__delitem__(name)
        if name == 'file_name':
            self.on_file_name_changed()
        return ret

    def __json_encode__(self):
        try:
            return self._data_backup
        except AttributeError:
            return self.data

    def save(self, /):
        with self.mux_dict.mux_file_lock:
            try:
                del self._data_backup
            except AttributeError:
                has_backup = False
            else:
                has_backup = True
        self.parent.save()
        if has_backup:
            _data_backup = copy.copy(self.data)
            with self.mux_dict.mux_file_lock:
                self._data_backup = _data_backup

    def is_hdr(self):
        if self.codec_type is not CodecType.video:
            return False
        ffprobe_stream_json, = self.file.ffprobe_dict['streams']
        color_transfer = ffprobe_stream_json.get('color_transfer', '')
        if any(v in color_transfer
               for v in hdr_color_transfer_stems):
            return True
        return False

    file = propex(
        name='file',
        type=propex.test_isinstance(File))

    @file.initter
    def file(self):
        cls = {
            CodecType.video: MovieFile,
            CodecType.audio: SoundFile,
            CodecType.subtitle: SubtitleFile,
            CodecType.image: ImageFile,
        }[self.codec_type]
        return cls.new_by_file_name(self.path)

    def __str__(self):
        orig_stream_file_name = self.get('original_file_name', self['file_name'])
        desc = '{codec_type} stream #{index}: title={title!r}, language={language}, disposition=({disposition}), ext={orig_ext}'.format(
            codec_type=str(self.codec_type).title(),
            index=self.pprint_index,
            title=self.get('title', None),
            language=isolang(self.get('language', 'und')),
            disposition=', '.join(k for k, v in self.get('disposition', {}).items() if v),
            orig_ext=my_splitext(orig_stream_file_name)[1],
        )
        external_stream_file_name_suffix = self.get('external_stream_file_name_suffix', None)
        if external_stream_file_name_suffix:
            desc += ', suffix={external_stream_file_name_suffix}'.format(
                external_stream_file_name_suffix=external_stream_file_name_suffix,
            )
        return desc

    key = stream_dict_key

    def __eq__(self, other):
        if not isinstance(other, MmdemuxStream):
            return NotImplemented
        return self.key() == other.key()

    def __lt__(self, other):
        if not isinstance(other, MmdemuxStream):
            return NotImplemented
        return self.key() < other.key()

    @property
    def mux_dict(self):
        parent = self.parent
        if isinstance(parent, MmdemuxTask):
            return parent
        return parent.mux_dict

    @property
    def inputdir(self):
        return self.parent.inputdir

    @property
    def is_sub_stream(self):
        parent = self.parent
        return isinstance(parent, MmdemuxStream)

    @property
    def skip(self):
        try:
            skip = self['skip']
        except KeyError:
            return False
        return skip or False

    @property
    def pprint_index(self):
        s = str(self.index)
        if self.is_sub_stream:
            s = f'{self.parent.pprint_index}.{s}'
        return s

    @property
    def index(self):
        try:
            return int(self['index'])
        except KeyError:
            return None

    @property
    def file_name(self):
        try:
            return Path(self['file_name'])
        except KeyError:
            raise AttributeError

    @property
    def path(self):
        return self.inputdir / self.file_name

    @property
    def codec_type(self):
        try:
            return CodecType(self['codec_type'])
        except KeyError:
            raise AttributeError

    @property
    def language(self):
        try:
            return isolang(self['language'])
        except KeyError:
            return isolang('und')

    @property
    def framerate(self):
        try:
            return FrameRate(self['framerate'])
        except KeyError:
            raise AttributeError

    @property
    def field_order(self):
        try:
            return self['field_order']
        except KeyError:
            raise AttributeError

    @contextlib.contextmanager
    def two_stage_commit_context(self):
        mux_dict = self.mux_dict
        if mux_dict is None or getattr(self, '_data_backup', None) is not None:
            yield
        else:
            _data_backup = copy.copy(self.data)
            with mux_dict.mux_file_lock:
                self._data_backup = _data_backup
            try:
                yield
            finally:
                with mux_dict.mux_file_lock:
                    del self._data_backup

    @property
    def estimated_duration(self):
        try:
            estimated_duration = self['estimated_duration']
        except KeyError:
            pass
        else:
            estimated_duration = AnyTimestamp(estimated_duration)
            if estimated_duration >= 0.0:
                return estimated_duration

        estimated_duration = estimate_stream_duration(inputfile=self.file)
        if estimated_duration is not None:
            return estimated_duration

        if not self.is_sub_stream:

            try:
                estimated_duration = self.mux_dict['estimated_duration']
            except KeyError:
                pass
            else:
                estimated_duration = AnyTimestamp(estimated_duration)
                if estimated_duration >= 0.0:
                    return estimated_duration

        return None

    def identifying_characteristics(self, mkvmerge=False):
        stream_characteristics = collections.OrderedDict()
        stream_characteristics['type'] = self.codec_type
        stream_characteristics['language'] = self.language
        stream_title = self.get('title', None)

        if self.codec_type is CodecType.video:
            if False:  # TODO
                video_angle += 1
                if False and video_angle > 1:
                    stream_characteristics['angle'] = video_angle

        elif self.codec_type is CodecType.subtitle:
            disposition = [
                d for d in (
                    'hearing_impaired',
                    'visual_impaired',
                    'karaoke',
                    'dub',
                    'clean_effects',
                    'lyrics',
                    'comment',
                    'forced',
                    'closed_caption',
                )
                if self['disposition'].get(d, None)]
            if disposition:
                stream_characteristics['disposition'] = '+'.join(disposition)

        if not mkvmerge:
            # TODO remove mkvmerge distinction!

            if self.codec_type is CodecType.audio:
                if self['disposition'].get('comment', None):
                    if stream_title is None:
                        stream_title = 'Commentary'
                elif self['disposition'].get('karaoke', None):
                    if stream_title is None:
                        stream_title = 'Karaoke'
                elif self['disposition'].get('dub', None):
                    if stream_title is None:
                        stream_title = 'Dub'
                elif self['disposition'].get('clean_effects', None):
                    if stream_title is None:
                        stream_title = 'Clean Effects'
                elif self['disposition'].get('original', None):
                    if stream_title is None:
                        stream_title = 'Original'
                elif app.args.audio_track_titles:
                    if stream_title is None:
                        stream_title = self.language.name

            if self.codec_type is CodecType.subtitle:
                if app.args.external_subtitles and my_splitext(self['file_name'])[1] != '.vtt':
                    stream_characteristics += ('external',)
                    try:
                        stream_characteristics += (
                            ('suffix', self['external_stream_file_name_suffix']),
                        )
                    except KeyError:
                        pass

        if stream_title is not None:
            stream_characteristics['title'] = stream_title

        return stream_characteristics

    def optimize(self, /, *, target_codec_names, stats):
        stream_dict = self
        with self.two_stage_commit_context():

            temp_files = []

            if stream_dict.skip:
                app.log.verbose('Stream #%s SKIP', stream_dict.pprint_index)
                return

            def done_optimize_iter(*, new_stream, do_skip=False):
                nonlocal temp_files
                nonlocal stream_dict
                nonlocal stream_file_base
                nonlocal stream_file_ext

                if do_skip:
                    stream_dict['skip'] = do_skip
                    app.log.info('Stream #%s %s: setting to be skipped', stream_dict.pprint_index, stream_dict.file_name)
                elif 'concat_streams' in new_stream:
                    # this iteration was to split into sub streams
                    stream_dict.replace_data(new_stream)
                else:
                    test_out_file(new_stream.path)
                    assert new_stream.path != stream_dict.path
                    temp_files.append(stream_dict.path)
                    new_stream.setdefault('original_file_name', stream_dict['file_name'])
                    stream_dict.replace_data(new_stream)
                    stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)
                if not app.args.dry_run:
                    stream_dict.save()
                    if not app.args.save_temps:
                        for file_name in temp_files:
                            os.unlink(file_name)
                        temp_files = []
                if app.args.step:
                    app.log.warning('Step done; Exit.')
                    exit(0)

            do_skip = False
            stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)

            if stream_dict.get('optimized', False):
                app.log.verbose('Stream #%s %s [%s] OPTIMIZED', stream_dict.pprint_index, stream_file_ext, stream_dict.language)
                return

            expected_framerate = None
            while True:

                new_stream = copy.copy(stream_dict)

                if stream_dict.codec_type is CodecType.video:

                    if 'concat_streams' in stream_dict:
                        del new_stream['concat_streams']

                        threads = []
                        for sub_stream_dict in stream_dict['concat_streams']:
                            future = slurm_executor.submit(
                                sub_stream_dict.optimize,
                                stats=stats,
                                target_codec_names=target_codec_names)
                            threads.append(future)

                        exc = None
                        for future in concurrent.futures.as_completed(threads):
                            try:
                                future.result()
                            except BaseException as e:
                                exc = e
                        if exc:
                            raise exc

                        sub_stream0 = stream_dict['concat_streams'][0]

                        new_stream_file_ext = my_splitext(sub_stream0['file_name'])[1]
                        new_stream['file_name'] = stream_file_base + new_stream_file_ext
                        app.log.verbose('Stream #%s concat -> %s', stream_dict.pprint_index, new_stream.file_name)

                        safe_concat = False
                        concat_list_file = ffmpeg.ConcatScriptFile(new_stream.inputdir / f'{new_stream.file_name}.concat.txt')
                        concat_list_file.files += [
                            concat_list_file.File(
                                sub_stream_dict['file_name'] if safe_concat else (new_stream.inputdir / sub_stream_dict['file_name']).resolve())
                            for sub_stream_dict in stream_dict['concat_streams']]
                        if not app.args.dry_run:
                            concat_list_file.create()

                        try:
                            new_stream['framerate'] = sub_stream0['framerate']
                        except KeyError:
                            sub_stream0_ffprobe_stream_json, = sub_stream0.file.ffprobe_dict['streams']

                            try:
                                sub_stream0_mediainfo_track_dict, = [e
                                                                     for e in sub_stream0.file.mediainfo_dict['media']['track']
                                                                     if e['@type'] != 'General']
                            except ValueError:
                                raise AssertionError('Expected a single mediainfo track: {!r}'.format(sub_stream0.file.mediainfo_dict['media']['track']))
                            assert sub_stream0_mediainfo_track_dict['@type'] == 'Video', 'Expected a mediainfo Video track: {!r}'.format(sub_stream0_mediainfo_track_dict)
                            assert CodecType(sub_stream0_mediainfo_track_dict['@type']) is sub_stream0.codec_type, f'Stream #{sub_stream0.pprint_index} has codec type {sub_stream0.codec_type} but mediainfo track has {sub_stream0_mediainfo_track_dict["@type"]}'

                            sub_stream0_field_order, sub_stream0_input_framerate, sub_stream0_framerate = analyze_field_order_and_framerate(
                                stream_dict=sub_stream0,
                                stream_file=sub_stream0.file,
                                ffprobe_stream_json=sub_stream0_ffprobe_stream_json,
                                mediainfo_track_dict=sub_stream0_mediainfo_track_dict)

                            assert sub_stream0_input_framerate or sub_stream0_framerate
                            new_stream['framerate'] = sub_stream0['framerate'] = str(sub_stream0_input_framerate or sub_stream0_framerate)
                        try:
                            new_stream['field_order'] = sub_stream0['field_order']
                        except KeyError:
                            try:
                                del new_stream['field_order']
                            except KeyError:
                                pass

                        # Concat
                        ffmpeg_concat_args = []
                        with perfcontext('Concat %s w/ ffmpeg' % (new_stream.file_name,), log=True):
                            cwd = concat_list_file.file_name.parent  # Certain characters (like '?') confuse the concat protocol
                            ffmpeg_args = [] + default_ffmpeg_args
                            try:
                                ffmpeg_args += [
                                    '-r', new_stream['framerate'],
                                ]
                            except KeyError:
                                pass
                            ffmpeg_args += [
                                '-f', 'concat', '-safe', 1 if safe_concat else 0,
                            ] + ffmpeg.input_args(concat_list_file.file_name.relative_to(cwd)) + [
                                '-codec', 'copy',
                                ] + ffmpeg_concat_args + [
                                '-start_at_zero',
                                '-f', ext_to_container(new_stream.file_name),
                                new_stream.path.relative_to(cwd),
                                ]
                            ffmpeg(*ffmpeg_args,
                                   cwd=cwd,
                                   progress_bar_max=stream_dict.estimated_duration,
                                   progress_bar_title=f'Concat {stream_dict.codec_type} stream #{stream_dict.pprint_index} w/ ffmpeg',
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)

                        temp_files += [sub_stream_dict.path
                                       for sub_stream_dict in stream_dict['concat_streams']]

                        done_optimize_iter(new_stream=new_stream)
                        continue

                    limit_duration = getattr(app.args, 'limit_duration', None)

                    try:
                        stream_dict.file.duration = float(ffmpeg.Timestamp(stream_dict.file.ffprobe_dict['format']['duration']))
                    except KeyError:
                        try:
                            stream_dict.file.duration = float(AnyTimestamp(self.mux_dict['estimated_duration']))
                        except KeyError:
                            pass
                    ffprobe_stream_json, = stream_dict.file.ffprobe_dict['streams']
                    stream_codec_name = ffprobe_stream_json['codec_name']
                    app.log.debug('stream_codec_name=%r', stream_codec_name)

                    if stream_codec_name in target_codec_names:
                        app.log.verbose('Stream #%s %s [%s] OK', stream_dict.pprint_index, stream_file_ext, stream_dict.language)
                        break

                    try:
                        mediainfo_track_dict, = [e
                                                 for e in stream_dict.file.mediainfo_dict['media']['track']
                                                 if e['@type'] == 'Video']
                    except ValueError:
                        raise AssertionError('Expected a single Video mediainfo track: {!r}'.format(stream_dict.file.mediainfo_dict['media']['track']))

                    field_order, input_framerate, framerate = analyze_field_order_and_framerate(
                        stream_dict=stream_dict,
                        stream_file=stream_dict.file,
                        ffprobe_stream_json=ffprobe_stream_json,
                        mediainfo_track_dict=mediainfo_track_dict)
                    if framerate:
                        new_stream['framerate'] = stream_dict['framerate'] = str(framerate)
                    if field_order:
                        new_stream['field_order'] = stream_dict['field_order'] = field_order

                    if expected_framerate is not None:
                        assert framerate == expected_framerate, (framerate, expected_framerate)
                    display_aspect_ratio = Ratio(stream_dict['display_aspect_ratio'])

                    lossless = False

                    if stream_file_base.upper().endswith('.MVC') and app.args.stereo_3d_mode is not None:
                        stereo_3d_mode = app.args.stereo_3d_mode
                        if stereo_3d_mode is Stereo3DMode.hdmi_frame_packing:
                            # Start with SBS, will reposition later
                            stereo_3d_mode = Stereo3DMode.full_side_by_side
                        if stereo_3d_mode is Stereo3DMode.multiview_encoding:
                            raise NotImplementedError('MVC')  # TODO MVC->MVC may undergo modifications below that would lose the MVC encoding
                        # .MVC -> FRIMDecode -> SBS/TAB/ALT
                        assert field_order == 'progressive'

                        assert ffprobe_stream_json['pix_fmt'] == 'yuv420p'
                        frimdecode_fmt = 'i420'
                        if stream_dict.is_hdr():
                            raise NotImplementedError('HDR support not implemented')
                        ffmpeg_pix_fmt = 'yuv420p'

                        new_stream_file_ext = pick_lossless_codec_ext(stream_dict)
                        lossless = True
                        new_stream_file_name_base = stream_file_base[0:-4]  # remove .MVC
                        if '3D' not in new_stream_file_name_base.upper().split('.'):
                            new_stream_file_name_base += '.3D'
                        new_stream_file_name_base += stereo_3d_mode.exts[0]
                        new_stream['file_name'] = new_stream_file_name_base + new_stream_file_ext
                        app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                        frimdecode_args = [
                            '-i:mvc', stream_dict.path,
                            {
                                Stereo3DMode.half_side_by_side: '-sbs',
                                Stereo3DMode.full_side_by_side: '-sbs',
                                Stereo3DMode.half_top_and_bottom: '-tab',
                                Stereo3DMode.full_top_and_bottom: '-tab',
                                Stereo3DMode.alternate_frame: '-alt',
                            }[app.args.stereo_3d_mode],
                            '-o', '-',
                        ]

                        ffmpeg_enc_args = [] + default_ffmpeg_args
                        force_input_framerate = getattr(app.args, 'force_input_framerate', None)
                        assert force_input_framerate or input_framerate or framerate
                        expected_framerate = force_input_framerate or input_framerate or framerate
                        if stereo_3d_mode is Stereo3DMode.alternate_frame:
                            expected_framerate *= 2
                        ffmpeg_enc_args += [
                            '-r', expected_framerate,
                        ]
                        new_stream['framerate'] = str(expected_framerate)
                        ffmpeg_enc_args += [
                            '-pix_fmt', ffmpeg_pix_fmt,
                        ]
                        if stereo_3d_mode in (
                                Stereo3DMode.half_side_by_side,
                                Stereo3DMode.full_side_by_side,
                        ):
                            ffmpeg_enc_args += [
                                '-s:v', '%dx%d' % (ffprobe_stream_json['width'] * 2, ffprobe_stream_json['height']),
                            ]
                        elif stereo_3d_mode in (
                                Stereo3DMode.half_top_and_bottom,
                                Stereo3DMode.full_top_and_bottom,
                        ):
                            ffmpeg_enc_args += [
                                '-s:v', '%dx%d' % (ffprobe_stream_json['width'], ffprobe_stream_json['height'] * 2),
                            ]
                        elif stereo_3d_mode in (
                                Stereo3DMode.alternate_frame,
                        ):
                            pass
                        else:
                            raise NotImplementedError(stereo_3d_mode)
                        ffmpeg_enc_args += [
                            '-f', 'rawvideo',
                            '-i', 'pipe:0',
                        ]
                        if stereo_3d_mode is Stereo3DMode.full_side_by_side:
                            new_stream['display_aspect_ratio'] = str(Ratio(new_stream['display_aspect_ratio']) * 2)
                        elif stereo_3d_mode is Stereo3DMode.half_side_by_side:
                            new_stream['display_aspect_ratio'] = str(Ratio(new_stream['display_aspect_ratio']) * 2)
                            new_stream['pixel_aspect_ratio'] = str(Ratio(new_stream['pixel_aspect_ratio']) * 2)
                            ffmpeg_enc_args += [
                                '-vf', 'scale=%d:%d' % (ffprobe_stream_json['width'], ffprobe_stream_json['height']),
                            ]
                        elif stereo_3d_mode is Stereo3DMode.full_top_and_bottom:
                            new_stream['display_aspect_ratio'] = str(Ratio(new_stream['display_aspect_ratio']) / 2)
                        elif stereo_3d_mode is Stereo3DMode.half_top_and_bottom:
                            new_stream['display_aspect_ratio'] = str(Ratio(new_stream['display_aspect_ratio']) / 2)
                            new_stream['pixel_aspect_ratio'] = str(Ratio(new_stream['pixel_aspect_ratio']) / 2)
                            ffmpeg_enc_args += [
                                '-vf', 'scale=%d:%d' % (ffprobe_stream_json['width'], ffprobe_stream_json['height']),
                            ]
                        codec = ext_to_codec(new_stream_file_ext,
                                             lossless=lossless,
                                             hdr=stream_dict.is_hdr())
                        ffmpeg_enc_args += [
                            '-codec:v', codec,
                        ] + ext_to_codec_args(new_stream_file_ext,
                                              codec=codec,
                                              lossless=lossless)
                        ffmpeg_enc_args += [
                            '-f', ext_to_container(new_stream_file_ext),
                            new_stream.path,
                        ]

                        with perfcontext('MVC -> FRIMDecode -> SBS/TAB/ALT', log=True):
                            p1 = FRIMDecode.popen(*frimdecode_args,
                                                  stdout=subprocess.PIPE,
                                                  stderr=open('/dev/stdout', 'wb'),
                                                  dry_run=app.args.dry_run)
                            try:
                                p2 = ffmpeg.popen(*ffmpeg_enc_args,
                                                  stdin=p1.stdout,
                                                  # TODO progress_bar_max=stream_dict.estimated_duration,
                                                  # TODO progress_bar_title=f'MVC->{stereo_3d_mode.exts[0]} {stream_dict.codec_type} stream {stream_dict.pprint_index} w/ FRIMDecode',
                                                  dry_run=app.args.dry_run,
                                                  y=app.args.yes)
                            finally:
                                if not app.args.dry_run:
                                    p1.stdout.close()
                            if not app.args.dry_run:
                                p2.communicate()
                                #assert p1.returncode == 0, f'FRIMDecode returned {p1.returncode}'
                                assert p2.returncode == 0, f'ffmpeg returned {p2.returncode}'

                        done_optimize_iter(new_stream=new_stream)
                        continue

                    if field_order == '23pulldown':
                        new_stream['field_order'] = 'progressive'

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
                            new_stream['file_name'] = new_stream_file_name_base + new_stream_file_ext
                            app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                            if stream_file_ext in ('.y4m', '.yuv'):
                                assert framerate == FrameRate(30000, 1001)
                                framerate = FrameRate(24000, 1001)
                                app.log.verbose('23pulldown y4m framerate correction: %s', framerate)

                            ffmpeg_dec_args = []
                            if stream_file_ext in ('.y4m', '.yuv'):
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
                                ffmpeg_dec_args += ffmpeg.input_args(stream_dict.file)
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
                                if stream_dict.is_hdr():
                                    raise NotImplementedError('HDR support not implemented')
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
                            new_stream['framerate'] = str(framerate)
                            #yuvkineco_cmd += ['-n', '2']  # Noise level (default: 10)
                            if deinterlace_using_ffmpeg:
                                yuvkineco_cmd += ['-i', '-1']  # Disable deinterlacing
                            yuvkineco_cmd += ['-C', stream_dict.inputdir / (new_stream_file_name_base + '.23c')]  # pull down cycle list file

                            if stream_dict.is_hdr():
                                raise NotImplementedError('HDR support not implemented')
                            codec = ext_to_codec(new_stream_file_ext,
                                                 lossless=lossless,
                                                 hdr=stream_dict.is_hdr())
                            ffmpeg_enc_args = [
                                '-i', 'pipe:0',
                                '-codec:v', codec,
                            ] + ext_to_codec_args(new_stream_file_ext,
                                                  codec=codec,
                                                  lossless=lossless) + [
                                '-f', ext_to_container(new_stream_file_ext),
                                new_stream.path,
                            ]

                            with perfcontext('Pullup w/ -> .y4m' + (' -> yuvcorrect' if use_yuvcorrect else '') + ' -> yuvkineco -> .ffv1', log=True):
                                if ffmpeg_dec_args:
                                    p1 = ffmpeg.popen(*ffmpeg_dec_args,
                                                      stdout=subprocess.PIPE,
                                                      dry_run=app.args.dry_run)
                                    p1_out = p1.stdout
                                elif not app.args.dry_run:
                                    p1_out = stream_dict.file.fp = stream_dict.file.pvopen(mode='r')
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
                                                              # TODO progress_bar_max=stream_dict.estimated_duration,
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
                                            stream_dict.file.close()
                                if not app.args.dry_run:
                                    p4.communicate()
                                    assert p4.returncode == 0

                            expected_framerate = framerate

                            done_optimize_iter(new_stream=new_stream)
                            continue

                        elif pullup_tool == 'ffmpeg':
                            # -> ffmpeg -> .ffv1

                            decimate_using_ffmpeg = True
                            decimate_using_ffmpeg = False

                            if stream_dict.is_hdr():
                                raise NotImplementedError('HDR support not implemented')
                            new_stream_file_ext = '.ffv1.mkv'
                            lossless = True
                            new_stream['file_name'] = '.'.join(e for e in stream_file_base.split('.')
                                                            if e not in ('23pulldown',)) \
                                + '.ffmpeg-pullup' + new_stream_file_ext
                            app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                            if stream_file_ext in ('.y4m', '.yuv'):
                                assert framerate == FrameRate(30000, 1001)
                                framerate = FrameRate(24000, 1001)
                                app.log.verbose('23pulldown %s framerate correction: %s', stream_file_ext, framerate)

                            orig_framerate = framerate * 30 / 24

                            ffmpeg_args = [] + default_ffmpeg_args
                            force_input_framerate = getattr(app.args, 'force_input_framerate', None)
                            if force_input_framerate:
                                ffmpeg_args += [
                                    '-r', force_input_framerate,
                                    ]
                            ffmpeg_args += ffmpeg.input_args(stream_dict.file)
                            codec = ext_to_codec(new_stream_file_ext,
                                                 lossless=lossless,
                                                 hdr=stream_dict.is_hdr())
                            ffmpeg_args += [
                                '-vf', f'fieldmatch,yadif,decimate' if decimate_using_ffmpeg else f'pullup,fps={framerate}',
                                '-r', framerate,
                                '-codec:v', codec,
                                ] + ext_to_codec_args(new_stream_file_ext,
                                                      codec=codec,
                                                      lossless=lossless)
                            if limit_duration:
                                ffmpeg_args += ['-t', ffmpeg.Timestamp(limit_duration)]
                            ffmpeg_args += [
                                '-f', ext_to_container(new_stream_file_ext),
                                new_stream.path,
                            ]

                            with perfcontext('Pullup w/ -> ffmpeg -> .ffv1', log=True):
                                ffmpeg(*ffmpeg_args,
                                       slurm=app.args.slurm,
                                       #slurm_cpus_per_task=2, # ~230-240%
                                       progress_bar_max=stream_dict.estimated_duration,
                                       progress_bar_title=f'Pullup {stream_dict.codec_type} stream #{stream_dict.pprint_index} w/ ffmpeg',
                                       dry_run=app.args.dry_run,
                                       y=app.args.yes)

                            expected_framerate = framerate

                            done_optimize_iter(new_stream=new_stream)
                            continue

                        elif pullup_tool == 'mencoder':
                            # -> mencoder -> .ffv1

                            if True:
                                # ffprobe and mediainfo don't agree on resulting frame rate.
                                new_stream_file_ext = '.ffv1.mkv'
                            else:
                                # mencoder seems to mess up the encoder frame rate in avi (total-frames/1), ffmpeg's r_frame_rate seems accurate.
                                new_stream_file_ext = '.ffv1.avi'
                            new_stream['file_name'] = '.'.join(e for e in stream_file_base.split('.')
                                                            if e not in ('23pulldown',)) \
                                + '.mencoder-pullup' + new_stream_file_ext
                            app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                            if stream_dict.is_hdr():
                                raise NotImplementedError('HDR support not implemented')
                            mencoder_args = [
                                '-aspect', display_aspect_ratio,
                                stream_dict.path,
                                '-ofps', framerate,
                                '-vf', 'pullup,softskip,harddup',
                                #'-ovc', 'lavc', '-lavcopts', 'vcodec=ffv1:slices=12:threads=4',
                                '-ovc', 'lavc', '-lavcopts', 'vcodec=ffv1:threads=4',
                                '-of', 'lavf', '-lavfopts', 'format=%s' % (ext_to_mencoder_libavcodec_format(new_stream_file_ext),),
                                '-o', new_stream.path,
                            ]
                            expected_framerate = framerate
                            with perfcontext('Pullup w/ mencoder', log=True):
                                mencoder(*mencoder_args,
                                         #slurm=app.args.slurm,
                                         dry_run=app.args.dry_run)

                            done_optimize_iter(new_stream=new_stream)
                            continue

                        else:
                            raise NotImplementedError(pullup_tool)

                    ffprobe_stream_json = stream_dict.file.ffprobe_dict['streams'][0]
                    app.log.debug(ffprobe_stream_json)

                    #mediainfo_duration = qip.utils.Timestamp(mediainfo_track_dict['Duration'])
                    mediainfo_width = int(mediainfo_track_dict['Width'])
                    mediainfo_height = int(mediainfo_track_dict['Height'])

                    if not stream_dict.is_sub_stream and stream_dict.mux_dict.get('chapters', None):
                        chaps = list(Chapters.from_mkv_xml(stream_dict.inputdir / stream_dict.mux_dict['chapters']['file_name'], add_pre_gap=True))
                    else:
                        chaps = []
                    parallel_chapters = app.args.parallel_chapters \
                        and len(chaps) > 1 \
                        and chaps[0].start == 0

                    extra_args = []
                    video_filter_specs = []

                    new_stream_file_name_base = stream_file_base

                    force_constant_framerate = app.args.force_constant_framerate

                    if field_order == 'progressive':
                        pass
                    elif field_order in ('auto-interlaced',):
                        video_filter_specs.append('yadif=mode=send_frame:parity=auto:deint=interlaced')
                        new_stream['field_order'] = 'progressive'
                    elif field_order in ('tt', 'tb'):
                        # ‘tt’ Interlaced video, top field coded and displayed first
                        # ‘tb’ Interlaced video, top coded first, bottom displayed first
                        # https://ffmpeg.org/ffmpeg-filters.html#yadif
                        video_filter_specs.append('yadif=parity=tff')
                        new_stream['field_order'] = 'progressive'
                    elif field_order in ('bb', 'bt'):
                        # ‘bb’ Interlaced video, bottom field coded and displayed first
                        # ‘bt’ Interlaced video, bottom coded first, top displayed first
                        # https://ffmpeg.org/ffmpeg-filters.html#yadif
                        video_filter_specs.append('yadif=parity=bff')
                        new_stream['field_order'] = 'progressive'
                    elif filters == '23pulldown':
                        raise NotImplementedError('pulldown should have been corrected already using yuvkineco or mencoder!')
                        force_constant_framerate = True  # fps
                        video_filter_specs.append('pullup')
                        new_stream['field_order'] = 'progressive'
                    else:
                        raise NotImplementedError(field_order)

                    if not stream_dict.is_sub_stream and app.args.crop in (Auto, True):
                        if any(new_stream_file_name_base.upper().endswith(m)
                               for m in (
                                       ()
                                       + Stereo3DMode.half_side_by_side.exts
                                       + Stereo3DMode.full_side_by_side.exts
                                       + Stereo3DMode.half_top_and_bottom.exts
                                       + Stereo3DMode.full_top_and_bottom.exts
                                       #+ Stereo3DMode.alternate_frame.exts
                                       + Stereo3DMode.multiview_encoding.exts
                                       + Stereo3DMode.hdmi_frame_packing.exts
                               )):
                            stream_crop = False
                        elif getattr(app.args, 'crop_wh', None) is not None:
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
                                        input_file=stream_dict.path,
                                        skip_frame_nokey=app.args.cropdetect_skip_frame_nokey,
                                        # Seek 5 minutes in
                                        #cropdetect_seek=max(0.0, min(300.0, float(mediainfo_duration) - 300.0)),
                                        cropdetect_seek=app.args.cropdetect_seek,
                                        cropdetect_duration=app.args.cropdetect_duration,
                                        cropdetect_limit=app.args.cropdetect_limit,
                                        cropdetect_round=app.args.cropdetect_round,
                                        video_filter_specs=video_filter_specs,
                                        dry_run=app.args.dry_run)
                            if stream_crop_whlt and (stream_crop_whlt[0], stream_crop_whlt[1]) == (mediainfo_width, mediainfo_height):
                                stream_crop_whlt = None
                            new_stream.setdefault('original_crop', stream_crop_whlt)
                            if stream_crop_whlt:
                                new_stream.setdefault('original_display_aspect_ratio', new_stream['display_aspect_ratio'])
                                pixel_aspect_ratio = Ratio(new_stream['pixel_aspect_ratio'])  # invariable
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
                                app.log.warning('TODO Fix parallel_chapters + crop') ; parallel_chapters = False  # XXXJST TODO!
                                # extra_args += ['-aspect', XXX]
                                new_stream['display_aspect_ratio'] = str(display_aspect_ratio)

                    if any(new_stream_file_name_base.upper().endswith(m)
                           for m in Stereo3DMode.full_side_by_side.exts):
                        # https://etmriwi.home.xs4all.nl/forum/hdmi_spec1.4a_3dextraction.pdf
                        if app.args.stereo_3d_mode is Stereo3DMode.hdmi_frame_packing:
                            new_stream_file_name_base = os.path.splitext(new_stream_file_name_base)[0]
                            if '3D' not in new_stream_file_name_base.upper().split('.'):
                                new_stream_file_name_base += '.3D'
                            new_stream_file_name_base += Stereo3DMode.hdmi_frame_packing.exts[0]
                            if (mediainfo_width, mediainfo_height) == (2*1280, 720):
                                # 720p: 1280x720@60 -> 1280x1470 w/ 30 active space in the middle
                                # Modeline "1280x1470@60" 148.5 1280 1390 1430 1650 1470 1475 1480 1500 +hsync +vsync
                                owidth, oheight, active_space = 1280, 720, 30
                                if framerate not in (FrameRate(60000,1000), FrameRate(60000, 1001)):
                                    raise NotImplementedError(f'720p HDMI frame packing at {framerate}fps')
                            elif (mediainfo_width, mediainfo_height) == (2*1920, 1080):
                                # 1080p: 1920x1080@24 -> 1920x2205 w/ 45 active space in the middle
                                # Modeline "1920x2205@24" 148.32 1920 2558 2602 2750 2205 2209 2214 2250 +hsync +vsync
                                owidth, oheight, active_space = 1920, 1080, 45
                                if framerate not in (FrameRate(24000,1000), FrameRate(24000, 1001)):
                                    raise NotImplementedError(f'1080p HDMI frame packing at {framerate}fps')
                            else:
                                raise NotImplementedError(f'HDMI frame packing for {mediainfo_width}x{mediainfo_height} SBS resolution')
                            # split[a][b]; [a]pad=1920:2205[ap]; [b]crop=1920:1080:0:1080[bc]; [ap][bc]overlay=0:1125
                            # The following rounds down the padding:
                            # video_filter_specs.append(f'split[a][b]; [a]crop={owidth}:{oheight}[ac]; [ac]pad={owidth}:{2*oheight+active_space}[ap]; [b]crop={owidth}:{oheight}:{owidth}:0[bc]; [ap][bc]overlay=0:{oheight+active_space}')
                            # 3-eyed version??:
                            # video_filter_specs.append(f'split[a][b]; [a]crop={owidth}:{oheight}[ac]; [ac]pad={owidth}:{2*oheight+active_space+1}[ap]; [b]crop={owidth}:{oheight}:{owidth}:0[bc]; [ap][bc]overlay=0:{oheight+active_space}[out]; [out]crop=w={owidth}:h={2*oheight+active_space}:exact=1')
                            video_filter_specs.append(f'stereo3d=sbsl:hdmi')
                            storage_aspect_ratio = Ratio(mediainfo_width, mediainfo_height)       # 3840:1080
                            display_aspect_ratio = Ratio(new_stream['display_aspect_ratio'])      # 32:9
                            pixel_aspect_ratio = display_aspect_ratio / storage_aspect_ratio      # 1:1
                            new_storage_aspect_ratio = Ratio(owidth, 2 * oheight + active_space)  # 1920:2205 => 128:147
                            display_aspect_ratio = pixel_aspect_ratio * new_storage_aspect_ratio  # 128:147
                            new_stream['display_aspect_ratio'] = str(display_aspect_ratio)

                    if stream_file_ext in still_image_exts:
                        if framerate == 1:
                            try:
                                framerate = {
                                    BroadcastFormat.NTSC: FrameRate(24000, 1001),
                                    BroadcastFormat.PAL: FrameRate(25000, 1000),
                                }[app.args.preferred_broadcast_format]
                            except KeyError:
                                pass
                            else:
                                app.log.warning('Selected %s (%.3f) fps for still image conversion based on %s preferred broadcast format', framerate, framerate, app.args.preferred_broadcast_format)
                        if framerate == 1:
                            raise ValueError('Please provide still image frame rate using --force-framerate or set --preferred-broadcast-format')
                        force_constant_framerate = True

                    if force_constant_framerate:
                        video_filter_specs.append(f'fps=fps={framerate}')

                    pad_video = app.args.pad_video
                    if pad_video is None:
                        if stream_file_ext in still_image_exts:
                            pad_video = 'clone'
                    if pad_video is None:
                        pass
                    elif pad_video == 'clone':
                        #video_filter_specs.append(f'tpad=stop_mode=clone:stop=-1')
                        estimated_duration = AnyTimestamp(stream_dict.mux_dict['estimated_duration'])
                        video_filter_specs.append(f'tpad=stop_mode=clone:stop_duration={float(estimated_duration)}')
                    elif pad_video == 'black':
                        video_filter_specs.append(f'tpad=stop_mode=color:stop=-1:color=black')
                    else:
                        raise NotImplementedError(pad_video)

                    if video_filter_specs:
                        extra_args += ['-filter:v', ','.join(video_filter_specs)]

                    lossless = False

                    if False and stream_dict.is_sub_stream:
                        new_stream_file_ext = '.ffv1.mkv'
                        if field_order == 'progressive':
                            app.log.verbose('Stream #%s %s [%s] OK', stream_dict.pprint_index, stream_file_ext, stream_dict.language)
                            break
                        new_stream['file_name'] = new_stream_file_name_base + '.progressive' + new_stream_file_ext
                    else:
                        new_stream_file_ext = '.ffv1.mkv' if app.args.ffv1 else '.vp9.ivf'
                        new_stream['file_name'] = new_stream_file_name_base + new_stream_file_ext
                    app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

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
                            if app.args.force_constant_framerate:
                                extra_args += ['-vsync', 'cfr']
                            else:
                                extra_args += ['-vsync', 'drop']

                    need_2pass = False
                    ffmpeg_conv_args = ffmpeg.Options()
                    codec = ext_to_codec(new_stream_file_ext,
                                         lossless=lossless,
                                         hdr=stream_dict.is_hdr())
                    ffmpeg_conv_args += [
                        '-codec:v', codec,
                    ]

                    if new_stream_file_ext == '.vp9.ivf':
                        # https://trac.ffmpeg.org/wiki/Encode/VP9

                        real_width, real_height = qwidth, qheight = mediainfo_width, mediainfo_height
                        if any(new_stream_file_name_base.upper().endswith(m)
                               for m in Stereo3DMode.full_side_by_side.exts + Stereo3DMode.half_side_by_side.exts):
                            real_width = qwidth // 2
                        elif any(new_stream_file_name_base.upper().endswith(m)
                                 for m in Stereo3DMode.full_top_and_bottom.exts + Stereo3DMode.half_top_and_bottom.exts):
                            real_height = qheight // 2
                        elif any(new_stream_file_name_base.upper().endswith(m)
                                 for m in Stereo3DMode.hdmi_frame_packing.exts):
                            if qheight == 2205:
                                real_height = 1080
                            elif qheight == 1470:
                                real_height = 720

                        # https://developers.google.com/media/vp9/settings/vod/
                        video_target_bit_rate = get_vp9_target_bitrate(
                            width=qwidth, height=qheight,
                            frame_rate=framerate,
                            )
                        video_target_bit_rate = int(video_target_bit_rate * 1.5)  # 1800 * 1.5 = 2700
                        video_target_quality = get_vp9_target_quality(
                            width=real_width, height=real_height,
                            frame_rate=framerate,
                            )
                        vp9_tile_columns, vp9_threads = get_vp9_tile_columns_and_threads(
                            width=qwidth, height=qheight,
                            )
                        if codec == 'libvpx-vp9':
                            # [libvpx-vp9 @ 0x55a6db68e900] Application has requested 24 threads. Using a thread count greater than 16 is not recommended.
                            vp9_threads = min(vp9_threads, 16)

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
                        ffmpeg_conv_args += ext_to_codec_args(new_stream_file_ext,
                                                              codec=codec,
                                                              lossless=lossless)

                    ffmpeg_conv_args += extra_args

                    ffmpeg_conv_args += get_hdr_codec_args(inputfile=stream_dict.file,
                                                           codec=codec,
                                                           ffprobe_stream_json=ffprobe_stream_json,
                                                           mediainfo_track_dict=mediainfo_track_dict)

                    safe_concat = False
                    if (parallel_chapters
                            and stream_file_ext in (
                                '.mpeg2', '.mpeg2.mp2v',  # Chopping using segment muxer is reliable (tested with mpeg2)
                                '.ffv1.mkv',
                                # '.vc1.avi',  # Stupidly slow (vc1 -> ffv1 @ 0.9x)
                                '.h264',
                                '.h265',
                            )):
                        #if app.args.force_constant_framerate:
                        #    raise NotImplementedError('--parallel-chapters and --force-constant-framerate')
                        if app.args.pad_video:
                            raise NotImplementedError('--parallel-chapters and --pad-video')
                        concat_list_file = ffmpeg.ConcatScriptFile(new_stream.inputdir / f'{new_stream.file_name}.concat.txt')
                        ffmpeg_concat_args = []
                        with perfcontext('Convert %s chapters to %s in parallel w/ ffmpeg' % (stream_file_ext, new_stream.file_name), log=True):
                            chapter_stream_file_ext = pick_lossless_codec_ext(stream_dict)
                            stream_chapter_file_name_pat = '%s-chap%%02d%s' % (stream_file_base.replace('%', '%%'),
                                                                               chapter_stream_file_ext.replace('%', '%%'))
                            new_stream_chapter_file_name_pat = '%s-chap%%02d%s' % (new_stream_file_name_base.replace('%', '%%'),
                                                                                   new_stream_file_ext.replace('%', '%%'))
                            threads = []

                            chapter_lossless = True
                            app.log.verbose('All chapters...')

                            assert 'concat_streams' not in new_stream
                            new_stream['file_name'] = stream_dict['file_name']  # Restore!
                            new_stream['concat_streams'] = []

                            stream_chapter_file_name_pat = \
                                chop_chapters(chaps=chaps,
                                              inputfile=stream_dict.file,
                                              chapter_file_ext=chapter_stream_file_ext,
                                              chapter_lossless=chapter_lossless,
                                              hdr=stream_dict.is_hdr())
                            stream_chapter_file_name_pat = os.fspath(
                                Path(stream_chapter_file_name_pat).relative_to(
                                    os.fspath(stream_dict.inputdir).replace('%', '%%')))

                            # Sometimes the last chapter is past the end
                            if len(chaps) > 1:
                                chap = chaps[-1]
                                stream_chapter_file_name = stream_chapter_file_name_pat % (chap.no,)
                                if not (stream_dict.inputdir / stream_chapter_file_name).exists():
                                    stream_chapter_file_name2 = stream_chapter_file_name_pat % (chaps[-2].no,)
                                    assert (stream_dict.inputdir / stream_chapter_file_name2).exists()
                                    app.log.warning('Stream #%s chapter %s not outputted!', stream_dict.pprint_index, chap)
                                    chaps.pop(-1)

                            for chap in chaps:
                                sub_stream = new_stream.new_sub_stream(chap.no,
                                                                        stream_chapter_file_name_pat % (chap.no,))
                                sub_stream['estimated_duration'] = str(chap.duration)
                                new_stream['concat_streams'].append(sub_stream)
                            done_optimize_iter(new_stream=new_stream)
                            continue

                    ffmpeg_args = [] + default_ffmpeg_args
                    force_input_framerate = getattr(app.args, 'force_input_framerate', None)
                    if force_input_framerate:
                        ffmpeg_args += [
                            '-r', force_input_framerate,
                            ]
                    ffmpeg_args += ffmpeg.input_args(stream_dict.file)
                    ffmpeg_args += ffmpeg_conv_args
                    if app.args.force_constant_framerate \
                            or stream_file_ext in still_image_exts:
                        ffmpeg_args += [
                            '-r', framerate,
                        ]
                    ffmpeg_args += [
                        '-f', ext_to_container(new_stream_file_ext), new_stream.path,
                        ]
                    if need_2pass or new_stream_file_ext in (
                            '.vp8.ivf',
                            '.vp9.ivf',
                            '.av1.ivf',
                            # '.ffv1.mkv',  # no need for better compression
                    ):
                        with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream.file_name), log=True):
                            ffmpeg.run2pass(*ffmpeg_args,
                                            slurm=app.args.slurm,
                                            progress_bar_max=stream_dict.estimated_duration,
                                            progress_bar_title=f'Convert {stream_dict.codec_type} stream {stream_dict.pprint_index} {stream_file_ext} -> {new_stream_file_ext} w/ ffmpeg',
                                            dry_run=app.args.dry_run,
                                            y=app.args.yes)
                    else:
                        with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream.file_name), log=True):
                            ffmpeg(*ffmpeg_args,
                                   progress_bar_max=stream_dict.estimated_duration,
                                   progress_bar_title=f'Convert {stream_dict.codec_type} stream {stream_dict.pprint_index} {stream_file_ext} -> {new_stream_file_ext} w/ ffmpeg',
                                   slurm=app.args.slurm,
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)
                    test_out_file(new_stream.path)

                    done_optimize_iter(new_stream=new_stream)
                    continue

                elif stream_dict.codec_type is CodecType.audio:

                    ok_exts = (
                            '.opus',
                            '.opus.ogg',
                            #'.mp3',
                            #'.flac',
                            )

                    stream_start_time = AnyTimestamp(stream_dict.get('start_time', 0))

                    if stream_file_ext in ok_exts \
                            and not stream_start_time:
                        app.log.verbose('Stream #%s %s [%s] OK', stream_dict.pprint_index, stream_file_ext, stream_dict.language)
                        break

                    try:
                        stream_dict.file.duration = float(ffmpeg.Timestamp(stream_dict.file.ffprobe_dict['format']['duration']))
                    except KeyError:
                        pass
                    app.log.debug(stream_dict.file.ffprobe_dict['streams'][0])
                    channels = stream_dict.file.ffprobe_dict['streams'][0]['channels']
                    channel_layout = stream_dict.file.ffprobe_dict['streams'][0].get('channel_layout', None)

                    # opusenc supports Wave, AIFF, FLAC, Ogg/FLAC, or raw PCM.
                    opusenc_formats = ('.wav', '.aiff', '.flac', '.ogg', '.pcm')
                    if stream_file_ext not in ok_exts + opusenc_formats \
                            or stream_start_time:
                        new_stream_file_ext = '.wav'
                        new_stream['file_name'] = stream_file_base + new_stream_file_ext
                        app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                        with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream.file_name), log=True):
                            ffmpeg_args = default_ffmpeg_args + [
                            ] + ffmpeg.input_args(stream_dict.file) + [
                                # '-channel_layout', channel_layout,
                                ]
                            ffmpeg_args += [
                                '-start_at_zero',
                                #'-codec', 'pcm_s16le',
                            ]
                            # See ffmpeg -sample_fmts
                            audio_samplefmt = stream_dict.file.ffprobe_dict['streams'][0]['sample_fmt']
                            if audio_samplefmt in ('s16', 's16p'):
                                ffmpeg_args += [
                                    '-codec', 'pcm_s16le',
                                ]
                            elif audio_samplefmt in ('s32', 's32p'):
                                bits_per_raw_sample = int(stream_dict.file.ffprobe_dict['streams'][0]['bits_per_raw_sample'])
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
                                    bits_per_raw_sample = int(stream_dict.file.ffprobe_dict['streams'][0]['bits_per_raw_sample'])
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
                                stream_start_time = qip.utils.Timestamp(0)
                                new_stream.setdefault('original_start_time', stream_dict['start_time'])
                                new_stream['start_time'] = str(stream_start_time)
                            if False:
                                # opusenc doesn't like RF64 headers!
                                # Other option is to pipe wav from ffmpeg to opusenc
                                ffmpeg_args += [
                                    '-rf64', 'auto',  # Use RF64 header rather than RIFF for large files
                                ]
                            ffmpeg_args += [
                                '-f', 'wav', new_stream.path,
                                ]
                            ffmpeg(*ffmpeg_args,
                                   progress_bar_max=stream_dict.estimated_duration,
                                   progress_bar_title=f'Convert {stream_dict.codec_type} stream {stream_dict.pprint_index} {stream_file_ext} -> {new_stream_file_ext} w/ ffmpeg',
                                   slurm=app.args.slurm,
                                   slurm_cpus_per_task=2, # ~230-240%
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)

                        done_optimize_iter(new_stream=new_stream)
                        continue

                    if stream_file_ext in opusenc_formats:
                        # opusenc supports Wave, AIFF, FLAC, Ogg/FLAC, or raw PCM.
                        new_stream_file_ext = '.opus.ogg'
                        new_stream['file_name'] = stream_file_base + new_stream_file_ext
                        app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                        audio_bitrate = 640000 if channels >= 4 else 384000
                        audio_bitrate = min(audio_bitrate, int(stream_dict.file.ffprobe_dict['streams'][0]['bit_rate']))
                        try:
                            audio_bitrate = min(audio_bitrate, int(stream_dict['original_bit_rate']))
                        except KeyError:
                            pass
                        audio_bitrate = audio_bitrate // 1000

                        with perfcontext('Convert %s -> %s w/ opusenc' % (stream_file_ext, new_stream.file_name), log=True):
                            opusenc_args = [
                                '--vbr',
                                '--bitrate', str(audio_bitrate),
                                stream_dict.path,
                                new_stream.path,
                                ]
                            opusenc(*opusenc_args,
                                    slurm=app.args.slurm,
                                    dry_run=app.args.dry_run)

                        done_optimize_iter(new_stream=new_stream)
                        continue

                    if True:
                        assert stream_file_ext not in ok_exts
                        # Hopefully ffmpeg supports it!
                        new_stream_file_ext = '.opus.ogg'
                        new_stream['file_name'] = stream_file_base + new_stream_file_ext
                        app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                        audio_bitrate = 640000 if channels >= 4 else 384000
                        audio_bitrate = min(audio_bitrate, int(stream_dict.file.ffprobe_dict['streams'][0]['bit_rate']))
                        audio_bitrate = audio_bitrate // 1000
                        if channels > 2:
                            raise NotImplementedError('Conversion not supported as ffmpeg does not respect the number of channels and channel mapping')

                        with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream.file_name), log=True):
                            ffmpeg_args = default_ffmpeg_args + [
                            ] + ffmpeg.input_args(stream_dict.file) + [
                                '-c:a', 'opus',
                                '-strict', 'experimental',  # for libopus
                                '-b:a', '%dk' % (audio_bitrate,),
                                # '-vbr', 'on', '-compression_level', '10',  # defaults
                                #'-channel', str(channels), '-channel_layout', channel_layout,
                                #'-channel', str(channels), '-mapping_family', '1', '-af', 'aformat=channel_layouts=%s' % (channel_layout,),
                                ]
                            ffmpeg_args += [
                                '-f', 'ogg', new_stream.path,
                                ]
                            ffmpeg(*ffmpeg_args,
                                   progress_bar_max=stream_dict.estimated_duration,
                                   progress_bar_title=f'Convert {stream_dict.codec_type} stream {stream_dict.pprint_index} {stream_file_ext} -> {new_stream_file_ext} w/ ffmpeg',
                                   slurm=app.args.slurm,
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)

                        done_optimize_iter(new_stream=new_stream)
                        continue

                    raise ValueError('Unsupported audio extension %r' % (stream_file_ext,))

                elif stream_dict.codec_type is CodecType.subtitle:

                    ok_exts = (
                            '.vtt',
                            )

                    if stream_file_ext in ('.vtt',):
                        app.log.verbose('Stream #%s %s (%s) [%s] OK', stream_dict.pprint_index, stream_file_ext, stream_dict.get('subtitle_count', '?'), stream_dict.language)
                        break

                    if False and stream_file_ext in ('.sup',):
                        new_stream_file_ext = '.sub'
                        new_stream['file_name'] = stream_file_base + new_stream_file_ext
                        app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                        if False:
                            with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream.file_name), log=True):
                                ffmpeg_args = default_ffmpeg_args + [
                                ] + ffmpeg.input_args(stream_dict.file) + [
                                    '-scodec', 'dvdsub',
                                    '-map', '0',
                                    ]
                                ffmpeg_args += [
                                    '-f', 'mpeg', new_stream.path,
                                    ]
                                ffmpeg(*ffmpeg_args,
                                       # TODO progress_bar_max=stream_dict.estimated_duration,
                                       # TODO progress_bar_title=,
                                       slurm=app.args.slurm,
                                       dry_run=app.args.dry_run,
                                       y=app.args.yes)
                        else:
                            with perfcontext('Convert %s -> %s w/ bdsup2sub' % (stream_file_ext, new_stream.file_name), log=True):
                                # https://www.videohelp.com/software/BDSup2Sub
                                # https://github.com/mjuhasz/BDSup2Sub/wiki/Command-line-Interface
                                cmd = [
                                    'bdsup2sub',
                                    # TODO --forced-only
                                    '--language', stream_dict.language.code2,
                                    '--output', new_stream.path,
                                    stream_dict.path,
                                    ]
                                out = do_spawn_cmd(cmd)

                        done_optimize_iter(new_stream=new_stream)
                        # continue

                    if stream_file_ext in ('.sup', '.sub',):
                        if app.args.external_subtitles is True \
                                or (app.args.external_subtitles == 'non-forced' and not stream_dict['disposition'].get('forced', None)):
                            app.log.verbose('Stream #%s %s (%s) [%s] -> EXTERNAL', stream_dict.pprint_index, stream_file_ext, stream_dict.get('subtitle_count', '?'), stream_dict.language)
                            return

                        new_stream_file_ext = '.srt'
                        new_stream['file_name'] = stream_file_base + new_stream_file_ext
                        if app.args.batch:
                            app.log.warning('BATCH MODE SKIP: Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)
                            do_chain = False
                            global_stats.num_batch_skips += 1
                            stats.this_num_batch_skips += 1
                            return
                        app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

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
                                    stream_dict.path,
                                    subrip_matrix_dir,
                                    ]
                                try:
                                    with perfcontext('SubRip /FINDMATRIX', log=True):
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

                            with perfcontext('SubRip /AUTOTEXT', log=True):
                                # ~/tools/installs/SubRip/CLI.txt
                                cmd = [
                                    'SubRip', '/AUTOTEXT',
                                    '--subtitle-language', stream_dict.language.code3,
                                    '--',
                                    stream_dict.path,
                                    new_stream.path,
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
                                        stream_dict.path,
                                        'subrip',  # format
                                    ]
                                else:
                                    subtitleedit_args += [
                                        stream_dict.path,
                                    ]
                                    if True:
                                        app.log.warning('Invoking %s: Please run OCR and save as SubRip (.srt) format: %s',
                                                        SubtitleEdit.name,
                                                        new_stream.path)
                                with perfcontext('Convert %s -> %s w/ SubtitleEdit' % (stream_file_ext, new_stream.file_name), log=True):
                                    SubtitleEdit(*subtitleedit_args,
                                                 language=stream_dict.language,
                                                 seed_file_name=new_stream.path,
                                                 dry_run=app.args.dry_run,
                                                 )
                                if not new_stream.path.is_file():
                                    try:
                                        raise OSError(errno.ENOENT, f'No such file: {new_stream.path}')
                                    except OSError as e:
                                        if not app.args.interactive:
                                            raise

                                        do_retry = False

                                        with app.need_user_attention():
                                            from prompt_toolkit.formatted_text import FormattedText
                                            from prompt_toolkit.completion import WordCompleter
                                            completer = None

                                            def setup_parser(in_err):
                                                nonlocal completer
                                                parser = argparse.NoExitArgumentParser(
                                                    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                                    description=str(in_err),
                                                    add_help=False, usage=argparse.SUPPRESS,
                                                    )
                                                subparsers = parser.add_subparsers(dest='action', required=True, help='Commands')
                                                subparser = subparsers.add_parser('help', aliases=('h', '?'), help='print this help')
                                                subparser = subparsers.add_parser('skip', aliases=('s',), help='skip this stream -- done')
                                                subparser = subparsers.add_parser('continue', aliases=('c', 'retry'), help='continue/retry processing this stream -- done')
                                                subparser = subparsers.add_parser('quit', aliases=('q',), help='quit')
                                                completer = WordCompleter([name for name in subparsers._name_parser_map.keys() if len(name) > 1])
                                                return parser
                                            parser = setup_parser(e)

                                            print('')
                                            app.print(
                                                FormattedText([
                                                    ('class:error', str(e)),
                                                ]))
                                            while True:
                                                print(new_stream)
                                                while True:
                                                    c = app.prompt(completer=completer, prompt_mode='error')
                                                    if c.strip():
                                                        break
                                                try:
                                                    ns = parser.parse_args(args=shlex.split(c, posix=os.name == 'posix'))
                                                except (argparse.ArgumentError, ValueError) as e:
                                                    app.log.error(e)
                                                    print('')
                                                    continue
                                                except argparse.ParserExitException as e:
                                                    if e.status:
                                                        app.log.error(e)
                                                        print('')
                                                    continue
                                                if ns.action == 'help':
                                                    print(parser.format_help())
                                                elif ns.action == 'skip':
                                                    do_skip = ns.comment or True
                                                    break
                                                elif ns.action == 'continue':
                                                    do_retry = True
                                                    break
                                                elif ns.action == 'quit':
                                                    raise
                                                else:
                                                    app.log.error('Invalid input: %r' % (ns.action,))

                                        if do_retry:
                                            continue
                                break

                        if not do_skip:
                            cmd = [
                                Path(__file__).with_name('fix-subtitles'),
                                new_stream.path,
                                ]
                            out = dbg_exec_cmd(cmd, encoding='utf-8')
                            if not app.args.dry_run:
                                out = clean_cmd_output(out)
                                new_stream.file.write(out)
                                if False and app.args.interactive:
                                    edfile(new_stream.path)

                        done_optimize_iter(new_stream=new_stream, do_skip=do_skip)
                        if do_skip:
                            return
                        else:
                            continue

                    # NOTE:
                    #  WebVTT format exported by SubtitleEdit is same as ffmpeg .srt->.vtt except ffmpeg's timestamps have more 0-padding
                    if stream_file_ext in ('.srt', '.ass'):
                        new_stream_file_ext = '.vtt'
                        new_stream['file_name'] = stream_file_base + new_stream_file_ext
                        app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                        with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream.file_name), log=True):
                            ffmpeg_args = default_ffmpeg_args + [
                            ] + ffmpeg.input_args(stream_dict.file) + [
                                '-f', 'webvtt', new_stream.path,
                                ]
                            ffmpeg(*ffmpeg_args,
                                   # TODO progress_bar_max=stream_dict.estimated_duration,
                                   # TODO progress_bar_title=,
                                   #slurm=app.args.slurm,
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)

                        done_optimize_iter(new_stream=new_stream)
                        continue

                    raise ValueError('Unsupported subtitle extension %r' % (stream_file_ext,))

                elif stream_dict.codec_type is CodecType.image:

                    # https://matroska.org/technical/cover_art/index.html
                    ok_exts = (
                            '.png',
                            '.jpg', '.jpeg',
                            )

                    if stream_file_ext in ok_exts:
                        app.log.verbose('Stream #%s %s OK', stream_dict.pprint_index, stream_file_ext)
                        app.log.verbose('Stream #%s %s [%s] OK', stream_dict.pprint_index, stream_file_ext, stream_dict.language)
                        break

                    if stream_file_ext not in ok_exts:
                        new_stream_file_ext = '.png'
                        new_stream['file_name'] = stream_file_base + new_stream_file_ext
                        app.log.verbose('Stream #%s %s -> %s', stream_dict.pprint_index, stream_file_ext, new_stream.file_name)

                        with perfcontext('Convert %s -> %s w/ ffmpeg' % (stream_file_ext, new_stream.file_name), log=True):
                            ffmpeg_args = default_ffmpeg_args + [
                            ] + ffmpeg.input_args(stream_dict.file) + [
                                ]
                            ffmpeg_args += [
                                '-f', 'png', new_stream.path,
                                ]
                            ffmpeg(*ffmpeg_args,
                                   #slurm=app.args.slurm,
                                   dry_run=app.args.dry_run,
                                   y=app.args.yes)

                        done_optimize_iter(new_stream=new_stream)
                        continue

                    raise ValueError('Unsupported image extension %r' % (stream_file_ext,))

                else:
                    raise ValueError('Unsupported codec type %r' % (stream_dict.codec_type,))

def action_optimize(inputdir, in_tags):
    app.log.info('Optimizing %s...', inputdir)
    do_chain = app.args.chain

    target_codec_names = set((
        'vp8', 'vp9',
        'opus',
        'webvtt',
    ))

    if not app.args.webm:
        target_codec_names |= set((
            'png', 'mjpeg',
        ))
    if app.args.ffv1:
        target_codec_names.add('ffv1')

    mux_dict = MmdemuxTask(inputdir / 'mux.json', in_tags=in_tags)

    if mux_dict.skip:
        app.log.info('%s: SKIP', inputdir)
        return

    stats = types.SimpleNamespace(
        this_num_batch_skips=0,
    )

    for stream_dict in sorted_stream_dicts(mux_dict['streams']):
        stream_dict.optimize(stats=stats, target_codec_names=target_codec_names)

    if not stats.this_num_batch_skips and do_chain:
        app.args.demux_dirs += (mux_dict.inputdir,)

def action_extract_music(inputdir, in_tags):
    app.log.info('Extracting music from %s...', inputdir)
    outputdir = inputdir

    mux_dict = MmdemuxTask(inputdir / 'mux.json', in_tags=in_tags)

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
            if stream_dict.skip:
                continue
            if 'original_file_name' in stream_dict:
                stream_dict = copy.copy(stream_dict)
                stream_dict['file_name'] = stream_dict.pop('original_file_name')
            stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)

            if stream_dict.codec_type is CodecType.video:
                pass
            elif stream_dict.codec_type is CodecType.audio:
                try:
                    stream_dict.file.duration = float(ffmpeg.Timestamp(stream_dict.file.ffprobe_dict['format']['duration']))
                except KeyError:
                    pass
                app.log.debug(stream_dict.file.ffprobe_dict['streams'][0])
                channels = stream_dict.file.ffprobe_dict['streams'][0]['channels']
                channel_layout = stream_dict.file.ffprobe_dict['streams'][0].get('channel_layout', None)

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

                    with perfcontext('Chop w/ ffmpeg', log=True):
                        ffmpeg_args = default_ffmpeg_args + [
                            '-start_at_zero', '-copyts',
                        ] + ffmpeg.input_args(stream_dict.file) + [
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
                               progress_bar_title=f'Chop {stream_dict.codec_type} stream {stream_dict.pprint_index} chapter {chap} w/ ffmpeg',
                               dry_run=app.args.dry_run,
                               y=app.args.yes)
                else:
                    stream_chapter_tmp_file = stream_dict.file

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
                    audio_bitrate = min(audio_bitrate, int(stream_dict.file.ffprobe_dict['streams'][0]['bit_rate']))
                    audio_bitrate = audio_bitrate // 1000

                    with perfcontext('Convert %s -> %s w/ M4aFile.encode' % (stream_chapter_tmp_file.file_name, '.m4a'), log=True):
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

            elif stream_dict.codec_type is CodecType.subtitle:
                pass
            elif stream_dict.codec_type is CodecType.image:
                # TODO image -> picture
                pass
            else:
                raise ValueError('Unsupported codec type %r' % (stream_dict.codec_type,))

def external_subtitle_file_name(output_file, stream_file_name, stream_dict):
    try:
        return stream_dict['external_stream_file_name']
    except KeyError:
        pass
    # stream_file_name = stream_dict['file_name']
    external_stream_file_name = my_splitext(output_file)[0]
    external_stream_file_name += '.' + stream_dict.language.code3
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
    if stream_dict['disposition'].get('clean_effects', None):
        external_stream_file_name += '.clean_effects'
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

    mux_dict = MmdemuxTask(inputdir / 'mux.json', in_tags=in_tags)

    if mux_dict.skip:
        app.log.info('%s: SKIP', inputdir)
        return

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
        in_err = e
        update_mux_conf = False

        if not app.args.interactive:
            raise

        with app.need_user_attention():
            from prompt_toolkit.formatted_text import FormattedText
            from prompt_toolkit.completion import WordCompleter
            completer = None

            def setup_parser(in_err):
                nonlocal completer
                parser = argparse.ArgumentParser(
                    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                    description=str(in_err),
                    add_help=False, usage=argparse.SUPPRESS,
                    exit_on_error=False,
                    )
                subparsers = parser.add_subparsers(dest='action', required=True, help='Commands')
                subparser = subparsers.add_parser('help', aliases=('h', '?'), help='print this help')
                subparser = subparsers.add_parser('skip', aliases=('s',), help='skip this stream -- done')
                subparser = subparsers.add_parser('print', aliases=('p',), help='print streams summary')
                subparser = subparsers.add_parser('default', help='toggle default disposition')
                subparser = subparsers.add_parser('language', help='edit language')
                subparser.add_argument('language', nargs='?')
                if stream_dict.codec_type in (CodecType.subtitle,):
                    subparser = subparsers.add_parser('forced', help='toggle forced disposition')
                if stream_dict.codec_type in (CodecType.subtitle,):
                    subparser = subparsers.add_parser('hearing_impaired', help='toggle hearing_impaired disposition')
                if stream_dict.codec_type in (CodecType.audio,):
                    subparser = subparsers.add_parser('visual_impaired', help='toggle visual_impaired disposition')
                if stream_dict.codec_type in (CodecType.audio, CodecType.subtitle):
                    subparser = subparsers.add_parser('comment', help='toggle comment disposition')
                if stream_dict.codec_type in (CodecType.audio, CodecType.subtitle):
                    subparser = subparsers.add_parser('karaoke', help='toggle karaoke disposition')
                if stream_dict.codec_type in (CodecType.audio, CodecType.subtitle):
                    subparser = subparsers.add_parser('dub', help='toggle dub disposition')
                if stream_dict.codec_type in (CodecType.audio, CodecType.subtitle):
                    subparser = subparsers.add_parser('clean_effects', help='toggle clean_effects disposition (stream without voice)')
                if stream_dict.codec_type in (CodecType.subtitle,):
                    subparser = subparsers.add_parser('lyrics', help='toggle lyrics disposition')
                if stream_dict.codec_type in (CodecType.audio,):
                    subparser = subparsers.add_parser('original', help='toggle original disposition')
                if stream_dict.codec_type in (CodecType.audio,):
                    subparser = subparsers.add_parser('title', help='edit title')
                    subparser.add_argument('title', nargs='?')
                if isinstance(in_err, StreamExternalSubtitleAlreadyCreated):
                    subparser = subparsers.add_parser('suffix', help='edit external stream file name suffix')
                    subparser.add_argument('suffix', nargs='?')
                subparser = subparsers.add_parser('open', help='open this stream')
                subparser = subparsers.add_parser('goto', aliases=('g',), help='jump to another stream')
                subparser.add_argument('index', help='target stream index', nargs='?')
                subparser = subparsers.add_parser('continue', aliases=('c', 'retry'), help='continue/retry processing this stream -- done')
                subparser = subparsers.add_parser('quit', aliases=('q',), help='quit')
                completer = WordCompleter([name for name in subparsers._name_parser_map.keys() if len(name) > 1])
                return parser
            parser = setup_parser(in_err)

            print('')
            app.print(
                FormattedText([
                    ('class:error', str(in_err)),
                ]))
            while True:
                print(stream_dict)
                while True:
                    c = app.prompt(completer=completer, prompt_mode='seen')
                    if c.strip():
                        break
                try:
                    ns = parser.parse_args(args=shlex.split(c, posix=os.name == 'posix'))
                except (argparse.ArgumentError, ValueError) as e:
                    if isinstance(e, argparse.ParserExitException) and e.status == 0:
                        # help?
                        pass
                    else:
                        app.log.error(e)
                        print('')
                    continue
                if ns.action == 'help':
                    print(parser.format_help())
                elif ns.action == 'skip':
                    stream_dict['skip'] = True
                    update_mux_conf = True
                    break
                elif ns.action == 'open':
                    try:
                        if stream_dict.codec_type in ('subtitle',):
                            from qip.subtitleedit import SubtitleEdit
                            subtitleedit_args = [
                                stream_dict.path,
                                ]
                            SubtitleEdit(*subtitleedit_args,
                                         language=stream_dict.language,
                                         #seed_file_name=new_stream.path,
                                         dry_run=app.args.dry_run,
                                         )
                        else:
                            xdg_open(inputdir / stream_dict['file_name'])
                    except Exception as e:
                        app.log.error(e)
                elif ns.action == 'continue':
                    i = next(i for i, d in enumerate(sorted_streams) if d is stream_dict)
                    enumerated_sorted_streams.send(i)
                    break
                elif ns.action == 'goto':
                    goto_index = ns.index
                    if goto_index is None:
                        goto_index = app.prompt('goto stream index: ', prompt_mode='')
                    if goto_index:
                        goto_index = int(goto_index)
                        forward = False
                        for i, d in enumerate(sorted_streams):
                            if d.index == goto_index:
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
                                mux_dict.save()
                                update_mux_conf = False
                            sorted_stream_index = i
                            stream_dict = d
                            enumerated_sorted_streams.send(sorted_stream_index)
                            if stream_dict.get('skip', False):
                                app.log.warning('Stream #%s skip cancelled', stream_dict.pprint_index)
                                del stream_dict['skip']
                                update_mux_conf = True
                        parser = setup_parser(in_err)
                elif ns.action == 'quit':
                    raise
                elif ns.action == 'print':
                    mux_dict.print_streams_summary(current_stream=stream_dict)
                elif ns.action == 'default':
                    stream_dict['disposition']['default'] = not stream_dict['disposition'].get('default', None)
                    update_mux_conf = True
                elif ns.action == 'forced':
                    stream_dict['disposition']['forced'] = not stream_dict['disposition'].get('forced', None)
                    update_mux_conf = True
                elif ns.action == 'hearing_impaired':
                    stream_dict['disposition']['hearing_impaired'] = not stream_dict['disposition'].get('hearing_impaired', None)
                    update_mux_conf = True
                elif ns.action == 'visual_impaired':
                    stream_dict['disposition']['visual_impaired'] = not stream_dict['disposition'].get('visual_impaired', None)
                    update_mux_conf = True
                elif ns.action == 'comment':
                    stream_dict['disposition']['comment'] = not stream_dict['disposition'].get('comment', None)
                    update_mux_conf = True
                elif ns.action == 'karaoke':
                    stream_dict['disposition']['karaoke'] = not stream_dict['disposition'].get('karaoke', None)
                    update_mux_conf = True
                elif ns.action == 'dub':
                    stream_dict['disposition']['dub'] = not stream_dict['disposition'].get('dub', None)
                    update_mux_conf = True
                elif ns.action == 'clean_effects':
                    stream_dict['disposition']['clean_effects'] = not stream_dict['disposition'].get('clean_effects', None)
                    update_mux_conf = True
                elif ns.action == 'lyrics':
                    stream_dict['disposition']['lyrics'] = not stream_dict['disposition'].get('lyrics', None)
                    update_mux_conf = True
                elif ns.action == 'original':
                    stream_dict['disposition']['original'] = not stream_dict['disposition'].get('original', None)
                    update_mux_conf = True
                elif ns.action == 'title':
                    stream_title = ns.title
                    if stream_title is None:
                        stream_title = app.input_dialog(
                            title=str(stream_dict),
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
                elif ns.action == 'language':
                    stream_language = ns.language
                    if stream_language is None:
                        stream_language = app.input_dialog(
                            title=str(stream_dict),
                            text='Please input stream language:',
                            initial_text=stream_dict.get('language', None) or '')
                    if stream_language is None:
                        print('Cancelled by user!')
                    else:
                        try:
                            stream_language = isolang(stream_language or 'und')
                        except ValueError as e:
                            app.log.error(e)
                        else:
                            stream_dict['language'] = str(stream_language)
                            update_mux_conf = True
                elif ns.action == 'suffix':
                    external_stream_file_name_suffix = ns.suffix
                    if external_stream_file_name_suffix is None:
                        external_stream_file_name_suffix = app.input_dialog(
                            title=str(stream_dict),
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
                    app.log.error('Invalid input: %r' % (ns.action,))

        if update_mux_conf:
            mux_dict.save()

    if use_mkvmerge:
        mkvmerge_args = []
        if webm:
            mkvmerge_args += [
                '--webm',
            ]
        mkvmerge_args += [
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
                unknown_language_warned=False,
            )

        sorted_streams = sorted_stream_dicts(mux_dict['streams'])
        enumerated_sorted_streams = qip.utils.advenumerate(sorted_streams)
        for sorted_stream_index, stream_dict in enumerated_sorted_streams:
            if stream_dict.skip:
                continue

            if stream_dict.codec_type not in (CodecType.video, CodecType.image, CodecType.data) \
                and stream_dict.language is isolang('und'):
                if not stream_dict['_temp'].unknown_language_warned:
                    stream_dict['_temp'].unknown_language_warned = True
                    try:
                        raise StreamLanguageUnknownError(stream=stream_dict)
                    except StreamLanguageUnknownError as e:
                        handle_StreamCharacteristicsSeenError(e)
                        continue

            stream_characteristics = stream_dict.identifying_characteristics(mkvmerge=True)

            if stream_characteristics in (
                    stream_dict2['_temp'].stream_characteristics
                    for stream_dict2 in sorted_streams[:sorted_stream_index]
                    if not stream_dict2.skip):
                try:
                    raise StreamCharacteristicsSeenError(stream=stream_dict,
                                                         stream_characteristics=stream_characteristics)
                except StreamCharacteristicsSeenError as e:
                    handle_StreamCharacteristicsSeenError(e)
                    continue
            stream_dict['_temp'].stream_characteristics = stream_characteristics

            if stream_dict.codec_type is CodecType.subtitle:
                if app.args.external_subtitles and my_splitext(stream_dict['file_name'])[1] != '.vtt':
                    stream_file_names = [stream_dict.file_name]
                    if my_splitext(stream_dict['file_name'])[1] == '.sub':
                        stream_file_names.append(my_splitext(stream_dict.file_name)[0] + '.idx')
                    for stream_file_name in stream_file_names:
                        external_stream_file_name = external_subtitle_file_name(
                            output_file=output_file,
                            stream_file_name=stream_file_name,
                            stream_dict=stream_dict)
                        app.log.warning('Stream #%s %s -> %s%s', stream_dict.pprint_index, stream_file_name, external_stream_file_name, ' (dry-run)' if app.args.dry_run else '')
                        if external_stream_file_name in external_stream_file_names_seen:
                            raise ValueError(f'Stream {stream_dict.pprint_index} External subtitle file already created: {external_stream_file_name}')
                        external_stream_file_names_seen.add(external_stream_file_name)
                        if not app.args.dry_run:
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
            if stream_dict.skip:
                continue
            stream_title = stream_dict.get('title', None)

            stream_dict['_temp'].out_index = max(
                (stream_index2['_temp'].out_index
                 for stream_index2 in sorted_streams[:sorted_stream_index]),
                default=-1) + 1

            if stream_dict.codec_type is CodecType.image:
                attachment_type = stream_dict['attachment_type']
                if webm:
                    # attachments not supported
                    stream_dict['_temp'].out_index = -1
                    attachment_counts[attachment_type] += 1
                    external_stream_file_name = output_file.file_name.parent / '{type}{num_suffix}{ext}'.format(
                        type=attachment_type,
                        num_suffix='' if attachment_counts[attachment_type] == 1 else '-%d' % (attachment_counts[attachment_type],),
                        ext=my_splitext(stream_dict.file_name)[1],
                    )
                    app.log.warning('Stream #%s %s -> %s%s', stream_dict.pprint_index, stream_dict.file_name, external_stream_file_name, ' (dry-run)' if app.args.dry_run else '')
                    if not app.args.dry_run:
                        shutil.copyfile(stream_dict.path,
                                        external_stream_file_name,
                                        follow_symlinks=True)
                    continue
                else:
                    mkvmerge_args += [
                        # '--attachment-description', <desc>
                        '--attachment-mime-type', byte_decode(dbg_exec_cmd(['file', '--brief', '--mime-type', stream_dict.path])).strip(),
                        '--attachment-name', '%s%s' % (attachment_type, my_splitext(stream_dict.file_name)[1]),
                        '--attach-file', stream_dict.path,
                        ]
            else:
                if stream_dict.codec_type is CodecType.video:
                    display_aspect_ratio = Ratio(stream_dict.get('display_aspect_ratio', None))
                    if display_aspect_ratio:
                        mkvmerge_args += ['--aspect-ratio', '%d:%s' % (0, display_aspect_ratio)]
                stream_default = stream_dict['disposition'].get('default', None)
                mkvmerge_args += ['--default-track', '%d:%s' % (0, ('true' if stream_default else 'false'))]
                if stream_dict.language is not isolang('und'):
                    mkvmerge_args += ['--language', '0:%s' % (stream_dict.language.code3,)]
                stream_forced = stream_dict['disposition'].get('forced', None)
                mkvmerge_args += ['--forced-track', '%d:%s' % (0, ('true' if stream_forced else 'false'))]
                if stream_title is not None:
                    mkvmerge_args += ['--track-name', '%d:%s' % (0, stream_title)]
                # TODO --tags
                if stream_dict.codec_type is CodecType.subtitle and stream_dict.file_name.suffix == '.sub':
                    mkvmerge_args += stream_dict.path.with_suffix('.idx')
                mkvmerge_args += [stream_dict.path]

        if mux_dict.get('chapters', None):
            mkvmerge_args += ['--chapters', inputdir / mux_dict['chapters']['file_name']]
        else:
            mkvmerge_args += ['--no-chapters']
        with perfcontext('Merge w/ mkvmerge', log=True):
            mkvmerge(*mkvmerge_args)

        if any(stream_dict['_temp'].post_process_subtitle
               for stream_dict in sorted_streams):
            num_inputs = 0
            noss_file_name = os.fspath(output_file.file_name) + '.noss%s' % ('.webm' if webm else '.mkv',)
            if not app.args.dry_run:
                shutil.move(output_file.file_name, noss_file_name)
            num_inputs += 1
            ffmpeg_args = default_ffmpeg_args + [
            ] + ffmpeg.input_args(noss_file_name) + [
                ]
            option_args = [
                '-map', str(num_inputs-1),
                ]
            for stream_dict in sorted_streams:
                if not stream_dict['_temp'].post_process_subtitle:
                    continue
                if stream_dict.skip:
                    continue

                stream_dict['_temp'].out_index = max(
                    (stream_index2['_temp'].out_index
                     for stream_index2 in sorted_streams),
                    default=-1) + 1

                num_inputs += 1
                ffmpeg_args += ffmpeg.input_args(stream_dict.file)
                option_args += [
                    '-map', str(num_inputs-1),
                    ]
                if stream_dict.language is not isolang('und'):
                    #ffmpeg_args += ['--language', '%d:%s' % (track_id, stream_dict.language.code3)]
                    option_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), 'language=%s' % (stream_dict.language.code3,),]

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
            with perfcontext('Merge subtitles w/ ffmpeg', log=True):
                ffmpeg(*ffmpeg_args,
                       progress_bar_max=estimated_duration,
                       progress_bar_title=f'Merge subtitles w/ ffmpeg',
                       dry_run=app.args.dry_run,
                       y=app.args.yes)
            raise NotImplementedError('BUG: unable to synchronize timestamps before and after adding subtitles, ffmpeg shifts video by 7ms (due to pre-skip of opus streams) and of vtts')
            if not app.args.dry_run:
                os.unlink(noss_file_name)

    else:  # !use_mkvmerge
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
        time_offset = 0  # qip.utils.Timestamp(-0.007)
        has_opus_streams = any(
                my_splitext(stream_dict['file_name'])[1] in ('.opus', '.opus.ogg')
                for stream_dict in mux_dict['streams'])
        video_angle = 0

        for stream_dict in mux_dict['streams']:
            stream_dict['_temp'] = types.SimpleNamespace(
                stream_characteristics=None,
                out_index=-1,
                external=False,
                unknown_language_warned=False,
            )

        sorted_streams = sorted_stream_dicts(mux_dict['streams'])
        enumerated_sorted_streams = qip.utils.advenumerate(sorted_streams)
        for sorted_stream_index, stream_dict in enumerated_sorted_streams:
            if stream_dict.skip:
                continue
            stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)

            if stream_dict.codec_type not in (CodecType.video, CodecType.image, CodecType.data) \
                and stream_dict.language is isolang('und'):
                if not stream_dict['_temp'].unknown_language_warned:
                    stream_dict['_temp'].unknown_language_warned = True
                    try:
                        raise StreamLanguageUnknownError(stream=stream_dict)
                    except StreamLanguageUnknownError as e:
                        handle_StreamCharacteristicsSeenError(e)
                        continue

            if stream_dict.codec_type is CodecType.subtitle:
                if app.args.external_subtitles and my_splitext(stream_dict['file_name'])[1] != '.vtt':
                    stream_file_names = [stream_dict.file_name]
                    if my_splitext(stream_dict['file_name'])[1] == '.sub':
                        stream_file_names.append(my_splitext(stream_dict.file_name)[0] + '.idx')
                    try:
                        for stream_file_name in stream_file_names:
                            external_stream_file_name = external_subtitle_file_name(
                                output_file=output_file,
                                stream_file_name=stream_file_name,
                                stream_dict=stream_dict)
                            app.log.warning('Stream #%s %s -> %s%s', stream_dict.pprint_index, stream_file_name, external_stream_file_name, ' (dry-run)' if app.args.dry_run else '')
                            if external_stream_file_name in external_stream_file_names_seen:
                                raise StreamExternalSubtitleAlreadyCreated(stream=stream_dict,
                                                                           external_stream_file_name=external_stream_file_name)
                            external_stream_file_names_seen.add(external_stream_file_name)
                            if not app.args.dry_run:
                                shutil.copyfile(inputdir / stream_file_name,
                                                external_stream_file_name,
                                                follow_symlinks=True)
                    except StreamExternalSubtitleAlreadyCreated as e:
                        handle_StreamCharacteristicsSeenError(e)
                        continue
                    stream_dict['_temp'].external = True
                    continue

            stream_characteristics = stream_dict.identifying_characteristics(mkvmerge=False)

            if stream_characteristics in (
                    stream_dict2['_temp'].stream_characteristics
                    for stream_dict2 in sorted_streams[:sorted_stream_index]
                    if not stream_dict2.skip):
                try:
                    raise StreamCharacteristicsSeenError(stream=stream_dict,
                                                         stream_characteristics=stream_characteristics)
                except StreamCharacteristicsSeenError as e:
                    handle_StreamCharacteristicsSeenError(e)
                    continue
            stream_dict['_temp'].stream_characteristics = stream_characteristics

        sorted_streams = sorted_stream_dicts(mux_dict['streams'])
        enumerated_sorted_streams = qip.utils.advenumerate(sorted_streams)
        for sorted_stream_index, stream_dict in enumerated_sorted_streams:
            if stream_dict.skip:
                continue
            if stream_dict['_temp'].external:
                # Already processed
                continue
            stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)
            stream_title = stream_dict.get('title', None)

            if stream_dict.codec_type is CodecType.image:
                attachment_type = stream_dict['attachment_type']
                if webm:
                    # attachments not supported
                    attachment_counts[attachment_type] += 1
                    external_stream_file_name = output_file.file_name.parent / '{type}{num_suffix}{ext}'.format(
                        type=attachment_type,
                        num_suffix='' if attachment_counts[attachment_type] == 1 else '-%d' % (attachment_counts[attachment_type],),
                        ext=my_splitext(stream_dict.file_name)[1],
                    )
                    app.log.warning('Stream #%s %s -> %s%s', stream_dict.pprint_index, stream_dict.file_name, external_stream_file_name, ' (dry-run)' if app.args.dry_run else '')
                    if not app.args.dry_run:
                        shutil.copyfile(stream_dict.path,
                                        external_stream_file_name,
                                        follow_symlinks=True)
                    continue

            stream_dict['_temp'].out_index = max(
                (stream_index2['_temp'].out_index
                 for stream_index2 in sorted_streams[:sorted_stream_index]),
                default=-1) + 1

            if stream_dict.codec_type is CodecType.subtitle:
                if my_splitext(stream_dict['file_name'])[1] == '.sub':
                    # ffmpeg doesn't read the .idx file?? Embed .sub/.idx into a .mkv first
                    tmp_stream_file_name = os.fspath(stream_dict.file_name) + '.mkv'
                    mkvmerge_args = [
                        '-o', inputdir / tmp_stream_file_name,
                        stream_dict.path,
                        '%s.idx' % (my_splitext(stream_dict.file_name)[0],),
                    ]
                    mkvmerge(*mkvmerge_args)
                    stream_dict = copy.copy(stream_dict)
                    stream_dict['file_name'] = tmp_stream_file_name
                    stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)

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
            if stream_dict.language is not isolang('und'):
                ffmpeg_output_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), 'language=%s' % (stream_dict.language.code3,),]
            if stream_title:
                ffmpeg_output_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), 'title=%s' % (stream_title,),]
            display_aspect_ratio = stream_dict.get('display_aspect_ratio', None)
            if display_aspect_ratio:
                ffmpeg_output_args += ['-aspect:%d' % (stream_dict['_temp'].out_index,), display_aspect_ratio]

            stream_start_time = AnyTimestamp(stream_dict.get('start_time', None) or 0)
            if stream_start_time:
                codec_encoding_delay = get_codec_encoding_delay(stream_dict.file)
                stream_start_time += codec_encoding_delay
            elif has_opus_streams and stream_file_ext in ('.opus', '.opus.ogg'):
                # Note that this is not needed if the audio track is wrapped in a mkv container
                stream_start_time = -ffmpeg.Timestamp.MAX
            if stream_start_time:
                ffmpeg_input_args += [
                    '-itsoffset', stream_start_time,
                    ]

            if stream_dict.codec_type is CodecType.video:

                if any(stream_file_base.upper().endswith(m)
                       for m in Stereo3DMode.full_side_by_side.exts + Stereo3DMode.half_side_by_side.exts):
                    ffmpeg_output_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), 'stereo_mode=left_right']
                elif any(stream_file_base.upper().endswith(m)
                         for m in Stereo3DMode.full_top_and_bottom.exts + Stereo3DMode.half_top_and_bottom.exts):
                    ffmpeg_output_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), 'stereo_mode=top_bottom']
                elif any(stream_file_base.upper().endswith(m)
                         for m in Stereo3DMode.alternate_frame.exts):
                    raise NotImplementedError(Stereo3DMode.alternate_frame)

                if stream_file_ext in {'.vp9', '.vp9.ivf',}:
                    # ivf:
                    #   ffmpeg does not generate packet durations from ivf -> mkv, causing some hickups at play time. But it does from .mkv -> .mkv, so create an intermediate
                    estimated_duration = estimated_duration or stream_dict.estimated_duration
                    tmp_stream_file_name = os.fspath(stream_dict.file_name) + '.mkv'
                    master_display = stream_dict.get('master_display', None)
                    max_cll = stream_dict.get('max_cll', None)
                    max_fall = stream_dict.get('max_fall', None)
                    color_transfer = stream_dict.get('color_transfer', None)
                    color_primaries = stream_dict.get('color_primaries', None)

                    if master_display or max_cll or max_fall:  # or color_transfer or color_primaries:
                        if max_cll is None and max_fall is None:
                            app.log.warning('HDR: max_cll and max_fall are not set; Defaulting both to 0.')
                            max_cll, max_fall = 0, 0
                        assert master_display and max_cll is not None and max_fall is not None and color_transfer and color_primaries, f'Incomplete color information: master_display={master_display!r}, max_cll={max_cll!r}, max_fall={max_fall!r}, color_transfer={color_transfer!r}, color_primaries={color_primaries!r}'
                        master_display = parse_master_display_str(master_display)

                        ffprobe_stream_json = stream_dict.file.ffprobe_dict['streams'][0]

                        mkvmerge_args = []
                        mkvmerge_args= [
                            # HDR
                            '--colour-matrix', '0:{}'.format(
                                ffmpeg.get_option_value_int('colorspace', ffprobe_stream_json['color_space']),
                            ),
                            '--colour-range', '0:{}'.format(
                                ffmpeg.get_option_value_int('color_range', ffprobe_stream_json['color_range']),
                            ),
                            '--colour-transfer-characteristics', '0:{}'.format(
                                ffmpeg.get_option_value_int('color_trc', color_transfer),
                            ),
                            '--colour-primaries', '0:{}'.format(
                                ffmpeg.get_option_value_int('color_primaries', color_primaries),
                            ),
                            '--max-content-light', f'0:{max_cll}',
                            '--max-frame-light', f'0:{max_fall}',
                            '--chromaticity-coordinates', '0:{xR:.3f},{yR:.3f},{xG:.3f},{yG:.3f},{xB:.3f},{yB:.3f}'.format(
                                xR=master_display.uxR * 0.00002,
                                yR=master_display.uyR * 0.00002,
                                xG=master_display.uxG * 0.00002,
                                yG=master_display.uyG * 0.00002,
                                xB=master_display.uxB * 0.00002,
                                yB=master_display.uyB * 0.00002,
                            ),
                            '--white-colour-coordinates', '0:{xW:.5f},{yW:.5f}'.format(
                                xW=master_display.uxW * 0.0001,
                                yW=master_display.uyW * 0.0001,
                            ),
                            '--min-luminance', '0:{minL}'.format(
                                minL=master_display.uminL * 0.0001,
                            ),
                            '--max-luminance', '0:{maxL}'.format(
                                maxL=master_display.umaxL * 0.0001,
                            ),
                            '-o', inputdir / tmp_stream_file_name,
                            stream_dict.path,
                        ]
                        mkvmerge(*mkvmerge_args)
                        stream_dict = copy.copy(stream_dict)
                        stream_dict['file_name'] = tmp_stream_file_name
                        stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)

                    else:

                        ffprobe_stream_json = stream_dict.file.ffprobe_dict['streams'][0]

                        ffmpeg_args = default_ffmpeg_args + [
                        ] + ffmpeg.input_args(stream_dict.file) + [
                            '-codec', 'copy',
                        ]
                        try:
                            ffmpeg_args += [
                                '-color_primaries', ffmpeg.get_option_value('color_primaries', ffprobe_stream_json['color_primaries']),
                            ]
                        except KeyError:
                            pass
                        try:
                            ffmpeg_args += [
                                '-color_trc', ffmpeg.get_option_value('color_trc', ffprobe_stream_json['color_transfer']),
                            ]
                        except KeyError:
                            pass
                        try:
                            ffmpeg_args += [
                                '-colorspace', ffmpeg.get_option_value('colorspace', ffprobe_stream_json['color_space']),
                            ]
                        except KeyError:
                            pass
                        try:
                            ffmpeg_args += [
                                '-color_range', ffmpeg.get_option_value('color_range', ffprobe_stream_json['color_range']),
                            ]
                        except KeyError:
                            pass
                        ffmpeg_args += [
                                inputdir / tmp_stream_file_name,
                            ]
                        assert estimated_duration is None or float(estimated_duration) > 0.0
                        ffmpeg(
                            *ffmpeg_args,
                            progress_bar_max=estimated_duration,
                            progress_bar_title=f'Encap {stream_dict.codec_type} stream {stream_dict.pprint_index} w/ ffmpeg',
                            dry_run=app.args.dry_run,
                            y=True,  # TODO temp file
                        )
                        stream_dict = copy.copy(stream_dict)
                        stream_dict['file_name'] = tmp_stream_file_name
                        stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)

                elif stream_file_ext in {
                    '.h264',
                    '.mp2v',
                }:
                    # h264:
                    #   [matroska @ 0x5637c1c58a40] Timestamps are unset in a packet for stream 0. This is deprecated and will stop working in the future. Fix your code to set the timestamps properly
                    #   [matroska @ 0x5637c1c58a40] Can't write packet with unknown timestamp
                    #   av_interleaved_write_frame(): Invalid argument
                    estimated_duration = estimated_duration or stream_dict.estimated_duration

                    tmp_stream_file_name = os.fspath(stream_dict.file_name) + '.mp4'
                    ffmpeg_args = default_ffmpeg_args + [
                    ] + ffmpeg.input_args(stream_dict.file) + [
                            '-codec', 'copy',
                            inputdir / tmp_stream_file_name,
                        ]
                    assert estimated_duration is None or float(estimated_duration) > 0.0
                    ffmpeg(
                        *ffmpeg_args,
                        progress_bar_max=estimated_duration,
                        progress_bar_title=f'Encap {stream_dict.codec_type} stream {stream_dict.pprint_index} w/ ffmpeg',
                        dry_run=app.args.dry_run,
                        y=True,  # TODO temp file
                    )
                    stream_dict = copy.copy(stream_dict)
                    stream_dict['file_name'] = tmp_stream_file_name
                    stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)

                    tmp_stream_file_name = os.fspath(stream_dict.file_name) + '.mkv'
                    ffmpeg_args = default_ffmpeg_args + [
                    ] + ffmpeg.input_args(inputdir / stream_dict.file_name) + [
                            '-codec', 'copy',
                            inputdir / tmp_stream_file_name,
                        ]
                    assert estimated_duration is None or float(estimated_duration) > 0.0
                    ffmpeg(
                        *ffmpeg_args,
                        progress_bar_max=estimated_duration,
                        progress_bar_title=f'Encap {stream_dict.codec_type} stream {stream_dict.pprint_index} w/ ffmpeg',
                        dry_run=app.args.dry_run,
                        y=True,  # TODO temp file
                    )
                    stream_dict = copy.copy(stream_dict)
                    stream_dict['file_name'] = tmp_stream_file_name
                    stream_file_base, stream_file_ext = my_splitext(stream_dict.file_name)
                elif stream_file_ext.endswith('.mkv'):
                    pass
                elif stream_file_ext in still_image_exts:
                    pass
                elif stream_file_ext in {'.h264', '.h265'}:
                    pass
                else:
                    raise NotImplementedError(stream_file_ext)
            elif stream_dict.codec_type is CodecType.subtitle:
                if '3d-plane' in stream_dict:
                    ffmpeg_output_args += ['-metadata:s:%d' % (stream_dict['_temp'].out_index,), '3d-plane=%d' % (stream_dict['3d-plane'],)]

            ffmpeg_input_args += ffmpeg.input_args(stream_dict.file)
            # Include all streams from this input file:
            ffmpeg_output_args += [
                '-map', stream_dict['_temp'].out_index,
                ]
        ffmpeg_output_args += [
            '-f', ext_to_container(output_file),
            output_file,
            ]
        ffmpeg_args = default_ffmpeg_args + ffmpeg_input_args + ffmpeg_output_args
        with perfcontext('Merge w/ ffmpeg', log=True):
            ffmpeg(*ffmpeg_args,
                   progress_bar_max=estimated_duration,
                   progress_bar_title='Merge w/ ffmpeg',
                   dry_run=app.args.dry_run,
                   y=app.args.yes)
        if mux_dict.get('chapters', None):
            chapters_xml_file = MatroskaChaptersFile(inputdir / mux_dict['chapters']['file_name'])
            chapters_xml_file.load()
            if time_offset:
                for chap in chapters_xml_file.chapters:
                    chap.offset(time_offset)
            output_file.write_chapters(chapters_xml_file.chapters, log=True)

    output_file.write_tags(tags=mux_dict['tags'],
            dry_run=app.args.dry_run,
            run_func=do_exec_cmd)
    app.log.info('DONE writing %s%s',
                 output_file.file_name,
                 ' (dry-run)' if app.args.dry_run else '')
    print('')

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
                    while True:
                        c = app.prompt(completer=completer, prompt_mode='error')
                        if c.strip():
                            break
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
                        mux_dict.print_streams_summary()
                    else:
                        app.log.error('Invalid input')

        app.log.info('DONE writing & verifying %s%s',
                     output_file.file_name,
                     ' (dry-run)' if app.args.dry_run else '')
        print('')

    if app.args.cleanup:
        app.log.info('Cleaning up %s', inputdir)
        shutil.rmtree(inputdir)

    return True

def action_concat(concat_files, in_tags):
    tags = copy.copy(in_tags)

    concat_file_name = 'concat.mkv'
    concat_file = MediaFile.new_by_file_name(concat_file_name)

    concat_files = [
        inputfile if isinstance(inputfile, MediaFile) else MediaFile.new_by_file_name(inputfile)
        for inputfile in concat_files]

    chaps = Chapters()
    prev_chap = Chapter(0, 0)
    for inputfile in concat_files:
        try:
            inputfile.duration = float(ffmpeg.Timestamp(inputfile.ffprobe_dict['format']['duration']))
        except KeyError:
            pass
        # inputfile.extract_info(need_actual_duration=True)
        chap = Chapter(start=prev_chap.end,
                       end=prev_chap.end + inputfile.duration,
                       title=re.sub(r'\.demux$', '', my_splitext(inputfile.file_name.name)[0]),
                       )
        chaps.append(chap)
    if app.args.interactive:
        chapters_xml = chaps.to_mkv_xml()
        chapters_xml = edvar(chapters_xml,
                             preserve_whitespace_tags=Chapters.MKV_XML_VALUE_TAGS)[1]
        chaps = Chapters.from_mkv_xml(chapters_xml)

    with ffmpeg.ConcatScriptFile.NamedTemporaryFile() as concat_list_file:
        safe_concat = False
        concat_list_file.files += [
            concat_list_file.File(inputfile.file_name.resolve())  # absolute
            for inputfile in concat_files]
        concat_list_file.create()
        # write -> read
        concat_list_file.flush()
        concat_list_file.seek(0)

        ffmpeg_concat_args = []
        ffmpeg_args = default_ffmpeg_args + [
            '-f', 'concat', '-safe', 1 if safe_concat else 0,
            # TODO -r
        ] + ffmpeg.input_args(concat_list_file) + [
            '-codec', 'copy',
        ] + ffmpeg_concat_args + [
            '-start_at_zero',
            '-f', ext_to_container(concat_file),
            concat_file,
        ]
        with perfcontext('Concat w/ ffmpeg', log=True):
            ffmpeg(*ffmpeg_args,
                   progress_bar_max=chaps.chapters[-1].end,
                   progress_bar_title=f'Concat w/ ffmpeg',
                   dry_run=app.args.dry_run,
                   y=app.args.yes)

    concat_file.write_chapters(chaps, log=True)

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
    assert l_series, 'No series!'
    i = 0
    if len(l_series) > 1 and app.args.interactive:
        i = app.radiolist_dialog(
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
        app.log.info('%s: %s', episode_file, episode_file.tags.cite())
        episode_file.write_tags(tags=episode_file.tags,
                                dry_run=app.args.dry_run)
        if app.args.rename:
            from qip.bin.organize_media import organize_tvshow
            opath = organize_tvshow(episode_file, suggest_tags=TrackTags())
            opath = episode_file.file_name.with_name(opath.name)
            if opath != episode_file.file_name:
                if opath.exists():
                    raise OSError(errno.EEXIST, f'File exists: {opath}')
                if app.args.dry_run:
                    app.log.info('  Rename to %s. (dry-run)', opath)
                else:
                    app.log.info('  Rename to %s.', opath)
                    episode_file.rename(opath)
                    episode_file.file_name = opath

def action_identify_files(file_names, in_tags):

    t = [os.fspath(e) for e in file_names]
    if t != sorted(t):
        m = 'File names not sorted; This is likely a mistake.'
        if app.args.force:
            app.log.warning(m + ' (--force used; Bypassing)')
        else:
            raise ValueError(m + ' (use --force to bypass)')

    if file_names[0].is_dir():
        seed_initial_text = file_names[0].name
    else:
        seed_initial_text = file_names[0].parent.name

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

    global tvdb
    if tvdb is None:
        global qip
        import qip.thetvdb
        tvdb = qip.thetvdb.Tvdb(
            apikey='d38d1a8df34d030f1be077798db952bc',  # mmdemux
            interactive=app.args.interactive,
        )
    o_show_cache = {}

    files = [MovieFile.new_by_file_name(file_name)
             for file_name in file_names]
    tags = files[0].load_tags()
    tags.update(in_tags)
    i_file = -1
    while (i_file + 1) < len(files):
        i_file += 1
        o_file = files[i_file]

        if tags.type is None:
            type_initial_text = 'movie'
        else:
            type_initial_text = tags.type

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

        if tags.episode is None:
            episode_initial_text = ''  # '1' if str(tags.type) == 'tvshow' else ''
        else:
            episode_initial_text = ','.join(str(e) for e in tags.episode)

        if tags.contenttype is None:
            contenttype_initial_text = ''
        else:
            contenttype_initial_text = str(tags.contenttype)

        if not tags.comment:
            comment_initial_text = ''
        else:
            comment_initial_text = str(tags.comment[0])

        def type_accept(buf):
            get_app().layout.focus(tvshow_textarea)
            return True  # Keep text.
        type_textarea = TextArea(
            text=type_initial_text,
            multiline=False,
            accept_handler=type_accept,
            auto_suggest=AutoSuggestFromHistory())

        def tvshow_accept(buf):
            get_app().layout.focus(season_textarea)
            return True  # Keep text.
        tvshow_textarea = TextArea(
            text=tvshow_initial_text,
            multiline=False,
            accept_handler=tvshow_accept,
            auto_suggest=AutoSuggestFromHistory())

        def season_accept(buf):
            get_app().layout.focus(episode_textarea)
            return True  # Keep text.
        season_textarea = NumericTextArea(
            text=season_initial_text,
            multiline=False,
            accept_handler=season_accept,
            auto_suggest=AutoSuggestFromHistory())

        def episode_accept(buf):
            get_app().layout.focus(contenttype_textarea)
            return True  # Keep text.
        episode_textarea = NumericTextArea(
            text=episode_initial_text,
            multiline=False,
            accept_handler=episode_accept,
            auto_suggest=AutoSuggestFromHistory())

        def contenttype_accept(buf):
            get_app().layout.focus(comment_textarea)
            return True  # Keep text.
        contenttype_textarea = TextArea(
            text=contenttype_initial_text,
            multiline=False,
            accept_handler=contenttype_accept,
            auto_suggest=AutoSuggestFromHistory())

        def comment_accept(buf):
            get_app().layout.focus(language_textarea)
            return True  # Keep text.
        comment_textarea = TextArea(
            text=comment_initial_text,
            multiline=False,
            accept_handler=comment_accept,
            auto_suggest=AutoSuggestFromHistory())

        def language_accept(buf):
            get_app().layout.focus(ok_button)
            return True  # Keep text.
        language_textarea = TextArea(
            text=str(tags.language or ''),
            multiline=False,
            accept_handler=language_accept,
            auto_suggest=AutoSuggestFromHistory())

        def open_handler():
            xdg_open(o_file)
        open_button = Button(text='&Open', handler=open_handler)

        def delete_handler():
            o_file.send2trash()
            get_app().exit(result='skip')
        delete_button = Button(text='&Delete', handler=delete_handler)

        def skip_handler():
            get_app().exit(result='deleted')
        skip_button = Button(text='&Skip', handler=skip_handler)

        def ok_handler():
            get_app().exit(result=(
                type_textarea.text,
                tvshow_textarea.text,
                season_textarea.text,
                episode_textarea.text,
                contenttype_textarea.text,
                comment_textarea.text,
                language_textarea.text,
            ))
        ok_button = Button(text='Ok', handler=ok_handler)

        cancel_button = Button(text='Cancel', handler=_return_none)

        def push_button_handler(button, event):
            # get_app().layout.focus(button)
            return button.handler()

        label_width = 14
        dialog = Dialog(
            title='Episode tagging',
            body=HSplit([
                VSplit([
                    Box(Label(text='File:'), padding_left=0, width=label_width),
                    Label(text=os.fspath(o_file)),
                ]),
                VSplit([
                    Box(Label(text='Type:'), padding_left=0, width=label_width),
                    type_textarea,
                ]),
                VSplit([
                    Box(Label(text='TV Show:'), padding_left=0, width=label_width),
                    tvshow_textarea,
                ]),
                VSplit([
                    Box(Label(text='Season:'), padding_left=0, width=label_width),
                    season_textarea,
                ]),
                VSplit([
                    Box(Label(text='Episode:'), padding_left=0, width=label_width),
                    episode_textarea,
                ]),
                VSplit([
                    Box(Label(text='Content Type:'), padding_left=0, width=label_width),
                    contenttype_textarea,
                ]),
                VSplit([
                    Box(Label(text='Comment:'), padding_left=0, width=label_width),
                    comment_textarea,
                ]),
                VSplit([
                    Box(Label(text='Language:'), padding_left=0, width=label_width),
                    language_textarea,
                ]),
            ], padding=D(preferred=1, max=1)),
            buttons=[open_button, skip_button, delete_button, ok_button, cancel_button],
            with_background=True)
        if dialog.body.key_bindings is None:
            from prompt_toolkit.key_binding.key_bindings import KeyBindings
            dialog.body.key_bindings = KeyBindings()
        kb = dialog.body.key_bindings
        kb.add('escape', 'o')(functools.partial(push_button_handler, open_button))  # Escape, o
        kb.add('escape', 's')(functools.partial(push_button_handler, skip_button))  # Escape, s
        kb.add('escape', 'd')(functools.partial(push_button_handler, delete_button))  # Escape, d
        kb.add('escape', 'escape')(functools.partial(push_button_handler, cancel_button))    # Escape, Escape
        kb.add('escape', 'enter')(functools.partial(push_button_handler, ok_button))    # Escape, Enter

        result = app.run_dialog(dialog)
        if result is None:
            raise ValueError('Cancelled by user!')
        if result == 'skip':
            continue
        elif result == 'deleted':
            del files[i_file]
            i_file -= 1
            continue
        tags.type, tags.tvshow, tags.season, tags.episode, tags.contenttype, tags.comment, tags.language = result
        print('tags=%r' % (dict(tags),))

        tags.type = tags.deduce_type()
        assert str(tags.type) == 'tvshow'

        if str(tags.type) == 'tvshow':
            if not tags.tvshow:
                raise ValueError('Missing tvshow')
            if tags.season is None:
                raise ValueError('Missing season number')
            #if tags.episode is None:
            #    raise ValueError('Missing episode number')

            tvdb.language = tags.language

            try:
                o_show = o_show_cache[tags.tvshow]
            except KeyError:
                l_series = tvdb.search(tags.tvshow)
                app.log.debug('l_series=%r', l_series)
                assert l_series, 'No series!'
                i = 0
                if len(l_series) > 1 and app.args.interactive:
                    i = app.radiolist_dialog(
                        title='Please select a series',
                        values=[(i, '{seriesName} [{language}], {network}, {firstAired}, {status} (#{id})'.format_map(d_series))
                                for i, d_series in enumerate(l_series)],
                        style=app.prompt_style)
                    if i is None:
                        raise ValueError('Cancelled by user!')
                d_series = l_series[i]
                tags.tvshow = d_series['seriesName']
                o_show = tvdb[d_series['id']]
                o_show_cache[tags.tvshow] = o_show
                app.log.debug('o_show=%r', o_show)

            o_season = o_show[tags.season]
            app.log.debug('o_season=%r', o_season)

            tags.episode = [e for e in (tags.episode or []) if e != 0]
            if tags.episode:
                i_episode = tags.episode[0]
                o_episode = o_season[i_episode]
            else:
                i_episode = None
                o_episode = None
            app.log.debug('o_file=%r, o_episode=%r:\n%s', o_file, o_episode, o_episode and pprint.pformat(dict(o_episode)))

            # o_file.tags.update(o_file.load_tags(file_type=tags.type))
            o_file.tags.update(tags)
            if o_episode:
                o_file.tags.episode = o_episode['airedEpisodeNumber']
                o_file.tags.title = o_episode['episodeName']
                o_file.tags.date = o_episode['firstAired']
            else:
                o_file.tags.episode = None
                o_file.tags.title = None
                o_file.tags.date = None
            app.log.info('%s: %s', o_file, o_file.tags.cite())
            o_file.write_tags(tags=o_file.tags,
                                    dry_run=app.args.dry_run)
            if app.args.rename:
                from qip.bin.organize_media import organize_tvshow
                try:
                    old_media_library_app = app.args.media_library_app
                    app.args.media_library_app = 'mmdemux'
                    opath = organize_tvshow(o_file, suggest_tags=TrackTags())
                finally:
                    app.args.media_library_app = old_media_library_app
                opath = o_file.file_name.with_name(opath.name)
                if opath != o_file.file_name:
                    if opath.exists():
                        raise OSError(errno.EEXIST, f'File exists: {opath}')
                    if app.args.dry_run:
                        app.log.info('  Rename to %s. (dry-run)', opath)
                    else:
                        app.log.info('  Rename to %s.', opath)
                        o_file.rename(opath)
                        o_file.file_name = opath

        else:
            raise NotImplementedError(tags.type)

if __name__ == '__main__':
    main()
