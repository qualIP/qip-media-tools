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
import unidecode
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
    pgroup.add_argument('--disk', '--disc', dest='disk_slash_disks', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--track', dest='track_slash_tracks', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--picture', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--tvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--season', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--episode', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--language', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--country', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-title', '--sort-song', dest='sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumtitle', '--sort-album', dest='sortalbumtitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-artist', dest='sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-albumartist', dest='sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sort-composer', '--sort-writer', dest='sortwriter', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--compilation', '-K', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sortartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sorttitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sortalbumartist', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sortalbumtitle', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sortcomposer', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)
    pgroup.add_argument('--sorttvshow', tags=in_tags, default=argparse.SUPPRESS, action=qip.snd.ArgparseSetTagAction)

    app.parser.add_argument('files', nargs='*', default=None, help='sound files')

    app.parse_args()

    if getattr(app.args, 'action', None) is None:
        app.args.action = 'taged'
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

    if app.args.action == 'taged':
        # {{{

        if not app.args.files:
            raise Exception('No files provided')
        for file_name in app.args.files:
            with perfcontext('taged'):
                taged(file_name, in_tags)

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
        if mp4_tag == 'xid':
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
        vTrackUID = eTrackUID.text if eTrackUID is not None else '0'
        if vTrackUID != TrackUID:
            continue
        eTargetTypeValue = eTargets.find('TargetTypeValue')
        vTargetTypeValue = eTargetTypeValue.text if eTargetTypeValue is not None else '50'
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
                tup_mkv_value = mkv_value if mkv_value is tuple else tuple(mkv_value)
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
    if file_ext == '.mkv':
        return taged_MKV(file_name, tags)
    raise NotImplementedError(file_ext)
    return True

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
