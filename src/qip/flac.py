# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'FlacFile',
)

import contextlib
import copy
import logging
import re
_log = log = logging.getLogger(__name__)

from .mm import MediaFile, SoundFile, taged, AudioType, parse_time_duration
from .vorbis import _vorbis_tag_map, _vorbis_picture_extensions

# ffmpeg -i audio.flac -i image.png -map 0:a -map 1 -codec copy -metadata:s:v title="Album cover" -metadata:s:v comment="Cover (front)" -disposition:v attached_pic output.flac

class FlacFile(SoundFile):

    _common_extensions = (
        '.flac',
    )

    @property
    def audio_type(self):
        return AudioType.flac

    @audio_type.setter
    def audio_type(self, value):
        if value is not None \
                and AudioType(value) is not AudioType.flac:
            raise ValueError(value)

    @property
    def tag_writer(self):
        return taged

    tag_map = dict(_vorbis_tag_map)

    _picture_extensions = tuple(_vorbis_picture_extensions)

    def rip_cue_track(self, cue_track, bin_file=None, tags=None, yes=False):
        from .ffmpeg import ffmpeg
        from qip.wav import WaveFile
        with WaveFile.NamedTemporaryFile() as wav_file:
            wav_file.rip_cue_track(cue_track=cue_track, bin_file=bin_file, tags=None, yes=yes)
            # write -> read
            wav_file.flush()
            wav_file.seel(0)
            ffmpeg_args = [
                '-i', wav_file,
            ]
            if yes:
                ffmpeg_args += [
                    '-y',
                ]
            ffmpeg_args += [
                '-f', 'flac',
                self,
            ]
            ffmpeg(*ffmpeg_args)
        if tags is not None:
            self.write_tags(tags=tags)

FlacFile._build_extension_to_class_map()
