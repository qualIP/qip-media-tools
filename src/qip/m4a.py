
__all__ = (
    'M4aFile',
)

import os
import struct
import tempfile
import logging
log = logging.getLogger(__name__)

import qip.snd as snd
import qip.wav as wav
import qip.cdda as cdda
from qip.qaac import qaac

class M4aFile(snd.SoundFile):

    @property
    def audio_type(self):
        return AudioType.m4a

    @audio_type.setter
    def audio_type(self, value):
        if value is not None \
                and AudioType(value) is not AudioType.m4a:
            raise ValueError(value)

    def rip_cue_track(self, cue_track, bin_file=None, tags=None):
        #with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = None
        with tempfile.NamedTemporaryFile(suffix='.wav') as tmp_fp:
            wav_file = wav.WaveFile(file_name=tmp_fp.name)
            wav_file.rip_cue_track(cue_track=cue_track, bin_file=bin_file, tags=None, fp=tmp_fp)
            qaac.encode(file_name=wav_file.file_name,
                        output_file_name=self.file_name,
                        threading=True,
                        )
        if tags is not None:
            self.write_tags(tags)

    def write_tags(self, tags):
        return snd.mp4tags.write_tags(tags, self.file_name)

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
