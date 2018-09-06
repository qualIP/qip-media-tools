#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

from qip.app import app
app.init(
        version='1.0',
        description='Media Organizer',
        )

import argparse
import decimal
import errno
import functools
import html
import logging
import os
import pexpect
import re
import reprlib
import shutil
import subprocess
import sys
import tempfile
import unidecode
import xml.etree.ElementTree as ET
reprlib.aRepr.maxdict = 100

from qip import json
from qip.cmp import *
from qip.exec import *
from qip.file import *
from qip.m4b import *
from qip.parser import *
from qip.qaac import qaac
import qip.snd
from qip.snd import *
from qip.utils import byte_decode

# replace_html_entities {{{

def replace_html_entities(s):
    s = html.unescape(s)
    m = re.search(r'&\w+;', s)
    if m:
        raise ValueError('Unknown HTML entity: %s' % (m.group(0),))
    return s

# }}}

# TODO app.parser.add_argument('--help', '-h', action='help')
app.parser.add_argument('--version', '-V', action='version')

pgroup = app.parser.add_argument_group('Program Control')
pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')
xgroup = pgroup.add_mutually_exclusive_group()
xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

pgroup = app.parser.add_argument_group('Files')
pgroup.add_argument('--output', '-o', dest='outputdir', default=argparse.SUPPRESS, help='specify the output directory')

pgroup = app.parser.add_argument_group('Compatibility')
xgroup = pgroup.add_mutually_exclusive_group()
xgroup.add_argument('--ascii-compat', dest='ascii_compat', default=True, action='store_true', help='ASCII compatibility (default)')
xgroup.add_argument('--no-ascii-compat', dest='ascii_compat', default=argparse.SUPPRESS, action='store_false', help='ASCII compatibility (disable)')

app.parser.add_argument('inputfiles', nargs='*', default=None, help='input sound files')

app.parse_args()

if getattr(app.args, 'action', None) is None:
    app.args.action = 'organize'
if not hasattr(app.args, 'logging_level'):
    app.args.logging_level = logging.INFO
app.set_logging_level(app.args.logging_level)
if app.args.logging_level <= logging.DEBUG:
    reprlib.aRepr.maxdict = 100

def main():
    global in_tags

    for prog in (
            'ffmpeg',  # ffmpeg | libav-tools
            'mp4info',  # mp4v2-utils
            ):
        if not shutil.which(prog):
            raise Exception('%s: command not found' % (prog,))
    for prog in (
            'id3info',  # libid3-utils
            'id3v2',  # id3v2
            'soxi',  # sox
            'sox',  # sox
            'gm',  # graphicsmagick
            'file',
            ):
        if not shutil.which(prog):
            app.log.warning('%s: command not found; Functionality may be limited.', prog)

    if app.args.action == 'organize':
        # {{{

        if not app.args.inputfiles:
            raise Exception('No input files provided')
        organize(app.args.inputfiles)

        # }}}
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

# clean_file_name {{{

def clean_file_name(file_name, keep_ext=True, extra=''):
    if keep_ext:
        name, ext = os.path.splitext(file_name)
    else:
        name, ext = file_name, ''
    name = unidecode.unidecode(name)
    # http://en.wikipedia.org/wiki/Filename {{{
    # UNIX: a leading . indicates that ls and file managers will not show the file by default
    name = re.sub(r'^[.]+', '', name)
    # Remove leading spaces too
    name = re.sub(r'^[ ]+', '', name)
    # NTFS: The Win32 API strips trailing space and period (full-stop) characters from filenames, except when UNC paths are used.
    name = re.sub(r'[ .]+$', '', name)
    # most: forbids the use of 0x00
    name = re.sub(r'\x00', '_', name)
    # NTFS/vfat: forbids the use of characters in range 1-31 (0x01-0x1F) and characters " * : < > ? \ / | unless the name is flagged as being in the Posix namespace.
    name = re.sub(r'[\x01-\x1F\"*:<>?\\/|]', '_', name)
    # vfat: forbids the use of 0x7F
    name = re.sub(r'\x7F', '_', name)
    # NTFS allows each path component (directory or filename) to be 255 characters long.
    over = len(name) + len(extra) + len(ext) - 255
    if over > 0:
        name = name[:len(name)-over]
    # }}}
    file_name = name + extra + ext
    return file_name

# }}}

def debug_tags(inputfile):
    app.log.debug(inputfile)
    print("Tags:")
    for tag_info in mp4tags.tag_args_info:
        # Force None values to actually exist
        if inputfile.tags[tag_info.tag_enum] is None:
            inputfile.tags[tag_info.tag_enum] = None
    for tag in sorted(inputfile.tags.keys(), key=functools.cmp_to_key(dictionarycmp)):
        value = inputfile.tags[tag]
        if isinstance(value, str):
            inputfile.tags[tag] = value = replace_html_entities(inputfile.tags[tag])
        if value is not None:
            if type(value) not in (int, str):
                value = str(value)
            print('    %-13s = %r' % (tag.value, value))

def organize(inputfiles):
    inputfiles = [
            inputfile if isinstance(inputfile, SoundFile) else SoundFile(file_name=inputfile)
            for inputfile in inputfiles]

    for inputfile in inputfiles:
        if not os.path.isfile(inputfile.file_name):
            raise OSError(errno.ENOENT, 'No such file', inputfile.file_name)
        app.log.info('Reading %s...', inputfile)
        inputfile.extract_info(need_actual_duration=False)
        #debug_tags(inputfile)

        dst_dir = \
            clean_file_name(inputfile.tags.albumartist, keep_ext=False) + '/' + \
            clean_file_name(inputfile.tags.albumtitle, keep_ext=False) + '/'
        if inputfile.tags.disk and inputfile.tags.disks and \
                inputfile.tags.disks > 1:
            disk = "%02d" % inputfile.tags.disk
        else:
            disk = None
        if inputfile.tags.track is not None:
            track = "%02d" % inputfile.tags.track
        else:
            track = None
        dst_file_base = "{disk}{disk_track_sep}{track}{track_title_sep}{title}{ext}".format(
            disk=disk or '',
            track=track or '',
            title=inputfile.tags.title,
            ext=os.path.splitext(inputfile.file_name)[1],
            disk_track_sep='-' if disk and track else '',
            track_title_sep=' ' if disk or track else '',
        )
        print("== " + str(inputfile.file_name))
        src_stat = os.lstat(inputfile.file_name)
        skip = False
        for n in range(1,10):
            dst_file_name = dst_dir + clean_file_name(dst_file_base,
                                                           extra='-%d' % (n,) if n > 1 else '')
            if os.path.exists(dst_file_name):
                dst_stat = os.lstat(dst_file_name)
                if dst_stat.st_ino == src_stat.st_ino:
                    skip = True
                    print('SS')
                    break;
            print("-> " + str(dst_file_name))
            break;
        else:
            print('EE')
    return

    app.log.debug('inputfiles = %r', inputfiles)
    inputfiles = sorted(inputfiles, key=functools.cmp_to_key(qip.snd.soundfilecmp))
    for inputfile in inputfiles:
        if inputfile.tags[SoundTagEnum.title] is not None:
            inputfile.tags[SoundTagEnum.title] = clean_audio_file_title(inputfile, inputfile.tags[SoundTagEnum.title])

    if app.args.single:
        for tag1, tag2 in [
                [SoundTagEnum.title,       SoundTagEnum.title],
                [SoundTagEnum.subtitle,    SoundTagEnum.subtitle],
                [SoundTagEnum.artist,      SoundTagEnum.artist],
                [SoundTagEnum.disk,        SoundTagEnum.disk],
                [SoundTagEnum.track,       SoundTagEnum.track],
                ]:
            if m4b.tags[tag1] is None:
                if m4b.tags[tag2] is not None:
                    m4b.tags[tag1] = m4b.tags[tag2]
                elif inputfiles[0].tags[tag2] is not None:
                    m4b.tags[tag1] = inputfiles[0].tags[tag2]
    if True:
        for tag1, tag2 in [
            [SoundTagEnum.albumtitle,  SoundTagEnum.albumtitle],
            [SoundTagEnum.albumtitle,  SoundTagEnum.title],
            [SoundTagEnum.title,       SoundTagEnum.albumtitle],
            [SoundTagEnum.title,       SoundTagEnum.title],
            [SoundTagEnum.albumartist, SoundTagEnum.albumartist],
            [SoundTagEnum.albumartist, SoundTagEnum.artist],
            [SoundTagEnum.artist,      SoundTagEnum.albumartist],
            [SoundTagEnum.artist,      SoundTagEnum.artist],
            [SoundTagEnum.composer,    SoundTagEnum.composer],
            [SoundTagEnum.genre,       SoundTagEnum.genre],
            [SoundTagEnum.grouping,    SoundTagEnum.grouping],
            [SoundTagEnum.date,        SoundTagEnum.date],
            [SoundTagEnum.copyright,   SoundTagEnum.copyright],
            [SoundTagEnum.encodedby,   SoundTagEnum.encodedby],
            [SoundTagEnum.tool,        SoundTagEnum.tool],
            [SoundTagEnum.type,        SoundTagEnum.type],
            ]:
            if m4b.tags[tag1] is None:
                if m4b.tags[tag2] is not None:
                    m4b.tags[tag1] = m4b.tags[tag2]
                elif inputfiles[0].tags[tag2] is not None:
                    m4b.tags[tag1] = inputfiles[0].tags[tag2]

    # m4b.file_name {{{
    if 'outputfile' in app.args:
        m4b.file_name = app.args.outputfile
    else:
        parts = []
        v = m4b.tags[SoundTagEnum.albumartist]
        if v:
            parts.append(v)
        if True or app.args.single:
            v = m4b.tags[SoundTagEnum.artist]
            if v:
                parts.append(v)
        v = m4b.tags[SoundTagEnum.albumtitle]
        assert v, '%r albumtitle not known' % (m4b,)
        if v:
            parts.append(v)
        if True or app.args.single:
            v = m4b.tags[SoundTagEnum.title]
            assert v, '%r title not known' % (m4b,)
            if v:
                parts.append(v)
        for i in range(len(parts)-2):  # skip last part XXXJST TODO why?
            parts[i] = re.sub(r' */ *', ' and ', parts[i])
        v = m4b.tags[SoundTagEnum.track]
        if v:
            parts.append('track%02d' % (v,))
        i = 0
        while i < len(parts)-1:  # skip last part
            if parts[i] == parts[i + 1]:
                del parts[i]
            else:
                i += 1
        m4b.file_name = clean_file_name(" - ".join(parts) + '.m4b')
    # }}}

    if len(inputfiles) > 1:
        filesfile = os.path.splitext(m4b.file_name)[0] + '.files.txt'
        app.log.info('Writing %s...', filesfile)
        def body(fp):
            print('ffconcat version 1.0', file=fp)
            for inputfile in inputfiles:
                print('file \'%s\'' % (
                    inputfile.file_name.replace('\\', '\\\\').replace('\'', '\'\\\'\''),
                    ), file=fp)
                if hasattr(inputfile, 'duration'):
                    print('duration %.3f' % (inputfile.duration,), file=fp)
        safe_write_file_eval(filesfile, body)
        print('Files:')
        print(re.sub(r'^', '    ', safe_read_file(filesfile), flags=re.MULTILINE))

    expected_duration = None
    chapters_file = TextFile(file_name=os.path.splitext(m4b.file_name)[0] + '.chapters.txt')
    if hasattr(app.args, 'chaptersfile'):
        if os.path.abspath(app.args.chaptersfile) == os.path.abspath(chapters_file.file_name):
            app.log.info('Reusing %s...', chapters_file)
        else:
            app.log.info('Writing %s from %s...', chapters_file, app.args.chaptersfile)
            shutil.copyfile(app.args.chaptersfile, chapters_file.file_name)
    elif app.args.reuse_chapters and chapters_file.exists():
        app.log.info('Reusing %s...', chapters_file)
    else:
        app.log.info('Writing %s...', chapters_file)
        def body(fp):
            nonlocal expected_duration
            offset = 0  # XXXJST TODO decimal.Decimal(0) ?
            for inputfile in inputfiles:
                for chap_info in get_audio_file_chapters(inputfile, chapter_naming_format=app.args.chapter_naming_format):
                    print('%s %s' % (
                        qip.snd.mp4chaps_format_time_offset(offset + chap_info.time),
                        replace_html_entities(chap_info.name),
                        ), file=fp)
                if len(inputfiles) == 1 and not hasattr(inputfile, 'duration'):
                    pass  # Ok... never mind
                else:
                    offset += inputfile.duration
            expected_duration = offset
        safe_write_file_eval(chapters_file, body)
    print('Chapters:')
    print(re.sub(r'^', '    ', safe_read_file(chapters_file), flags=re.MULTILINE))
    if expected_duration is not None:
        app.log.info('Expected final duration: %s (%.3f seconds)', qip.snd.mp4chaps_format_time_offset(expected_duration), expected_duration)

    src_picture = m4b.tags.picture
    if not src_picture:
        if inputfiles[0].tags.picture:
            src_picture = inputfiles[0].tags.picture
        if getattr(inputfiles[0], 'num_cover', 0):
            src_picture = inputfiles[0].file_name
        else:
            for ext in ('.png', '.jpg', '.jpeg', '.gif'):
                test_src_picture = os.path.join(os.path.dirname(inputfiles[0].file_name), 'AlbumArt' + ext)
                if os.path.exists(test_src_picture):
                    src_picture = test_src_picture
                    break

    picture = None
    # select_src_picture {{{

    def select_src_picture(new_picture):
        nonlocal picture
        nonlocal src_picture
        if not new_picture:
            src_picture = ''
            app.log.warning('No picture.')
            picture = None
        else:
            src_picture = new_picture
            app.log.info('Using picture from %s...', src_picture)
            picture = src_picture
            if os.path.splitext(new_picture)[1] not in ('.gif', '.png', '.jpg', '.jpeg'):
                picture = os.path.splitext(m4b.file_name)[0] + '.png'
                if new_picture != picture:
                    app.log.info('Writing new picture %s...', picture)
                cmd = [shutil.which('ffmpeg')]
                if True or app.args.yes:
                    cmd += ['-y']
                cmd += ['-i', new_picture]
                cmd += ['-an', picture]
                do_exec_cmd(cmd, stderr=subprocess.STDOUT)
                new_picture = picture
            if app.args.ipod_compat and shutil.which('gm'):
                picture = os.path.splitext(m4b.file_name)[0] + '.png'
                app.log.info('Writing iPod-compatible picture %s...', picture)
                cmd = [shutil.which('gm'),
                        'convert', new_picture,
                        '-resize', 'x480>',
                        picture]
                do_exec_cmd(cmd)

    # }}}
    select_src_picture(src_picture)

    # Sort tags
    # NOT: composer artist albumartist
    if False:
        # XXXJST
        for tag in (SoundTagEnum.title, SoundTagEnum.albumtitle, SoundTagEnum.show):
            sorttag = SoundTagEnum('sort' + tag.value)
            if sorttag not in m4b.tags and tag in m4b.tags:
                m = re.search(r'^(?P<a>.+) \((?P<b>.+) #(?P<n>\d+)\)$', m4b.tags[tag])
                if m:
                    m4b.tags[sorttag] = '{b} #{n!d:%02} - {a}'.format(m.groupdict())

    print("Tags:")
    for tag_info in mp4tags.tag_args_info:
        # Force None values to actually exist
        if m4b.tags[tag_info.tag_enum] is None:
            m4b.tags[tag_info.tag_enum] = None
    for tag in sorted(m4b.tags.keys(), key=functools.cmp_to_key(dictionarycmp)):
        value = m4b.tags[tag]
        if isinstance(value, str):
            m4b.tags[tag] = value = replace_html_entities(m4b.tags[tag])
        if value is not None:
            if type(value) not in (int, str):
                value = str(value)
            print('    %-13s = %r' % (tag.value, value))

    if app.args.interactive:
        while True:
            print('')
            print('Interactive mode...')
            print(' t - edit tags')
            print(' c - edit chapters')
            print(' p - change picture%s' % (' (%s)' % (src_picture,) if src_picture else ''))
            print(' q - quit')
            print(' y - yes, do it!')
            c = input('Choice: ')
            if c == 't':
                try:
                    m4b.tags = edvar(m4b.tags)[1]
                except ValueError as e:
                    app.log.error(e)
            elif c == 'c':
                edfile(chapters_file)
            elif c == 'p':
                select_src_picture(os.path.expanduser(input('Cover file: ')))
            elif c == 'q':
                return False
            elif c == 'y':
                break
            else:
                app.log.error('Invalid input')

    app.log.info('Writing %s...', m4b)
    use_qaac_cmd = False
    use_qaac_intermediate = False
    ffmpeg_cmd = [shutil.which('ffmpeg')]
    ffmpeg_input_cmd = []
    ffmpeg_output_cmd = []
    qaac_cmd = [qaac.which()]
    qaac_cmd += ['--threading']
    if app.args.yes:
        ffmpeg_cmd += ['-y']
    ffmpeg_cmd += ['-stats']
    qaac_cmd += ['--verbose']
    ffmpeg_output_cmd += ['-vn']
    ffmpeg_format = 'ipod'
    bCopied = False
    bitrate = getattr(app.args, 'bitrate', None)
    if bitrate is None:
        # bitrate = ... {{{
        audio_type = [inputfile.audio_type for inputfile in inputfiles]
        audio_type = sorted(set(audio_type))
        if (
                not app.args.force_encode and
                len(audio_type) == 1 and audio_type[0] in (
                    AudioType.aac,
                    AudioType.lc_aac,
                    AudioType.he_aac,
                    AudioType.ac3,
                    )):
            # https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio (Audio formats supported by MP4/M4A)
            ffmpeg_output_cmd += ['-c:a', 'copy']
            bCopied = True
            ffmpeg_format = 'ipod'  # See codec_ipod_tags @ ffmpeg/libavformat/movenc.c
        elif (
                not app.args.force_encode and
                not app.args.ipod_compat and
                len(audio_type) == 1 and audio_type[0] in (
                    AudioType.mp2,
                    AudioType.mp3,
                    )):
            # https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio (Audio formats supported by MP4/M4A)
            ffmpeg_output_cmd += ['-c:a', 'copy']
            bCopied = True
            ffmpeg_format = 'mp4'
        else:
            # TODO select preferred encoder based on bitrate: https://trac.ffmpeg.org/wiki/Encode/HighQualityAudio
            kbitrate = [getattr(app.args, 'target_bitrate', None)]
            if kbitrate[0] is None:
                kbitrate = [round(inputfile.bitrate / 1000.0 / 16.0) * 16 for inputfile in inputfiles]
                kbitrate = sorted(set(kbitrate))
                kbitrate = [kbitrate[0]]  # TODO
            if len(kbitrate) == 1:
                kbitrate = kbitrate[0]
                if app.args.use_qaac:
                    use_qaac_cmd = True
                    if len(audio_type) == 1 and audio_type[0] in (
                            AudioType.mp2,
                            AudioType.mp3,
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
                        if app.args.itunes_compat:
                            ffmpeg_output_cmd += ['-signaling:a', 'implicit']  # iTunes compatibility: implicit backwards compatible signaling
                    elif True:
                        app.log.info('NOTE: Using recommended high-quality HE-AAC libfdk_aac 32k settings; If it fails, try: --bitrate %dk', kbitrate)
                        ffmpeg_output_cmd += ['-c:a', 'libfdk_aac', '-profile:a', 'aac_he_v2', '-b:a', '32k']
                        if app.args.itunes_compat:
                            ffmpeg_output_cmd += ['-signaling:a', 'implicit']  # iTunes compatibility: implicit backwards compatible signaling
                    else:
                        bitrate = '%dk' % (kbitrate,)
            else:
                raise Exception('Unable to determine proper bitrate from %rk' % (kbitrate,))
        # }}}
    if bitrate is not None:
        ffmpeg_output_cmd += ['-b:a', bitrate]
    if hasattr(app.args, 'channels'):
        ffmpeg_output_cmd += ['-ac', app.args.channels]
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
        ffmpeg_input_cmd += ['-f', 'concat', '-safe', '0', '-i', filesfile]
    else:
        ffmpeg_input_cmd += ['-i', inputfiles_names[0]]

    ffmpeg_output_cmd += ['-f', ffmpeg_format]

    intermediate_wav_files = []
    try:

        if use_qaac_intermediate:
            assert use_qaac_cmd
            new_inputfiles_names = []
            for inputfile_name in inputfiles_names:
                intermediate_wav_file = SoundFile(file_name=os.path.splitext(inputfile_name)[0] + '.tmp.wav')
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
            qaac_cmd += ['--chapter', chapters_file.file_name]
            # TODO qaac_cmd += qaac.get_tag_args(m4b.tags)
            if picture is not None:
                qaac_cmd += ['--artwork', picture]
        if use_qaac_cmd:
            out = do_spawn_cmd(qaac_cmd)
        else:
            out = do_spawn_cmd(ffmpeg_cmd + ffmpeg_input_cmd + ffmpeg_output_cmd)
        out_time = None
        # {{{
        out = clean_cmd_output(out)
        if use_qaac_cmd:
            parser = lines_parser(out.split('\n'))
            while parser.advance():
                parser.line = parser.line.strip()
                if parser.re_search(r'^\[[0-9.]+%\] [0-9:.]+/(?P<out_time>[0-9:.]+) \([0-9.]+x\), ETA [0-9:.]+$'):
                    # [35.6%] 2:51:28.297/8:01:13.150 (68.2x), ETA 4:32.491  
                    out_time = parse_time_duration(parser.match.group('out_time'))
                else:
                    pass  # TODO
        else:
            parser = lines_parser(out.split('\n'))
            while parser.advance():
                parser.line = parser.line.strip()
                if parser.re_search(r'^size= *(?P<out_size>\S+) time= *(?P<out_time>\S+) bitrate= *(?P<out_bitrate>\S+)(?: speed= *(?P<out_speed>\S+))?$'):
                    # size=  223575kB time=07:51:52.35 bitrate=  64.7kbits/s
                    # size= 3571189kB time=30:47:24.86 bitrate= 263.9kbits/s speed= 634x
                    out_time = parse_time_duration(parser.match.group('out_time'))
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

    if not use_qaac_cmd:
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
            cmd += ['--add', picture, m4b.file_name]
            out = do_exec_cmd(cmd)

    app.log.info('DONE!')

    if mp4info.which(assert_found=False):
        print('')
        cmd = [mp4info.which()]
        cmd += [m4b.file_name]
        out = do_exec_cmd(cmd)
        out = clean_cmd_output(out)
        print(out)

    return True

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
