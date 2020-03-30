
__all__ = (
    'Mpeg2ContainerFile',
    'Mp2File',
)

from pathlib import Path
import logging
import os
log = logging.getLogger(__name__)

from .mm import MediaFile
from .mm import SoundFile
from .mm import RingtoneFile
from .mm import MovieFile
from .mm import AudiobookFile
from .mm import AlbumTags
import qip.mm as mm
from .exec import Executable

class Mpeg2ContainerFile(MediaFile):

    @property
    def tag_writer(self):
        return mm.taged

class Mp2File(Mpeg2ContainerFile, MovieFile):

    _common_extensions = (
        #'.mpeg2',
        '.m2v',
        '.mp2v',
    )

    def load_tags(self):
        # Raw container; No tags.
        tags = AlbumTags()
        return tags


Mpeg2ContainerFile._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
