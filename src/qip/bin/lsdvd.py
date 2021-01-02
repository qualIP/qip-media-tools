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

# References:
#   http://stnsoft.com/DVD/index.html
#   http://dvdnav.mplayerhq.hu/dvdinfo/index.html

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

from pathlib import Path
import argparse
import enum
import itertools
import json
import logging
import os
import reprlib
import socket
import sys
import types
log = logging.getLogger(__name__)
reprlib.aRepr.maxdict = 100

from qip.app import app
from qip.cdrom import cdrom_ready, read_dvd_title
from qip.isolang import isolang, IsoLang
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
        version='1.1',
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

    pgroup.add_bool_argument('--check-cdrom-ready', default=False, help='check CDROM readiness')
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
    pgroup.add_argument('--format', default='human', choices=('human', 'perl', 'python', 'ruby', 'xml', 'json'), help='Output format')
    pgroup.add_argument('-Oh', dest='format', default=argparse.SUPPRESS, action='store_const', const='human', help='Output as human readable')
    pgroup.add_argument('-Op', dest='format', default=argparse.SUPPRESS, action='store_const', const='perl', help='Output as human Perl')
    pgroup.add_argument('-Oy', dest='format', default=argparse.SUPPRESS, action='store_const', const='python', help='Output as Python')
    pgroup.add_argument('-Or', dest='format', default=argparse.SUPPRESS, action='store_const', const='ruby', help='Output as Ruby')
    pgroup.add_argument('-Ox', dest='format', default=argparse.SUPPRESS, action='store_const', const='xml', help='Output as XML')
    pgroup.add_argument('-Oj', dest='format', default=argparse.SUPPRESS, action='store_const', const='json', help='Output as JSON')

    pgroup.add_argument('device', default=argparse.SUPPRESS, nargs='?', help='specify alternate cdrom device')

    app.parse_args()

    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    if app.args.check_cdrom_ready:
        if not cdrom_ready(app.args.device,
                           timeout=app.args.cdrom_ready_timeout,
                           progress_bar=False):
            raise Exception("CDROM not ready")

    if app.args.show_all:
        app.args.show_audio = True
        app.args.show_cells = True
        app.args.show_angles = True
        app.args.show_chapters = True
        app.args.show_subpictures = True
        app.args.show_palette = True
        app.args.show_video = True

    dvd_info = lsdvd(device=app.args.device,
                     show_all=app.args.show_all,
                     show_audio=app.args.show_audio,
                     show_cells=app.args.show_cells,
                     show_angles=app.args.show_angles,
                     show_chapters=app.args.show_chapters,
                     show_subpictures=app.args.show_subpictures,
                     show_palette=app.args.show_palette,
                     show_video=app.args.show_video,
                     target_title=app.args.target_title,
                     )

    if app.args.format == 'human':
        ohuman_print(dvd_info)
    elif app.args.format == 'perl':
        ocode_print(perl_syntax, dvd_info)
    elif app.args.format == 'python':
        #ocode_print(python_syntax, dvd_info)
        print(repr(json_encode(dvd_info)))
    elif app.args.format == 'ruby':
        ocode_print(ruby_syntax, dvd_info)
    elif app.args.format == 'xml':
        ocode_print(xml_syntax, dvd_info)
    elif app.args.format == 'json':
        json.dump(json_encode(dvd_info), sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        raise NotImplementedError(app.args.format)

dvdAudioIds = {
    0: 0x80,
    1: 0,
    2: 0xC0,
    3: 0xC0,
    4: 0xA0,
    5: 0,
    6: 0x88,
}

dvdFpss = libdvdread.dvdFpss

def dvd_lang_code_to_str(u16_lang_code):
    u16_lang_code = socket.ntohs(u16_lang_code)
    lang_code = chr(u16_lang_code & 0xff) + chr(u16_lang_code >> 8)
    return lang_code

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

def lsdvd(device,
          show_all=True,
          show_audio=False, show_cells=False, show_angles=False, show_chapters=False, show_subpictures=False, show_palette=False, show_video=False,
          target_title=None,
          ):

    if show_all:
        show_audio = True
        show_cells = True
        show_angles = True
        show_chapters = True
        show_subpictures = True
        show_palette = True
        show_video = True

    max_length = Timestamp(0)
    longest_track = None

    dvd_reader = libdvdread.dvd_reader(device)
    ifo_zero = dvd_reader.open_ifo(0)

    ifos = [ifo_zero] + list(itertools.repeat(None, ifo_zero.vts_atrt.nr_of_vtss))

    for i in range(1, ifo_zero.vts_atrt.nr_of_vtss + 1):
        try:
            ifos[i] = dvd_ifo = dvd_reader.open_ifo(i)
        except Exception:
            if target_title is not None and target_title == i:
                raise

    num_titles = ifo_zero.tt_srpt.nr_of_srpts
    if target_title is not None:
        if not (0 <= target_title < num_titles):
            raise ValueError(f'Only {num_titles} on this disc!')

    title = read_dvd_title(dvd_reader.device)

    vmgi_mat = ifo_zero.vmgi_mat

    dvd_info = types.SimpleNamespace()
    dvd_info.discinfo = types.SimpleNamespace()
    dvd_info.discinfo.device = dvd_reader.device
    dvd_info.discinfo.disc_title = title
    dvd_info.discinfo.vmg_id = vmgi_mat.vmg_identifier
    dvd_info.discinfo.provider_id = vmgi_mat.provider_identifier

    dvd_info.title_count = num_titles
    dvd_info.titles = list(itertools.repeat(None, num_titles))

    for j in range(num_titles):
        if target_title is not None and target_title != j + 1:
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
            dvd_title.general.playback_time = libdvdread.dvd_time_to_Timestamp(pgc.playback_time)
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
        if show_video:
            dvd_title.parameter = types.SimpleNamespace()
            dvd_title.parameter.vts = title_set_nr
            dvd_title.parameter.ttn = ifo_zero.tt_srpt.get_title(j).vts_ttn
            dvd_title.parameter.fps = dvdFpss[(pgc.playback_time.frame_u & 0xc0) >> 6]

            dvd_title.parameter.mpeg_version = {
                0: 'mpeg1',
                1: 'mpeg2',
            }[video_attr.mpeg_version]
            dvd_title.parameter.format = {
                0: 'NTSC',
                1: 'PAL',
                2: 'reserved(2)',
                3: 'reserved(3)',
            }[video_attr.video_format]
            dvd_title.parameter.aspect = {
                0: Ratio(4, 3),
                1: 'reserved(1)',
                2: 'reserved(2)',
                3: Ratio(16, 9),
            }[video_attr.display_aspect_ratio]
            dvd_title.parameter.df = set()
            if video_attr.permitted_df & 0x1 == 0:
                dvd_title.parameter.df.add('Letterbox')
            if video_attr.permitted_df & 0x2 == 0:
                dvd_title.parameter.df.add('Pan and Scan')
            if dvd_title.parameter.format == 'NTSC':
                dvd_title.parameter.line21_cc_1 = video_attr.line21_cc_1
                dvd_title.parameter.line21_cc_2 = video_attr.line21_cc_2
            dvd_title.parameter.width, dvd_title.parameter.height = {
                'NTSC': {
                    0: (720, 480),
                    1: (704, 480),
                    2: (352, 480),
                    3: (352, 240),
                    4: ('reserved(4)', 'reserved(4)'),
                    5: ('reserved(5)', 'reserved(5)'),
                    6: ('reserved(6)', 'reserved(6)'),
                    7: ('reserved(7)', 'reserved(7)'),
                },
                'PAL': {
                    0: (720, 576),
                    1: (704, 576),
                    2: (352, 576),
                    3: (352, 288),
                    4: ('reserved(4)', 'reserved(4)'),
                    5: ('reserved(5)', 'reserved(5)'),
                    6: ('reserved(6)', 'reserved(6)'),
                    7: ('reserved(7)', 'reserved(7)'),
                },
            }[dvd_title.parameter.format][video_attr.picture_size]
            dvd_title.parameter.letterboxed = {
                0: 'full screen',
                1: 'top and bottom cropped',
            }[video_attr.letterboxed]
            if dvd_title.parameter.format == 'PAL':
                dvd_title.parameter.film_mode = {
                    0: 'camera',
                    1: 'film',
                }[video_attr.film_mode]

        # PALETTE
        if show_palette:
            palsize = 16
            dvd_title.palette = [
                pgc.get_palette(i)
                for i in range(palsize)]

        # ANGLES
        if show_angles:
            dvd_title.angle_count = ifo_zero.tt_srpt.get_title(j).nr_of_angles

        # AUDIO
        if show_audio:
            dvd_title.audiostreams = list(itertools.repeat(None, dvd_title.audiostream_count_reported))
            for i in range(dvd_title.audiostream_count_reported):
                if (pgc.get_audio_control(i) & 0x8000) == 0:
                    continue
                dvd_title.audiostreams[i] = dvd_audiostream = types.SimpleNamespace()
                audio_attr = vtsi_mat.get_vts_audio_attr(i)
                dvd_audiostream.format = {
                    0: 'ac3',
                    1: None,  # TODO ???
                    2: 'mpeg1',
                    3: 'mpeg2ext',
                    4: 'lpcm',
                    5: 'sdds',  # TODO ???
                    6: 'dts',
                    7: None,  # TODO ???
                }[audio_attr.audio_format]
                dvd_audiostream.multichannel_extension = audio_attr.multichannel_extension != 0  # lsdvd 1.0
                dvd_audiostream.lang_type = {
                    0: 'unspecified',
                    1: 'language',
                    2: None,  # TODO ???
                    3: None,  # TODO ???
                }[audio_attr.lang_type]
                if dvd_audiostream.lang_type == 'lang_type':
                    lang_code = dvd_lang_code_to_str(audio_attr.lang_code)
                else:
                    lang_code = None
                dvd_audiostream.langcode = lang_code
                dvd_audiostream.language = isolang(lang_code) if lang_code else None
                dvd_audiostream.ap_mode = {
                    0: 'unspecified',
                    1: 'karaoke',
                    2: 'surround',
                    3: None,  # TODO ???
                }[audio_attr.application_mode]
                if dvd_audiostream.format in ('mpeg1', 'mpeg2ext'):
                    # TODO http://stnsoft.com/DVD/ifo.html does not specify these for mpeg1/mpeg2ext
                    dvd_audiostream.quantization = {
                        0: 'no-drc',
                        1: 'drc',
                        2: None,  # TODO ???
                        3: None,  # TODO ???
                    }[audio_attr.quantization]
                elif dvd_audiostream.format in ('lpcm'):
                    dvd_audiostream.quantization = {
                        0: '16bit',
                        1: '20bit',
                        2: '24bit',
                        3: 'drc',
                    }[audio_attr.quantization]
                else:
                    dvd_audiostream.quantization = None
                dvd_audiostream.frequency = {
                    0: 48000,
                    1: 96000,
                }[audio_attr.sample_frequency]
                dvd_audiostream.unknown1 = audio_attr.unknown1  # lsdvd 1.0
                dvd_audiostream.channels = audio_attr.channels + 1
                dvd_audiostream.lang_extension = audio_attr.lang_extension  # lsdvd 1.0
                # code_extension: See SRPM #17 http://dvdnav.mplayerhq.hu/dvdinfo/sprm.html
                dvd_audiostream.content = {
                    0: 'unspecified',
                    1: 'normal',
                    2: 'visually-impaired',
                    3: 'director\'s comments',
                    4: 'alternate director\'s comments',
                }.get(audio_attr.code_extension, None)
                dvd_audiostream.unknown3 = audio_attr.unknown3  # lsdvd 1.0
                dvd_audiostream.streamid = dvdAudioIds[audio_attr.audio_format] + i  # TODO Wrong?
                if dvd_audiostream.ap_mode == 'karaoke':
                    dvd_audiostream.unknown4 = audio_attr.app_info.karaoke.unknown4
                    dvd_audiostream.channel_assignment = {
                        0: '1+1 (not valid)',
                        1: '1/0 (not valid)',
                        2: '2/0 L,R',
                        3: '3/0 L,M,R',
                        4: '2/1 L,R,V1',
                        5: '3/1 L,M,R,V1',
                        6: '2/2 L,R,V1,V2',
                        7: '3/2 L,M,R,V1,V2',
                    }[audio_attr.app_info.karaoke.channel_assignment]
                    dvd_audiostream.karaoke_version = audio_attr.app_info.karaoke.karaoke_version
                    dvd_audiostream.mc_intro = audio_attr.app_info.karaoke.mc_intro == 1
                    dvd_audiostream.karaoke_mode = {
                        0: 'solo',
                        1: 'duet',
                    }[audio_attr.app_info.karaoke.karaoke_mode]
                elif dvd_audiostream.ap_mode == 'surround':
                    dvd_audiostream.unknown5 = audio_attr.app_info.surround.unknown5
                    dvd_audiostream.dolby_encoded = audio_attr.app_info.surround.dolby_encoded == 1
                    dvd_audiostream.unknown6 = audio_attr.app_info.surround.unknown6

        # CELLS
        if show_cells or show_chapters:
            dvd_title.cells = list(itertools.repeat(None, dvd_title.cell_count))
            for cell in range(dvd_title.cell_count):
                dvd_title.cells[cell] = dvd_cell = types.SimpleNamespace()
                dvd_cell.playback_time = libdvdread.dvd_time_to_Timestamp(pgc.get_cell_playback(cell).playback_time)
                dvd_cell.first_sector = pgc.get_cell_playback(cell).first_sector
                dvd_cell.last_sector = pgc.get_cell_playback(cell).last_sector

        # CHAPTERS
        if show_chapters:
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
        if show_subpictures:
            dvd_title.subtitles = list(itertools.repeat(None, dvd_title.subtitle_count))
            for i in range(dvd_title.subtitle_count):
                if (pgc.get_subp_control(i) & 0x80000000) == 0:
                    continue
                subp_attr = vtsi_mat.get_vts_subp_attr(i)
                dvd_title.subtitles[i] = dvd_subtitle = types.SimpleNamespace()
                dvd_subtitle.lang_type = {
                    0: 'unspecified',
                    1: 'language',
                    2: 'other',
                    3: None,  # TODO ???
                }[subp_attr.type]
                if dvd_subtitle.lang_type == 'language':
                    lang_code = dvd_lang_code_to_str(subp_attr.lang_code)
                else:
                    lang_code = None
                dvd_subtitle.langcode = lang_code
                dvd_subtitle.language = isolang(lang_code) if lang_code else None
                dvd_subtitle.lang_extension = subp_attr.lang_extension
                # code_extension: See SRPM #19 http://dvdnav.mplayerhq.hu/dvdinfo/sprm.html
                dvd_subtitle.content = {
                    0: 'unspecified',
                    1: 'normal',
                    2: 'large',
                    3: 'children\'s',
                    4: 'reserved(4)',
                    5: 'normal CC',
                    6: 'large CC',
                    7: 'children\'s CC',
                    8: 'reserved(8)',
                    9: 'forced',
                    10: 'reserved(10)',
                    11: 'reserved(11)',
                    12: 'reserved(12)',
                    13: 'director\'s comments',
                    14: 'large director\'s comments',
                    15: 'children\'s director\'s comments',
                }[subp_attr.code_extension]
                dvd_subtitle.streamid = 0x20 + i

    if target_title is None:
        dvd_info.longest_track = longest_track

    return dvd_info

def json_encode(obj):
    if obj is None or isinstance(obj, (str, int)):
        return obj
    if isinstance(obj, types.SimpleNamespace):
        obj = vars(obj)
    if isinstance(obj, dict):
        return {k: json_encode(v) for k, v in obj.items()}
    if isinstance(obj, set):
        obj = sorted(obj)
    if isinstance(obj, (tuple, list)):
        return [json_encode(e) for e in obj]
    if isinstance(obj, (FrameRate, Ratio)):
        return str(obj)
    if isinstance(obj, Path):
        return os.fspath(obj)
    if isinstance(obj, Timestamp):
        return str_Timestamp(obj)
    if isinstance(obj, IsoLang):
        return obj.name
    raise NotImplementedError(type(obj))

def ohuman_print(dvd_info):

    print(f'Disc Title: {dvd_info.discinfo.disc_title}')

    for j in range(dvd_info.title_count):
        if app.args.target_title is None or app.args.target_title == j + 1:
            dvd_title = dvd_info.titles[j]
            if not dvd_title:
                continue

            # GENERAL
            print('Title: %d, Length: %s, ' % (
                j+1,
                str_Timestamp(dvd_title.general.playback_time),
            ), end='')
            print('Chapters: %d, Cells: %d, ' % (
                dvd_title.chapter_count,
                dvd_title.cell_count,
            ), end='')
            print('Audio streams: %d, Subpictures: %d' % (
                dvd_title.audiostream_count,
                dvd_title.subtitle_count,
            ), end='')
            print('')

            # VIDEO
            if app.args.show_video:
                print('\tVTS: %d, TTN: %d, ' % (
                    dvd_title.parameter.vts,
                    dvd_title.parameter.ttn,
                ), end='')
                if dvd_title.parameter.fps is None:
                    print('FPS: None, ', end='')
                else:
                    print('FPS: %.2f, ' % (
                        dvd_title.parameter.fps,
                    ), end='')
                print('Mode: %s, Format: %s, Aspect ratio: %s, ' % (
                    dvd_title.parameter.mpeg_version,
                    dvd_title.parameter.format,
                    dvd_title.parameter.aspect,
                ), end='')
                print('Size: %sx%s, ' % (
                    dvd_title.parameter.width,
                    dvd_title.parameter.height,
                ), end='')
                print('DF: %s, ' % (
                    ' + '.join(sorted(dvd_title.parameter.df or ('None',))),
                ), end='')
                print('Letterboxed: %s' % (
                    dvd_title.parameter.letterboxed,
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
                    print('Channels: %d, AP: %s, ' % (
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
                    print('\tChapter: %d, Length: %s, Start Cell: %d' % (
                        i + 1,
                        str_Timestamp(dvd_chapter.playback_time),
                        dvd_chapter.startcell,
                    ))

            # CELLS
            if app.args.show_cells:
                for i, dvd_cell in enumerate(dvd_title.cells):
                    print('\tCell: %d, Length: %s' % (
                        i + 1,
                        str_Timestamp(dvd_cell.playback_time),
                    ))

            # SUBTITLES
            if app.args.show_subpictures:
                for i, dvd_subtitle in enumerate(dvd_title.subtitles):
                    if dvd_subtitle is None:
                        continue
                    print('\tSubtitle: %d, ' % (
                        i + 1,
                    ), end='')
                    if dvd_subtitle.lang_type == 'language':
                        print('Language: %s - %s, ' % (
                            dvd_subtitle.langcode,
                            dvd_subtitle.language and dvd_subtitle.language.name,
                        ), end='')
                    else:
                        print('Language: %s, ' % (
                            dvd_subtitle.lang_type,
                        ), end='')
                    print('Content: %s, ' % (
                        dvd_subtitle.content,
                    ), end='')
                    print('Stream id: 0x%x, ' % (
                        dvd_subtitle.streamid,
                    ), end='')
                    print('')

    if app.args.target_title is None:
        print('Longest track: %d' % (
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
                            f.DEF("mpeg_version", "'%s'", dvd_title.parameter.mpeg_version)
                            f.DEF("format", "'%s'", dvd_title.parameter.format)
                            f.DEF("aspect", "'%s'", dvd_title.parameter.aspect)
                            if dvd_title.parameter.format == 'NTSC':
                                f.DEF("line21_cc_1", "%d", dvd_title.parameter.line21_cc_1)
                                f.DEF("line21_cc_2", "%d", dvd_title.parameter.line21_cc_2)
                            f.DEF("width", "%s", dvd_title.parameter.width)
                            f.DEF("height", "%s", dvd_title.parameter.height)
                            f.DEF("df", "'%s'", ', '.join(sorted(dvd_title.parameter.df)))
                            if dvd_title.parameter.format == 'PAL':
                                f.DEF("film_mode", "'%s'", dvd_title.parameter.film_mode)

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
