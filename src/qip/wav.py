# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'WaveFile',
)

import struct
import logging
log = logging.getLogger(__name__)

from .mm import SoundFile
import qip.mm as mm
import qip.cdda as cdda

WAV_RIFF_HLEN = 12
WAV_FORMAT_HLEN = 24
WAV_DATA_HLEN = 8
WAV_HEADER_LEN = WAV_RIFF_HLEN + WAV_FORMAT_HLEN + WAV_DATA_HLEN

class WaveFile(SoundFile):

    _common_extensions = (
        '.wav',
    )

    @property
    def audio_type(self):
        return mm.AudioType.wav

    @audio_type.setter
    def audio_type(self, value):
        if value is not None \
                and mm.AudioType(value) is not mm.AudioType.wav:
            raise ValueError(value)

    def rip_cue_track(self, cue_track, bin_file=None, tags=None, fp=None):
        if bin_file is None:
            bin_file = BinaryFile(cue_track.file.name)

        if fp is None:
            with self.open('w') as fp:
                self.rip_cue_track(cue_track=cue_track, bin_file=bin_file, tags=None, fp=fp)
        else:
            assert tags is None
            fp.write(
                    struct.pack('<4sL4s4sLHHLLHH4sL',
                        # RIFF header
                        b'RIFF',
                        # length of file, starting from WAVE
                        cue_track.length.bytes + WAV_DATA_HLEN + WAV_FORMAT_HLEN + 4,
                        b'WAVE',
                        # FORMAT header
                        b'fmt ',
                        0x10,  # length of FORMAT header
                        0x01,  # constant
                        cdda.CDDA_CHANNELS,  # channels
                        cdda.CDDA_SAMPLE_RATE,  # sample rate
                        cdda.CDDA_BYTES_PER_SECOND,  # bytes per second
                        cdda.CDDA_BYTES_PER_SAMPLE,  # bytes per sample
                        cdda.CDDA_SAMPLE_BITS,  # bits per channel
                        # DATA header
                        b'data',
                        cue_track.length.bytes,
                        ))
            with bin_file.open('r') as binfp:
                binfp.seek(cue_track.begin.bytes)
                for _ in range(cue_track.length.frames):
                    fp.write(binfp.read(cdda.CDDA_BYTES_PER_SECTOR))
        if tags is not None:
            self.write_tags(tags=tags)

    @property
    def tag_writer(self):
        return mm.id3v2

WaveFile._build_extension_to_class_map()
