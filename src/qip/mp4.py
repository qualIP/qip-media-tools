# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'Mpeg4ContainerFile',
    'Mp4File',
    'M4aFile',
    'M4bFile',
    'M4rFile',
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
from .mm import BinaryMediaFile
from .mm import Chapter, Chapters
from .mm import MovieFile
from .mm import RingtoneFile
from .mm import SoundFile
from .mm import TrackTags
from .utils import byte_decode, Timestamp, Timestamp as _BaseTimestamp, replace_html_entities

class Mpeg4ContainerFile(BinaryMediaFile):

    def rip_cue_track(self, cue_track, bin_file=None, tags=None, yes=False):
        from qip.wav import WaveFile
        with WaveFile.NamedTemporaryFile() as wav_file:
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

    @classmethod
    def prep_picture(cls, src_picture, *,
            yes=False,  # unused
            ipod_compat=True,
            keep_picture_file_name=None,
            ):
        from .exec import do_exec_cmd

        if not src_picture:
            return None
        src_picture = cache_url(src_picture)

        return cls._lru_prep_picture(src_picture,
                                     ipod_compat,
                                     keep_picture_file_name)

    @classmethod
    @functools.lru_cache
    def _lru_prep_picture(cls,
                          src_picture : Path,
                          ipod_compat,
                          keep_picture_file_name):
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
               ipod_compat=True,
               itunes_compat=True,
               use_qaac=True,
               channels=None,
               picture=None,
               expected_duration=None,
               show_progress_bar=None, progress_bar_max=None, progress_bar_title=None):
        from .exec import do_exec_cmd, do_spawn_cmd, clean_cmd_output
        from .parser import lines_parser
        from .qaac import qaac
        from .ffmpeg import ffmpeg
        m4b = self
        chapters_added = False
        tags_added = False
        picture_added = False

        assert self.fp is None  # Writing using file name

        if show_progress_bar:
            if progress_bar_max is None:
                progress_bar_max = expected_duration

        with contextlib.ExitStack() as exit_stack:

            log.info('Writing %s...', m4b)
            use_qaac_cmd = False
            use_qaac_intermediate = False
            ffmpeg_cmd = []
            ffmpeg_input_cmd = []
            ffmpeg_output_cmd = []
            qaac_cmd = [qaac.which()]
            qaac_cmd += ['--threading']
            if yes:
                ffmpeg_cmd += ['-y']
            else:
                if self.exists():
                    raise OSError(errno.EEXIST, f'File exists: {self}')

            ffmpeg_cmd += ['-stats']
            qaac_cmd += ['--verbose']
            ffmpeg_output_cmd += ['-vn']
            ffmpeg_format = 'ipod'
            bCopied = False
            bitrate = force_input_bitrate
            if bitrate is None:
                # bitrate = ... {{{
                audio_type = [inputfile.audio_type for inputfile in inputfiles]
                audio_type = sorted(set(audio_type))
                if (
                        not force_encode and
                        len(audio_type) == 1 and audio_type[0] in (
                            mm.AudioType.aac,
                            mm.AudioType.lc_aac,
                            mm.AudioType.he_aac,
                            mm.AudioType.ac3,
                            )):
                    # https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio (Audio formats supported by MP4/M4A)
                    ffmpeg_output_cmd += ['-c:a', 'copy']
                    bCopied = True
                    ffmpeg_format = 'ipod'  # See codec_ipod_tags @ ffmpeg/libavformat/movenc.c
                elif (
                        not force_encode and
                        not ipod_compat and
                        len(audio_type) == 1 and audio_type[0] in (
                            mm.AudioType.mp2,
                            mm.AudioType.mp3,
                            )):
                    # https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio (Audio formats supported by MP4/M4A)
                    ffmpeg_output_cmd += ['-c:a', 'copy']
                    bCopied = True
                    ffmpeg_format = 'mp4'
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
                            if len(audio_type) == 1 and audio_type[0] in (
                                    mm.AudioType.mp2,
                                    mm.AudioType.mp3,
                                    mm.AudioType.dts,
                            ):
                                use_qaac_intermediate = True
                                ffmpeg_format = 'wav'
                            qaac_cmd += ['--no-smart-padding']  # Like iTunes
                            # qaac_cmd += ['--ignorelength']
                            if kbitrate >= 256:
                                qaac_cmd += qaac.Preset.itunes_plus.cmdargs
                            elif kbitrate >= 192:
                                qaac_cmd += qaac.Preset.high_quality192.cmdargs
                            elif kbitrate >= 128:
                                qaac_cmd += qaac.Preset.high_quality.cmdargs
                            elif kbitrate >= 96:
                                qaac_cmd += qaac.Preset.high_quality96.cmdargs
                            else:
                                qaac_cmd += qaac.Preset.spoken_podcast.cmdargs
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
                    del m4b.tags.encodedby
                except AttributeError:
                    pass
                try:
                    del m4b.tags.tool
                except AttributeError:
                    pass
            inputfiles_names = [inputfile.file_name for inputfile in inputfiles]
            if len(inputfiles_names) > 1:
                concat_file = ffmpeg.ConcatScriptFile.NamedTemporaryFile()
                exit_stack.enter(concat_file)
                concat_file.files = inputfiles
                log.info('Writing %s...', concat_file)
                concat_file.create(absolute=True)
                # write -> read
                concat_file.flush()
                concat_file.seek(0)
                concat_file.pprint()
                ffmpeg_input_cmd += ['-f', 'concat', '-safe', '0', '-i', concat_file]
            else:
                ffmpeg_input_cmd += ['-i', inputfiles_names[0]]

            ffmpeg_output_cmd += ['-f', ffmpeg_format]

            intermediate_wav_files = []
            try:

                if use_qaac_intermediate:
                    assert use_qaac_cmd
                    new_inputfiles_names = []
                    for inputfile_name in inputfiles_names:
                        if False:
                            # Slower
                            intermediate_wav_file = mm.SoundFile.new_by_file_name(file_name=inputfile_name.with_suffix('.tmp.alac.m4a'))
                            intermediate_wav_files.append(intermediate_wav_file)
                            new_inputfiles_names.append(intermediate_wav_file.file_name)
                            out = ffmpeg('-i', inputfile_name, '-acodec', 'alac', intermediate_wav_file.file_name)
                        else:
                            intermediate_wav_file = mm.SoundFile.new_by_file_name(file_name=inputfile_name.with_suffix('.tmp.wav'))
                            intermediate_wav_files.append(intermediate_wav_file)
                            new_inputfiles_names.append(intermediate_wav_file.file_name)
                            out = ffmpeg('-i', inputfile_name, intermediate_wav_file.file_name)
                        # TODO out
                    inputfiles_names = new_inputfiles_names

                if len(inputfiles_names) > 1:
                    qaac_cmd += ['--concat'] + inputfiles_names
                else:
                    qaac_cmd += [inputfiles_names[0]]

                ffmpeg_output_cmd += [m4b.file_name]
                qaac_cmd += ['-o', m4b.file_name]
                with contextlib.ExitStack() as exit_stack:
                    if use_qaac_cmd:
                        qaac_cmd += ['--text-codepage', '65001']  # utf-8
                        if not chapters_added and chapters:
                            chapters_file = Mp4chapsFile.NamedTemporaryFile()
                            exit_stack.enter_context(chapters_file)
                            chapters_file.chapters = chapters
                            chapters_file.create()
                            # write -> read
                            chapters_file.flush()
                            chapters_file.seek(0)
                            qaac_cmd += ['--chapter', chapters_file]
                            chapters_added = True
                        # TODO qaac_cmd += qaac.get_tag_args(m4b.tags)
                        if not picture_added and picture is not None:
                            qaac_cmd += ['--artwork', str(picture)]
                            picture_added = True
                    out_time = None
                    if use_qaac_cmd:
                        out = do_spawn_cmd(qaac_cmd, encoding='utf-8')
                        out = clean_cmd_output(out)
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
                        ffmpeg_chapters_cmd = []
                        if not chapters_added and chapters:
                            metadata_file = ffmpeg.MetadataFile.NamedTemporaryFile()
                            exit_stack.enter_context(metadata_file)
                            chapters.fill_end_times(duration=expected_duration)
                            metadata_file.chapters = chapters
                            metadata_file.create()
                            # write -> read
                            metadata_file.flush()
                            metadata_file.seek(0)
                            ffmpeg_chapters_cmd += [
                                '-i', metadata_file,
                                '-map_metadata', 1,  # second input
                            ]
                            chapters_added = True
                        out = ffmpeg(*(ffmpeg_cmd + ffmpeg_input_cmd + ffmpeg_chapters_cmd + ffmpeg_output_cmd),
                                     show_progress_bar=show_progress_bar,
                                     progress_bar_max=progress_bar_max,
                                     progress_bar_title=progress_bar_title or f'Encode {self} w/ ffmpeg',
                                     )
                        out_time = ffmpeg.Timestamp(byte_decode(out.spawn.progress_match.group('time')))
                print('')
                if expected_duration is not None:
                    log.info('Expected final duration: %s (%.3f seconds)', Mp4chapsFile.Timestamp(expected_duration), expected_duration)
                if out_time is None:
                    log.warning('final duration unknown!')
                else:
                    log.info('Final duration:          %s (%.3f seconds)', Mp4chapsFile.Timestamp(out_time), out_time)

            finally:
                for intermediate_wav_file in intermediate_wav_files:
                    intermediate_wav_file.unlink(force=True)

            if not chapters_added and chapters:
                chapters.fill_end_times(duration=out_time if out_time is not None else expected_duration)
                m4b.write_chapters(chapters,
                                   show_progress_bar=show_progress_bar,
                                   progress_bar_max=progress_bar_max,
                                   log=True)
                chapters_added = True

            if not tags_added and m4b.tags is not None:
                log.info('Adding tags...')
                tags = copy.copy(m4b.tags)
                tags.picture = None
                m4b.write_tags(tags=tags)
                tags_added = True

            if not picture_added and picture is not None:
                log.info('Adding picture...')
                tags = TrackTags()
                tags.picture = picture
                m4b.write_tags(tags=tags)
                picture_added = True

    def load_chapters(self):
        import mutagen
        mf = mutagen.File(self.file_name)
        chaps = Chapters.from_mutagen_mp4_chapters(mf.chapters)
        return chaps

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
            if self.cover_file:
                cmd += [
                        '--cover', oldcwd / self.cover_file,
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

    def load(self):
        from .parser import lines_parser
        self.chapters = Chapters()
        with self.open('r') as fp:
            parser = lines_parser(fp)
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
                    parser.raiseValueError('Invalid MP4 chaoters line: {line!r}', input=self)

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
