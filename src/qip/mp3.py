# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'Mp3File',
)

from pathlib import Path
import functools
import logging
import struct
log = logging.getLogger(__name__)

from . import mm
from .mm import AudioType
from .mm import SoundFile
from .propex import propex

class Mp3File(SoundFile):

    _common_extensions = (
        '.mp3',
    )

    ffmpeg_container_format = 'mp3'

    audio_type = propex(
        name='audio_type',
        default=AudioType.mp3,
        type=propex.test_type_in(AudioType, (AudioType.mp3,)))

    @property
    def tag_writer(self):
        #return mm.id3v2
        #return mm.operon
        return mm.taged

    @classmethod
    def prep_picture(cls, src_picture, *,
            yes=False,  # unused
            keep_picture_file_name=None,
            ):

        if not src_picture:
            return None
        src_picture = Path(src_picture)

        return cls._lru_prep_picture(src_picture,
                                     keep_picture_file_name)

    @classmethod
    @functools.lru_cache()
    def _lru_prep_picture(cls,
                          src_picture : Path,
                          keep_picture_file_name):
        picture = src_picture

        if src_picture.suffix not in (
                '.png',
                '.jpg',
                '.jpeg'):
            if keep_picture_file_name:
                picture = ImageFile.new_by_file_name(keep_picture_file_name)
            else:
                picture = PngFile.NamedTemporaryFile()
            if src_picture.resolve() != picture.file_name.resolve():
                log.info('Writing new picture %s...', picture)
                from .ffmpeg import ffmpeg
                ffmpeg_args = []
                if True:  # yes
                    ffmpeg_args += ['-y']
                ffmpeg_args += ['-i', src_picture]
                ffmpeg_args += ['-an', str(picture)]
                ffmpeg(*ffmpeg_args)
            src_picture = picture

        return picture

Mp3File._build_extension_to_class_map()
