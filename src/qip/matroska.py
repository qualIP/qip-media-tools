# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'MatroskaFile',
    'MatroskaChaptersFile',
    'MkvFile',
    'WebmFile',
    'MkaFile',
    'mkvextract',
    'mkvpropedit',
)

# https://matroska.org/technical/specs/tagging/index.html
# https://www.webmproject.org/docs/container/
# http://wiki.webmproject.org/webm-metadata/global-metadata

from pathlib import Path
import collections
import contextlib
import copy
import functools
import io
import logging
import re
import xml.etree.ElementTree as ET
log = logging.getLogger(__name__)

from .exec import Executable
from .ffmpeg import ffmpeg
from .file import XmlFile
from .img import ImageFile, PngFile
from .mm import MediaTagEnum, MediaFile, BinaryMediaFile, SoundFile, MovieFile, taged, AlbumTags, ContentType, Chapters, parse_time_duration
from .utils import KwVarsObject, byte_decode


class MatroskaTagTarget(KwVarsObject):

    TargetType = None
    TrackUID = None

    def __init__(self, *,
                 TargetTypeValue,
                 TargetType=None,
                 TrackUID=0,
                 **kwargs):
        self.TargetTypeValue = TargetTypeValue
        if TargetType is not None:
            self.TargetType = TargetType
        if TrackUID is not None:
            self.TrackUID = TrackUID
        super().__init__(**kwargs)

    def apply_default_TargetTypes(self, default_TargetTypes):
        if self.TargetType is None and self.TrackUID == 0:
            newTargetType = default_TargetTypes.get(self.TargetTypeValue, None)
            if newTargetType is not None:
                self.TargetType = newTargetType
                return True
        return False


class MatroskaTagSimple(KwVarsObject):

    String = None
    Binary = None
    TagLanguage = None
    TagLanguageIETF = None

    def __init__(self, *,
                 Target,
                 Name,
                 String=None,
                 Binary=None,
                 TagLanguage=None,
                 TagLanguageIETF=None,
                 **kwargs):
        self.Target = Target
        self.Name = Name
        if String is not None:
            self.String = String
        if Binary is not None:
            self.Binary = Binary
        if TagLanguage is not None:
            self.TagLanguage = TagLanguage
        if TagLanguageIETF is not None:
            self.TagLanguageIETF = TagLanguageIETF
        super().__init__(**kwargs)

    def apply_default_TargetTypes(self, default_TargetTypes):
        return self.Target.apply_default_TargetTypes(default_TargetTypes)


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
    TagInfo(None, None, 'LANGUAGE', 'language'),  # SPECIAL
    TagInfo(70, 'COLLECTION', 'TITLE', 'grouping'),
    # XXXJST CONFLICT TagInfo(70, 'COLLECTION', 'TITLE', 'tvshow'),
    # XXXJST CONFLICT TagInfo(60, 'SEASON', 'PART_NUMBER', 'season'),
    # XXXJST CONFLICT TagInfo(50, 'EPISODE', 'PART_NUMBER', 'episode'),
    TagInfo(50, None, 'TOTAL_PARTS', 'parts'),
    TagInfo(40, None, 'PART_NUMBER', 'part'),
    TagInfo(40, None, 'TITLE', 'parttitle'),
    #TagInfo(None, None, '3d-plane', 'object_3d_plane'),
    TagInfo(None, None, '3D-PLANE', 'object_3d_plane'),
    # XXXJST CONFLICT TagInfo(None, None, 'TODO','albumartist'),
    TagInfo(None, None, 'ARTIST', 'artist'),  # CONFLICT
    # XXXJST CONFLICT TagInfo(None, None, 'TODO', 'albumtitle'),
    TagInfo(None, None, 'TITLE', 'title'),  # CONFLICT, also a property
    TagInfo(None, None, 'SUBTITLE', 'subtitle'),
    TagInfo(None, None, 'COMPOSER', 'composer'),
    TagInfo(None, None, 'PERFORMER', 'performer'),
    TagInfo(None, None, 'PUBLISHER', 'publisher'),
    TagInfo(None, None, 'ORIGINAL/ARTIST', 'originalartist'),
    TagInfo(None, None, 'DATE_RELEASED', 'date'),
    #TagInfo(None, None, 'TODO', 'country'),
    TagInfo(None, None, 'RECORDING_LOCATION', 'recording_location'),
    TagInfo(None, None, 'DATE_RECORDED', 'recording_date'),
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
    #TagInfo(None, None, 'TODO', 'isbn'),
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


class MatroskaChaptersFile(XmlFile):
    """A chapters file in matroska XML format"""

    chapters = None

    Timestamp = ffmpeg.Timestamp

    def __init__(self, *args, **kwargs):
        self.chapters = Chapters()
        super().__init__(*args, **kwargs)

    XML_VALUE_ELEMENTS = set((
        'ChapterTimeStart',
        'ChapterTimeEnd',
        'ChapterUID',
        'ChapterFlagHidden',
        'ChapterFlagEnabled',
        'ChapterString',
        'ChapterLanguage',
    ))

    def load(self, *, add_pre_gap=True, fix=True, return_raw_xml=False):
        chapters_out = self.read()
        if fix:
            chapters_out = self.fix_chapters_out(chapters_out)
        if return_raw_xml:
            return chapters_out
        chapters_xml = ET.parse(io.StringIO(byte_decode(chapters_out)))
        self.chapters = Chapters.from_mkv_xml(chapters_xml, add_pre_gap=add_pre_gap)

    @classmethod
    def fix_chapters_out(cls, chapters_out):
        from .ffmpeg import ffmpeg
        chapters_xml = ET.parse(io.StringIO(byte_decode(chapters_out)))
        chapters_root = chapters_xml.getroot()
        for eEditionEntry in chapters_root.findall('EditionEntry'):
            for chapter_no, eChapterAtom in enumerate(eEditionEntry.findall('ChapterAtom'), start=1):
                e = eChapterAtom.find('ChapterTimeStart')
                v = ffmpeg.Timestamp(e.text)
                if v != 0.0:
                    # In case initial frame is a I frame to be displayed after
                    # subqequent P or B frames, the start time will be
                    # incorrect.
                    log.warning('Fixing first chapter start time %s to 0', v)
                    if False:
                        # mkvpropedit doesn't like unknown elements
                        e.tag = 'original_ChapterTimeStart'
                        e = ET.SubElement(eChapterAtom, 'ChapterTimeStart')
                    e.text = str(ffmpeg.Timestamp(0))
                    chapters_xml_io = io.StringIO()
                    cls.write_xml(self=None, xml=chapters_xml, file=chapters_xml_io)
                    chapters_out = chapters_xml_io.getvalue()
                break
        return chapters_out

    def create(self, file=None):
        self.write_xml(self.chapters.to_mkv_xml(), file=file)

    @classmethod
    def NamedTemporaryFile(cls, *, suffix=None, **kwargs):
        if suffix is None:
            suffix = '.chapters.xml'
        return super().NamedTemporaryFile(suffix=suffix, **kwargs)


class MatroskaFile(BinaryMediaFile):

    @property
    def tag_writer(self):
        return taged

    XML_VALUE_ELEMENTS = set((
        'Binary',
        'Name',
        'String',
        'TagLanguage',
        'TagLanguageIETF',
        'TargetType',
        'TargetTypeValue',
        'TrackUID',
    ))

    # <Tags>
    #   <Tag>
    #     <Targets>
    #       <TrackUID>1</TrackUID>
    #       <TargetType>MOVIE</TargetType>
    #       <TargetTypeValue>50</TargetTypeValue>
    #     </Targets>
    #     <Simple>
    #       <Name>BPS</Name>
    #       <TagLanguageIETF>-CA-x-ca</TagLanguageIETF>
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
        log.debug('get_matroska_tag_map for file_type %r', file_type)
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
                TagInfo(30, None, 'ACTOR', 'performer'),
            ]
        if file_type in ('musicvideo',):
            default_TargetTypes.update({
                50: 'CONCERT',
            })
            tag_map += [
                TagInfo(60, None, 'TOTAL_PARTS', 'disks'),
                TagInfo(50, None, 'PART_NUMBER', 'disk'),
                TagInfo(50, None, 'TOTAL_PARTS', 'parts'),
                TagInfo(40, None, 'PART_NUMBER', 'part'),
            ]
        if file_type in ('movie', 'oldmovie'):
            default_TargetTypes.update({
                #60: 'SEQUEL',
                50: 'MOVIE',
                40: 'PART',
            })
            tag_map += [
                #TagInfo(70, None, 'TOTAL_PARTS', 'seriesparts'),
                #TagInfo(60, 'SEQUEL', 'PART_NUMBER', 'seriespart'),
                #TagInfo(60, 'SEQUEL', 'TITLE', 'seriestitle'),
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
                TagInfo(50, None, 'TOTAL_PARTS', 'parts'),
                TagInfo(40, None, 'PART_NUMBER', 'part'),
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
                    'performer',
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
        with XmlFile.NamedTemporaryFile(suffix='.tags.xml') as tmp_tags_xml_file:
            cmd = [
                'mkvextract',
                self,
                'tags',
                tmp_tags_xml_file,
            ]
            dbg_exec_cmd(cmd)
            # write -> read
            # tmp_tags_xml_file.flush()
            # tmp_tags_xml_file.seek(0)
            # https://mkvtoolnix.download/doc/mkvextract.html
            # If no tags are found in the file, the output file is not created.
            if tmp_tags_xml_file.exists() and tmp_tags_xml_file.getsize() > 0:
                tags_xml = ET.parse(tmp_tags_xml_file.fp)
            else:
                tags_xml = self.create_empty_tags_xml()
        return tags_xml

    def set_tags_xml(self, tags_xml):
        from qip.exec import do_exec_cmd
        with XmlFile.NamedTemporaryFile(suffix='.tags.xml') as tmp_tags_xml_file:
            tmp_tags_xml_file.write_xml(tags_xml)
            # write -> read
            tmp_tags_xml_file.flush()
            tmp_tags_xml_file.seek(0)
            #if log.isEnabledFor(logging.DEBUG):
            #    with open(tmp_tags_xml_file, 'r') as fd:
            #        log.debug('Tags XML: %s', fd.read())
            mkvpropedit(
                self,
                actions=mkvpropedit.ActionArgs(
                    tags=f'all:{tmp_tags_xml_file}',
                ),
            )

    @classmethod
    def iter_matroska_tags(cls, tags_xml):
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
        vTagLanguageIETF = None
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
            elif eSub.tag == 'TagLanguageIETF':
                assert vTagLanguageIETF is None
                vTagLanguageIETF = eSub.text  # TODO isolang(eSub.text)
            elif eSub.tag == 'DefaultLanguage':
                # Deprecated; Was always 1.
                pass
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
                TagLanguageIETF=vTagLanguageIETF,
            )
        for eSub in lSubSimples:
            yield from cls._parse_tags_xml_Simple(eSub, d_target, parent_Simple_names=parent_Simple_names)

    def create_tags_list(self):
        from .exec import do_exec_cmd
        default_TargetTypeValue, default_TargetTypes, tag_map = self.get_matroska_tag_map()
        tags_list = None

        tags_to_set = set(self.tags.keys())

        for tag in tags_to_set:
            if tag in (
                    MediaTagEnum.type,  # Mostly implicit from tag map choices
            ):
                continue
            tag = tag.name
            value = self.tags[tag]

            for tag_info in tag_map:
                if tag_info.tag != tag:
                    continue
                log.debug(f'tag_info = %r', tag_info)
                break
            else:
                if value is None:
                    continue
                raise NotImplementedError(f'Tag not supported in Matroska w/ type {self.deduce_type()}: {tag} = {value}')

            if tag_info.TargetTypeValue is None:
                tag_info = tag_info._replace(
                    TargetTypeValue=default_TargetTypeValue or 50)
            if tag_info.TargetType is None:
                tag_info = tag_info._replace(
                    TargetType=default_TargetTypes.get(tag_info.TargetTypeValue, None))

            if value is None:
                mkv_value = ()
            elif type(value) is tuple:
                mkv_value = tuple(str(e) for e in value)
            else:
                mkv_value = str(value)
            if tag == 'title':
                mkvpropedit(
                    self,
                    actions=mkvpropedit.ActionArgs(
                        '--edit', 'info',
                        '--set', 'title=%s' % (value,),
                    ))
            elif tag == 'language':
                # https://www.matroska.org/technical/specs/index.html#languages
                from qip.isolang import isolang
                mkvpropedit(
                    self,
                    actions=mkvpropedit.ActionArgs(
                        '--edit', 'track:@1',  # TODO
                        '--set', 'language=%s' % (isolang(value or 'und').iso639_2,),
                    ))
                continue
            if tags_list is None:
                tags_xml = self.get_tags_xml()
                tags_list = self.iter_matroska_tags(tags_xml)
                if default_TargetTypes:
                    for d_tag in tags_list:
                        d_tag.apply_default_TargetTypes(default_TargetTypes)
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
        tags_xml = ET.ElementTree(ET.fromstring(
            '''<?xml version="1.0"?>
            <!-- <!DOCTYPE Tags SYSTEM "matroskatags.dtd"> -->
            <Tags />
            '''))
        return tags_xml

    @classmethod
    def create_tags_xml_from_list(cls, tags_list):
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
                    eTagLanguageIETF = ET.SubElement(eSimple, 'TagLanguageIETF')
                    eTagLanguageIETF.text = isolang(d_tag.TagLanguageIETF).iso639_2
                # if d_tag.TagLanguageIETF is not None:
                #     eTagLanguageIETF = ET.SubElement(eSimple, 'TagLanguageIETF')
                #     eTagLanguageIETF.text = str(d_tag.TagLanguageIETF)
        return tags_xml

    def load_tags(self, file_type=None):
        tags = AlbumTags()
        tags_xml = self.get_tags_xml()
        tags_list = self.iter_matroska_tags(tags_xml)
        tags_list = list(tags_list)

        tags.type = file_type
        if tags.type is None:
            for d_tag in tags_list:
                if (d_tag.Target.TrackUID, d_tag.Target.TargetTypeValue) == (0, 50):
                    try:
                        tags.type = {
                            'ALBUM': 'normal',
                            'MOVIE': 'movie',
                            'CONCERT': 'musicvideo',
                            'EPISODE': 'tvshow',
                            # TODO booklet
                            # TODO ringtone
                        }[d_tag.Target.TargetType]
                    except KeyError:
                        log.debug('Deduced type is %r based on %r', tags.type, d_tag)
                        pass
                    else:
                        break
        if tags.contenttype is None:
            for d_tag in tags_list:
                if (d_tag.Target.TrackUID, d_tag.Target.TargetTypeValue, d_tag.Name) == (0, 50, 'CONTENT_TYPE'):
                    tags.contenttype = d_tag.String
                    log.debug('Deduced contenttype is %r based on %r', tags.contenttype, d_tag)
                    break
        if (tags.type, tags.contenttype) == ('normal', ContentType.audiobook):
            tags.type = 'audiobook'
        if tags.type is None:
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
                    tags.type = 'tvshow'
                    log.debug('Deduced type is %r based on %r + %r', tags.type, d_tag_collection_title, d_tag_episode)
                    break
        if tags.type is None:
            tags.type = self.deduce_type()

        default_TargetTypeValue, default_TargetTypes, tag_map = self.get_matroska_tag_map(file_type=tags.type)
        for d_tag in tags_list:
            log.debug('d_tag = %r', d_tag)
            d_tag.Name = {
                '3d-plane': '3D-PLANE',
            }.get(d_tag.Name, d_tag.Name)
            if False:
                target_tags = tags if d_tag.Target.TrackUID == 0 else tags.tracks_tags[d_tag.Target.TrackUID]
            else:
                if d_tag.Target.TrackUID != 0:
                    target_tags = tags.tracks_tags[d_tag.Target.TrackUID]
                elif False and d_tag.Target.TargetTypeValue is not None and d_tag.Target.TargetTypeValue <= default_TargetTypeValue:
                    target_tags = tags.tracks_tags[1]
                else:
                    target_tags = tags
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
                        'MAJOR_BRAND',  # TODO -- "isom"
                        'MINOR_VERSION',  # TODO -- "512"
                        'COMPATIBLE_BRANDS',  # TODO -- "isomiso2mp41"
                        'HANDLER_NAME',  # TODO -- "VideoHandler"
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
                log.debug('%s = %r', mapped_tag, d_tag.String)
                target_tags.set_tag(mapped_tag, d_tag.String)
        return tags

    def load_chapters(self, *, fix=True, return_raw_xml=False, **kwargs):
        from qip.perf import perfcontext
        with perfcontext('Extract chapters w/ mkvextract'):
            chapters_out = mkvextract('chapters', self,
                                      encoding='utf-8-sig').out
        if fix:
            chapters_out = MatroskaChaptersFile.fix_chapters_out(chapters_out)
        if return_raw_xml:
            return chapters_out
        chapters_xml = ET.parse(io.StringIO(byte_decode(chapters_out)))
        chaps = Chapters.from_mkv_xml(chapters_xml, **kwargs)
        return chaps

    def write_chapters(self, chaps,
                       show_progress_bar=None, progress_bar_max=None, progress_bar_title=None,
                       log=False):
        with MatroskaChaptersFile.NamedTemporaryFile() as chapters_file:
            if isinstance(chaps, ET.ElementTree):
                # XML tree
                chapters_file.write_xml(chaps)
                # write -> read
                chapters_file.flush()
                chapters_file.seek(0)
                return
            if isinstance(chaps, str) and chaps.startswith('<'):
                # XML string -> Chapters
                # This allows for verification and standardization
                chaps = Chapters.from_mkv_xml(chaps)
            chapters_file.chapters = chaps
            chapters_file.create()
            # write -> read
            chapters_file.flush()
            chapters_file.seek(0)
            from qip.perf import perfcontext
            with perfcontext('Write chapters w/ mkvpropedit', log=log):
                mkvpropedit(
                    self,
                    actions=mkvpropedit.ActionArgs(
                        '--chapters', chapters_file,
                    ))

    @classmethod
    def prep_picture(cls, src_picture, *,
            yes=False,  # unused
            ipod_compat=True,  # unused
            keep_picture_file_name=None,
            ):
        from .exec import do_exec_cmd

        if not src_picture:
            return None
        src_picture = Path(src_picture)

        return cls._lru_prep_picture(src_picture,
                                     keep_picture_file_name)

    @classmethod
    @functools.lru_cache()
    def _lru_prep_picture(cls,
                          src_picture : Path,
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
                ffmpeg_args += ['-an', str(picture)]
                ffmpeg(*ffmpeg_args)
            src_picture = picture

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
        with contextlib.ExitStack() as exit_stack:

            if show_progress_bar:
                if progress_bar_max is None:
                    progress_bar_max = expected_duration

            log.info('Writing %s...', output_file)

            ffmpeg_cmd = []

            ffmpeg_input_cmd = []
            ffmpeg_output_cmd = []
            if yes:
                ffmpeg_cmd += ['-y']
            ffmpeg_cmd += ['-stats']
            # ffmpeg_output_cmd += ['-vn']
            ffmpeg_format = 'matroska'
            bCopied = False

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
                    log.debug('Files:\n' +
                              re.sub(r'^', '    ', concat_file.read(), flags=re.MULTILINE))
                    concat_file.seek(0)
                ffmpeg_input_cmd += [
                    '-f', 'concat', '-safe', '0', '-i', concat_file,
                ]
            else:
                ffmpeg_input_cmd += ffmpeg.input_args(inputfiles[0])
            ffmpeg_output_cmd += [
                '-map', '0:a',
            ]

            if not picture_added and picture is not None:
                ffmpeg_input_cmd += ffmpeg.input_args(picture, attach=True)
                ffmpeg_output_cmd += [
                    '-metadata:s:1', 'mimetype={}'.format(picture.mime_type),
                    '-metadata:s:1', f'filename=cover{picture.file_name.suffix}',
                ]
                picture_added = True

            ffmpeg_output_cmd += [
                '-codec', 'copy',
            ]

            ffmpeg_output_cmd += [
                '-map_metadata', -1,
                '-map_chapters', -1,
            ]

            ffmpeg_output_cmd += [
                '-f', ffmpeg_format,
                output_file,
            ]

            out = ffmpeg(*(ffmpeg_cmd + ffmpeg_input_cmd + ffmpeg_output_cmd),
                         show_progress_bar=show_progress_bar,
                         progress_bar_max=progress_bar_max,
                         progress_bar_title=progress_bar_title or f'Encode {self} w/ ffmpeg',
                         )
            out = out.out
            out_time = None
            # {{{
            out = clean_cmd_output(out)
            parser = lines_parser(out.split('\n'))
            while parser.advance():
                parser.line = parser.line.strip()
                if parser.re_search(r'^size= *(?P<out_size>\S+) time= *(?P<out_time>\S+) bitrate= *(?P<out_bitrate>\S+)(?: speed= *(?P<out_speed>\S+))?$'):
                    # size=  223575kB time=07:51:52.35 bitrate=  64.7kbits/s
                    # size= 3571189kB time=30:47:24.86 bitrate= 263.9kbits/s speed= 634x
                    out_time = parse_time_duration(parser.match.group('out_time'))
                elif parser.re_search(r' time= *(?P<out_time>\S+) bitrate='):
                    log.warning('TODO: %s', parser.line)
                    pass
                else:
                    pass  # TODO
            # }}}
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
                                           show_progress_bar=show_progress_bar,
                                           progress_bar_max=progress_bar_max,
                                           log=True)
                chapters_added = True

            if not tags_added and output_file.tags is not None:
                log.info('Adding tags...')
                tags = copy.copy(output_file.tags)
                tags.picture = None  # Already added
                output_file.write_tags(tags=tags, run_func=do_exec_cmd)
                tags_added = True

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

class Mkvextract(Executable):

    name = 'mkvextract'

mkvextract = Mkvextract()

class Mkvpropedit(Executable):

    name = 'mkvpropedit'

    OptionArgs = Executable.Args

    ActionArgs = Executable.Args

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_gnu_getopt

    def build_cmd(self, file, *, options=None, actions=None):
        # mkvpropedit [options] <file> <actions>
        args = []
        if options is not None:
            options = Mkvpropedit.OptionArgs.new_from(options)
            args += list(options.args) + self.kwargs_to_cmdargs(**options.keywords)
        if file is not None:
            args.append(file)
        if actions is not None:
            actions = Mkvpropedit.ActionArgs.new_from(actions)
            args += list(actions.args) + self.kwargs_to_cmdargs(**actions.keywords)
        return super().build_cmd(*args)

mkvpropedit = Mkvpropedit()
