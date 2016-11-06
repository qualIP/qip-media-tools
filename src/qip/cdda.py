
__all__ = [
        'CDDACueSheetFile',
        'CDToc',
        'CDTocFile',
        ]

import enum
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
from .snd import *

# class MSF {{{

class MSF(object):
    '''mm:ss:ff (minute-second-frame) format'''

    def __init__(self, value):
        if isinstance(value, int):
            frames = value
        elif isinstance(value, MSF):
            frames = value.frames
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
        if not isinstance(other, MSF):
            return NotImplemented
        return MSF(self.frames + other.frames)

    def __sub__(self, other):
        if not isinstance(other, MSF):
            return NotImplemented
        return MSF(self.frames - other.frames)

# }}}

# class CDToc {{{

class CDToc(object):

    class Track(object):
        def __init__(self, begin=None, length=None, copy_permitted=False, pre_emphasis=False, audio_channels=2):
            self.begin = MSF(begin) if begin is not None else None
            self.length = MSF(length) if length is not None else None
            assert isinstance(copy_permitted, bool)
            self.copy_permitted = bool(copy_permitted)
            assert isinstance(pre_emphasis, bool)
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
            track = CDToc.Track(*args, **kwargs)
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

    catalog_id = None
    session_type = None
    files = None
    tracks = None

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
        def __init__(self, mode, sub_channel_mode=None, copy_permitted=False, pre_emphasis=False, audio_channels=2, isrc_code=None):
            self.mode = CDTocFile.TrackModeEnum(mode)
            self.sub_channel_mode = CDTocFile.TrackSubChannelModeEnum(sub_channel_mode) if sub_channel_mode is not None else None
            assert isrc_code is None or isinstance(isrc_code, bool)
            self.isrc_code = str(isrc_code) if isrc_code is not None else None
            self.datas = []
            super().__init__(
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
        self.parse(content)
        return content

    def parse_CD_TEXT(self, parser):
        while True:
            assert parser.advance()
            parser.line = parser.line.strip()
            if not parser.line:
                pass
            elif parser.re_search(r'LANGUAGE_MAP\s+\{$'):
                while True:
                    assert parser.advance()
                    parser.line = parser.line.strip()
                    if not parser.line:
                        pass
                    elif parser.re_search(r'(\d+)\s*:\s*(\d+)$'):
                        pass
                    elif parser.line == '}':
                        break
                    else:
                        raise ValueError('Unsupported toc line: %s' % (parser.line,))
            elif parser.re_search(r'LANGUAGE\s+(\d+)\s+\{$'):
                while True:
                    assert parser.advance()
                    parser.line = parser.line.strip()
                    if not parser.line:
                        pass
                    elif parser.re_search(r'TITLE\s+"([^"]+)"$'):
                        pass
                    elif parser.re_search(r'PERFORMER\s+"([^"]+)"$'):
                        pass
                    elif parser.re_search(r'SIZE_INFO\s+{((?:\s*\d+,)*)(?:(\s*\d+)\s*\})?$'):
                        size_info = parser.line
                        while parser.line[-1] != '}' and parser.advance():
                            parser.line = parser.line.strip()
                            size_info += parser.line
                        assert size_info[-1] == '}'
                    elif parser.line == '}':
                        break
                    else:
                        raise ValueError('Unsupported toc line: %s' % (parser.line,))
            elif parser.line == '}':
                break

    def parse(self, content):
        self.catalog_id = None
        self.session_type = None
        self.files = []
        self.tracks = []
        from .parser import lines_parser
        parser = lines_parser(content.splitlines())
        cur_file = None
        cur_track = None
        while parser.advance():
            parser.line = parser.line.strip()
            if not parser.line:
                pass
            elif parser.re_search(r'^//'):
                pass
            elif parser.re_search(r'^CATALOG\s+"(?P<catalog_id>\d{13})"$'):
                assert self.catalog_id is None
                self.catalog_id = int(parser.match.group('catalog_id'))
            elif parser.re_search(r'^(?P<session_type>CD_DA|CD_ROM|CD_ROM_XA)$'):
                assert self.session_type is None
                self.session_type = CDTocFile.SessionTypeEnum(parser.match.group('session_type'))
            elif parser.re_search(r'^CD_TEXT\s+\{$'):
                self.parse_CD_TEXT(parser)
            elif parser.re_search(r'^TRACK\s+(?P<mode>\S+)(?:\s+(?P<sub_channel_mode>\S+))?$'):
                track = CDTocFile.Track(
                        mode=parser.match.group('mode'),
                        sub_channel_mode=parser.match.group('sub_channel_mode'),
                        )
                self.add_track(track)
                while parser.advance():
                    parser.line = parser.line.strip()
                    if not parser.line:
                        pass
                    elif parser.re_search(r'^//'):
                        pass
                    elif parser.re_search(r'^(?P<no>NO\s+)?COPY$'):
                        track.copy_permitted = parser.match.group('no') is None
                    elif parser.re_search(r'^(?P<no>NO\s+)?PRE_EMPHASIS$'):
                        track.pre_emphasis = parser.match.group('no') is None
                    elif parser.re_search(r'^TWO_CHANNEL_AUDIO$'):
                        track.audio_channels = 2
                    elif parser.re_search(r'^FOUR_CHANNEL_AUDIO$'):
                        track.audio_channels = 4
                    elif parser.re_search(r'^ISRC\s+"(?P<isrc_code>\S{12})"$'):
                        # CCOOOYYSSSSS
                        # Sets ISRC code of track (only for audio tracks).
                        # C: country code (upper case letters or digits)
                        # O: owner code (upper case letters or digits)
                        # Y: year (digits)
                        # S: serial number (digits) 
                        track.isrc_code = parser.match.group('isrc_code')
                    elif parser.re_search(r'^(?:FILE|AUDIOFILE)\s+"(?P<filename>[^"]+)"\s+(?P<start>0|\d\d:\d\d:\d\d)(?:\s+(?P<length>0|\d\d:\d\d:\d\d))?$'):
                        filename = parser.match.group('filename')
                        for file in self.files:
                            if file.name == filename:
                                break
                        else:
                            file = CDTocFile.File(name=filename)
                            self.files.append(file)
                        data = CDTocFile.TrackAudioData(
                                file=file,
                                start=parser.match.group('start'),
                                length=parser.match.group('length'),
                                )
                        track.datas.append(data)
                    elif parser.re_search(r'^CD_TEXT\s+\{$'):
                        self.parse_CD_TEXT(parser)
                    else:
                        parser.pushback(parser.line)
                        break
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
            else:
                raise ValueError('Unsupported toc line: %s' % (parser.line,))
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
            track = CDToc.CDTocFile(*args, **kwargs)
        self.tracks.append(track)
        return track

    def create(self, indent='  ', include_defaults=False, file=None):
        if file is None:
            with self.open('w') as file:
                return self.create(file=file)
        if self.catalog_id:
            print('CATALOG "%s"' % (self.catalog_id,), file=file)
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

    files = None
    tracks = None
    _sectors = None
    tags = None

    pregap = 150

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

        cue_file = None  # CDDACueSheetFile
        type = None  # CDDACueSheetFile.TrackTypeEnum
        file = None  # CDDACueSheetFile.File
        indexes = None  # [CDDACueSheetFile.Index]
        _length = None  # MSF

        @property
        def tags(self):
            track_no = self.track_no
            tags = self.cue_file.tags.tracks_tags[track_no]
            tags.track_no = track_no
            return tags

        def __init__(self, cue_file, type, file):
            self.cue_file = cue_file
            self.type = CDDACueSheetFile.TrackTypeEnum(type)
            assert file and isinstance(file, CDDACueSheetFile.File)
            self.file = file
            self.indexes = {}
            super().__init__()
            # self.tags.track_no = self.track_no  # TODO make dynamic?!?

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
        def track_no(self):
            idx = self.cue_file.tracks.index(self)
            return idx + 1

        @property
        def next_track(self):
            idx = self.cue_file.tracks.index(self)
            try:
                return self.cue_file.tracks[idx + 1]
            except IndexError:
                return None

        @property
        def end(self):
            length = self._length
            if length is not None:
                return self.begin + length
            next_track = self.next_track
            if next_track:
                return next_track.begin
            else:
                return MSF(self.cue_file.sectors)

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
        self.parse(content)
        return content

    def parse(self, content):
        self.files = []
        #self.tags = AlbumTags()
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
            elif parser.re_search(r'^TITLE\s+"(?P<value>.+)"$'):
                self.tags.title = parser.match.group('value')
            elif parser.re_search(r'^PERFORMER\s+"(?P<value>.+)"$'):
                self.tags.artist = parser.match.group('value')
            elif parser.re_search(r'^SONGWRITER\s+"(?P<value>.+)"$'):
                self.tags.composer = parser.match.group('value')
            elif parser.re_search(r'^CATALOG\s+"(?P<value>.+)"$'):
                self.tags.barcode = parser.match.group('value')
            elif parser.re_search(r'^REM GENRE\s+"(?P<value>.+)"$'):
                self.tags.genre = parser.match.group('value')
            elif parser.re_search(r'^REM DATE\s+"(?P<value>.+)"$'):
                self.tags.date = parser.match.group('value')
            elif parser.re_search(r'^REM DISCID\s+"(?P<value>.+)"$'):
                self.tags.cddb_discid = parser.match.group('value')
            elif parser.re_search(r'^REM ACCURATERIPID\s+"(?P<value>.+)"$'):
                self.tags.musicbrainz_discid = parser.match.group('value')
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
                    elif parser.re_search(r'^TITLE\s+"(?P<value>.+)"$'):
                        track.tags.title = parser.match.group('value')
                        # TODO title = '(HTOA)'
                    elif parser.re_search(r'^PERFORMER\s+"(?P<value>.+)"$'):
                        track.tags.artist = parser.match.group('value')
                    elif parser.re_search(r'^SONGWRITER\s+"(?P<value>.+)"$'):
                        track.tags.composer = parser.match.group('value')
                    # TODO PREGAP [00:00:00]
                    #   -- unless track 1 is (HTOA)
                    # TODO ISRC
                    # TODO FLAGS [PRE] [DCP]
                    else:
                        parser.pushback(parser.line)
                        break
            else:
                raise ValueError('Unsupported cue sheet line: %s' % (parser.line,))
        self.tags.tracks = len(self.tracks)

    def create(self, indent='  ', file=None):
        if file is None:
            with self.open('w') as file:
                return self.create(file=file)
        cur_file = None
        for cmd, tag_enum in (
                ('PERFORMER', SoundTagEnum.artist),
                ('TITLE', SoundTagEnum.title),
                ('SONGWRITER', SoundTagEnum.composer),
                ('CATALOG', SoundTagEnum.barcode),
                ('REM GENRE', SoundTagEnum.genre),
                ('REM DATE', SoundTagEnum.date),
                ('REM DISCID', SoundTagEnum.cddb_discid),
                ('REM ACCURATERIPID', SoundTagEnum.musicbrainz_discid),
                ('REM DISCNUMBER', SoundTagEnum.disk),
                ('REM TOTALDISCS', SoundTagEnum.disks),
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
                    ('PERFORMER', SoundTagEnum.artist),
                    ('TITLE', SoundTagEnum.title),
                    ('SONGWRITER', SoundTagEnum.composer),
                    # TODO PREGAP [00:00:00]
                    #   -- unless track 1 is (HTOA)
                    # TODO ISRC
                    # TODO FLAGS [PRE] [DCP]
                    ):
                if track.tags.contains(tag_enum, strict=True):
                    v = track.tags[tag_enum]
                    if v is not None:
                        print('%s%s "%s"' % (indent * 2, cmd, v), file=file)
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

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
