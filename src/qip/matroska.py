
__all__ = (
    'MatroskaFile',
    'MkvFile',
    'MkaFile',
)

# https://matroska.org/technical/specs/tagging/index.html
# https://www.webmproject.org/docs/container/
# http://wiki.webmproject.org/webm-metadata/global-metadata

import collections
import logging
log = logging.getLogger(__name__)

from .mm import MediaFile
from .snd import SoundFile, MovieFile, taged, AlbumTags

mkv_tag_map = {
    (50, 'EPISODE', 'PART_NUMBER'): 'episode',
    (50, None, 'ARTIST'): 'artist',
    (50, None, 'ARTIST/SORT_WITH'): 'sortartist',
    (50, None, 'ORIGNAL_MEDIA_TYPE'): 'mediatype',
    (50, None, 'CONTENT_TYPE'): 'contenttype',
    (50, None, 'DATE_RELEASED'): 'date',
    (50, None, 'ENCODER'): 'tool',
    (50, None, 'GENRE'): 'genre',
    (50, None, 'PART_NUMBER'): 'track',
    (50, None, 'TITLE'): 'title',
    (50, None, 'TITLE/SORT_WITH'): 'sorttitle',
    (50, None, 'TOTAL_PARTS'): 'tracks',
    (60, 'SEASON', 'PART_NUMBER'): 'season',
    (70, 'COLLECTION', 'TITLE'): 'tvshow',
    (70, 'COLLECTION', 'TITLE/SORT_WITH'): 'sorttvshow',
    }

mkv_tag_rev_map = {}
for _k, _v in mkv_tag_map.items():
    mkv_tag_rev_map[_v] = _k


class MatroskaTagTarget(collections.namedtuple(
        'MatroskaTagTarget',
        (
            'TrackUID',
            'TargetTypeValue',
            'TargetType',
        ),
        # defaults=(
        #     None,  # TargetType
        # ),
        )):

    __slots__ = ()

    def __new__(cls, *,
            TargetType=None,
            **kwargs):
        return super().__new__(
                cls,
                TargetType=TargetType,
                **kwargs)


class MatroskaTagSimple(collections.namedtuple(
        'MatroskaTagSimple',
        (
            'Target',
            'Name',
            'String',
            'Binary',
            'TagLanguage',
        ),
        # defaults=(
        #     None,  # String
        #     None,  # Binary
        #     None,  # TagLanguage
        # ),
        )):

    __slots__ = ()

    def __new__(cls, *,
            String=None, Binary=None, TagLanguage=None,
            **kwargs):
        return super().__new__(
                cls,
                String=String,
                Binary=Binary,
                TagLanguage=TagLanguage,
                **kwargs)


class MatroskaFile(MediaFile):

    @property
    def tag_writer(self):
        return taged

    # <Tags>
    #   <Tag>
    #     <Targets>
    #       <TrackUID>1</TrackUID>
    #       <TargetType>MOVIE</TargetType>
    #       <TargetTypeValue>50</TargetTypeValue>
    #     </Targets>
    #     <Simple>
    #       <Name>BPS</Name>
    #       <TagLanguage>eng</TagLanguage>
    #       <String>4203293</String>
    #       <Binary>...</Binary>
    #       <Simple>
    #         ...
    #       </Simple>
    #       ...
    #     </Simple>
    #     ...
    #   </Tag>
    #   ...
    # </Tags>

    def get_tags_xml(self):
        from qip.exec import dbg_exec_cmd
        from qip.file import TempFile
        import xml.etree.ElementTree as ET
        with TempFile.mkstemp(text=True, suffix='.tags.xml') as tmp_tags_xml_file:
            cmd = [
                'mkvextract',
                self.file_name,
                'tags',
                tmp_tags_xml_file.file_name,
            ]
            dbg_exec_cmd(cmd)
            # https://mkvtoolnix.download/doc/mkvextract.html
            # If no tags are found in the file, the output file is not created.
            if tmp_tags_xml_file.exists():
                tags_xml = ET.parse(tmp_tags_xml_file.file_name)
            else:
                tags_xml = self.create_empty_tags_xml()
        return tags_xml

    def set_tags_xml(self, tags_xml):
        from qip.exec import do_exec_cmd
        from qip.file import TempFile
        with TempFile.mkstemp(text=True, suffix='.tags.xml') as tmp_tags_xml_file:
            tags_xml.write(tmp_tags_xml_file.file_name,
                #encoding='unicode',
                xml_declaration=True,
                )
            #if log.isEnabledFor(logging.DEBUG):
            #    with open(tmp_tags_xml_file.file_name, 'r') as fd:
            #        log.debug('Tags XML: %s', fd.read())
            cmd = [
                'mkvpropedit',
                '--tags', 'all:%s' % (tmp_tags_xml_file.file_name),
                self.file_name,
            ]
            do_exec_cmd(cmd)

    @classmethod
    def parse_tags_xml(cls, tags_xml):
        root = tags_xml.getroot()
        for eSub in root:
            if eSub.tag == 'Tag':
                yield from cls._parse_tags_xml_Tag(eSub)
            else:
                raise NotImplementedError('Unsupported Matroska XML tag %r' % (eSub.tag,))

    @classmethod
    def _parse_tags_xml_Tag(cls, eTag):
        d_target = None
        lSubSimples = []
        for eSub in eTag:
            if eSub.tag == 'Targets':
                assert d_target is None
                d_target = cls._parse_tags_xml_Target(eSub)
            elif eSub.tag == 'Simple':
                lSubSimples.append(eSub)
            else:
                raise NotImplementedError('Unsupported Matroska XML tag %r' % (eSub.tag,))
        for eSimple in lSubSimples:
            yield from cls._parse_tags_xml_Simple(eSimple, d_target=d_target)

    @classmethod
    def _parse_tags_xml_Target(cls, eTarget):
        vTrackUID = None
        vTargetTypeValue = None
        vTargetType = None
        for eSub in eTarget:
            if eSub.tag == 'TrackUID':
                assert vTrackUID is None
                vTrackUID = 0 if eSub.text is None else int(eSub.text)
            elif eSub.tag == 'TargetTypeValue':
                assert vTargetTypeValue is None
                vTargetTypeValue = 50 if eSub.text is None else int(eSub.text)
            elif eSub.tag == 'TargetType':
                assert vTargetType is None
                vTargetType = eSub.text or ''
            else:
                raise NotImplementedError('Unsupported Matroska XML tag %r' % (eSub.tag,))
        if vTrackUID is None:
            vTrackUID = 0
        if vTargetTypeValue is None:
            vTargetTypeValue = {
                'COLLECTION': 70,
                'EDITION': 60,
                'ISSUE': 60,
                'VOLUME': 60,
                'OPUS': 60,
                'SEASON': 60,
                'SEQUEL': 60,
                'ALBUM': 50,
                'OPERA': 50,
                'CONCERT': 50,
                'MOVIE': 50,
                'EPISODE': 50,
                'PART': 40,
                'SESSION': 40,
                'TRACK': 30,
                'SONG': 30,
                'CHAPTER': 30,
                'SUBTRACK': 20,
                # 'PART': 20,
                'MOVEMENT': 20,
                'SCENE': 20,
                'SHOT': 10,
            }.get(vTargetType, 50)
        vTargetType = vTargetType or None
        return MatroskaTagTarget(
            TrackUID=vTrackUID,
            TargetTypeValue=vTargetTypeValue,
            TargetType=vTargetType,  # Can be None
        )

    @classmethod
    def _parse_tags_xml_Simple(cls, eSimple, d_target, parent_Simple_names=()):
        from qip.isolang import isolang
        vName = None
        vString = None
        vBinary = None
        vTagLanguage = None
        lSubSimples = []
        for eSub in eSimple:
            if eSub.tag == 'Name':
                assert vName is None
                vName = eSub.text or ''
                assert vName
            elif eSub.tag == 'String':
                assert vString is None
                vString = eSub.text or ''
            elif eSub.tag == 'Binary':
                assert vBinary is None
                vBinary = eSub.text or ''
            elif eSub.tag == 'TagLanguage':
                assert vTagLanguage is None
                vTagLanguage = isolang(eSub.text)
            elif eSub.tag == 'Simple':
                lSubSimples.append(eSub)
            else:
                raise NotImplementedError('Unsupported Matroska XML tag %r' % (eSub.tag,))
        assert vName is not None
        parent_Simple_names = parent_Simple_names + (vName,)
        if vString is not None or vBinary is not None:
            yield MatroskaTagSimple(
                Target=d_target,
                Name='/'.join(parent_Simple_names),
                String=vString,
                Binary=vBinary,
                TagLanguage=vTagLanguage,
            )
        for eSub in lSubSimples:
            yield from cls._parse_tags_xml_Simple(eSub, d_target, parent_Simple_names=parent_Simple_names)

    @classmethod
    def create_empty_tags_xml(cls):
        import xml.etree.ElementTree as ET
        tags_xml = ET.ElementTree(ET.fromstring(
            '''<?xml version="1.0"?>
            <!-- <!DOCTYPE Tags SYSTEM "matroskatags.dtd"> -->
            <Tags />
            '''))
        return tags_xml

    @classmethod
    def create_tags_xml(cls, tags_list):
        import xml.etree.ElementTree as ET
        tags_xml = cls.create_empty_tags_xml()
        root = tags_xml.getroot()
        d_tags_per_target = collections.defaultdict(list)
        for d_tag in tags_list:
            d_tags_per_target[d_tag.Target].append(d_tag)
        for d_target, tags_list in d_tags_per_target.items():
            eTag = ET.SubElement(root, 'Tag')
            eTargets = ET.SubElement(eTag, 'Targets')
            eTrackUID = ET.SubElement(eTargets, 'TrackUID')
            eTrackUID.text = str(d_target.TrackUID)
            eTargetTypeValue = ET.SubElement(eTargets, 'TargetTypeValue')
            eTargetTypeValue.text = str(d_target.TargetTypeValue)
            if d_target.TargetType is not None:
                eTargetType = ET.SubElement(eTargets, 'TargetType')
                eTargetType.text = str(d_target.TargetType)
            for d_tag in tags_list:
                eSimple = eTag  # parent
                assert d_tag.Name
                tag_names = d_tag.Name.split('/')
                for tag_idx, name in enumerate(tag_names):
                    eParent = eSimple
                    if tag_idx != len(tag_names) - 1:
                        # Nested tag...
                        # NOTE: WebM does not support nested tags
                        # (https://www.webmproject.org/docs/container/);
                        # mkvpropedit will silently remove them
                        eSimple = eParent.find('./Simple[Name="%s"]' % (name,))
                        if eSimple:
                            continue
                    eSimple = ET.SubElement(eParent, 'Simple')
                    eName = ET.SubElement(eSimple, 'Name')
                    eName.text = name
                assert eSimple is not eTag
                if d_tag.String is not None:
                    eString = ET.SubElement(eSimple, 'String')
                    eString.text = d_tag.String
                if d_tag.Binary is not None:
                    eBinary = ET.SubElement(eSimple, 'Binary')
                    eBinary.text = d_tag.Binary
                if d_tag.TagLanguage is not None:
                    eTagLanguage = ET.SubElement(eSimple, 'TagLanguage')
                    eTagLanguage.text = str(d_tag.TagLanguage)
        return tags_xml

    def load_tags(self):
        import xml.etree.ElementTree as ET
        tags = AlbumTags()
        tags_xml = self.get_tags_xml()
        tags_list = self.parse_tags_xml(tags_xml)
        for d_tag in tags_list:
            log.debug('d_tag = %r', d_tag)
            target_tags = tags if d_tag.Target.TrackUID == 0 else tags.tracks_tags[d_tag.Target.TrackUID]
            if d_tag.Name in (
                    'BPS',  # TODO
                    'DURATION',  # TODO
                    'NUMBER_OF_FRAMES',  # TODO
                    'NUMBER_OF_BYTES',  # TODO
                    'SOURCE_ID',  # TODO
                    '_STATISTICS_WRITING_APP',  # TODO
                    '_STATISTICS_WRITING_DATE_UTC',  # TODO
                    '_STATISTICS_TAGS',  # TODO
                    ):
                continue
            if d_tag.String is not None:
                try:
                    mapped_tag = mkv_tag_map[(d_tag.Target.TargetTypeValue, d_tag.Target.TargetType, d_tag.Name)]
                except KeyError as e:
                    #log.debug('e: %s', e)
                    raise
                    # mapped_tag = mkv_tag_map[(d_tag.Target.TargetTypeValue, None, d_tag.Name)]
                old_value = tags[mapped_tag] if mapped_tag in ('episode',) else None
                if old_value is not None:
                    if not isinstance(old_value, tuple):
                        old_value = (old_value,)
                    if not isinstance(d_tag.String, tuple):
                        d_tag.String = (d_tag.String,)
                    d_tag.String = old_value + d_tag.String
                #log.debug('%s = %r', mapped_tag, d_tag.String)
                target_tags.set_tag(mapped_tag, d_tag.String)
        return tags


class MkvFile(MatroskaFile, MovieFile):

    _common_extensions = (
        '.mkv',
    )

class MkaFile(MatroskaFile, SoundFile):

    _common_extensions = (
        '.mka',
    )

MatroskaFile._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
