#!/usr/bin/env python3
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
from qip.snd import *
from qip.file import *
from qip.exec import *
import qip.cdda as cdda
from qip.cdda import *
from qip.utils import byte_decode

def main():

    app.init(
            version='1.0',
            description='BIN/CUE Ripper',
            contact='jst@qualipsoft.com',
            )

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_argument('--continue', '-c', dest='_continue', action='store_true', help='continue creating RIP')
    #pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
    #pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')
    pgroup.add_argument('--save-temps', dest='save_temps', default=False, action='store_true', help='do not delete intermediate files')
    pgroup.add_argument('--format',
                        #default="wav",
                        required=True,
                        help='output format', choices=["m4a", "wav"])
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

    # Tie in to bincuetags {{{
    pgroup = app.parser.add_argument_group('Database Control (bincuetags)')
    pgroup.add_argument('--cddb', dest='use_cddb', default=True, action='store_true', help='Use CDDB')
    pgroup.add_argument('--no-cddb', dest='use_cddb', default=argparse.SUPPRESS, action='store_false', help='Do not use CDDB')
    pgroup.add_argument('--musicbrainz', dest='use_musicbrainz', default=True, action='store_true', help='Use MusicBrainz')
    pgroup.add_argument('--no-musicbrainz', dest='use_musicbrainz', default=argparse.SUPPRESS, action='store_false', help='Do not use MusicBrainz')

    pgroup.add_argument('--mbdiscid', default=None, help='specify MusicBrainz discid')
    pgroup.add_argument('--mbreleaseid', default=None, help='specify MusicBrainz releaseid')
    pgroup.add_argument('--barcode', default=None, help='specify barcode')
    pgroup.add_argument('--country', dest='country_list', default=None, nargs='*', help='specify country list')
    # }}}

    app.parser.add_argument('cue_files', nargs='*', default=None, help='cue file names')

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
            raise Exception('No CUE file name provided')
        for cue_file in app.args.cue_files:
            bincuerip(cue_file)
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

def bincuerip(cue_file_name):

    cue_file = CDDACueSheetFile(cue_file_name)
    cue_file.read()
    assert len(cue_file.files) == 1
    assert cue_file.files[0].format is CDDACueSheetFile.FileFormatEnum.BINARY

    tags_file = JsonFile(os.path.splitext(cue_file.file_name)[0] + '.tags')
    if tags_file.exists():
        app.log.info('Reading %s...', tags_file)
        with tags_file.open('r') as fp:
            album_tags = AlbumTags.json_load(fp)
        print('{}'.format(
            album_tags.short_str()))
        for track_no, track_tags in album_tags.tracks_tags.items():
            print('  Track {:2d}: {}'.format(track_no, track_tags.short_str()))
    else:
        import qip.bin.bincuetags
        album_tags = qip.bin.bincuetags.bincuetags(cue_file_name)

    for track_no, track in enumerate(cue_file.tracks, start=1):
        bin_file = BinaryFile(os.path.join(os.path.dirname(cue_file.file_name), track.file.name))

        if app.args.format == 'wav':
            import qip.wav as wav
            track_out_file = wav.WaveFile('{base}-{track_no:02d}.wav'.format(
                base=os.path.splitext(bin_file.file_name)[0],
                track_no=track_no))
        elif app.args.format == 'm4a':
            import qip.m4a as m4a
            track_out_file = m4a.M4aFile('{base}-{track_no:02d}.m4a'.format(
                base=os.path.splitext(bin_file.file_name)[0],
                track_no=track_no))
        else:
            raise ValueError(app.args.format)

        app.log.info('Ripping %s...', track_out_file)
        track_out_file.rip_cue_track(track,
                                     bin_file=bin_file,
                                     tags=album_tags.tracks_tags[track_no])

    return True

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
