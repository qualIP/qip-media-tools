#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

import argparse
import logging
import os
import pexpect
import re
import shutil
import subprocess
import musicbrainzngs
import urllib
import sys
import struct

from qip.app import app
from qip.cdda import *
from qip.exec import *
from qip.file import *
from qip.mm import *
from qip.utils import byte_decode
from qip import json
import qip.cdda as cdda

import qip.wav
import qip.mp4
import qip.flac

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='BIN/CUE Ripper',
            contact='jst@qualipsoft.com',
            )

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_argument('--continue', dest='_continue', action='store_true', help='continue creating RIP')
    #pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
    #pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')  # TODO
    pgroup.add_bool_argument('--save-temps', default=False, help='do not delete intermediate files')
    pgroup.add_argument('--format',
                        #default="wav",
                        #required=True,  # TODO Fix required with value from config file
                        help='output format', choices=['wav', 'm4a', 'flac'])
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

    # Tie in to bincuetags {{{
    pgroup = app.parser.add_argument_group('Database Control (bincuetags)')
    pgroup.add_bool_argument('--tags', dest='use_bincuetags', default=True, help='retrieve tags using bincuetags')
    pgroup.add_bool_argument('--cddb', dest='use_cddb', default=False, help='query CDDB (closed!)')
    pgroup.add_bool_argument('--musicbrainz', dest='use_musicbrainz', default=True, help='query MusicBrainz')

    pgroup.add_argument('--mb-discid', dest='musicbrainz_discid', default=None, help='specify MusicBrainz discid')
    pgroup.add_argument('--mb-releaseid', dest='musicbrainz_releaseid', default=None, help='specify MusicBrainz releaseid')
    pgroup.add_argument('--cddb-discid', dest='cddb_discid', default=None, help='specify CDDB discid')
    pgroup.add_argument('--barcode', default=None, help='specify barcode')
    pgroup.add_argument('--country', dest='country_list', default=None, nargs='*', help='specify country list')
    # }}}

    app.parser.add_argument('cue_files', nargs='*', default=None, type=CDDACueSheetFile.argparse_type(), help='cue file names')

    app.parse_args()

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'bincuerip'
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)

    for prog in ():
        if prog and not shutil.which(prog):
            raise Exception('%s: command not found' % (prog,))

    if app.args.action == 'bincuerip':
        if not app.args.cue_files:
            raise Exception('No CUE file names provided')
        if app.args.use_bincuetags:
            for cue_file in app.args.cue_files:
                prep_bincuetags(cue_file)
        for cue_file in app.args.cue_files:
            if not app.args.format:
                app.parser.error('the following argument is required: --format')
            bincuerip(cue_file, format=app.args.format)
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

def prep_bincuetags(cue_file):
    if not isinstance(cue_file, CDDACueSheetFile):
        cue_file = CDDACueSheetFile(cue_file)

    tags_file = json.JsonFile(cue_file.file_name.with_suffix('.tags'))
    if not tags_file.exists():
        import qip.bin.bincuetags
        qip.bin.bincuetags.bincuetags(cue_file)

def bincuerip(cue_file, *, format):
    if not isinstance(cue_file, CDDACueSheetFile):
        cue_file = CDDACueSheetFile(cue_file)

    app.log.debug('%r...', cue_file)
    if not cue_file.files:
        cue_file.read()
    assert len(cue_file.files) == 1, f'{cue_file}: Expected 1 source file, got {cue_file.files!r}'
    assert cue_file.files[0].format is CDDACueSheetFile.FileFormatEnum.BINARY

    tags_file = json.JsonFile(cue_file.file_name.with_suffix('.tags'))
    if tags_file.exists():
        app.log.info('Reading %s...', tags_file)
        with tags_file.open('r', encoding='utf-8') as fp:
            album_tags = AlbumTags.json_load(fp)
        try:
            type_ = album_tags.deduce_type()
        except MissingMediaTagError:
            type_ = 'audio'
        print('{}'.format(
            album_tags.cite(type_=type_)))
        for track_no, track_tags in album_tags.tracks_tags.items():
            print('  Track {:2d}: {}'.format(track_no, track_tags.cite(type_=type_)))
    #elif app.args.use_bincuetags:
    #    import qip.bin.bincuetags
    #    album_tags = qip.bin.bincuetags.bincuetags(cue_file)
    else:
        album_tags = AlbumTags()

    for track_no, track in enumerate(cue_file.tracks, start=1):
        bin_file = BinaryFile(cue_file.file_name.with_name(track.file.name))

        track_out_file = SoundFile.new_by_file_name(
            '{base}-{track_no:02d}.{format}'.format(
                base=os.path.splitext(os.fspath(bin_file.file_name))[0],
                track_no=track_no,
                format=format))

        track_tags = album_tags.tracks_tags[track_no]
        try:
            type_ = track_tags.deduce_type()
        except MissingMediaTagError:
            type_ = 'audio'

        summary = track_tags.cite(type_=type_)
        if summary:
            summary += ''
        summary += f'[{track.length}]'
        app.log.info('Ripping %s (%s)...', track_out_file, summary)
        track_out_file.rip_cue_track(track,
                                     bin_file=bin_file,
                                     tags=track_tags)

    return True

if __name__ == "__main__":
    main()
