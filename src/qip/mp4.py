# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'Mpeg4ContainerFile',
    'Mp4File',
    'M4aFile',
    'M4bFile',
    'M4rFile',
    'AlacFile',
    # 'mp4chaps',  # Deprecated
    'Mp4chapsFile',
)

# https://en.wikipedia.org/wiki/MPEG-4_Part_14

from pathlib import Path
import contextlib
import copy
import errno
import functools
import logging
import os
import re
import shutil
import struct
import tempfile
log = logging.getLogger(__name__)

from . import mm
from .exec import Executable
from .file import cache_url, TextFile
from .img import ImageFile, PngFile
from .mm import AudiobookFile
from .mm import MediaFile
from .mm import BinaryMediaFile
from .mm import Chapter, Chapters
from .mm import MovieFile
from .mm import RingtoneFile
from .mm import SoundFile
from .mm import TrackTags
from .utils import Timestamp, Timestamp as _BaseTimestamp, replace_html_entities
from .propex import propex, dynamicmethod

class Mpeg4ContainerFile(BinaryMediaFile):

    ffmpeg_container_format = 'mp4'  # Also: ipod

    def rip_cue_track(self, cue_track, bin_file=None, tags=None, yes=False):
        from qip.wav import WavFile
        with WavFile.NamedTemporaryFile() as wav_file:
            wav_file.rip_cue_track(cue_track=cue_track, bin_file=bin_file, tags=None, yes=yes)
            # write -> read
            wav_file.flush()
            wav_file.seek(0)
            wav_file.bitrate = 1411200  # 44100Hz * 16 bits/sample * 2 channels
            self.encode(inputfiles=[wav_file], yes=yes)
        if tags is not None:
            self.write_tags(tags=tags)

    @property
    def tag_writer(self):
        return mm.taged

    @dynamicmethod
    def prep_picture(self, src_picture, *,
            yes=False,  # unused
            keep_picture_file_name=None,
            ):
        ipod_compat = self.ffmpeg_container_format == 'ipod'

        if not src_picture:
            return None
        src_picture = cache_url(src_picture)

        return self._lru_prep_picture(src_picture,
                                     ipod_compat,
                                     keep_picture_file_name)

    @classmethod
    @functools.lru_cache()
    def _lru_prep_picture(cls,
                          src_picture : Path,
                          ipod_compat,
                          keep_picture_file_name):
        from .exec import do_exec_cmd
        picture = src_picture

        if src_picture.suffix not in (
                #'.gif',
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
                ffmpeg_args += ['-an', picture]
                ffmpeg(*ffmpeg_args)
            src_picture = picture

        if ipod_compat and shutil.which('gm'):
            if keep_picture_file_name:
                picture = ImageFile(keep_picture_file_name)
            else:
                picture = PngFile.NamedTemporaryFile()
            log.info('Writing iPod-compatible picture %s...', picture)
            cmd = [shutil.which('gm'),
                    'convert', src_picture,
                    '-resize', 'x480>',
                    str(picture)]
            do_exec_cmd(cmd)

        return picture

    def encode(self, *,
               inputfiles,
               chapters=None,
               force_input_bitrate=None,
               target_bitrate=None,
               yes=False,
               force_encode=False,
               itunes_compat=True,
               use_qaac=True,
               channels=None,
               fflags=None,
               picture=None,
               expected_duration=None,
               show_progress_bar=None, progress_bar_max=None, progress_bar_title=None):
        from .exec import clean_cmd_output
        from .ffmpeg import ffmpeg
        from .parser import lines_parser
        if use_qaac:
            from .qaac import qaac
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
        ipod_compat = self.ffmpeg_container_format == 'ipod'
        with contextlib.ExitStack() as exit_stack:

            # if chapters and len(chapters) > 255:
            #     raise NotImplementedError(f'MPEG-4 supports up to 255 chapters ({len(chapters)} requested)')

            assert self.fp is None  # Writing using file name

            if show_progress_bar:
                if progress_bar_max is None:
                    progress_bar_max = expected_duration

            log.info('Writing %s...', output_file)
            use_qaac_cmd = False
            use_qaac_intermediate = False

            ffmpeg_cmd = []
            ffmpeg_format_args = []

            ffmpeg_input_cmd = []
            ffmpeg_chapters_cmd = []
            ffmpeg_output_cmd = []
            qaac_args = []
            qaac_args += ['--threading']
            qaac_args += ['--verbose']
            if yes:
                ffmpeg_cmd += ['-y']
            else:
                if self.exists():
                    raise OSError(errno.EEXIST, f'File exists: {self}')

            ffmpeg_cmd += ['-stats']
            if fflags is not None:
                ffmpeg_cmd += ffmpeg.fflags_arguments_to_ffmpeg_args(fflags)
            # ffmpeg_output_cmd += ['-vn']
            bCopied = False

            if ipod_compat:
                supported_audio_types = (
                    mm.AudioType.aac,
                    mm.AudioType.lc_aac,
                    mm.AudioType.he_aac,
                    mm.AudioType.ac3,
                )
            else:
                supported_audio_types = (
                    # https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio (Audio formats supported by MP4/M4A)
                    mm.AudioType.mp2,
                    mm.AudioType.mp3,
                    mm.AudioType.aac,
                    mm.AudioType.lc_aac,
                    mm.AudioType.he_aac,
                    mm.AudioType.ac3,
                )
                from qip.app import app
                if getattr(app.args, 'experimental', False):
                    supported_audio_types += (
                        # Others
                        mm.AudioType.flac,
                    )

            bitrate = force_input_bitrate
            if bitrate is None:
                # bitrate = ... {{{
                audio_type = [inputfile.audio_type for inputfile in inputfiles]
                audio_type = sorted(set(audio_type))
                if not force_encode \
                        and len(audio_type) == 1 \
                        and audio_type[0] in supported_audio_types:
                    # https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio (Audio formats supported by MP4/M4A)
                    ffmpeg_output_cmd += ['-codec:a', 'copy']
                    if audio_type[0] is mm.AudioType.flac:
                        # ffmpeg: flac in MP4 support is experimental
                        ffmpeg_format_args += ['-strict', -2]
                    bCopied = True
                else:
                    # TODO select preferred encoder based on bitrate: https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio
                    kbitrate = [target_bitrate]
                    if kbitrate[0] is None:
                        def get_kbitrate(inputfile):
                            try:
                                bitrate = inputfile.bitrate
                            except AttributeError:
                                inputfile.extract_info()
                                bitrate = inputfile.bitrate
                            return round(bitrate / 1000.0 / 16.0) * 16
                        kbitrate = [get_kbitrate(inputfile) for inputfile in inputfiles]
                        kbitrate = sorted(set(kbitrate))
                        kbitrate = [kbitrate[0]]  # TODO
                    if len(kbitrate) == 1:
                        kbitrate = kbitrate[0]
                        if use_qaac:
                            use_qaac_cmd = True
                            # https://github.com/nu774/qaac/wiki/About-input-format
                            # > qaac accepts raw PCM, WAV, ALAC, MP3 AAC(LC), and other LPCM formats supported by Apple AudioFile service. Also, qaac can read cue sheets.
                            # https://developer.apple.com/documentation/audiotoolbox/audio_file_stream_services
                            # > Audio File Stream Services supports the following audio data types:
                            # > - AIFF
                            # > - AIFC
                            # > - WAVE
                            # > - CAF
                            # > - NeXT
                            # > - ADTS
                            # > - MPEG Audio Layer 3
                            # > - AAC
                            if any(
                                    e not in (
                                        mm.AudioType.pcm_s16le,
                                        mm.AudioType.wav,
                                        mm.AudioType.alac,
                                        mm.AudioType.mp3,
                                        mm.AudioType.aac,
                                        # TODO mm.AudioType.he_aac,
                                        mm.AudioType.lc_aac,
                                        # TODO mm.AudioType.ac3,
                                    )
                                    for e in audio_type):
                                use_qaac_intermediate = True
                            qaac_args += ['--no-smart-padding']  # Like iTunes
                            # qaac_args += ['--ignorelength']
                            if kbitrate >= 256:
                                qaac_args += qaac.Preset.itunes_plus.cmdargs
                            elif kbitrate >= 192:
                                qaac_args += qaac.Preset.high_quality192.cmdargs
                            elif kbitrate >= 128:
                                qaac_args += qaac.Preset.high_quality.cmdargs
                            elif kbitrate >= 96:
                                qaac_args += qaac.Preset.high_quality96.cmdargs
                            else:
                                qaac_args += qaac.Preset.spoken_podcast.cmdargs
                        else:
                            if False and kbitrate >= 160:
                                # http://wiki.hydrogenaud.io/index.php?title=FAAC
                                log.info('NOTE: Using recommended high-quality LC-AAC libfaac settings; If it fails, try: --bitrate %dk', kbitrate)
                                ffmpeg_output_cmd += ['-c:a', 'libfaac', '-q:a', '330', '-cutoff', '15000']  # 100% ~= 128k, 330% ~= ?
                            elif kbitrate > 64:
                                log.info('NOTE: Using recommended high-quality LC-AAC libfdk_aac settings; If it fails, try: --bitrate %dk', kbitrate)
                                ffmpeg_output_cmd += ['-c:a', 'libfdk_aac', '-b:a', '%dk' % (kbitrate,)]
                            elif kbitrate >= 48:
                                log.info('NOTE: Using recommended high-quality HE-AAC libfdk_aac 64k settings; If it fails, try: --bitrate %dk', kbitrate)
                                ffmpeg_output_cmd += ['-c:a', 'libfdk_aac', '-profile:a', 'aac_he', '-b:a', '64k']
                                if itunes_compat:
                                    ffmpeg_output_cmd += ['-signaling:a', 'implicit']  # iTunes compatibility: implicit backwards compatible signaling
                            elif True:
                                log.info('NOTE: Using recommended high-quality HE-AAC libfdk_aac 32k settings; If it fails, try: --bitrate %dk', kbitrate)
                                ffmpeg_output_cmd += ['-c:a', 'libfdk_aac', '-profile:a', 'aac_he_v2', '-b:a', '32k']
                                if itunes_compat:
                                    ffmpeg_output_cmd += ['-signaling:a', 'implicit']  # iTunes compatibility: implicit backwards compatible signaling
                            else:
                                bitrate = '%dk' % (kbitrate,)
                    else:
                        raise Exception('Unable to determine proper bitrate from %rk' % (kbitrate,))
                # }}}
            if bitrate is not None:
                ffmpeg_output_cmd += ['-b:a', bitrate]
            if channels is not None:
                ffmpeg_output_cmd += ['-ac', channels]
            if not bCopied:
                try:
                    del output_file.tags.encodedby
                except AttributeError:
                    pass
                try:
                    del output_file.tags.tool
                except AttributeError:
                    pass
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

            if use_qaac_intermediate:
                assert use_qaac_cmd
                for i, inputfile in enumerate(inputfiles):
                    if False:
                        # Slower
                        intermediate_file = M4aFile.NamedTemporaryFile(prefix=inputfile.file_name.stem)
                        exit_stack.enter_context(intermediate_file)
                        ffmpeg('-i', inputfile,
                               '-map', '0:a', '-codec:a', 'alac',
                               '-y',  # Temp file already exists
                               '-f', intermediate_file.ffmpeg_container_format or 'mp4',
                               intermediate_file)
                        inputfiles[i] = intermediate_file
                    else:
                        from qip.wav import WavFile
                        intermediate_file = WavFile.NamedTemporaryFile(prefix=inputfile.file_name.stem)
                        exit_stack.enter_context(intermediate_file)
                        ffmpeg('-i', inputfile,
                               '-map', '0:a',
                               '-y',  # Temp file already exists
                               '-f', intermediate_file.ffmpeg_container_format or 'wav',
                               intermediate_file)
                        inputfiles[i] = intermediate_file

            if len(inputfiles) > 1:
                qaac_args += ['--concat'] + inputfiles
            else:
                qaac_args += [inputfiles[0]]
            qaac_args += ['-o', output_file.file_name]

            if use_qaac_cmd:
                qaac_args += ['--text-codepage', '65001']  # utf-8
                if not chapters_added and chapters:
                    chapters_file = Mp4chapsFile.NamedTemporaryFile()
                    exit_stack.enter_context(chapters_file)
                    chapters_file.chapters = chapters
                    chapters_file.create()
                    # write -> read
                    chapters_file.flush()
                    chapters_file.seek(0)
                    qaac_args += ['--chapter', chapters_file]
                    chapters_added = True
                # TODO qaac_args += qaac.get_tag_args(output_file.tags)
                if not picture_added and picture is not None:
                    qaac_args += ['--artwork', str(picture)]
                    picture_added = True
            out_time = None
            if use_qaac_cmd:
                out = qaac(*qaac_args)
                out = clean_cmd_output(out.out)
                parser = lines_parser(out.split('\n'))
                out_time_match = None
                while parser.advance():
                    parser.line = parser.line.strip()
                    if parser.re_search(r'^\[[0-9.]+%\] [0-9:.]+/(?P<out_time>[0-9:.]+) \([0-9.]+x\), ETA [0-9:.]+$'):
                        # [35.6%] 2:51:28.297/8:01:13.150 (68.2x), ETA 4:32.491
                        # [100.0%] 10:04.626/10:04.626 (79.9x), ETA 0:00.000
                        out_time_match = parser.match
                    else:
                        pass  # TODO
                if out_time_match is not None:
                    out_time = mm.parse_time_duration(out_time_match.group('out_time'))
            else:
                if (not chapters_added and chapters
                        # ffmpeg wants end times; Try again later when duration
                        # is (hopefully) known to avoid falling back to a final
                        # chapter with 1 second duration.
                        and (expected_duration is not None
                             or chapters[-1].end is not None)):
                    metadata_file = ffmpeg.MetadataFile.NamedTemporaryFile()
                    exit_stack.enter_context(metadata_file)
                    chapters.fill_end_times(duration=expected_duration)
                    metadata_file.chapters = chapters
                    metadata_file.create()
                    # write -> read
                    metadata_file.flush()
                    metadata_file.seek(0)
                    ffmpeg_chapters_cmd += ffmpeg.input_args(metadata_file)
                    input_id += 1
                    metadata_input_id = chapters_input_id = input_id
                    if len(chapters) > 255:
                        # ffmpeg's (n4.5-dev) 'chpl' atom implementation is limited to 255 chapters
                        ffmpeg_chapters_cmd += [
                            '-movflags', 'disable_chpl',
                        ]
                    chapters_added = True

                ffmpeg_output_cmd += [
                    '-map_metadata', metadata_input_id,
                    '-map_chapters', chapters_input_id,
                ]

                ffmpeg_output_cmd += [
                    '-f', output_file.ffmpeg_container_format or 'mp4',
                    output_file,
                ]

                out = ffmpeg(*(ffmpeg_cmd + ffmpeg_input_cmd + ffmpeg_chapters_cmd + ffmpeg_format_args + ffmpeg_output_cmd),
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
                                           ffmpeg_args=ffmpeg_format_args,
                                           show_progress_bar=show_progress_bar,
                                           progress_bar_max=progress_bar_max,
                                           log=True)
                chapters_added = True

            if not tags_added and output_file.tags is not None:
                tags = copy.copy(output_file.tags)
                if picture is not None:
                    tags.picture = picture
                if tags.picture is not None:
                    log.info('Adding tags and picture...')
                else:
                    log.info('Adding tags...')
                if picture_added:
                    try:
                        del tags.picture  # Already added
                    except AttributeError:
                        pass
                output_file.write_tags(tags=tags)
                tags_added = True
                if tags.picture is not None:
                    picture_added = True

            if not picture_added and picture is not None:
                log.info('Adding picture...')
                tags = TrackTags()
                tags.picture = picture
                output_file.write_tags(tags=tags)
                picture_added = True

    def load_chapters(self):
        chaps = None
        # ffmpeg documentation aludes that QuickTime chapters are more
        # compatible and writing Nero chapters may cause issues.
        if not chaps:
            # ffmpeg reads only QuickTime chapters
            chaps = super().load_chapters()
        if not chaps:
            # mutagen reads only Nero chapters ('chpl' atom)
            import mutagen
            mf = mutagen.File(self.file_name)
            chaps = Chapters.from_mutagen_mp4_chapters(mf.chapters)
        return chaps

    def write_chapters(self, chapters, ffmpeg_args=None, *args, **kwargs):
        if chapters and len(chapters) > 255:
            # ffmpeg's (n4.5-dev) 'chpl' atom implementation is limited to 255 chapters
            ffmpeg_args = list(ffmpeg_args or [])
            ffmpeg_args += [
                '-movflags', 'disable_chpl',
            ]
        return super().write_chapters(chapters=chapters, ffmpeg_args=ffmpeg_args, *args, **kwargs)

class Mp4File(Mpeg4ContainerFile, MovieFile):

    _common_extensions = (
        '.mp4',
        '.m4v',  # Raw MPEG-4 Visual bitstreams m4v but also sometimes used for video in MP4 container format.
        '.mpeg4',
    )

class M4aFile(Mpeg4ContainerFile, SoundFile):

    _common_extensions = (
        '.m4a',
        '.m4p',  # encrypted by FairPlay Digital Rights Management
    )

class AlacFile(M4aFile):

    _common_extensions = (
        '.alac',
    )

    audio_type = propex(
        name='audio_type',
        default=mm.AudioType.alac,
        type=propex.test_type_in(mm.AudioType, (mm.AudioType.alac,)))

class M4rFile(M4aFile, RingtoneFile):

    _common_extensions = (
        '.m4r',  # Apple iPhone ringtones
    )

class M4bFile(M4aFile, AudiobookFile):

    _common_extensions = (
        '.m4b',
    )

    def create_mkm4b(self, snd_files, out_dir=None, interactive=False, single=False):
        oldcwd = os.getcwd()
        try:
            if out_dir is not None:
                os.chdir(out_dir)
            cmd = [
                    'mkm4b',
                    ]
            if self.tags.picture:
                cmd += [
                        '--cover', oldcwd / self.tags.picture,
                        ]
            if interactive:
                cmd += ['--interactive']
            if single:
                cmd += ['--single']
            cmd += ['--logging_level', str(logging.getLogger().level)]
            cmd += [oldcwd / e for e in snd_files]
            if log.isEnabledFor(logging.DEBUG):
                log.debug('CMD: %s', subprocess.list2cmdline(cmd))
            subprocess.check_call(cmd)
        finally:
            os.chdir(oldcwd)

Mpeg4ContainerFile._build_extension_to_class_map()

class Mp4chapsTimestamp(_BaseTimestamp):
    '''hh:mm:ss.sss format'''

    def canonical_str(self):
        s = self.seconds
        if s < 0.0:
            sign = '-'
            s = -s
        else:
            sign = ''
        m = s // 60
        s = s - m * 60
        h = m // 60
        m = m - h * 60
        return '%s%02d:%02d:%s' % (sign, h, m, ('%.3f' % (s + 100.0))[1:])

class Mp4chapsFile(TextFile):
    """A chapters file in mp4chaps format"""

    chapters = None

    Timestamp = Mp4chapsTimestamp

    def __init__(self, *args, **kwargs):
        self.chapters = Chapters()
        super().__init__(*args, **kwargs)

    def load(self, file=None):
        if file is None:
            file = self.fp
        if file is None:
            with self.open('r') as file:
                return self.load(file=file)
        from .parser import lines_parser
        self.chapters = Chapters()
        parser = lines_parser(file)
        while parser.advance():
            if parser.line == '':
                pass
            elif parser.re_search(r'^(?P<start>\d+:\d+:\d+\.\d+)(?:\s+(?P<title>.*))?$'):
                # 00:00:00.000 Chapter 1
                self.chapters.append(Chapter(
                    start=parser.match.group('start'), end=None,
                    title=(parser.match.group('title') or '').strip(),
                ))
            else:
                log.debug('TODO: %s', parser.line)
                parser.raiseValueError('Invalid MP4 chapters line: {line!r}', input=self)

    def create(self, file=None):
        if file is None:
            file = self.fp
        if file is None:
            with self.open('w') as file:
                return self.create(file=file)
        for chap in self.chapters:
            line = f'{Mp4chapsTimestamp(chap.start)}'
            if chap.title:
                line += f' {replace_html_entities(chap.title)}'
            print(line, file=file)

    @classmethod
    def NamedTemporaryFile(cls, *, suffix=None, **kwargs):
        if suffix is None:
            suffix = '.chapters.txt'
        return super().NamedTemporaryFile(suffix=suffix, **kwargs)


class Mp4chaps(Executable):
    """mp4chaps is part of the deprecated mp4v2 utils.
    Only the syntax is still used here.
    """

    name = 'mp4chaps'

    Timestamp = Mp4chapsTimestamp

    @classmethod
    def parse_chapters_out(cls, chapters_out):
        from .parser import lines_parser
        chaps = Chapters()
        chapters_out = mp4chaps.clean_cmd_output(chapters_out)
        parser = lines_parser(chapters_out.split('\n'))
        while parser.advance():
            if parser.line == '':
                pass
            elif parser.re_search(r'^(QuickTime|Nero) Chapters of "(.*)"$'):
                # QuickTime Chapters of "../Carl Hiaasen - Bad Monkey.m4b"
                # Nero Chapters of "../Carl Hiaasen - Bad Monkey.m4b"
                pass
            elif parser.re_search(r'^ +Chapter #0*(?P<chapter_no>\d+) - (?P<start>\d+:\d+:\d+\.\d+) - "(?P<title>.*)"$') \
                or parser.re_search(r'^(?P<start>\d+:\d+:\d+\.\d+) (?P<title>.*)$'):
                #     Chapter #001 - 00:00:00.000 - "Bad Monkey"
                # 00:00:00.000 Chapter 1
                chaps.append(Chapter(
                    start=parser.match.group('start'), end=None,
                    title=parser.match.group('title'),
                ))
            elif parser.re_search(r'^File ".*" does not contain chapters'):
                # File "Mario Jean_ Gare au gros nounours!.m4a" does not contain chapters of type QuickTime and Nero
                pass
            else:
                log.debug('TODO: %s', parser.line)
                parser.raiseValueError('Invalid mp4chaps line: {line}')
                # TODO
        return chaps

mp4chaps = Mp4chaps()
