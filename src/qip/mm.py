
__all__ = (
    'Chapter',
    'Chapters',
    'MediaFile',
    'FrameRate',
)

from fractions import Fraction
import io
import logging
import xml.etree.ElementTree as ET
log = logging.getLogger(__name__)

from .file import BinaryFile
from .ffmpeg import ffmpeg, ffprobe


class Chapter(object):

    def __init__(self, start, end, *,
                 uid=None, hidden=False, enabled=True, title=None, no=None):
        self.start = ffmpeg.Timestamp(start)
        self.end = ffmpeg.Timestamp(end)
        self.uid = uid
        self.hidden = hidden
        self.enabled = enabled
        self.title = title
        self.no = no

    @classmethod
    def from_mkv_xml_ChapterAtom(cls, eChapterAtom, **kwargs):
        # <ChapterAtom>
        #   <ChapterUID>6524138974649683444</ChapterUID>
        uid = eChapterAtom.find('ChapterUID').text
        #   <ChapterTimeStart>00:00:00.000000000</ChapterTimeStart>
        start = eChapterAtom.find('ChapterTimeStart').text
        #   <ChapterFlagHidden>0</ChapterFlagHidden>
        hidden = {'0': False, '1': True}[eChapterAtom.find('ChapterFlagHidden').text]
        #   <ChapterFlagEnabled>1</ChapterFlagEnabled>
        enabled = {'0': False, '1': True}[eChapterAtom.find('ChapterFlagEnabled').text]
        #   <ChapterTimeEnd>00:07:36.522733333</ChapterTimeEnd>
        end = eChapterAtom.find('ChapterTimeEnd').text
        #   <ChapterDisplay>
        #     <ChapterString>Chapter 01</ChapterString>
        title = eChapterAtom.find('ChapterDisplay').find('ChapterString').text
        #     <ChapterLanguage>eng</ChapterLanguage>
        #   </ChapterDisplay>
        # </ChapterAtom>
        return cls(start=start, end=end,
                   uid=uid, hidden=hidden, enabled=enabled,
                   title=title, **kwargs)

    def __str__(self):
        s = ''
        if self.no is not None:
            s += '%d ' % (self.no,)
        s += '[%s..%s]' % (self.start, self.end)
        if self.title is not None:
            s += ' %r' % (self.title,)
        return s


class Chapters(object):

    def __init__(self, chapters=None, add_pre_gap=False):
        self.chapters = list(chapters or [])
        if self.chapters and add_pre_gap and self.chapters[0].start > 0:
            chap = Chapter(0, self.chapters[0].start, title='pre-gap', hidden=True)
            self.chapters.insert(0, chap)

    @classmethod
    def from_mkv_xml(cls, xml, **kwargs):
        if isinstance(xml, ET.ElementTree):
            pass
        elif isinstance(xml, str):
            if xml.startswith('<'):
                # XML string
                xml = ET.parse(io.StringIO(xml))
            else:
                # file name
                xml = ET.parse(xml)
        elif isinstance(xml, byte):
            # XML data/bytes
            xml = ET.parse(io.StringIO(byte_decode(xml)))
        elif getattr(xml, 'read', None) is not None:
            # io.IOBase or file-like object
            xml = ET.parse(xml)
        else:
            raise ValueError(xml)
        root = xml.getroot()

        eEditionEntry, = root.findall('EditionEntry')
        # TODO EditionFlagHidden ==? 0
        # TODO EditionFlagDefault ==? 1

        chapters = [
            Chapter.from_mkv_xml_ChapterAtom(eChapterAtom, no=chapter_no)
            for chapter_no, eChapterAtom in enumerate(eEditionEntry.findall('ChapterAtom'), start=1)]
        return cls(chapters, **kwargs)

    def __iter__(self):
        return iter(self.chapters)


class MediaFile(BinaryFile):

    def __init__(self, file_name, *args, **kwargs):
        super().__init__(file_name=file_name, *args, **kwargs)

    def test_integrity(self):
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        log.info('Testing %s...' % (self.file_name,))
        ffmpeg_args = [
                '-i', self.file_name,
                '-vn',
                '-f', 'null',
                '-y',
                '/dev/null',
                ]
        d = ffmpeg(*ffmpeg_args)
        out = d.out
        out = byte_decode(out)
        out = io.IncrementalNewlineDecoder(decoder=None, translate=True).decode(out, final=True)
        m = re.search(r'Error while decoding stream.*', out)
        if m:
            # raise ValueError("%s: %s" % (self.file_name, m.group(0)))
            log.error("%s: %s", self.file_name, m.group(0))
            return False
        return True

    def extract_ffprobe_json(self, **kwargs):
        from .exec import clean_cmd_output
        from .parser import lines_parser
        from . import json

        kwargs.setdefault('show_streams', True)
        kwargs.setdefault('show_format', True)
        kwargs.setdefault('show_chapters', True)
        kwargs.setdefault('show_error', True)

        d = ffprobe(i=self.file_name,
                    #threads=0,
                    v='info',
                    print_format='json',
                    **kwargs)
        out = d.out
        out = clean_cmd_output(out)
        parser = lines_parser(out.split('\n'))
        ffprobe_dict = None
        while parser.advance():
            if parser.line == '{':
                parser.pushback(parser.line)
                ffprobe_dict = json.loads('\n'.join(parser.lines_iter))
                break
            parser.line = parser.line.strip()
            if parser.line == '':
                pass
            else:
                #log.debug('TODO: %s', parser.line)
                pass
        if ffprobe_dict:
            if log.isEnabledFor(logging.DEBUG):
                import pprint
                log.debug('ffprobe_dict:\n%s', pprint.pformat(ffprobe_dict))
            return ffprobe_dict
        raise ValueError('No json found in output of ffprobe')

    def extract_mediainfo_dict(self,
                               *args, **kwargs):
        from .mediainfo import mediainfo
        d = mediainfo(self.file_name, *args, **kwargs)
        out = d.out
        mediainfo_dict = mediainfo.parse(out)
        if mediainfo_dict:
            if log.isEnabledFor(logging.DEBUG):
                import pprint
                log.debug('mediainfo_dict:\n%s', pprint.pformat(mediainfo_dict))
            return mediainfo_dict
        raise ValueError('Nothing found in output of mediainfo')


class FrameRate(Fraction):

    def __new__(cls, numerator=0, denominator=None, **kwargs):
        if denominator is None:
            if isinstance(numerator, str):
                try:
                    numerator = int(numerator)
                except ValueError:
                    try:
                        numerator = float(numerator)
                    except ValueError:
                        pass
            if isinstance(numerator, (int, float)):
                if numerator == 23.976:
                    numerator, denominator = 24000, 1001
                elif numerator == 29.970:
                    numerator, denominator = 30000, 1001
                elif numerator in (24.0, 30.0):
                    pass
                else:
                    raise NotImplementedError(numerator)
        return super().__new__(cls, numerator, denominator, **kwargs)

    def round_common(self):
        for framerate in common_framerates:
            if framerate * 0.998 < self <= framerate:
                return framerate
        raise ValueError(framerate)


common_framerates = sorted([
    FrameRate(24000, 1001),
    FrameRate(24000, 1000),
    FrameRate(30000, 1001),
    FrameRate(30000, 1000),
    ])

MediaFile._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
