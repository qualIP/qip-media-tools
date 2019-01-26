#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

import argparse
import decimal
import errno
import functools
import glob
import html
import logging
import mutagen
import os
import pexpect
import re
import reprlib
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
reprlib.aRepr.maxdict = 100

from qip import json
from qip.app import app
from qip.cmp import *
from qip.exec import *
from qip.file import *
from qip.parser import *
from qip.perf import perfcontext
from qip.snd import *
from qip.img import *
from qip.utils import byte_decode
import qip.snd

import mutagen.mp4
mutagen.mp4.MP4Tags._MP4Tags__atoms[b'idx'] = (
    mutagen.mp4.MP4Tags._MP4Tags__parse_text,
    mutagen.mp4.MP4Tags._MP4Tags__render_text,
)

# replace_html_entities {{{

def replace_html_entities(s):
    s = html.unescape(s)
    m = re.search(r'&\w+;', s)
    if m:
        raise ValueError('Unknown HTML entity: %s' % (m.group(0),))
    return s

# }}}

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='Tag Editor',
            contact='jst@qualipsoft.com',
            )

    in_tags = TrackTags()

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    pgroup.add_argument('--dry-run', '-n', dest='dry_run', action='store_true', help='dry-run mode')
    pgroup.add_argument('--yes', '-y', action='store_true', help='answer "yes" to all prompts')
    pgroup.add_argument('--save-temps', dest='save_temps', default=False, action='store_true', help='do not delete intermediate files')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

    pgroup = app.parser.add_argument_group('Actions')
    xgroup = pgroup.add_mutually_exclusive_group()
    pgroup.add_argument('--edit', dest='action', default='edit', action='store_const', const='edit', help='edit tags (default)')
    pgroup.add_argument('--list', dest='action', default=argparse.SUPPRESS, action='store_const', const='list', help='list tags')

    pgroup = app.parser.add_argument_group('Compatibility')
    pgroup.add_argument('--prep-picture', dest='prep_picture', action='store_true', help='prepare picture')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--ipod-compat', dest='ipod_compat', default=True, action='store_true', help='iPod compatibility (default)')
    xgroup.add_argument('--no-ipod-compat', dest='ipod_compat', default=argparse.SUPPRESS, action='store_false', help='iPod compatibility (disable)')

    pgroup = app.parser.add_argument_group('Tags')
    pgroup.add_argument('--title', '--song', '-s', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--albumtitle', '--album', '-A', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--artist', '-a', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--albumartist', '-R', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--genre', '-g', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--writer', '--composer', '-w', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--date', '--year', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--type', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--contenttype', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction, help='Content Type (%s)' % (', '.join((str(e) for e in qip.snd.ContentType)),))
    pgroup.add_argument('--disk', '--disc', dest='disk_slash_disks', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--track', dest='track_slash_tracks', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--picture', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--tvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--season', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--episode', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--language', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--country', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--compilation', '-K', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-artist', dest='sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-title', '--sort-song', dest='sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumartist', dest='sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumtitle', '--sort-album', dest='sortalbumtitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-composer', '--sort-writer', dest='sortcomposer', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-tvshow', dest='sorttvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--xid', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)

    app.parser.add_argument('files', nargs='*', default=None, help='sound files')

    app.parse_args()

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'edit'
    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)
    if app.args.logging_level <= logging.DEBUG:
        reprlib.aRepr.maxdict = 100

    for prog in (
            ):
        if not shutil.which(prog):
            raise Exception('%s: command not found' % (prog,))
    for prog in (
            ):
        if not shutil.which(prog):
            app.log.warning('%s: command not found; Functionality may be limited.', prog)

    if app.args.action == 'edit':
        # {{{

        if not app.args.files:
            raise Exception('No files provided')
        for file_name in app.args.files:
            with perfcontext('taged'):
                taged(file_name, in_tags)

        # }}}
    elif app.args.action == 'list':
        # {{{

        if not app.args.files:
            raise Exception('No files provided')
        for file_name in app.args.files:
            with perfcontext('list'):
                taglist(file_name)

        # }}}
    else:
        raise ValueError('Invalid action \'%s\'' % (app.args.action,))

def taged_mf_id3(file_name, mf, tags):
    # http://id3.org/Developer%20Information
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.debug('Old tags: %r', list(mf.tags.keys()))
    app.log.debug('Mod tags: %r', list(tags.keys()))
    for tag, value in tags.items():
        tag = tag.name
        if tag in ('track', 'tracks'):
            tag = 'track_slash_tracks'
            value = tags[tag]
        elif tag in ('disk', 'disks'):
            tag = 'disk_slash_disks'
            value = tags[tag]
        try:
            mapped_tag = qip.snd.tag_info['map'][tag]
            id3_tag = qip.snd.tag_info['tags'][mapped_tag]['id3v2_30_tag']
        except KeyError:
            raise NotImplementedError(tag)
        if id3_tag == 'TPE2':  # albumartist
            if mf.tags.pop('TXXX:QuodLibet::albumartist', None) is not None:
                app.log.verbose(' Removed %s (%s)', tag, 'TXXX:QuodLibet::albumartist')
        if value is None:
            if mf.tags.pop(id3_tag, None) is not None:
                app.log.verbose(' Removed %s (%s)', tag, id3_tag)
        else:
            mf.tags[id3_tag] = getattr(mutagen.id3, id3_tag)(encoding=mutagen.id3.Encoding.UTF8, text=str(value))
            app.log.verbose(' Set %s (%s): %r', tag, id3_tag, value)
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.debug('New tags: %r', list(mf.tags.keys()))
    return True

def taged_mf_MP4Tags(file_name, mf, tags):
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.debug('Old tags: %r', list(mf.tags.keys()))
    tags_to_set = set(tags.keys())
    #app.log.debug('tags %r, tags_to_set: %r', type(tags), tags_to_set)
    if SoundTagEnum.disk in tags_to_set:
        tags_to_set.discard(SoundTagEnum.disks)
    if SoundTagEnum.track in tags_to_set:
        tags_to_set.discard(SoundTagEnum.tracks)
    for tag in (
            SoundTagEnum.barcode,
            SoundTagEnum.isrc,
            SoundTagEnum.asin,
            SoundTagEnum.isrc,
            SoundTagEnum.musicbrainz_discid,
            SoundTagEnum.cddb_discid,
            SoundTagEnum.accuraterip_discid,
    ):
        if tag in tags_to_set:
            tags_to_set.remove(tag)
            tags_to_set.add(SoundTagEnum.xid)
    for tag in tags_to_set:
        if tag in (
                SoundTagEnum.musicbrainz_releaseid,
        ):
            continue
        tag = tag.name
        value = tags[tag]
        try:
            mapped_tag = qip.snd.tag_info['map'][tag]
            mp4_tag = qip.snd.tag_info['tags'][mapped_tag]['mp4v2_tag']
            mp4v2_data_type = qip.snd.tag_info['tags'][mapped_tag]['mp4v2_data_type']
        except KeyError:
            raise NotImplementedError(tag)
        if mp4_tag in 'xid':
            value = tags.xids or None
        if value is None:
            if mf.tags.pop(mp4_tag, None) is not None:
                app.log.verbose(' Removed %s (%s)', tag, mp4_tag)
        else:
            if mp4v2_data_type == 'utf-8':
                if mp4_tag == 'xid':
                    mp4_value = [str(v) for v in value]
                else:
                    mp4_value = str(value)
                    if mp4_tag.startswith('----:'):
                        # freeform tags are expected in bytes
                        mp4_value = mp4_value.encode('utf-8')
            elif mp4v2_data_type == 'bool8':
                mp4_value = 1 if value else 0
            elif mp4v2_data_type in ('int8', 'int16', 'int32', 'int64'):
                if mp4_tag == 'sfID':
                    # raise ValueError('value %r = %r -> %s' % (type(value), value, value))
                    mp4_value = [qip.snd.mp4_country_map[value]]
                else:
                    mp4_value = int(value)
            elif mp4v2_data_type in ('binary',):
                if mp4_tag == 'disk':  # disk
                    # arg must be a list of 1(or more) tuple of (track, total)
                    mp4_value = [(int(tags.disk), int(tags.disks or 0))]
                elif mp4_tag == 'trkn':  # track
                    # arg must be a list of 1(or more) tuple of (track, total)
                    mp4_value = [(int(tags.track), int(tags.tracks or 0))]
                else:
                    raise NotImplementedError((tag, mp4v2_data_type))
            elif mp4v2_data_type in ('picture',):
                assert mp4_tag == 'covr'
                mp4_value = []
                from qip.file import cache_url
                value = cache_url(str(value))
                if getattr(app.args, 'prep_picture', False):
                    from qip.m4a import M4aFile
                    m4a = M4aFile(file_name)
                    value = m4a.prep_picture(value)
                img_file = ImageFile(str(value))
                img_type = img_file.image_type
                if img_type is ImageType.jpg:
                    img_type = mutagen.mp4.MP4Cover.FORMAT_JPEG
                elif img_type is ImageType.png:
                    img_type = mutagen.mp4.MP4Cover.FORMAT_PNG
                else:
                    raise ValueError('Unsupported image type: %s' % (img_type,))
                with img_file.open('rb') as fp:
                    v = fp.read()
                    mp4_value.append(mutagen.mp4.MP4Cover(v, img_type))
            else:
                raise NotImplementedError(mp4v2_data_type)
            try:
                mf.tags[mp4_tag] = mp4_value
            except:
                if mp4_tag in ('covr',):
                    app.log.debug('ERROR! mf.tags[%r] = ...', mp4_tag)
                else:
                    app.log.debug('ERROR! mf.tags[%r] = %r', mp4_tag, mp4_value)
                raise
            if mp4_tag in ('covr',):
                app.log.verbose(' Set %s (%s)', tag, mp4_tag)
            else:
                app.log.verbose(' Set %s (%s): %r', tag, mp4_tag, mp4_value)
    if app.log.isEnabledFor(logging.DEBUG):
        app.log.debug('New tags: %r', list(mf.tags.keys()))
    return True

def taged_mf(file_name, mf, tags):
    if isinstance(mf.tags, mutagen.id3.ID3):
        return taged_mf_id3(file_name, mf, tags)
    if isinstance(mf.tags, mutagen.mp4.MP4Tags):
        return taged_mf_MP4Tags(file_name, mf, tags)
    raise NotImplementedError(mf.tags.__class__.__name__)

def find_Tag_element(root, *, TargetTypeValue, TargetType=None, TrackUID=0):
    TrackUID = str(TrackUID) if TrackUID is not None else '0'
    TargetTypeValue = str(TargetTypeValue) if TargetTypeValue is not None else '50'
    TargetType = str(TargetType) if TargetType is not None else None
    for eTag in root.findall('Tag'):
        eTargets = eTag.find('Targets')
        eTrackUID = eTargets.find('TrackUID')
        vTrackUID = eTrackUID.text if (eTrackUID is not None and eTrackUID.text is not None) else '0'
        if vTrackUID != TrackUID:
            continue
        eTargetTypeValue = eTargets.find('TargetTypeValue')
        vTargetTypeValue = eTargetTypeValue.text if (eTargetTypeValue is not None and eTargetTypeValue.text is not None) else '50'
        if vTargetTypeValue != TargetTypeValue:
            continue
        eTargetType = eTargets.find('TargetType')
        vTargetType = eTargetType.text if eTargetType is not None else '50'
        if vTargetType != TargetType:
            continue
        return eTag

def find_all_Simple_element(eTag, *, Name):
    Name = str(Name) if Name is not None else ''
    for eSimple in eTag.findall('Simple'):
        eName = eSimple.find('Name')
        vName = eName.text if eName is not None else ''
        if vName != Name:
            continue
        if app.log.isEnabledFor(logging.DEBUG):
            app.log.debug('Found eSimple with Name %r: %r', Name, ET.tostring(eSimple))
        yield eSimple

def find_Simple_element(eTag, *, Name):
    for eSimple in find_all_Simple_element(eTag, Name=Name):
        return eSimple

def clean_Tag_elements(root):
    for eTag in root.findall('Tag'):
        # Error: The XML tag file '...' contains an error: <Tag> is missing the <Simple> child.
        app.log.debug('eTag.find = %r', eTag.find('Simple'))
        gotValidSimpleTag = False
        for eSimple in eTag.findall('Simple'):
            # Error: The XML tag file '...' contains an error: <Simple> must contain either a <String> or a <Binary> child.
            if eSimple.find('String') is None and eSimple.find('Binary') is None:
                app.log.debug('remove <Simple> missing <String> or a <Binary> child. %r', ET.tostring(eSimple))
                eTag.remove(eSimple)
                continue
            gotValidSimpleTag = True
        if not gotValidSimpleTag:
            app.log.debug('remove <Tag> missing <Simple> child.')
            root.remove(eTag)
            continue
        eTargets = eTag.find('Targets')
        if eTargets is not None:
            eTargetTypeValue = eTargets.find('TargetTypeValue')
            if eTargetTypeValue is None:
                eTargetTypeValue = ET.SubElement(eTargets, 'TargetTypeValue')
                eTargetTypeValue.text = '50'

def taged_MKV(file_name, tags):
    # https://matroska.org/technical/specs/tagging/index.html
    with TempFile(file_name + '.tags.tmp.xml',
                  delete=not getattr(app.args, 'save_temps', False)) as tmp_tags_xml_file:
        tags_xml = None
        for tag, value in tags.items():
            tag = tag.name
            if False and tag == 'title':
                cmd = [
                    'mkvpropedit',
                    '--edit', 'info',
                    '--set', 'title=%s' % (value,),
                    file_name,
                ]
                do_exec_cmd(cmd)
            else:
                if type(value) is tuple:
                    mkv_value = tuple(str(e) for e in value)
                else:
                    mkv_value = str(value)
                TargetType = None
                TargetTypeValue = 50
                if tag == 'track':
                    mkv_tag = 'PART_NUMBER'
                elif tag == 'episode':
                    TargetType = 'EPISODE'
                    mkv_tag = 'PART_NUMBER'
                elif tag == 'tracks':
                    mkv_tag = 'TOTAL_PARTS'
                elif tag == 'date':
                    mkv_tag = 'DATE_RELEASED'
                elif tag == 'genre':
                    mkv_tag = 'GENRE'
                # albumartist should be 50/ARTIST while artist should be on individual tracks
                #elif tag == 'albumartist':
                #    mkv_tag = 'ARTIST'
                elif tag == 'artist':
                    mkv_tag = 'ARTIST'
                elif tag == 'tvshow':
                    TargetType = 'COLLECTION'
                    TargetTypeValue = 70
                    mkv_tag = 'TITLE'
                elif tag == 'season':
                    TargetType = 'SEASON'
                    TargetTypeValue = 60
                    mkv_tag = 'PART_NUMBER'
                elif tag == 'title':
                    mkv_tag = 'TITLE'
                elif tag == 'contenttype':
                    mkv_tag = 'CONTENT_TYPE'
                else:
                    raise NotImplementedError(tag)
                if tag == 'title':
                    cmd = [
                        'mkvpropedit',
                        '--edit', 'info',
                        '--set', 'title=%s' % (value,),
                        file_name,
                    ]
                    do_exec_cmd(cmd)
                if tags_xml is None:
                    cmd = [
                        'mkvextract',
                        file_name,
                        'tags',
                        tmp_tags_xml_file.file_name,
                    ]
                    dbg_exec_cmd(cmd)
                    tags_xml = ET.parse(tmp_tags_xml_file.file_name)
                    clean_Tag_elements(tags_xml.getroot())
                root = tags_xml.getroot()
                eTag = find_Tag_element(root, TargetTypeValue=TargetTypeValue, TargetType=TargetType)
                if not eTag:
                    eTag = ET.SubElement(root, 'Tag')
                    eTargets = ET.SubElement(eTag, 'Targets')
                    eTrackUID = ET.SubElement(eTargets, 'TrackUID')
                    eTrackUID.text = '0'
                    eTargetTypeValue = ET.SubElement(eTargets, 'TargetTypeValue')
                    eTargetTypeValue.text = str(TargetTypeValue)
                    if TargetType:
                        eTargetType = ET.SubElement(eTargets, 'TargetType')
                        eTargetType.text = str(TargetType)
                for eSimple in find_all_Simple_element(eTag, Name=mkv_tag):
                    app.log.debug('Remove %r', ET.tostring(eSimple))
                    eTag.remove(eSimple)
                tup_mkv_value = mkv_value if type(mkv_value) is tuple else (mkv_value,)
                #app.log.debug('value=%r, mkv_value=%r, tup_mkv_value=%r', value, mkv_value, tup_mkv_value)
                for one_mkv_value in tup_mkv_value:
                    eSimple = ET.SubElement(eTag, 'Simple')
                    eName = ET.SubElement(eSimple, 'Name')
                    eName.text = mkv_tag
                    eString = ET.SubElement(eSimple, 'String')
                    eString.text = one_mkv_value
                    if app.log.isEnabledFor(logging.DEBUG):
                        app.log.debug('Add %r', ET.tostring(eSimple))
        if tags_xml is not None:
            tags_xml.write(tmp_tags_xml_file.file_name,
                #encoding='unicode',
                xml_declaration=True,
                )
            if app.log.isEnabledFor(logging.DEBUG):
                with open(tmp_tags_xml_file.file_name, 'r') as fd:
                    app.log.debug('Tags XML: %s', fd.read())
            cmd = [
                'mkvpropedit',
                '--tags', 'all:%s' % (tmp_tags_xml_file.file_name),
                file_name,
            ]
            do_exec_cmd(cmd)

def taged(file_name, tags):
    app.log.info('Editing %s...', file_name)
    with perfcontext('mf.load'):
        mf = mutagen.File(file_name)
    if mf:
        if not taged_mf(file_name, mf, tags):
            app.log.verbose('Nothing to do.')
            return False
        if getattr(app.args, 'dry_run', False):
            app.log.verbose('Not saving. (dry-run)')
        else:
            with perfcontext('mf.save'):
                mf.save()
        return True
    file_base, file_ext = os.path.splitext(file_name)
    if file_ext in ('.mkv', '.webm'):
        return taged_MKV(file_name, tags)
    raise NotImplementedError(file_ext)
    return True

def taglist_mf(file_name, mf):
    if isinstance(mf.tags, mutagen.id3.ID3):
        return taglist_mf_id3(file_name, mf)
    if isinstance(mf.tags, mutagen.mp4.MP4Tags):
        return taglist_mf_MP4Tags(file_name, mf)
    raise NotImplementedError(mf.tags.__class__.__name__)

def taglist_mf_id3(file_name, mf):
    tags = TrackTags(album_tags=AlbumTags())
    for id3_tag, tag_value in mf.items():
        id3_tag = {
            'APIC:': 'APIC',
            }.get(id3_tag, id3_tag)
        if id3_tag in (
                'COMM:iTunNORM:eng',  # TODO
                'COMM:iTunPGAP:eng',  # TODO
                'COMM:iTunSMPB:eng',  # TODO
                'COMM:iTunes_CDDB_IDs:eng',  # TODO
                'TDRC',  # TODO
                'UFID:http://www.cddb.com/id3/taginfo1.html',  # TODO
                ):
            continue
        try:
            mapped_tag = qip.snd.tag_info['map'][id3_tag]
        except:
            app.log.debug('id3_tag=%r, tag_value=%r', id3_tag, tag_value)
            raise
        if mapped_tag in ('picture',):
            app.log.debug('id3_tag/mapped_tag=%r/%r, tag_value=...', id3_tag, mapped_tag)
        else:
            app.log.debug('id3_tag/mapped_tag=%r/%r, tag_value=%r', id3_tag, mapped_tag, tag_value)
        if mapped_tag == 'picture':
            assert isinstance(tag_value, mutagen.id3.APIC)
            # tag_value=APIC(encoding=<Encoding.LATIN1: 0>, mime='image/jpeg', type=<PictureType.OTHER: 0>, desc='', data=b'...')
            file_desc = byte_decode(dbg_exec_cmd(['file', '-b', '-'], input=tag_value.data)).strip()
            tag_value = '(%s: %s: %s)' % (tag_value.mime, tag_value.desc, file_desc)
        if isinstance(tag_value, mutagen.id3.TextFrame):
            tag_value = tag_value.text
        if isinstance(tag_value, list) and len(tag_value) == 1:
            tag_value = tag_value[0]
        old_value = tags[mapped_tag] if mapped_tag in ('episode',) else None
        if old_value is not None:
            if not isinstance(old_value, tuple):
                old_value = (old_value,)
            if not isinstance(tag_value, tuple):
                tag_value = (tag_value,)
            tag_value = old_value + tag_value
        tags.set_tag(mapped_tag, tag_value)
    return tags

def taglist_mf_MP4Tags(file_name, mf):
    tags = TrackTags(album_tags=AlbumTags())
    for mp4_tag, tag_value in mf.items():
        if mp4_tag in (
                '----:com.apple.iTunes:Encoding Params',  # TODO
                '----:com.apple.iTunes:iTunNORM',  # TODO
                '----:com.apple.iTunes:iTunes_CDDB_1',  # TODO
                '----:com.apple.iTunes:iTunes_CDDB_TrackNumber',  # TODO
                ):
            continue
        try:
            mapped_tag = qip.snd.tag_info['map'][mp4_tag]
        except:
            app.log.debug('mp4_tag=%r, tag_value=%r', mp4_tag, tag_value)
            raise
        if mapped_tag in ('picture',):
            app.log.debug('mp4_tag/mapped_tag=%r/%r, tag_value=...', mp4_tag, mapped_tag)
        else:
            app.log.debug('mp4_tag/mapped_tag=%r/%r, tag_value=%r', mp4_tag, mapped_tag, tag_value)
        if mapped_tag == 'picture':
            new_tag_value = []
            for cover in tag_value:
                assert isinstance(cover, mutagen.mp4.MP4Cover)
                imageformat = {
                        mutagen.mp4.MP4Cover.FORMAT_JPEG: 'JPEG',
                        mutagen.mp4.MP4Cover.FORMAT_PNG: 'PNG',
                        }.get(cover.imageformat, repr(cover.imageformat))
                file_desc = byte_decode(dbg_exec_cmd(['file', '-b', '-'], input=bytes(cover))).strip()
                new_tag_value.append('(%s: %s)' % (imageformat, file_desc))
            tag_value = new_tag_value
        if isinstance(tag_value, list) and len(tag_value) == 1:
            tag_value = tag_value[0]
        if isinstance(tag_value, mutagen.mp4.MP4FreeForm):
            if tag_value.dataformat == mutagen.mp4.AtomDataType.UTF8:
                tag_value = tag_value.decode('utf-8')
            else:
                raise NotImplementedError(tag_value.dataformat)
        old_value = tags[mapped_tag] if mapped_tag in ('episode',) else None
        if old_value is not None:
            if not isinstance(old_value, tuple):
                old_value = (old_value,)
            if not isinstance(tag_value, tuple):
                tag_value = (tag_value,)
            tag_value = old_value + tag_value
        tags.set_tag(mapped_tag, tag_value)
    return tags

mkv_tag_map = {
    (50, 'EPISODE', 'PART_NUMBER'): 'episode',
    (50, None, 'ARTIST'): 'artist',
    (50, None, 'CONTENT_TYPE'): 'contenttype',
    (50, None, 'DATE_RELEASED'): 'date',
    (50, None, 'ENCODER'): 'tool',
    (50, None, 'GENRE'): 'genre',
    (50, None, 'PART_NUMBER'): 'track',
    (50, None, 'TITLE'): 'title',
    (50, None, 'TOTAL_PARTS'): 'tracks',
    (60, 'SEASON', 'PART_NUMBER'): 'season',
    (70, 'COLLECTION', 'TITLE'): 'tvshow',
    }

def taglist_MKV(file_name):
    tags = AlbumTags()
    tags_xml_txt = dbg_exec_cmd(['mkvextract', file_name, 'tags', '-'])
    tags_xml = ET.fromstring(tags_xml_txt)
    root = tags_xml  # tags_xml.getroot()
    for eTag in root.findall('Tag'):
        eTargets = eTag.find('Targets')
        # <Targets>
        #   <TargetTypeValue>50</TargetTypeValue>
        #   <TrackUID>9427439434839936200</TrackUID>
        #   <TargetType>MOVIE</TargetType>
        # </Targets>
        eTargetTypeValue = eTargets and eTargets.find('TargetTypeValue')
        vTargetTypeValue = int(eTargetTypeValue.text) if (eTargetTypeValue is not None and eTargetTypeValue.text is not None) else 50
        eTargetType = eTargets and eTargets.find('TargetType')
        vTargetType = eTargetType.text if eTargetType is not None else None
        eTrackUID = eTargets and eTargets.find('TrackUID')
        vTrackUID = eTrackUID.text if (eTrackUID is not None and eTrackUID.text is not None) else '0'
        app.log.debug('Target: TargetType=%r/%s, TrackUID=%r', vTargetTypeValue, vTargetType, vTrackUID)
        target_tags = tags if vTrackUID == '0' else tags.tracks_tags[int(vTrackUID)]
        #if vTrackUID != '0':
        #    continue
        for eSimple in eTag.findall('Simple'):
            # <Simple>
            #   <Name>BPS</Name>
            #   <String>325282</String>
            #   <TagLanguage>eng</TagLanguage>
            # </Simple>
            mkv_tag = eSimple.find('Name').text
            if mkv_tag in (
                    'BPS',  # TODO
                    'DURATION',  # TODO
                    'NUMBER_OF_FRAMES',  # TODO
                    'NUMBER_OF_BYTES',  # TODO
                    '_STATISTICS_WRITING_APP',  # TODO
                    '_STATISTICS_WRITING_DATE_UTC',  # TODO
                    '_STATISTICS_TAGS',  # TODO
                    ):
                continue
            tag_value = eSimple.find('String').text
            app.log.debug('Simple: name=%r, value=%r', mkv_tag, tag_value)
            try:
                mapped_tag = mkv_tag_map[(vTargetTypeValue, vTargetType, mkv_tag)]
            except KeyError:
                raise
                # mapped_tag = mkv_tag_map[(vTargetTypeValue, None, mkv_tag)]
            old_value = tags[mapped_tag] if mapped_tag in ('episode',) else None
            if old_value is not None:
                if not isinstance(old_value, tuple):
                    old_value = (old_value,)
                if not isinstance(tag_value, tuple):
                    tag_value = (tag_value,)
                tag_value = old_value + tag_value
            target_tags.set_tag(mapped_tag, tag_value)
    return tags

def dump_tags(tags, *, deep=True, heading='Tags:'):
    if heading:
        print(heading)
    for tag_info in mp4tags.tag_args_info:
        # Force None values to actually exist
        if tags[tag_info.tag_enum] is None:
            tags[tag_info.tag_enum] = None
    tags_keys = tags.keys() if deep else tags.keys(deep=False)
    for tag in sorted(tags_keys, key=functools.cmp_to_key(dictionarycmp)):
        value = tags[tag]
        if isinstance(value, str):
            tags[tag] = value = replace_html_entities(tags[tag])
        if value is not None:
            if type(value) not in (int, str, bool, tuple):
                value = str(value)
            print('    %-13s = %r' % (tag.value, value))
    for track_no, track_tags in tags.tracks_tags.items() if isinstance(tags, AlbumTags) else ():
        dump_tags(track_tags, deep=False, heading='- Track %d' % (track_no,))

def taglist(file_name):
    app.log.info('Listing %s...', file_name)
    if True:
        tags = TrackTags(album_tags=AlbumTags())
    else:
        tags = AlbumTags()
    tags = None
    if tags is None:
        with perfcontext('mf.load'):
            mf = mutagen.File(file_name)
    if tags is None and mf:
        tags = taglist_mf(file_name, mf)
    if tags is None:
        file_base, file_ext = os.path.splitext(file_name)
        if file_ext in ('.mkv', '.webm')
            tags = taglist_MKV(file_name)
    if tags is None:
        raise NotImplementedError(file_ext)
    dump_tags(tags)
    return True

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
