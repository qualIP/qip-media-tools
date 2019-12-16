#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

import argparse
import functools
import logging
import musicbrainzngs
import os
import pexpect
import re
import shutil
import subprocess
import sys
import urllib
import types

from qip import json
from qip.app import app
from qip.cdda import *
from qip.exec import *
from qip.extern import CDDB
from qip.file import *
from qip.mm import *
from qip.utils import byte_decode
import qip.cdda as cdda

class MusicBrainzLoggingFilter(logging.Filter):
    def filter(self, record):
        if record.levelno == logging.INFO:
            if record.msg % record.args == 'in <ws2:disc>, uncaught <offset-list>':
                return False
            if record.msg % record.args == 'in <ws2:release-group>, uncaught attribute type-id':
                return False
        return True

musicbrainzLoggingFilter = MusicBrainzLoggingFilter()
logging.getLogger("musicbrainzngs").addFilter(musicbrainzLoggingFilter)

def set_useragent(app, version, contact=None):
    if False:
        musicbrainzngs.set_useragent(app, version, contact)
    else:
        """Set the User-Agent to be used for requests to the MusicBrainz webservice.
        This must be set before requests are made."""
        #global _useragent, _client
        from musicbrainzngs import musicbrainz as _mb
        if not app or not version:
            raise ValueError("App and version can not be empty")
        if contact is not None:
            #_useragent = "%s/%s python-musicbrainzngs/%s ( %s )" % (app, version, _version, contact)
            _mb._useragent = "%s/%s ( %s )" % (app, version, contact)
        else:
            #_useragent = "%s/%s python-musicbrainzngs/%s" % (app, version, _version)
            _mb._useragent = "%s/%s" % (app, version)
        #_client = "%s-%s" % (app, version)
        _mb._client = "%s-%s" % (app, version)
        _mb._log.debug("set user-agent to %s" % _mb._useragent)

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='BIN/CUE Tagger',
            contact='jst@qualipsoft.com',
            )

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    #pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
    #pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')
    pgroup.add_argument('--save-temps', dest='save_temps', default=False, action='store_true', help='do not delete intermediate files')
    pgroup.add_argument('--no-save-temps', dest='save_temps', default=argparse.SUPPRESS, action='store_false', help='delete intermediate files (default)')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

    pgroup = app.parser.add_argument_group('Database Control')
    pgroup.add_argument('--cddb', dest='use_cddb', default=True, action='store_true', help='Use CDDB')
    pgroup.add_argument('--no-cddb', dest='use_cddb', default=argparse.SUPPRESS, action='store_false', help='Do not use CDDB')
    pgroup.add_argument('--musicbrainz', dest='use_musicbrainz', default=True, action='store_true', help='Use MusicBrainz')
    pgroup.add_argument('--no-musicbrainz', dest='use_musicbrainz', default=argparse.SUPPRESS, action='store_false', help='Do not use MusicBrainz')
    pgroup.add_argument('--cache', dest='use_cache', default=True, action='store_true', help='Use caching')
    pgroup.add_argument('--no-cache', dest='use_cache', default=argparse.SUPPRESS, action='store_false', help='Do not use caching')

    pgroup.add_argument('--mb-discid', dest='musicbrainz_discid', default=None, help='specify MusicBrainz discid')
    pgroup.add_argument('--mb-releaseid', dest='musicbrainz_releaseid', default=None, help='specify MusicBrainz releaseid')
    pgroup.add_argument('--cddb-discid', dest='cddb_discid', default=None, help='specify CDDB discid')
    pgroup.add_argument('--barcode', default=None, help='specify barcode')
    pgroup.add_argument('--country', dest='country_list', default=None, nargs='*', help='specify country list')

    app.parser.add_argument('cue_files', nargs='*', default=None, type=CDDACueSheetFile.argparse_type(), help='cue file names')

    app.parse_args()

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'bincuetags'
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)

    for prog in ():
        if prog and not shutil.which(prog):
            raise Exception('%s: command not found' % (prog,))

    if app.args.action == 'bincuetags':
        if not app.args.cue_files:
            raise Exception('No CUE file names provided')
        if app.args.use_cache:
            if False:
                # Parameters are not hashable!
                musicbrainzngs.get_releases_by_discid = functools.lru_cache(typed=True)(musicbrainzngs.get_releases_by_discid)
                musicbrainzngs.get_release_by_id = functools.lru_cache(typed=True)(musicbrainzngs.get_release_by_id)
        for cue_file in app.args.cue_files:
            bincuetags(cue_file)
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

def mbrelease_to_tags(album_tags, mbrel):
    for k, v in mbrel.items():
        k = {
            # {
            #     'packaging': 'Jewel Case',
            #     'status': 'Official',
            #     'quality': 'normal',
            #     'asin': 'B00000JY9M',
            #     'release-event-list': [{'area': {'iso-3166-1-code-list': ['US'], 'id': '489ce91b-6658-3307-9877-795b68554c98', 'name': 'United States', 'sort-name': 'United States'}, 'date': '1999-08-24'}],
            #     'cover-art-archive': {'artwork': 'true', 'front': 'true', 'count': '2', 'back': 'true'},
            #     'id': 'd4faf895-c0c0-45ab-a912-42e99672425f',
            'id': 'musicbrainz_releaseid',
            #     'title': 'Christina Aguilera',
            #     'text-representation': {'language': 'eng', 'script': 'Latn'},
            #     'medium-count': 1,
            'medium-count': 'disks',
            #     'country': 'US',
            #     'medium-list': [
            #     {'disc-count': 15, 'disc-list': [{'id': '.sLNEoph1JD2Qc3Av5uSK8cbif4-', 'sectors': '209340'}, {'id': '05LvXK6i04M1j3kiBXNV0TET9_U-', 'sectors': '209490'}, {'id': '4lQBj33cLOjAKN80z6BFSEkN06c-', 'sectors': '208047'}, {'id': '6wGe70fCevmsNvASQkX3Ty7jGBY-', 'sectors': '209340'}, {'id': '8B9S916VNEODK4P5weQgM_IwIJo-', 'sectors': '209230'}, {'id': '8Y8_ezk0Djx_Si.1ubqtFWOBf4E-', 'sectors': '209350'}, {'id': 'CeWbtYPyDZDogQ1AJQP.6WCx_8g-', 'sectors': '209527'}, {'id': 'HkHc8wzQEuwGXZphJ_RKGKdDc3o-', 'sectors': '208085'}, {'id': 'M9zc50eiNXPkowKNO.pa_5FyLWI-', 'sectors': '209340'}, {'id': 'V_2jT25KMi8xqA4rVlwaHaq.CfI-', 'sectors': '209340'}, {'id': 'Z_0qeqthKdo3IX53K26Ep6OGTIU-', 'sectors': '210369'}, {'id': 'gCKyAvNkxL5FK0EXr.0ckLN0FOA-', 'sectors': '208047'}, {'id': 'hO07pF1acOAleHPXZljhZhBlPLo-', 'sectors': '209200'}, {'id': 'igBGRmnohBOe.S.oOjAnrYK7yfI-', 'sectors': '208077'}, {'id': 'rif7SkN0YELLexm8umpjTYD68mI-', 'sectors': '209562'}], 'position': '1', 'track-list': [], 'track-count': 12, 'format': 'CD'}
            #     ],
            #     'barcode': '078636769028',
            #     'date': '1999-08-24',
            #     'release-event-count': 1
            # /
            #     'label-info-list': [
            #         {'catalog-number': '74321780542', 'label': {'id': '1ca5ed29-e00b-4ea5-b817-0bcca0e04946', 'disambiguation': "RCA Records: simple ‘RCA’ or 'RCA' with lightning bolt in circle", 'sort-name': 'RCA', 'label-code': '316', 'name': 'RCA'}}
            #     ],
            #     'label-info-count': 1,
            #     'release-event-count': 1,
            #     'artist-credit-phrase': 'Christina Aguilera',
            'artist-credit-phrase': 'artist',
            #     'barcode': '743217805425',
            #     'status': 'Official',
            #     'release-event-list': [...],
            #     'packaging': 'Jewel Case',
            #     'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}],
            #     'country': 'XE',
            #     'date': '2000-11-06',
            #     'date': '1987-09',
            #     'date': '2006',
            #     'title': 'Christina Aguilera',
            #     'cover-art-archive': {'front': 'true', 'back': 'false', 'artwork': 'true', 'count': '1'},
            #     'text-representation': {'language': 'eng', 'script': 'Latn'},
            #     'quality': 'normal',
            #     'medium-list': [...],
            #     'asin': 'B00004Y7XO'}
        }.get(k, k)
        if k:
            try:
                album_tags[k] = v
            except KeyError:
                pass
        if mbrel['cover-art-archive']['front'] == 'true':

            url = 'http://coverartarchive.org/release/{id}/front'.format(**mbrel)
            album_tags.picture = get_url_location(url)

_get_url_location_cache = {}

def get_url_location(url):

    if url not in _get_url_location_cache:

        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def http_error_302(self, req, fp, code, msg, headers):
                infourl = urllib.request.addinfourl(fp, headers, req.get_full_url())
                infourl.status = code
                infourl.code = code
                return infourl
            http_error_300 = http_error_302
            http_error_301 = http_error_302
            http_error_303 = http_error_302
            http_error_307 = http_error_302

        app.log.debug('GET %s', url)
        req = urllib.request.Request(url, method='GET')
        opener = urllib.request.build_opener(NoRedirectHandler)
        with opener.open(req) as f:
            _get_url_location_cache[url] = f.headers['Location']

    return _get_url_location_cache[url]

def mbcdstub_to_tags(album_tags, mbcdstub):
    for k, v in mbcdstub.items():
        k = {
            # {
            #     'cdstub': {
            #         'track-list': [
            #             ...
            #         ],
            #         'id': 'dJCchRlRoQwXEdvoH9psmbvj.Y0-',
            'id': 'musicbrainz_cdstubid',
            #         'title': 'Afrika: Survival of the Tribal Spirit',
            #         'artist': 'John St. John'
            #     }
            # }
        }.get(k, k)
        if k:
            try:
                album_tags[k] = v
            except KeyError:
                pass


def mbmedium_to_tags(album_tags, mbmedium):
    for k, v in mbmedium.items():
        k = {
                # {
                #     'track-count': 12,
                'track-count': 'tracks',
                #     'disc-list': [...],
                #     'disc-count': 14
                # TODO 'disc-count': 'disks',
                #     'format': 'CD',
                #     'position': '1',
                'position': 'disk',
                #     'track-list': [...],
                'disc-id': 'musicbrainz_discid',
                # },
                }.get(k, k)
        if k:
            try:
                album_tags[k] = v
            except KeyError:
                pass

def mbtrack_to_tags(track_tags, mbtrack):
    for k, v in mbtrack.items():
        k = {
                # {
                #     'id': 'f838e4f1-485b-352c-9a3a-52e4af0951d9',
                'id': None,
                #     'number': '1',
                'number': None,
                #     'position': '1',
                #     'artist-credit-phrase': 'Christina Aguilera',
                'artist-credit-phrase': 'artist',
                #     'recording': {
                'recording': None,
                #     },
                #     'length': '218426',
                #     'track_or_recording_length': '218426',
                #     'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]
                # }
                }.get(k, k)
        if k:
            try:
                track_tags[k] = v
            except KeyError:
                pass
    for k, v in mbtrack.get('recording', {}).items():
        k = {
                #         'id': '748e2772-41ca-4608-8a94-70c7f7a91957',
                'id': None,
                #         'artist-credit-phrase': 'Christina Aguilera',
                'artist-credit-phrase': 'artist',
                #         'length': '218000',
                #         'title': 'Genie in a Bottle',
                #         'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]
                }.get(k, k)
        if k:
            try:
                track_tags[k] = v
            except KeyError:
                pass

def cddbinfo_to_tags(album_tags, cddb_info):
    album_tag_map = {
            'DISCID': MediaTagEnum.cddb_discid,  # 8f0ae30c
            'disc_id': MediaTagEnum.cddb_discid,  # 8f0ae30c
            'DTITLE': MediaTagEnum.title,  # Christina Aguilera / Christina Aguilera
            'title': MediaTagEnum.title,  # Christina Aguilera / Christina Aguilera
            'DYEAR': MediaTagEnum.date,  # 1999
            'DGENRE': MediaTagEnum.genre,  # Pop
            'EXTD': None,  # TODO MediaTagEnum.XXX,  #  YEAR: 1999 ID3G: 13
            'PLAYORDER': None,  # TODO MediaTagEnum.XXX,
            'submitted_via': None,
            'revision': None,
            'disc_len': None,
            'category': MediaTagEnum.genre,
            }
    track_tag_map = {
            'TTITLE': MediaTagEnum.title,  # Genie in a Bottle
            'EXTT': None,  # TODO MediaTagEnum.XXX,
            }

    for key, value in cddb_info.items():
        if value == '':
            continue
        m = re.match(r'^(TTITLE|EXTT)(\d+)$', key)
        try:
            if m:
                key = m.group(1)
                track_no = int(m.group(2)) + 1
                tag_type = track_tag_map[key]
                if tag_type:
                    value = value.strip()
                    if tag_type is MediaTagEnum.title:
                        ls = [s.strip() for s in value.split('/')]
                        if len(ls) == 2:
                            album_tags.tracks_tags[track_no].artist, value = ls
                    album_tags.tracks_tags[track_no][tag_type] = value
            else:
                tag_type = album_tag_map[key]
                if tag_type:
                    value = value.strip()
                    if tag_type is MediaTagEnum.title:
                        ls = [s.strip() for s in value.split('/')]
                        if len(ls) == 2:
                            album_tags.artist, value = ls
                    album_tags[tag_type] = value
        except ValueError as e:
            app.log.error(e)

def bincuetags(cue_file):
    if not isinstance(cue_file, CDDACueSheetFile):
        cue_file = CDDACueSheetFile(cue_file)

    if not cue_file.files:
        cue_file.read()
    app.log.debug('%r: tags: %r', cue_file, cue_file.tags)
    discid = cue_file.discid
    discid = types.SimpleNamespace(
        id=app.args.musicbrainz_discid or discid.id,
        freedb_id=app.args.cddb_discid or discid.freedb_id,
        toc=discid.toc,
        track_offsets=discid.track_offsets,
    )
    app.log.debug('%r: MusicBrainz disc ID: %r', cue_file, discid.id)
    app.log.debug('%r: CDDB/FreeDB disc ID: %r', cue_file, discid.freedb_id)

    album_tags_list = []
    mbrels = {}
    mbmediums = []
    if app.args.use_musicbrainz:
        app.log.info('Querying MusicBrainz...')
        set_useragent(app.prog, app.version, app.contact)
        try:
            d = musicbrainzngs.get_releases_by_discid(
                    discid.id,
                    toc=discid.toc,
                    includes=['artists', 'recordings', 'release-groups'],
                    )
            #d={'disc':
            #    {'release-list': [
            #        {
            #            'packaging': 'Jewel Case',
            #            'status': 'Official',
            #            'quality': 'normal',
            #            'asin': 'B00000JY9M',
            #            'release-event-list': [{'area': {'iso-3166-1-code-list': ['US'], 'id': '489ce91b-6658-3307-9877-795b68554c98', 'name': 'United States', 'sort-name': 'United States'}, 'date': '1999-08-24'}],
            #            'cover-art-archive': {'artwork': 'true', 'front': 'true', 'count': '2', 'back': 'true'},
            #            'id': 'd4faf895-c0c0-45ab-a912-42e99672425f',
            #            'title': 'Christina Aguilera',
            #            'text-representation': {'language': 'eng', 'script': 'Latn'},
            #            'medium-count': 1,
            #            'country': 'US',
            #            'medium-list': [{'disc-count': 15, 'disc-list': [{'id': '.sLNEoph1JD2Qc3Av5uSK8cbif4-', 'sectors': '209340'}, {'id': '05LvXK6i04M1j3kiBXNV0TET9_U-', 'sectors': '209490'}, {'id': '4lQBj33cLOjAKN80z6BFSEkN06c-', 'sectors': '208047'}, {'id': '6wGe70fCevmsNvASQkX3Ty7jGBY-', 'sectors': '209340'}, {'id': '8B9S916VNEODK4P5weQgM_IwIJo-', 'sectors': '209230'}, {'id': '8Y8_ezk0Djx_Si.1ubqtFWOBf4E-', 'sectors': '209350'}, {'id': 'CeWbtYPyDZDogQ1AJQP.6WCx_8g-', 'sectors': '209527'}, {'id': 'HkHc8wzQEuwGXZphJ_RKGKdDc3o-', 'sectors': '208085'}, {'id': 'M9zc50eiNXPkowKNO.pa_5FyLWI-', 'sectors': '209340'}, {'id': 'V_2jT25KMi8xqA4rVlwaHaq.CfI-', 'sectors': '209340'}, {'id': 'Z_0qeqthKdo3IX53K26Ep6OGTIU-', 'sectors': '210369'}, {'id': 'gCKyAvNkxL5FK0EXr.0ckLN0FOA-', 'sectors': '208047'}, {'id': 'hO07pF1acOAleHPXZljhZhBlPLo-', 'sectors': '209200'}, {'id': 'igBGRmnohBOe.S.oOjAnrYK7yfI-', 'sectors': '208077'}, {'id': 'rif7SkN0YELLexm8umpjTYD68mI-', 'sectors': '209562'}], 'position': '1', 'track-list': [], 'track-count': 12, 'format': 'CD'}],
            #            'barcode': '078636769028',
            #            'date': '1999-08-24',
            #            'release-event-count': 1
            #            },
            #        ...
            #        ],
            #    'id': 'hO07pF1acOAleHPXZljhZhBlPLo-',
            #    'release-count': 6,
            #    'sectors': '209200'
            #    }
            #}

            # {
            #     'cdstub': {
            #         'track-list': [
            #             {'track_or_recording_length': '313373', 'title': 'Googoola', 'length': '313373'},
            #             {'track_or_recording_length': '297706', 'title': 'Shakseti', 'length': '297706'},
            #             {'track_or_recording_length': '314960', 'title': 'Nali', 'length': '314960'},
            #             {'track_or_recording_length': '348533', 'title': 'Zooma', 'length': '348533'},
            #             {'track_or_recording_length': '292706', 'title': 'Gowgawg', 'length': '292706'},
            #             {'track_or_recording_length': '350213', 'title': 'Heavenly Mama', 'length': '350213'},
            #             {'track_or_recording_length': '264653', 'title': 'Rain Dance', 'length': '264653'},
            #             {'track_or_recording_length': '312986', 'title': 'Mayo', 'length': '312986'},
            #             {'track_or_recording_length': '227960', 'title': 'Marry Me', 'length': '227960'},
            #             {'track_or_recording_length': '255440', 'title': 'Come Back to Africa', 'length': '255440'}
            #         ],
            #         'id': 'dJCchRlRoQwXEdvoH9psmbvj.Y0-',
            #         'title': 'Afrika: Survival of the Tribal Spirit',
            #         'artist': 'John St. John'
            #     }
            # }

            if 'cdstub' in d:
                app.log.debug('Found musicbrainz cdstub...')
                mbcdstub = d['cdstub']
                album_tags = AlbumTags()
                mbcdstub_to_tags(album_tags, mbcdstub)
                #print('album_tags=%r' % (album_tags,))
                for track_no, mbtrack in enumerate(mbcdstub['track-list'], start=1):
                    track_tags = album_tags.tracks_tags[track_no]
                    mbtrack_to_tags(track_tags, mbtrack)
                    #print('track_tags=%r' % (track_tags,))
                album_tags_list.append(album_tags)
            else:
                if 'disc' in d and 'release-list' in d['disc']:
                    # Sometimes, there is no 'disc', collapse...
                    d = d['disc']
                if 'release-list' in d:
                    app.log.debug('Found musicbrainz release-list...')
                    for mbrel in d['release-list']:
                        if app.args.barcode and mbrel.get('barcode', None) != app.args.barcode:
                            continue
                        if app.args.country_list and mbrel.get('country', None) not in app.args.country_list:
                            continue
                        mbrels[mbrel['id']] = mbrel.copy()
                else:
                    app.log.error('musicbrainzngs.get_releases_by_discid returned %r', d)
        except musicbrainzngs.ResponseError as e:
            if isinstance(e.cause, urllib.HTTPError):
                if e.cause.code == 404:
                    # Not found
                    pass
                else:
                    #print('e.cause:%r' % (vars(e.cause),))
                    #print('e.cause.hdrs:%r' % (vars(e.cause.hdrs),))
                    raise
            else:
                raise

        app.log.debug('mbrels=%r', mbrels)

        for mbrelid, mbrel in mbrels.items():
            app.log.debug('Parsing musicbrainz release...')
            mbrel2 = musicbrainzngs.get_release_by_id(
                mbrelid,
                includes=["artists", "artist-credits", "recordings", "discids", "labels"],
            )
            app.log.debug('mbrel2=%r', mbrel2)
            mbrel.update(mbrel2)
            #mbrel2={'release': {
            #    'label-info-list': [
            #        {'catalog-number': '74321780542', 'label': {'id': '1ca5ed29-e00b-4ea5-b817-0bcca0e04946', 'disambiguation': "RCA Records: simple ‘RCA’ or 'RCA' with lightning bolt in circle", 'sort-name': 'RCA', 'label-code': '316', 'name': 'RCA'}}
            #    ],
            #    'label-info-count': 1,
            #    'release-event-count': 1,
            #    'artist-credit-phrase': 'Christina Aguilera',
            #    'barcode': '743217805425',
            #    'status': 'Official',
            #    'release-event-list': [{'date': '2000-11-06', 'area': {'id': '89a675c2-3e37-3518-b83c-418bad59a85a', 'sort-name': 'Europe', 'iso-3166-1-code-list': ['XE'], 'name': 'Europe'}}],
            #    'packaging': 'Jewel Case',
            #    'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}],
            #    'id': '13178962-c02f-3084-aa8a-a888cd867cde',
            #    'country': 'XE',
            #    'date': '2000-11-06',
            #    'title': 'Christina Aguilera',
            #    'cover-art-archive': {'front': 'true', 'back': 'false', 'artwork': 'true', 'count': '1'},
            #    'text-representation': {'language': 'eng', 'script': 'Latn'},
            #    'quality': 'normal',
            #    'medium-list': [
            #        {
            #            'track-count': 12,
            #            'disc-list': [{'id': '.sLNEoph1JD2Qc3Av5uSK8cbif4-', 'sectors': '209340'}, {'id': '05LvXK6i04M1j3kiBXNV0TET9_U-', 'sectors': '209490'}, {'id': '4lQBj33cLOjAKN80z6BFSEkN06c-', 'sectors': '208047'}, {'id': '6wGe70fCevmsNvASQkX3Ty7jGBY-', 'sectors': '209340'}, {'id': '8B9S916VNEODK4P5weQgM_IwIJo-', 'sectors': '209230'}, {'id': 'CeWbtYPyDZDogQ1AJQP.6WCx_8g-', 'sectors': '209527'}, {'id': 'HkHc8wzQEuwGXZphJ_RKGKdDc3o-', 'sectors': '208085'}, {'id': 'M9zc50eiNXPkowKNO.pa_5FyLWI-', 'sectors': '209340'}, {'id': 'V_2jT25KMi8xqA4rVlwaHaq.CfI-', 'sectors': '209340'}, {'id': 'Z_0qeqthKdo3IX53K26Ep6OGTIU-', 'sectors': '210369'}, {'id': 'gCKyAvNkxL5FK0EXr.0ckLN0FOA-', 'sectors': '208047'}, {'id': 'hO07pF1acOAleHPXZljhZhBlPLo-', 'sectors': '209200'}, {'id': 'igBGRmnohBOe.S.oOjAnrYK7yfI-', 'sectors': '208077'}, {'id': 'rif7SkN0YELLexm8umpjTYD68mI-', 'sectors': '209562'}],
            #            'disc-count': 14
            #            'format': 'CD',
            #            'position': '1',
            #            'track-list': [
            #                {'id': 'f838e4f1-485b-352c-9a3a-52e4af0951d9', 'number': '1', 'position': '1', 'artist-credit-phrase': 'Christina Aguilera',
            #                    'recording': {'id': '748e2772-41ca-4608-8a94-70c7f7a91957', 'artist-credit-phrase': 'Christina Aguilera', 'length': '218000', 'title': 'Genie in a Bottle', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                    'length': '218426', 'track_or_recording_length': '218426', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': 'a3994167-ebd2-37f9-b6e2-d5a32fb831f7', 'number': '2', 'position': '2', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '6002e85b-46e0-453c-9ef6-12fb383fabfb', 'artist-credit-phrase': 'Christina Aguilera', 'length': '233066', 'title': 'What a Girl Wants', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '233066', 'track_or_recording_length': '233066', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': '1801a9fe-f1a9-3ee6-810d-57faedc71e9f', 'number': '3', 'position': '3', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': 'cf4399bc-d85e-4bfb-9492-0b4578df6355', 'artist-credit-phrase': 'Christina Aguilera', 'length': '273533', 'title': 'I Turn to You', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '273533', 'track_or_recording_length': '273533', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': '44a91edf-635f-39bb-b5e1-81377f9367ce', 'number': '4', 'position': '4', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '805c3e2d-1883-4a82-bafa-34b7a84175f6', 'artist-credit-phrase': 'Christina Aguilera', 'length': '240800', 'title': 'So Emotional', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '240800', 'track_or_recording_length': '240800', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': '82bf1046-6268-34f2-87cb-620a09f7a678', 'number': '5', 'position': '5', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': 'af07c5fd-b983-42e9-9157-b585305c7e65', 'artist-credit-phrase': 'Christina Aguilera', 'length': '189866', 'title': 'Come On Over (All I Want Is You)', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '189866', 'track_or_recording_length': '189866', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': '73fade62-f95c-3e50-865d-ed47cee96c9e', 'number': '6', 'position': '6', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '8e1a9607-0c2c-4453-8048-f7ffa4a3e656', 'artist-credit-phrase': 'Christina Aguilera', 'length': '214187', 'title': 'Reflection (pop version)', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '213306', 'track_or_recording_length': '213306', 'title': 'Reflection', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': 'd5e234f6-e8a6-3998-9c50-2a3a2d070efa', 'number': '7', 'position': '7', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '3ed5c998-9753-4230-9d83-0e5413052a59', 'artist-credit-phrase': 'Christina Aguilera', 'length': '239426', 'title': 'Love for All Seasons', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '239426', 'track_or_recording_length': '239426', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': '3ac70592-3f45-3b67-862b-6af09b5330f7', 'number': '8', 'position': '8', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '426d7593-2207-45a7-8a1b-a8e89b6e585a', 'artist-credit-phrase': 'Christina Aguilera', 'length': '303640', 'title': "Somebody's Somebody", 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '303640', 'track_or_recording_length': '303640', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': '440467bb-f560-3672-8c1b-0b86c84d06a9', 'number': '9', 'position': '9', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '498a44a7-125c-4c9f-822f-f80e98a4b308', 'artist-credit-phrase': 'Christina Aguilera', 'length': '215493', 'title': 'When You Put Your Hands on Me', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '215493', 'track_or_recording_length': '215493', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': '79fa957f-5599-369d-b2de-e1bd6cc1972a', 'number': '10', 'position': '10', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': 'c3666618-cc84-42cc-915b-96554e7d2935', 'artist-credit-phrase': 'Christina Aguilera', 'length': '186040', 'title': 'Blessed', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '186040', 'track_or_recording_length': '186040', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': 'cfcbbc88-212b-35b6-ada6-d35ea2a6f817', 'number': '11', 'position': '11', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': 'f78d9e71-536f-4a8e-aac6-a6f1ca12fb4a', 'artist-credit-phrase': 'Christina Aguilera', 'length': '236400', 'title': 'Love Will Find a Way', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '236400', 'track_or_recording_length': '236400', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]},
            #                {'id': '9e46177f-497e-324b-92e2-fb472de06f29', 'number': '12', 'position': '12', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': 'f31fef74-4017-4c93-a397-cc5c77bcf0d3', 'artist-credit-phrase': 'Christina Aguilera', 'length': '239000', 'title': 'Obvious', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '239000', 'track_or_recording_length': '239000', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}
            #                ],
            #            },
            #        {'track-count': 6, 'disc-list': [{'id': 'Gb1QQt8ItdEf4SK8lSqyPnG91TY-', 'sectors': '120127'}], 'format': 'CD', 'position': '2', 'track-list': [{'id': '0db5f839-7e54-3376-b9d2-b467fdf467dc', 'number': '1', 'position': '1', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': 'c2deae55-e4c0-428c-bd3a-2a244db146e7', 'artist-credit-phrase': 'Christina Aguilera', 'length': '391466', 'title': 'Genie in a Bottle (Flavio vs. Mad Boris mix)', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '391466', 'track_or_recording_length': '391466', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, {'id': '3f4d119a-cc24-3486-bf60-56230c4fa576', 'number': '2', 'position': '2', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': 'a1ffea16-7eca-4c6c-8582-6b697dbcffe5', 'artist-credit-phrase': 'Christina Aguilera', 'length': '245733', 'title': 'What a Girl Wants (Eddie Arroyo Dance radio edit)', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '245733', 'track_or_recording_length': '245733', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, {'id': '84d6539b-0bc0-3e55-97f4-547c6613fa5b', 'number': '3', 'position': '3', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '136c7d38-abf8-4a5a-848c-98ec4c08cf48', 'artist-credit-phrase': 'Christina Aguilera', 'length': '261760', 'title': 'I Turn to You (Thunderpuss remix)', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '261760', 'track_or_recording_length': '261760', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, {'id': 'b16b0385-e90d-3378-b244-d8c64f153303', 'number': '4', 'position': '4', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '9edce578-3f71-4755-b55c-5d9dfbc84e1f', 'artist-credit-phrase': 'Christina Aguilera', 'length': '278106', 'title': 'Genio Atrapado (remix)', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '278106', 'track_or_recording_length': '278106', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, {'id': '0e537cbf-547e-36d2-b1ad-fe23b99209d4', 'number': '5', 'position': '5', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '17ea8559-2d41-4c5f-a600-10594f4e254d', 'artist-credit-phrase': 'Christina Aguilera', 'length': '219293', 'title': 'Don’t Make Me Love You (’Til I’m Ready)', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '219293', 'track_or_recording_length': '219293', 'title': "Don't Make Me Love You", 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, {'id': 'defece3b-e661-3d9e-b0ee-895de0ec7908', 'number': '6', 'position': '6', 'artist-credit-phrase': 'Christina Aguilera', 'recording': {'id': '6e151bce-8a67-4d9d-b403-a188496af7c2', 'artist-credit-phrase': 'Christina Aguilera', 'length': '204000', 'title': 'Come on Over Baby (All I Want Is You) (radio version)', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}, 'length': '203333', 'track_or_recording_length': '203333', 'artist-credit': [{'artist': {'id': 'b202beb7-99bd-47e7-8b72-195c8d72ebdd', 'sort-name': 'Aguilera, Christina', 'name': 'Christina Aguilera'}}]}], 'disc-count': 1, 'title': 'special edition'}
            #    ],
            #    'medium-count': 2,
            #    'asin': 'B00004Y7XO'}
            #}
            app.log.debug('Parsing musicbrainz medium-list...')
            medium_found = False
            for mbmedium in mbrel['release']['medium-list']:
                if mbmedium['disc-list']:
                    for mbdisc in mbmedium['disc-list']:
                        if mbdisc['id'] != discid.id:
                            continue
                        break
                    else:
                        continue
                medium_found = True
                mbmedium = mbmedium.copy()
                mbmedium['disc-id'] = discid.id  # mbdisc['id']
                mbmedium['release-id'] = mbrelid
                mbmediums.append(mbmedium)
            if not medium_found:
                app.log.error('no medium with disc id %r found!', discid.id)

        for mbmedium in mbmediums:
            app.log.debug('Parsing musicbrainz medium...')
            mbrel = mbrels[mbmedium['release-id']]
            album_tags = AlbumTags()
            mbrelease_to_tags(album_tags, mbrel)
            mbmedium_to_tags(album_tags, mbmedium)
            #print('album_tags=%r' % (album_tags,))
            for mbtrack in mbmedium['track-list']:
                track_no = int(mbtrack['position'])
                track_tags = album_tags.tracks_tags[track_no]
                mbtrack_to_tags(track_tags, mbtrack)
                #print('track_tags=%r' % (track_tags,))
            album_tags_list.append(album_tags)

    cddbinfos = []
    if app.args.use_cddb:
        app.log.info('Querying FreeDB...')
        toc = [int(e) for e in discid.toc.split()]
        #print('toc=%r' % (toc,))
        first_track = toc.pop(0)
        last_track = toc.pop(0)
        leadout_offset = toc.pop(0)
        total_time = leadout_offset / cdda.CDDA_TIMECODE_FRAME_PER_SECOND
        track_info = [
            int(discid.freedb_id, 16),
            last_track] \
            + list(discid.track_offsets) \
            + [total_time]
        #print('track_info=%r' % (track_info,))
        query_status, query_info = CDDB.query(track_info)
        #print('query_status=%r, query_info=%r' % (query_status, query_info))
        # query_status=200, query_info={'category': 'misc', 'title': 'Christina Aguilera / Christina Aguilera', 'disc_id': '8f0ae30c'}
        if query_status == 200: # OK
            cddbinfos.append(query_info)
        elif query_status in (211, 210): # Multiple
            cddbinfos.extend(query_info)
        else:
            app.log.error('CDDB Query status: %r' % (query_status,))

        for cddb_info in cddbinfos:
            app.log.debug('Found cddb info...')
            read_status, read_info = CDDB.read(cddb_info['category'], cddb_info['disc_id'])
            #print('read_status=%r, read_info=%r' % (read_status, read_info))
            # read_status=210, read_info={'TTITLE7': "Somebody's Somebody", 'TTITLE11': 'Obvious', 'TTITLE8': 'When You Put Your Hands on Me', 'DTITLE': 'Christina Aguilera / Christina Aguilera', 'DISCID': '8f0ae30c', 'TTITLE0': 'Genie in a Bottle', 'TTITLE4': 'Come On Over Baby (All I Want Is You)', 'TTITLE10': 'Love Will Find a Way', 'submitted_via': 'ExactAudioCopy v0.99pb4', 'TTITLE6': 'Love for All Seasons', 'EXTT5': '', 'revision': 8, 'TTITLE1': 'What a Girl Wants', 'EXTT7': '', 'EXTT6': '', 'EXTT8': '', 'TTITLE2': 'I Turn to You', 'PLAYORDER': '', 'EXTT1': '', 'EXTT0': '', 'TTITLE3': 'So Emotional', 'EXTT9': '', 'EXTT2': '', 'EXTD': ' YEAR: 1999 ID3G: 13', 'EXTT4': '', 'TTITLE5': 'Reflection', 'EXTT10': '', 'TTITLE9': 'Blessed', 'EXTT11': '', 'DGENRE': 'Pop', 'DYEAR': '1999', 'disc_len': 2789, 'EXTT3': ''}
            if read_status in (200, 210, 211):
                cddb_info.update(read_info)
            else:
                app.log.error('CDDB Read status: %r' % (read_status,))

        for cddb_info in cddbinfos:
            app.log.debug('Parsing cddb info...')
            app.log.debug('cddb_info=%r', cddb_info)
            album_tags = AlbumTags()
            cddbinfo_to_tags(album_tags, cddb_info)
            album_tags_list.append(album_tags)

    # Cleanup

    def cleanup_album_tags(album_tags):
        album_tags.update(cue_file.tags)
        for track_no, track_tags in album_tags.tracks_tags.items():
            if track_no in cue_file.tags.tracks_tags:
                track_tags.update(cue_file.tags.tracks_tags[track_no])
            if track_tags.contains('artist', strict=True) and track_tags.artist == album_tags.artist:
                del track_tags.artist
            if track_tags.contains('title', strict=True) and track_tags.title == album_tags.title:
                del track_tags.title
        if album_tags.contains('tracks', strict=True) and album_tags.tracks == len(album_tags.tracks_tags):
            del album_tags.tracks

    for album_tags in album_tags_list:
        cleanup_album_tags(album_tags)

    tags_file = json.JsonFile(os.path.splitext(cue_file.file_name)[0] + '.tags')

    if album_tags_list:
        album_tags_sel = 0
        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.completion import WordCompleter
        completer = WordCompleter([
            'help',
            'diff',
            'continue',
            'quit',
        ])
        print('')
        while True:
            for i, album_tags in enumerate(album_tags_list, start=1):
                print('{}{} - {}'.format(
                    '*' if album_tags_sel == i - 1 else ' ',
                    i, album_tags.short_str()))
                for track_no, track_tags in album_tags.tracks_tags.items():
                    print('  Track {:2d}: {}'.format(track_no, track_tags.short_str()))
            c = app.prompt(completer=completer)
            try:
                c = int(c)
            except ValueError:
                pass
            if c in ('help', 'h', '?'):
                print('')
                print('List of commands:')
                print('')
                print('help -- Print this help')
                print('diff -- Bring up a side-by-side diff of the tags')
                print('yes, continue -- Yes, continue processing')
                print('<n> -- Select the n\'th entry')
                print('quit -- Quit')
            elif isinstance(c, int):
                assert 1 <= c <= len(album_tags_list)
                album_tags_sel = c - 1
                break
            elif c in ('quit', 'q'):
                return False
            elif c in ('diff', 'd'):
                edcmd = ['vim', '-d']
                for i, album_tags in enumerate(album_tags_list, start=1):
                    if i == 1:
                        tags_filei = tags_file
                    else:
                        tags_filei = json.JsonFile('{}.{}'.format(tags_file.file_name, i))
                    with tags_filei.open('w', encoding='utf-8') as fp:
                        album_tags.json_dump(fp)
                        fp.write('\n')
                    edcmd.append(tags_filei.file_name)
                subprocess.call(edcmd)
                with tags_file.open('r', encoding='utf-8') as fp:
                    album_tags_list[0] = AlbumTags.json_load(fp)
                for i, album_tags in enumerate(album_tags_list, start=1):
                    if i == 1:
                        continue
                    tags_filei = json.JsonFile('{}.{}'.format(tags_file.file_name, i))
                    tags_filei.unlink(force=True)
                album_tags_sel = 0
            elif c in ('continue', 'c', 'yes', 'y'):
                break
            else:
                app.log.error('Invalid input')
        album_tags = album_tags_list[album_tags_sel]

    else:
        app.log.error('No appropriate tags found!')
        album_tags = AlbumTags()
        for track_no, track in enumerate(cue_file.tracks, start=1):
            track_tags = album_tags.tracks_tags[track_no]
            track_tags.setdefault('title', 'Track %0*d' % (len(str(len(cue_file.tracks))), track_no))
        cleanup_album_tags(album_tags)

    app.log.info('Writing %s...', tags_file)
    with tags_file.open('w', encoding='utf-8') as fp:
        album_tags.json_dump(fp)
        fp.write('\n')

    app.log.info('DONE!')

    return album_tags

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
