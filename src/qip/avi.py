
__all__ = (
    'AviFile',
)

from pathlib import Path
import logging
import os
log = logging.getLogger(__name__)

from .mm import MediaFile
from .mm import MovieFile
from .mm import AlbumTags
import qip.mm as mm
from .exec import Executable

class AviFile(MovieFile):

    _common_extensions = (
        '.avi',
    )

    @property
    def tag_writer(self):
        return mm.taged

    def load_tags(self):
        tags = AlbumTags()
        # TODO
        return tags


AviFile._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker