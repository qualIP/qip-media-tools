#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :
# PYTHON_ARGCOMPLETE_OK

# https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes
# https://en.wikipedia.org/wiki/List_of_ISO_639-2_codes

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

from pathlib import Path
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
reprlib.aRepr.maxdict = 100

from qip import json
from qip.app import app
from qip.cmp import *
from qip.exec import *
from qip.file import *
from qip.mm import *
from qip.mm import MediaFile
from qip.parser import *
from qip.utils import byte_decode
import qip.mm
import qip.utils

#import qip.pgs
#import qip.vob
import qip.avi
import qip.flac
import qip.img
import qip.matroska
import qip.mp2
import qip.mp3
import qip.mp4
import qip.wav

Auto = qip.utils.Constants.Auto
all_part_names = {'disk', 'track', 'part'}

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
    pgroup.add_argument('--media-library-app', '--app', default='plex', choices=['emby', 'plex', 'mmdemux'], help='App compatibility mode')
    pgroup.add_argument('--aux', dest='aux', default=True, action='store_true', help='Handle auxiliary files')
    pgroup.add_argument('--no-aux', dest='aux', default=argparse.SUPPRESS, action='store_false', help='Do not handle auxiliary files')
    pgroup.add_bool_argument('--overwrite', default=False, help='overwrite files')
    pgroup.add_bool_argument('--copy', default=False, help='hard link files instead of copying')
    pgroup.add_bool_argument('--link', '-l', default=False, help='hard link files copying')

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
    pgroup.add_argument('--output', '-o', dest='outputdir', default=argparse.SUPPRESS, type=Path, help='specify the output directory')
    pgroup.add_bool_argument('--use-default-output', default=True, help='use default output directory from config file')

    pgroup = app.parser.add_argument_group('Compatibility')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--ascii-compat', dest='ascii_compat', default=True, action='store_true', help='Enable ASCII compatibility')
    xgroup.add_argument('--no-ascii-compat', dest='ascii_compat', default=argparse.SUPPRESS, action='store_false', help='Disable ASCII compatibility')

    pgroup = app.parser.add_argument_group('Actions')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--organize', dest='action', default=None, action='store_const', const='organize', help='organize media files')
    xgroup.add_argument('--set-default', dest='action', default=argparse.SUPPRESS, action='store_const', const='set-default', help='set default (with a Library Mode argument and --output)')

    app.parser.add_argument('inputfiles', nargs='*', default=(), type=Path, help='input sound files')

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
            #'mp4info',  # mp4v2-utils
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
                if inputfile.is_dir():
                    raise Exception('Output directory mandatory when input directory provided')
            if not app.args.use_default_output:
                raise ValueError('No output directory specified and use of default output directories disabled')
        for inputfile in app.args.inputfiles:
            organize(inputfile)

        # }}}
    elif app.args.action == 'set-default':
        # {{{
        if app.args.inputfiles:
            raise Exception('Cannot provide input files with --set-default')
        if not getattr(app.args, 'library_mode', None):
            raise Exception('No Library Mode provided')
        if not getattr(app.args, 'outputdir', None):
            raise Exception('No output directory provided')
        if not app.config_file_parser.has_section('default-output'):
            app.config_file_parser.add_section('default-output')
        app.config_file_parser.set('default-output', app.args.library_mode, os.fspath(app.args.outputdir.resolve()))
        app.config_file_parser.write()
        # }}}
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

supported_media_exts = \
        set(qip.mm.get_mp4v2_app_support().extensions_can_read) | \
        set(qip.mm.get_sox_app_support().extensions_can_read) | \
        set(('.ogg', '.mka', '.mp4', '.m4a', '.m4p', '.m4b', '.m4r', '.m4v')) | \
        set(('.mp3', '.wav', '.flac')) | \
        set(('.avi', '.mkv', '.webm'))

def dir_empty(d):
    d = Path(d)
    if not d.is_dir():
        return False
    for sub in d.glob('*'):
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
        do_apply_suggestions = getattr(app.args, 'apply_suggestions', False)
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

def format_part_suffix(inputfile, which=all_part_names):

    dst_file_base = ''

    if 'disk' in which and inputfile.tags.disk and inputfile.tags.disks and \
            inputfile.tags.disks > 1:
        disk = "%0*d" % (len(str(inputfile.tags.disks or 1)), inputfile.tags.disk)
    else:
        disk = None
    if 'track' in which and inputfile.tags.track is not None:
        track = "%0*d" % (len(str(inputfile.tags.tracks or 99)), inputfile.tags.track)
    else:
        track = None
    if 'part' in which and inputfile.tags.part is not None:
        part = "%0*d" % (len(str(inputfile.tags.parts or 1)), inputfile.tags.part)
    else:
        part = None
    app.log.debug('disk=%r, track=%r, part=%r', disk, track, part)

    if app.args.media_library_app in ('plex', 'mmdemux'):
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
    elif app.args.media_library_app == 'emby':
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

def organize_music(inputfile, *, suggest_tags, dbtype='music'):

    # ARTIST
    if not inputfile.tags.artist:
        raise MissingMediaTagError(MediaTagEnum.artist, file=inputfile)

    # ALBUMARTIST
    if not inputfile.tags.albumartist and inputfile.tags.artist:
        inputfile.tags.albumartist = inputfile.tags.artist
        if dbtype == 'music':
            suggest_tags.albumartist = inputfile.tags.albumartist

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

    dst_dir = Path()

    # https://github.com/MediaBrowser/Wiki/wiki/Music%20naming
    # Compilations/ALBUMTITLE/
    # ALBUMARTIST/ALBUMTITLE/
    if inputfile.tags.compilation:
        dst_dir /= 'Compilations'
    else:
        dst_dir /= clean_file_name(re.sub(r';', ',', inputfile.tags.albumartist), keep_ext=False)
    dst_dir /= clean_file_name(inputfile.tags.albumtitle, keep_ext=False)

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

    dst_file_base += format_part_suffix(inputfile, which=all_part_names - {'disk', 'track'})

    dst_file_base = clean_file_name(dst_file_base, keep_ext=False)
    dst_file_base += inputfile.file_name.suffix

    return dst_dir / dst_file_base

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

    # ALBUMTITLE
    if not inputfile.tags.albumtitle and inputfile.tags.title:
        suggest_tags.albumtitle = inputfile.tags.albumtitle = inputfile.tags.title

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

    dst_dir = Path()

    # https://github.com/MediaBrowser/Wiki/wiki/Music%20naming
    # ALBUMARTIST/ALBUMTITLE/
    dst_dir /= clean_file_name(re.sub(r';', ',', inputfile.tags.albumartist), keep_ext=False)
    dst_dir /= clean_file_name(inputfile.tags.albumtitle, keep_ext=False)

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

    dst_file_base = clean_file_name(dst_file_base, keep_ext=False)
    dst_file_base += inputfile.file_name.suffix

    return dst_dir / dst_file_base

def get_plex_format_hints_suffix(inputfile, dst_file_base):
    suffix = ''
    stereo_3d_mode = getattr(inputfile, 'stereo_3d_mode', None)
    if stereo_3d_mode is not None:
        # For Kodi compatibility, make sure '3D' is included
        if '3D' not in dst_file_base.split('.'):
            suffix += '.3D'
        # Plex requires 3D mode ((H-?)?(SBS|TAB))
        suffix += stereo_3d_mode.exts[0]
    return suffix

def get_plex_contenttype_suffix(inputfile, *, default=None, dbtype='movie'):
    contenttype = inputfile.tags.contenttype or default
    try:
        return {
            qip.mm.ContentType.behind_the_scenes: '-behindthescenes',
            #qip.mm.ContentType.cartoon: '-TODO',
            qip.mm.ContentType.concert: '-concert',
            qip.mm.ContentType.deleted: '-deleted',
            qip.mm.ContentType.documentary: (
                # https://github.com/contrary-cat/LocalTVExtras.bundle
                # '-extra' if dbtype in ('tvshow',)  # Plex Media Scanner says "Got nothing for ... Extra"
                '-other' if dbtype in ('tvshow',)    # <- Revert to other
                else '-other'),  # TODO documentary support in Local TV Extras
            #qip.mm.ContentType.feature_film: '-TODO',
            qip.mm.ContentType.featurette: '-featurette',
            qip.mm.ContentType.interview: '-interview',
            qip.mm.ContentType.live: '-live',
            qip.mm.ContentType.lyrics: (
                '-lyrics' if dbtype in ('musicvideo',)
                else '-other'),
            #qip.mm.ContentType.music: '-TODO',
            qip.mm.ContentType.other: '-other',
            qip.mm.ContentType.scene: '-scene',
            qip.mm.ContentType.short: '-short',
            #qip.mm.ContentType.sound_fx: '-TODO',
            qip.mm.ContentType.trailer: '-trailer',
            qip.mm.ContentType.video: (
                '-video' if dbtype in ('musicvideo',)
                else '-other'),
        }[contenttype]
    except KeyError:
        raise ValueError(f'contenttype = {contenttype}')

def organize_inline_musicvideo(inputfile, *, suggest_tags):

    opath = organize_music(inputfile, suggest_tags=suggest_tags,
                                            dbtype='musicvideo')
    dst_dir, dst_file_base = opath.parent, opath.name
    dst_file_base, dst_file_base_ext = os.path.splitext(os.fspath(dst_file_base))

    # COMMENT
    if inputfile.tags.comment:
        # - [comment]
        dst_file_base += ' - %s' % (inputfile.tags.comment[0],)

    dst_file_base += get_plex_format_hints_suffix(inputfile, dst_file_base)

    # -video
    dst_file_base += get_plex_contenttype_suffix(
        inputfile,
        default=qip.mm.ContentType.video,
        dbtype='musicvideo')

    dst_file_base += format_part_suffix(inputfile, which=all_part_names - {'disk', 'track'})

    dst_file_base = clean_file_name(dst_file_base, keep_ext=False)
    dst_file_base += dst_file_base_ext

    return dst_dir / dst_file_base

def organize_movie(inputfile, *, suggest_tags, orig_type):

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

    dst_dir = Path()

    # https://github.com/MediaBrowser/Wiki/wiki/Movie-naming
    # https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/
    # plex: TITLE [SUBTITLE] (YEAR)/
    # emby: TITLE (YEAR)/

    # TITLE
    dst_dir /= clean_file_name(inputfile.tags.title, keep_ext=False)

    if app.args.media_library_app == 'plex':
        # https://support.plex.tv/articles/200381043-multi-version-movies/
        if inputfile.tags.subtitle:
            # [SUBTITLE]
            dst_dir = dst_dir.with_name(dst_dir.name + ' [%s]' % (clean_file_name(inputfile.tags.subtitle, keep_ext=False),))

    if inputfile.tags.year:
        # (YEAR)
        dst_dir = dst_dir.with_name(dst_dir.name + ' (%d)' % (inputfile.tags.year,))

    if inputfile.tags.contenttype in (None,
                                      qip.mm.ContentType.feature_film,
                                      qip.mm.ContentType.cartoon):
        # plex: TITLE [SUBTITLE] (YEAR)
        # emby: TITLE (YEAR) - [SUBTITLE]

        # TITLE
        dst_file_base = inputfile.tags.title

        if app.args.media_library_app == 'plex':
            # https://support.plex.tv/articles/200381043-multi-version-movies/
            if inputfile.tags.subtitle:
                # [SUBTITLE]
                dst_file_base += f' [{inputfile.tags.subtitle}]'

        if inputfile.tags.year:
            # (YEAR)
            dst_file_base += f' ({inputfile.tags.year})'

        # TODO https://support.plex.tv/articles/200220677-local-media-assets-movies/

        if app.args.media_library_app == 'emby':
            # - [SUBTITLE]
            if inputfile.tags.subtitle:
                dst_file_base += f' - {inputfile.tags.subtitle}'

    else:
        # plex: behindthescenes, deleted, featurette, interview, scene, short, trailer, other
        #       https://support.plex.tv/articles/200220677-local-media-assets-movies/

        # COMMENT
        if inputfile.tags.comment:
            # COMMENT
            dst_file_base = inputfile.tags.comment[0]
        else:
            # ContentType
            dst_file_base = str(inputfile.tags.contenttype)

    dst_file_base += get_plex_format_hints_suffix(inputfile, dst_file_base)

    if inputfile.tags.contenttype in (None,
                                      qip.mm.ContentType.feature_film,
                                      qip.mm.ContentType.cartoon):
        pass  # Ok
    else:
        dst_file_base += get_plex_contenttype_suffix(inputfile,
                                                     dbtype='movie')

    dst_file_base += format_part_suffix(inputfile)

    dst_file_base = clean_file_name(dst_file_base, keep_ext=False)

    dst_file_base += inputfile.file_name.suffix

    return dst_dir / dst_file_base

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
    if inputfile.tags.episode == (0,):
        suggest_tags.episode = inputfile.tags.episode = None

    # EPISODE

    do_suggest_tags(inputfile, suggest_tags=suggest_tags)

    for tag in (
            'tvshow',   # Not allowed to be empty
            ):
        if tag and not getattr(inputfile.tags, tag):
            raise MissingMediaTagError(tag, file=inputfile)

    dst_dir = Path()

    # https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/
    # https://github.com/MediaBrowser/Wiki/wiki/TV-naming
    # TVSHOW/
    dst_dir /= clean_file_name(inputfile.tags.tvshow, keep_ext=False)

    if inputfile.tags.season is None:
        assert inputfile.tags.episode is None
        if inputfile.tags.contenttype is None:
            raise MissingMediaTagError('contenttype', file=inputfile)

        dst_file_base = ''

    else:
        # https://github.com/MediaBrowser/Wiki/wiki/TV-naming
        # .../Season 1/
        # .../Specials/
        if inputfile.tags.season == 0:
            dst_dir /= 'Specials/'
        else:
            dst_dir /= f'Season {inputfile.tags.season}'

        dst_file_base = ''

    if inputfile.tags.episode is None:
        # Show/Season extra
        # https://github.com/contrary-cat/LocalTVExtras.bundle
        if inputfile.tags.contenttype is None:
            raise MissingMediaTagError('contenttype', file=inputfile)

        if app.args.media_library_app == 'mmdemux':
            # TVSHOW S01E00 ...
            dst_file_base += inputfile.tags.tvshow
            dst_file_base += ' S%02dE00' % (
                inputfile.tags.season,
                )
            dst_file_base_SE = dst_file_base
            if inputfile.tags.title and inputfile.tags.title != inputfile.tags.tvshow:
                dst_file_base += ' %s' % (inputfile.tags.title,)
            else:
                pass  # Could be the episode name is not known.

            # -- ContentType
            if dst_file_base != dst_file_base_SE:
                dst_file_base += ' --'
            dst_file_base += f' {inputfile.tags.contenttype}'
            if inputfile.tags.comment:
                # COMMENT
                dst_file_base += f': {inputfile.tags.comment[0]}'

        else:
            # COMMENT|TITLE
            if inputfile.tags.comment:
                # COMMENT
                dst_file_base = '%s' % (inputfile.tags.comment[0],)
            elif inputfile.tags.title:
                # TITLE
                dst_file_base = '%s' % (inputfile.tags.title,)
            else:
                # ContentType
                dst_file_base = str(inputfile.tags.contenttype)

    else:
        if inputfile.tags.season is None:
            raise MissingMediaTagError('season', file=inputfile)
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
                dst_file_base += '-E%02d' % (episodes[-1],)
        dst_file_base_SE = dst_file_base
        if inputfile.tags.title and inputfile.tags.title != inputfile.tags.tvshow:
            dst_file_base += ' %s' % (inputfile.tags.title,)
        else:
            pass  # Could be the episode name is not known.

        if inputfile.tags.contenttype in (
                None,
                qip.mm.ContentType.cartoon):
            pass  # Ok
        else:
            # Episode extra
            if app.args.media_library_app == 'mmdemux':
                # -- ContentType
                if dst_file_base != dst_file_base_SE:
                    dst_file_base += ' --'
                dst_file_base += f' {inputfile.tags.contenttype}'
                if inputfile.tags.comment:
                    # COMMENT
                    dst_file_base += f': {inputfile.tags.comment[0]}'
            else:
                # https://github.com/contrary-cat/LocalTVExtras.bundle
                # COMMENT
                if inputfile.tags.comment:
                    # COMMENT
                    dst_file_base += '-%s' % (inputfile.tags.comment[0],)
                else:
                    # ContentType
                    dst_file_base = str(inputfile.tags.contenttype)

    dst_file_base += get_plex_format_hints_suffix(inputfile, dst_file_base)

    if inputfile.tags.contenttype in (
            None,
            qip.mm.ContentType.cartoon):
        pass  # Ok
    else:
        if app.args.media_library_app == 'mmdemux':
            pass  # Ok
        else:
            dst_file_base += get_plex_contenttype_suffix(inputfile,
                                                         dbtype='tvshow')

    dst_file_base += format_part_suffix(inputfile)

    # TODO https://support.plex.tv/articles/200220677-local-media-assets-movies/

    if app.args.media_library_app != 'mmdemux':
        dst_file_base = clean_file_name(dst_file_base, keep_ext=False)
    dst_file_base += inputfile.file_name.suffix

    return dst_dir / dst_file_base

def organize(inputfile):

    if isinstance(inputfile, str):
        inputfile = Path(inputfile)
    if isinstance(inputfile, Path) and inputfile.is_dir():
        inputdir = inputfile
        app.log.verbose('Recursing into %s...', inputdir)
        for inputfile_path in sorted(set(inputdir.glob('**/*'))):
            inputext = inputfile_path.suffix
            if (inputext in supported_media_exts
                    or inputfile_path.is_dir()):
                organize(inputfile_path)
        return True

    if not isinstance(inputfile, MediaFile):
        inputfile = MediaFile.new_by_file_name(inputfile)

    if not inputfile.file_name.is_file():
        raise OSError(errno.ENOENT, 'No such file', inputfile.file_name)
    app.log.info('Organizing %s...', inputfile)
    inputfile.extract_info(need_actual_duration=False)
    #inputfile.tags = inputfile.load_tags()  # Already done by extract_info
    if app.log.isEnabledFor(logging.DEBUG):
        inputfile.tags.pprint()

    suggest_tags = TrackTags()

    if app.args.contenttype:
        inputfile.tags.contenttype = app.args.contenttype
    orig_type = inputfile.tags.type = inputfile.deduce_type()
    if getattr(app.args, 'library_mode', None):
        inputfile.tags.type = app.args.library_mode
    inputfile.tags.type = inputfile.deduce_type()

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
        opath = organize_music(inputfile, suggest_tags=suggest_tags)
    elif inputfile.tags.type == 'audiobook':
        opath = organize_audiobook(inputfile, suggest_tags=suggest_tags)
    elif inputfile.tags.type == 'musicvideo':
        if app.args.media_library_app == 'emby':
            app.log.debug('emby: musicvideo -> music')
            opath = organize_music(inputfile, suggest_tags=suggest_tags,
                                  dbtype='musicvideo')
        elif True or app.args.media_library_app in ('plex', 'mmdemux'):
            app.log.debug('plex: musicvideo -> inline musicvideo')
            opath = organize_inline_musicvideo(inputfile, suggest_tags=suggest_tags)
    elif inputfile.tags.type == 'movie':
        opath = organize_movie(inputfile, suggest_tags=suggest_tags, orig_type=orig_type)
    elif inputfile.tags.type == 'tvshow':
        opath = organize_tvshow(inputfile, suggest_tags=suggest_tags)
    else:
        raise ValueError('type = %r' % (inputfile.tags.type,))
    dst_dir, dst_file_base = opath.parent, opath.name
    outputdir = getattr(app.args, 'outputdir', None)
    if not outputdir and app.args.use_default_output:
        try:
            outputdir = Path(app.config_file_parser['default-output'][inputfile.tags.type]).resolve()
        except (TypeError, KeyError):
            # TypeError: 'NoneType' object is not subscriptable
            raise ValueError(f'No output directory specified and no default set for type {inputfile.tags.type!r}')
    dst_dir = outputdir / dst_dir

    src_stat = os.lstat(inputfile.file_name)
    skip = False
    for n in range(1,10):
        dst_file_tail = clean_file_name(dst_file_base,
                                        extra='-%d' % (n,) if n > 1 else '')
        dst_file_name = os.fspath(dst_dir / dst_file_tail)
        if os.path.exists(dst_file_name):
            dst_stat = os.lstat(dst_file_name)
            if dst_stat.st_ino == src_stat.st_ino:
                app.log.verbose('  Use existing %s.', dst_file_name)
                skip = True
                break
            else:
                if app.args.overwrite:
                    app.log.debug('  Collision with %s. (overwriting)', dst_file_name)
                else:
                    app.log.debug('  Collision with %s.', dst_file_name)
                    continue
        if not dst_dir.exists():
            if app.args.dry_run:
                app.log.info('  Create %s. (dry-run)', dst_dir)
            else:
                app.log.info('  Create %s.', dst_dir)
                dst_dir.mkdir(parents=True)
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
                dst_aux_file_name = os.fspath(dst_dir / dst_aux_file_tail)
                if os.path.exists(dst_aux_file_name):
                    if app.args.overwrite:
                        app.log.debug('  Collision with %s. (overwriting)', dst_aux_file_name)
                    else:
                        raise OSError(errno.EEXIST, dst_aux_file_name)
                aux_moves.append((aux_file_name, dst_aux_file_name))

        def do_file_op(src, dst, *, is_aux=False):
            s_dry_run = " (dry-run)" if app.args.dry_run else ""
            s_to_aux = "aux" if is_aux else "to"
            if app.args.copy or app.args.link:
                app.log.info('  Copy %s %s.%s', s_to_aux, dst, s_dry_run)
                if not app.args.dry_run:
                    if app.args.link:
                        qip.utils.progress_copy2_link(src, dst)
                    else:
                        qip.utils.progress_copy2(src, dst)
            else:
                app.log.info('  Rename %s %s.%s', s_to_aux, dst, s_dry_run)
                if not app.args.dry_run:
                    qip.utils.progress_move(src, dst)

        do_file_op(inputfile.file_name, dst_file_name)
        for aux_file_name, dst_aux_file_name in aux_moves:
            do_file_op(aux_file_name, dst_aux_file_name, is_aux=True)
        if not (app.args.copy or app.args.link):
            inputdir = os.path.dirname(inputfile.file_name)
            if inputdir not in ('.', '') and dir_empty(inputdir):
                app.log.info('Remove %s.', inputdir)
                if not app.args.dry_run:
                    os.rmdir(inputdir)
        break
    else:
        raise ValueError('Ran out of options / Too many collisions!')

    return True


if __name__ == "__main__":
    main()
