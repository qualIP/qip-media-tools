# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'ImageFile',
    'ImageTags',
    'ImageType',
)

import copy
import datetime
import decimal
import enum
import functools
import inspect
import io
import logging
import operator
import os
import re
import reprlib
import shutil
import string
import subprocess
import types
log = logging.getLogger(__name__)

from qip import _py
from qip import argparse
from qip import json
from qip.app import app
from qip.cmp import *
from qip.exec import *
import qip.file
from qip.isolang import isolang
from qip.file import *
from qip.parser import *
from qip.propex import propex
from qip.utils import byte_decode, TypedKeyDict, TypedValueDict, pairwise
from .mm import MediaFile, MediaTagDict


def _tIntRange(value, rng):
    value = int(value)
    if value not in rng:
        raise ValueError('Must be in {}..{}'.format(rng[0], rng[-1]))
    return value

def _tYear(value):
    return _tIntRange(value, range(datetime.MINYEAR, datetime.MAXYEAR + 1))

def _tMonth(value):
    return _tIntRange(value, range(1, 12 + 1))

def _tDay(value):
    # max = datetime._days_in_month(year, month)
    return _tIntRange(value, range(1, 31 + 1))

class _tReMatchTest(object):

    def __init__(self, expr, flags=None):
        self.expr = expr
        self.flags = flags

    def __call__(self, value):
        m = re.match(self.expr, value, flags)
        if not m:
            raise ValueError('Doesn\'t match r.e. {!r}'.format(self.expr))
        return value

    def __repr__(self):
        return '{}({!r}{})'.format(
            self.__class__.__name__,
            self.expr,
            ', {}'.format(self.flags) if self.flags is not None else '',
        )


class _tReMatchGroups(_tReMatchTest):

    def __call__(self, value):
        m = re.match(self.expr, value, self.flags or 0)
        if not m:
            raise ValueError('Doesn\'t match r.e. {!r}'.format(self.expr))
        return m.groups()

def _tArtist(value):
    if isinstance(value, (tuple, list)):
        value = '; '.join(value)
    if isinstance(value, str):
        return value
    raise ValueError('Must be a string or list: %r' % (value,))

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

# tags {{{

class ImageTags(MediaTagDict):

    def __init__(self, *args, **kwargs):
        if args:
            d, = args
        super().__init__(*args, **kwargs)

    def deduce_type(self):
        if self.type is not None:
            return self.type
        # raise MissingMediaTagError(MediaTagEnum.type)
        return 'image'

    def cite(self, **kwargs):
        try:
            return super().cite(**kwargs)
        except (NotImplementedError, TypeError):
            pass
        l = []
        for tag_enum in (
                MediaTagEnum.title,
                MediaTagEnum.country,
                MediaTagEnum.date,
                MediaTagEnum.barcode,
                ):
            v = getattr(self, tag_enum.value)
            if v is not None:
                l.append('{}: {}'.format(tag_enum.value, v))
        s = ', '.join(l)
        if self.picture is not None:
            s += ' [PIC]'
        return s

# }}}

# image_tag_info {{{

image_tag_info = {
        'tags': {},
        'map': {},
        }
for element, tag, aliases in [

    ["Title",               "title",                []],
    ["Subtitle",            "subtitle",             []],

    ["Date",                "date",                 []],
    ["Year",                "year",                 []],
    ["Country",             "country",              []],

    ["Description",         "description",          []],
    ["Long Description",    "longdescription",      []],

    ["Copyright",           "copyright",            []],
    ["Encodedby",           "encodedby",            []],
    ["Tool",                "tool",                 []],

    ["Comment",             "comment",              []],

    ["Sort Title",          "sorttitle",            []],

    ["Purchase Date",       "purchasedate",         []],

    ["Content Rating",      "contentrating",        []],
    ]:
    tag = (tag or element).lower()
    for v in ["element", "tag", "aliases"]:
        t = locals()[v]
        if t is not None:
            image_tag_info['tags'].setdefault(tag, {})
            image_tag_info['tags'][tag][v] = t
    for t in [element, tag] + aliases:
        if t is not None:
            image_tag_info['map'][t.lower()] = tag
            image_tag_info['map'][t] = tag

# }}}
#import pprint ; pprint.pprint(image_tag_info)

# class ImageAppSupport {{{

class ImageAppSupport(types.SimpleNamespace):

    def __init__(cls, app, formats=None):
        super().__init__(
                app=app,
                formats=formats if formats is not None else {},
                )

    def map_extension(self, ext):
        for fmt, support in self.formats.items():
            if ext in support.extensions:
                return fmt
        raise LookupError(ext)

    @property
    def extensions_can_read(self):
        for support in self.formats.values():
            if support.can_read:
                for ext in support.extensions:
                    yield ext

    @property
    def extensions_can_write(self):
        for support in self.formats.values():
            if support.can_write:
                for ext in support.extensions:
                    yield ext

# }}}
# class ImageFormatSupport {{{

class ImageFormatSupport(types.SimpleNamespace):

    def __init__(self, format, description=None, can_read=False, can_write=False, extensions=None):
        super().__init__(
                format=format,
                extensions=set(extensions) if extensions is not None else set(),
                can_read=can_read,
                can_write=can_write,
                description=description if description is not None else format,
                )

# }}}

# ImageType {{{

@functools.total_ordering
class ImageType(enum.Enum):
    bmp = 'bmp'
    gif = 'gif'
    jpg = 'jpg'
    png = 'png'
    tif = 'tif'

    def __eq__(self, other):
        try:
            other = ImageType(other)
        except ValueError:
            return NotImplemented
        return self.value == other.value

    def __lt__(self, other):
        other = ImageType(other)
        return self.value < other.value

    def __hash__(self):
        return hash(id(self))

    def __new(cls, value):
        if type(value) is str:
            value = value.strip()
            for pattern, new_value in (
                (r'^GIF$', 'gif'),
                (r'^JPEG$', 'jpg'),
                (r'^.jpeg$', 'jpg'),
                (r'^PC bitmap$', 'bmp'),
                (r'^PNG$', 'png'),
                (r'^TIFF$', 'tif'),
                ):
                m = re.search(pattern, value)
                if m:
                    value = new_value
                    break
            else:
                if value.startswith('.'):
                    value = value[1:]
        return super().__new__(cls, value)

ImageType.__new__ = ImageType._ImageType__new

# }}}

# class ImageFile {{{

class ImageFile(MediaFile):

    _common_extensions = (
        '.png',
        '.jpeg',
        '.jpg',
        '.gif',
        '.tiff',
    )

    @property
    def image_type(self):
        image_type = getattr(self, '_image_type', None)
        if image_type is None:
            ext = self.file_name.suffix
            image_type = ImageType(ext)
        return image_type

    @image_type.setter
    def image_type(self, value):
        if value is not None:
            value = ImageType(value)
        self._image_type = value

    def __init__(self, file_name, *args, **kwargs):
        super().__init__(file_name=file_name, *args, **kwargs)
        self.tags = ImageTags()

    def test_integrity(self):
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        log.info('Testing %s...' % (self.file_name,))
        cmd = [
                'ffmpeg',
                '-i', self.file_name,
                '-vn',
                '-f', 'null',
                '-y',
                '/dev/null',
                ]
        with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                ) as proc:
            out, unused_err = proc.communicate()
            if proc.returncode != 0:
                raise subprocess.CalledProcessError(proc.returncode, cmd, out)
        # Error while decoding stream #0:0: Invalid data found when processing input
        out = byte_decode(out)
        out = io.IncrementalNewlineDecoder(decoder=None, translate=True).decode(out, final=True)
        m = re.search(r'Error while decoding stream.*', out)
        if m:
            # raise ValueError("%s: %s" % (self.file_name, m.group(0)))
            log.error("%s: %s", self.file_name, m.group(0))
            return False
        return True

    def set_tag(self, tag, value, source=''):
        return self.tags.set_tag(tag, value, source=source)

    def write_tags(self, *, tags=None, **kwargs):
        if tags is None:
            tags = self.tags
        self.tag_writer.write_tags(tags=tags, file_name=self.file_name, **kwargs)

    def extract_ffprobe_dict(self,
            show_streams=True,
            show_format=True,
            show_error=True,
        ):
        cmd = [
            'ffprobe',
            '-i', self,
            '-threads', '0',
            '-v', 'info',
            '-print_format', 'json',
        ]
        if show_streams:
            cmd += ['-show_streams']
        if show_format:
            cmd += ['-show_format']
        if show_error:
            cmd += ['-show_error']
        try:
            # ffprobe -print_format json -show_streams -show_format -i ...
            out = dbg_exec_cmd(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError:
            # TODO ignore/report failure only?
            raise
        else:
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
                return ffprobe_dict
            raise ValueError('No json found in output of %r' % subprocess.list2cmdline(cmd))

    def extract_info(self, need_actual_duration=False):
        tags_done = False

        if shutil.which('ffprobe'):
            ffprobe_dict = self.extract_ffprobe_dict()
            if ffprobe_dict:
                # import pprint ; pprint.pprint(ffprobe_dict)
                stream_dict, = ffprobe_dict['streams']
                assert stream_dict['codec_type'] == 'video'
                try:
                    self.width = int(stream_dict['width'])
                except KeyError:
                    pass
                try:
                    self.height = int(stream_dict['height'])
                except KeyError:
                    pass
                for tag, value in ffprobe_dict['format'].get('tags', {}).items():
                    if value == 'None':
                        continue
                    if tag in (
                    ):
                        continue
                    self.set_tag(tag, value)
                tags_done = True

        if not tags_done:
            #raise Exception('Failed to read tags from %s' % (self.file_name,))
            app.log.warning('Failed to read tags from %s' % (self.file_name,))
        # log.debug('extract_info: %r', vars(self))

class ImageTagsCache(dict):

    def __missing__(self, key):
        tags_file = json.JsonFile(key)
        image_tags = None
        if tags_file.exists():
            app.log.info('Reading %s...', tags_file)
            with tags_file.open('r', encoding='utf-8') as fp:
                image_tags = ImageTags.json_load(fp)
        self[key] = image_tags
        return image_tags

image_tags_file_cache = ImageTagsCache()

def get_image_tags_from_tags_file(img_file):
    img_file = str(img_file)
    m = re.match(r'^(?P<imageum_base_name>.+)-\d\d?$', os.path.splitext(os.fspath(img_file))[0])
    if m:
        tags_file_name = m.group('image_base_name') + '.tags'
        return image_tags_file_cache[os.fspath(tags_file_name)]

# }}}

# class ArgparseSetTagAction {{{

class ArgparseSetTagAction(argparse.Action):

    def __init__(self,
                 option_strings,
                 tags,
                 dest,
                 default=argparse.SUPPRESS,
                 help='specify the \'{tag}\' tag'):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=1,
            help=help.format(tag=dest))
        self.tags = tags

    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) != 1:
            raise ValueError(values)
        value = values[0]
        if value == 'None':
            value = None
        if not self.tags.set_tag(self.dest, value):
            raise ValueError('Failed to set tag %r to %r' % (self.dest, value))

# }}}

def date_to_year(date):
    m = re.match('^(\d{4})(?:\d\d?-\d\d?)?$', date)
    if m:
        return int(m.group(1))

ImageFile._build_extension_to_class_map()
