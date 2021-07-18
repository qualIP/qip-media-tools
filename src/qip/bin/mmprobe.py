#!/usr/bin/env python3

from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import av
import collections
import logging
import os
import struct

from qip import argparse
from qip.app import app
from qip.ffmpeg import ffmpeg, ffprobe

def av_reorder_packets(av_packets):  # TODO RENAME
    prev_av_packet = None
    prev_pts = None
    for av_packet in av_packets:
        pts = av_packet.pts
        if pts is None:
            pts = av_packet.dts
        if pts is None:
            yield av_packet
            continue
        assert pts is not None, f'{av_packet!r} pts is None'
        if prev_av_packet is None:
            prev_av_packet = av_packet
            prev_pts = pts
            continue
        if prev_pts < pts:
            yield prev_av_packet
            prev_av_packet = av_packet
        else:
            yield av_packet
    if prev_av_packet is not None:
        yield prev_av_packet

def av_reorder_packets(av_packets):  # TODO RENAME
    prev_av_packet = None
    prev_pts = None
    for i, av_packet in enumerate(av_packets):
        pts = av_packet.pts
        if pts is None:
            pts = av_packet.dts
        print(f'{i}: pts={pts}')
        if pts is None:
            print(f'{i}: yield av_packet')
            yield av_packet
            continue
        assert pts is not None, f'{av_packet!r} pts is None'
        if prev_av_packet is None:
            prev_av_packet = av_packet
            prev_pts = pts
            print(f'{i}: prev_av_packet = av_packet')
            continue
        if prev_pts < pts:
            print(f'{i}: {prev_pts} <= {pts}. yield prev_av_packet')
            yield prev_av_packet
            prev_av_packet = av_packet
            prev_pts = pts
        else:
            print(f'{i}: {prev_pts} > {pts}. yield av_packet')
            yield av_packet
    if prev_av_packet is not None:
        print(f'yield prev_av_packet')
        yield prev_av_packet

# From ffmpeg-dmo-4.3.2/libavutil/channel_layout.h
#
# @defgroup channel_masks Audio channel masks
#
# A channel layout is a 64-bits integer with a bit set for every channel.
# The number of bits set must be equal to the number of channels.
# The value 0 means that the channel layout is not known.
# @note this data structure is not powerful enough to handle channels
# combinations that have the same channel multiple times, such as
# dual-mono.
#
AV_CH_FRONT_LEFT = 0x00000001
AV_CH_FRONT_RIGHT = 0x00000002
AV_CH_FRONT_CENTER = 0x00000004
AV_CH_LOW_FREQUENCY = 0x00000008
AV_CH_BACK_LEFT = 0x00000010
AV_CH_BACK_RIGHT = 0x00000020
AV_CH_FRONT_LEFT_OF_CENTER = 0x00000040
AV_CH_FRONT_RIGHT_OF_CENTER = 0x00000080
AV_CH_BACK_CENTER = 0x00000100
AV_CH_SIDE_LEFT = 0x00000200
AV_CH_SIDE_RIGHT = 0x00000400
AV_CH_TOP_CENTER = 0x00000800
AV_CH_TOP_FRONT_LEFT = 0x00001000
AV_CH_TOP_FRONT_CENTER = 0x00002000
AV_CH_TOP_FRONT_RIGHT = 0x00004000
AV_CH_TOP_BACK_LEFT = 0x00008000
AV_CH_TOP_BACK_CENTER = 0x00010000
AV_CH_TOP_BACK_RIGHT = 0x00020000
AV_CH_STEREO_LEFT = 0x20000000  # Stereo downmix.
AV_CH_STEREO_RIGHT = 0x40000000  # See AV_CH_STEREO_LEFT.
AV_CH_WIDE_LEFT = 0x0000000080000000
AV_CH_WIDE_RIGHT = 0x0000000100000000
AV_CH_SURROUND_DIRECT_LEFT = 0x0000000200000000
AV_CH_SURROUND_DIRECT_RIGHT = 0x0000000400000000
AV_CH_LOW_FREQUENCY_2 = 0x0000000800000000

# Channel mask value used for AVCodecContext.request_channel_layout
# to indicate that the user requests the channel order of the decoder output
# to be the native codec channel order.
AV_CH_LAYOUT_NATIVE = 0x8000000000000000

#
# @}
# @defgroup channel_mask_c Audio channel layouts
# @{
#
AV_CH_LAYOUT_MONO = (AV_CH_FRONT_CENTER)
AV_CH_LAYOUT_STEREO = (AV_CH_FRONT_LEFT|AV_CH_FRONT_RIGHT)
AV_CH_LAYOUT_2POINT1 = (AV_CH_LAYOUT_STEREO|AV_CH_LOW_FREQUENCY)
AV_CH_LAYOUT_2_1 = (AV_CH_LAYOUT_STEREO|AV_CH_BACK_CENTER)
AV_CH_LAYOUT_SURROUND = (AV_CH_LAYOUT_STEREO|AV_CH_FRONT_CENTER)
AV_CH_LAYOUT_3POINT1 = (AV_CH_LAYOUT_SURROUND|AV_CH_LOW_FREQUENCY)
AV_CH_LAYOUT_4POINT0 = (AV_CH_LAYOUT_SURROUND|AV_CH_BACK_CENTER)
AV_CH_LAYOUT_4POINT1 = (AV_CH_LAYOUT_4POINT0|AV_CH_LOW_FREQUENCY)
AV_CH_LAYOUT_2_2 = (AV_CH_LAYOUT_STEREO|AV_CH_SIDE_LEFT|AV_CH_SIDE_RIGHT)
AV_CH_LAYOUT_QUAD = (AV_CH_LAYOUT_STEREO|AV_CH_BACK_LEFT|AV_CH_BACK_RIGHT)
AV_CH_LAYOUT_5POINT0 = (AV_CH_LAYOUT_SURROUND|AV_CH_SIDE_LEFT|AV_CH_SIDE_RIGHT)
AV_CH_LAYOUT_5POINT1 = (AV_CH_LAYOUT_5POINT0|AV_CH_LOW_FREQUENCY)
AV_CH_LAYOUT_5POINT0_BACK = (AV_CH_LAYOUT_SURROUND|AV_CH_BACK_LEFT|AV_CH_BACK_RIGHT)
AV_CH_LAYOUT_5POINT1_BACK = (AV_CH_LAYOUT_5POINT0_BACK|AV_CH_LOW_FREQUENCY)
AV_CH_LAYOUT_6POINT0 = (AV_CH_LAYOUT_5POINT0|AV_CH_BACK_CENTER)
AV_CH_LAYOUT_6POINT0_FRONT = (AV_CH_LAYOUT_2_2|AV_CH_FRONT_LEFT_OF_CENTER|AV_CH_FRONT_RIGHT_OF_CENTER)
AV_CH_LAYOUT_HEXAGONAL = (AV_CH_LAYOUT_5POINT0_BACK|AV_CH_BACK_CENTER)
AV_CH_LAYOUT_6POINT1 = (AV_CH_LAYOUT_5POINT1|AV_CH_BACK_CENTER)
AV_CH_LAYOUT_6POINT1_BACK = (AV_CH_LAYOUT_5POINT1_BACK|AV_CH_BACK_CENTER)
AV_CH_LAYOUT_6POINT1_FRONT = (AV_CH_LAYOUT_6POINT0_FRONT|AV_CH_LOW_FREQUENCY)
AV_CH_LAYOUT_7POINT0 = (AV_CH_LAYOUT_5POINT0|AV_CH_BACK_LEFT|AV_CH_BACK_RIGHT)
AV_CH_LAYOUT_7POINT0_FRONT = (AV_CH_LAYOUT_5POINT0|AV_CH_FRONT_LEFT_OF_CENTER|AV_CH_FRONT_RIGHT_OF_CENTER)
AV_CH_LAYOUT_7POINT1 = (AV_CH_LAYOUT_5POINT1|AV_CH_BACK_LEFT|AV_CH_BACK_RIGHT)
AV_CH_LAYOUT_7POINT1_WIDE = (AV_CH_LAYOUT_5POINT1|AV_CH_FRONT_LEFT_OF_CENTER|AV_CH_FRONT_RIGHT_OF_CENTER)
AV_CH_LAYOUT_7POINT1_WIDE_BACK = (AV_CH_LAYOUT_5POINT1_BACK|AV_CH_FRONT_LEFT_OF_CENTER|AV_CH_FRONT_RIGHT_OF_CENTER)
AV_CH_LAYOUT_OCTAGONAL = (AV_CH_LAYOUT_5POINT0|AV_CH_BACK_LEFT|AV_CH_BACK_CENTER|AV_CH_BACK_RIGHT)
AV_CH_LAYOUT_HEXADECAGONAL = (AV_CH_LAYOUT_OCTAGONAL|AV_CH_WIDE_LEFT|AV_CH_WIDE_RIGHT|AV_CH_TOP_BACK_LEFT|AV_CH_TOP_BACK_RIGHT|AV_CH_TOP_BACK_CENTER|AV_CH_TOP_FRONT_CENTER|AV_CH_TOP_FRONT_LEFT|AV_CH_TOP_FRONT_RIGHT)
AV_CH_LAYOUT_STEREO_DOWNMIX = (AV_CH_STEREO_LEFT|AV_CH_STEREO_RIGHT)

channel_layout_map = {
    # (nb_channels, layout): "name",
    (1, AV_CH_LAYOUT_MONO): "mono",
    (2, AV_CH_LAYOUT_STEREO): "stereo",
    (3, AV_CH_LAYOUT_2POINT1): "2.1",
    (3, AV_CH_LAYOUT_SURROUND): "3.0",
    (3, AV_CH_LAYOUT_2_1): "3.0(back)",
    (4, AV_CH_LAYOUT_4POINT0): "4.0",
    (4, AV_CH_LAYOUT_QUAD): "quad",
    (4, AV_CH_LAYOUT_2_2): "quad(side)",
    (4, AV_CH_LAYOUT_3POINT1): "3.1",
    (5, AV_CH_LAYOUT_5POINT0_BACK): "5.0",
    (5, AV_CH_LAYOUT_5POINT0): "5.0(side)",
    (5, AV_CH_LAYOUT_4POINT1): "4.1",
    (6, AV_CH_LAYOUT_5POINT1_BACK): "5.1",
    (6, AV_CH_LAYOUT_5POINT1): "5.1(side)",
    (6, AV_CH_LAYOUT_6POINT0): "6.0",
    (6, AV_CH_LAYOUT_6POINT0_FRONT): "6.0(front)",
    (6, AV_CH_LAYOUT_HEXAGONAL): "hexagonal",
    (7, AV_CH_LAYOUT_6POINT1): "6.1",
    (7, AV_CH_LAYOUT_6POINT1_BACK): "6.1(back)",
    (7, AV_CH_LAYOUT_6POINT1_FRONT): "6.1(front)",
    (7, AV_CH_LAYOUT_7POINT0): "7.0",
    (7, AV_CH_LAYOUT_7POINT0_FRONT): "7.0(front)",
    (8, AV_CH_LAYOUT_7POINT1): "7.1",
    (8, AV_CH_LAYOUT_7POINT1_WIDE_BACK): "7.1(wide)",
    (8, AV_CH_LAYOUT_7POINT1_WIDE): "7.1(wide-side)",
    (8, AV_CH_LAYOUT_OCTAGONAL): "octagonal",
    (16, AV_CH_LAYOUT_HEXADECAGONAL): "hexadecagonal",
    (2, AV_CH_LAYOUT_STEREO_DOWNMIX): "downmix",
}

channel_names = {
    # number: ("name", "description"),
    1: ("FR", "front right"),
    2: ("FC", "front center"),
    3: ("LFE", "low frequency"),
    4: ("BL", "back left"),
    5: ("BR", "back right"),
    6: ("FLC", "front left-of-center"),
    7: ("FRC", "front right-of-center"),
    8: ("BC", "back center"),
    9: ("SL", "side left"),
    10: ("SR", "side right"),
    11: ("TC", "top center"),
    12: ("TFL", "top front left"),
    13: ("TFC", "top front center"),
    14: ("TFR", "top front right"),
    15: ("TBL", "top back left"),
    16: ("TBC", "top back center"),
    17: ("TBR", "top back right"),
    29: ("DL", "downmix left"),
    30: ("DR", "downmix right"),
    31: ("WL", "wide left"),
    32: ("WR", "wide right"),
    33: ("SDL", "surround direct left"),
    34: ("SDR", "surround direct right"),
    35: ("LFE2", "low frequency 2"),
}

def av_bprint_channel_layout(layout):
    if layout.name:
        return layout.name
    s = f'{len(layout.channels)} channels'
    if layout.channels:
        s += ' ({})'.format(
            '+'.join(channel.name for channel in layout.channels))
    return s

class UncheckedFraction(collections.namedtuple(
        'UncheckedFraction',
        (
            'numerator',
            'denominator',
        ),
        )):
    pass

def av_reduce(value, vmax):
    # returns (den == 0, Fraction)
    a0 = UncheckedFraction(0, 1)
    a1 = UncheckedFraction(1, 0)
    num = value.numerator
    den = value.denominator
    sign = (num < 0) != (den < 0)
    gcd = av_gcd(abs(num), abs(den))

    if gcd:
        num = abs(num) // gcd
        den = abs(den) // gcd
    if num <= vmax and den <= vmax:
        a1 = UncheckedFraction(num, den)
        den = 0

    while den:
        x = num // den
        next_den = num - den * x
        a2n = x * a1.numerator + a0.numerator
        a2d = x * a1.denominator + a0.denominator

        if a2n > vmax or a2d > vmax:
            if a1.numerator:
                x = (vmax - a0.numerator) // a1.numerator
            if a1.denominator:
                x = min(x, (vmax - a0.denominator) // a1.denominator)

            if den * (2 * x * a1.denominator + a0.denominator) > num * a1.denominator:
                a1 = UncheckedFraction(x * a1.numerator + a0.numerator, x * a1.denominator + a0.denominator)
            break

        a0 = a1
        a1 = UncheckedFraction(a2n, a2d)
        num = den
        den = next_den
    assert av_gcd(a1.numerator, a1.denominator) <= 1
    assert a1.numerator <= vmax and a1.denominator <= vmax

    dst_num = -a1.numerator if sign else a1.numerator
    dst_den = a1.denominator

    return (den == 0, Fraction(dst_num, dst_den) if dst_den != 0 else None)

from ctypes import c_uint64 as uint64_t

def ff_ctzll_c(v):
    """We use the De-Bruijn method outlined in:
    http://supertech.csail.mit.edu/papers/debruijn.pdf.
    """
    debruijn_ctz64 = (
        0, 1, 2, 53, 3, 7, 54, 27, 4, 38, 41, 8, 34, 55, 48, 28,
        62, 5, 39, 46, 44, 42, 22, 9, 24, 35, 59, 56, 49, 18, 29, 11,
        63, 52, 6, 26, 37, 40, 33, 47, 61, 45, 43, 21, 23, 58, 17, 10,
        51, 25, 36, 32, 60, 20, 57, 16, 50, 31, 19, 15, 30, 14, 13, 12
    )
    return debruijn_ctz64[uint64_t((uint64_t(v).value & uint64_t(-v).value) * 0x022FDD63CC95386D).value >> 58]

ff_ctzll = ff_ctzll_c

def av_gcd(a, b):
    """Stein's binary GCD algorithm:
    https://en.wikipedia.org/wiki/Binary_GCD_algorithm
    """
    if a == 0:
        return b
    if b == 0:
        return a
    za = ff_ctzll(a)
    zb = ff_ctzll(b)
    k  = min(za, zb)
    u = abs(a >> za)
    v = abs(b >> zb)
    while u != v:
        if u > v:
            u, v = v, u
        v -= u
        v >>= ff_ctzll(v)
    return uint64_t(uint64_t(u).value << k).value

INT_MAX = 2147483647

def av_guess_sample_aspect_ratio(av_stream, av_frame):
    undef = Fraction(0, 1)
    stream_sample_aspect_ratio = av_stream.sample_aspect_ratio if (av_stream) else undef
    codec_sample_aspect_ratio = av_stream.codec_context.sample_aspect_ratio if (av_stream and av_stream.codec_context) else undef
    frame_sample_aspect_ratio = av_frame.sample_aspect_ratio if (av_frame) else codec_sample_aspect_ratio

    _, stream_sample_aspect_ratio = av_reduce(stream_sample_aspect_ratio, INT_MAX)
    if stream_sample_aspect_ratio is None or stream_sample_aspect_ratio.numerator <= 0 or stream_sample_aspect_ratio.denominator <= 0:
        stream_sample_aspect_ratio = undef

    _, frame_sample_aspect_ratio = av_reduce(frame_sample_aspect_ratio, INT_MAX)
    if frame_sample_aspect_ratio is None or frame_sample_aspect_ratio.numerator <= 0 or frame_sample_aspect_ratio.denominator <= 0:
        frame_sample_aspect_ratio = undef

    if stream_sample_aspect_ratio.numerator:
        return stream_sample_aspect_ratio
    else:
        return frame_sample_aspect_ratio

def calc_packet_time(value, time_base):
    if value is None:
        return Value
    return Decimal(value) * time_base.numerator / time_base.denominator

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='Multimedia prober',
            contact='jst@qualipsoft.com',
            )

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
    pgroup.add_argument('--packets', default=0, type=int, help='number of packets to decode')
    pgroup.add_argument('--packet-order', default='file', choices=('file', 'pts'), help='packet order')

    pgroup = app.parser.add_argument_group('Extra information')
    pgroup.add_bool_argument('--pretty', help='Enable pretty output')
    pgroup.add_bool_argument('--dump', default=None, help='Dump (default action)')
    pgroup.add_bool_argument('--show-packets', '--show_packets', help='Emit like ffprobe -show_packets')
    pgroup.add_bool_argument('--show-frames', '--show_frames', help='Emit like ffprobe -show_frames')

    pgroup = app.parser.add_argument_group('Format context flags')
    ffmpeg.argparse_add_fflags_arguments(pgroup, encode=False)

    pgroup.add_argument('input_file', type=Path, help='file to probe')

    app.parse_args()

    if app.args.dump is None:
        app.args.dump = not (app.args.show_packets
                             or app.args.show_frames)

    do_frames = app.args.dump or app.args.show_frames
    do_packets = do_frames or app.args.dump or app.args.show_packets
    do_streams = app.args.dump
    do_side_data = app.args.dump or app.args.show_frames
    if do_packets or do_frames:
        p = ffprobe.PrintContext(pretty=app.args.pretty)

    def egetattr(obj, attr):
        try:
            return getattr(obj, attr)
        except Exception as e:
            return e

    av_file = av.open(os.fspath(app.args.input_file))
    av_file.max_analyze_duration = 0  # 10000000
    ffmpeg.fflags_arguments_to_av_file(av_file, app.args.fflags)
    # av_file.non_block = TODO
    # av_file.custom_io = TODO
    # av_file.flush_packets = TODO
    # av_file.bit_exact = TODO
    # av_file.mp4a_latm = TODO
    # av_file.priv_opt = TODO
    # av_file.shortest = TODO

    # TODO stream.codec_context.skip_frame = 'NONKEY'

    if app.args.dump:
        t = ', '.join([
            f'{attr}={egetattr(av_file, attr)}'
            for attr in [
                    'flags',
                    #flags:
                    # 'gen_pts',
                    # 'ign_dts',
                    # 'ign_idx',
                    # 'non_block',
                    # 'no_fill_in',
                    # 'no_parse',
                    # 'no_buffer',
                    # 'custom_io',
                    # 'discard_corrupt',
                    # 'flush_packets',
                    # 'bit_exact',
                    # 'mp4a_latm',
                    # 'sort_dts',
                    # 'priv_opt',
                    # 'keep_side_data',
                    # 'fast_seek',
                    # 'shortest',
                    # 'auto_bsf',
                    'bit_rate',
                    'container_options',
                    'duration',
                    'file',
                    'format',
                    'metadata',
                    'metadata_encoding',
                    'metadata_errors',
                    'name',
                    'open_timeout',
                    'options',
                    'read_timeout',
                    'size',
                    'start_time',
                    'stream_options',
                    #'streams',
                    'writeable',
                    #'close',
                    #'decode',
                    #'demux',
                    #'dumps_format',
                    #'seek',
            ]])
        print(f'File: {t}')

    if do_streams:
        av_streams = av_file.streams
        for istream, av_stream in enumerate(av_streams):

            if app.args.dump:
                t = ', '.join([
                    f'{attr}={egetattr(av_stream, attr)}'
                    for attr in [
                            'type',
                            'id',
                            'index',
                            'time_base',
                            'start_time',
                            'average_rate',
                            'base_rate',
                            #'codec_context',
                            #'container',
                            'disposition',
                            'duration',
                            #'encode', 'decode',
                            'frames',
                            'guessed_rate',
                            'language',
                            'metadata',
                            'profile',
                            #'seek',
                    ]])
                print(f'Stream #{istream}: {t}')

                codec_context = av_stream.codec_context
                t = ', '.join([
                    f'{attr}={egetattr(codec_context, attr)}'
                    for attr in [
                            'ac_pred',
                            'bit_rate',
                            'bit_rate_tolerance',
                            'bitexact',
                            'chunks',
                            #'close',
                            'closed_gop',
                            #'codec',
                            'codec_tag',
                            'coded_height',
                            'coded_width',
                            #'create',
                            #'decode',
                            'display_aspect_ratio',
                            'drop_changed',
                            'drop_frame_timecode',
                            #'encode',
                            'encoded_frame_count',
                            'export_mvs',
                            # TODO 'extradata',
                            'extradata_size',
                            'fast',
                            'flags',
                            'flags2',
                            'format',
                            'four_mv',
                            'framerate',
                            'global_header',
                            'gop_size',
                            'gray',
                            'has_b_frames',
                            'height',
                            'ignore_crop',
                            'interlaced_dct',
                            'interlaced_me',
                            'is_decoder',
                            'is_encoder',
                            'is_open',
                            'local_header',
                            'loop_filter',
                            'low_delay',
                            'max_bit_rate',
                            'name',
                            'no_output',
                            # 'open',
                            'options',
                            'output_corrupt',
                            # 'parse',
                            'pass1',
                            'pass2',
                            'pix_fmt',
                            'profile',
                            'psnr',
                            'qpel',
                            'qscale',
                            'rate',
                            'reformatter',
                            'ro_flush_noop',
                            'sample_aspect_ratio',
                            'show_all',
                            'skip_frame',
                            'skip_manual',
                            'thread_count',
                            'thread_type',
                            'ticks_per_frame',
                            'time_base',
                            'truncated',
                            'type',
                            'unaligned',
                            'width',
                    ]])
                print(f'  Codec context: {t}')
                # Codec context: ac_pred=False, bit_rate=None, bit_rate_tolerance=None, bitexact=False, chunks=False, closed_gop=False, codec=<av.codec.codec.Codec object at 0x7f7832401600>, codec_tag=, coded_height=480, coded_width=720, display_aspect_ratio=16/9, drop_changed=False, drop_frame_timecode=False, encoded_frame_count=0, export_mvs=False, extradata_size=152, fast=False, flags=NONE, flags2=NONE, format=<av.VideoFormat yuv420p, 720x480>, four_mv=False, framerate=89/3, global_header=False, gop_size=12, gray=False, has_b_frames=True, height=480, ignore_crop=False, interlaced_dct=False, interlaced_me=False, is_decoder=0, is_encoder=0, is_open=0, local_header=False, loop_filter=False, low_delay=False, max_bit_rate=None, name=mpeg2video, no_output=False, options={}, output_corrupt=False, pass1=False, pass2=False, pix_fmt=yuv420p, profile=None, psnr=False, qpel=False, qscale=False, rate=89/3, reformatter=None, ro_flush_noop=False, sample_aspect_ratio=32/27, show_all=False, skip_frame=DEFAULT, skip_manual=False, thread_count=0, thread_type=SLICE, ticks_per_frame=2, time_base=1001/60000, truncated=False, type=video, unaligned=False, width=720

                av_codec = codec_context.codec
                t = ', '.join([
                    f'{attr}={egetattr(av_codec, attr)}'
                    for attr in [
                            'type',
                            'audio_formats',
                            'audio_rates',
                            'auto_threads',
                            'avoid_probing',
                            'bitmap_sub',
                            'capabilities',
                            'channel_conf',
                            'delay',
                            'descriptor',
                            'dr1',
                            'draw_horiz_band',
                            'encoder_reordered_opaque',
                            'experimental',
                            'frame_rates',
                            'frame_threads',
                            'hardware',
                            'hwaccel',
                            'hwaccel_vdpau',
                            'hybrid',
                            'id',
                            'intra_only',
                            'is_decoder',
                            'is_encoder',
                            'long_name',
                            'lossless',
                            'lossy',
                            'name',
                            'neg_linesizes',
                            'param_change',
                            'properties',
                            'reorder',
                            'slice_threads',
                            'small_last_frame',
                            'subframes',
                            'text_sub',
                            'truncated',
                            'variable_frame_size',
                            'video_formats',
                            #'create',
                    ]])
                print(f'    Codec: {t}')

    if do_packets:
        # av_packets = av_file.demux(av_stream)
        av_packets = av_file.demux()
        if app.args.packet_order == 'pts':
            av_packets = av_reorder_packets(av_packets)
        for ipacket, av_packet in enumerate(av_packets):
            av_stream = av_packet.stream

            if app.args.dump:
                t = ', '.join([
                    f'{attr}={egetattr(av_packet, attr)}'
                    for attr in [
                            'pos',
                            'dts', 'pts',
                            #'buffer_ptr', 'buffer_size',
                            #'decode', 'decode_one',
                            'duration',
                            'is_corrupt',
                            'is_keyframe',
                            'size',
                            #'stream',
                            'stream_index',
                            'time_base',
                            #'to_bytes',
                            #'update',
                    ]])
                print(f'  Packet #{ipacket}: {t}')
                #print(f'  Packet #{ipacket}: {dir(av_packet)}')

            if app.args.show_packets:
                print(f'[PACKET]')
                codec_type = av_stream.type
                if codec_type:
                    p.print_str('codec_type', codec_type)
                else:
                    p.print_str_opt('codec_type', 'unknown')
                p.print_int('stream_index', av_packet.stream_index)
                p.print_ts('pts', av_packet.pts)
                p.print_time('pts_time', av_packet.pts, av_stream.time_base)
                p.print_ts('dts', av_packet.dts)
                p.print_time('dts_time', av_packet.dts, av_stream.time_base)
                p.print_duration_ts('duration', av_packet.duration)
                p.print_duration_time('duration_time', av_packet.duration, av_stream.time_base)
                # DEPRECATED p.print_duration_ts('convergence_duration', av_packet.convergence_duration)
                # DEPRECATED p.print_duration_time('convergence_duration_time', av_packet.convergence_duration, av_stream.time_base)
                p.print_val('size', av_packet.size, p.unit_byte_str)
                if av_packet.pos != -1:  # 0x-8000000000000000 | -9223372036854775808 ?
                    p.print_fmt('pos', '%d', av_packet.pos)
                else:
                    p.print_str_opt('pos', 'N/A')
                p.print_fmt('flags', '%c%c',
                            'K' if av_packet.is_keyframe else '_',
                            'D' if av_packet.is_discard else '_')
                print(f'[/PACKET]')

            if do_frames:
                av_frames = av_packet.decode()
                #print(f'av_frames: {av_frames}')
                for iframe, av_frame in enumerate(av_frames):

                    if do_side_data:
                        side_datas = getattr(av_frame, 'side_data', [])

                    if app.args.dump:
                        av_frame_attrs = [
                            'format',
                            'index',
                            'key_frame',
                            'pts', 'dts',
                            'time', 'time_base',
                            'best_effort_timestamp',
                            'pkt_duration',
                            'pkt_pos',
                            'is_corrupt',
                            #'planes',
                            #'side_data',
                            #'from_ndarray',
                            #'to_nd_array',
                            #'to_ndarray
                        ]
                        if av_stream.type == 'video':
                            av_frame_attrs += [
                                    'width', 'height',
                                    'interlaced_frame',
                                    'top_field_first',
                                    'repeat_pict',
                                    'pict_type',
                                    'coded_picture_number',
                                    'display_picture_number',
                                    'interlaced_frame',
                                    'color_range',
                                    'color_space',
                                    'color_primaries',
                                    'color_trc',
                                    'chroma_location',
                                    #'reformat',
                                    #'from_image',
                                    #'to_image',
                                    #'to_rgb',
                            ]
                        elif av_stream.type == 'audio':
                            av_frame_attrs += [
                                'layout',
                                'rate',
                                'sample_rate',
                                'samples',
                            ]
                        elif av_stream.type == 'subtitle':
                            av_frame_attrs += [
                                'packet',
                                'rects',
                                'start_display_time',
                                'end_display_time',
                            ]
                        else:
                            print(f'    Frame #{iframe}: {dir(av_frame)}')
                        t = ', '.join([
                            f'{attr}={egetattr(av_frame, attr)}'
                            for attr in av_frame_attrs])
                        print(f'    Frame #{iframe}: {t}')

                        for iside_data, side_data in enumerate(side_datas):
                            t = ', '.join([
                                f'{attr}={egetattr(side_data, attr)}'
                                for attr in [
                                        'buffer_size',
                                        'type',
                                        #'buffer_ptr',
                                        #'to_bytes',
                                        #'update',
                                ]])
                            print(f'      Side data ${iside_data}: {t}, byte: {side_data.to_bytes()}')

                    if app.args.show_frames:
                        print(f'[FRAME]')
                        codec_type = av_stream.type
                        if codec_type:
                            p.print_str('media_type', codec_type)
                        else:
                            p.print_str_opt('media_type', 'unknown')
                        p.print_int('stream_index', av_stream.index)
                        p.print_int('key_frame', av_frame.key_frame)
                        p.print_ts('pkt_pts', av_frame.pts)
                        p.print_time('pkt_pts_time', av_frame.pts, av_stream.time_base)
                        p.print_ts('pkt_dts', av_frame.dts)  # Note: av_frame.dts = libav.Frame.pkt_dts
                        p.print_time('pkt_dts_time', av_frame.dts, av_stream.time_base)
                        p.print_ts('best_effort_timestamp', av_frame.best_effort_timestamp)
                        p.print_time('best_effort_timestamp_time', av_frame.best_effort_timestamp, av_stream.time_base)
                        p.print_duration_ts('pkt_duration', av_frame.pkt_duration)
                        p.print_duration_time('pkt_duration_time', av_frame.pkt_duration, av_stream.time_base)
                        if av_frame.pkt_pos != -1:
                            p.print_fmt('pkt_pos', '%d', av_frame.pkt_pos)
                        else:
                            p.print_str_opt('pkt_pos', 'N/A')
                        if av_frame.pkt_size != -1:
                            p.print_val('pkt_size', av_frame.pkt_size, p.unit_byte_str)
                        else:
                            p.print_str_opt('pkt_size', 'N/A')
                        if codec_type == 'video':
                            p.print_int('width', av_frame.width)
                            p.print_int('height', av_frame.height)
                            format_name = getattr(av_frame.format, 'name', None)
                            if format_name:
                                p.print_str('pix_fmt', format_name)
                            else:
                                p.print_str_opt('pix_fmt', 'unknown')

                            sar = av_guess_sample_aspect_ratio(av_stream, av_frame)
                            if sar.numerator:
                                p.print_q('sample_aspect_ratio', sar, ':')
                            else:
                                p.print_str_opt('sample_aspect_ratio', 'N/A')
                            p.print_fmt('pict_type', '%s', av_frame.pict_type)
                            p.print_int('coded_picture_number', av_frame.coded_picture_number)
                            p.print_int('display_picture_number', av_frame.display_picture_number)
                            p.print_int('interlaced_frame', av_frame.interlaced_frame)
                            p.print_int('top_field_first', av_frame.top_field_first)
                            p.print_int('repeat_pict', av_frame.repeat_pict)
                            p.print_color_range(av_frame.color_range)
                            p.print_color_space(av_frame.color_space)
                            p.print_primaries(av_frame.color_primaries)
                            p.print_color_trc(av_frame.color_trc)
                            p.print_chroma_location(av_frame.chroma_location)
                        elif codec_type == 'audio':
                            format_name = getattr(av_frame.format, 'name', None)
                            if format_name:
                                p.print_str('sample_fmt', format_name)
                            else:
                                p.print_str_opt('sample_fmt', 'unknown')
                            p.print_int('nb_samples', av_frame.samples)
                            p.print_int('channels', av_frame.channels)
                            if av_frame.channel_layout:
                                p.print_str('channel_layout', av_bprint_channel_layout(av_frame.layout))
                            else:
                                p.print_str_opt('channel_layout', 'unknown')
                        for side_data in side_datas:
                            if app.args.show_frames:
                                print('[SIDE_DATA]')
                                if isinstance(side_data.type, int):
                                    name = side_data.type
                                else:
                                    name = side_data.type.name
                                ffname = {
                                    'PANSCAN': "AVPanScan",
                                    'A53_CC': 'ATSC A53 Part 4 Closed Captions',
                                    'STEREO3D': "Stereo 3D",
                                    'MATRIXENCODING': "AVMatrixEncoding",
                                    'DOWNMIX_INFO': "Metadata relevant to a downmix procedure",
                                    'REPLAYGAIN': "AVReplayGain",
                                    'DISPLAYMATRIX': "3x3 displaymatrix",
                                    'AFD': "Active format description",
                                    'MOTION_VECTORS': "Motion vectors",
                                    'SKIP_SAMPLES': "Skip samples",
                                    'AUDIO_SERVICE_TYPE': "Audio service type",
                                    'MASTERING_DISPLAY_METADATA': "Mastering display metadata",
                                    'GOP_TIMECODE': "GOP timecode",
                                    'SPHERICAL': "Spherical Mapping",
                                    'CONTENT_LIGHT_LEVEL': "Content light level metadata",
                                    'ICC_PROFILE': "ICC profile",
                                    # More from av_frame_side_data_name:
                                    #    case AV_FRAME_DATA_S12M_TIMECODE:               return "SMPTE 12-1 timecode";
                                    ##if FF_API_FRAME_QP
                                    16: "QP table properties",  # AV_FRAME_DATA_QP_TABLE_PROPERTIES
                                    17: "QP table data",  # AV_FRAME_DATA_QP_TABLE_DATA
                                    ##endif
                                    #    case AV_FRAME_DATA_DYNAMIC_HDR_PLUS: return "HDR Dynamic Metadata SMPTE2094-40 (HDR10+)";
                                    #    case AV_FRAME_DATA_REGIONS_OF_INTEREST: return "Regions Of Interest";
                                    #    case AV_FRAME_DATA_VIDEO_ENC_PARAMS:            return "Video encoding parameters";
                                }.get(name, name)
                                p.print_str("side_data_type", ffname or 'unknown')
                                if name == 'DISPLAYMATRIX' and side_data.buffer_size >= 9 * 4:
                                    pass
                                    #    p.writer_print_integers(w, "displaymatrix", sd->data, 9, " %11d", 3, 4, 1);
                                    #    p.print_int("rotation", av_display_rotation_get((int32_t *)sd->data));
                                elif name == 'GOP_TIMECODE' and side_data.buffer_size >= 8:
                                    #
                                    # The GOP timecode in 25 bit timecode format. Data format is 64-bit integer.
                                    # This is set on the first frame of a GOP that has a temporal reference of 0.
                                    #
                                    tc25bit, = struct.unpack('<Q', side_data.to_bytes())
                                    def av_timecode_make_mpeg_tc_string(tc25bit):
                                        return '%02d:%02d:%02d%c%02d' % (
                                            tc25bit >> 19 & 0x1f,                 # 5-bit hours
                                            tc25bit >> 13 & 0x3f,                 # 6-bit minutes
                                            tc25bit >> 6 & 0x3f,                  # 6-bit seconds
                                            ';' if (tc25bit & 1 << 24) else ':',  # 1-bit drop flag
                                            tc25bit & 0x3f,                       # 6-bit frames
                                        )
                                    p.print_str("timecode", av_timecode_make_mpeg_tc_string(tc25bit))
                                elif name == 'STEREO3D':
                                    pass
                                    #    const AVStereo3D *stereo = (AVStereo3D *)sd->data;
                                    #    p.print_str("type", av_stereo3d_type_name(stereo->type));
                                    #    p.print_int("inverted", !!(stereo->flags & AV_STEREO3D_FLAG_INVERT));
                                elif name == 'SPHERICAL':
                                    pass
                                    #    const AVSphericalMapping *spherical = (AVSphericalMapping *)sd->data;
                                    #    p.print_str("projection", av_spherical_projection_name(spherical->projection));
                                    #    if (spherical->projection == AV_SPHERICAL_CUBEMAP) {
                                    #        p.print_int("padding", spherical->padding);
                                    #    } else if (spherical->projection == AV_SPHERICAL_EQUIRECTANGULAR_TILE) {
                                    #        size_t l, t, r, b;
                                    #        av_spherical_tile_bounds(spherical, par->width, par->height,
                                    #                                 &l, &t, &r, &b);
                                    #        p.print_int("bound_left", l);
                                    #        p.print_int("bound_top", t);
                                    #        p.print_int("bound_right", r);
                                    #        p.print_int("bound_bottom", b);
                                    #    }
                                    #    p.print_int("yaw", (double) spherical->yaw / (1 << 16));
                                    #    p.print_int("pitch", (double) spherical->pitch / (1 << 16));
                                    #    p.print_int("roll", (double) spherical->roll / (1 << 16));
                                elif name == 'SKIP_SAMPLES' and side_data.buffer_size == 10:
                                    pass
                                    #    p.print_int("skip_samples",    AV_RL32(sd->data));
                                    #    p.print_int("discard_padding", AV_RL32(sd->data + 4));
                                    #    p.print_int("skip_reason",     AV_RL8(sd->data + 8));
                                    #    p.print_int("discard_reason",  AV_RL8(sd->data + 9));
                                elif name == 'MASTERING_DISPLAY_METADATA':
                                    pass
                                    #    AVMasteringDisplayMetadata *metadata = (AVMasteringDisplayMetadata *)sd->data;
                                    #    if (metadata->has_primaries) {
                                    #        p.print_q("red_x", metadata->display_primaries[0][0], '/');
                                    #        p.print_q("red_y", metadata->display_primaries[0][1], '/');
                                    #        p.print_q("green_x", metadata->display_primaries[1][0], '/');
                                    #        p.print_q("green_y", metadata->display_primaries[1][1], '/');
                                    #        p.print_q("blue_x", metadata->display_primaries[2][0], '/');
                                    #        p.print_q("blue_y", metadata->display_primaries[2][1], '/');
                                    #        p.print_q("white_point_x", metadata->white_point[0], '/');
                                    #        p.print_q("white_point_y", metadata->white_point[1], '/');
                                    #    }
                                    #    if (metadata->has_luminance) {
                                    #        p.print_q("min_luminance", metadata->min_luminance, '/');
                                    #        p.print_q("max_luminance", metadata->max_luminance, '/');
                                    #    }
                                elif name == 'CONTENT_LIGHT_LEVEL':
                                    pass
                                    #    AVContentLightMetadata *metadata = (AVContentLightMetadata *)sd->data;
                                    #    p.print_int("max_content", metadata->MaxCLL);
                                    #    p.print_int("max_average", metadata->MaxFALL);
                                #} else if (sd->type == AV_PKT_DATA_DOVI_CONF) {
                                #    AVDOVIDecoderConfigurationRecord *dovi = (AVDOVIDecoderConfigurationRecord *)sd->data;
                                #    p.print_int("dv_version_major", dovi->dv_version_major);
                                #    p.print_int("dv_version_minor", dovi->dv_version_minor);
                                #    p.print_int("dv_profile", dovi->dv_profile);
                                #    p.print_int("dv_level", dovi->dv_level);
                                #    p.print_int("rpu_present_flag", dovi->rpu_present_flag);
                                #    p.print_int("el_present_flag", dovi->el_present_flag);
                                #    p.print_int("bl_present_flag", dovi->bl_present_flag);
                                #    p.print_int("dv_bl_signal_compatibility_id", dovi->dv_bl_signal_compatibility_id);
                                #}
                                print('[/SIDE_DATA]')
                        print(f'[/FRAME]')

            if app.args.packets and (ipacket + 1) >= app.args.packets:
                break

if __name__ == "__main__":
    main()
