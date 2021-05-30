
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
            self.write_tags(tags=tags)

    @property
    def tag_writer(self):
        return snd.taged
        #return snd.mp4tags

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
