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
from qip.mm import *
from qip.utils import byte_decode
from qip.mm import MediaFile
import qip.mm
import qip.utils
Auto = qip.utils.Constants.Auto

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

    pgroup.add_argument('--contenttype', help='Content Type (%s)' % (', '.join((str(e) for e in qip.mm.ContentType)),))
    pgroup.add_argument('--app', default='plex', choices=['emby', 'plex'], help='App compatibility mode')
    pgroup.add_argument('--aux', dest='aux', default=True, action='store_true', help='Handle auxiliary files')
    pgroup.add_argument('--no-aux', dest='aux', default=argparse.SUPPRESS, action='store_false', help='Do not handle auxiliary files')

    pgroup = app.parser.add_argument_group('Library Mode')
    pgroup.add_argument('--music', '--normal', dest='library_mode', default=argparse.SUPPRESS, action='store_const', const='normal', help='Normal (Music) mode')
    pgroup.add_argument('--musicvideo', dest='library_mode', default=argparse.SUPPRESS, action='store_const', const='musicvideo', help='Music Video mode')
    pgroup.add_argument('--movie', dest='library_mode', default=argparse.SUPPRESS, action='store_const', const='movie', help='Movie mode')
    pgroup.add_argument('--tvshow', dest='library_mode', default=argparse.SUPPRESS, action='store_const', const='tvshow', help='TV show mode')
    pgroup.add_argument('--audiobook', dest='library_mode', default=argparse.SUPPRESS, action='store_const', const='audiobook', help='Audiobook mode')

#TODO
#    app.parser.epilog = ''
#    app.parser.epilog += '''
#How Library Modes Affect Organization:
#
#  - music:
#            <albumartist>/<albumtitle>/<disk>-<track> <title>
#            Compilations/<albumtitle>/<disk>-<track> <title>
#  - musicvideo:
#    - Plex:
#            <albumartist>/<albumtitle>/<disk>-<track> <title> - <comment>-<contenttype>
#    - Emby:
#            <albumartist>/<albumtitle>/<disk>-<track> <title>
#  - movie:
#    - Plex:
#            <title> (<year>)/<title> (<year>)
#            <title> [<subtitle>] (<year>)/<title> (<year>)
#    - Emby:
#            <title> (<year>)/<title> (<year>)
#            <title> (<year>)/<title> (<year>) - <subtitle>
#  - tvshow:
#            <tvshow>/Season <season>/<tvshow> S##E## <title>
#            <tvshow>/Specials/<tvshow> S00E## <title>
#'''

    pgroup = app.parser.add_argument_group('Files')
    pgroup.add_argument('--output', '-o', dest='outputdir', default=argparse.SUPPRESS, help='specify the output directory')

    pgroup = app.parser.add_argument_group('Compatibility')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--ascii-compat', dest='ascii_compat', default=True, action='store_true', help='Enable ASCII compatibility')
    xgroup.add_argument('--no-ascii-compat', dest='ascii_compat', default=argparse.SUPPRESS, action='store_false', help='Disable ASCII compatibility')

    app.parser.add_argument('inputfiles', nargs='*', default=(), help='input sound files')

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
            for inputfile in app.args.inputfiles:
                if os.path.isdir(inputfile):
                    raise Exception('Output directory mandatory when input directory provided')
            app.args.outputdir = ''
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

supported_audio_exts = \
        set(qip.mm.get_mp4v2_app_support().extensions_can_read) | \
        set(qip.mm.get_sox_app_support().extensions_can_read) | \
        set(('.ogg', '.mka', '.mp4', '.m4a', '.m4p', '.m4b', '.m4r', '.m4v')) | \
        set(('.mp3', '.wav')) | \
        set(('.avi', '.mkv', '.webm'))

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

def format_part_suffix(inputfile):

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
    if inputfile.tags.part is not None:
        part = "%0*d" % (len(str(inputfile.tags.parts or 1)), inputfile.tags.part)
    else:
        part = None

    if app.args.app == 'plex':
        # - [DISK]
        # - [PART]
        # - [TRACK]
        if disk:
            dst_file_base += ' - disk{disk}'.format(
                disk=disk)
        if part:
            # https://support.plex.tv/articles/200264966-naming-multi-file-movies/
            dst_file_base += ' - part{part}'.format(
                part=part)
        elif track:
            # https://support.plex.tv/articles/200264966-naming-multi-file-movies/
            dst_file_base += ' - part{track}'.format(
                track=track)
    elif app.args.app == 'emby':
        # -[DISK]
        # -[PART]
        # -[TRACK]
        if disk:
            dst_file_base += '-disk{disk}'.format(
                disk=disk)
        if part:
            # https://support.plex.tv/articles/200264966-naming-multi-file-movies/
            dst_file_base += '-part{part}'.format(
                part=part)
        elif track:
            # https://support.plex.tv/articles/200264966-naming-multi-file-movies/
            dst_file_base += '-part{track}'.format(
                track=track)

    return dst_file_base

def organize_music(inputfile, *, suggest_tags):

    # ARTIST
    if not inputfile.tags.artist:
        raise MissingMediaTagError(MediaTagEnum.artist, file=inputfile)

    # ALBUMARTIST
    if not inputfile.tags.albumartist and inputfile.tags.artist:
        suggest_tags.albumartist = inputfile.tags.albumartist = inputfile.tags.artist

    # TITLE
    if not inputfile.tags.title:
        raise MissingMediaTagError(MediaTagEnum.title, file=inputfile)

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
            raise MissingMediaTagError(tag, file=inputfile)

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

    # [DISK]-[TRACK]<spc>
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
        raise MissingMediaTagError(MediaTagEnum.artist, file=inputfile)

    # ALBUMARTIST
    if not inputfile.tags.albumartist and inputfile.tags.artist:
        suggest_tags.albumartist = inputfile.tags.albumartist = inputfile.tags.artist

    # TITLE
    if not inputfile.tags.title:
        raise MissingMediaTagError(MediaTagEnum.title, file=inputfile)

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
            raise MissingMediaTagError(tag, file=inputfile)

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

    # [DISK]-[TRACK]<spc>
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

def get_plex_contenttype_suffix(inputfile, default=None):
    contenttype = inputfile.tags.contenttype or default
    try:
        return {
            qip.mm.ContentType.behind_the_scenes: '-behindthescenes',
            #qip.mm.ContentType.cartoon: '-TODO',
            qip.mm.ContentType.concert: '-concert',
            qip.mm.ContentType.deleted: '-deleted',
            #qip.mm.ContentType.documentary: '-TODO',
            #qip.mm.ContentType.feature_film: '-TODO',
            qip.mm.ContentType.featurette: '-featurette',
            qip.mm.ContentType.interview: '-interview',
            qip.mm.ContentType.live: '-live',
            qip.mm.ContentType.lyrics: '-lyrics',
            #qip.mm.ContentType.music: '-TODO',
            qip.mm.ContentType.other: '-other',
            qip.mm.ContentType.scene: '-scene',
            qip.mm.ContentType.short: '-short',
            #qip.mm.ContentType.sound_fx: '-TODO',
            qip.mm.ContentType.trailer: '-trailer',
            qip.mm.ContentType.video: '-video',
        }[contenttype]
    except KeyError:
        raise ValueError(f'contenttype = {contenttype}')

def organize_inline_musicvideo(inputfile, *, suggest_tags):

    dst_dir, dst_file_base = organize_music(inputfile, suggest_tags=suggest_tags)
    dst_file_base, dst_file_base_ext = os.path.splitext(dst_file_base)

    # COMMENT
    if inputfile.tags.comment:
        # - [comment]
        dst_file_base += ' - %s' % (inputfile.tags.comment[0],)

    # -video
    dst_file_base += get_plex_contenttype_suffix(
        inputfile,
        default=qip.mm.ContentType.video)

    dst_file_base += dst_file_base_ext

    return dst_dir, dst_file_base

def organize_movie(inputfile, *, suggest_tags):

    # ALBUMTITLE
    if not inputfile.tags.albumtitle and inputfile.tags.title:
        #suggest_tags.albumtitle =
        inputfile.tags.albumtitle = inputfile.tags.title

    # TITLE
    if not inputfile.tags.title:
        raise MissingMediaTagError(MediaTagEnum.title, file=inputfile)

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
            raise MissingMediaTagError(tag, file=inputfile)

    dst_dir = ''

    # https://github.com/MediaBrowser/Wiki/wiki/Movie-naming
    # https://support.plex.tv/articles/200381023-naming-movie-files/
    # plex: TITLE [SUBTITLE] (YEAR)/
    # emby: TITLE (YEAR)/

    # TITLE
    dst_dir += '%s' % (clean_file_name(inputfile.tags.title, keep_ext=False),)

    if app.args.app == 'plex':
        # https://support.plex.tv/articles/200381043-multi-version-movies/
        if inputfile.tags.subtitle:
            # [SUBTITLE]
            dst_dir += ' [%s]' % (clean_file_name(inputfile.tags.subtitle, keep_ext=False),)

    if inputfile.tags.year:
        # (YEAR)
        dst_dir += ' (%d)' % (inputfile.tags.year,)

    dst_dir += '/'

    dst_file_base = ''

    if inputfile.tags.contenttype in (None, qip.mm.ContentType.feature_film):
        # plex: TITLE [SUBTITLE] (YEAR)
        # emby: TITLE (YEAR) - [SUBTITLE]

        # TITLE
        dst_file_base += inputfile.tags.title

        if app.args.app == 'plex':
            # https://support.plex.tv/articles/200381043-multi-version-movies/
            if inputfile.tags.subtitle:
                # [SUBTITLE]
                dst_file_base += ' [%s]' % (clean_file_name(inputfile.tags.subtitle, keep_ext=False),)

        if inputfile.tags.year:
            # (YEAR)
            dst_file_base += ' (%d)' % (inputfile.tags.year,)

        # TODO https://support.plex.tv/articles/200220677-local-media-assets-movies/

        if app.args.app == 'emby':
            # - [SUBTITLE]
            if inputfile.tags.subtitle:
                dst_dir += ' - %s' % (clean_file_name(inputfile.tags.subtitle, keep_ext=False),)

    else:
        # COMMENT
        if inputfile.tags.comment:
            # COMMENT
            dst_file_base = '%s' % (inputfile.tags.comment[0],)
        else:
            # ContentType
            dst_file_base = str(inputfile.tags.contenttype)

        dst_file_base += get_plex_contenttype_suffix(inputfile)

    dst_file_base += format_part_suffix(inputfile)

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
        raise MissingMediaTagError(MediaTagEnum.tvshow, file=inputfile)

    if not inputfile.tags.sorttvshow:
        v = make_sort_tag(inputfile.tags.tvshow)
        if v:
            suggest_tags.sorttvshow = v

    # SEASON

    # EPISODE

    do_suggest_tags(inputfile, suggest_tags=suggest_tags)

    for tag in (
            'season',   # Must be set but can be 0
            ):
        if tag and getattr(inputfile.tags, tag) is None:
            raise MissingMediaTagError(tag, file=inputfile)
    for tag in (
            'tvshow',   # Not allowed to be empty
            'episode',  # Not allowed to be an empty list
            ):
        if tag and not getattr(inputfile.tags, tag):
            raise MissingMediaTagError(tag, file=inputfile)

    dst_dir = ''

    # https://github.com/MediaBrowser/Wiki/wiki/TV-naming
    # TVSHOW/SEASON 01/
    dst_dir += '%s/' % (clean_file_name(inputfile.tags.tvshow, keep_ext=False),)
    if inputfile.tags.season is not None:
        if inputfile.tags.season == 0:
            # https://support.plex.tv/articles/200220707-naming-tv-show-specials/
            dst_dir += 'Specials/'
        else:
            dst_dir += 'Season %d/' % (inputfile.tags.season,)

    dst_file_base = ''

    # TVSHOW S01E01 [TITLE]
    dst_file_base += inputfile.tags.tvshow
    dst_file_base += ' S%02d' % (
        inputfile.tags.season,
        )
    episodes = inputfile.tags.episode
    if episodes is not None:
        episodes = sorted(episodes)
        dst_file_base += 'E%02d' % (episodes[0],)
        if len(episodes) > 1:
            # https://support.plex.tv/articles/200220687-naming-series-season-based-tv-shows/
            dst_file_base += '-E%02d' % (episodes[-1],)
    if inputfile.tags.title and inputfile.tags.title != inputfile.tags.tvshow:
        dst_file_base += ' %s' % (inputfile.tags.title,)
    else:
        pass  # Could be the episode name is not known.

    # TODO https://support.plex.tv/articles/200220677-local-media-assets-movies/

    dst_file_base += format_part_suffix(inputfile)

    dst_file_base += os.path.splitext(inputfile.file_name)[1]

    return dst_dir, dst_file_base

def organize(inputfile):

    if type(inputfile) is str and os.path.isdir(inputfile):
        inputdir = inputfile
        inputfile_glob_pattern = os.path.join(glob.escape(inputdir), '**')
        app.log.verbose('Recursing info %s...', inputfile_glob_pattern)
        for inputfile_path in sorted(glob.glob(inputfile_glob_pattern, recursive=True)):
            inputext = os.path.splitext(inputfile_path)[1]
            if inputext in supported_audio_exts and \
                    os.path.isfile(inputfile_path):
                organize(inputfile_path)
        return True

    if not isinstance(inputfile, MediaFile):
        inputfile = MediaFile.new_by_file_name(str(inputfile))

    if not os.path.isfile(inputfile.file_name):
        raise OSError(errno.ENOENT, 'No such file', inputfile.file_name)
    app.log.info('Organizing %s...', inputfile)
    inputfile.extract_info(need_actual_duration=False)
    #inputfile.tags = inputfile.load_tags()  # Already done by extract_info
    if app.log.isEnabledFor(logging.DEBUG):
        from qip.bin.taged import dump_tags
        dump_tags(inputfile.tags)

    suggest_tags = TrackTags()

    if app.args.contenttype:
        inputfile.tags.contenttype = app.args.contenttype
    if getattr(app.args, 'library_mode', None):
        inputfile.tags.type = app.args.library_mode
    inputfile.tags.type = inputfile.deduce_type()
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
        dst_file_tail = clean_file_name(dst_file_base,
                                        extra='-%d' % (n,) if n > 1 else '')
        dst_file_name = os.path.join(dst_dir, dst_file_tail)
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
        aux_moves = []
        if app.args.aux:
            dst_file_base, dst_file_ext = os.path.splitext(dst_file_tail)
            inputfile_dir, inputfile_tail = os.path.split(inputfile.file_name)
            inputfile_base, inputfile_ext = os.path.splitext(inputfile_tail)
            aux_file_pattern = glob.escape(os.path.join(inputfile_dir, inputfile_base)) + '.*'
            app.log.verbose('Looking for %s...', aux_file_pattern)
            for aux_file_name in sorted(glob.glob(aux_file_pattern)):
                aux_file_tail = os.path.split(aux_file_name)[1]
                if aux_file_tail == inputfile_tail:
                    continue
                assert aux_file_tail.startswith(inputfile_base), (aux_file_tail, inputfile_base)
                aux_file_suffix = aux_file_tail[len(inputfile_base):]
                dst_aux_file_tail = dst_file_base + aux_file_suffix
                dst_aux_file_name = os.path.join(dst_dir, dst_aux_file_tail)
                if os.path.exists(dst_aux_file_name):
                    raise OSError(errno.EEXIST, dst_aux_file_name)
                aux_moves.append((aux_file_name, dst_aux_file_name))
        if app.args.dry_run:
            app.log.info('  Rename to %s. (dry-run)', dst_file_name)
            for aux_file_name, dst_aux_file_name in aux_moves:
                app.log.info('  Rename aux %s. (dry-run)', dst_aux_file_name)
        else:
            app.log.info('  Rename to %s.', dst_file_name)
            shutil.move(inputfile.file_name, dst_file_name,
                        copy_function=qip.utils.progress_copy2)
            for aux_file_name, dst_aux_file_name in aux_moves:
                app.log.info('  Rename aux %s.', dst_aux_file_name)
                shutil.move(aux_file_name, dst_aux_file_name,
                            copy_function=qip.utils.progress_copy2)
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
