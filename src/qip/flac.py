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

    def encode(self, *,
               inputfiles,
               chapters=None,
               force_input_bitrate=None,
               target_bitrate=None,
               yes=False,
               force_encode=False,
               ipod_compat=True,  # unused
               itunes_compat=True,
               use_qaac=True,  # unused
               channels=None,
               picture=None,
               expected_duration=None,
               show_progress_bar=None, progress_bar_max=None, progress_bar_title=None):
        from .exec import do_exec_cmd, do_spawn_cmd, clean_cmd_output
        from .parser import lines_parser
        from .ffmpeg import ffmpeg
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
            ffmpeg_output_cmd = []
            if yes:
                ffmpeg_cmd += ['-y']
            ffmpeg_cmd += ['-stats']
            # ffmpeg_output_cmd += ['-vn']
            ffmpeg_format = 'flac'
            bCopied = False

            ffmpeg_output_cmd += [
                '-map_metadata', -1,
                '-map_chapters', -1,
            ]

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
                    log.debug('Files:\n' +
                              re.sub(r'^', '    ', concat_file.read(), flags=re.MULTILINE))
                    concat_file.seek(0)
                ffmpeg_input_cmd += [
                    '-f', 'concat', '-safe', '0', '-i', concat_file,
                ]
            else:
                ffmpeg_input_cmd += ffmpeg.input_args(inputfiles[0])
            input_id = 0
            ffmpeg_output_cmd += [
                '-map', f'{input_id}:a',
            ]
            output_id = 0

            if not picture_added and picture is not None:
                ffmpeg_input_cmd += ffmpeg.input_args(picture)
                input_id += 1
                ffmpeg_output_cmd += [
                    '-map', f'{input_id}:v',
                ]
                output_id += 1
                ffmpeg_output_cmd += [
                    #f'-metadata:s:{output_id}', f'mimetype={picture.mime_type}',
                    f'-metadata:s:{output_id}', f'title=cover',
                    #f'-metadata:s:{output_id}', f'comment=cover',  # TODO Can't get rid of ffmpeg generating/reporting "Comment : Other"
                    #f'-metadata:s:{output_id}', f'filename=cover{picture.file_name.suffix}',
                    f'-disposition:{output_id}', f'attached_pic',
                ]
                picture_added = True

            ffmpeg_output_cmd += [
                '-codec', 'copy',
            ]

            ffmpeg_output_cmd += [
                '-f', ffmpeg_format,
                output_file,
            ]

            out = ffmpeg(*(ffmpeg_cmd + ffmpeg_input_cmd + ffmpeg_output_cmd),
                         show_progress_bar=show_progress_bar,
                         progress_bar_max=progress_bar_max,
                         progress_bar_title=progress_bar_title or f'Encode {self} w/ ffmpeg',
                         )
            out = out.out
            out_time = None
            # {{{
            out = clean_cmd_output(out)
            parser = lines_parser(out.split('\n'))
            while parser.advance():
                parser.line = parser.line.strip()
                if parser.re_search(r'^size= *(?P<out_size>\S+) time= *(?P<out_time>\S+) bitrate= *(?P<out_bitrate>\S+)(?: speed= *(?P<out_speed>\S+))?$'):
                    # size=  223575kB time=07:51:52.35 bitrate=  64.7kbits/s
                    # size= 3571189kB time=30:47:24.86 bitrate= 263.9kbits/s speed= 634x
                    out_time = parse_time_duration(parser.match.group('out_time'))
                elif parser.re_search(r' time= *(?P<out_time>\S+) bitrate='):
                    log.warning('TODO: %s', parser.line)
                    pass
                else:
                    pass  # TODO
            # }}}
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
                output_file.write_tags(tags=tags, run_func=do_exec_cmd)
                tags_added = True

    supports_chapters = False

    def write_chapters(self, chapters,
                       show_progress_bar=None, progress_bar_max=None, progress_bar_title=None,
                       log=False):
        raise NotImplementedError('FLAC does not support chapters')

FlacFile._build_extension_to_class_map()
