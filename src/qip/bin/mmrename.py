#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

from pathlib import Path
import argparse
import collections
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

from qip.propex import propex
from qip.mm import MediaFile
from qip.app import app
from qip.ffmpeg import ffmpeg
import qip.utils

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='Multimedia File Renamer',
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

    pgroup = app.parser.add_argument_group('Actions')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--rename', dest='action', default=None, action='store_const', const='rename', help='rename media files')

    pgroup = app.parser.add_argument_group('Rename Pattern')
    xgroup.add_argument('--pattern', default=None, type=str, help='file renaming pattern')

    app.parser.add_argument('inputfiles', nargs='*', default=(), type=Path, help='input files')

    app.parse_args()

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'rename'
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    if app.args.action == 'rename':

        if not app.args.pattern:
            raise Exception('Missing file renaming pattern (--pattern)')
        if '/' in app.args.pattern:
            raise Exception(f'Invalid file renaming pattern {app.args.pattern!r}')

        if not app.args.inputfiles:
            raise Exception('No input files provided')

        for inputfile in app.args.inputfiles:
            rename(inputfile, app.args.pattern)

    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

supported_media_exts = set(MediaFile.get_common_extensions())

def AnyTimestamp(value):
    try:
        return qip.utils.Timestamp(value)
    except ValueError:
        return qip.utils.Timestamp(ffmpeg.Timestamp(value))

def estimate_stream_duration(inputfile=None, ffprobe_json=None):
    ffprobe_json = ffprobe_json or inputfile.ffprobe_dict
    try:
        ffprobe_format_json = ffprobe_json['format']
    except KeyError:
        pass
    else:

        try:
            estimated_duration = ffprobe_format_json['duration']
        except KeyError:
            pass
        else:
            estimated_duration = ffmpeg.Timestamp(estimated_duration)
            if estimated_duration >= 0.0:
                return estimated_duration

    try:
        ffprobe_stream_json, = ffprobe_json['streams']
    except ValueError:
        pass
    else:

        try:
            estimated_duration = ffprobe_stream_json['duration']
        except KeyError:
            pass
        else:
            estimated_duration = AnyTimestamp(estimated_duration)
            if estimated_duration >= 0.0:
                return estimated_duration

        try:
            estimated_duration = ffprobe_stream_json['tags']['NUMBER_OF_FRAMES']
        except KeyError:
            pass
        else:
            estimated_duration = int(estimated_duration)
            if estimated_duration > 0:
                return estimated_duration

        try:
            estimated_duration = ffprobe_stream_json['tags']['NUMBER_OF_FRAMES-eng']
        except KeyError:
            pass
        else:
            estimated_duration = int(estimated_duration)
            if estimated_duration > 0:
                return estimated_duration

    if inputfile is not None:

        try:
            estimated_duration = inputfile.duration
        except AttributeError:
            pass
        else:
            if estimated_duration is not None:
                estimated_duration = AnyTimestamp(estimated_duration)
                if estimated_duration >= 0.0:
                    return estimated_duration

    return None

class FileRenameSubstitutionsMap(collections.UserDict):

    def __init__(self, /, inputfile):
        self._inputfile = inputfile
        super().__init__()

    @property
    def drive(self):
        return self._inputfile.file_name.drive

    @property
    def root(self):
        return self._inputfile.file_name.root

    @property
    def anchor(self):
        return self._inputfile.file_name.anchor

    @property
    def parent(self):
        return self._inputfile.file_name.parent

    @property
    def name(self):
        return self._inputfile.file_name.name

    @property
    def suffix(self):
        return self._inputfile.file_name.suffix

    @property
    def stem(self):
        return self._inputfile.file_name.stem

    duration = propex(
        name='duration')
    @duration.initter
    def duration(self):
        duration = estimate_stream_duration(self._inputfile)
        if isinstance(duration, qip.utils.Timestamp):
            return qip.utils.Timestamp(duration)
        raise AttributeError

    def __missing__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)


def rename(inputfile, pattern):

    if isinstance(inputfile, str):
        inputfile = Path(inputfile)
    if isinstance(inputfile, Path) and inputfile.is_dir():
        inputdir = inputfile
        app.log.verbose('Recursing into %s...', inputdir)
        for inputfile_path in sorted(inputdir.glob('**/*')):
            inputext = inputfile_path.suffix
            if (inputext in supported_media_exts
                    or inputfile_path.is_dir()):
                rename(inputfile_path, pattern)
        return True

    if not isinstance(inputfile, MediaFile):
        inputfile = MediaFile.new_by_file_name(inputfile)

    if not inputfile.file_name.is_file():
        raise OSError(errno.ENOENT, f'No such file: {inputfile}')

    subs = FileRenameSubstitutionsMap(inputfile)
    new_file_name = pattern.format_map(subs)
    if '/' not in new_file_name:
        new_file_name = inputfile.file_name.parent / new_file_name
    app.log.warning('Renaming %s to %s%s', inputfile, new_file_name, ' (dry-run)' if app.args.dry_run else '')
    if not app.args.dry_run:
        shutil.move(inputfile.file_name, new_file_name)

    return True

if __name__ == "__main__":
    main()
