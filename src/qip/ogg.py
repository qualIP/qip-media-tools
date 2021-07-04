# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'OggFile',
    'OggMovieFile',
    'OggSoundFile',
    'OgvFile',
    'OgmFile',
    'OgaFile',
    'OpusFile',
)

# https://en.wikipedia.org/wiki/Ogg

import contextlib
import copy
import logging
import re
log = logging.getLogger(__name__)

from .mm import MediaFile, BinaryMediaFile, SoundFile, MovieFile, AudioType, taged, parse_time_duration
from .vorbis import _vorbis_tag_map, _vorbis_picture_extensions


class OggFile(BinaryMediaFile):

    _common_extensions = (
        '.ogg',
        # '.ogv',
        # '.ogm',
        # '.oga',
        '.ogx',
        '.spx',
        # '.opus',
    )

    @property
    def tag_writer(self):
        return taged

    tag_map = dict(_vorbis_tag_map)

    _picture_extensions = tuple(_vorbis_picture_extensions)

    def encode(self, *,
               inputfiles,
               chapters=None,
               force_input_bitrate=None,
               target_bitrate=None,
               yes=False,
               force_encode=False,
               ipod_compat=True,  # unused
               itunes_compat=True,  # unused
               use_qaac=True,  # unused
               channels=None,
               picture=None,
               expected_duration=None,
               show_progress_bar=None, progress_bar_max=None, progress_bar_title=None):
        from .exec import clean_cmd_output
        from .ffmpeg import ffmpeg
        from .parser import lines_parser
        output_file = self
        chapters_added = False
        tags_added = False
        picture_added = False
        if picture is None:
            picture = self.tags.picture
        if picture is not None:
            if not isinstance(picture, MediaFile):
                picture = MediaFile.new_by_file_name(picture)
            if not picture.exists():
                raise FileNotFoundError(errno.ENOENT,
                                        os.strerror(errno.ENOENT),
                                        f'Picture file not found: {picture}')
        with contextlib.ExitStack() as exit_stack:

            if show_progress_bar:
                if progress_bar_max is None:
                    progress_bar_max = expected_duration

            log.info('Writing %s...', output_file)

            ffmpeg_cmd = []

            ffmpeg_input_cmd = []
            ffmpeg_chapters_cmd = []
            ffmpeg_output_cmd = []
            if yes:
                ffmpeg_cmd += ['-y']
            else:
                if self.exists():
                    raise OSError(errno.EEXIST, f'File exists: {self}')

            ffmpeg_cmd += ['-stats']
            # ffmpeg_output_cmd += ['-vn']
            ffmpeg_format = 'oga'
            bCopied = False

            if len(inputfiles) > 1:
                concat_file = ffmpeg.ConcatScriptFile.NamedTemporaryFile()
                exit_stack.enter_context(concat_file)
                concat_file.files = inputfiles
                log.info('Writing %s...', concat_file)
                concat_file.create(absolute=True)
                # write -> read
                concat_file.flush()
                concat_file.seek(0)
                if log.isEnabledFor(logging.DEBUG):
                    concat_file.pprint()
                ffmpeg_input_cmd += [
                    '-f', 'concat', '-safe', '0', '-i', concat_file,
                ]
            else:
                ffmpeg_input_cmd += ffmpeg.input_args(inputfiles[0])
            input_id = 0
            metadata_input_id = -1
            chapters_input_id = -1
            ffmpeg_output_cmd += [
                '-map', f'{input_id}:a',
            ]
            output_id = 0

            if isinstance(self, VorbisFile):
                supported_audio_types = (
                    mm.AudioType.vorbis,
                )
            elif isinstance(self, OpusFile):
                supported_audio_types = (
                    mm.AudioType.opus,
                )
            else:
                supported_audio_types = (
                    mm.AudioType.vorbis,
                    mm.AudioType.opus,
                    mm.AudioType.flac,
                )
            audio_type = [inputfile.audio_type for inputfile in inputfiles]
            audio_type = sorted(set(audio_type))
            if not force_encode \
                    and len(audio_type) == 1 \
                    and audio_type[0] in supported_audio_types:
                ffmpeg_output_cmd += ['-codec:a', 'copy']
                bCopied = True
            else:
                ffmpeg_output_cmd += [
                    '-codec:a', {
                        mm.AudioType.vorbis: 'libvorbis', # or vorbis with `-strict -2`
                        mm.AudioType.opus: 'opus',
                        mm.AudioType.flac: 'flac',
                    }[supported_audio_types[0]],
                ]

            if not picture_added and picture is not None:
                ffmpeg_input_cmd += ffmpeg.input_args(picture)
                input_id += 1
                ffmpeg_output_cmd += [
                    '-map', f'{input_id}:v',
                ]
                output_id += 1
                ffmpeg_output_cmd += [
                    f'-codec:{output_id}', f'libtheora',
                    #f'-metadata:s:{output_id}', f'mimetype={picture.mime_type}',
                    f'-metadata:s:{output_id}', f'title=cover',
                    #f'-metadata:s:{output_id}', f'comment=cover',  # TODO Can't get rid of ffmpeg generating/reporting "Comment : Other"
                    #f'-metadata:s:{output_id}', f'filename=cover{picture.file_name.suffix}',
                    f'-disposition:{output_id}', f'attached_pic',  # TODO ffmpeg ignores this
                ]
                picture_added = True

            ffmpeg_output_cmd += [
                '-map_metadata', metadata_input_id,
                '-map_chapters', chapters_input_id,
            ]

            ffmpeg_output_cmd += [
                '-f', ffmpeg_format,
                output_file,
            ]

            out = ffmpeg(*(ffmpeg_cmd + ffmpeg_input_cmd + ffmpeg_chapters_cmd + ffmpeg_output_cmd),
                         show_progress_bar=show_progress_bar,
                         progress_bar_max=progress_bar_max,
                         progress_bar_title=progress_bar_title or f'Encode {self} w/ ffmpeg',
                         )
            out_time = ffmpeg.Timestamp(out.spawn.progress_match.group('time'))
            print('')
            if expected_duration is not None:
                expected_duration = ffmpeg.Timestamp(expected_duration)
                log.info('Expected final duration: %s (%.3f seconds)', expected_duration, expected_duration)
            if out_time is None:
                log.warning('final duration unknown!')
            else:
                out_time = ffmpeg.Timestamp(out_time)
                log.info('Final duration:          %s (%.3f seconds)', out_time, out_time)

            if not chapters_added and chapters:
                chapters.fill_end_times(duration=out_time if out_time is not None else expected_duration)
                output_file.write_chapters(chapters,
                                           show_progress_bar=show_progress_bar,
                                           progress_bar_max=progress_bar_max,
                                           log=True)
                chapters_added = True

            if not tags_added and output_file.tags is not None:
                log.info('Adding tags...')
                tags = copy.copy(output_file.tags)
                if picture_added:
                    try:
                        del tags.picture  # Already added
                    except AttributeError:
                        pass
                output_file.write_tags(tags=tags)
                tags_added = True

    def write_ffmpeg_metadata(self, *args, **kwargs):
        import mutagen
        from .perf import perfcontext
        with perfcontext('mf.load'):
            mf = mutagen.File(self.file_name)
        if isinstance(mf.tags, mutagen.oggtheora.OggTheoraCommentDict):
            # [theora @ 0x55d94aa7c1c0] Corrupt extradata
            raise NotImplementedError('Refusing to write metadata w/ ffmpeg on Ogg-Theora file to avoid corruption')
        return super().write_ffmpeg_metadata(*args, **kwargs)

class OggMovieFile(OggFile, MovieFile):
    pass

class OggSoundFile(OggFile, SoundFile):
    pass

class OgvFile(OggMovieFile):

    _common_extensions = (
        '.ogv',
    )

class OgmFile(OggMovieFile):
    """Discontinued format. Use OgvFile"""

    _common_extensions = (
        '.ogm',
    )

class OgaFile(OggSoundFile):

    _common_extensions = (
        '.oga',
    )

class VorbisFile(OgaFile):

    _common_extensions = (
        '.vorbis',
    )

class OpusFile(OggSoundFile):

    _common_extensions = (
        '.opus',
    )

    @property
    def audio_type(self):
        return AudioType.opus

    @audio_type.setter
    def audio_type(self, value):
        if value is not None \
                and AudioType(value) is not AudioType.opus:
            raise ValueError(value)

OggFile._build_extension_to_class_map()
