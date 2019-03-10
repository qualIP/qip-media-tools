
__all__ = (
    'MatroskaFile',
    'MkvFile',
    'WebmFile',
    'MkaFile',
)

# https://matroska.org/technical/specs/tagging/index.html
# https://www.webmproject.org/docs/container/
# http://wiki.webmproject.org/webm-metadata/global-metadata

import collections
import logging
log = logging.getLogger(__name__)

from .mm import MediaFile, SoundFile, MovieFile, taged, AlbumTags, ContentType


class MatroskaTagTarget(collections.namedtuple(
        'MatroskaTagTarget',
        (
            'TargetTypeValue',
            'TargetType',
            'TrackUID',
        ),
        # defaults=(
        #     None,  # TargetType
        #     None,  # TrackUID
        # ),
        )):

    __slots__ = ()

    def __new__(cls, *,
            TargetType=None,
            TrackUID=0,
            **kwargs):
        return super().__new__(
                cls,
                TargetType=TargetType,
                TrackUID=TrackUID,
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


class TagInfo(collections.namedtuple(
        'TagInfo',
        (
            'TargetTypeValue',
            'TargetType',
            'Name',
            'tag',
        ),
        )):

    __slots__ = ()

    def __new__(cls,
                *args,
                **kwargs):
        return super().__new__(
                cls,
                *args,
                **kwargs)

default_tag_map = (
    TagInfo(70, 'COLLECTION', 'TITLE', 'grouping'),
    # XXXJST CONFLICT TagInfo(70, 'COLLECTION', 'TITLE', 'tvshow'),
    # XXXJST CONFLICT TagInfo(60, 'SEASON', 'PART_NUMBER', 'season'),
    # XXXJST CONFLICT TagInfo(50, 'EPISODE', 'PART_NUMBER', 'episode'),
    TagInfo(50, None, 'TOTAL_PARTS', 'parts'),
    TagInfo(40, None, 'PART_NUMBER', 'part'),
    TagInfo(40, None, 'TITLE', 'parttitle'),
    # XXXJST CONFLICT TagInfo(None, None, 'TODO','albumartist'),
    TagInfo(None, None, 'ARTIST', 'artist'),  # CONFLICT
    # XXXJST CONFLICT TagInfo(None, None, 'TODO', 'albumtitle'),
    TagInfo(None, None, 'TITLE', 'title'),  # CONFLCT, also a property
    TagInfo(None, None, 'SUBTITLE', 'subtitle'),
    TagInfo(None, None, 'COMPOSER', 'composer'),
    TagInfo(None, None, 'PUBLISHER', 'publisher'),
    TagInfo(None, None, 'ORIGINAL/ARTIST', 'originalartist'),
    TagInfo(None, None, 'DATE_RELEASED', 'date'),
    #TagInfo(None, None, 'TODO', 'country'),
    # XXXJST CONFLICT TagInfo(None, None, 'PART_NUMBER', 'disk'),
    # XXXJST CONFLICT TagInfo(None, None, 'TOTAL_PARTS', 'disks'),
    # XXXJST CONFLICT TagInfo(None, None, 'PART_NUMBER', 'track'),
    # XXXJST CONFLICT TagInfo(None, None, 'TOTAL_PARTS', 'tracks'),
    #TagInfo(None, None, 'TODO', 'tvnetwork'),
    TagInfo(None, None, 'DESCRIPTION', 'description'),
    TagInfo(None, None, 'SUMMARY', 'longdescription'),
    #TagInfo(None, None, 'TODO', 'compilation'),
    #TagInfo(None, None, 'TODO', 'podcast'),
    #TagInfo(None, None, 'TODO', 'hdvideo'),
    TagInfo(None, None, 'GENRE', 'genre'),
    #TagInfo(None, None, 'TODO', 'type'),
    TagInfo(None, None, 'ORIGINAL_MEDIA_TYPE', 'mediatype'),
    TagInfo(None, None, 'CONTENT_TYPE', 'contenttype'),
    #TagInfo(None, None, 'TODO', 'category'),
    #TagInfo(None, None, 'TODO', 'language'),
    TagInfo(None, None, 'COPYRIGHT', 'copyright'),
    TagInfo(None, None, 'ENCODED_BY', 'encodedby'),
    TagInfo(None, None, 'ENCODER', 'tool'),
    #TagInfo(None, None, 'TODO', 'picture'),
    TagInfo(None, None, 'BPM', 'tempo'),
    #TagInfo(None, None, 'TODO', 'gapless'),
    #TagInfo(None, None, 'TODO', 'itunesgaplessinfo'),
    TagInfo(None, None, 'COMMENT', 'comment'),
    TagInfo(None, None, 'LYRICS', 'lyrics'),
    TagInfo(None, None, 'PURCHASE_OWNER', 'owner'),
    TagInfo(None, None, 'DATE_PURCHASED', 'purchasedate'),
    #TagInfo(None, None, 'TODO', 'itunesaccount'),
    #TagInfo(None, None, 'TODO', 'xid'),
    #TagInfo(None, None, 'TODO', 'cddb_discid'),
    #TagInfo(None, None, 'TODO', 'musicbrainz_discid'),
    #TagInfo(None, None, 'TODO', 'musicbrainz_releaseid'),
    #TagInfo(None, None, 'TODO', 'musicbrainz_cdstubid'),
    #TagInfo(None, None, 'TODO', 'accuraterip_discid'),
    TagInfo(None, None, 'ISRC', 'isrc'),
    TagInfo(None, None, 'BARCODE', 'barcode'),
    #TagInfo(None, None, 'TODO', 'asin'),
    TagInfo(None, None, 'LAW_RATING', 'contentrating'),
    #TagInfo(None, None, 'TODO', 'itunescountryid'),
    #TagInfo(None, None, 'TODO', 'itunesartistid'),
    #TagInfo(None, None, 'TODO', 'itunescomposerid'),
    #TagInfo(None, None, 'TODO', 'itunesepisodeid'),
    #TagInfo(None, None, 'TODO', 'itunesgenreid'),
    #TagInfo(None, None, 'TODO', 'itunescatalogid'),
    #TagInfo(None, None, 'TODO', 'itunesplaylistid'),
)


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

    def get_matroska_tag_map(self, *, file_type=None):

        tag_map = []
        default_TargetTypes = {}
        default_TargetTypeValue = 50

        if file_type is None:
            file_type = self.deduce_type()
        log.debug('file_type = %r', file_type)
        if file_type in ('normal', 'audiobook'):
            default_TargetTypes.update({
                60: 'EDITION',
                50: 'ALBUM',
                30: 'SONG',
            })
            default_TargetTypeValue = 30
            tag_map += [
                TagInfo(60, None, 'TOTAL_PARTS', 'disks'),
                TagInfo(50, None, 'PART_NUMBER', 'disk'),
                TagInfo(50, None, 'ARTIST', 'albumartist'),
                TagInfo(50, None, 'TITLE', 'albumtitle'),
                TagInfo(50, None, 'ORIGINAL_MEDIA_TYPE', 'mediatype'),
                TagInfo(50, None, 'CONTENT_TYPE', 'contenttype'),
                TagInfo(50, None, 'TOTAL_PARTS', 'tracks'),
                TagInfo(30, None, 'PART_NUMBER', 'track'),
            ]
        if file_type in ('audiobook',):
            tag_map += [
                TagInfo(30, None, 'LEAD_PERFORMER', 'composer'),
            ]
        if file_type in ('musicvideo',):
            default_TargetTypes.update({
                50: 'CONCERT',
            })
            tag_map += [
            ]
        if file_type in ('movie', 'oldmovie'):
            default_TargetTypes.update({
                50: 'MOVIE',
                40: 'PART',
            })
            tag_map += [
                TagInfo(60, None, 'TOTAL_PARTS', 'disks'),
                TagInfo(50, None, 'PART_NUMBER', 'disk'),
                TagInfo(50, None, 'TOTAL_PARTS', 'parts'),
                TagInfo(40, None, 'PART_NUMBER', 'part'),
            ]
        if file_type in ('tvshow',):
            default_TargetTypes.update({
                70: 'COLLECTION',
                60: 'SEASON',
                50: 'EPISODE',
            })
            tag_map += [
                TagInfo(70, None, 'TITLE', 'tvshow'),
                TagInfo(70, None, 'TOTAL_PARTS', 'seasons'),
                TagInfo(60, None, 'PART_NUMBER', 'season'),
                TagInfo(60, None, 'TOTAL_PARTS', 'episodes'),
                TagInfo(50, None, 'PART_NUMBER', 'episode'),
            ]
        if file_type in ('booklet',):
            default_TargetTypes.update({
            })
            tag_map += [
            ]
        if file_type in ('ringtone',):
            default_TargetTypes.update({
            })
            tag_map += [
            ]

        tag_map.extend(default_tag_map)

        for tag_info in tag_map:
            if tag_info.tag in (
                    'grouping',
                    'albumartist',
                    'albumtitle',
                    'artist',
                    'title',
                    'subtitle',
                    'partitle',
                    'composer',
                    'tvshow',
            ):
                sort_tag_info = tag_info._replace(
                    Name=tag_info.Name + '/SORT_WITH',
                    tag='sort' + tag_info.tag,
                )
                tag_map.append(sort_tag_info)

        return default_TargetTypeValue, default_TargetTypes, tag_map

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
    def iter_matroska_tags(cls, tags_xml, default_TargetTypes=None):
        root = tags_xml.getroot()
        for eSub in root:
            if eSub.tag == 'Tag':
                yield from cls._parse_tags_xml_Tag(eSub, default_TargetTypes=default_TargetTypes)
            else:
                raise NotImplementedError('Unsupported Matroska XML tag %r' % (eSub.tag,))

    @classmethod
    def _parse_tags_xml_Tag(cls, eTag, default_TargetTypes=None):
        d_target = None
        lSubSimples = []
        for eSub in eTag:
            if eSub.tag == 'Targets':
                assert d_target is None
                d_target = cls._parse_tags_xml_Target(eSub, default_TargetTypes=default_TargetTypes)
            elif eSub.tag == 'Simple':
                lSubSimples.append(eSub)
            else:
                raise NotImplementedError('Unsupported Matroska XML tag %r' % (eSub.tag,))
        for eSimple in lSubSimples:
            yield from cls._parse_tags_xml_Simple(eSimple, d_target=d_target)

    @classmethod
    def _parse_tags_xml_Target(cls, eTarget, default_TargetTypes=None):
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
        if vTargetType is None and vTrackUID == 0 and default_TargetTypes:
            vTargetType = default_TargetTypes.get(vTargetTypeValue, None)
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
                vName = {
                    'ORIGNAL_MEDIA_TYPE': 'ORIGINAL_MEDIA_TYPE',
                }.get(vName, vName)
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

    def create_tags_list(self):
        from .exec import do_exec_cmd
        default_TargetTypeValue, default_TargetTypes, tag_map = self.get_matroska_tag_map()
        tags_list = None
        for tag, value in self.tags.items():
            tag = tag.name

            for tag_info in tag_map:
                if tag_info.tag != tag:
                    continue
                log.debug(f'tag_info = %r', tag_info)
                break
            else:
                raise NotImplementedError(f'Tag not supported in Matroska: {tag}')

            if tag_info.TargetTypeValue is None:
                tag_info = tag_info._replace(
                    TargetTypeValue=default_TargetTypeValue or 50)
            if tag_info.TargetType is None:
                tag_info = tag_info._replace(
                    TargetType=default_TargetTypes.get(tag_info.TargetTypeValue, None))

            if type(value) is tuple:
                mkv_value = tuple(str(e) for e in value)
            else:
                mkv_value = str(value)
            if tag == 'title':
                cmd = [
                    'mkvpropedit',
                    '--edit', 'info',
                    '--set', 'title=%s' % (value,),
                    self.file_name,
                ]
                do_exec_cmd(cmd)
            if tags_list is None:
                tags_xml = self.get_tags_xml()
                tags_list = self.iter_matroska_tags(tags_xml, default_TargetTypes=default_TargetTypes)
                # tags_list = list(tags_list)
            d_target = MatroskaTagTarget(
                TrackUID=0,
                TargetTypeValue=tag_info.TargetTypeValue,
                TargetType=tag_info.TargetType,
            )
            # Remove any existing similar tag
            tags_list = [d_tag
                         for d_tag in tags_list
                         if d_tag.Target != d_target or d_tag.Name != tag_info.Name]
            tup_mkv_value = mkv_value if type(mkv_value) is tuple else (mkv_value,)
            for one_mkv_value in tup_mkv_value:
                d_tag = MatroskaTagSimple(Target=d_target,
                                                       Name=tag_info.Name,
                                                       String=one_mkv_value,
                                                       )
                if log.isEnabledFor(logging.DEBUG):
                    log.debug('Add %r', d_tag)
                tags_list.append(d_tag)
        return tags_list

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
    def create_tags_xml_from_list(cls, tags_list):
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
        tags_list = self.iter_matroska_tags(tags_xml)
        tags_list = list(tags_list)
        file_type = None
        if file_type is None:
            for d_tag in tags_list:
                if (d_tag.Target.TrackUID, d_tag.Target.TargetTypeValue, d_tag.Name) == (0, 50, 'CONTENT_TYPE'):
                    contenttype = str(ContentType(d_tag.Value))
                    if 'Music Video' in contenttype \
                            or 'Concert' in contenttype:
                        file_type = 'musicvideo'
                        log.debug('Deduced type is %r based on %r', file_type, d_tag)
                        break
        if file_type is None:
            d_tag_collection_title = None
            d_tag_episode = None
            for d_tag in tags_list:
                if (d_tag.Target.TrackUID, d_tag.Target.TargetTypeValue, d_tag.Target.TargetType, d_tag.Name) == (0, 70, 'COLLECTION', 'TITLE'):
                    d_tag_collection_title = d_tag
                elif (d_tag.Target.TrackUID, d_tag.Target.TargetTypeValue, d_tag.Target.TargetType) == (0, 50, 'EPISODE'):
                    d_tag_episode = d_tag
                else:
                    continue
                if d_tag_collection_title and d_tag_episode:
                    file_type = 'tvshow'
                    log.debug('Deduced type is %r based on %r + %r', file_type, d_tag_collection_title, d_tag_episode)
                    break
        default_TargetTypeValue, default_TargetTypes, tag_map = self.get_matroska_tag_map(file_type=file_type)
        for d_tag in tags_list:
            log.debug('d_tag = %r', d_tag)
            target_tags = tags if d_tag.Target.TrackUID == 0 else tags.tracks_tags[d_tag.Target.TrackUID]
            for tag_info in tag_map:
                if tag_info.Name != d_tag.Name:
                    continue
                if tag_info.TargetTypeValue not in (None, d_tag.Target.TargetTypeValue):
                    continue
                if tag_info.TargetType not in (None, d_tag.Target.TargetType):
                    continue
                #log.debug(f'tag_info = %r', tag_info)
                mapped_tag = tag_info.tag
                break
            else:
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
                raise NotImplementedError(f'Matroska tag not supported: {d_tag.Name}')
            if d_tag.String is not None:
                old_value = tags[mapped_tag] if mapped_tag in ('episode',) else None
                if old_value is not None:
                    if not isinstance(old_value, tuple):
                        old_value = (old_value,)
                    if not isinstance(d_tag.String, tuple):
                        d_tag = d_tag._replace(String=(d_tag.String,))
                    d_tag = d_tag._replace(String=old_value + d_tag.String)
                #log.debug('%s = %r', mapped_tag, d_tag.String)
                target_tags.set_tag(mapped_tag, d_tag.String)
        return tags

class MkvFile(MatroskaFile, MovieFile):

    _common_extensions = (
        '.mkv',
    )

class WebmFile(MkvFile):

    _common_extensions = (
        '.webm',
    )

class MkaFile(MatroskaFile, SoundFile):

    _common_extensions = (
        '.mka',
    )

MatroskaFile._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
