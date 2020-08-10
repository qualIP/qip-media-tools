#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

from pathlib import Path
import argparse
import concurrent.futures
import contextlib
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
import xml.etree.ElementTree as ET
reprlib.aRepr.maxdict = 100

from qip import json
from qip.app import app
from qip.cmp import *
from qip.exec import *
from qip.file import *
from qip.mm import *
from qip.mp4 import Mpeg4ContainerFile, M4bFile, mp4chaps
from qip.matroska import MkaFile
from qip.parser import *
from qip.utils import byte_decode, save_and_restore_tcattr
import qip.mm
import qip.utils
Auto = qip.utils.Constants.Auto

# https://www.ffmpeg.org/ffmpeg.html

# times_1000 {{{

def times_1000(v):
    if type(v) is int:
        v *= 1000
    else:
        # 1E+3 = 1000 with precision of 1 so precision of v is not increased
        v = decimal.Decimal(v) * decimal.Decimal('1E+3')
        if v.as_tuple().exponent >= 0:
            v = int(v)
    return v

# }}}

# replace_html_entities {{{

def replace_html_entities(s):
    s = html.unescape(s)
    m = re.search(r'&\w+;', s)
    if m:
        raise ValueError('Unknown HTML entity: %s' % (m.group(0),))
    return s

# }}}

# get_audio_file_chapters {{{

def get_audio_file_chapters(snd_file, chapter_naming_format):
    chaps = []
    if not chaps and app.args.OverDrive_MediaMarkers:
        if hasattr(snd_file, 'OverDrive_MediaMarkers'):
            chaps = parse_OverDrive_MediaMarkers(snd_file.OverDrive_MediaMarkers)
    if not chaps and snd_file.file_name.suffix in qip.mm.get_mp4v2_app_support().extensions_can_read:
        try:
            chaps = snd_file.load_chapters()
        except subprocess.CalledProcessError:
            # TODO
            raise
    if not chaps:
        chaps.append(qip.mm.Chapter(
            start=0, end=None,
            title=get_audio_file_default_chapter(snd_file, chapter_naming_format=chapter_naming_format),
        ))
    return chaps

# }}}
# get_audio_file_default_chapter {{{

def get_audio_file_default_chapter(d, chapter_naming_format):
    if chapter_naming_format == 'default':
        if d.tags.contains(MediaTagEnum.title, strict=True):
            m = re.search(r'^Track \d+$', d.tags.title)
            if m:
                if d.tags.disk is not None and d.tags.disk != '1/1':
                    return get_audio_file_default_chapter(d, chapter_naming_format='disk-track')
                else:
                    return get_audio_file_default_chapter(d, chapter_naming_format='track')
            return d.tags.title
        if d.tags.track is not None:
            return get_audio_file_default_chapter(d, chapter_naming_format='disk-track')
        else:
            return get_audio_file_default_chapter(d, chapter_naming_format='title')
    if chapter_naming_format == 'title':
        if d.tags.contains(MediaTagEnum.title, strict=True):
            return d.tags.title
        return clean_audio_file_title(d, d.file_name.with_suffix('').name)
    if chapter_naming_format == 'track':
        track = d.tags.track
        if track is not None:
            return 'Track %0*d' % (len(str(d.tags.tracks or 1)), track)
        return get_audio_file_default_chapter(d, chapter_naming_format='title')
    if chapter_naming_format in ('disc', 'disk'):
        disk = d.tags.disk
        if disk is not None:
            return 'Disk %0*d' % (len(str(d.tags.disks or 1)), disk)
        return get_audio_file_default_chapter(d, chapter_naming_format='title')
    if chapter_naming_format in ('disc-track', 'disk-track'):
        if d.tags.disk is not None:
            return '%s - %s' % (
                get_audio_file_default_chapter(d, chapter_naming_format='disk'),
                get_audio_file_default_chapter(d, chapter_naming_format='track'),
            )
        return get_audio_file_default_chapter(d, chapter_naming_format='track')
    raise Exception('Invalid chapter naming format \'%s\'' % (chapter_naming_format,))

# }}}
# clean_audio_file_title {{{

def clean_audio_file_title(d, title):
    track = d.tags.track
    if track is not None:
        title = re.sub(fr'^0*{track}( *[:-] *)', '', title)
    m = re.search(r'^Chapter *0*(?P<chapter_no>\d+)$', title)
    if m:
        chapter_no = int(m.group('chapter_no'))
        title = f'Chapter {chapter_no}'
    return title

# }}}
# parse_OverDrive_MediaMarkers {{{

def parse_OverDrive_MediaMarkers(xml):
    markers = []
    root = ET.fromstring(xml)
    for nodeMarker in root.findall('Markers/Marker') or root.findall('Marker'):
        marker = {}
        bKeep = True
        for childNode in nodeMarker:
            tag = childNode.tag
            value = childNode.text
            if tag == 'Name':
                # "Chapter 1"
                if value.startswith('\xA0') or value.endswith(' continued'):
                    # Continuation
                    # "______Chapter 1 (05:58)" (\xA0 = &nbsp;, shown as "_")
                    # "Chapter 1 continued"
                    bKeep = False
                    break
            elif tag == 'Time':
                pass
            else:
                pass
            marker[tag] = value
        if bKeep:
            markers.append(marker)
    chaps = []
    for marker in markers:
        chap = qip.mm.Chapter(
            start=marker['Time'], end=None,
            title=marker['Name'],
        )
        # chap.OverDrive_MediaMarker = marker
        chaps.append(chap)
    return chaps

# }}}

# get_vbr_formats {{{

def get_vbr_formats():
    # List of possibly VBR formats
    return [
            'mp3',
            ]

# }}}

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='M4B Audiobook Maker',
            contact='jst@qualipsoft.com',
            )

    app.cache_dir = 'mkm4b-cache'  # in current directory!

    in_tags = TrackTags(contenttype='audiobook')

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
    pgroup.add_argument('--jobs', '-j', type=int, nargs='?', default=1, const=Auto, help='Specifies the number of jobs (threads) to run simultaneously')

    pgroup = app.parser.add_argument_group('Alternate Actions')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--ffmpegstats', dest='action', default=argparse.SUPPRESS, action='store_const', const='ffmpegstats', help='execute ffmpeg stats action only')
    xgroup.add_argument('--type-list', action=qip.mm.ArgparseTypeListAction)
    xgroup.add_argument('--genre-list', action=qip.mm.ArgparseGenreListAction)

    pgroup = app.parser.add_argument_group('Files')
    pgroup.add_argument('--single', action='store_true', help='create single audiobooks files')
    pgroup.add_argument('--output', '-o', dest='outputfile', default=argparse.SUPPRESS, type=Path, help='specify the output file name')
    pgroup.add_argument('--format', default=Auto, choices=('m4b', 'mka'), help='specify the output file format')

    pgroup = app.parser.add_argument_group('Compatibility')
    pgroup.add_bool_argument('--ipod-compat', default=False, help='iPod compatibility')
    pgroup.add_bool_argument('--itunes-compat', default=True, help='iTunes compatibility')

    pgroup = app.parser.add_argument_group('Chapters Control')
    pgroup.add_argument('--chapters', dest='chaptersfile', default=argparse.SUPPRESS, type=Path, help='specify the chapters file name')
    pgroup.add_argument('--no-chapters', default=False, action='store_true', help='do not generate chapters')
    pgroup.add_argument('--reuse-chapters', action='store_true', help='reuse chapters.txt file')
    pgroup.add_argument('--chapter-naming', dest='chapter_naming_format', default="default", help='chapters naming format',
            choices=["default", "title", "track", "disc", "disk", "disc-track", "disk-track"])
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--OverDrive-MediaMarkers', dest='OverDrive_MediaMarkers', default=True, action='store_true', help='use OverDrive MediaMarkers (default)')
    xgroup.add_argument('--no-OverDrive-MediaMarkers', dest='OverDrive_MediaMarkers', default=argparse.SUPPRESS, action='store_false', help='do not use OverDrive MediaMarkers')

    pgroup = app.parser.add_argument_group('Encoding')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--force-encode', dest='force_encode', default=False, action='store_true', help='force encoding (enable)')
    xgroup.add_argument('--no-force-encode', dest='force_encode', default=argparse.SUPPRESS, action='store_false', help='do not force encoding (default)')
    pgroup.add_argument('--bitrate', type=int, default=argparse.SUPPRESS, help='force the encoding bitrate')  # TODO support <int>k
    pgroup.add_argument('--target-bitrate', dest='target_bitrate', type=int, default=argparse.SUPPRESS, help='specify the resampling target bitrate')
    pgroup.add_argument('--channels', type=int, default=argparse.SUPPRESS, help='force the number of audio channels')
    pgroup.add_argument('--qaac', dest='use_qaac', default=True, action='store_true', help='use qaac, if available')
    pgroup.add_argument('--no-qaac', dest='use_qaac', default=argparse.SUPPRESS, action='store_false', help='do not use qaac')

    pgroup = app.parser.add_argument_group('Tags')
    pgroup.add_argument('--grouping', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--albumartist', '-R', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--albumtitle', '--album', '-A', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--artist', '-a', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--copyright', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
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

    app.parser.add_argument('inputfiles', nargs='*', default=None, help='input sound files')

    app.parse_args()

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'mkm4b'
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100
    # app.log.debug('get_sox_app_support: %r', qip.mm.get_sox_app_support())
    # app.log.debug('get_vbr_formats: %r', get_vbr_formats())
    # app.log.debug('get_mp4v2_app_support: %r', qip.mm.get_mp4v2_app_support())

    for prog in (
            'ffmpeg',  # ffmpeg | libav-tools
            'mp4chaps',  # mp4v2-utils
            'mp4tags',  # mp4v2-utils
            'mp4art',  # mp4v2-utils
            'mp4info',  # mp4v2-utils
            ):
        if not shutil.which(prog):
            raise Exception('%s: command not found' % (prog,))
    for prog in (
            'id3info',  # libid3-utils
            'id3v2',  # id3v2
            'soxi',  # sox
            'sox',  # sox
            'gm',  # graphicsmagick
            'file',
            ):
        if not shutil.which(prog):
            app.log.warning('%s: command not found; Functionality may be limited.', prog)

    if app.args.action == 'ffmpegstats':
        # {{{

        if not app.args.inputfiles:
            raise Exception('No input files provided')
        for inputfile in app.args.inputfiles:
            d = SoundFile.new_by_file_name(file_name=inputfile)
            qip.mm.get_audio_file_ffmpeg_stats(d)

        # }}}
    elif app.args.action == 'mkm4b':
        # {{{

        if not app.args.inputfiles:
            raise Exception('No input files provided')
        if app.args.single:
            for inputfile in app.args.inputfiles:
                mkm4b([inputfile], in_tags)
        else:
            mkm4b(app.args.inputfiles, in_tags)

        # }}}
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

def mkm4b(inputfiles, default_tags):
    exit_stack = contextlib.ExitStack()
    thread_executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=None if app.args.jobs is Auto else app.args.jobs)
    exit_stack.enter_context(thread_executor)

    if app.args.format is Auto:
        if 'outputfile' in app.args:
            m4b = SoundFile.new_by_file_name(app.args.outputfile)
        else:
            m4b = M4bFile(file_name=None)
    else:
        if app.args.format == 'm4b':
            m4b = M4bFile(file_name=None)
        elif app.args.format == 'mka':
            m4b = MkaFile(file_name=None)
        else:
            raise NotImplementedError(app.args.format)
    m4b.tags.update(default_tags)

    inputfiles = [
            inputfile if isinstance(inputfile, SoundFile) else SoundFile.new_by_file_name(file_name=inputfile)
            for inputfile in inputfiles]
    def task_extract_info(inputfile):
        if not inputfile.file_name.is_file():
            raise OSError(errno.ENOENT, 'No such file', inputfile.file_name)
        app.log.info('Reading %s...', inputfile)
        inputfile.extract_info(need_actual_duration=(len(inputfiles) > 1))
        #inputfile.tags.picture = None
        #app.log.debug(inputfile)
    with save_and_restore_tcattr():
        for x in thread_executor.map(task_extract_info, inputfiles):
            pass

    app.log.debug('inputfiles = %r', inputfiles)
    orig_inputfiles = inputfiles
    inputfiles = sorted(inputfiles, key=functools.cmp_to_key(qip.mm.soundfilecmp))
    if inputfiles != orig_inputfiles:
        app.log.warning("Rearranged list of input files!")

    for inputfile in inputfiles:
        if inputfile.tags[MediaTagEnum.title] is not None:
            inputfile.tags[MediaTagEnum.title] = clean_audio_file_title(inputfile, inputfile.tags[MediaTagEnum.title])

    if app.args.single:
        for tag1, tag2 in [
                [MediaTagEnum.title,       MediaTagEnum.title],
                [MediaTagEnum.subtitle,    MediaTagEnum.subtitle],
                [MediaTagEnum.artist,      MediaTagEnum.artist],
                [MediaTagEnum.disk,        MediaTagEnum.disk],
                [MediaTagEnum.track,       MediaTagEnum.track],
                ]:
            if m4b.tags[tag1] is None:
                if m4b.tags[tag2] is not None:
                    m4b.tags[tag1] = m4b.tags[tag2]
                elif inputfiles[0].tags[tag2] is not None:
                    m4b.tags[tag1] = inputfiles[0].tags[tag2]
    if True:
        for tag1, tag2 in [
            [MediaTagEnum.albumtitle,  MediaTagEnum.albumtitle],
            [MediaTagEnum.albumtitle,  MediaTagEnum.title],
            [MediaTagEnum.title,       MediaTagEnum.albumtitle],
            [MediaTagEnum.title,       MediaTagEnum.title],
            [MediaTagEnum.albumartist, MediaTagEnum.albumartist],
            [MediaTagEnum.albumartist, MediaTagEnum.artist],
            [MediaTagEnum.artist,      MediaTagEnum.albumartist],
            [MediaTagEnum.artist,      MediaTagEnum.artist],
            [MediaTagEnum.composer,    MediaTagEnum.composer],
            [MediaTagEnum.genre,       MediaTagEnum.genre],
            [MediaTagEnum.grouping,    MediaTagEnum.grouping],
            [MediaTagEnum.date,        MediaTagEnum.date],
            [MediaTagEnum.copyright,   MediaTagEnum.copyright],
            [MediaTagEnum.encodedby,   MediaTagEnum.encodedby],
            [MediaTagEnum.tool,        MediaTagEnum.tool],
            [MediaTagEnum.contenttype, MediaTagEnum.contenttype],
            ]:
            if m4b.tags[tag1] is None:
                if m4b.tags[tag2] is not None:
                    m4b.tags[tag1] = m4b.tags[tag2]
                elif inputfiles[0].tags[tag2] is not None:
                    m4b.tags[tag1] = inputfiles[0].tags[tag2]

    # m4b.file_name {{{
    if 'outputfile' in app.args:
        m4b.file_name = app.args.outputfile
    else:
        parts = []
        v = m4b.tags[MediaTagEnum.albumartist]
        if v:
            parts.append(v)
        if True or app.args.single:
            v = m4b.tags[MediaTagEnum.artist]
            if v:
                parts.append(v)
        v = m4b.tags[MediaTagEnum.albumtitle]
        assert v, '%r albumtitle not known' % (m4b,)
        if v:
            parts.append(v)
        if True or app.args.single:
            v = m4b.tags[MediaTagEnum.title]
            assert v, '%r title not known' % (m4b,)
            if v:
                parts.append(v)
        for i in range(len(parts)-2):  # skip last part XXXJST TODO why?
            parts[i] = re.sub(r' */ *', ' and ', parts[i])
        v = m4b.tags[MediaTagEnum.track]
        if v:
            parts.append('track%02d' % (v,))
        i = 0
        while i < len(parts)-1:  # skip last part
            if parts[i] == parts[i + 1]:
                del parts[i]
            else:
                i += 1
        m4b.file_name = clean_file_name(" - ".join(parts) + m4b._common_extensions[0])
    # }}}

    expected_duration = None
    chapters_file = TextFile(file_name=m4b.file_name.with_suffix('.chapters.txt'))
    if hasattr(app.args, 'chaptersfile'):
        if app.args.chaptersfile.samefile(chapters_file.file_name):
            app.log.info('Reusing %s...', chapters_file)
        else:
            app.log.info('Writing %s from %s...', chapters_file, app.args.chaptersfile)
            shutil.copyfile(app.args.chaptersfile, chapters_file.file_name)
    elif app.args.reuse_chapters and chapters_file.exists():
        app.log.info('Reusing %s...', chapters_file)
    elif app.args.no_chapters:
        app.log.info('Writing empty %s...', chapters_file)
        chapters_file.touch()
    else:
        app.log.info('Writing %s...', chapters_file)
        inputfile_to_chapters = {}
        def task_fill_inputfile_to_chapters(inputfile):
            nonlocal inputfile_to_chapters
            inputfile_to_chapters[inputfile.file_name] = get_audio_file_chapters(inputfile, chapter_naming_format=app.args.chapter_naming_format)
            print(f'inputfile_to_chapters[{inputfile.file_name}] = {inputfile_to_chapters[inputfile.file_name]!r}')
        for x in thread_executor.map(task_fill_inputfile_to_chapters, inputfiles):
            pass
        def body(fp):
            nonlocal expected_duration
            offset = qip.utils.Timestamp(0)
            for inputfile in inputfiles:
                for chap_info in inputfile_to_chapters[inputfile.file_name]:
                    print('%s %s' % (
                        mp4chaps.Timestamp(offset + chap_info.start),
                        replace_html_entities(chap_info.title),
                        ), file=fp)
                if len(inputfiles) == 1 and not hasattr(inputfile, 'duration'):
                    pass  # Ok... never mind
                else:
                    offset += inputfile.duration
            expected_duration = offset
        safe_write_file_eval(chapters_file, body, text=True)
    print('Chapters:')
    print(re.sub(r'^', '    ', safe_read_file(chapters_file), flags=re.MULTILINE))
    if expected_duration is not None:
        expected_duration = mp4chaps.Timestamp(expected_duration)
        app.log.info('Expected final duration: %s (%.3f seconds)', expected_duration, expected_duration)

    src_picture = m4b.tags.picture
    if isinstance(src_picture, qip.mm.PictureTagInfo):
        src_picture = m4b.file_name
    if not src_picture:
        if inputfiles[0].tags.picture:
            src_picture = inputfiles[0].tags.picture
            if isinstance(src_picture, qip.mm.PictureTagInfo):
                src_picture = inputfiles[0].file_name
        if getattr(inputfiles[0], 'num_cover', 0):
            src_picture = inputfiles[0].file_name
        else:
            for ext in ('.png', '.jpg', '.jpeg', '.gif'):
                test_src_picture = inputfiles[0].file_name.with_name('AlbumArt' + ext)
                if test_src_picture.exists():
                    src_picture = test_src_picture
                    break

    picture = None
    # select_src_picture {{{

    def select_src_picture(new_picture):
        nonlocal picture
        nonlocal src_picture
        if not new_picture:
            src_picture = None
            app.log.warning('No picture.')
            picture = None
        else:
            src_picture = new_picture
            app.log.info('Using picture from %s...', src_picture)
            picture = m4b.prep_picture(
                src_picture,
                yes=app.args.yes,
                ipod_compat=app.args.ipod_compat,
                keep_picture_file_name=m4b.file_name.with_suffix('.png'))

    # }}}
    select_src_picture(src_picture)

    # Sort tags
    # NOT: composer artist albumartist
    if False:
        # XXXJST
        for tag in (MediaTagEnum.title, MediaTagEnum.albumtitle, MediaTagEnum.show):
            sorttag = MediaTagEnum('sort' + tag.value)
            if sorttag not in m4b.tags and tag in m4b.tags:
                m = re.search(r'^(?P<a>.+) \((?P<b>.+) #(?P<n>\d+)\)$', m4b.tags[tag])
                if m:
                    m4b.tags[sorttag] = '{b} #{n!d:%02} - {a}'.format(m.groupdict())

    print("Tags:")
    for tag in set(MediaTagEnum) - set(MediaTagEnum.iTunesInternalTags):
        try:
            mapped_tag = qip.mm.sound_tag_info['map'][tag.name]
            mp4_tag = qip.mm.sound_tag_info['tags'][mapped_tag]['mp4v2_tag']
        except KeyError:
            continue
        # Force None values to actually exist
        if m4b.tags[tag] is None:
            m4b.tags[tag] = None
    for tag in sorted(m4b.tags.keys(), key=functools.cmp_to_key(dictionarycmp)):
        value = m4b.tags[tag]
        if isinstance(value, str):
            m4b.tags[tag] = value = replace_html_entities(m4b.tags[tag])
        if value is not None:
            if type(value) not in (int, str):
                value = str(value)
            print('    %-13s = %r' % (tag.value, value))

    if app.args.interactive:
        while True:
            print('')
            print('Interactive mode...')
            print(' t - edit tags')
            print(' c - edit chapters')
            print(' p - change picture%s' % (' (%s)' % (src_picture,) if src_picture else ''))
            print(' q - quit')
            print(' y - yes, do it!')
            c = app.prompt('Choice: ')
            if c == 't':
                try:
                    m4b.tags = edvar(m4b.tags)[1]
                except ValueError as e:
                    app.log.error(e)
            elif c == 'c':
                edfile(chapters_file)
            elif c == 'p':
                value = app.prompt('Cover file')
                if value is None:
                    print('Cancelled by user!')
                    continue
                select_src_picture(Path(value).expanduser())
            elif c == 'q':
                return False
            elif c == 'y':
                break
            else:
                app.log.error('Invalid input')

    m4b.encode(inputfiles=inputfiles,
               chapters_file=chapters_file if chapters_file.getsize() else None,
               force_input_bitrate=getattr(app.args, 'bitrate', None),
               target_bitrate=getattr(app.args, 'target_bitrate', None),
               yes=app.args.yes,
               force_encode=app.args.force_encode,
               ipod_compat=app.args.ipod_compat,
               itunes_compat=app.args.itunes_compat,
               use_qaac=app.args.use_qaac,
               channels=getattr(app.args, 'channels', None),
               picture=picture,
               expected_duration=expected_duration,
               )

    app.log.info('DONE!')

    if isinstance(m4b, Mpeg4ContainerFile) and mp4info.which(assert_found=False):
        print('')
        cmd = [mp4info.which()]
        cmd += [m4b.file_name]
        out = do_exec_cmd(cmd)
        out = clean_cmd_output(out)
        print(out)

    return True

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
