
__all__ = (
    'M4aFile',
)

import os
import re
import shutil
import struct
import tempfile
import logging
log = logging.getLogger(__name__)

import qip.snd as snd
import qip.wav as wav
import qip.cdda as cdda
from .img import ImageFile
from .utils import byte_decode

class M4aFile(snd.SoundFile):

    def rip_cue_track(self, cue_track, bin_file=None, tags=None):
        from qip.qaac import qaac
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

    def prep_picture(self, src_picture, *,
            yes=False,
            ipod_compat=True,
            keep_picture_file_name=None,
            ):
        from qip.app import app
        from qip.file import TempFile
        from qip.exec import do_exec_cmd

        if not src_picture:
            return None
        picture = src_picture
        if os.path.splitext(str(src_picture))[1] not in (
                #'.gif',
                '.png',
                '.jpg',
                '.jpeg'):
            if keep_picture_file_name:
                picture = ImageFile(keep_picture_file_name)
            else:
                picture = TempFile.mkstemp(suffix='.png')
            if str(src_picture) != str(picture):
                app.log.info('Writing new picture %s...', picture)
            cmd = [shutil.which('ffmpeg')]
            if True or yes:
                cmd += ['-y']
            cmd += ['-i', str(src_picture)]
            cmd += ['-an', str(picture)]
            do_exec_cmd(cmd, stderr=subprocess.STDOUT)
            src_picture = picture
        if ipod_compat and shutil.which('gm'):
            if keep_picture_file_name:
                picture = ImageFile(keep_picture_file_name)
            else:
                picture = TempFile.mkstemp(suffix='.png')
            app.log.info('Writing iPod-compatible picture %s...', picture)
            cmd = [shutil.which('gm'),
                    'convert', str(src_picture),
                    '-resize', 'x480>',
                    str(picture)]
            do_exec_cmd(cmd)
        return picture

    def encode(self, *,
               inputfiles,
               chapters_file=None,
               force_input_bitrate=None,
               target_bitrate=None,
               yes=False,
               force_encode=False,
               ipod_compat=True,
               itunes_compat=True,
               use_qaac=True,
               channels=None,
               picture=None,
               expected_duration=None):
        from qip.app import app
        from qip.exec import do_exec_cmd, do_spawn_cmd, clean_cmd_output
        from qip.parser import lines_parser
        from qip.qaac import qaac
        from qip.ffmpeg import ffmpeg
        from qip.file import TempFile, safe_write_file_eval, safe_read_file
        import qip.snd
        m4b = self

        app.log.info('Writing %s...', m4b)
        use_qaac_cmd = False
        use_qaac_intermediate = False
        ffmpeg_cmd = []
        ffmpeg_input_cmd = []
        ffmpeg_output_cmd = []
        qaac_cmd = [qaac.which()]
        qaac_cmd += ['--threading']
        if yes:
            ffmpeg_cmd += ['-y']
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
                        snd.AudioType.aac,
                        snd.AudioType.lc_aac,
                        snd.AudioType.he_aac,
                        snd.AudioType.ac3,
                        )):
                # https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio (Audio formats supported by MP4/M4A)
                ffmpeg_output_cmd += ['-c:a', 'copy']
                bCopied = True
                ffmpeg_format = 'ipod'  # See codec_ipod_tags @ ffmpeg/libavformat/movenc.c
            elif (
                    not force_encode and
                    not ipod_compat and
                    len(audio_type) == 1 and audio_type[0] in (
                        snd.AudioType.mp2,
                        snd.AudioType.mp3,
                        )):
                # https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio (Audio formats supported by MP4/M4A)
                ffmpeg_output_cmd += ['-c:a', 'copy']
                bCopied = True
                ffmpeg_format = 'mp4'
            else:
                # TODO select preferred encoder based on bitrate: https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio
                kbitrate = [target_bitrate]
                if kbitrate[0] is None:
                    kbitrate = [round(inputfile.bitrate / 1000.0 / 16.0) * 16 for inputfile in inputfiles]
                    kbitrate = sorted(set(kbitrate))
                    kbitrate = [kbitrate[0]]  # TODO
                if len(kbitrate) == 1:
                    kbitrate = kbitrate[0]
                    if use_qaac:
                        use_qaac_cmd = True
                        if len(audio_type) == 1 and audio_type[0] in (
                                snd.AudioType.mp2,
                                snd.AudioType.mp3,
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
                            app.log.info('NOTE: Using recommended high-quality LC-AAC libfaac settings; If it fails, try: --bitrate %dk', kbitrate)
                            ffmpeg_output_cmd += ['-c:a', 'libfaac', '-q:a', '330', '-cutoff', '15000']  # 100% ~= 128k, 330% ~= ?
                        elif kbitrate > 64:
                            app.log.info('NOTE: Using recommended high-quality LC-AAC libfdk_aac settings; If it fails, try: --bitrate %dk', kbitrate)
                            ffmpeg_output_cmd += ['-c:a', 'libfdk_aac', '-b:a', '%dk' % (kbitrate,)]
                        elif kbitrate >= 48:
                            app.log.info('NOTE: Using recommended high-quality HE-AAC libfdk_aac 64k settings; If it fails, try: --bitrate %dk', kbitrate)
                            ffmpeg_output_cmd += ['-c:a', 'libfdk_aac', '-profile:a', 'aac_he', '-b:a', '64k']
                            if itunes_compat:
                                ffmpeg_output_cmd += ['-signaling:a', 'implicit']  # iTunes compatibility: implicit backwards compatible signaling
                        elif True:
                            app.log.info('NOTE: Using recommended high-quality HE-AAC libfdk_aac 32k settings; If it fails, try: --bitrate %dk', kbitrate)
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
            filesfile = TempFile.mkstemp(suffix='.files.txt')
            app.log.info('Writing %s...', filesfile)
            def body(fp):
                print('ffconcat version 1.0', file=fp)
                for inputfile in inputfiles:
                    print('file \'%s\'' % (
                        os.path.join(os.getcwd(), inputfile.file_name) \
                            .replace('\\', '\\\\').replace('\'', '\'\\\'\''),
                        ), file=fp)
                    if hasattr(inputfile, 'duration'):
                        print('duration %.3f' % (inputfile.duration,), file=fp)
            safe_write_file_eval(filesfile, body)
            app.log.info('Files:\n' +
                         re.sub(r'^', '    ', safe_read_file(filesfile), flags=re.MULTILINE))
            ffmpeg_input_cmd += ['-f', 'concat', '-safe', '0', '-i', filesfile.file_name]
        else:
            ffmpeg_input_cmd += ['-i', inputfiles_names[0]]

        ffmpeg_output_cmd += ['-f', ffmpeg_format]

        intermediate_wav_files = []
        try:

            if use_qaac_intermediate:
                assert use_qaac_cmd
                new_inputfiles_names = []
                for inputfile_name in inputfiles_names:
                    intermediate_wav_file = snd.SoundFile(file_name=os.path.splitext(inputfile_name)[0] + '.tmp.wav')
                    intermediate_wav_files.append(intermediate_wav_file)
                    new_inputfiles_names.append(intermediate_wav_file.file_name)
                    out = do_spawn_cmd([shutil.which('ffmpeg'), '-i', inputfile_name, intermediate_wav_file.file_name])
                    # TODO out
                inputfiles_names = new_inputfiles_names

            if len(inputfiles_names) > 1:
                qaac_cmd += ['--concat'] + inputfiles_names
            else:
                qaac_cmd += [inputfiles_names[0]]

            ffmpeg_output_cmd += [m4b.file_name]
            qaac_cmd += ['-o', m4b.file_name]
            if use_qaac_cmd:
                qaac_cmd += ['--text-codepage', '65001']  # utf-8
                if chapters_file:
                    qaac_cmd += ['--chapter', chapters_file.file_name]
                # TODO qaac_cmd += qaac.get_tag_args(m4b.tags)
                if picture is not None:
                    qaac_cmd += ['--artwork', str(picture)]
            if use_qaac_cmd:
                out = do_spawn_cmd(qaac_cmd)
            else:
                out = ffmpeg(*(ffmpeg_cmd + ffmpeg_input_cmd + ffmpeg_output_cmd))
                out = out.out
            out_time = None
            # {{{
            out = clean_cmd_output(out)
            if use_qaac_cmd:
                parser = lines_parser(out.split('\n'))
                while parser.advance():
                    parser.line = parser.line.strip()
                    if parser.re_search(r'^\[[0-9.]+%\] [0-9:.]+/(?P<out_time>[0-9:.]+) \([0-9.]+x\), ETA [0-9:.]+$'):
                        # [35.6%] 2:51:28.297/8:01:13.150 (68.2x), ETA 4:32.491
                        out_time = qip.snd.parse_time_duration(parser.match.group('out_time'))
                    else:
                        pass  # TODO
            else:
                parser = lines_parser(out.split('\n'))
                while parser.advance():
                    parser.line = parser.line.strip()
                    if parser.re_search(r'^size= *(?P<out_size>\S+) time= *(?P<out_time>\S+) bitrate= *(?P<out_bitrate>\S+)(?: speed= *(?P<out_speed>\S+))?$'):
                        # size=  223575kB time=07:51:52.35 bitrate=  64.7kbits/s
                        # size= 3571189kB time=30:47:24.86 bitrate= 263.9kbits/s speed= 634x
                        out_time = qip.snd.parse_time_duration(parser.match.group('out_time'))
                    elif parser.re_search(r' time= *(?P<out_time>\S+) bitrate='):
                        app.log.warning('TODO: %s', parser.line)
                        pass
                    else:
                        pass  # TODO
            # }}}
            print('')
            if expected_duration is not None:
                app.log.info('Expected final duration: %s (%.3f seconds)', qip.snd.mp4chaps_format_time_offset(expected_duration), expected_duration)
            if out_time is None:
                app.log.warning('final duration unknown!')
            else:
                app.log.info('Final duration:          %s (%.3f seconds)', qip.snd.mp4chaps_format_time_offset(out_time), out_time)

        finally:
            for intermediate_wav_file in intermediate_wav_files:
                intermediate_wav_file.unlink(force=True)

        if not use_qaac_cmd and chapters_file:
            app.log.info("Adding chapters...")
            cmd = [shutil.which('mp4chaps')]
            cmd += ['-i', m4b.file_name]
            out = do_exec_cmd(cmd)

        app.log.info('Adding tags...')
        m4b.write_tags(run_func=do_exec_cmd)

        if not use_qaac_cmd:
            if picture is not None:
                app.log.info('Adding picture...')
                cmd = [shutil.which('mp4art')]
                cmd += ['--add', str(picture), m4b.file_name]
                out = do_exec_cmd(cmd)

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
