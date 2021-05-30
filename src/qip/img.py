
__all__ = (
    'ImageFile',
    'ImageTagEnum',
    'ImageTags',
    'ImageType',
    'MissingImageTagError',
)

import collections
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
from .mm import MediaFile


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


class MissingImageTagError(Exception):

    def __init__(self, tag, file=None):
        tag = ImageTagEnum(tag)
        super().__init__(tag)
        self.tag = tag
        self.file_name = str(file) if file else None

    def __str__(self):
        s = '%s tag missing' % (self.tag.name,)
        if self.file_name:
            s = '%s: %s' % (self.file_name, s)
        return s


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

def _tImageTagRating(value):
    if type(value) is str:
        value = value.strip()
        value = {
            '0': 'None',
            '1': 'Clean',
            '2': 'Explicit',
            }.get(value, value)
    return ImageTagRating(value)

class ImageTagRating(enum.Enum):
    none = 'None'          # 0
    clean = 'Clean'        # 2
    explicit = 'Explicit'  # 3

    def __str__(self):
        return self.value

@functools.total_ordering
class ImageTagDate(object):

    year = propex(
        name='year',
        fdel=None,
        type=_tYear)

    month = propex(
        name='month',
        default=None,
        type=(None, _tMonth))

    day = propex(
        name='day',
        default=None,
        type=(None, _tDay))

    def __init__(self, value):

        if isinstance(value, (ImageTagDate, datetime.datetime, datetime.date)):
            # Copy constructor (or close)
            self.year, self.month, self.day = value.year, value.month, value.day
        elif type(value) is int:
            self.year = value
        elif type(value) is str:
            try:
                # 2013-11-20T08:00:00Z
                # 2013-11-20 08:00:00
                m = re.match(r'^(\d+-\d+-\d+)[T ]', value)
                tmp_value = m.group(1) if m else value
                d = datetime.datetime.strptime(tmp_value, '%Y-%m-%d').date()
            except ValueError:
                try:
                    d = datetime.datetime.strptime(value, '%Y:%m:%d').date()
                except ValueError:
                    try:
                        d = datetime.datetime.strptime(value, '%Y-%m').date()
                    except ValueError:
                        try:
                            d = datetime.datetime.strptime(value, '%Y').date()
                        except ValueError:
                            raise ValueError('Not a compatible date string')
                        else:
                            self.year = d.year
                    else:
                        self.year, self.month = d.year, d.month
                else:
                    self.year, self.month, self.day = d.year, d.month, d.day
            else:
                self.year, self.month, self.day = d.year, d.month, d.day
        else:
            raise TypeError('Not a compatible date type')

    def __str__(self):
        v = str(self.year)
        if self.month is not None:
            v += '-{:02}'.format(self.month)
            if self.day is not None:
                v += '-{:02}'.format(self.day)
        return v

    __json_encode__ = __str__

    def __eq__(self, other):
        if not isinstance(other, ImageTagDate):
            return NotImplemented
        return (self.year, self.month, self.day) == (other.year, other.month, other.day)

    def __lt__(self, other):
        if not isinstance(other, ImageTagDate):
            return NotImplemented
        return (self.year, self.month, self.day) < (other.year, other.month, other.day)

@functools.total_ordering
class ImageTagEnum(enum.Enum):

    title = 'title'  # STR
    subtitle = 'subtitle'  # STR

    date = 'date'  # None|ImageTagDate
    year = 'year'  # NUM  Set the release date (*from date)
    country = 'country'

    description = 'description'  # STR  Set the short description
    longdescription = 'longdescription'  # STR  Set the long description

    copyright = 'copyright'  # STR  Set the copyright information
    encodedby = 'encodedby'  # STR  Set the name of the person or company who encoded the file
    tool = 'tool'  # STR  Set the software used for encoding

    comment = 'comment'  # STR  Set a general comment

    sorttitle = 'sorttitle'

    purchasedate = 'purchasedate'

    contentrating = 'contentrating'  # None|ImageTagRating  Set the Rating(none, clean, explicit)

    def __repr__(self):
        return self.value

    def __eq__(self, other):
        other = ImageTagEnum(other)
        return self.value == other.value

    def __lt__(self, other):
        other = ImageTagEnum(other)
        return self.value < other.value

    def __hash__(self):
        return hash(id(self))

    def __json_encode__(self):
        return self.value

def _tNullTag(value):
    if value is None:
        return None
    elif type(value) is str:
        if value.strip() in ('', 'null', 'XXX'):
            return None
    raise ValueError('Not a null tag')

def _tNullDate(value):
    try:
        return _tNullTag(value)
    except ValueError:
        if type(value) is str:
            value = int(value)
        if type(value) is int:
            if value == 0:
                return None
    raise ValueError('Not a null date tag')

def _tPosIntNone0(value):
    value = int(value)
    if value < 0:
        raise ValueError('Not a positive integer')
    return value or None

def _tBool(value):
    if type(value) is bool:
        return value
    elif type(value) is int:
        if value == 0:
            return False
        elif value == 1:
            return True
    elif type(value) is str:
        try:
            return {
                '0': False,
                'false': False,
                'off': False,
                'no': False,
                '1': True,
                'true': True,
                'on': True,
                'yes': True,
            }[value.lower()]
        except KeyError:
            pass
    raise ValueError('Not a boolean')

def _tCommentTag(value):
    if value is None:
        return None
    elif type(value) is str:
        return (value,)
    else:
        return tuple(value)

class ImageTagDict(json.JSONEncodable, json.JSONDecodable, collections.MutableMapping):

    def __init__(self, dict=None, **kwargs):
        if dict is not None:
            #print('dict=%r' % (dict,))
            self.update(dict)
        if len(kwargs):
            self.update(kwargs)

    def _sanitize_key(self, key):
        try:
            return ImageTagEnum(key)
        except ValueError:
            raise KeyError(key)

    def __json_encode_vars__(self):
        d = collections.OrderedDict()
        for k, v in self.items():
            d[k.value] = v
        try:
            v = d['date']
        except KeyError:
            pass
        else:
            if v is not None and type(v) not in (int,):
                d['date'] = str(v)
        return d

    date = propex(
        name='date',
        type=(_tNullDate, ImageTagDate))

    year = propex(
        name='year',
        attr='date',
        type=(None, int),
        gettype=(None, operator.attrgetter('year')))

    comment = propex(
        name='comment',
        type=(_tNullTag, _tCommentTag))

    contentrating = propex(
        name='contentrating',
        type=(_tNullTag, _tImageTagRating))

    purchasedate = propex(
        name='purchasedate',
        type=(_tNullDate, ImageTagDate))

    def __setitem__(self, key, value):
        key = self._sanitize_key(key)
        setattr(self, key.value, value)

    def __delitem__(self, key):
        key = self._sanitize_key(key)
        try:
            delattr(self, key.value)
        except AttributeError:
            raise KeyError(key)

    def __contains__(self, key):
        return self.contains(key)

    def setdefault(self, key, default=None):
        'od.setdefault(k[,d]) -> od.get(k,d), also set od[k]=d if k not in od'
        if key in self:
            return self[key]
        self[key] = default
        return default

    def contains(self, key, strict=False):
        # valid key?
        try:
            key = self._sanitize_key(key)
        except KeyError:
            return False
        # value exists?
        # (could getattr but this avoids descriptor side-effects)
        try:
            value = self.__dict__[key.value]
        except KeyError:
            pass
        else:
            return True
        # is it a property?
        descr = _py._PyType_Lookup(type(self), key.value)
        if inspect.isdatadescriptor(descr):
            _key = (isinstance(descr, propex) and descr._propex__attr) or '_' + key.value
            if _key in self.__dict__:
                # direct property
                pass
            else:
                # indirect property
                if strict:
                    return False
            try:
                value = getattr(self, key.value)
            except AttributeError:
                pass
            else:
                return True
        return False

    def __iter__(self):
        for key in ImageTagEnum:
            if self.contains(key, strict=True):
                yield key

    def __len__(self):
        return len(list(iter(self)))

    def __getitem__(self, key):
        key = self._sanitize_key(key)
        return getattr(self, key.value)

    def __repr__(self):
        return '%s(%s)' % (
                self.__class__.__name__,
                reprlib.aRepr.repr_dict(self, reprlib.aRepr.maxlevel))

    def __getattr__(self, name):
        if not name.startswith('_'):
            if name in ImageTagEnum.__members__:
                return None
        f = getattr(super(), '__getattr__', None)
        if f is not None:
            return f(name)
        else:
            raise AttributeError(name)

    def set_tag(self, tag, value, source=''):
        if isinstance(tag, ImageTagEnum):
            tag = tag.value
        else:
            tag = tag.strip()
            try:
                tag = ImageTagEnum(tag.lower()).value
            except ValueError:
                try:
                    tag = image_tag_info['map'][tag]
                except KeyError:
                    try:
                        tag = image_tag_info['map'][tag.lower()]
                    except:
                        log.debug('tag %r not known: %r', tag, value)
                        return False
        if isinstance(value, str):
            value = value.strip()
            if value in ('', 'null', 'XXX'):
                return False

        elif tag == 'comment':
            if value == '<p>':
                return False
            try:
                l = self[tag] or []
            except KeyError:
                l = []
                pass
            if value not in l:
                l.append(value)
            value = l

        else:
            pass  # TODO

        # log.debug('%s: Tag %s = %r', self.file_name, tag, value)
        self[tag] = value
        return True

    class Formatter(string.Formatter):

        def __init__(self, tags):
            self.tags = tags
            super().__init__()

        def get_value(self, key, args, kwargs):
            try:
                value = super().get_value(key, args, kwargs)
            except KeyError:
                value = self.tags[key]
            return value

    def format(self, format_string, *args, **kwargs):
        return self.vformat(format_string, args, kwargs)

    def vformat(self, format_string, args, kwargs):
        formatter = self.Formatter(tags=self)
        return formatter.vformat(format_string, args, kwargs)


# Set all tags as propex!
for tag_enum in ImageTagEnum:
    if tag_enum.value not in ImageTagDict.__dict__:
        setattr(ImageTagDict, tag_enum.value,
                propex(name=tag_enum.value,
                       type=(None, propex.test_istype(str))))


class ImageTags(ImageTagDict):

    def __init__(self, *args, **kwargs):
        if args:
            d, = args
        super().__init__(*args, **kwargs)

    def short_str(self):
        l = []
        for tag_enum in (
                ImageTagEnum.title,
                ImageTagEnum.country,
                ImageTagEnum.date,
                ImageTagEnum.barcode,
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
            ext = os.path.splitext(self.file_name)[1]
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

    def extract_ffprobe_json(self,
            show_streams=True,
            show_format=True,
            show_error=True,
        ):
        cmd = [
            'ffprobe',
            '-i', self.file_name,
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
            ffprobe_dict = self.extract_ffprobe_json()
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
    m = re.match(r'^(?P<imageum_base_name>.+)-\d\d?$', os.path.splitext(img_file)[0])
    if m:
        tags_file_name = m.group('image_base_name') + '.tags'
        return image_tags_file_cache[tags_file_name]

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

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
