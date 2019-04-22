
__all__ = [
        'CDDACueSheetFile',
        'CDToc',
        'CDTocFile',
        ]

import enum
import functools
import os
import re
import logging
log = logging.getLogger(__name__)

CDDA_BYTES_PER_SECTOR = 2352  # bytes
CDDA_CHANNELS = 2  # channels
CDDA_SAMPLE_BITS = 16  # bits/sample
CDDA_BYTES_PER_SAMPLE = CDDA_CHANNELS * CDDA_SAMPLE_BITS // 8
CDDA_SAMPLE_RATE = 44100  # samples/s/channel
CDDA_BYTES_PER_SECOND = CDDA_SAMPLE_RATE * CDDA_BYTES_PER_SAMPLE
CDDA_SECTORS_PER_SECOND = CDDA_BYTES_PER_SECOND // CDDA_BYTES_PER_SECTOR
# 1 timecode frame = 1 sector
CDDA_TIMECODE_FRAME_PER_SECOND = CDDA_SECTORS_PER_SECOND
assert CDDA_TIMECODE_FRAME_PER_SECOND == 75

CDDA_1X_SPEED = CDDA_BYTES_PER_SECOND

from .file import *
from .mm import *

# class MSF {{{

@functools.total_ordering
class MSF(object):
    '''mm:ss:ff (minute-second-frame) format'''

    def __init__(self, value):
        if isinstance(value, MSF):
            frames = value.frames
        elif isinstance(value, int):
            frames = value
        elif isinstance(value, str):
            m = re.search('^(?P<mm>\d\d):(?P<ss>\d\d):(?P<ff>\d\d)$', value)
            if m:
                mm = int(m.group('mm'))
                ss = int(m.group('ss'))
                ff = int(m.group('ff'))
                assert ff < CDDA_TIMECODE_FRAME_PER_SECOND
                frames = ((mm * 60) + ss) * CDDA_TIMECODE_FRAME_PER_SECOND + ff
            else:
                m = re.search('(?P<f>\d+)$', value)
                if m:
                    frames = int(m.group('f'))
                else:
                    raise ValueError('Invalid mm:ss:ff format: %s' % (value,))
        else:
            raise ValueError(value)
        self.frames = frames

    @property
    def msf_triplet(self):
        return (
                (self.frames // CDDA_TIMECODE_FRAME_PER_SECOND // 60),
                (self.frames // CDDA_TIMECODE_FRAME_PER_SECOND) % 60,
                (self.frames) % CDDA_TIMECODE_FRAME_PER_SECOND,
                )

    @property
    def msf(self):
        return '%02d:%02d:%02d' % self.msf_triplet

    @property
    def seconds(self):
        return self.frames / CDDA_TIMECODE_FRAME_PER_SECOND

    @property
    def bytes(self):
        return (self.frames # 1 timeframe per sector
                * CDDA_BYTES_PER_SECTOR)

    def __str__(self):
        return self.msf

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.msf)

    def __add__(self, other):
        if isinstance(other, MSF):
            return MSF(self.frames + other.frames)
        if isinstance(other, int):
            return MSF(self.frames + other)
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, MSF):
            return MSF(self.frames - other.frames)
        if isinstance(other, int):
            return MSF(self.frames - other)
        return NotImplemented

    def __int__(self):
        return self.frames

    def __add__(self, other):
        if isinstance(other, MSF):
            return self.__class__(self.frames + other.frames)
        if isinstance(other, int):
            return self.__class__(self.frames + other)
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, MSF):
            return self.__class__(self.frames - other.frames)
        if isinstance(other, int):
            return self.__class__(self.frames - other)
        return NotImplemented

    def __eq__(self, other):
        if isinstance(other, MSF):
            return self.frames == other.frames
        if isinstance(other, int):
            return self.frames == other
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, MSF):
            return self.frames < other.frames
        if isinstance(other, int):
            return self.frames < other
        return NotImplemented

# }}}

# class CDToc {{{

class CDToc(object):

    class Track(object):

        parent = None  # CDToc/CDDACueSheetFile

        @property
        def tags(self):
            track_no = self.track_no
            tags = self.parent.tags.tracks_tags[track_no]
            tags.track_no = track_no
            return tags

        @property
        def track_no(self):
            idx = self.parent.tracks.index(self)
            return idx + 1

        @property
        def next_track(self):
            idx = self.parent.tracks.index(self)
            try:
                return self.parent.tracks[idx + 1]
            except IndexError:
                return None

        def __init__(self, *, parent, begin=None, length=None, copy_permitted=False, pre_emphasis=False, audio_channels=2):
            self.parent = parent
            self.begin = MSF(begin) if begin is not None else None
            self.length = MSF(length) if length is not None else None
            assert isinstance(copy_permitted, bool), (type(copy_permitted), copy_permitted)
            self.copy_permitted = bool(copy_permitted)
            assert isinstance(pre_emphasis, bool), (type(pre_emphasis), pre_emphasis)
            self.pre_emphasis = bool(pre_emphasis)
            self.audio_channels = int(audio_channels)

        def __repr__(self):
            return '%s(%s)' % (
                    self.__class__.__name__,
                    ', '.join(
                        ['%s=%r' % (attr, getattr(self, attr))
                            for attr, default in (
                                ('begin', None),
                                ('length', None),
                                ('copy_permitted', False),
                                ('pre_emphasis', False),
                                ('audio_channels', 2),
                                )
                            if getattr(self, attr) != default]))

    def __init__(self):
        self.tracks = []

    def add_track(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], CDToc.Track):
            assert not kwargs
            track = args[0]
        else:
            track = CDToc.Track(*args, parent=self, **kwargs)
        self.tracks.append(track)
        return track

    # def getAccurateRipIds(self):
    #     """
    #     Ported from morituri
    #
    #     Calculate the two AccurateRip ID's.
    #
    #     @returns: the two 8-character hexadecimal disc ID's
    #     @rtype:   tuple of (str, str)
    #     """
    #     # AccurateRip does not take into account data tracks,
    #     # but does count the data track to determine the leadout offset
    #     discId1 = 0
    #     discId2 = 0
    #
    #     for track in self.tracks:
    #         if not track.audio:
    #             continue
    #         offset = self.getTrackStart(track.number)
    #         discId1 += offset
    #         discId2 += (offset or 1) * track.number
    #
    #     # also add end values, where leadout offset is one past the end
    #     # of the last track
    #     last = self.tracks[-1]
    #     offset = self.getTrackEnd(last.number) + 1
    #     discId1 += offset
    #     discId2 += offset * (self.getAudioTracks() + 1)
    #
    #     discId1 &= 0xffffffff
    #     discId2 &= 0xffffffff
    #
    #     return ("%08x" % discId1, "%08x" % discId2)

    # def getAccurateRipURL(self):
    #     """
    #     Ported from morituri
    #
    #     Return the full AccurateRip URL.
    #
    #     @returns: the AccurateRip URL
    #     @rtype:   str
    #     """
    #     discId1, discId2 = self.getAccurateRipIds()
    #
    #     return "http://www.accuraterip.com/accuraterip/" \
    #         "%s/%s/%s/dBAR-%.3d-%s-%s-%s.bin" % (
    #             discId1[-1], discId1[-2], discId1[-3],
    #             self.getAudioTracks(), discId1, discId2, self.getCDDBDiscId())

# }}}
# class CDTocFile {{{

class CDTocFile(TextFile):
    '''CD Table of Contents (TOC) file
    See: http://linux.die.net/man/1/cdrdao
    '''

    _common_extensions = (
        '.toc',
    )

    tags = None
    session_type = None
    files = None
    tracks = None
    language_map = None
    pregap = 2 * CDDA_TIMECODE_FRAME_PER_SECOND

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tags = AlbumTags()

    class LanguageEnum(enum.IntEnum):
        eng = 9

    class SessionTypeEnum(enum.Enum):
        CD_DA = 'CD_DA'
        '''The disc contains only audio tracks.'''
        CD_ROM = 'CD_ROM'
        '''The disc contains just mode 1 tracks or mode 1 and audio tracks (mixed mode CD).'''
        CD_ROM_XA = 'CD_ROM_XA'
        '''The disc contains mode 2 form 1 or mode 2 form 2 tracks. Audio tracks are allowed, too.'''

    class TrackModeEnum(enum.Enum):
        AUDIO = 'AUDIO'
        '''2352 bytes (588 samples)'''
        MODE1 = 'MODE1'
        '''2048 bytes'''
        MODE1_RAW = 'MODE1_RAW'
        '''2352 bytes'''
        MODE2 = 'MODE2'
        '''2336 bytes'''
        MODE2_FORM1 = 'MODE2_FORM1'
        '''2048 bytes'''
        MODE2_FORM2 = 'MODE2_FORM2'
        '''2324 bytes'''
        MODE2_FORM_MIX = 'MODE2_FORM_MIX'
        '''2336 bytes including the sub-header'''
        MODE2_RAW = 'MODE2_RAW'
        '''2352 bytes'''

    class TrackSubChannelModeEnum(enum.Enum):
        RW = 'RW'
        '''packed R-W sub-channel data (96 bytes, L-EC data will be generated if required)'''
        RW_RAW = 'RW_RAW'
        '''raw R-W sub-channel data (interleaved and L-EC data already calculated, 96 bytes). The block length is increased by the sub-channel data length if a <sub-channel-mode> is specified. If the input data length is not a multiple of the block length it will be padded with zeros.'''

    class File(object):
        def __init__(self, name):
            assert name and isinstance(name, str)
            self.name = name

    class Track(CDToc.Track):

        def __init__(self, *, parent, mode, sub_channel_mode=None, copy_permitted=False, pre_emphasis=False, audio_channels=2):
            self.mode = CDTocFile.TrackModeEnum(mode)
            self.sub_channel_mode = CDTocFile.TrackSubChannelModeEnum(sub_channel_mode) if sub_channel_mode is not None else None
            self.datas = []
            super().__init__(
                parent=parent,
                begin=None,
                length=None,
                copy_permitted=copy_permitted,
                pre_emphasis=pre_emphasis,
                audio_channels=audio_channels,
            )

    class TrackDataTypeEnum(enum.Enum):
        AudioFile = 'AUDIOFILE'

    class TrackData(object):
        pass

    class TrackAudioData(TrackData):
        @property
        def data_type(self):
            return CDTocFile.TrackDataTypeEnum.AudioFile
        def __init__(self, file, start, length):
            assert file and isinstance(file, CDTocFile.File)
            self.file = file
            self.start = MSF(start)
            self.length = MSF(length if length is not None else 0)

    def read(self):
        content = super().read()
        assert content, f'{self} is empty?!'
        self.parse(content)
        return content

    def cmd__session_type(self, *, value, dest, lang):
        assert isinstance(value, str), (type(value), value)
        assert isinstance(dest, CDTocFile), (type(dest), dest)
        assert value
        if value:
            self.session_type = CDTocFile.SessionTypeEnum(value)

    def sec_CD_TEXT(self, *, parser, value, dest, lang):
        assert value is None
        for statement in self.iter_cdtoc_statements(parser=parser, top=False):
            self.handle_statement(statement=statement, parser=parser, dest=dest, lang=lang)

    def sec_LANGUAGE_MAP(self, *, parser, value, dest, lang):
        assert value is None
        while True:
            assert parser.advance()
            parser.line = parser.line.strip()
            if not parser.line:
                pass
            elif parser.re_search(r'(?P<index>\d+)\s*:\s*(?P<lang_id>\d+)$'):
                lang_id = int(parser.match.group('lang_id'))
                lang = CDTocFile.LanguageEnum(lang_id)
                self.language_map[int(parser.match.group('index'))] = lang
                pass
            elif parser.line == '}':
                return
            else:
                raise ValueError('Unsupported toc LANGUAGE_MAP line: %s' % (parser.line,))
        if not top:
            raise ValueError('Invalid toc: \'\}\' missing')

    def sec_LANGUAGE(self, *, parser, value, dest, lang):
        assert isinstance(value, int), (type(value), value)
        lang = self.language_map[value]
        for statement in self.iter_cdtoc_statements(parser=parser, top=False):
            self.handle_statement(statement=statement, parser=parser, dest=dest, lang=lang)

    def sec_TRACK(self, *, parser, value, dest, lang):
        assert lang is None
        assert isinstance(dest, CDTocFile), (type(dest), dest)
        mode, sub_channel_mode = value
        track = CDTocFile.Track(
            parent=self,
            mode=mode,
            sub_channel_mode=sub_channel_mode,
        )
        self.add_track(track)
        for statement in self.iter_cdtoc_statements(parser=parser, top=True):
            line, statement_type, cmd, value = statement
            if (statement_type, cmd) == ('sec', 'TRACK'):
                parser.pushback(line)
                break;
            self.handle_statement(statement=statement, parser=parser, dest=track, lang=lang)

    def cmd_TITLE(self, *, value, dest, lang):
        assert isinstance(value, str), (type(value), value)
        if value:
            dest.tags.title = value

    def cmd_PERFORMER(self, *, value, dest, lang):
        assert isinstance(value, str), (type(value), value)
        if value:
            dest.tags.artist = value

    def cmd_COMPOSER(self, *, value, dest, lang):
        assert isinstance(value, str), (type(value), value)
        if value:
            dest.tags.composer = value

    cmd_SONGWRITER = cmd_COMPOSER
    cmd_ARRANGER = cmd_COMPOSER

    def cmd_MESSAGE(self, *, value, dest, lang):
        assert isinstance(value, str), (type(value), value)
        if value:
            dest.tags.comment = value

    def cmd_GENRE(self, *, value, dest, lang):
        if isinstance(value, str):
            if value:
                dest.tags.genre = value
        elif isinstance(value, bytearray):
            assert value == b'\0\0\0'
        else:
            raise ValueError(value)

    def cmd_DISC_ID(self, *, value, dest, lang):
        assert isinstance(value, str), (type(value), value)
        if value:
            pass

    def cmd_ISRC(self, *, value, dest, lang):
        # CCOOOYYSSSSS
        # Sets ISRC code of track (only for audio tracks).
        # C: country code (upper case letters or digits)
        # O: owner code (upper case letters or digits)
        # Y: year (digits)
        # S: serial number (digits) 
        assert isinstance(value, str), (type(value), value)
        if value:
            assert re.search(r'^\S{12}$', value)
            dest.tags.isrc = value

    def cmd_UPC_EAN(self, *, value, dest, lang):
        assert isinstance(value, str), (type(value), value)
        if value:
            raise NotImplementedError(value)
            dest.tags.upc = value  # TODO

    def cmd_CATALOG(self, *, value, dest, lang):
        assert isinstance(value, str), (type(value), value)
        if value:
            dest.tags.barcode = value

    def cmd_SIZE_INFO(self, *, value, dest, lang):
        assert isinstance(value, bytearray), (type(value), value)
        pass

    def cmd_COPY(self, *, value, dest, lang):
        assert isinstance(value, bool), (type(value), value)
        assert isinstance(dest, CDTocFile.Track), (type(dest), dest)
        dest.copy_permitted = value

    def cmd_PRE_EMPHASIS(self, *, value, dest, lang):
        assert isinstance(value, bool), (type(value), value)
        assert isinstance(dest, CDTocFile.Track), (type(dest), dest)
        dest.pre_emphasis = value

    def cmd_TWO_CHANNEL_AUDIO(self, *, value, dest, lang):
        assert value is None
        assert isinstance(dest, CDTocFile.Track), (type(dest), dest)
        dest.audio_channels = 2

    def cmd_FOUR_CHANNEL_AUDIO(self, *, value, dest, lang):
        assert value is None
        assert isinstance(dest, CDTocFile.Track), (type(dest), dest)
        dest.audio_channels = 4

    def cmd_FILE(self, *, value, dest, lang):
        assert isinstance(value, tuple), (type(value), value)
        filename, start, length = value
        assert isinstance(dest, CDTocFile.Track), (type(dest), dest)
        for file in self.files:
            if file.name == filename:
                break
        else:
            file = CDTocFile.File(name=filename)
            self.files.append(file)
        data = CDTocFile.TrackAudioData(
                file=file,
                start=start,
                length=length,
                )
        dest.datas.append(data)

    cmd_AUDIOFILE = cmd_FILE

    def cmd_START(self, *, value, dest, lang):
        assert isinstance(value, MSF), (type(value), value)
        assert isinstance(dest, CDTocFile.Track), (type(dest), dest)
        dest.pregap = value.frames

    def handle_statement(self, *, statement, parser, dest, lang):
        line, statement_type, cmd, value = statement
        if statement_type == 'cmd':
            try:
                method = getattr(self, 'cmd_' + cmd)
            except AttributeError:
                raise NotImplementedError('Unsupported %s toc command' % (cmd,))
            log.debug('-> %r(%r, %r, %r)', method, value, dest, lang)
            method(value=value, dest=dest, lang=lang)
        elif statement_type == 'sec':
            try:
                method = getattr(self, 'sec_' + cmd)
            except AttributeError:
                raise NotImplementedError('Unsupported %s toc section' % (cmd,))
            log.debug('-> %r(%r, %r, %r)', method, value, dest, lang)
            method(parser=parser, value=value, dest=dest, lang=lang)
        else:
            raise ValueError(statement_type)

    def iter_cdtoc_statements(self, *, parser, top):
        while parser.advance():
            parser.line = parser.line.strip()
            log.debug('line=%r', parser.line)
            if not parser.line:
                pass
            elif parser.re_search(r'^(?P<sec>CD_TEXT|LANGUAGE_MAP)\s+\{$'):
                # section: <sec> \{
                sec = parser.match.group('sec')
                yield (parser.line, 'sec', sec, None)
            elif parser.re_search(r'^(?P<sec>LANGUAGE)\s+(?P<value>\d+)\s+\{$'):
                # section: <sec> <int-value> \{
                sec = parser.match.group('sec')
                value = int(parser.match.group('value'))
                yield (parser.line, 'sec', sec, value)
            elif parser.re_search(r'^(?P<sec>TRACK)\s+(?P<mode>\S+)(?:\s+(?P<sub_channel_mode>\S+))?$'):
                # section: TRACK <mode> [<sub_channel_mode>]
                sec = parser.match.group('sec')
                value = (
                    parser.match.group('mode'),
                    parser.match.group('sub_channel_mode'),
                )
                yield (parser.line, 'sec', sec, value)
            elif parser.re_search(r'^(?P<session_type>CD_DA|CD_ROM|CD_ROM_XA)$'):
                # session_type: <session_type>
                value = parser.match.group('session_type')
                yield (parser.line, 'cmd', '_session_type', value)
            elif parser.re_search(r'^(?P<cmd>TWO_CHANNEL_AUDIO|FOUR_CHANNEL_AUDIO|START)$'):
                # no value: <cmd>
                # Note: START
                cmd = parser.match.group('cmd')
                yield (parser.line, 'cmd', cmd, None)
            elif parser.re_search(r'^(?P<no>NO\s+)?(?P<cmd>COPY|PRE_EMPHASIS)$'):
                # boolean: [NO ]<cmd>
                cmd = parser.match.group('cmd')
                value = parser.match.group('no') is None
                yield (parser.line, 'cmd', cmd, value)
            elif parser.re_search(r'^(?P<cmd>[A-Z][A-Z_]*)\s+"(?P<value>[^"]*)"$'):
                # string: <cmd> "<value>"
                cmd = parser.match.group('cmd')
                value = parser.match.group('value')
                yield (parser.line, 'cmd', cmd, value)
            elif parser.re_search(r'^(?P<cmd>[A-Z][A-Z_]*)\s+(?P<value>\d\d:\d\d:\d\d)$'):
                # MSF: <cmd> <MM:SS:FF>
                # Note: START <MM:SS:FF>
                cmd = parser.match.group('cmd')
                value = MSF(parser.match.group('value'))
                yield (parser.line, 'cmd', cmd, value)
            elif parser.re_search(r'^(?P<cmd>FILE|AUDIOFILE)\s+"(?P<filename>[^"]+)"\s+(?P<start>0|\d\d:\d\d:\d\d)(?:\s+(?P<length>0|\d\d:\d\d:\d\d))?$'):
                # file: <cmd> "<filename>" <start> <length>
                cmd = parser.match.group('cmd')
                value = (
                    parser.match.group('filename'),
                    parser.match.group('start'),
                    parser.match.group('length'),
                )
                yield (parser.line, 'cmd', cmd, value)
            elif parser.re_search(r'^(?P<cmd>[A-Z][A-Z_]*)\s+\{(?P<bin_data>\s*\d+(?:\s*,\s*\d+)*\s*)?(?:\}|,)$'):
                # bytearray: <cmd> { 1, 2, 3 ... }
                full_line = parser.line
                while parser.line[-1] != '}' and parser.advance():
                    parser.line = parser.line.strip()
                    full_line += parser.line
                    log.debug('line=%r', full_line)
                assert full_line[-1] == '}'
                m = re.search(r'^(?P<cmd>[A-Z][A-Z_]*)\s+\{(?P<bin_data>\s*\d+(?:\s*,\s*\d+)*\s*)?\}$', full_line)
                assert m
                cmd = m.group('cmd')
                bin_data = m.group('bin_data') or ''
                value = bytearray(int(e) for e in bin_data.split(','))
                yield (full_line, 'cmd', cmd, value)
            elif parser.re_search(r'^//'):
                continue
            elif parser.line == '}':
                if top:
                    raise ValueError('Invalid toc: \'\}\' found at top-level')
                return
            else:
                raise ValueError('Invalid toc line: %s' % (parser.line,))
        if not top:
            raise ValueError('Invalid toc: \'\}\' missing')

    def parse(self, content):
        self.session_type = None
        self.files = []
        self.tracks = []
        self.tags = AlbumTags()
        self.language_map = {}
        pregap = 2 * CDDA_TIMECODE_FRAME_PER_SECOND
        from .parser import lines_parser
        parser = lines_parser(content.splitlines())
        cur_file = None
        cur_track = None
        for statement in self.iter_cdtoc_statements(parser=parser, top=True):
            self.handle_statement(statement=statement, parser=parser, dest=self, lang=None)

        # An optional CD-TEXT block that defines the CD-TEXT data for this track may follow. See the CD-TEXT section below for the syntax of the CD-TEXT block contents.
        # CD_TEXT { ... }
        # At least one of the following statements must appear to specify the data for the current track. Lengths and start positions may be expressed in samples (1/44100 seconds) for audio tracks or in bytes for data tracks. It is also possible to give the length in blocks with the MSF format 'MM:SS:FF' specifying minutes, seconds and frames (0 <= 'FF' < 75) . A frame equals one block. 
        # 
        # If more than one statement is used the track will be composed by concatenating the data in the specified order.
        # SILENCE <length>
        #     Adds zero audio data of specified length to the current audio track. Useful to create silent pre-gaps. 
        # ZERO <length>
        #     Adds zero data to data tracks. Must be used to define pre- or post-gaps between tracks of different mode. 
        # DATAFILE "<filename>" [ <length> ]
        #     Adds data from given file to the current data track. If <length> is omitted the actual file length will be used. 
        # FIFO "<fifo path>" <length>
        #     Adds data from specified FIFO path to the current audio or data track. <length> must specify the amount of data that will be read from the FIFO. The value is always in terms of bytes (scalar value) or in terms of the block length (MSF value). 
        # START [ MM:SS:FF ]
        #     Defines the length of the pre-gap (position where index switches from 0 to 1). If the MSF value is omitted the current track length is used. If the current track length is not a multiple of the block length the pre-gap length will be rounded up to next block boundary.
        # 
        #     If no START statement is given the track will not have a pre-gap. 
        # PREGAP MM:SS:FF
        #     This is an alternate way to specify a pre-gap with zero audio data. It may appear before the first SILENCE, ZERO or FILE statement. Either PREGAP or START can be used within a track specification. It is equivalent to the sequence
        #     SILENCE MM:SS:FF
        #     START
        #     for audio tracks or
        #     ZERO MM:SS:FF
        #     START
        #     for data tracks. 
        # Nothing prevents mixing 'DATAFILE'/'ZERO' and 'AUDIOFILE'/'SILENCE' statements within the same track. The results, however, are undefined.
        # 
        # The end of a track specification may contain zero or more index increment statements:
        # INDEX MM:SS:FF
        #     Increments the index number at given position within the track. The first statement will increment from 1 to 2. The position is relative to the real track start, not counting an existing pre-gap.

        # CD-TEXT Blocks
        # 
        # A CD-TEXT block may be placed in the global section to define data valid for the whole CD and in each track specification of a toc-file. The global section must define a language map that is used to map a language-number to country codes. Up to 8 different languages can be defined:
        # LANGUAGE_MAP { 0 : c1 1 : c2 ... 7 : c7 }
        #     The country code may be an integer value in the range 0..255 or one of the following countries (the corresponding integer value is placed in braces behind the token): EN(9, English)
        #     It is just necessary to define a mapping for the used languages. 
        # If no mapping exists for a language-number the data for this language will be ignored.
        # 
        # For each language a language block must exist that defines the actual data for a certain language.
        # LANGUAGE language-number { cd-text-item cd-text-data cd-text-item cd-text-data ... }
        #     Defines the CD-TEXT items for given language-number which must be defined in the language map. 
        # The cd-text-data may be either a string enclosed by " or binary data like
        # 
        # { 0, 10, 255, ... }
        # 
        # where each integer number must be in the range 0..255.
        # The cd-text-item may be one of the following:
        # TITLE
        # 
        # String data: Title of CD or track.
        # PERFORMER
        #     String data. 
        # SONGWRITER
        #     String data. 
        # COMPOSER
        #     String data. 
        # ARRANGER
        #     String data. 
        # MESSAGE
        #     String data. Message to the user. 
        # DISC_ID
        #     String data: Should only appear in the global CD-TEXT block. The format is usually: XY12345 
        # GENRE
        # 
        # Mixture of binary data (genre code) and string data. Should only appear in the global CD-TEXT block. Useful entries will be created by gcdmaster.
        # TOC_INFO1
        #     Binary data: Optional table of contents 1. Should only appear in the global CD-TEXT block. 
        # TOC_INFO2
        #     Binary data: Optional table of contents 2. Should only appear in the global CD-TEXT block. 
        # UPC_EAN
        #     String data: This item should only appear in the global CD-TEXT block. Was always an empty string on the CD-TEXT CDs I had access to. 
        # ISRC
        # 
        # String data: ISRC code of track. The format is usually: CC-OOO-YY-SSSSS
        # SIZE_INFO
        #     Binary data: Contains summary about all CD-TEXT data and should only appear in the global CD-TEXT block. The data will be automatically (re)created when the CD-TEXT data is written.
        # 
        #     If one of the CD-TEXT items TITLE, PERFORMER, SONGWRITER, COMPOSER, ARRANGER, ISRC is defined for at least on track or in the global section it must be defined for all tracks and in the global section. If a DISC_ID item is defined in the global section, an ISRC entry must be defined for each track. 

    def add_track(self, *args, **kwargs):
        if len(args) == 1 and isinstance(args[0], CDTocFile.Track):
            assert not kwargs
            track = args[0]
        else:
            track = CDToc.Track(*args, parent=self, **kwargs)
        self.tracks.append(track)
        return track

    def create(self, indent='  ', include_defaults=False, file=None):
        if file is None:
            with self.open('w', encoding='utf-8') as file:
                return self.create(file=file)
        if self.tags.barcode:
            print('CATALOG "%s"' % (self.tags.barcode,), file=file)
        print('s' % (self.session_type.value,), file=file)
        for track_no, track in enumerate(self.tracks, start=1):
            print('', file=file)
            print('// Track %d' % (track_no,), file=file)
            print('TRACK %s' % (track.mode.value,), file=file)
            if include_defaults or track.copy_permitted is not False:
                print('%sCOPY' % ('' if track.copy_permitted else 'NO ',), file=file)
            if include_defaults or track.pre_emphasis is not False:
                print('%sPRE_EMPHASIS' % ('' if track.pre_emphasis else 'NO ',), file=file)
            if track.audio_channels == 2:
                if include_defaults:
                    print('TWO_CHANNEL_AUDIO', file=file)
            elif track.audio_channels == 4:
                print('FOUR_CHANNEL_AUDIO', file=file)
            else:
                raise ValueError(track.audio_channels)
            for data in track.datas:
                if data.data_type == CDTocFile.TrackDataTypeEnum.AudioFile:
                    print('FILE "%s" %s %s' % (
                        data.file.name,
                        data.start.msf if data.start.frames != 0 else 0,
                        data.length.msf if data.length.frames != 0 else 0,
                        ), file=file)
                else:
                    raise ValueError(data)

# }}}
# class CDDACueSheetFile {{{

class CDDACueSheetFile(TextFile):

    _common_extensions = (
        '.cue',
    )

    files = None
    tracks = None
    _sectors = None
    tags = None

    pregap = 2 * CDDA_TIMECODE_FRAME_PER_SECOND

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tags = AlbumTags()

    class FileFormatEnum(enum.Enum):
        MP3 = 'MP3'
        WAVE = 'WAVE'
        BINARY = 'BINARY'
        MOTOROLA = 'MOTOROLA'

    class TrackTypeEnum(enum.Enum):
        AUDIO = 'AUDIO'
        MODE1_2352 = 'MODE1/2352'
        # CDG ?
        # MODE1_2048 ?
        # MODE1_2352 ?
        # MODE2_2336 ?
        # MODE2_2352 ?
        # CDI_2336 ?
        # CDI_2352 ?

    class File(object):
        def __init__(self, name, format):
            assert name and isinstance(name, str)
            self.name = name
            self.format = CDDACueSheetFile.FileFormatEnum(format)
            self.tags = AlbumTags()

    class Track(CDToc.Track):

        type = None  # CDDACueSheetFile.TrackTypeEnum
        file = None  # CDDACueSheetFile.File
        indexes = None  # [CDDACueSheetFile.Index]
        _length = None  # MSF

        def __init__(self, cue_file, type, file):
            self.type = CDDACueSheetFile.TrackTypeEnum(type)
            assert file and isinstance(file, CDDACueSheetFile.File)
            self.file = file
            self.indexes = {}
            super().__init__(
                parent=cue_file,
            )

        @property
        def begin(self):
            index1 = self.indexes.get(1, None)
            if index1:
                return index1.position

        @begin.setter
        def begin(self, value):
            if value is None:
                try:
                    del self.indexes[1]
                except KeyError:
                    pass
            else:
                index1 = CDDACueSheetFile.Index(
                        number=1,
                        position=value,
                        )
                self.indexes[1] = index1

        @property
        def end(self):
            length = self._length
            if length is not None:
                return self.begin + length
            next_track = self.next_track
            if next_track:
                return next_track.begin
            else:
                return MSF(self.parent.sectors)

        @property
        def length(self):
            length = self._length
            if length is not None:
                return length
            return self.end - self.begin

        @length.setter
        def length(self, value):
            self._length = value

    class Index(object):
        def __init__(self, number, position):
            #assert position
            self.number = int(number)
            self.position = MSF(position)

    def read(self):
        content = super().read()
        assert content, f'{self} is empty?!'
        self.parse(content)
        return content

    def parse(self, content):
        self.files = []
        self.tags = AlbumTags()
        self.tracks = []
        from .parser import lines_parser
        parser = lines_parser(content.splitlines())
        cur_file = None
        while parser.advance():
            parser.line = parser.line.strip()
            if not parser.line:
                pass
            elif parser.re_search(r'^FILE\s+"(?P<name>.+)"\s+(?P<format>MP3|WAVE|BINARY)$'):
                cur_file = CDDACueSheetFile.File(
                        name=parser.match.group('name'),
                        format=parser.match.group('format'),
                        )
                self.files.append(cur_file)
            elif parser.re_search(r'^TITLE\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.title = v
            elif parser.re_search(r'^PERFORMER\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.artist = v
            elif parser.re_search(r'^(?:COMPOSER|SONGWRITER|ARRANGER)\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.composer = v
            elif parser.re_search(r'^CATALOG\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.barcode = v
            elif parser.re_search(r'^MESSAGE\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.comment = v
            elif parser.re_search(r'^REM GENRE\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.genre = v
            elif parser.re_search(r'^REM DATE\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.date = v
            elif parser.re_search(r'^(?:DISC_ID|REM DISCID)\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.cddb_discid = v
            elif parser.re_search(r'^REM ACCURATERIPID\s+"(?P<value>.*)"$'):
                v = parser.match.group('value')
                if v:
                    self.tags.musicbrainz_discid = v
            elif parser.re_search(r'^REM DISCNUMBER\s+"(?P<value>.+)"$'):
                self.tags.disk = int(parser.match.group('value'))
            elif parser.re_search(r'^REM TOTALDISCS\s+"(?P<value>.+)"$'):
                self.tags.disks = int(parser.match.group('value'))
            elif parser.re_search(r'^TRACK\s+(?P<track_no>\d\d)\s+(?P<type>AUDIO|MODE1/2352)$'):
                track_no=int(parser.match.group('track_no'))
                assert track_no == len(self.tracks) + 1
                track = CDDACueSheetFile.Track(
                        cue_file=self,
                        type=parser.match.group('type'),
                        file=cur_file,
                        )
                self.tracks.append(track)
                while parser.advance():
                    parser.line = parser.line.strip()
                    if not parser.line:
                        pass
                    elif parser.re_search(r'^INDEX\s+(?P<number>\d\d)\s+(?P<position>\S+)$'):
                        index = CDDACueSheetFile.Index(
                                number=parser.match.group('number'),
                                position=parser.match.group('position'),
                                )
                        assert index.number not in track.indexes
                        track.indexes[index.number] = index
                    elif parser.re_search(r'^TITLE\s+"(?P<value>.*)"$'):
                        v = parser.match.group('value')
                        if v:
                            track.tags.title = v
                        # TODO title = '(HTOA)'
                    elif parser.re_search(r'^PERFORMER\s+"(?P<value>.*)"$'):
                        v = parser.match.group('value')
                        if v:
                            track.tags.artist = v
                    elif parser.re_search(r'^(?:COMPOSER|SONGWRITER|ARRANGER)\s+"(?P<value>.*)"$'):
                        v = parser.match.group('value')
                        if v:
                            track.tags.composer = v
                    elif parser.re_search(r'^MESSAGE\s+"(?P<value>.*)"$'):
                        v = parser.match.group('value')
                        if v:
                            track.tags.comment = v
                    # TODO PREGAP [00:00:00]
                    #   -- unless track 1 is (HTOA)
                    elif parser.re_search(r'^ISRC\s+"(?P<isrc>\S{12})?"$') or \
                        parser.re_search(r'^ISRC\s+(?P<isrc>\S{12})$'):
                        # CCOOOYYSSSSS
                        # Sets ISRC code of track (only for audio tracks).
                        # C: country code (upper case letters or digits)
                        # O: owner code (upper case letters or digits)
                        # Y: year (digits)
                        # S: serial number (digits) 
                        v = parser.match.group('isrc')
                        if v:  # and lang is CDTocFile.LanguageEnum.eng:
                            track.tags.isrc = v
                    elif parser.re_search(r'^FLAGS\s+(?P<value>.+)$'):
                        # http://www.goldenhawk.com/download/cdrwin.pdf
                        for flag in parser.match.group('value').split():
                            if flag == "DCP":
                                self.copy_permitted = True
                            elif flag == "4CH":
                                self.audio_channels = 4
                            elif flag == "PRE":
                                self.pre_emphasis = True
                            #elif flag == "SCMS":
                            #    # TODO Serial Copy Management System (not supported by all recorders)
                            #elif flag == "DATA":
                            #    # TODO Data track
                            else:
                                raise ValueError('Unsupported cue sheet track flag: %s' % (flag,))
                    elif parser.re_search(r'^DISC_ID\s+""$'):
                        pass  # dummy!
                    else:
                        parser.pushback(parser.line)
                        break
            elif parser.re_search(r'^\d+: syntax error$'):
                # cueconvert error
                pass
            else:
                raise ValueError('Unsupported cue sheet line: %s' % (parser.line,))
        self.tags.tracks = len(self.tracks)

    def create(self, indent='  ', file=None):
        if file is None:
            with self.open('w', encoding='utf-8') as file:
                return self.create(file=file)
        cur_file = None
        for cmd, tag_enum in (
                ('PERFORMER', MediaTagEnum.artist),
                ('TITLE', MediaTagEnum.title),
                ('COMPOSER', MediaTagEnum.composer),
                #('SONGWRITER', MediaTagEnum.composer),
                #('ARRANGER', MediaTagEnum.composer),
                ('CATALOG', MediaTagEnum.barcode),
                ('REM GENRE', MediaTagEnum.genre),
                ('REM DATE', MediaTagEnum.date),
                ('REM DISCID', MediaTagEnum.cddb_discid),
                ('REM ACCURATERIPID', MediaTagEnum.musicbrainz_discid),
                ('REM DISCNUMBER', MediaTagEnum.disk),
                ('REM TOTALDISCS', MediaTagEnum.disks),
                ):
            v = self.tags[tag_enum]
            if v is not None:
                print('%s "%s"' % (cmd, v), file=file)
        for track_no, track in enumerate(self.tracks, start=1):
            if cur_file is not track.file:
                cur_file = track.file
                print('FILE "%s" %s' % (cur_file.name, cur_file.format.value), file=file)
            print('%sTRACK %02d %s' % (indent * 1, track_no, track.type.value), file=file)
            for cmd, tag_enum in (
                    ('PERFORMER', MediaTagEnum.artist),
                    ('TITLE', MediaTagEnum.title),
                    ('COMPOSER', MediaTagEnum.composer),
                    #('SONGWRITER', MediaTagEnum.composer),
                    #('ARRANGER', MediaTagEnum.composer),
                    # TODO PREGAP [00:00:00]
                    #   -- unless track 1 is (HTOA)
                    ('ISRC', MediaTagEnum.isrc),
                    ):
                if track.tags.contains(tag_enum, strict=True):
                    v = track.tags[tag_enum]
                    if v is not None:
                        print('%s%s "%s"' % (indent * 2, cmd, v), file=file)
            flags = []
            if track.copy_permitted:
                flags.append('DCP')
            if track.audio_channels == 4:
                flags.append('4CH')
            if track.pre_emphasis:
                flags.append('PRE')
            if flags:
                print('%sFLAGS %s' % (indent * 2, ' '.join(flags)))
            for index_key, index in sorted(track.indexes.items()):
                print('%sINDEX %02d %s' % (indent * 2, index.number, index.position), file=file)

    def prepare_from_toc(self, toc,
            file=None,
            file_format='BINARY',
            track_type='AUDIO'):
        self.files = []
        self.tracks = []
        #self.tags = AlbumTags()
        file_format = CDDACueSheetFile.FileFormatEnum(file_format)
        track_type = CDDACueSheetFile.TrackTypeEnum(track_type)
        if file:
            assert type(file) is str
            file = CDDACueSheetFile.File(
                    name=file,
                    format=file_format,
                    )
            self.files.append(file)
        for toc_track in toc.tracks:
            track = CDDACueSheetFile.Track(
                    cue_file=self,
                    type=track_type,
                    file=file)
            track.begin = toc_track.begin
            self.tracks.append(track)

    @property
    def sectors(self):  # leadout
        sectors = self._sectors
        if sectors is None:
            assert len(self.files) == 1
            bin_file = BinaryFile(os.path.join(
                os.path.dirname(self.file_name),
                self.files[0].name))
            size = bin_file.getsize()
            assert (size % CDDA_BYTES_PER_SECTOR) == 0
            sectors = size // CDDA_BYTES_PER_SECTOR
        return sectors

    @property
    def discid(self):
        import libdiscid
        discid = libdiscid.put(
                1, len(self.tracks),
                self.sectors + self.pregap,
                [track.begin.frames + self.pregap for track in self.tracks])
        return discid

    def getMusicBrainzDiscId(self):
        return self.discid.id

    def getFreeDbDiscId(self):
        return self.discid.freedb_id

# }}}

CDTocFile._build_extension_to_class_map()
CDDACueSheetFile._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
