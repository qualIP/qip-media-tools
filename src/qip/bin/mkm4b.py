#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

from qip.app import app
app.init(
        version='1.0',
        description='M4B Audiobook Maker',
        )

import argparse
import decimal
import functools
import html
import logging
import os
import pexpect
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import sys
import errno
import reprlib
reprlib.aRepr.maxdict = 100

from qip.cmp import *
from qip.parser import *
import qip.snd
from qip.snd import *
from qip.m4b import *
from qip.file import *
from qip.exec import *
from qip.utils import byte_decode
from qip import json
from qip.qaac import qaac

# https://www.ffmpeg.org/ffmpeg.html

def dbg_spawn_cmd(cmd, hidden_args=[], no_status=False, yes=False):
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.verbose('CMD: %s', subprocess.list2cmdline(cmd))
    out = ''
    p = pexpect.spawn(cmd[0], args=cmd[1:] + hidden_args, timeout=None, logfile=sys.stdout.buffer)
    while True:
        index = p.expect([
            r'.*[\r\n]',  # 0
            r'File \'.*\' already exists\. Overwrite \? \[y/N\] $',  # 1
            pexpect.EOF,
            ])
        if index == 0:
            #app.log.debug('<<< %s%s', byte_decode(p.before), byte_decode(p.match.group(0)))
            out += byte_decode(p.before) + byte_decode(p.match.group(0))
        elif index == 1:
            #app.log.debug('<<< %s%s', byte_decode(p.before), p.match.group(0))
            #puts [list <<< $expect_out(buffer)]
            out += byte_decode(p.before) + byte_decode(p.match.group(0))
            logfile = p.logfile
            logfile_send = p.logfile_send
            try:
                if yes:
                    s = "y"
                else:
                    print('<interact>', end='', flush=True)
                    s = input()
                    print('</interact>', end='', flush=True)
                    p.logfile = None
                    p.logfile_send = None
                #app.log.debug('>>> sending %r', s)
                p.send(s)
                #puts [list >>> sending eol]
                p.send('\r')
            finally:
                p.logfile_send = logfile_send
                p.logfile = logfile
        elif index == 2:
            #app.log.debug('<<< %s%s', byte_decode(p.before))
            out += byte_decode(p.before)
            break
    try:
        p.wait()
    except pexpect.ExceptionPexpect as err:
        if err.value != 'Cannot wait for dead child process.':
            raise
    p.close()
    if p.signalstatus is not None:
        raise Exception('Command exited due to signal %r' % (p.signalstatus,))
    if not no_status and p.exitstatus:
        raise Exception('Command returned status %r' % (p.exitstatus,))
    return out

def do_spawn_cmd(cmd, **kwargs):
    if app.args.dry_run:
        app.log.verbose('CMD (dry-run): %s', subprocess.list2cmdline(cmd))
        return ''
    else:
        return dbg_spawn_cmd(cmd, **kwargs)

# edfile {{{

def edfile(file):
    file = str(file)

    if 'EDITOR' in os.environ:
        editor = os.editor['EDITOR']
    else:
        for e in ('vim', 'vi', 'emacs'):
            editor = shutil.which(e)
            if editor:
                break
        else:
            raise Exception('No editor found; Please set \'EDITOR\' environment variable.')

    startMtime = os.path.getmtime(file)
    os.system(subprocess.list2cmdline([editor, file]))
    return os.path.getmtime(file) != startMtime

# }}}
# edvar {{{

def edvar(value, *, encoding='utf-8'):

    with TempFile(file_name=None) as tmp_file:
        fp, tmp_file.file_name = tempfile.mkstemp(suffix='.json', text=True)
        with os.fdopen(fp, 'w') as fp:
            json.dump(value, fp, indent=2, sort_keys=True, ensure_ascii=False)
            print('', file=fp)
        if not edfile(tmp_file):
            return (False, value)
        with tmp_file.open(mode='r', encoding=encoding) as fp:
            new_value = json.load(fp)
            #if type(new_value) is not type(value):
            #    raise ValueError(new_value)
            return (True, new_value)

# }}}

# safe_write_file_eval {{{

def safe_write_file_eval(file, body, *, encoding='utf-8'):
    file = str(file)
    if (
            not os.access(file, os.W_OK) and
            (os.path.exists(file) or
                not os.access(os.path.dirname(file), os.W_OK))):
        pass # XXXJST TODO: raise Exception('couldn\'t open "%s"' % (file,))
    with TempFile(file + '.tmp') as tmp_file:
        with tmp_file.open(mode='w', encoding=encoding) as fp:
            ret = body(fp)
        os.rename(tmp_file.file_name, file)
        tmp_file.delete = False
    return ret

# }}}
# safe_write_file {{{

def safe_write_file(file, content):
    def body(fp):
        fp.buffer.write(content)
    safe_write_file_eval(file, body)

# }}}
# safe_read_file {{{

def safe_read_file(file, *, encoding='utf-8'):
    return open(str(file), mode='r', encoding=encoding).read()

# }}}

# times_1000 {{{

def times_1000(v):
    if type(v) is int:
        v *= 1000
    else:
        # 1E+3 = 1000 with precision of 1 so precision of v is not increased
        v = decimal.Decimal(v) * decimal.Decimal('1E+3')
        if v.as_tuple().exponent >= 0:
            v = int(v)
    return v

# }}}

# mk_cache_file {{{

def mk_cache_file(base_file, cache_ext):
    base_file = str(base_file)
    cache_dir = os.path.join(
            os.path.dirname(base_file),
            "mkm4b-cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(
        cache_dir,
        os.path.basename(base_file) + cache_ext)
    return cache_file

# }}}

# replace_html_entities {{{

def replace_html_entities(s):
    s = html.unescape(s)
    m = re.search(r'&\w+;', s)
    if m:
        raise ValueError('Unknown HTML entity: %s' % (m.group(0),))
    return s

# }}}

# get_audio_file_info {{{

def get_audio_file_info(d, need_actual_duration=True):
    tags_done = False
    if os.path.splitext(d.file_name)[1] in qip.snd.get_mp4v2_app_support().extensions_can_read:
        if not tags_done and mp4info.which(assert_found=False):
            # {{{
            d2, track_tags = mp4info.query(d.file_name)
            if d2.get('audio_type', None) is not None:
                tags_done = True
            for k, v in track_tags.items():
                d.tags.update(track_tags)
            for k, v in d2.items():
                setattr(d, k, v)
            # }}}
    if os.path.splitext(d.file_name)[1] not in ('.ogg', '.mp4', '.m4a', '.m4p', '.m4b', '.m4r', '.m4v'):
        # parse_id3v2_id3info_out {{{
        def parse_id3v2_id3info_out(out):
            nonlocal d
            nonlocal tags_done
            out = clean_cmd_output(out)
            parser = lines_parser(out.split('\n'))
            while parser.advance():
                tag_type = 'id3v2'
                if parser.line == '':
                    pass
                elif parser.re_search(r'^\*\*\* Tag information for '):
                    # (id3info)
                    # *** Tag information for 01 Bad Monkey - Part 1.mp3
                    pass
                elif parser.re_search(r'^\*\*\* mp3 info$'):
                    # (id3info)
                    # *** mp3 info
                    pass
                elif parser.re_search(r'^(MPEG1/layer III)$'):
                    # (id3info)
                    # MPEG1/layer III
                    d.audio_type = parser.match.group(1)
                elif parser.re_search(r'^Bitrate: (\d+(?:\.\d+)?)KBps$'):
                    # (id3info)
                    # Bitrate: 64KBps
                    d.bitrate = times_1000(parser.match.group(1))
                elif parser.re_search(r'^Frequency: (\d+(?:\.\d+)?)KHz$'):
                    # (id3info)
                    # Frequency: 44KHz
                    d.frequency = times_1000(parser.match.group(1))
                elif parser.re_search(r'^(?P<tag_type>id3v1|id3v2) tag info for '):
                    # (id3v2)
                    # id3v1 tag info for 01 Bad Monkey - Part 1.mp3:
                    # id3v2 tag info for 01 Bad Monkey - Part 1.mp3:
                    tag_type = parser.match.group('tag_type')

                elif parser.re_search(r'^Title *: (?P<Title>.+) Artist:(?: (?P<Artist>.+))?$'):
                    # (id3v2)
                    # Title  : Bad Monkey - Part 1             Artist: Carl Hiaasen
                    tags_done = True
                    for tag, value in parser.match.groupdict(default='').items():
                        d.set_tag(tag, value, tag_type)
                elif parser.re_search(r'^Album *: (?P<Album>.+) Year: (?P<Year>.+), Genre:(?: (?P<Genre>.+))?$'):
                    # (id3v2)
                    # Album  : Bad Monkey                      Year:     , Genre: Other (12)
                    tags_done = True
                    for tag, value in parser.match.groupdict(default='').items():
                        d.set_tag(tag, value, tag_type)
                elif parser.re_search(r'^Comment: (?P<Comment>.+) Track:(?: (?P<Track>.+))?$'):
                    # (id3v2)
                    # Comment: <p>                             Track: 1
                    tags_done = True
                    for tag, value in parser.match.groupdict(default='').items():
                        d.set_tag(tag, value, tag_type)

                elif (
                        parser.re_search(r'^(?:=== )?(TPA|TPOS) \(.*?\): (.+)$') or 
                        parser.re_search(r'^(?:=== )?(TRK|TRCK) \(.*?\): (.+)$')
                        ):
                    # ("===" version is id3info, else id3v2)
                    # === TPA (Part of a set): 1/2
                    # === TRK (Track number/Position in set): 1/3
                    tags_done = True
                    tag, value = parser.match.groups()
                    d.set_tag(tag, value, tag_type)

                elif (
                        parser.re_search(r'^(?:=== )?(TAL|TALB) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TCM|TCOM) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TCO|TCON) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TCR|TCOP) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TEN|TENC) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TMT|TMED) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TP1|TPE1) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TSE|TSSE) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TT2|TIT2) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TT3|TIT3) \(.*?\): (.+)$') or
                        parser.re_search(r'^(?:=== )?(TYE|TYER) \(.*?\): (.+)$')
                        ):
                    # ("===" version is id3info, else id3v2)
                    tags_done = True
                    tag, value = parser.match.groups()
                    d.set_tag(tag, value, tag_type)

                elif parser.re_search(r'^(?:=== )?(PIC|APIC) \(.*?\): (.+)$'):
                    # ("===" version is id3info, else id3v2)
                    # === PIC (Attached picture): ()[PNG, 0]: , 407017 bytes
                    # APIC (Attached picture): ()[, 0]: image/jpeg, 40434 bytes
                    tags_done = True
                    d.num_cover = 1  # TODO

                elif parser.re_search(r'^(?:=== )?(TXX|TXXX) \(.*?\): \(OverDrive MediaMarkers\): (<Markers>.+</Markers>)$'):
                    # TXXX (User defined text information): (OverDrive MediaMarkers): <Markers><Marker><Name>Bad Monkey</Name><Time>0:00.000</Time></Marker><Marker><Name>Preface</Name><Time>0:11.000</Time></Marker><Marker><Name>Chapter 1</Name><Time>0:35.000</Time></Marker><Marker><Name>      Chapter 1 (05:58)</Name><Time>5:58.000</Time></Marker><Marker><Name>      Chapter 1 (10:30)</Name><Time>10:30.000</Time></Marker><Marker><Name>Chapter 2</Name><Time>17:51.000</Time></Marker><Marker><Name>      Chapter 2 (24:13)</Name><Time>24:13.000</Time></Marker><Marker><Name>      Chapter 2 (30:12)</Name><Time>30:12.000</Time></Marker><Marker><Name>      Chapter 2 (36:57)</Name><Time>36:57.000</Time></Marker><Marker><Name>Chapter 3</Name><Time>42:28.000</Time></Marker><Marker><Name>      Chapter 3 (49:24)</Name><Time>49:24.000</Time></Marker><Marker><Name>      Chapter 3 (51:41)</Name><Time>51:41.000</Time></Marker><Marker><Name>      Chapter 3 (55:27)</Name><Time>55:27.000</Time></Marker><Marker><Name>Chapter 4</Name><Time>59:55.000</Time></Marker><Marker><Name>      Chapter 4 (01:07:10)</Name><Time>67:10.000</Time></Marker><Marker><Name>      Chapter 4 (01:10:57)</Name><Time>70:57.000</Time></Marker></Markers>
                    tags_done = True
                    app.log.debug('TODO: OverDrive: %s', parser.match.groups(2))
                    d.OverDrive_MediaMarkers = parser.match.group(2)

                else:
                    app.log.debug('TODO: %s', parser.line)
                    # TLAN (Language(s)): XXX
                    # TPUB (Publisher): Books On Tape
                    pass
        # }}}
        if not tags_done and shutil.which('id3info'):
            if os.path.splitext(d.file_name)[1] not in ('.wav'):
                # id3info is not reliable on WAVE files as it may perceive some raw bytes as MPEG/Layer I and give out incorrect info
                # {{{
                try:
                    out = dbg_exec_cmd(['id3info', d.file_name])
                except subprocess.CalledProcessError as err:
                    app.log.debug(err)
                    pass
                else:
                    parse_id3v2_id3info_out(out)
                # }}}
        if not tags_done and shutil.which('id3v2'):
            # {{{
            try:
                out = dbg_exec_cmd(['id3v2', '-l', d.file_name])
            except subprocess.CalledProcessError as err:
                app.log.debug(err)
                pass
            else:
                parse_id3v2_id3info_out(out)
            # }}}
    if os.path.splitext(d.file_name)[1] in qip.snd.get_sox_app_support().extensions_can_read:
        if not tags_done and shutil.which('soxi'):
            # {{{
            try:
                out = dbg_exec_cmd(['soxi', d.file_name])
            except subprocess.CalledProcessError:
                pass
            else:
                out = clean_cmd_output(out)
                parser = lines_parser(out.split('\n'))
                while parser.advance():
                    tag_type = 'id3v2'
                    if parser.line == '':
                        pass
                    elif parser.re_search(r'^Sample Rate *: (\d+)$'):
                        # Sample Rate    : 44100
                        d.frequency = int(parser.match.group(1))
                    elif parser.re_search(r'^Duration *: 0?(\d+):0?(\d+):0?(\d+\.\d+) '):
                        # Duration       : 01:17:52.69 = 206065585 samples = 350452 CDDA sectors
                        d.duration = (
                                decimal.Decimal(parser.match.group(3)) +
                                int(parser.match.group(2)) * 60 +
                                int(parser.match.group(1)) * 60 * 60
                                )
                    elif parser.re_search(r'^Bit Rate *: (\d+(?:\.\d+)?)M$'):
                        # Bit Rate       : 99.1M
                        v = decimal.Decimal(parser.match.group(1))
                        if v >= 2:
                            #raise ValueError('soxi bug #251: soxi reports invalid rate (M instead of K) for some VBR MP3s. (https://sourceforge.net/p/sox/bugs/251/)')
                            pass
                        else:
                            d.sub_bitrate = times_1000(times_1000(v))
                    elif parser.re_search(r'^Bit Rate *: (\d+(?:\.\d+)?)k$'):
                        # Bit Rate       : 64.1k
                        d.sub_bitrate = times_1000(parser.match.group(1))
                    elif parser.re_search(r'(?i)^(?P<tag>Discnumber|Tracknumber)=(?P<value>\d*/\d*)$'):
                        # Tracknumber=1/2
                        # Discnumber=1/2
                        d.set_tag(parser.match.group('tag'), parser.match.group('value'), tag_type)
                    elif parser.re_search(r'(?i)^(?P<tag>ALBUMARTIST|Artist|Album|DATE|Genre|Title|Year|encoder)=(?P<value>.+)$'):
                        # ALBUMARTIST=James Patterson & Maxine Paetro
                        # Album=Bad Monkey
                        # Artist=Carl Hiaasen
                        # DATE=2012
                        # Genre=Spoken & Audio
                        # Title=Bad Monkey - Part 1
                        # Year=2012
                        tags_done = True
                        d.set_tag(parser.match.group('tag'), parser.match.group('value'), tag_type)
                    elif parser.re_search(r'^Sample Encoding *: (.+)$'):
                        # Sample Encoding: MPEG audio (layer I, II or III)
                        try:
                            d.audio_type = parser.match.group(1)
                        except ValueError:
                            # Sample Encoding: 16-bit Signed Integer PCM
                            # TODO
                            pass
                    elif parser.re_search(r'(?i)^TRACKNUMBER=(\d+)$'):
                        # Tracknumber=1
                        # TRACKNUMBER=1
                        d.set_tag('track', parser.match.group(1))
                    elif parser.re_search(r'(?i)^TRACKTOTAL=(\d+)$'):
                        # TRACKTOTAL=15
                        d.set_tag('tracks', parser.match.group(1))
                    elif parser.re_search(r'(?i)^DISCNUMBER=(\d+)$'):
                        # DISCNUMBER=1
                        d.set_tag('disk', parser.match.group(1))
                    elif parser.re_search(r'(?i)^DISCTOTAL=(\d+)$'):
                        # DISCTOTAL=15
                        d.set_tag('disks', parser.match.group(1))
                    elif parser.re_search(r'(?i)^Input File *: \'(.+)\'$'):
                        # Input File     : 'path.ogg'
                        pass
                    elif parser.re_search(r'(?i)^Channels *: (\d+)$'):
                        # Channels       : 2
                        d.channels = int(parser.match.group(1))
                    elif parser.re_search(r'(?i)^Precision *: (\d+)-bit$'):
                        # Precision      : 16-bit
                        d.precision_bits = int(parser.match.group(1))
                    elif parser.re_search(r'(?i)^File Size *: (.+)$'):
                        # File Size      : 5.47M
                        # File Size      : 552k
                        pass
                    elif parser.re_search(r'(?i)^Comments *: (.*)$'):
                        # Comments       :
                        pass  # TODO
                    else:
                        app.log.debug('TODO: %s', parser.line)
                        # TODO
                        # DISCID=c8108f0f
                        # MUSICBRAINZ_DISCID=liGlmWj2ww4up0n.XKJUqaIb25g-
                        # RATING:BANSHEE=0.5
                        # PLAYCOUNT:BANSHEE=0
            # }}}
    if not hasattr(d, 'bitrate'):
        if shutil.which('file'):
            # {{{
            try:
                out = dbg_exec_cmd(['file', '-b', '-L', d.file_name])
            except subprocess.CalledProcessError:
                pass
            else:
                out = clean_cmd_output(out)
                parser = lines_parser(out.split(','))
                # Ogg data, Vorbis audio, stereo, 44100 Hz, ~160000 bps, created by: Xiph.Org libVorbis I
                # RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, stereo 44100 Hz
                while parser.advance():
                    parser.line = parser.line.strip()
                    if parser.re_search(r'^(\d+) Hz$'):
                        d.frequency = int(parser.match.group(1))
                    elif parser.re_search(r'^stereo (\d+) Hz$'):
                        d.channels = 2
                        d.frequency = int(parser.match.group(1))
                    elif parser.re_search(r'^\~(\d+) bps$'):
                        if not hasattr(d, 'bitrate'):
                            d.bitrate = int(parser.match.group(1))
                    elif parser.re_search(r'^created by: (.+)$'):
                        d.set_tag('tool', parser.match.group(1))
                    elif parser.line == 'Ogg data':
                        pass
                    elif parser.line == 'Vorbis audio':
                        d.audio_type = parser.line
                    elif parser.line == 'WAVE audio':
                        d.audio_type = parser.line
                    elif parser.line == 'stereo':
                        d.channels = 2
                    elif parser.re_search(r'^Audio file with ID3 version ([0-9.]+)$'):
                        # Audio file with ID3 version 2.3.0
                        pass
                    elif parser.line == 'RIFF (little-endian) data':
                        # RIFF (little-endian) data
                        pass
                    elif parser.line == 'contains: RIFF (little-endian) data':
                        # contains: RIFF (little-endian) data
                        pass
                    elif parser.line == 'Microsoft PCM':
                        # Microsoft PCM
                        pass
                    elif parser.re_search(r'^(\d+) bit$'):
                        # 16 bit
                        d.sample_bits = int(parser.match.group(1))
                        pass
                    else:
                        app.log.debug('TODO: %r: %s', d, parser.line)
                        # TODO
                        pass
            # }}}

    # TODO ffprobe

    if need_actual_duration and not hasattr(d, 'actual_duration'):
        get_audio_file_ffmpeg_stats(d)
    if need_actual_duration and not hasattr(d, 'actual_duration'):
        get_audio_file_sox_stats(d)

    if hasattr(d, 'sub_bitrate') and not hasattr(d, 'bitrate'):
        d.bitrate = d.sub_bitrate
    if not hasattr(d, 'bitrate'):
        try:
            d.bitrate = d.frequency * d.sample_bits * d.channels
        except AttributeError:
            pass
    if hasattr(d, 'actual_duration'):
        d.duration = d.actual_duration

    album_tags = get_album_tags_from_tags_file(d)
    if album_tags is not None:
        d.tags.album_tags = album_tags
        tags_done = True
    track_tags = get_track_tags_from_tags_file(d)
    if track_tags is not None:
        d.tags.update(track_tags)
        tags_done = True
    if not tags_done:
        raise Exception('Failed to read tags from %s' % (d.file_name,))
    # app.log.debug('get_audio_file_info: %r', vars(d))
    return d

class AlbumTagsCache(dict):

    def __missing__(self, key):
        tags_file = JsonFile(key)
        album_tags = None
        if tags_file.exists():
            app.log.info('Reading %s...', tags_file)
            with tags_file.open('r', encoding='utf-8') as fp:
                album_tags = AlbumTags.json_load(fp)
        self[key] = album_tags
        return album_tags

class TrackTagsCache(dict):

    def __missing__(self, key):
        tags_file = JsonFile(key)
        track_tags = None
        if tags_file.exists():
            app.log.info('Reading %s...', tags_file)
            with tags_file.open('r', encoding='utf-8') as fp:
                track_tags = TrackTags.json_load(fp)
        self[key] = track_tags
        return track_tags

album_tags_file_cache = AlbumTagsCache()

def get_album_tags_from_tags_file(snd_file):
    snd_file = str(snd_file)
    m = re.match(r'^(?P<album_base_name>.+)-\d\d?$', os.path.splitext(snd_file)[0])
    if m:
        tags_file_name = m.group('album_base_name') + '.tags'
        return album_tags_file_cache[tags_file_name]

track_tags_file_cache = TrackTagsCache()

def get_track_tags_from_tags_file(snd_file):
    snd_file = str(snd_file)
    tags_file_name = os.path.splitext(snd_file)[0] + '.tags'
    return track_tags_file_cache[tags_file_name]

# }}}
# get_audio_file_sox_stats {{{

def get_audio_file_sox_stats(d):
    cache_file = mk_cache_file(d.file_name, '.soxstats')
    if (
            os.path.exists(cache_file) and
            os.path.getmtime(cache_file) >= os.path.getmtime(d.file_name)
            ):
        out = safe_read_file(cache_file)
    elif shutil.which('sox') and os.path.splitext(d.file_name)[1] in qip.snd.get_sox_app_support().extensions_can_read:
        app.log.info('Analyzing %s...', d.file_name)
        # NOTE --ignore-length: see #251 soxi reports invalid rate (M instead of K) for some VBR MP3s. (https://sourceforge.net/p/sox/bugs/251/)
        try:
            out = dbg_exec_cmd(['sox', '--ignore-length', d.file_name, '-n', 'stat'], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            # TODO ignore/report failure only?
            raise
        else:
            safe_write_file(cache_file, out)
    else:
        out = ''
    # {{{
    out = clean_cmd_output(out)
    parser = lines_parser(out.split('\n'))
    while parser.advance():
        if parser.line == '':
            pass
        elif parser.re_search(r'^Samples +read: +(\S+)$'):
            # Samples read:         398082816
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Length +\(seconds\): +(\d+(?:\.\d+)?)$'):
            # Length (seconds):   4513.410612
            d.actual_duration = decimal.Decimal(parser.match.group(1))
        elif parser.re_search(r'^Scaled +by: +(\S+)$'):
            # Scaled by:         2147483647.0
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Maximum +amplitude: +(\S+)$'):
            # Maximum amplitude:     0.597739
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Minimum +amplitude: +(\S+)$'):
            # Minimum amplitude:    -0.586463
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Midline +amplitude: +(\S+)$'):
            # Midline amplitude:     0.005638
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Mean +norm: +(\S+)$'):
            # Mean    norm:          0.027160
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Mean +amplitude: +(\S+)$'):
            # Mean    amplitude:     0.000005
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^RMS +amplitude: +(\S+)$'):
            # RMS     amplitude:     0.047376
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Maximum +delta: +(\S+)$'):
            # Maximum delta:         0.382838
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Minimum +delta: +(\S+)$'):
            # Minimum delta:         0.000000
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Mean +delta: +(\S+)$'):
            # Mean    delta:         0.002157
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^RMS +delta: +(\S+)$'):
            # RMS     delta:         0.006849
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Rough +frequency: +(\S+)$'):
            # Rough   frequency:         1014
            pass  # d.TODO = parser.match.group(1)
        elif parser.re_search(r'^Volume +adjustment: +(\S+)$'):
            # Volume adjustment:        1.673
            pass  # d.TODO = parser.match.group(1)
        else:
            app.log.debug('TODO: %s', parser.line)
    # }}}
    # app.log.debug('get_audio_file_sox_stats: %r', vars(d))

# }}}
# get_audio_file_ffmpeg_stats {{{

def get_audio_file_ffmpeg_stats(d):
    cache_file = mk_cache_file(d.file_name, '.ffmpegstats')
    if (
            os.path.exists(cache_file) and
            os.path.getmtime(cache_file) >= os.path.getmtime(d.file_name)
            ):
        out = safe_read_file(cache_file)
    elif shutil.which('ffmpeg'):
        app.log.info('Analyzing %s...', d.file_name)
        try:
            out = dbg_exec_cmd([
                'ffmpeg',
                '-i', d.file_name,
                '-vn',
                '-f', 'null',
                '-y',
                '/dev/null'], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            # TODO ignore/report failure only?
            raise
        else:
            safe_write_file(cache_file, out)
    else:
        out = ''
    # {{{
    out = clean_cmd_output(out)
    parser = lines_parser(out.split('\n'))
    while parser.advance():
        parser.line = parser.line.strip()
        if parser.line == '':
            pass
        elif parser.re_search(r'^size= *(?P<out_size>\S+) time= *(?P<out_time>\S+) bitrate= *(?P<out_bitrate>\S+)(?: speed= *(?P<out_speed>\S+))?$'):
            # size=N/A time=00:02:17.71 bitrate=N/A
            # size=N/A time=00:12:32.03 bitrate=N/A speed= 309x    
            # There will be multiple; Only the last one is relevant.
            d.actual_duration = parse_time_duration(parser.match.group('out_time'))
        elif parser.re_search(r'Error while decoding stream .*: Invalid data found when processing input'):
            # Error while decoding stream #0:0: Invalid data found when processing input
            raise Exception('%s: %s' % (d.file_name, parser.line))
        else:
            #app.log.debug('TODO: %s', parser.line)
            pass
    # }}}
    # app.log.debug('ffmpegstats: %r', vars(d))

# }}}

# get_audio_file_chapters {{{

def get_audio_file_chapters(snd_file, chapter_naming_format):
    chaps = []
    if not chaps and app.args.OverDrive_MediaMarkers:
        if hasattr(snd_file, 'OverDrive_MediaMarkers'):
            chaps = parse_OverDrive_MediaMarkers(snd_file.OverDrive_MediaMarkers)
    if not chaps and os.path.splitext(snd_file.file_name)[1] in qip.snd.get_mp4v2_app_support().extensions_can_read:
        if shutil.which('mp4chaps'):
            # {{{
            try:
                out = dbg_exec_cmd(['mp4chaps', '-l', snd_file.file_name])
            except subprocess.CalledProcessError:
                pass
            else:
                out = clean_cmd_output(out)
                parser = lines_parser(out.split('\n'))
                while parser.advance():
                    if parser.line == '':
                        pass
                    elif parser.re_search(r'^(QuickTime|Nero) Chapters of "(.*)"$'):
                        # QuickTime Chapters of "../Carl Hiaasen - Bad Monkey.m4b"
                        # Nero Chapters of "../Carl Hiaasen - Bad Monkey.m4b"
                        pass
                    elif parser.re_search(r'^ +Chapter #0*(\d+) - (\d+:\d+:\d+\.\d+) - "(.*)"$'):
                        #     Chapter #001 - 00:00:00.000 - "Bad Monkey"
                        chaps.append(SoundFile.Chapter(
                            time = parse_time_duration(parser.match.group(2)),
                            name = parser.match.group(3)))
                    elif parser.re_search(r'^File ".*" does not contain chapters'):
                        # File "Mario Jean_ Gare au gros nounours!.m4a" does not contain chapters of type QuickTime and Nero
                        pass
                    else:
                        app.log.debug('TODO: %s', parser.line)
                        raise ValueError('Invalid mp4chaps line: %s' % (parser.line,))
                        # TODO
            # }}}
    if not chaps:
        chaps.append(SoundFile.Chapter(
                time=0,
                name=get_audio_file_default_chapter(snd_file, chapter_naming_format=chapter_naming_format)))
    return chaps

# }}}
# get_audio_file_default_chapter {{{

def get_audio_file_default_chapter(d, chapter_naming_format):
    if chapter_naming_format == 'default':
        if d.tags.contains(SoundTagEnum.title, strict=True):
            m = re.search(r'^Track \d+$', d.tags.title)
            if m:
                if d.tags.disk is not None and d.tags.disk != '1/1':
                    return get_audio_file_default_chapter(d, chapter_naming_format='disk-track')
                else:
                    return get_audio_file_default_chapter(d, chapter_naming_format='track')
            return d.tags.title
        if d.tags.track is not None:
            return get_audio_file_default_chapter(d, chapter_naming_format='disk-track')
        else:
            return get_audio_file_default_chapter(d, chapter_naming_format='title')
    if chapter_naming_format == 'title':
        if d.tags.contains(SoundTagEnum.title, strict=True):
            return d.tags.title
        return clean_audio_file_title(d, os.path.splitext(os.path.split(d.file_name)[1])[0])
    if chapter_naming_format == 'track':
        track = d.tags.track
        if track is not None:
            return 'Track %0*d' % (len(str(d.tags.tracks or 1)), track)
        return get_audio_file_default_chapter(d, chapter_naming_format='title')
    if chapter_naming_format in ('disc', 'disk'):
        disk = d.tags.disk
        if disk is not None:
            return 'Disk %0*d' % (len(str(d.tags.disks or 1)), disk)
        return get_audio_file_default_chapter(d, chapter_naming_format='title')
    if chapter_naming_format in ('disc-track', 'disk-track'):
        if d.tags.disk is not None:
            return '%s - %s' % (
                get_audio_file_default_chapter(d, chapter_naming_format='disk'),
                get_audio_file_default_chapter(d, chapter_naming_format='track'),
            )
        return get_audio_file_default_chapter(d, chapter_naming_format='track')
    raise Exception('Invalid chapter naming format \'%s\'' % (chapter_naming_format,))

# }}}
# clean_audio_file_title {{{

def clean_audio_file_title(d, title):
    track = d.tags.track
    if track is not None:
        title = re.sub(r'^0*%s( *\[:-\] *)'.format(track), '', title)
    return title

# }}}

# parse_time_duration {{{

def parse_time_duration(dur):
    match = re.search(r'^(?:(?:0*(?P<h>\d+):)?0*(?P<m>\d+):)?0*(?P<s>\d+.\d+)$', dur)
    if match:
        # 00:00:00.000
        # 00:00.000
        # 00.000
        h = match.group('h')
        m = match.group('m')
        s = decimal.Decimal(match.group('s'))
        if m:
            s += int(m) * 60
        if h:
            s += int(h) * 60 * 60
    else:
        raise ValueError('Invalid time offset format: %s' % (dur,))
    return s

# }}}
# parse_OverDrive_MediaMarkers {{{

def parse_OverDrive_MediaMarkers(xml):
    markers = []
    root = ET.fromstring(xml)
    for nodeMarker in root.findall('Markers/Marker'):
        marker = {}
        bKeep = True
        for childNode in nodeMarker:
            tag = childNode.tag
            value = childNode.text
            if tag == 'Name':
                # "Chapter 1"
                if value.startswith('\xA0') or value.endswith(' continued'):
                    # Continuation
                    # "______Chapter 1 (05:58)" (\xA0 = &nbsp;, shown as "_")
                    # "Chapter 1 continued"
                    bKeep = False
                    break
            elif tag == 'Time':
                pass
            else:
                pass
            marker[tag] = value
        if bKeep:
            markers.append(marker)
    chaps = []
    for marker in markers:
        chap = SoundFile.Chapter(
                time=parse_time_duration(marker['Time']),
                name=marker['Name'],
                )
        chap.OverDrive_MediaMarker = marker
    return chaps

# }}}

# get_vbr_formats {{{

def get_vbr_formats():
    # List of possibly VBR formats
    return [
            'mp3',
            ]

# }}}

in_tags = TrackTags()

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

pgroup = app.parser.add_argument_group('Alternate Actions')
xgroup = pgroup.add_mutually_exclusive_group()
xgroup.add_argument('--ffmpegstats', dest='action', default=argparse.SUPPRESS, action='store_const', const='ffmpegstats', help='execute ffmpeg stats action only')
xgroup.add_argument('--type-list', action=qip.snd.ArgparseTypeListAction)
xgroup.add_argument('--genre-list', action=qip.snd.ArgparseGenreListAction)

pgroup = app.parser.add_argument_group('Files')
pgroup.add_argument('--single', action='store_true', help='create single audiobooks files')
pgroup.add_argument('--output', '-o', dest='outputfile', default=argparse.SUPPRESS, help='specify the output file name')

pgroup = app.parser.add_argument_group('Compatibility')
xgroup = pgroup.add_mutually_exclusive_group()
xgroup.add_argument('--ipod-compat', dest='ipod_compat', default=True, action='store_true', help='iPod compatibility (default)')
xgroup.add_argument('--no-ipod-compat', dest='ipod_compat', default=argparse.SUPPRESS, action='store_false', help='iPod compatibility (disable)')
xgroup = pgroup.add_mutually_exclusive_group()
xgroup.add_argument('--itunes-compat', dest='itunes_compat', default=True, action='store_true', help='iTunes compatibility (default)')
xgroup.add_argument('--no-itunes-compat', dest='itunes_compat', default=argparse.SUPPRESS, action='store_false', help='iTunes compatibility (disable)')

pgroup = app.parser.add_argument_group('Chapters Control')
pgroup.add_argument('--chapters', dest='chaptersfile', default=argparse.SUPPRESS, help='specify the chapters file name')
pgroup.add_argument('--reuse-chapters', action='store_true', help='reuse chapters.txt file')
pgroup.add_argument('--chapter-naming', dest='chapter_naming_format', default="default", help='chapters naming format',
        choices=["default", "title", "track", "disc", "disk", "disc-track", "disk-track"])
xgroup = pgroup.add_mutually_exclusive_group()
xgroup.add_argument('--OverDrive-MediaMarkers', dest='OverDrive_MediaMarkers', default=True, action='store_true', help='use OverDrive MediaMarkers (default)')
xgroup.add_argument('--no-OverDrive-MediaMarkers', dest='OverDrive_MediaMarkers', default=argparse.SUPPRESS, action='store_false', help='do not use OverDrive MediaMarkers')

pgroup = app.parser.add_argument_group('Encoding')
xgroup = pgroup.add_mutually_exclusive_group()
xgroup.add_argument('--force-encode', dest='force_encode', default=False, action='store_true', help='force encoding (enable)')
xgroup.add_argument('--no-force-encode', dest='force_encode', default=argparse.SUPPRESS, action='store_false', help='do not force encoding (default)')
pgroup.add_argument('--bitrate', type=int, default=argparse.SUPPRESS, help='force the encoding bitrate')  # TODO support <int>k
pgroup.add_argument('--target-bitrate', dest='target_bitrate', type=int, default=argparse.SUPPRESS, help='specify the resampling target bitrate')
pgroup.add_argument('--channels', dest='ac', type=int, default=argparse.SUPPRESS, help='force the number of audio channels (ffmpeg -ac)')
pgroup.add_argument('--qaac', dest='use_qaac', default=True, action='store_true', help='use qaac, if available')
pgroup.add_argument('--no-qaac', dest='use_qaac', default=argparse.SUPPRESS, action='store_false', help='do not use qaac')

pgroup = app.parser.add_argument_group('Tags')
pgroup.add_argument('--title', '--song', '-s', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--album', '-A', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--artist', '-a', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--albumartist', '-R', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--genre', '-g', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--writer', '-w', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--year', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--type', tags=in_tags, default='audiobook', action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--disk', '--disc', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--track', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--picture', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--sort-title', '--sort-song', dest='sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--sort-album', dest='sortalbum', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--sort-artist', dest='sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--sort-albumartist', dest='sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
pgroup.add_argument('--sort-writer', dest='sortwriter', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)

app.parser.add_argument('inputfiles', nargs='*', default=None, help='input sound files')

app.parse_args()

if getattr(app.args, 'action', None) is None:
    app.args.action = 'mkm4b'
if not hasattr(app.args, 'logging_level'):
    app.args.logging_level = logging.INFO
app.set_logging_level(app.args.logging_level)
if app.args.logging_level <= logging.DEBUG:
    reprlib.aRepr.maxdict = 100
# app.log.debug('get_sox_app_support: %r', qip.snd.get_sox_app_support())
# app.log.debug('get_vbr_formats: %r', get_vbr_formats())
# app.log.debug('get_mp4v2_app_support: %r', qip.snd.get_mp4v2_app_support())

def main():
    global in_tags

    for prog in (
            'ffmpeg',  # ffmpeg | libav-tools
            'mp4chaps',  # mp4v2-utils
            'mp4tags',  # mp4v2-utils
            'mp4art',  # mp4v2-utils
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

    if app.args.action == 'ffmpegstats':
        # {{{

        if not app.args.inputfiles:
            raise Exception('No input files provided')
        for inputfile in app.args.inputfiles:
            d = SoundFile(file_name=inputfile)
            get_audio_file_ffmpeg_stats(d)

        # }}}
    elif app.args.action == 'mkm4b':
        # {{{

        if not app.args.inputfiles:
            raise Exception('No input files provided')
        if app.args.single:
            for inputfile in app.args.inputfiles:
                mkm4b([inputfile], in_tags)
        else:
            mkm4b(app.args.inputfiles, in_tags)

        # }}}
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

# clean_file_name {{{

def clean_file_name(file_name):
    name, ext = os.path.splitext(file_name)
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
    over = len(name) + len(ext) - 255
    if over > 0:
        name = name[:len(name)-over]
    # }}}
    file_name = name + ext
    return file_name

# }}}

def mkm4b(inputfiles, default_tags):
    m4b = AudiobookFile(file_name=None)
    m4b.tags.update(default_tags)

    inputfiles = [
            inputfile if isinstance(inputfile, SoundFile) else SoundFile(file_name=inputfile)
            for inputfile in inputfiles]
    for inputfile in inputfiles:
        if not os.path.isfile(inputfile.file_name):
            raise OSError(errno.ENOENT, 'No such file', inputfile.file_name)
        app.log.info('Reading %s...', inputfile)
        get_audio_file_info(inputfile, need_actual_duration=(len(inputfiles) > 1))
        #app.log.debug(inputfile)

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
        app.log.info(re.sub(r'^', '    ', safe_read_file(filesfile), flags=re.MULTILINE))

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
                    elif kbitrate >= 128:
                        qaac_cmd += qaac.Preset.high_quality.cmdargs
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
                if parser.re_search(r'^size= *(?P<out_size>\S+) time= *(?P<out_time>\S+) bitrate= *(?P<out_bitrate>\S+)$'):
                    # size=  223575kB time=07:51:52.35 bitrate=  64.7kbits/s
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
