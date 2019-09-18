#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

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
import mutagen
import os
import pexpect
import re
import reprlib
import shutil
import subprocess
import sys
import tempfile
reprlib.aRepr.maxdict = 100

from qip import json
from qip.app import app
from qip.cmp import *
from qip.exec import *
from qip.file import *
from qip.parser import *
from qip.perf import perfcontext
from qip.mm import *
from qip.img import *
from qip.utils import byte_decode
import qip.mm

import mutagen.mp4
mutagen.mp4.MP4Tags._MP4Tags__atoms[b'idx'] = (
    mutagen.mp4.MP4Tags._MP4Tags__parse_text,
    mutagen.mp4.MP4Tags._MP4Tags__render_text,
)

m4a_prepped_picture = None

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

    #https://genius.com/api-clients
    #API Clients
    #App Website URL
    #    http://qualipsoft.com/taged/
    #Redirect URI
    #    http://qualipsoft.com/taged/
    #Client ID
    #    mudU4SVqVbrQ4YG0dKDnOPktNbJ65sW3mB2yPG8SVhTJ3JiskPPgLKeKvlDgzhnK
    #Client Secret
    #    gY66ic2V2vcdFhXLlEwUiZBWx8ZdlxQG5ab8IRTgIjamUGZVL54Nqq2qn2ODN_291zw-0966Azio8EaOLfel2g
    #Client Access Token
    #    djPgExvVVDyXSaNLTpyZrsbAZ8JsC4cvMtQyXogt0oIcV_9BnY_EKBpu3Ixds83o
    os.environ.setdefault('GENIUS_CLIENT_ACCESS_TOKEN',
                          'djPgExvVVDyXSaNLTpyZrsbAZ8JsC4cvMtQyXogt0oIcV_9BnY_EKBpu3Ixds83o')

    app.init(
            version='1.0',
            description='Tag Editor',
            contact='jst@qualipsoft.com',
            )

    in_tags = TrackTags()

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
    pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')
    pgroup.add_argument('--save-temps', dest='save_temps', default=False, action='store_true', help='do not delete intermediate files')
    pgroup.add_argument('--no-save-temps', dest='save_temps', default=argparse.SUPPRESS, action='store_false', help='delete intermediate files (default)')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

    pgroup = app.parser.add_argument_group('Actions')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--set', dest='action', default=None, action='store_const', const='set', help='set tags')
    xgroup.add_argument('--edit', dest='action', default=argparse.SUPPRESS, action='store_const', const='edit', help='edit tags')
    xgroup.add_argument('--list', dest='action', default=argparse.SUPPRESS, action='store_const', const='list', help='list tags')
    xgroup.add_argument('--apply', dest='action', default=argparse.SUPPRESS, action='store_const', const='apply', help='apply tags')
    xgroup.add_argument('--find-lyrics', dest='action', default=argparse.SUPPRESS, action='store_const', const='find_lyrics', help='find lyrics')

    pgroup = app.parser.add_argument_group('Compatibility')
    pgroup.add_argument('--prep-picture', dest='prep_picture', action='store_true', help='prepare picture')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--ipod-compat', dest='ipod_compat', default=True, action='store_true', help='iPod compatibility (default)')
    xgroup.add_argument('--no-ipod-compat', dest='ipod_compat', default=argparse.SUPPRESS, action='store_false', help='iPod compatibility (disable)')

    pgroup = app.parser.add_argument_group('Other')
    pgroup.add_argument('--format', default='human', choices=('human', 'json'), help='Output list format')

    pgroup = app.parser.add_argument_group('Lyrics')
    pgroup.add_argument('--genius-timeout', dest='genius_timeout', default=5, type=int, help='Genius API timeout')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--lyrics-section-headers', dest='lyrics_section_headers', default=True, action='store_true', help='Include lyrics section headers (default)')
    xgroup.add_argument('--no-lyrics-section-headers', dest='lyrics_section_headers', default=argparse.SUPPRESS, action='store_false', help='Do not nclude lyrics section headers')
    pgroup.add_argument('--lyrics-exclude-terms', dest='lyrics_exclude_terms', default=[], nargs="+", help='Terms to exclude from title songs')
    pgroup.add_argument('--lyrics-save', dest='lyrics_save', action='store_true', help='Save lyrics to .txt file if found')
    pgroup.add_argument('--lyrics-embed', dest='lyrics_embed', action='store_true', help='Embed lyrics in sound file if found')

    pgroup = app.parser.add_argument_group('Tags')
    xgroup.add_argument('--import', dest='import_file', default=None, type=qip.file.File.argparse_type(), help='import tags')
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
    pgroup.add_argument('--recording-location', dest='recording_location', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--recording-date', dest='recording_date', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--compilation', '-K', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--gapless', '-Q', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-grouping', dest='sortgrouping', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumartist', dest='sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumtitle', '--sort-album', dest='sortalbumtitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-artist', dest='sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-title', '--sort-song', dest='sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-composer', '--sort-writer', dest='sortcomposer', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--sort-tvshow', dest='sorttvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)
    pgroup.add_argument('--xid', tags=in_tags, default=argparse.SUPPRESS, action=qip.mm.ArgparseSetTagAction)

    app.parser.add_argument('files', nargs='*', default=None, help='sound files')

    app.parse_args()

    if app.args.import_file:
        if getattr(app.args, 'action', None) is None:
            app.args.action = 'set'
        import_content = None
        if app.args.import_file.file_name is None:
            import_content = app.args.import_file.read()
            app.args.import_file.close()
            if import_content.startswith('{'):
                app.args.import_file = json.JsonFile(file_name='<stdin>')
        if isinstance(app.args.import_file, json.JsonFile):
            if import_content is None:
                import_content = json.load(app.args.import_file.fp)
                app.args.import_file.close()
            else:
                import_content = json.loads(import_content)
            if not isinstance(import_content, TrackTags):
                import_content = TrackTags(import_content)
            app.log.debug('Imported tags: %r', import_content)
            in_tags.update(import_content)
        else:
            raise NotImplementedError(f'Unrecognized import file format')

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'set' if in_tags else 'edit'
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    for prog in (
            ):
        if not shutil.which(prog):
            raise Exception('%s: command not found' % (prog,))
    for prog in (
            ):
        if not shutil.which(prog):
            app.log.warning('%s: command not found; Functionality may be limited.', prog)

    if app.args.action == 'set':
        # {{{

        if not app.args.files:
            raise Exception('No files provided')
        for file_name in app.args.files:
            with perfcontext('taged'):
                taged(file_name, in_tags)

        # }}}
    elif app.args.action == 'edit':
        # {{{

        if not app.args.files:
            raise Exception('No files provided')
        for file_name in app.args.files:
            with perfcontext('list'):
                tageditor(file_name)

        # }}}
    elif app.args.action == 'list':
        # {{{

        if not app.args.files:
            raise Exception('No files provided')
        for file_name in app.args.files:
            with perfcontext('list'):
                taglist(file_name, app.args.format)

        # }}}
    elif app.args.action == 'find_lyrics':
        # {{{

        import lyricsgenius
        genius = lyricsgenius.Genius(
                os.environ['GENIUS_CLIENT_ACCESS_TOKEN'],
                timeout=app.args.genius_timeout,
                sleep_time=0.5 if len(app.args.files) > 1 else 0,  # Enforce rate limiting
                verbose = app.log.isEnabledFor(logging.VERBOSE),
                remove_section_headers=not app.args.lyrics_section_headers,
                excluded_terms=app.args.lyrics_exclude_terms,
                )

        #if not app.args.files:
        #    raise Exception('No files provided')
        if app.args.files:
            file_names = app.args.files
        else:
            file_names = [None]
            if in_tags.artist is None or in_tags.title is None:
                raise Exception('%s: --artist and --title required to find lyrics' % (prog,))

        for file_name in file_names:
            lyrics = find_lyrics(file_name, genius=genius, tags=in_tags).rstrip()
            if not lyrics:
                app.log.error('%s: Lyrics not found for %s', prog, file_name)
                continue
            print_lyrics = True
            if app.args.interactive:
                print(lyrics)
                print_lyrics = False
                while True:
                    print('')
                    print('Interactive mode...')
                    print(' e - edit lyrics')
                    print(' q - quit')
                    print(' y - yes, continue!')
                    c = input('Choice: ')
                    if c == 'e':
                        lyrics = edvar(lyrics)[1].rstrip()
                    elif c == 'q':
                        return False
                    elif c == 'y':
                        break
                    else:
                        app.log.error('Invalid input')
            if file_name is not None:
                if app.args.lyrics_save:
                    lyrics_file = TextFile(os.path.splitext(file_name)[0] + '.txt')
                    assert app.args.yes or not lyrics_file.exists()
                    app.log.info('Writing lyrics to %s', lyrics_file)
                    lyrics_file.write(lyrics)
                    print_lyrics = False
                if app.args.lyrics_embed:
                    taged(file_name, TrackTags(lyrics=lyrics))
                    print_lyrics = False
            if print_lyrics:
                print(lyrics)
                print_lyrics = False

        # }}}
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

def find_lyrics(file_name, *, genius=None, tags=None, **kwargs):

    if not genius:
        client_access_token = kwargs.get('client_access_token', None)
        if not client_access_token:
            client_access_token = os.environ.get("GENIUS_CLIENT_ACCESS_TOKEN", None)
        assert client_access_token, 'Must declare environment variable: GENIUS_CLIENT_ACCESS_TOKEN'
        kwargs['client_access_token'] = client_access_token
        kwargs.setdefault('verbose', app.log.isEnabledFor(logging.VERBOSE))
        import lyricsgenius
        genius = lyricsgenius.Genius(
                os.environ['GENIUS_CLIENT_ACCESS_TOKEN'],
                **kwargs)

    if file_name is not None:
        mm_file = MediaFile.new_by_file_name(file_name)
        tags = mm_file.load_tags()
    with perfcontext('genius.search_song'):
        song = genius.search_song(tags.title, tags.artist)
    if song:
        return song.lyrics
    return None

def taged_mf_id3(file_name, mf, tags):
    # http://id3.org/Developer%20Information
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.debug('Old tags: %r', list(mf.tags.keys()))
    app.log.debug('Mod tags: %r', list(tags.keys()))
    for tag, value in tags.items():
        tag = tag.name
        if tag in ('track', 'tracks'):
            tag = 'track_slash_tracks'
            value = tags[tag]
        elif tag in ('disk', 'disks'):
            tag = 'disk_slash_disks'
            value = tags[tag]
        try:
            mapped_tag = qip.mm.sound_tag_info['map'][tag]
            id3_tag = qip.mm.sound_tag_info['tags'][mapped_tag]['id3v2_30_tag']
        except KeyError:
            raise NotImplementedError(tag)
        if id3_tag == 'TPE2':  # albumartist
            if mf.tags.pop('TXXX:QuodLibet::albumartist', None) is not None:
                app.log.verbose(' Removed %s (%s)', tag, 'TXXX:QuodLibet::albumartist')
        if value is None:
            if mf.tags.pop(id3_tag, None) is not None:
                app.log.verbose(' Removed %s (%s)', tag, id3_tag)
        else:
            mf.tags[id3_tag] = getattr(mutagen.id3, id3_tag)(encoding=mutagen.id3.Encoding.UTF8, text=str(value))
            app.log.verbose(' Set %s (%s): %r', tag, id3_tag, value)
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.debug('New tags: %r', list(mf.tags.keys()))
    return True

def taged_mf_MP4Tags(file_name, mf, tags):
    assert mutagen.version >= (1, 42, 0), f'Update mutagen ({mutagen.version_string}) module to at least 1.42.0'
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.debug('Old tags: %r', list(mf.tags.keys()))
    tags_to_set = set(tags.keys())
    #app.log.debug('tags %r, tags_to_set: %r', type(tags), tags_to_set)
    if MediaTagEnum.disk in tags_to_set:
        tags_to_set.discard(MediaTagEnum.disks)
    if MediaTagEnum.track in tags_to_set:
        tags_to_set.discard(MediaTagEnum.tracks)
    if MediaTagEnum.contenttype in tags_to_set:
        tags_to_set.discard(MediaTagEnum.contenttype)
        tags_to_set.add(MediaTagEnum.type)
    for tag in (
            MediaTagEnum.barcode,
            MediaTagEnum.isrc,
            MediaTagEnum.asin,
            MediaTagEnum.isrc,
            MediaTagEnum.musicbrainz_discid,
            MediaTagEnum.cddb_discid,
            MediaTagEnum.accuraterip_discid,
    ):
        if tag in tags_to_set:
            tags_to_set.remove(tag)
            tags_to_set.add(MediaTagEnum.xid)
    for tag in tags_to_set:
        if tag in (
                MediaTagEnum.musicbrainz_releaseid,
                MediaTagEnum.mediatype,
        ):
            continue
        tag = tag.name
        if tag == 'type':
            mm_file = MediaFile.new_by_file_name(file_name)
            mm_file.tags = tags
            value = mm_file.deduce_type()
        else:
            value = tags[tag]
        try:
            mapped_tag = qip.mm.sound_tag_info['map'][tag]
            mp4_tag = qip.mm.sound_tag_info['tags'][mapped_tag]['mp4v2_tag']
            mp4v2_data_type = qip.mm.sound_tag_info['tags'][mapped_tag]['mp4v2_data_type']
        except KeyError:
            raise NotImplementedError(tag)
        if mp4_tag in 'xid':
            value = tags.xids or None
        if value is None:
            if mf.tags.pop(mp4_tag, None) is not None:
                app.log.verbose(' Removed %s (%s)', tag, mp4_tag)
        else:
            if mp4v2_data_type == 'utf-8':
                if mp4_tag == 'xid':
                    mp4_value = [str(v) for v in value]
                elif mp4_tag == '©cmt':
                    if isinstance(value, tuple):
                        mp4_value = '\n'.join(value)
                    elif isinstance(value, str):
                        mp4_value = value
                    else:
                        raise NotImplementedError(value)
                else:
                    mp4_value = str(value)
                    if mp4_tag.startswith('----:'):
                        # freeform tags are expected in bytes
                        mp4_value = mp4_value.encode('utf-8')
            elif mp4v2_data_type == 'bool8':
                mp4_value = 1 if value else 0
            elif mp4v2_data_type in ('int8', 'int16', 'int32', 'int64'):
                if mp4_tag == 'sfID':
                    # raise ValueError('value %r = %r -> %s' % (type(value), value, value))
                    mp4_value = [qip.mm.mp4_country_map[value]]
                else:
                    mp4_value = int(value)
            elif mp4v2_data_type in ('binary',):
                if mp4_tag == 'disk':  # disk
                    # arg must be a list of 1(or more) tuple of (track, total)
                    mp4_value = [(int(tags.disk), int(tags.disks or 0))]
                elif mp4_tag == 'trkn':  # track
                    # arg must be a list of 1(or more) tuple of (track, total)
                    mp4_value = [(int(tags.track), int(tags.tracks or 0))]
                else:
                    raise NotImplementedError((tag, mp4v2_data_type))
            elif mp4v2_data_type in ('picture',):
                assert mp4_tag == 'covr'
                mp4_value = []
                from qip.file import cache_url
                value = cache_url(str(value))
                if getattr(app.args, 'prep_picture', False):
                    global m4a_prepped_picture
                    if not m4a_prepped_picture:
                        from qip.mp4 import M4aFile
                        m4a = M4aFile(file_name)
                        m4a_prepped_picture = m4a.prep_picture(value)
                    value = m4a_prepped_picture
                img_file = ImageFile(str(value))
                img_type = img_file.image_type
                if img_type is ImageType.jpg:
                    img_type = mutagen.mp4.MP4Cover.FORMAT_JPEG
                elif img_type is ImageType.png:
                    img_type = mutagen.mp4.MP4Cover.FORMAT_PNG
                else:
                    raise ValueError('Unsupported image type: %s' % (img_type,))
                with img_file.open('rb') as fp:
                    v = fp.read()
                    mp4_value.append(mutagen.mp4.MP4Cover(v, img_type))
            elif mp4v2_data_type in ('enum8',):
                if mp4_tag == 'stik':
                    if isinstance(value, str):
                        value = qip.mm.tag_stik_info['map'][value.lower()]
                    value = qip.mm.tag_stik_info['stik'][value]['stik']
                    mp4_value = [value]
                else:
                    raise NotImplementedError((tag, mp4v2_data_type))
            else:
                raise NotImplementedError((tag, mp4v2_data_type))
            try:
                mf.tags[mp4_tag] = mp4_value
            except:
                if mp4_tag in ('covr',):
                    app.log.debug('ERROR! mf.tags[%r] = ...', mp4_tag)
                else:
                    app.log.debug('ERROR! mf.tags[%r] = %r', mp4_tag, mp4_value)
                raise
            if mp4_tag in ('covr',):
                app.log.verbose(' Set %s (%s)', tag, mp4_tag)
            else:
                app.log.verbose(' Set %s (%s): %r', tag, mp4_tag, mp4_value)
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.debug('New tags: %r', list(mf.tags.keys()))
    return True

def taged_mf(file_name, mf, tags):
    if isinstance(mf.tags, mutagen.id3.ID3):
        return taged_mf_id3(file_name, mf, tags)
    if isinstance(mf.tags, mutagen.mp4.MP4Tags):
        return taged_mf_MP4Tags(file_name, mf, tags)
    raise NotImplementedError(mf.tags.__class__.__name__)

def find_Tag_element(root, *, TargetTypeValue, TargetType=None, TrackUID=0):
    TrackUID = str(TrackUID) if TrackUID is not None else '0'
    TargetTypeValue = str(TargetTypeValue) if TargetTypeValue is not None else '50'
    TargetType = str(TargetType) if TargetType is not None else None
    for eTag in root.findall('Tag'):
        eTargets = eTag.find('Targets')
        eTrackUID = eTargets.find('TrackUID')
        vTrackUID = eTrackUID.text if (eTrackUID is not None and eTrackUID.text is not None) else '0'
        if vTrackUID != TrackUID:
            continue
        eTargetTypeValue = eTargets.find('TargetTypeValue')
        vTargetTypeValue = eTargetTypeValue.text if (eTargetTypeValue is not None and eTargetTypeValue.text is not None) else '50'
        if vTargetTypeValue != TargetTypeValue:
            continue
        eTargetType = eTargets.find('TargetType')
        vTargetType = eTargetType.text if eTargetType is not None else '50'
        if vTargetType != TargetType:
            continue
        return eTag

def taged_Matroska(file_name, tags):
    import qip.matroska
    import qip.utils
    # https://matroska.org/technical/specs/tagging/index.html
    matroska_file = qip.matroska.MatroskaFile.new_by_file_name(file_name)
    matroska_file.tags = matroska_file.load_tags()
    matroska_file.tags.update(tags)
    tags_list = matroska_file.create_tags_list()
    tags_xml = matroska_file.create_tags_xml_from_list(tags_list)
    app.log.debug('tags_xml: %s', qip.utils.prettyxml(tags_xml))
    matroska_file.set_tags_xml(tags_xml)

def taged(file_name, tags):
    app.log.info('Editing %s...', file_name)
    with perfcontext('mf.load'):
        mf = mutagen.File(file_name)
    if mf:
        if not taged_mf(file_name, mf, tags):
            app.log.verbose('Nothing to do.')
            return False
        if getattr(app.args, 'dry_run', False):
            app.log.verbose('Not saving. (dry-run)')
        else:
            with perfcontext('mf.save'):
                mf.save()
        return True
    file_base, file_ext = os.path.splitext(file_name)
    if file_ext in ('.mka', '.mkv', '.webm'):
        return taged_Matroska(file_name, tags)
    raise NotImplementedError(file_ext)
    return True

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

def tageditor(file_name):
    app.log.info('Editing %s...', file_name)
    mm_file = MediaFile.new_by_file_name(file_name)
    import qip.matroska
    if isinstance(mm_file, qip.matroska.MatroskaFile):
        tags_xml = mm_file.get_tags_xml()
        modified, tags_xml = edvar(tags_xml)
        if modified:
            mm_file.set_tags_xml(tags_xml)
        return True
    raise NotImplementedError(mm_file)

def taglist(file_name, format):
    if format == 'human':
        app.log.info('Listing %s...', file_name)
    mm_file = MediaFile.new_by_file_name(file_name)
    app.log.debug('mm_file = %r', mm_file)
    tags = mm_file.load_tags()
    assert tags is not None
    if format == 'human':
        dump_tags(tags)
        sys.stdout.flush()  # Sync with logging
    elif format == 'json':
        json.dump(tags, fp=sys.stdout)
        sys.stdout.flush()  # Sync with logging
    else:
        raise NotImplementedError(format)
    return True

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
