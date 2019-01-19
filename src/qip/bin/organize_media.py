#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

# https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes
# https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

import argparse
import decimal
import errno
import functools
import glob
import html
import logging
import os
import pexpect
import re
import reprlib
import shutil
import subprocess
import sys
import unidecode
import xml.etree.ElementTree as ET
reprlib.aRepr.maxdict = 100

from qip import json
from qip.app import app
from qip.cmp import *
from qip.exec import *
from qip.file import *
from qip.parser import *
from qip.snd import *
from qip.utils import byte_decode
import qip.snd

# replace_html_entities {{{

def replace_html_entities(s):
    s = html.unescape(s)
    m = re.search(r'&\w+;', s)
    if m:
        raise ValueError('Unknown HTML entity: %s' % (m.group(0),))
    return s

# }}}

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='Media Organizer',
            contact='jst@qualipsoft.com',
            )

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
    pgroup.add_argument('--apply-suggestions', dest='apply_suggestions', default=False, action='store_true', help='apply suggestions')
    pgroup.add_argument('--music', '--normal', dest='library_mode', default=None, action='store_const', const='normal', help='Normal (Music) mode (<albumartist>/<albumtitle>/<track>)')
    pgroup.add_argument('--musicvideo', dest='library_mode', default=argparse.SUPPRESS, action='store_const', const='musicvideo', help='Music Video mode (Plex: <albumartist>/<albumartist>/<track> - <comment>-video; Emby: same as music)')
    pgroup.add_argument('--movie', dest='library_mode', default=argparse.SUPPRESS, action='store_const', const='movie', help='Movie mode (<title>/<file>)')
    pgroup.add_argument('--tvshow', dest='library_mode', default=argparse.SUPPRESS, action='store_const', const='tvshow', help='TV show mode (<title>/<file>)')
    pgroup.add_argument('--contenttype', help='Content Type (%s)' % (', '.join((str(e) for e in qip.snd.ContentType)),))
    pgroup.add_argument('--app', default='plex', choices=['emby', 'plex'], help='App compatibility mode')

    pgroup = app.parser.add_argument_group('Files')
    pgroup.add_argument('--output', '-o', dest='outputdir', default=argparse.SUPPRESS, help='specify the output directory')

    pgroup = app.parser.add_argument_group('Compatibility')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--ascii-compat', dest='ascii_compat', default=True, action='store_true', help='ASCII compatibility (default)')
    xgroup.add_argument('--no-ascii-compat', dest='ascii_compat', default=argparse.SUPPRESS, action='store_false', help='ASCII compatibility (disable)')

    app.parser.add_argument('inputfiles', nargs='*', default=None, help='input sound files')

    app.parse_args()

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'organize'
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    for prog in (
            'ffmpeg',  # ffmpeg | libav-tools
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

    if app.args.action == 'organize':
        # {{{

        if not app.args.inputfiles:
            raise Exception('No input files provided')
        if 'outputdir' not in app.args:
            app.args.outputdir = ''
            #raise Exception('No output directory provided')
        for inputfile in app.args.inputfiles:
            organize(inputfile)

        # }}}
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

# clean_file_name {{{

def clean_file_name(file_name, keep_ext=True, extra=''):
    if keep_ext:
        name, ext = os.path.splitext(file_name)
    else:
        name, ext = file_name, ''
    name = unidecode.unidecode(name)
    # http://en.wikipedia.org/wiki/Filename {{{
    # UNIX: a leading . indicates that ls and file managers will not show the file by default
    name = re.sub(r'^[.]+', '', name)
    # Remove leading spaces too
    name = re.sub(r'^[ ]+', '', name)
    # NTFS: The Win32 API strips trailing space and period (full-stop) characters from filenames, except when UNC paths are used.
    # XXXJST: Include ! which may be considered as an event command even within double-quotes
    name = re.sub(r'[ .!]+$', '', name)
    # most: forbids the use of 0x00
    name = re.sub(r'\x00', '_', name)
    # NTFS/vfat: forbids the use of characters in range 1-31 (0x01-0x1F) and characters " * : < > ? \ / | unless the name is flagged as being in the Posix namespace.
    name = re.sub(r'[\x01-\x1F\"*:<>?\\/|]', '_', name)
    # XXXJST: Include ! which may be considered as an event command even within double-quotes
    name = re.sub(r'[!]', '_', name)
    # vfat: forbids the use of 0x7F
    name = re.sub(r'\x7F', '_', name)
    # Shouldn't be empty!
    if len(name) + len(extra) == 0:
        name = '_'
    # NTFS allows each path component (directory or filename) to be 255 characters long.
    over = len(name) + len(extra) + len(ext) - 255
    if over > 0:
        name = name[:len(name)-over]
    # }}}
    file_name = name + extra + ext
    return file_name

# }}}

def dump_tags(tags, *, deep=True, heading='Tags:'):
    if heading:
        print(heading)
    for tag_info in mp4tags.tag_args_info:
        # Force None values to actually exist
        if tags[tag_info.tag_enum] is None:
            tags[tag_info.tag_enum] = None
    tags_keys = tags.keys() if deep else tags.keys(deep=False)
    for tag in sorted(tags_keys, key=functools.cmp_to_key(dictionarycmp)):
        value = tags[tag]
        if isinstance(value, str):
            tags[tag] = value = replace_html_entities(tags[tag])
        if value is not None:
            if type(value) not in (int, str, bool, tuple):
                value = str(value)
            print('    %-13s = %r' % (tag.value, value))
    for track_no, track_tags in tags.tracks_tags.items() if isinstance(tags, AlbumTags) else ():
        dump_tags(track_tags, deep=False, heading='- Track %d' % (track_no,))

supported_audio_exts = \
        set(qip.snd.get_mp4v2_app_support().extensions_can_read) | \
        set(qip.snd.get_sox_app_support().extensions_can_read) | \
        set(('.ogg', '.mp4', '.m4a', '.m4p', '.m4b', '.m4r', '.m4v')) | \
        set(('.mp3', '.wav')) | \
        set(('.avi', '.mkv'))

def dir_empty(d):
    if not os.path.isdir(d):
        return False
    glob_pattern = os.path.join(glob.escape(d), '*')
    for sub in glob.iglob(glob_pattern):
        return False
    glob_pattern = os.path.join(glob.escape(d), '.*')
    for sub in glob.iglob(glob_pattern):
        return False
    return True

def make_sort_tag(value):
        m = value and re.match(r'^(.+) \((.+) #([0-9]+)\)', value)
        if m:
            sort_value = "%s #%02d - %s" % (
                    m.group(2),
                    int(m.group(3)),
                    m.group(1),
                    )
            return sort_value

def do_suggest_tags(inputfile, *, suggest_tags):
    if suggest_tags:
        do_apply_suggestions = app.args.apply_suggestions
        if not do_apply_suggestions:
            inputfile.write_tags(tags=suggest_tags, run_func=suggest_exec_cmd)
            if app.args.interactive:
                while suggest_tags:
                    c = input('Apply? [y/n/e] ')
                    if c.lower() in ('y', 'yes'):
                        do_apply_suggestions = True
                        break
                    elif c.lower() in ('n', 'no'):
                        do_apply_suggestions = False
                        break
                    elif c.lower() in ('e', 'edit'):
                        try:
                            suggest_tags = edvar(suggest_tags)[1]
                        except ValueError as e:
                            app.log.error(e)
                    else:
                        app.log.error('Invalid input')
        if suggest_tags and do_apply_suggestions:
            for tag, value in suggest_tags.items():
                app.log.info('APPLY: %s = %r%s',
                    tag.name,
                    value,
                    ' (dry-run)' if app.args.dry_run else '')
            inputfile.write_tags(tags=suggest_tags, dry_run=app.args.dry_run, run_func=do_exec_cmd)
            inputfile.tags.update(suggest_tags)

def organize_music(inputfile, *, suggest_tags):

    # ARTIST
    if not inputfile.tags.artist:
        raise MissingSoundTagError(SoundTagEnum.artist, file=inputfile)

    # ALBUMARTIST
    if not inputfile.tags.albumartist and inputfile.tags.artist:
        suggest_tags.albumartist = inputfile.tags.albumartist = inputfile.tags.artist

    # TITLE
    if not inputfile.tags.title:
        raise MissingSoundTagError(SoundTagEnum.title, file=inputfile)

    if not inputfile.tags.sorttitle:
        v = make_sort_tag(inputfile.tags.title)
        if v:
            suggest_tags.sorttitle = v

    # ALBUMTITLE
    if not inputfile.tags.albumtitle and inputfile.tags.title:
        inputfile.tags.albumtitle = inputfile.tags.title

    if not inputfile.tags.sortalbumtitle:
        v = make_sort_tag(inputfile.tags.albumtitle)
        if v:
            suggest_tags.sortalbumtitle = v

    do_suggest_tags(inputfile, suggest_tags=suggest_tags)

    for tag in (
            not inputfile.tags.compilation and 'albumartist',
            'albumtitle',
            'artist',
            'title',
            ):
        if tag and not getattr(inputfile.tags, tag):
            raise MissingSoundTagError(tag, file=inputfile)

    dst_dir = ''

    # https://github.com/MediaBrowser/Wiki/wiki/Music%20naming
    # Compilations/ALBUMTITLE/
    # ALBUMARTIST/ALBUMTITLE/
    if inputfile.tags.compilation:
        dst_dir += 'Compilations/'
    else:
        dst_dir += '%s/' % (clean_file_name(re.sub(r';', ',', inputfile.tags.albumartist), keep_ext=False),)
    dst_dir += clean_file_name(inputfile.tags.albumtitle, keep_ext=False) + '/'

    dst_file_base = ''

    if inputfile.tags.disk and inputfile.tags.disks and \
            inputfile.tags.disks > 1:
        disk = "%0*d" % (len(str(inputfile.tags.disks or 1)), inputfile.tags.disk)
    else:
        disk = None
    if inputfile.tags.track is not None:
        track = "%0*d" % (len(str(inputfile.tags.tracks or 99)), inputfile.tags.track)
    else:
        track = None

    # [DISC]-[TRACK]<spc>
    if disk or track:
        dst_file_base += '{disk}{disk_track_sep}{track} '.format(
            disk=disk or '',
            track=track or '',
            disk_track_sep='-' if disk and track else '',
        )

    # TITLE
    dst_file_base += inputfile.tags.title

    # TODO https://support.plex.tv/articles/200220677-local-media-assets-movies/

    dst_file_base += os.path.splitext(inputfile.file_name)[1]

    return dst_dir, dst_file_base

def organize_audiobook(inputfile, *, suggest_tags):

    # ARTIST
    if not inputfile.tags.artist:
        raise MissingSoundTagError(SoundTagEnum.artist, file=inputfile)

    # ALBUMARTIST
    if not inputfile.tags.albumartist and inputfile.tags.artist:
        suggest_tags.albumartist = inputfile.tags.albumartist = inputfile.tags.artist

    # TITLE
    if not inputfile.tags.title:
        raise MissingSoundTagError(SoundTagEnum.title, file=inputfile)

    if not inputfile.tags.sorttitle:
        v = make_sort_tag(inputfile.tags.title)
        if v:
            suggest_tags.sorttitle = v

    do_suggest_tags(inputfile, suggest_tags=suggest_tags)

    for tag in (
            'albumartist',
            'albumtitle',
            'title',
            ):
        if tag and not getattr(inputfile.tags, tag):
            raise MissingSoundTagError(tag, file=inputfile)

    dst_dir = ''

    # https://github.com/MediaBrowser/Wiki/wiki/Music%20naming
    # ALBUMARTIST/ALBUMTITLE/
    dst_dir += '%s/' % (clean_file_name(re.sub(r';', ',', inputfile.tags.albumartist), keep_ext=False),)
    dst_dir += clean_file_name(inputfile.tags.albumtitle, keep_ext=False) + '/'

    dst_file_base = ''

    if inputfile.tags.disk and inputfile.tags.disks and \
            inputfile.tags.disks > 1:
        disk = "%0*d" % (len(str(inputfile.tags.disks or 1)), inputfile.tags.disk)
    else:
        disk = None
    if inputfile.tags.track is not None:
        track = "%0*d" % (len(str(inputfile.tags.tracks or 99)), inputfile.tags.track)
    else:
        track = None

    # [DISC]-[TRACK]<spc>
    if disk or track:
        dst_file_base += '{disk}{disk_track_sep}{track} '.format(
            disk=disk or '',
            track=track or '',
            disk_track_sep='-' if disk and track else '',
        )

    # TITLE
    dst_file_base += inputfile.tags.title

    # TODO https://support.plex.tv/articles/200220677-local-media-assets-movies/

    dst_file_base += os.path.splitext(inputfile.file_name)[1]

    return dst_dir, dst_file_base

def organize_inline_musicvideo(inputfile, *, suggest_tags):

    dst_dir, dst_file_base = organize_music(inputfile, suggest_tags=suggest_tags)
    dst_file_base, dst_file_base_ext = os.path.splitext(dst_file_base)

    # COMMENT
    if inputfile.tags.comment:
        # - [comment]
        dst_file_base += ' - %s' % (inputfile.tags.comment[0],)

    # -video
    dst_file_base += {
        qip.snd.ContentType.behind_the_scenes: '-behindthescenes',
        qip.snd.ContentType.concert: '-concert',
        qip.snd.ContentType.interview: '-interview',
        qip.snd.ContentType.live_music_video: '-live',
        qip.snd.ContentType.lyrics_music_video: '-lyrics',
        qip.snd.ContentType.music_video: '-video',
    }.get(inputfile.tags.contenttype, '-video')

    dst_file_base += dst_file_base_ext

    return dst_dir, dst_file_base

def organize_movie(inputfile, *, suggest_tags):

    # ALBUMTITLE
    if not inputfile.tags.albumtitle and inputfile.tags.title:
        #suggest_tags.albumtitle =
        inputfile.tags.albumtitle = inputfile.tags.title

    # TITLE
    if not inputfile.tags.title:
        raise MissingSoundTagError(SoundTagEnum.title, file=inputfile)

    if not inputfile.tags.sorttitle:
        v = make_sort_tag(inputfile.tags.title)
        if v:
            suggest_tags.sorttitle = v

    do_suggest_tags(inputfile, suggest_tags=suggest_tags)

    for tag in (
            'albumtitle',
            'title',
            ):
        if tag and not getattr(inputfile.tags, tag):
            raise MissingSoundTagError(tag, file=inputfile)

    dst_dir = ''

    # https://github.com/MediaBrowser/Wiki/wiki/Movie-naming
    # https://support.plex.tv/articles/200381023-naming-movie-files/
    # ALBUMTITLE (YEAR)/
    dst_dir += '%s' % (clean_file_name(inputfile.tags.albumtitle, keep_ext=False),)
    if inputfile.tags.year:
        dst_dir += ' (%d)' % (inputfile.tags.year,)
    dst_dir += '/'

    dst_file_base = ''

    if inputfile.tags.disk and inputfile.tags.disks and \
            inputfile.tags.disks > 1:
        disk = "%0*d" % (len(str(inputfile.tags.disks or 1)), inputfile.tags.disk)
    else:
        disk = None
    if inputfile.tags.track is not None:
        track = "%0*d" % (len(str(inputfile.tags.tracks or 99)), inputfile.tags.track)
    else:
        track = None

    if app.args.app == 'plex':
        # TITLE (YEAR)
        dst_file_base += inputfile.tags.title
        if inputfile.tags.year:
            dst_file_base += ' (%d)' % (inputfile.tags.year,)
    else:
        # TITLE
        dst_file_base += inputfile.tags.title
    # https://support.plex.tv/articles/200381043-multi-version-movies/
    # TODO format!

    # TODO https://support.plex.tv/articles/200220677-local-media-assets-movies/

    # -[DISC]
    # -[TRACK]
    if disk:
        dst_file_base += '-disk{disk}'.format(
            disk=disk)
    if track:
        # https://support.plex.tv/articles/200264966-naming-multi-file-movies/
        dst_file_base += '-part{track}'.format(
            track=track)

    dst_file_base += os.path.splitext(inputfile.file_name)[1]

    return dst_dir, dst_file_base

def organize_tvshow(inputfile, *, suggest_tags):

    # TITLE
    if not inputfile.tags.title:
        suggest_tags.title = inputfile.tags.title = inputfile.tags.tvshow

    # TVSHOW
    if not inputfile.tags.tvshow and inputfile.tags.albumtitle:
        suggest_tags.tvshow = inputfile.tags.tvshow = inputfile.tags.albumtitle
    if not inputfile.tags.tvshow:
        raise MissingSoundTagError(SoundTagEnum.tvshow, file=inputfile)

    if not inputfile.tags.sorttvshow:
        v = make_sort_tag(inputfile.tags.tvshow)
        if v:
            suggest_tags.sorttvshow = v

    # SEASON

    # EPISODE

    do_suggest_tags(inputfile, suggest_tags=suggest_tags)

    for tag in (
            'tvshow',
            'season',
            'episode',
            ):
        if tag and not getattr(inputfile.tags, tag):
            raise MissingSoundTagError(tag, file=inputfile)

    dst_dir = ''

    # https://github.com/MediaBrowser/Wiki/wiki/TV-naming
    # TVSHOW/SEASON 01/
    dst_dir += '%s/' % (clean_file_name(inputfile.tags.tvshow, keep_ext=False),)
    if inputfile.tags.season:
        dst_dir += 'Season %d/' % (inputfile.tags.season,)

    dst_file_base = ''

    if inputfile.tags.disk and inputfile.tags.disks and \
            inputfile.tags.disks > 1:
        disk = "%0*d" % (len(str(inputfile.tags.disks or 1)), inputfile.tags.disk)
    else:
        disk = None
    if inputfile.tags.track is not None:
        track = "%0*d" % (len(str(inputfile.tags.tracks or 99)), inputfile.tags.track)
    else:
        track = None

    # TVSHOW S01E01 [TITLE]
    dst_file_base += inputfile.tags.tvshow
    dst_file_base += ' S%02dE' % (
        inputfile.tags.season,
        )
    for episode in inputfile.tags.episode:
        dst_file_base += '%02d' % (episode,)
    if inputfile.tags.title and inputfile.tags.title != inputfile.tags.tvshow:
        dst_file_base += ' %s' % (inputfile.tags.title,)

    else:
        raise ValueError('type = %r' % (inputfile.tags.type,))

    # TODO https://support.plex.tv/articles/200220677-local-media-assets-movies/

    if inputfile.tags.type not in ('normal', 'audiobook', 'musicvideo'):
        # -[DISC]
        # -[TRACK]
        if disk:
            dst_file_base += '-disk{disk}'.format(
                disk=disk)
        if track:
            # https://support.plex.tv/articles/200264966-naming-multi-file-movies/
            dst_file_base += '-part{track}'.format(
                track=track)

    dst_file_base += os.path.splitext(inputfile.file_name)[1]

    return dst_dir, dst_file_base

def organize(inputfile):

    if type(inputfile) is str and os.path.isdir(inputfile):
        inputdir = inputfile
        glob_pattern = os.path.join(glob.escape(inputdir), '**')
        app.log.verbose('Recursing info %s...', glob_pattern)
        for inputfile in sorted(glob.iglob(glob_pattern, recursive=True)):
            inputext = os.path.splitext(inputfile)[1]
            if inputext in supported_audio_exts and \
                    os.path.isfile(inputfile):
                organize(inputfile)
        return True

    if not isinstance(inputfile, SoundFile):
        if os.path.splitext(inputfile)[1] in {'.m4b',}:
            from qip.m4b import AudiobookFile
            inputfile = AudiobookFile(file_name=inputfile)
        elif os.path.splitext(inputfile)[1] in {'.mp3',}:
            from qip.mp3 import Mp3File
            inputfile = Mp3File(file_name=inputfile)
        elif os.path.splitext(inputfile)[1] in {'.wav',}:
            from qip.wav import WaveFile
            inputfile = WaveFile(file_name=inputfile)
        elif os.path.splitext(inputfile)[1] in {'.mkv',}:
            from qip.mkv import MkvFile
            inputfile = MkvFile(file_name=inputfile)
        elif os.path.splitext(inputfile)[1] in qip.snd.get_mp4v2_app_support().extensions_can_write:
            from qip.m4a import M4aFile
            inputfile = M4aFile(file_name=inputfile)
        else:
            inputfile = SoundFile(file_name=inputfile)

    if not os.path.isfile(inputfile.file_name):
        raise OSError(errno.ENOENT, 'No such file', inputfile.file_name)
    app.log.info('Organizing %s...', inputfile)
    inputfile.extract_info(need_actual_duration=False)
    if app.log.isEnabledFor(logging.DEBUG):
        dump_tags(inputfile.tags)

    suggest_tags = TrackTags()

    if app.args.contenttype:
        inputfile.tags.contenttype = app.args.contenttype
    if app.args.library_mode:
        inputfile.tags.type = app.args.library_mode
    if not inputfile.tags.type:
        name, ext = os.path.splitext(inputfile.file_name)
        if ext in ('.m4a', '.mp3', '.ogg', '.wav'):
            inputfile.tags.type = 'normal'
        elif ext in ('.m4b'):
            inputfile.tags.type = 'audiobook'
        elif ext in ('.mkv', '.avi', '.mp4', '.m4v'):
            contenttype = inputfile.tags.contenttype
            if 'Music Video' in str(inputfile.tags.contenttype) \
                    or 'Concert' in str(inputfile.tags.contenttype):
                inputfile.tags.type = 'musicvideo'
            elif inputfile.tags.tvshow is not None:
                inputfile.tags.type = 'tvshow'
            else:
                inputfile.tags.type = 'movie'
        else:
            raise MissingSoundTagError(SoundTagEnum.type, file=inputfile)
    app.log.debug('type = %r', inputfile.tags.type)

    # PEOPLE
    for tag in (
            'albumartist',
            'artist',
            'composer',
            ):
        if not tag:
            continue
        old_value = getattr(inputfile.tags, tag)
        new_value = old_value
        if new_value is None:
            if tag == 'albumartist':
                if inputfile.tags.compilation:
                    new_value = inputfile.tags.albumartist = 'Various Artists'
                elif inputfile.tags.type not in ('movie',):
                    new_value = inputfile.tags.albumartist = inputfile.tags.artist
        if new_value is None:
            continue
        new_value = re.sub(r', *|,? +and +|,? +et +| +& +', '; ', new_value)
        if new_value != old_value:
            suggest_tags[tag] = new_value

    if inputfile.tags.type == 'normal':
        ores = organize_music(inputfile, suggest_tags=suggest_tags)
    elif inputfile.tags.type == 'audiobook':
        ores = organize_audiobook(inputfile, suggest_tags=suggest_tags)
    elif inputfile.tags.type == 'musicvideo':
        if app.args.app == 'emby':
            ores = organize_music(inputfile, suggest_tags=suggest_tags)
        else:
            ores = organize_inline_musicvideo(inputfile, suggest_tags=suggest_tags)
    elif inputfile.tags.type == 'movie':
        ores = organize_movie(inputfile, suggest_tags=suggest_tags)
    elif inputfile.tags.type == 'tvshow':
        ores = organize_tvshow(inputfile, suggest_tags=suggest_tags)
    else:
        raise ValueError('type = %r' % (inputfile.tags.type,))
    dst_dir, dst_file_base = ores
    dst_dir = os.path.join(app.args.outputdir, dst_dir)

    src_stat = os.lstat(inputfile.file_name)
    skip = False
    for n in range(1,10):
        dst_file_name = os.path.join(dst_dir,
                                     clean_file_name(dst_file_base,
                                         extra='-%d' % (n,) if n > 1 else ''))
        if os.path.exists(dst_file_name):
            dst_stat = os.lstat(dst_file_name)
            if dst_stat.st_ino == src_stat.st_ino:
                app.log.verbose('  Use existing %s.', dst_file_name)
                skip = True
                break
            else:
                app.log.debug('  Collision with %s.', dst_file_name)
                continue
        if not os.path.exists(dst_dir):
            if app.args.dry_run:
                app.log.info('  Create %s. (dry-run)', dst_dir)
            else:
                app.log.info('  Create %s.', dst_dir)
                os.makedirs(dst_dir)
        if app.args.dry_run:
            app.log.info('  Rename to %s. (dry-run)', dst_file_name)
        else:
            app.log.info('  Rename to %s.', dst_file_name)
            shutil.move(inputfile.file_name, dst_file_name)
            inputdir = os.path.dirname(inputfile.file_name)
            if inputdir not in ('.', '') and dir_empty(inputdir):
                app.log.info('Remove %s.', inputdir)
                os.rmdir(inputdir)
        break
    else:
        app.log.error('  Ran out of options!')

    return True

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
