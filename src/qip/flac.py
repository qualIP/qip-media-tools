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

    ffmpeg_container_format = 'flac'

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
                '-f', self.ffmpeg_container_format or 'flac',
                self,
            ]
            ffmpeg(*ffmpeg_args)
        if tags is not None:
            self.write_tags(tags=tags)

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
        if chapters:
            raise NotImplementedError('FLAC does not support chapters')
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

            supported_audio_types = (
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
                    f'-codec:{output_id}', 'copy',
                    #f'-metadata:s:{output_id}', f'mimetype={picture.mime_type}',
                    f'-metadata:s:{output_id}', f'title=cover',
                    #f'-metadata:s:{output_id}', f'comment=cover',  # TODO Can't get rid of ffmpeg generating/reporting "Comment : Other"
                    #f'-metadata:s:{output_id}', f'filename=cover{picture.file_name.suffix}',
                    f'-disposition:{output_id}', f'attached_pic',
                ]
                picture_added = True

            ffmpeg_output_cmd += [
                '-map_metadata', metadata_input_id,
                '-map_chapters', chapters_input_id,
            ]

            ffmpeg_output_cmd += [
                '-f', output_file.ffmpeg_container_format or 'flac',
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
                tags = copy.copy(output_file.tags)
                log.info('Adding tags...')
                if picture_added:
                    try:
                        del tags.picture  # Already added
                    except AttributeError:
                        pass
                output_file.write_tags(tags=tags)
                tags_added = True

    supports_chapters = False

    def write_chapters(self, chapters,
                       show_progress_bar=None, progress_bar_max=None, progress_bar_title=None,
                       log=False):
        raise NotImplementedError('FLAC does not support chapters')

FlacFile._build_extension_to_class_map()
