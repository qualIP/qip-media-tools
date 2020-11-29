#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

# DVD info lister
# 
# Copyright (C) 2020 Jean-Sebastien Trottier
#
# Based on the original lsdvd:
#     lsdvd 0.18 - GPL Copyright (c) 2002-2005, 2014 "Written" by Chris Phillips <acid_kewpie@users.sf.net>
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation;

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

from pathlib import Path
import argparse
import enum
import itertools
import os
import reprlib
import sys
import types
reprlib.aRepr.maxdict = 100

import logging
log = logging.getLogger(__name__)

from qip.app import app
from qip.cdrom import cdrom_ready, read_dvd_title
from qip.isolang import isolang
from qip.mm import FrameRate
from qip.utils import Ratio, Timestamp
from qip.ocode import perl_syntax, python_syntax, ruby_syntax
import qip.libdvdread as libdvdread

def _resolved_Path(path):
    return Path(path).resolve()

@app.main_wrapper
def main():

    # https://sourceforge.net/projects/lsdvd/

    app.init(
        version='1.0',
        description='DVD info lister',
        contact='jst@qualipsoft.com',
        parser_suppress_option_strings={'-c',},
    )

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    #pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
    pgroup.add_argument('--dry-run',  dest='dry_run', action='store_true', help='dry-run mode')
    pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    #xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--verbose',  dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    #xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')
    xgroup.add_argument('--debug', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

    pgroup.add_bool_argument('--check-cdrom-ready', default=True, help='check CDROM readiness')
    pgroup.add_argument('--cdrom-ready-timeout', default=24, type=int, help='CDROM readiness timeout')
    pgroup.add_argument('--device', default=Path(os.environ.get('CDROM', '/dev/cdrom')), type=_resolved_Path, help='specify alternate cdrom device')

    pgroup.add_argument('--target-title', '-t', default=None, type=int, help='Target title')

    pgroup = app.parser.add_argument_group('Extra information')
    pgroup.add_bool_argument('--show-audio', '-a', default=False, help='Show audio streams')
    pgroup.add_bool_argument('--show-cells', '-d', default=False, help='Show cells')
    pgroup.add_bool_argument('--show-angles', '-n', default=False, help='Show angles')
    pgroup.add_bool_argument('--show-chapters', '-c', default=False, help='Show chapters')
    pgroup.add_bool_argument('--show-subpictures', '-s', default=False, help='Show subpictures')
    pgroup.add_bool_argument('--show-palette', '-P', default=False, help='Show palette')
    pgroup.add_bool_argument('--show-video', '-v', default=False, help='Show video')
    pgroup.add_bool_argument('--show-all', '-x', default=False, help='Show all information')

    pgroup = app.parser.add_argument_group('Formatting')
    pgroup.add_argument('--format', default='human', choices=('human', 'perl', 'python', 'json', 'ruby', 'xml'), help='Output format')
    pgroup.add_argument('-Oh', dest='format', default=argparse.SUPPRESS, action='store_const', const='human', help='Output as human readable')
    pgroup.add_argument('-Op', dest='format', default=argparse.SUPPRESS, action='store_const', const='perl', help='Output as human Perl')
    pgroup.add_argument('-Oy', dest='format', default=argparse.SUPPRESS, action='store_const', const='json', help='Output as Python (Json)')
    pgroup.add_argument('-Or', dest='format', default=argparse.SUPPRESS, action='store_const', const='ruby', help='Output as Ruby')
    pgroup.add_argument('-Ox', dest='format', default=argparse.SUPPRESS, action='store_const', const='xml', help='Output as XML')

    pgroup.add_argument('device', default=argparse.SUPPRESS, nargs='?', help='specify alternate cdrom device')

    app.parse_args()

    if app.args.format == 'python':
        app.args.format = 'json'
    if app.args.show_all:
        app.args.show_audio = True
        app.args.show_cells = True
        app.args.show_angles = True
        app.args.show_chapters = True
        app.args.show_subpictures = True
        app.args.show_palette = True
        app.args.show_video = True

    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    lsdvd(app.args.device)

dvdVideoFormats = {
    0: 'NTSC',
    1: 'PAL',
}

dvdAspectRatios = {
    0: Ratio(4, 3),
    1: Ratio(16, 9),
    2: None,  # TODO ?/?
    3: Ratio(16, 9),
}

dvdQuantizations = {
    0: '16bit',
    1: '20bit',
    2: '24bit',
    3: 'drc',
}

# TODO Unused
#dvdMpegVersions = {
#    0: 'mpeg1',
#    1: 'mpeg2',
#}

# 28.9.2003: The European chicken run title has height index 3, and
# 576 lines seems right, mplayer -vop cropdetect shows from 552 to
# 576 lines.  What the correct value is for index 2 is harder to say
dvdVideoHeights = {
    0: 480,
    1: 576,
    2: None,  # TODO ???
    3: 576,
}
dvdVideoWidths = {
    0: 720,
    1: 704,
    2: 352,
    3: 352,
}

dvdPermittedDfs = {
    0: {'Pan and Scan', 'Letterbox',},
    1: {'Pan and Scan',},
    2: {'Letterbox',},
    3: None,  # TODO ?
}

dvdAudioFormats = {
    0: 'ac3',
    1: None,  # TODO ???
    2: 'mpeg1',
    3: 'mpeg2',
    4: 'lpcm',
    5: 'sdds',
    6: 'dts',
}

dvdAudioIds = {
    0: 0x80,
    1: 0,
    2: 0xC0,
    3: 0xC0,
    4: 0xA0,
    5: 0,
    6: 0x88,
}

# 28.9.2003: Chicken run again, it has frequency index of 1.
# According to dvd::rip the frequency is 48000
dvdSampleFreqs = {
    0: 48000,
    1: 96000,
}

dvdAudioTypes = {
    0: 'Undefined',
    1: 'Normal',
    2: 'Impaired',
    3: 'Comments1',
    4: 'Comments2',
}

dvdSubtitleContentTypes = {
    0: 'Undefined',
    1: 'Normal',
    2: 'Large',
    3: 'Children',
    4: 'reserved(4)',
    5: 'Normal_CC',
    6: 'Large_CC',
    7: 'Children_CC',
    8: 'reserved(8)',
    9: 'Forced',
    10: 'reserved(10)',
    11: 'reserved(11)',
    12: 'reserved(12)',
    13: 'Director',
    14: 'Large_Director',
    15: 'Children_Director',
}

dvdFpss = {
    0: None,  # TODO
    1: FrameRate(25000, 1000),
    2: None,  # TODO
    3: FrameRate(30000, 1001),
}

def dvd_time_to_Timestamp(dt: 'dvd_time_t *') -> Timestamp:
    hour, minute, second, frame_u = dt.hour, dt.minute, dt.second, dt.frame_u
    ms = (((hour & 0xf0) >> 3) * 5 + (hour & 0x0f)) * 3600000
    ms += (((minute & 0xf0) >> 3) * 5 + (minute & 0x0f)) * 60000
    ms += (((second & 0xf0) >> 3) * 5 + (second & 0x0f)) * 1000

    fps = dvdFpss[(frame_u & 0xc0) >> 6]
    if fps is not None:
        ms += (((frame_u & 0x30) >> 3) * 5 + (frame_u & 0x0f)) * 1000.0 / fps

    ts = Timestamp(ms / 1000.0)
    return ts

def str_Timestamp(ts):
    s = ts.seconds
    m = s // 60
    s = s - m * 60
    h = m // 60
    m = m - h * 60
    s = '%.3f' % (s,)
    if s[1] == '.':
        s = '0'+ s
    return '%02d:%02d:%s' % (h, m, s)

def lsdvd(device):

    max_length = Timestamp(0)
    longest_track = None

    if not cdrom_ready(device, timeout=app.args.cdrom_ready_timeout, progress_bar=False):
        raise Exception("CDROM not ready")

    dvd = libdvdread.dvd_reader(device)
    ifo_zero = dvd.open_ifo(0)

    ifos = [ifo_zero] + list(itertools.repeat(None, ifo_zero.vts_atrt.nr_of_vtss))

    for i in range(1, ifo_zero.vts_atrt.nr_of_vtss + 1):
        try:
            ifos[i] = dvd_ifo = dvd.open_ifo(i)
        except Exception:
            if app.args.target_title is not None and app.args.target_title == i:
                raise

    num_titles = ifo_zero.tt_srpt.nr_of_srpts
    if app.args.target_title is not None:
        if not (0 <= app.args.target_title < num_titles):
            raise ValueError(f'Only {num_titles} on this disc!')

    title = read_dvd_title(dvd.device)

    vmgi_mat = ifo_zero.vmgi_mat

    dvd_info = types.SimpleNamespace()
    dvd_info.discinfo = types.SimpleNamespace()
    dvd_info.discinfo.device = dvd.device
    dvd_info.discinfo.disc_title = title
    dvd_info.discinfo.vmg_id = vmgi_mat.vmg_identifier
    dvd_info.discinfo.provider_id = vmgi_mat.provider_identifier

    dvd_info.title_count = num_titles
    dvd_info.titles = list(itertools.repeat(None, num_titles))

    for j in range(num_titles):
        if app.args.target_title is not None and app.args.target_title != j + 1:
            continue

        title_set_nr = ifo_zero.tt_srpt.get_title(j).title_set_nr
        ifo = ifos[title_set_nr]
        assert ifo is not None
        if ifo is None:
            continue
        assert ifo.vtsi_mat is not None
        if ifo.vtsi_mat is None:
            continue

        dvd_info.titles[j] = dvd_title = types.SimpleNamespace()

        # GENERAL
        vtsi_mat   = ifo.vtsi_mat
        vts_pgcit  = ifo.vts_pgcit
        video_attr = vtsi_mat.vts_video_attr
        vts_ttn = ifo_zero.tt_srpt.get_title(j).vts_ttn
        vmgi_mat = ifo_zero.vmgi_mat
        pgc = vts_pgcit.get_pgci_srp(ifo.vts_ptt_srpt.get_title(vts_ttn - 1).get_ptt(0).pgcn - 1).pgc
        dvd_title.general = types.SimpleNamespace()
        dvd_title.general.vts_id = vtsi_mat.vts_identifier
        dvd_title.chapter_count_reported = (ifo_zero.tt_srpt.get_title(j).nr_of_ptts)
        if pgc.cell_playback is None or pgc.program_map is None:
            if False:
                dvd_title.general.playback_time = Timestamp(0)
                dvd_title.chapter_count = 0
                dvd_title.cell_count = 0
                dvd_title.audiostream_count_reported = 0
                dvd_title.audiostream_count = 0
                dvd_title.subtitle_count_reported = 0
                dvd_title.subtitle_count = 0
        else:
            dvd_title.general.playback_time = dvd_time_to_Timestamp(pgc.playback_time)
            dvd_title.chapter_count = pgc.nr_of_programs
            dvd_title.cell_count = pgc.nr_of_cells
            dvd_title.audiostream_count_reported = vtsi_mat.nr_of_vts_audio_streams
            dvd_title.audiostream_count = sum(
                1 if (pgc.get_audio_control(k) & 0x8000) != 0 else 0
                for k in range(dvd_title.audiostream_count_reported))
            dvd_title.subtitle_count_reported = vtsi_mat.nr_of_vts_subp_streams
            dvd_title.subtitle_count = 0
            dvd_title.subtitle_count = sum(
                1 if (pgc.get_subp_control(k) & 0x80000000) != 0 else 0
                for k in range(dvd_title.subtitle_count_reported))
            if dvd_title.general.playback_time > max_length:
                max_length = dvd_title.general.playback_time
                longest_track = j + 1

        # VIDEO
        if app.args.show_video:
            dvd_title.parameter = types.SimpleNamespace()
            dvd_title.parameter.vts = title_set_nr
            dvd_title.parameter.ttn = ifo_zero.tt_srpt.get_title(j).vts_ttn
            dvd_title.parameter.fps = dvdFpss[(pgc.playback_time.frame_u & 0xc0) >> 6]
            dvd_title.parameter.format = dvdVideoFormats[video_attr.video_format]
            dvd_title.parameter.aspect = dvdAspectRatios[video_attr.display_aspect_ratio]
            dvd_title.parameter.width = dvdVideoWidths[video_attr.picture_size]
            dvd_title.parameter.height = dvdVideoHeights[video_attr.video_format]  # TODO Wrong?
            dvd_title.parameter.df = dvdPermittedDfs[video_attr.permitted_df]

        # PALETTE
        if app.args.show_palette:
            palsize = 16
            dvd_title.palette = [
                pgc.get_palette(i)
                for i in range(palsize)]

        # ANGLES
        if app.args.show_angles:
            dvd_title.angle_count = ifo_zero.tt_srpt.get_title(j).nr_of_angles

        # AUDIO
        if app.args.show_audio:
            dvd_title.audiostreams = list(itertools.repeat(None, dvd_title.audiostream_count_reported))
            for i in range(dvd_title.audiostream_count_reported):
                if (pgc.get_audio_control(i) & 0x8000) == 0:
                    continue
                dvd_title.audiostreams[i] = dvd_audiostream = types.SimpleNamespace()
                audio_attr = vtsi_mat.get_vts_audio_attr(i)
                lang_code = f'{chr(audio_attr.lang_code >> 8)}{chr(audio_attr.lang_code & 0xff)}'.strip(chr(0)) or None
                dvd_audiostream.langcode = lang_code
                dvd_audiostream.language = isolang(lang_code) if lang_code else None
                dvd_audiostream.format = dvdAudioFormats[audio_attr.audio_format]
                dvd_audiostream.frequency = dvdSampleFreqs[audio_attr.sample_frequency]
                dvd_audiostream.quantization = dvdQuantizations[audio_attr.quantization]
                dvd_audiostream.channels = audio_attr.channels + 1
                dvd_audiostream.ap_mode = audio_attr.application_mode
                dvd_audiostream.content = dvdAudioTypes[audio_attr.code_extension]
                dvd_audiostream.streamid = dvdAudioIds[audio_attr.audio_format] + i  # TODO Wrong?
                dvd_audiostream.lang_type = audio_attr.lang_type  # lsdvd 1.0
                dvd_audiostream.multichannel_extension = audio_attr.multichannel_extension != 0  # lsdvd 1.0
                dvd_audiostream.unknown1 = audio_attr.unknown1  # lsdvd 1.0
                dvd_audiostream.lang_extension = audio_attr.lang_extension  # lsdvd 1.0
                dvd_audiostream.unknown3 = audio_attr.unknown3  # lsdvd 1.0

        # CELLS
        if app.args.show_cells or app.args.show_chapters:
            dvd_title.cells = list(itertools.repeat(None, dvd_title.cell_count))
            for cell in range(dvd_title.cell_count):
                dvd_title.cells[cell] = dvd_cell = types.SimpleNamespace()
                dvd_cell.playback_time = dvd_time_to_Timestamp(pgc.get_cell_playback(cell).playback_time)
                dvd_cell.first_sector = pgc.get_cell_playback(cell).first_sector
                dvd_cell.last_sector = pgc.get_cell_playback(cell).last_sector

        # CHAPTERS
        if app.args.show_chapters:
            cell = 0
            dvd_title.chapters = list(itertools.repeat(None, dvd_title.chapter_count))
            for chap in range(dvd_title.chapter_count):
                dvd_title.chapters[chap] = dvd_chapter = types.SimpleNamespace()
                dvd_chapter.playback_time = Timestamp(0)
                inext = pgc.get_program_map(chap + 1)
                if chap == pgc.nr_of_programs - 1:
                    inext = pgc.nr_of_cells + 1
                while cell < inext - 1:
                    dvd_cell = dvd_title.cells[cell]
                    dvd_chapter.playback_time += dvd_cell.playback_time
                    cell += 1
                dvd_chapter.startcell = pgc.get_program_map(chap)

        # SUBTITLES
        if app.args.show_subpictures:
            dvd_title.subtitles = list(itertools.repeat(None, dvd_title.subtitle_count))
            for i in range(dvd_title.subtitle_count):
                if (pgc.get_subp_control(i) & 0x80000000) == 0:
                    continue
                subp_attr = vtsi_mat.get_vts_subp_attr(i)
                lang_code = f'{chr(subp_attr.lang_code >> 8)}{chr(subp_attr.lang_code & 0xff)}'.strip(chr(0)) or None
                dvd_title.subtitles[i] = dvd_subtitle = types.SimpleNamespace()
                dvd_subtitle.langcode = lang_code
                dvd_subtitle.language = isolang(lang_code)
                dvd_subtitle.content = dvdSubtitleContentTypes[subp_attr.code_extension]
                dvd_subtitle.streamid = 0x20 + i

    if app.args.target_title is None:
        dvd_info.longest_track = longest_track

    if app.args.format == 'human':
        ohuman_print(dvd_info)
    elif app.args.format == 'perl':
        ocode_print(perl_syntax, dvd_info)
    elif app.args.format == 'json':
        ocode_print(python_syntax, dvd_info)
    elif app.args.format == 'ruby':
        ocode_print(ruby_syntax, dvd_info)
    elif app.args.format == 'xml':
        ocode_print(xml_syntax, dvd_info)
    else:
        raise NotImplementedError(app.args.format)

def ohuman_print(dvd_info):

    print(f'Disc Title: {dvd_info.discinfo.disc_title}')

    for j in range(dvd_info.title_count):
        if app.args.target_title is None or app.args.target_title == j + 1:
            dvd_title = dvd_info.titles[j]
            if not dvd_title:
                continue

            # GENERAL
            print('Title: %02d, Length: %s ' % (
                j+1,
                str_Timestamp(dvd_title.general.playback_time),
            ), end='')
            print('Chapters: %02d, Cells: %02d, ' % (
                dvd_title.chapter_count,
                dvd_title.cell_count,
            ), end='')
            print('Audio streams: %02d, Subpictures: %02d' % (
                dvd_title.audiostream_count,
                dvd_title.subtitle_count,
            ), end='')
            print('')

            # VIDEO
            if app.args.show_video:
                print('\tVTS: %02d, TTN: %02d, ' % (
                    dvd_title.parameter.vts,
                    dvd_title.parameter.ttn,
                ), end='')
                if dvd_title.parameter.fps is None:
                    print('FPS: None, ', end='')
                else:
                    print('FPS: %.2f, ' % (
                        dvd_title.parameter.fps,
                    ), end='')
                print('Format: %s, Aspect ratio: %s, ' % (
                    dvd_title.parameter.format,
                    dvd_title.parameter.aspect,
                ), end='')
                print('Width: %s, Height: %s, ' % (
                    dvd_title.parameter.width,
                    dvd_title.parameter.height,
                ), end='')
                print('DF: %s' % (
                    dvd_title.parameter.df or '?',
                ), end='')
                print('')

            # PALETTE
            if app.args.show_palette:
                print('\tPalette: ', end='')
                for dvd_palette in dvd_title.palette:
                    print('%06x ' % (
                        dvd_palette,
                    ), end='')
                print('')

            # ANGLES
            if app.args.show_angles:
                if dvd_title.angle_count:
                    print('\tNumber of Angles: %d' % (
                        dvd_title.angle_count,
                    ))

            # AUDIO
            if app.args.show_audio:
                for i, dvd_audiostream in enumerate(dvd_title.audiostreams):
                    if dvd_audiostream is None:
                        continue
                    print('\tAudio: %d, Language: %s - %s, ' % (
                        i + 1,
                        dvd_audiostream.langcode,
                        dvd_audiostream.language and dvd_audiostream.language.name,
                    ), end='')
                    print('Format: %s, ' % (
                        dvd_audiostream.format,
                    ), end='')
                    print('Frequency: %s, ' % (
                        dvd_audiostream.frequency,
                    ), end='')
                    print('Quantization: %s, ' % (
                        dvd_audiostream.quantization,
                    ), end='')
                    print('Channels: %d, AP: %d, ' % (
                        dvd_audiostream.channels,
                        dvd_audiostream.ap_mode,
                    ), end='')
                    print('Content: %s, ' % (
                        dvd_audiostream.content,
                    ), end='')
                    print('Stream id: 0x%x' % (
                        dvd_audiostream.streamid,
                    ), end='')
                    print('')

            # CHAPTERS
            if app.args.show_chapters:
                for i, dvd_chapter in enumerate(dvd_title.chapters):
                    print('\tChapter: %02d, Length: %s, Start Cell: %02d' % (
                        i + 1,
                        str_Timestamp(dvd_chapter.playback_time),
                        dvd_chapter.startcell,
                    ))

            # CELLS
            if app.args.show_cells:
                for i, dvd_cell in enumerate(dvd_title.cells):
                    print('\tCell: %02d, Length: %s' % (
                        i + 1,
                        str_Timestamp(dvd_cell.playback_time),
                    ))

            # SUBTITLES
            if app.args.show_subpictures:
                for i, dvd_subtitle in enumerate(dvd_title.subtitles):
                    if dvd_subtitle is None:
                        continue
                    print('\tSubtitle: %02d, Language: %s - %s, ' % (
                        i + 1,
                        dvd_subtitle.langcode,
                        dvd_subtitle.language and dvd_subtitle.language.name,
                    ), end='')
                    print('Content: %s, ' % (
                        dvd_subtitle.content,
                    ), end='')
                    print('Stream id: 0x%x, ' % (
                        dvd_subtitle.streamid,
                    ), end='')
                    print('')

    if app.args.target_title is None:
        print('Longest track: %02d' % (
            dvd_info.longest_track,
        ))

def ocode_print(syntax, dvd_info):
    f = syntax.Formatter()
    with f.START('lsdvd'):
        f.DEF("device", "'%s'", dvd_info.discinfo.device)
        f.DEF("title", "'%s'", dvd_info.discinfo.disc_title)
        f.DEF("vmg_id", "'%.12s'", dvd_info.discinfo.vmg_id)
        f.DEF("provider_id", "'%.32s'", dvd_info.discinfo.provider_id)

        # This should probably be "tracks":
        with f.ARRAY("track"):

            for j in range(dvd_info.title_count):
                if app.args.target_title is None or app.args.target_title == j + 1:
                    dvd_title = dvd_info.titles[j]
                    if not dvd_title:
                        continue

                    with f.HASH(None):
                        # GENERAL 
                        f.DEF("ix", "%d", j + 1)
                        f.DEF("length", "%.3f", dvd_title.general.playback_time)
                        f.DEF("vts_id", "'%s'", dvd_title.general.vts_id)

                        # VIDEO
                        if app.args.show_video:
                            f.DEF("vts", "%d", dvd_title.parameter.vts)
                            f.DEF("ttn", "%d", dvd_title.parameter.ttn)
                            f.DEF("fps", "%.2f", dvd_title.parameter.fps)
                            f.DEF("format", "'%s'", dvd_title.parameter.format)
                            f.DEF("aspect", "'%s'", dvd_title.parameter.aspect)
                            f.DEF("width", "%s", dvd_title.parameter.width)
                            f.DEF("height", "%s", dvd_title.parameter.height)
                            f.DEF("df", "'%s'", dvd_title.parameter.df)

                        # PALETTE
                        if app.args.show_palette:
                            with f.ARRAY("palette"):
                                for dvd_palette in dvd_title.palette:
                                    f.ADEF("'%06x'",  dvd_palette)

                        # ANGLES
                        if app.args.show_angles:
                            if dvd_title.angle_count:  # poor check, but there's no other info anyway.
                                f.DEF("angles", "%d", dvd_title.angle_count)

                        # AUDIO
                        if app.args.show_audio:
                            with f.ARRAY("audio"):
                                for i, dvd_audiostream in enumerate(dvd_title.audiostreams):
                                    if dvd_audiostream is None:
                                        continue
                                    with f.HASH(None):
                                        f.DEF("ix", "%d", i + 1)
                                        f.DEF("langcode", "'%s'", dvd_audiostream.langcode)
                                        f.DEF("language", "'%s'", dvd_audiostream.language and dvd_audiostream.language.name)
                                        f.DEF("format", "'%s'", dvd_audiostream.format)
                                        f.DEF("frequency", "%s", dvd_audiostream.frequency)
                                        f.DEF("quantization", "'%s'", dvd_audiostream.quantization)
                                        f.DEF("channels", "%d", dvd_audiostream.channels)
                                        f.DEF("ap_mode", "%d", dvd_audiostream.ap_mode)
                                        f.DEF("content", "'%s'", dvd_audiostream.content)
                                        f.DEF("streamid", "0x%x", dvd_audiostream.streamid)
                                        f.DEF("multichannel_extension", "%s", dvd_audiostream.multichannel_extension)  # lsdvd 1.0
                                        f.DEF("unknown1", "%d", dvd_audiostream.unknown1)  # lsdvd 1.0
                                        f.DEF("lang_extension", "%d", dvd_audiostream.lang_extension)  # lsdvd 1.0
                                        f.DEF("unknown3", "%d", dvd_audiostream.unknown3)  # lsdvd 1.0

                        # CHAPTERS
                        if app.args.show_chapters:
                            # This should probably be "chapters":
                            with f.ARRAY("chapter"):
                                for i, dvd_chapter in enumerate(dvd_title.chapters):
                                    with f.HASH(None):
                                        f.DEF("ix", "%d", i + 1)
                                        f.DEF("length", "%.3f", dvd_chapter.playback_time)
                                        f.DEF("startcell", "%d", dvd_chapter.startcell)

                        # CELLS
                        if app.args.show_cells:
                            with f.ARRAY("cell"):
                                for i, dvd_cell in enumerate(dvd_title.cells):
                                    with f.HASH(None):
                                        f.DEF("ix", "%d", i + 1)
                                        f.DEF("length", "%.3f", dvd_cell.playback_time)
                                        # added to get the size information
                                        f.DEF("first_sector", "%d", dvd_cell.first_sector)
                                        f.DEF("last_sector", "%d", dvd_cell.last_sector)

                        # SUBTITLES
                        if app.args.show_subpictures:
                            with f.ARRAY("subp"):
                                for i, dvd_subtitle in enumerate(dvd_title.subtitles):
                                    if dvd_subtitle is None:
                                        continue
                                    with f.HASH(None):
                                        f.DEF("ix", "%d", i + 1)
                                        f.DEF("langcode", "'%s'", dvd_subtitle.langcode)
                                        f.DEF("language", "'%s'", dvd_subtitle.language and dvd_subtitle.language.name)
                                        f.DEF("content", "'%s'", dvd_subtitle.content)
                                        f.DEF("streamid", "0x%x", dvd_subtitle.streamid)

        if app.args.target_title is None:
            f.DEF("longest_track", "%d", dvd_info.longest_track)

if __name__ == "__main__":
    main()
