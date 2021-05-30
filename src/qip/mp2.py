# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'Mpeg2ContainerFile',
    'Mpeg2MovieFile',
    'Mp2File',
)

from pathlib import Path
import logging
import os
log = logging.getLogger(__name__)

from .mm import BinaryMediaFile
from .mm import SoundFile
from .mm import RingtoneFile
from .mm import MovieFile
from .mm import AlbumTags
import qip.mm as mm
from .exec import Executable

class Mpeg2ContainerFile(BinaryMediaFile):

    _common_extensions = (
    )

    @property
    def tag_writer(self):
        return mm.taged

class Mpeg2MovieFile(Mpeg2ContainerFile, MovieFile):

    _common_extensions = (
        '.mpeg2',      # MPEG-2 Movie. Note: mediainfo prefers .mpeg, .mpg, .m2p
        '.m2p',        # MPEG-2 Program Stream
        '.m2ts',       # MPEG-2 Transport Stream
        '.mpegts',     # MPEG-2 Transport Stream
        '.mpegtsraw',  # raw MPEG-2 Transport Stream
        '.mpeg',       # MPEG Movie (MPEG-1 or MPEG-2)
        '.mpg',        # MPEG Movie (MPEG-1 or MPEG-2)
        '.m2v',        # MPEG-2 Movie (without audio)
        '.mp2v',       # MPEG-2 Movie (without audio)
    )

    def load_tags(self):
        # Raw container; No tags.
        tags = AlbumTags()
        return tags

class Mp2File(Mpeg2ContainerFile, SoundFile):

    _common_extensions = (
        '.mp2',        # MPEG-2 Audio
    )

    def load_tags(self):
        # Raw container; No tags.
        tags = AlbumTags()
        return tags

    @property
    def audio_type(self):
        return mm.AudioType.mp2


Mpeg2ContainerFile._build_extension_to_class_map()
