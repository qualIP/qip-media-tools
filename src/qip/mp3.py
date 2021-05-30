
__all__ = (
    'Mp3File',
)

import struct
import logging
log = logging.getLogger(__name__)

from .mm import SoundFile
from . import mm

class Mp3File(SoundFile):

    _common_extensions = (
        '.mp3',
    )

    @property
    def audio_type(self):
        return mm.AudioType.mp3

    @audio_type.setter
    def audio_type(self, value):
        if value is not None \
                and mm.AudioType(value) is not mm.AudioType.mp3:
            raise ValueError(value)

    @property
    def tag_writer(self):
        #return mm.id3v2
        #return mm.operon
        return mm.taged

Mp3File._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
