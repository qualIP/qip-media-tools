
__all__ = (
    'Mp3File',
)

import struct
import logging
log = logging.getLogger(__name__)

from . import snd

class Mp3File(snd.SoundFile):

    _common_extensions = (
        '.mp3',
    )

    @property
    def audio_type(self):
        return snd.AudioType.mp3

    @audio_type.setter
    def audio_type(self, value):
        if value is not None \
                and snd.AudioType(value) is not snd.AudioType.mp3:
            raise ValueError(value)

    @property
    def tag_writer(self):
        #return snd.id3v2
        #return snd.operon
        return snd.taged

Mp3File._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
