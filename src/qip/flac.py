# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'FlacFile',
)

import logging
import struct
import tempfile
log = logging.getLogger(__name__)

from . import mm
from .mm import SoundFile

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
        'totaldiscs': 'disks',  # HDtracks
        'tracktotal': 'tracks',
        'totaltracks': 'tracks',  # HDtracks
        'publisher': 'publisher',  # HDtracks
        'upc': 'barcode',  # HDtracks
    }

    def rip_cue_track(self, cue_track, bin_file=None, tags=None):
        from .ffmpeg import ffmpeg
        #with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = None
        with tempfile.NamedTemporaryFile(suffix='.wav') as tmp_fp:
            from qip.wav import WaveFile
            wav_file = WaveFile(file_name=tmp_fp.name)
            wav_file.rip_cue_track(cue_track=cue_track, bin_file=bin_file, tags=None, fp=tmp_fp)
            ffmpeg(
                '-i', wav_file,
                '-f', 'flac',
                self,
            )
        if tags is not None:
            self.write_tags(tags=tags)

FlacFile._build_extension_to_class_map()
