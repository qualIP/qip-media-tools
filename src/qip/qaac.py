# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'qaac',
        ]

import argparse
import enum
import collections
import types
import io
import os
import re
import shutil
import subprocess
from types import MappingProxyType
import logging
log = logging.getLogger(__name__)

from .exec import Executable
from .mm import MediaTagEnum
import qip.file

class Qaac(Executable):

    name = 'qaac'

    class Preset(enum.Enum):
        spoken_podcast = ('Spoken Podcast(64k)', MappingProxyType({'abr': 64, 'quality': 0, 'he': True}))
        high_quality96 = ('High Quality(96k)', MappingProxyType({'abr': 96, 'quality': 1}))  # Custom
        high_quality = ('High Quality(128k)', MappingProxyType({'abr': 128, 'quality': 1}))
        high_quality192 = ('High Quality(192k)', MappingProxyType({'abr': 192, 'quality': 1}))
        itunes_plus = ('iTunes Plus(256k)', MappingProxyType({'cvbr': 256, 'quality': 2}))

        @property
        def name(self):
            return self.value[0]

        @property
        def kwargs(self):
            return self.value[1]

        @property
        def cmdargs(self):
            return Qaac.kwargs_to_cmdargs(**self.kwargs)

        def __str__(self):
            return self.name

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def encode(self, file_name, output_file_name=None, preset=Preset.itunes_plus, run_func=None, **kwargs):
        args = []
        if preset:
            for k, v in preset.kwargs.items():
                kwargs.setdefault(k, v)
        if output_file_name is not None:
            assert 'o' not in kwargs
            kwargs['o'] = output_file_name
        args += self.kwargs_to_cmdargs(**kwargs)
        if isinstance(file_name, (str, os.PathLike)) or not isinstance(file_name, collections.abc.Sequence):
            file_names = [file_name]
        else:
            file_names = file_name
        file_names = [os.fspath(file_name) for file_name in file_names]
        return self(*(args + file_names), run_func=run_func)

    STR = str
    NUM = int
    PTH = qip.file.cache_url

    class TagArgInfo(collections.namedtuple('TagArgInfo', 'short_arg long_arg tag_enum type description')):
        __slots__ = ()

    tag_args_info = (
        # Tagging options:
        #  (same value is set to all files, so use with care for multiple files)
        TagArgInfo(None, '--title', MediaTagEnum.title, STR, 'Set the title'),
        TagArgInfo(None, '--artist', MediaTagEnum.artist, STR, 'Set the artist'),
        TagArgInfo(None, '--band', MediaTagEnum.albumartist, STR, 'Set the album artist'),
        TagArgInfo(None, '--album', MediaTagEnum.albumtitle, STR, 'Set the album title'),
        TagArgInfo(None, '--grouping', MediaTagEnum.grouping, STR, 'Set the grouping name'),
        TagArgInfo(None, '--composer', MediaTagEnum.composer, STR, 'Set the composer information'),
        TagArgInfo(None, '--comment', MediaTagEnum.comment, STR, 'Set a general comment'),
        TagArgInfo(None, '--genre', MediaTagEnum.genre, STR, 'Set the genre name'),
        TagArgInfo(None, '--date', MediaTagEnum.year, STR, 'Set the release date'),  # Yes, year only
        TagArgInfo(None, '--track', MediaTagEnum.track_slash_tracks, STR, 'Set the track number[/total]'),
        TagArgInfo(None, '--disk', MediaTagEnum.disk_slash_disks, STR, 'Set the disk number[/total]'),
        TagArgInfo(None, '--compilation', MediaTagEnum.disk_slash_disks, NUM, 'Set the compilation flag'),
        # TagArgInfo(None, '--lyrics', MediaTagEnum.lyrics, FILE, 'Set the lyrics'),
        TagArgInfo(None, '--artwork', MediaTagEnum.picture, PTH, 'Set the picture'),
        # --artwork-size <n>    Specify maximum width or height of artwork in pixels.
        #                       If specified artwork (with --artwork) is larger than
        #                       this, artwork is automatically resized.
        # --tag <fcc>:<value>
        #                       Set iTunes pre-defined tag with fourcc key
        #                       and value.
        #                       1) When key starts with U+00A9 (copyright sign),
        #                          you can use 3 chars starting from the second char
        #                          instead.
        #                       2) Some known tags having type other than UTF-8 string
        #                          are taken care of. Others are just stored as UTF-8
        #                          string.
        # --long-tag <key>:<value>
        #                       Set long tag (iTunes custom metadata) with
        #                       arbitrary key/value pair. Value is always stored as
        #                       UTF8 string.
    )

    @classmethod
    def get_tag_args(cls, tags):
        tagargs = []
        for tag_info in cls.tag_args_info:
            value = tags.get(tag_info.tag_enum, None)
            if value is not None:
                value = str(tag_info.type(value))
                tagargs += [tag_info.long_arg or tag_info.short_arg, value]
        return tuple(tagargs)

    def write_tags(self, *, tags, file_name, **kwargs):
        tagargs = tuple(str(e) for e in self.get_tag_args(tags))
        self(*(tagargs + (file_name,)), **kwargs)

qaac = Qaac()
