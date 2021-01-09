
__all__ = (
    'FlacFile',
)

import struct
import logging
log = logging.getLogger(__name__)

from .mm import SoundFile
from . import mm

class FlacFile(SoundFile):

    _common_extensions = (
        '.flac',
    )

    @property
    def audio_type(self):
        return mm.AudioType.flac

    @audio_type.setter
    def audio_type(self, value):
        if value is not None \
                and mm.AudioType(value) is not mm.AudioType.flac:
            raise ValueError(value)

    @property
    def tag_writer(self):
        return mm.taged

    # https://xiph.org/flac/faq.html#general__tagging
    tag_map = {
        # https://xiph.org/vorbis/doc/v-comment.html
        'title': 'title',
        'version': 'subtitle',  # TODO CHECK!
        'album': 'album',
        'tracknumber': 'track',
        'artist': 'artist',
        'performer': 'performer',
        'copyright': 'copyright',
        'license': 'license',
        'organization': 'record_label',
        'description': 'description',
        'genre': 'genre',
        'date': 'date',  # TODO vs recording_date
        'location': 'recording_location',
        'contact': 'encodedby',  # TODO CHECK!
        'isrc': 'isrc',
        # More:
        'composer': 'composer',
        'albumartist': 'albumartist',
        'comment': 'comment',
        'discnumber': 'disk',
        'disctotal': 'disks',
        'tracktotal': 'tracks',
    }

FlacFile._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
