
__all__ = (
    'SoundFile',
    'SoundTagEnum',
    'TrackTags',
    'AlbumTags',
    'mp4tags',
    'mp4info',
    'id3v2',
    'AudioType',
)

import collections
import operator
import datetime
import decimal
import enum
import functools
import inspect
import io
import os
import re
import reprlib
import shutil
import string
import subprocess
import types
import logging
log = logging.getLogger(__name__)

import qip.file
from qip.file import *
from qip.cmp import *
from qip.exec import *
from qip.parser import *
from qip.propex import propex
from qip.utils import byte_decode, TypedKeyDict, TypedValueDict
from qip import json
from qip import argparse
from qip import _py


def _tIntRange(value, rng):
    value = int(value)
    if value not in rng:
        raise ValueError('Must be in {}..{}'.format(rng[0], rng[-1]))
    return value

def _tTrackRange(value):
    return _tIntRange(value, range(1, 99 + 1))

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
        m = re.match(self.expr, value, flags)
        if not m:
            raise ValueError('Doesn\'t match r.e. {!r}'.format(self.expr))
        return m.groups()


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

class ITunesXid(object):

    class Scheme(enum.Enum):
        upc = 'upc'
        isrc = 'isrc'
        isan = 'isan'
        grid = 'grid'
        uuid = 'uuid'
        vendor_id = 'vendor_id'

        def __str__(self):
            return self.value

    RE_XID = (r'^'
              r'(?P<prefix>[A-Za-z0-9_.-]+)'
              r':'
              r'(?P<scheme>' + r'|'.join(scheme.value for scheme in Scheme) + r')'
              r':'
              r'(?P<identifier>[A-Za-z0-9_.-]+)'  # TODO
              r'$')

    prefix = propex(
        name='prefix',
        type=propex.test_istype(str))

    scheme = propex(
        name='scheme',
        type=Scheme)

    identifier = propex(
        name='identifier',
        type=propex.test_istype(str))

    xid = propex(
        name='xid',
        fdel=None)

    @xid.getter
    def xid(self):
        return '{}:{}:{}'.format(
            self.prefix,
            self.scheme,
            self.identifier)

    @xid.setter
    def xid(self, value):
        m = re.match(self.RE_XID, str(value))
        if not m:
            raise ValueError('Not a iTunes XID')
        for k, v in m.groupdict().items():
            setattr(self, k, v)

    def __str__(self):
        return self.xid

    def __repr__(self):
        return '{}({!r})'.format(
            self.__class__.__name__,
            self.xid)

    def __init__(self, *args):
        if len(args) == 1:
            xid = args[0]
            if isinstance(xid, ITunesXid):
                # Copy constructor
                self.prefix, self.scheme, self.identifier = xid.prefix, xid.scheme, xid.identifier
            else:
                self.xid = xid
        elif len(args) == 3:
            self.prefix, self.scheme, self.identifier = args
        else:
            raise TypeError('{}(xid | prefix, scheme, identifier)'.format(self.__class__.__name__))
        super().__init__()

class SoundTagRating(enum.Enum):
    none = 'none'
    clean = 'clean'
    explicit = 'explicit'

    def __str__(self):
        return self.value

@functools.total_ordering
class SoundTagDate(object):

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

        if isinstance(value, (SoundTagDate, datetime.datetime, datetime.date)):
            # Copy constructor (or close)
            self.year, self.month, self.day = value.year, value.month, value.day
        elif type(value) is int:
            self.year = value
        elif type(value) is str:
            try:
                d = datetime.datetime.strptime(value, '%Y-%m-%d').date()
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
        if not isinstance(other, SoundTagDate):
            return NotImplemented
        return (self.year, self.month, self.day) == (other.year, other.month, other.day)

    def __lt__(self, other):
        if not isinstance(other, SoundTagDate):
            return NotImplemented
        return (self.year, self.month, self.day) < (other.year, other.month, other.day)

@functools.total_ordering
class SoundTagEnum(enum.Enum):

    albumartist = 'albumartist'  # STR  Set the album artist
    artist = 'artist'  # STR  Set the artist information
    artistid = 'artistid'  # NUM  Set the artist ID
    albumtitle = 'albumtitle'  # STR  Set the album title (album)
    title = 'title'  # STR  Set the song title
    subtitle = 'subtitle'  # STR
    composer = 'composer'  # STR  Set the composer information (writer)
    composerid = 'composerid'  # NUM  Set the composer ID

    date = 'date'  # None|SoundTagDate
    year = 'year'  # NUM  Set the release date (*from date)
    country = 'country'

    disk = 'disk'  # NUM  Set the disk number
    disks = 'disks'  # NUM  Set the number of disks
    disk_slash_disks = 'disk_slash_disks'  # NUM  Set the disk number (*from disk[/disks])
    track = 'track'  # NUM  Set the track number
    tracks = 'tracks'  # NUM  Set the number of tracks
    track_slash_tracks = 'track_slash_tracks'  # NUM  Set the track number (*from track[/tracks])

    tvnetwork = 'tvnetwork'  # STR  Set the TV network
    tvshow = 'tvshow'  # STR  Set the TV show
    season = 'season'  # NUM  Set the season number
    episode = 'episode'  # NUM  Set the episode number
    episodeid = 'episodeid'  # STR  Set the TV episode ID

    description = 'description'  # STR  Set the short description
    longdescription = 'longdescription'  # STR  Set the long description

    compilation = 'compilation'  # NUM  Set the compilation flag (1\0)
    podcast = 'podcast'  # NUM  Set the podcast flag.
    hdvideo = 'hdvideo'  # NUM  Set the HD flag (1\0)

    genre = 'genre'  # STR  Set the genre name
    genreid = 'genreid'  # NUM  Set the genre ID
    type = 'type'  # STR  Set the Media Type(tvshow, movie, music, ...)
    category = 'category'  # STR  Set the category
    grouping = 'grouping'  # STR  Set the grouping name

    copyright = 'copyright'  # STR  Set the copyright information
    encodedby = 'encodedby'  # STR  Set the name of the person or company who encoded the file
    tool = 'tool'  # STR  Set the software used for encoding

    contentid = 'contentid'  # NUM  Set the content ID

    picture = 'picture'  # PTH  Set the picture as a .png

    tempo = 'tempo'  # NUM  Set the tempo (beats per minute)

    comment = 'comment'  # STR  Set a general comment
    lyrics = 'lyrics'  # NUM  Set the lyrics  # TODO STR!

    sortartist = 'sortartist'
    sorttitle = 'sorttitle'
    sortalbumartist = 'sortalbumartist'
    sortalbumtitle = 'sortalbumtitle'
    sortcomposer = 'sortcomposer'
    sorttvshow = 'sorttvshow'

    xid = 'xid'  # ITunesXid  Set the globally-unique xid (vendor:scheme:id)
    cddb_discid = 'cddb_discid'
    musicbrainz_discid = 'musicbrainz_discid'
    musicbrainz_releaseid = 'musicbrainz_releaseid'
    musicbrainz_cdstubid = 'musicbrainz_cdstubid'
    accuraterip_discid = 'accuraterip_discid'
    barcode = 'barcode'
    asin = 'asin'

    playlistid = 'playlistid'  # NUM  Set the playlist ID
    rating = 'rating'  # None|SoundTagRating  Set the Rating(none, clean, explicit)

    def __repr__(self):
        return self.value

    def __eq__(self, other):
        other = SoundTagEnum(other)
        return self.value == other.value

    def __lt__(self, other):
        other = SoundTagEnum(other)
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

class SoundTagDict(json.JSONEncodable, json.JSONDecodable, collections.MutableMapping):

    def __init__(self, dict=None, **kwargs):
        if dict is not None:
            self.update(dict)
        if len(kwargs):
            self.update(kwargs)

    def _sanitize_key(self, key):
        try:
            return SoundTagEnum(key)
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

    disk = propex(
        name='disk',
        type=(_tNullTag, _tPosIntNone0))

    disks = propex(
        name='disks',
        type=(_tNullTag, _tPosIntNone0))

    disk_slash_disks = propex(
        name='disk_slash_disks',
        type=(_tNullTag, int, _tReMatchGroups(r'^0*(?P<disk>\d+)(?:(?: of |/)0*(?P<disks>\d+))?')))

    @disk_slash_disks.getter
    def disk_slash_disks(self):
        try:
            disk = self.disk
        except AttributeError:
            raise AttributeError
        if disk is None:
            return None
        value = str(disk)
        disks = getattr(self, 'disks', None)
        if disks is not None:
            value += '/' + str(disks)
        return value

    @disk_slash_disks.setter
    def disk_slash_disks(self, value):
        if value is None:
            self.disk = None
            self.disks = None
        elif type(value) is int:
            self.disk = value
            self.disks = None
        elif type(value) is tuple:
            self.disk, self.disks = value
        else:
            raise RuntimeError(value)

    @disk_slash_disks.deleter
    def disk_slash_disks(self):
        try:
            del self.disk
        except AttributeError:
            pass
        try:
            del self.disks
        except AttributeError:
            pass

    track = propex(
        name='track',
        type=(_tNullTag, _tPosIntNone0))

    tracks = propex(
        name='tracks',
        type=(_tNullTag, _tPosIntNone0))

    track_slash_tracks = propex(
        name='track_slash_tracks',
        type=(_tNullTag, int, _tReMatchGroups(r'^0*(?P<track>\d+)(?:(?: of |/)0*(?P<tracks>\d+))?')))

    @track_slash_tracks.getter
    def track_slash_tracks(self):
        try:
            track = self.track
        except AttributeError:
            raise AttributeError
        if track is None:
            return None
        value = str(track)
        tracks = getattr(self, 'tracks', None)
        if tracks is not None:
            value += '/' + str(tracks)
        return value

    @track_slash_tracks.setter
    def track_slash_tracks(self, value):
        if value is None:
            self.track = None
            self.tracks = None
        elif type(value) is int:
            self.track = value
            self.tracks = None
        elif type(value) is tuple:
            self.track, self.tracks = value
        else:
            raise RuntimeError(value)

    @track_slash_tracks.deleter
    def track_slash_tracks(self):
        try:
            del self.track
        except AttributeError:
            try:
                del self.tracks
            except AttributeError:
                raise AttributeError
        else:
            try:
                del self.tracks
            except AttributeError:
                pass

    date = propex(
        name='date',
        type=(_tNullDate, SoundTagDate))

    year = propex(
        name='year',
        attr='date',
        type=(None, int),
        gettype=(None, operator.attrgetter('year')))

    artistid = propex(
        name='artistid',
        type=(_tNullTag, int))

    composerid = propex(
        name='composerid',
        type=(_tNullTag, int))

    season = propex(
        name='season',
        type=(_tNullTag, int))

    episode = propex(
        name='episode',
        type=(_tNullTag, int))

    compilation = propex(
        name='compilation',
        type=(_tNullTag, _tBool))

    podcast = propex(
        name='podcast',
        type=(_tNullTag, _tBool))

    hdvideo = propex(
        name='hdvideo',
        type=(_tNullTag, _tBool))

    genreid = propex(
        name='genreid',
        type=(_tNullTag, int))

    contentid = propex(
        name='contentid',
        type=(_tNullTag, int))

    tempo = propex(
        name='tempo',
        type=(_tNullTag, int))  # TODO pint ppm

    playlistid = propex(
        name='playlistid',
        type=(_tNullTag, int))

    rating = propex(
        name='rating',
        type=(_tNullTag, SoundTagRating))

    xid = propex(
        name='xid',
        type=(_tNullTag, ITunesXid))

    @xid.defaulter
    def xid(self):
        for tag_enum, prefix, scheme in (
                (SoundTagEnum.barcode, 'unknown', ITunesXid.Scheme.upc),
                (SoundTagEnum.asin, 'amazon', ITunesXid.Scheme.vendor_id),
                (SoundTagEnum.musicbrainz_discid, 'musicbrainz', ITunesXid.Scheme.vendor_id),
                (SoundTagEnum.cddb_discid, 'cddb', ITunesXid.Scheme.vendor_id),
                (SoundTagEnum.accuraterip_discid, 'accuraterip', ITunesXid.Scheme.vendor_id),
        ):
            identifier = self[tag_enum]
            if identifier is not None:
                return ITunesXid(prefix, scheme, identifier)
        raise AttributeError

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
        for key in SoundTagEnum:
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
            if name in SoundTagEnum.__members__:
                return None
        f = getattr(super(), '__getattr__', None)
        if f is not None:
            return f(name)
        else:
            raise AttributeError(name)

    def set_tag(self, tag, value, source=''):
        if isinstance(tag, SoundTagEnum):
            tag = tag.value
        else:
            tag = tag.strip()
            try:
                tag = SoundTagEnum(tag.lower()).value
            except ValueError:
                try:
                    tag = tag_info['map'][tag]
                except KeyError:
                    try:
                        tag = tag_info['map'][tag.lower()]
                    except:
                        log.debug('tag %r not known', tag)
                        return False
        if isinstance(value, str):
            value = value.strip()
            if value in ('', 'null', 'XXX'):
                return False
        if tag in ('genre', 'genreID'):
            if isinstance(value, str):
                value = re.sub(r'^\((\d+)\)$', r'\1', value)
                if value.isdigit():
                    value = int(value)
            if isinstance(value, int):
                if source.startswith('id3'):
                    try:
                        value = id3v1_genres_id_map[value]
                    except KeyError:
                        # The iTunes (mp4v2) genre tag is one greater than the corresponding ID3 tag
                        value += 1
            if isinstance(value, int):
                try:
                    value = mp4v2_genres_id_map[value]
                except:
                    pass
            else:
                m = (
                        re.search(r'^(?P<value>.+) \((?P<id>\d+)\)$', value) or
                        re.search(r'^(?P<id>\d+), (?P<value>.+)$', value)
                        )
                if m:
                    # Attempt to normalize
                    value = m.group('value')
                    if source.startswith('id3'):
                        if value not in id3v1_genres:
                            raise ValueError('Not a valid id3v1 genre')
                    else:
                        if value not in mp4v2_genres:
                            raise ValueError('Not a valid mp4v2 genre')
            if isinstance(value, int):
                tag = 'genreID'
                self.pop('genre', None)
            else:
                tag = 'genre'
                self.pop('genreID', None)

        elif tag in ('disk', 'track'):
            m = re.search(r'^0*(?P<value>\d*)(?:(?: of |/)0*(?P<n>\d*))?$', value)
            if m:
                value = m.group('value')
                if m.group('n') is not None:
                    self[tag + 's'] = m.group('n')

        elif tag == 'comment':
            if value == '<p>':
                return False
            l = []
            try:
                l += self[tag]
            except KeyError:
                pass
            if value not in l:
                l.append(value)
            value = l

        elif tag == 'type':
            if value.isdigit():
                # Ok
                # NOTE: AtomicParsley takes "value=$value"
                pass
            else:
                try:
                    value = tag_stik_info['map'][value]
                except KeyError:
                    try:
                        value = tag_stik_info['map'][m.sub(r'\s', '', value.lower())]
                    except KeyError:
                        raise ValueError('Unsupported %s value' % (tag, ))
            try:
                value = tag_stik_info['stik'][value]['mp4v2_arg']
            except KeyError:
                pass

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
for tag_enum in SoundTagEnum:
    if tag_enum.value not in SoundTagDict.__dict__:
        setattr(SoundTagDict, tag_enum.value,
                propex(name=tag_enum.value,
                       type=(None, propex.test_istype(str))))


class TrackTags(SoundTagDict):

    album_tags = None

    track = SoundTagDict.track.copy()

    @track.defaulter
    def track(self):
        album_tags = self.album_tags
        if album_tags is not None:
            for track_no, v in album_tags.tracks_tags.items():
                if v is self:
                    return track_no
        return None

    def __init__(self, *args, **kwargs):
        album_tags = kwargs.pop('album_tags', None)
        if album_tags is not None:
            self.album_tags = album_tags
        super().__init__(*args, **kwargs)

    def __getattr__(self, name):
        if not name.startswith('_'):
            if name in SoundTagEnum.__members__:
                album_tags = self.album_tags
                if album_tags:
                    return getattr(album_tags, name)
        f = getattr(super(), '__getattr__', None)
        if f is not None:
            return f(name)
        else:
            raise AttributeError(name)

    def short_str(self):
        l = []
        for tag_enum in (
                SoundTagEnum.artist,
                SoundTagEnum.title,
                ):
            try:
                l.append('{}: {}'.format(tag_enum.value, getattr(self, tag_enum.value)))
            except KeyError:
                pass
        return ', '.join(l)

class AlbumTags(SoundTagDict):

    albumtitle = SoundTagDict.title.copy()
    albumartist = SoundTagDict.artist.copy()

    tracks = SoundTagDict.tracks.copy()

    @tracks.defaulter
    def tracks(self):
        tracks_tags = self.tracks_tags
        if tracks_tags:
            return len(tracks_tags)
        raise AttributeError

    class TracksDict(TypedKeyDict, TypedValueDict, dict):

        album_tags = None

        def __init__(self, *args, **kwargs):
            album_tags = kwargs.pop('album_tags')
            if album_tags is not None:
                self.album_tags = album_tags
            super().__init__(*args, **kwargs)

        def _sanitize_key(self, key):
            try:
                key = _tIntRange(key, range(1, 100))
            except:
                raise KeyError(key)
            return key

        def _sanitize_value(self, value, key=None):
            if isinstance(value, TrackTags) \
                    and value.album_tags is self.album_tags:
                pass
            else:
                value = TrackTags(value, album_tags=self.album_tags)
            return value

        def update(self, *args, **kwargs):
            return super().update(*args, **kwargs)

        def __missing__(self, key):
            self[key] = value = TrackTags(album_tags=self.album_tags)
            return value

    def __init__(self, *args, tracks_tags=None, **kwargs):
        self.tracks_tags = self.TracksDict(album_tags=self)
        if tracks_tags:
            self.tracks_tags.update(tracks_tags)
        super().__init__(*args, **kwargs)

    def short_str(self):
        l = []
        for tag_enum in (
                SoundTagEnum.artist,
                SoundTagEnum.title,
                SoundTagEnum.country,
                SoundTagEnum.date,
                SoundTagEnum.barcode,
                SoundTagEnum.musicbrainz_discid,
                SoundTagEnum.musicbrainz_releaseid,
                SoundTagEnum.musicbrainz_cdstubid,
                SoundTagEnum.cddb_discid,
                ):
            v = getattr(self, tag_enum.value)
            if v is not None:
                l.append('{}: {}'.format(tag_enum.value, v))
        s = ', '.join(l)
        if self.picture is not None:
            s += ' [PIC]'
        return s

    #def __json_prepare_dump__(self):
    #    return self.__json_encode_vars__()  # implicit class

    def __json_encode_vars__(self):
        d = super().__json_encode_vars__()
        d['tracks_tags'] = {
            k: v.__json_encode_vars__()  # implicit class
            for k, v in self.tracks_tags.items()}
        return d

# }}}

# id3v1_genres_id_map {{{

# From: id3v2 -L
id3v1_genres_id_map = {
        0:   "Blues",
        1:   "Classic Rock",
        2:   "Country",
        3:   "Dance",
        4:   "Disco",
        5:   "Funk",
        6:   "Grunge",
        7:   "Hip-Hop",
        8:   "Jazz",
        9:   "Metal",
        10:  "New Age",
        11:  "Oldies",
        12:  "Other",
        13:  "Pop",
        14:  "R&B",
        15:  "Rap",
        16:  "Reggae",
        17:  "Rock",
        18:  "Techno",
        19:  "Industrial",
        20:  "Alternative",
        21:  "Ska",
        22:  "Death Metal",
        23:  "Pranks",
        24:  "Soundtrack",
        25:  "Euro-Techno",
        26:  "Ambient",
        27:  "Trip-Hop",
        28:  "Vocal",
        29:  "Jazz+Funk",
        30:  "Fusion",
        31:  "Trance",
        32:  "Classical",
        33:  "Instrumental",
        34:  "Acid",
        35:  "House",
        36:  "Game",
        37:  "Sound Clip",
        38:  "Gospel",
        39:  "Noise",
        40:  "AlternRock",
        41:  "Bass",
        42:  "Soul",
        43:  "Punk",
        44:  "Space",
        45:  "Meditative",
        46:  "Instrumental Pop",
        47:  "Instrumental Rock",
        48:  "Ethnic",
        49:  "Gothic",
        50:  "Darkwave",
        51:  "Techno-Industrial",
        52:  "Electronic",
        53:  "Pop-Folk",
        54:  "Eurodance",
        55:  "Dream",
        56:  "Southern Rock",
        57:  "Comedy",
        58:  "Cult",
        59:  "Gangsta",
        60:  "Top 40",
        61:  "Christian Rap",
        62:  "Pop/Funk",
        63:  "Jungle",
        64:  "Native American",
        65:  "Cabaret",
        66:  "New Wave",
        67:  "Psychedelic",
        68:  "Rave",
        69:  "Showtunes",
        70:  "Trailer",
        71:  "Lo-Fi",
        72:  "Tribal",
        73:  "Acid Punk",
        74:  "Acid Jazz",
        75:  "Polka",
        76:  "Retro",
        77:  "Musical",
        78:  "Rock & Roll",
        79:  "Hard Rock",
        80:  "Folk",
        81:  "Folk-Rock",
        82:  "National Folk",
        83:  "Swing",
        84:  "Fast Fusion",
        85:  "Bebob",
        86:  "Latin",
        87:  "Revival",
        88:  "Celtic",
        89:  "Bluegrass",
        90:  "Avantgarde",
        91:  "Gothic Rock",
        92:  "Progressive Rock",
        93:  "Psychedelic Rock",
        94:  "Symphonic Rock",
        95:  "Slow Rock",
        96:  "Big Band",
        97:  "Chorus",
        98:  "Easy Listening",
        99:  "Acoustic",
        100: "Humour",
        101: "Speech",
        102: "Chanson",
        103: "Opera",
        104: "Chamber Music",
        105: "Sonata",
        106: "Symphony",
        107: "Booty Bass",
        108: "Primus",
        109: "Porn Groove",
        110: "Satire",
        111: "Slow Jam",
        112: "Club",
        113: "Tango",
        114: "Samba",
        115: "Folklore",
        116: "Ballad",
        117: "Power Ballad",
        118: "Rhythmic Soul",
        119: "Freestyle",
        120: "Duet",
        121: "Punk Rock",
        122: "Drum Solo",
        123: "A capella",
        124: "Euro-House",
        125: "Dance Hall",
        126: "Goa",
        127: "Drum & Bass",
        128: "Club-House",
        129: "Hardcore",
        130: "Terror",
        131: "Indie",
        132: "Britpop",
        133: "Negerpunk",
        134: "Polsk Punk",
        135: "Beat",
        136: "Christian Gangsta Rap",
        137: "Heavy Metal",
        138: "Black Metal",
        139: "Crossover",
        140: "Contemporary Christian",
        141: "Christian Rock ",
        142: "Merengue",
        143: "Salsa",
        144: "Thrash Metal",
        145: "Anime",
        146: "JPop",
        147: "Synthpop",
}
id3v1_genres = set(id3v1_genres_id_map.values())

# }}}
# mp4v2_categories... / mp4v2_genres... {{{

mp4v2_categories = set()
mp4v2_categories_id_map = {}
mp4v2_genres = set()
mp4v2_genres_id_map = {}
mp4v2_genres_info = {}

# http://www.apple.com/itunes/affiliates/resources/documentation/genre-mapping.html
#   Category    Genre       Sub Genre
for cat_id, cat_name, genres_info in [
    [26, "Podcasts", [
        [1301, "Arts", [
            [1306, "Food"],
            [1401, "Literature"],
            [1402, "Design"],
            [1405, "Performing Arts"],
            [1406, "Visual Arts"],
            [1459, "Fashion & Beauty"],
        ]],
        [1303, "Comedy", [
        ]],
        [1304, "Education", [
            [1415, "K-12"],
            [1416, "Higher Education"],
            [1468, "Educational Technology"],
            [1469, "Language Courses"],
            [1470, "Training"],
        ]],
        [1305, "Kids & Family", [
        ]],
        [1307, "Health", [
            [1417, "Fitness & Nutrition"],
            [1420, "Self-Help"],
            [1421, "Sexuality"],
            [1481, "Alternative Health"],
        ]],
        [1309, "TV & Film", [
        ]],
        [1310, "Music", [
        ]],
        [1311, "News & Politics", [
        ]],
        [1314, "Religion & Spirituality", [
            [1438, "Buddhism"],
            [1439, "Christianity"],
            [1440, "Islam"],
            [1441, "Judaism"],
            [1444, "Spirituality"],
            [1463, "Hinduism"],
            [1464, "Other"],
        ]],
        [1315, "Science & Medicine", [
            [1477, "Natural Sciences"],
            [1478, "Medicine"],
            [1479, "Social Sciences"],
        ]],
        [1316, "Sports & Recreation", [
            [1456, "Outdoor"],
            [1465, "Professional"],
            [1466, "College & High School"],
            [1467, "Amateur"],
        ]],
        [1318, "Technology", [
            [1446, "Gadgets"],
            [1448, "Tech News"],
            [1450, "Podcasting"],
            [1480, "Software How-To"],
        ]],
        [1321, "Business", [
            [1410, "Careers"],
            [1412, "Investing"],
            [1413, "Management & Marketing"],
            [1471, "Business News"],
            [1472, "Shopping"],
        ]],
        [1323, "Games & Hobbies", [
            [1404, "Video Games"],
            [1454, "Automotive"],
            [1455, "Aviation"],
            [1460, "Hobbies"],
            [1461, "Other Games"],
        ]],
        [1324, "Society & Culture", [
            [1302, "Personal Journals"],
            [1320, "Places & Travel"],
            [1443, "Philosophy"],
            [1462, "History"],
        ]],
        [1325, "Government & Organizations", [
            [1473, "National"],
            [1474, "Regional"],
            [1475, "Local"],
            [1476, "Non-Profit"],
        ]],
    ]],
    [31, "Music Videos", [
        [1602, "Blues", [
        ]],
        [1603, "Comedy", [
        ]],
        [1604, "Children's Music", [
        ]],
        [1605, "Classical", [
        ]],
        [1606, "Country", [
        ]],
        [1607, "Electronic", [
        ]],
        [1608, "Holiday", [
        ]],
        [1609, "Opera", [
        ]],
        [1610, "Singer/Songwriter", [
        ]],
        [1611, "Jazz", [
        ]],
        [1612, "Latino", [
        ]],
        [1613, "New Age", [
        ]],
        [1614, "Pop", [
        ]],
        [1615, "R&B/Soul", [
        ]],
        [1616, "Soundtrack", [
        ]],
        [1617, "Dance", [
        ]],
        [1618, "Hip-Hop/Rap", [
        ]],
        [1619, "World", [
        ]],
        [1620, "Alternative", [
        ]],
        [1621, "Rock", [
        ]],
        [1622, "Christian & Gospel", [
        ]],
        [1623, "Vocal", [
        ]],
        [1624, "Reggae", [
        ]],
        [1625, "Easy Listening", [
        ]],
        [1626, "Podcasts", [
        ]],
        [1627, "J-Pop", [
        ]],
        [1628, "Enka", [
        ]],
        [1629, "Anime", [
        ]],
        [1630, "Kayokyoku", [
        ]],
        [1631, "Disney", [
        ]],
        [1632, "French Pop", [
        ]],
        [1633, "German Pop", [
        ]],
        [1634, "German Folk", [
        ]],
    ]],
    [32, "TV Shows", [
        [4000, "Comedy", [
        ]],
        [4001, "Drama", [
        ]],
        [4002, "Animation", [
        ]],
        [4003, "Action & Adventure", [
        ]],
        [4004, "Classic", [
        ]],
        [4005, "Kids", [
        ]],
        [4006, "Nonfiction", [
        ]],
        [4007, "Reality TV", [
        ]],
        [4008, "Sci-Fi & Fantasy", [
        ]],
        [4009, "Sports", [
        ]],
        [4010, "Teens", [
        ]],
        [4011, "Latino TV", [
        ]],
    ]],
    [33, "Movies", [
        [4401, "Action & Adventure", [
        ]],
        [4402, "Anime", [
        ]],
        [4403, "Classics", [
        ]],
        [4404, "Comedy", [
        ]],
        [4405, "Documentary", [
        ]],
        [4406, "Drama", [
        ]],
        [4407, "Foreign", [
        ]],
        [4408, "Horror", [
        ]],
        [4409, "Independent", [
        ]],
        [4410, "Kids & Family", [
        ]],
        [4411, "Musicals", [
        ]],
        [4412, "Romance", [
        ]],
        [4413, "Sci-Fi & Fantasy", [
        ]],
        [4414, "Short Films", [
        ]],
        [4415, "Special Interest", [
        ]],
        [4416, "Thriller", [
        ]],
        [4417, "Sports", [
        ]],
        [4418, "Western", [
        ]],
        [4419, "Urban", [
        ]],
        [4420, "Holiday", [
        ]],
        [4421, "Made for TV", [
        ]],
        [4422, "Concert Films", [
        ]],
        [4423, "Music Documentaries", [
        ]],
        [4424, "Music Feature Films", [
        ]],
        [4425, "Japanese Cinema", [
        ]],
        [4426, "Jidaigeki", [
        ]],
        [4427, "Tokusatsu", [
        ]],
        [4428, "Korean Cinema", [
        ]],
    ]],
    [34, "Music", [
        [2, "Blues", [
            [1007, "Chicago Blues"],
            [1009, "Classic Blues"],
            [1010, "Contemporary Blues"],
            [1011, "Country Blues"],
            [1012, "Delta Blues"],
            [1013, "Electric Blues"],
            [1210, "Acoustic Blues"],
        ]],
        [3, "Comedy", [
            [1167, "Novelty"],
            [1171, "Standup Comedy"],
        ]],
        [4, "Children's Music", [
            [1014, "Lullabies"],
            [1015, "Sing-Along"],
            [1016, "Stories"],
        ]],
        [5, "Classical", [
            [1017, "Avant-Garde"],
            [1018, "Baroque"],
            [1019, "Chamber Music"],
            [1020, "Chant"],
            [1021, "Choral"],
            [1022, "Classical Crossover"],
            [1023, "Early Music"],
            [1024, "Impressionist"],
            [1025, "Medieval"],
            [1026, "Minimalism"],
            [1027, "Modern Composition"],
            [1028, "Opera"],
            [1029, "Orchestral"],
            [1030, "Renaissance"],
            [1031, "Romantic"],
            [1032, "Wedding Music"],
            [1211, "High Classical"],
        ]],
        [6, "Country", [
            [1033, "Alternative Country"],
            [1034, "Americana"],
            [1035, "Bluegrass"],
            [1036, "Contemporary Bluegrass"],
            [1037, "Contemporary Country"],
            [1038, "Country Gospel"],
            [1039, "Honky Tonk"],
            [1040, "Outlaw Country"],
            [1041, "Traditional Bluegrass"],
            [1042, "Traditional Country"],
            [1043, "Urban Cowboy"],
        ]],
        [7, "Electronic", [
            [1056, "Ambient"],
            [1057, "Downtempo"],
            [1058, "Electronica"],
            [1060, "IDM/Experimental"],
            [1061, "Industrial"],
        ]],
        [8, "Holiday", [
            [1079, "Chanukah"],
            [1080, "Christmas"],
            [1081, "Christmas: Children's"],
            [1082, "Christmas: Classic"],
            [1083, "Christmas: Classical"],
            [1084, "Christmas: Jazz"],
            [1085, "Christmas: Modern"],
            [1086, "Christmas: Pop"],
            [1087, "Christmas: R&B"],
            [1088, "Christmas: Religious"],
            [1089, "Christmas: Rock"],
            [1090, "Easter"],
            [1091, "Halloween"],
            [1092, "Holiday: Other"],
            [1093, "Thanksgiving"],
        ]],
        [9, "Opera", [
        ]],
        [10, "Singer/Songwriter", [
            [1062, "Alternative Folk"],
            [1063, "Contemporary Folk"],
            [1064, "Contemporary Singer/Songwriter"],
            [1065, "Folk-Rock"],
            [1066, "New Acoustic"],
            [1067, "Traditional Folk"],
        ]],
        [11, "Jazz", [
            [1052, "Big Band"],
            [1106, "Avant-Garde Jazz"],
            [1107, "Contemporary Jazz"],
            [1108, "Crossover Jazz"],
            [1109, "Dixieland"],
            [1110, "Fusion"],
            [1111, "Latin Jazz"],
            [1112, "Mainstream Jazz"],
            [1113, "Ragtime"],
            [1114, "Smooth Jazz"],
            [1207, "Hard Bop"],
            [1208, "Trad Jazz"],
            [1209, "Cool"],
        ]],
        [12, "Latino", [
            [1115, "Latin Jazz"],
            [1116, "Contemporary Latin"],
            [1117, "Pop Latino"],
            [1118, "Raíces"],
            [1119, "Reggaeton y Hip-Hop"],
            [1120, "Baladas y Boleros"],
            [1121, "Alternativo & Rock Latino"],
            [1123, "Regional Mexicano"],
            [1124, "Salsa y Tropical"],
        ]],
        [13, "New Age", [
            [1125, "Environmental"],
            [1126, "Healing"],
            [1127, "Meditation"],
            [1128, "Nature"],
            [1129, "Relaxation"],
            [1130, "Travel"],
        ]],
        [14, "Pop", [
            [1131, "Adult Contemporary"],
            [1132, "Britpop"],
            [1133, "Pop/Rock"],
            [1134, "Soft Rock"],
            [1135, "Teen Pop"],
        ]],
        [15, "R&B/Soul", [
            [1136, "Contemporary R&B"],
            [1137, "Disco"],
            [1138, "Doo Wop"],
            [1139, "Funk"],
            [1140, "Motown"],
            [1141, "Neo-Soul"],
            [1142, "Quiet Storm"],
            [1143, "Soul"],
        ]],
        [16, "Soundtrack", [
            [1165, "Foreign Cinema"],
            [1166, "Musicals"],
            [1168, "Original Score"],
            [1169, "Soundtrack"],
            [1172, "TV Soundtrack"],
        ]],
        [17, "Dance", [
            [1044, "Breakbeat"],
            [1045, "Exercise"],
            [1046, "Garage"],
            [1047, "Hardcore"],
            [1048, "House"],
            [1049, "Jungle/Drum'n'bass"],
            [1050, "Techno"],
            [1051, "Trance"],
        ]],
        [18, "Hip-Hop/Rap", [
            [1068, "Alternative Rap"],
            [1069, "Dirty South"],
            [1070, "East Coast Rap"],
            [1071, "Gangsta Rap"],
            [1072, "Hardcore Rap"],
            [1073, "Hip-Hop"],
            [1074, "Latin Rap"],
            [1075, "Old School Rap"],
            [1076, "Rap"],
            [1077, "Underground Rap"],
            [1078, "West Coast Rap"],
        ]],
        [19, "World", [
            [1177, "Afro-Beat"],
            [1178, "Afro-Pop"],
            [1179, "Cajun"],
            [1180, "Celtic"],
            [1181, "Celtic Folk"],
            [1182, "Contemporary Celtic"],
            [1184, "Drinking Songs"],
            [1185, "Indian Pop"],
            [1186, "Japanese Pop"],
            [1187, "Klezmer"],
            [1188, "Polka"],
            [1189, "Traditional Celtic"],
            [1190, "Worldbeat"],
            [1191, "Zydeco"],
            [1195, "Caribbean"],
            [1196, "South America"],
            [1197, "Middle East"],
            [1198, "North America"],
            [1199, "Hawaii"],
            [1200, "Australia"],
            [1201, "Japan"],
            [1202, "France"],
            [1203, "Africa"],
            [1204, "Asia"],
            [1205, "Europe"],
            [1206, "South Africa"],
        ]],
        [20, "Alternative", [
            [1001, "College Rock"],
            [1002, "Goth Rock"],
            [1003, "Grunge"],
            [1004, "Indie Rock"],
            [1005, "New Wave"],
            [1006, "Punk"],
        ]],
        [21, "Rock", [
            [1144, "Adult Alternative"],
            [1145, "American Trad Rock"],
            [1146, "Arena Rock"],
            [1147, "Blues-Rock"],
            [1148, "British Invasion"],
            [1149, "Death Metal/Black Metal"],
            [1150, "Glam Rock"],
            [1151, "Hair Metal"],
            [1152, "Hard Rock"],
            [1153, "Metal"],
            [1154, "Jam Bands"],
            [1155, "Prog-Rock/Art Rock"],
            [1156, "Psychedelic"],
            [1157, "Rock & Roll"],
            [1158, "Rockabilly"],
            [1159, "Roots Rock"],
            [1160, "Singer/Songwriter"],
            [1161, "Southern Rock"],
            [1162, "Surf"],
            [1163, "Tex-Mex"],
        ]],
        [22, "Christian & Gospel", [
            [1094, "CCM"],
            [1095, "Christian Metal"],
            [1096, "Christian Pop"],
            [1097, "Christian Rap"],
            [1098, "Christian Rock"],
            [1099, "Classic Christian"],
            [1100, "Contemporary Gospel"],
            [1101, "Gospel"],
            [1103, "Praise & Worship"],
            [1104, "Southern Gospel"],
            [1105, "Traditional Gospel"],
        ]],
        [23, "Vocal", [
            [1173, "Standards"],
            [1174, "Traditional Pop"],
            [1175, "Vocal Jazz"],
            [1176, "Vocal Pop"],
        ]],
        [24, "Reggae", [
            [1183, "Dancehall"],
            [1192, "Roots Reggae"],
            [1193, "Dub"],
            [1194, "Ska"],
        ]],
        [25, "Easy Listening", [
            [1053, "Bop"],
            [1054, "Lounge"],
            [1055, "Swing"],
        ]],
        [27, "J-Pop", [
        ]],
        [28, "Enka", [
        ]],
        [29, "Anime", [
        ]],
        [30, "Kayokyoku", [
        ]],
        [50, "Fitness & Workout", [
        ]],
        [51, "K-Pop", [
        ]],
        [52, "Karaoke", [
        ]],
        [53, "Instrumental", [
        ]],
        [1122, "Brazilian", [
            [1220, "Axé"],
            [1221, "Bossa Nova"],
            [1222, "Choro"],
            [1223, "Forró"],
            [1224, "Frevo"],
            [1225, "MPB"],
            [1226, "Pagode"],
            [1227, "Samba"],
            [1228, "Sertanejo"],
            [1229, "Baile Funk"],
        ]],
        [50000061, "Spoken Word", [
        ]],
        [50000063, "Disney", [
        ]],
        [50000064, "French Pop", [
        ]],
        [50000066, "German Pop", [
        ]],
        [50000068, "German Folk", [
        ]],
    ]],
    [35, "iPod Games", [
    ]],
    [36, "App Store", [
        [6000, "Business", [
        ]],
        [6001, "Weather", [
        ]],
        [6002, "Utilities", [
        ]],
        [6003, "Travel", [
        ]],
        [6004, "Sports", [
        ]],
        [6005, "Social Networking", [
        ]],
        [6006, "Reference", [
        ]],
        [6007, "Productivity", [
        ]],
        [6008, "Photo & Video", [
        ]],
        [6009, "News", [
        ]],
        [6010, "Navigation", [
        ]],
        [6011, "Music", [
        ]],
        [6012, "Lifestyle", [
        ]],
        [6013, "Health & Fitness", [
        ]],
        [6014, "Games", [
            [7001, "Action"],
            [7002, "Adventure"],
            [7003, "Arcade"],
            [7004, "Board"],
            [7005, "Card"],
            [7006, "Casino"],
            [7007, "Dice"],
            [7008, "Educational"],
            [7009, "Family"],
            [7010, "Kids"],
            [7011, "Music"],
            [7012, "Puzzle"],
            [7013, "Racing"],
            [7014, "Role Playing"],
            [7015, "Simulation"],
            [7016, "Sports"],
            [7017, "Strategy"],
            [7018, "Trivia"],
            [7019, "Word"],
        ]],
        [6015, "Finance", [
        ]],
        [6016, "Entertainment", [
        ]],
        [6017, "Education", [
        ]],
        [6018, "Books", [
        ]],
        [6020, "Medical", [
        ]],
        [6021, "Newsstand", [
            [13001, "News & Politics"],
            [13002, "Fashion & Style"],
            [13003, "Home & Garden"],
            [13004, "Outdoors & Nature"],
            [13005, "Sports & Leisure"],
            [13006, "Automotive"],
            [13007, "Arts & Photography"],
            [13008, "Brides & Weddings"],
            [13009, "Business & Investing"],
            [13010, "Children's Magazines"],
            [13011, "Computers & Internet"],
            [13012, "Cooking, Food & Drink"],
            [13013, "Crafts & Hobbies"],
            [13014, "Electronics & Audio"],
            [13015, "Entertainment"],
            [13017, "Health, Mind & Body"],
            [13018, "History"],
            [13019, "Literary Magazines & Journals"],
            [13020, "Men's Interest"],
            [13021, "Movies & Music"],
            [13023, "Parenting & Family"],
            [13024, "Pets"],
            [13025, "Professional & Trade"],
            [13026, "Regional News"],
            [13027, "Science"],
            [13028, "Teens"],
            [13029, "Travel & Regional"],
            [13030, "Women's Interest"],
        ]],
        [6022, "Catalogs", [
        ]],
    ]],
    [37, "Tones", [
        [8053, "Ringtones", [
            [8001, "Alternative"],
            [8002, "Blues"],
            [8003, "Children's Music"],
            [8004, "Classical"],
            [8005, "Comedy"],
            [8006, "Country"],
            [8007, "Dance"],
            [8008, "Electronic"],
            [8009, "Enka"],
            [8010, "French Pop"],
            [8011, "German Folk"],
            [8012, "German Pop"],
            [8013, "Hip-Hop/Rap"],
            [8014, "Holiday"],
            [8015, "Inspirational"],
            [8016, "J-Pop"],
            [8017, "Jazz"],
            [8018, "Kayokyoku"],
            [8019, "Latin"],
            [8020, "New Age"],
            [8021, "Opera"],
            [8022, "Pop"],
            [8023, "R&B/Soul"],
            [8024, "Reggae"],
            [8025, "Rock"],
            [8026, "Singer/Songwriter"],
            [8027, "Soundtrack"],
            [8028, "Spoken Word"],
            [8029, "Vocal"],
            [8030, "World"],
        ]],
        [8054, "Alert Tones", [
            [8050, "Sound Effects"],
            [8051, "Dialogue"],
            [8052, "Music"],
        ]],
    ]],
    [38, "Books", [
        [9002, "Nonfiction", [
            [10038, "Family & Relationships"],
            [10091, "Philosophy"],
            [10120, "Social Science"],
            [10138, "Transportation"],
            [10149, "True Crime"],
        ]],
        [9003, "Romance", [
            [10056, "Erotica"],
            [10057, "Contemporary"],
            [10058, "Fantasy, Futuristic & Ghost"],
            [10059, "Historical"],
            [10060, "Short Stories"],
            [10061, "Suspense"],
            [10062, "Western"],
        ]],
        [9004, "Travel & Adventure", [
            [10139, "Africa"],
            [10140, "Asia"],
            [10141, "Specialty Travel"],
            [10142, "Canada"],
            [10143, "Caribbean"],
            [10144, "Latin America"],
            [10145, "Essays & Memoirs"],
            [10146, "Europe"],
            [10147, "Middle East"],
            [10148, "United States"],
        ]],
        [9007, "Arts & Entertainment", [
            [10002, "Art & Architecture"],
            [10036, "Theater"],
            [10067, "Games"],
            [10087, "Music"],
            [10089, "Performing Arts"],
            [10092, "Photography"],
        ]],
        [9008, "Biographies & Memoirs", [
        ]],
        [9009, "Business & Personal Finance", [
            [10005, "Industries & Professions"],
            [10006, "Marketing & Sales"],
            [10007, "Small Business & Entrepreneurship"],
            [10008, "Personal Finance"],
            [10009, "Reference"],
            [10010, "Careers"],
            [10011, "Economics"],
            [10012, "Investing"],
            [10013, "Finance"],
            [10014, "Management & Leadership"],
        ]],
        [9010, "Children & Teens", [
            [10081, "Children's Fiction"],
            [10082, "Children's Nonfiction"],
        ]],
        [9012, "Humor", [
        ]],
        [9015, "History", [
            [10070, "Africa"],
            [10071, "Americas"],
            [10072, "Ancient"],
            [10073, "Asia"],
            [10074, "Australia & Oceania"],
            [10075, "Europe"],
            [10076, "Latin America"],
            [10077, "Middle East"],
            [10078, "Military"],
            [10079, "United States"],
            [10080, "World"],
        ]],
        [9018, "Religion & Spirituality", [
            [10003, "Bibles"],
            [10105, "Bible Studies"],
            [10106, "Buddhism"],
            [10107, "Christianity"],
            [10108, "Hinduism"],
            [10109, "Islam"],
            [10110, "Judaism"],
        ]],
        [9019, "Science & Nature", [
            [10085, "Mathematics"],
            [10088, "Nature"],
            [10111, "Astronomy"],
            [10112, "Chemistry"],
            [10113, "Earth Sciences"],
            [10114, "Essays"],
            [10115, "History"],
            [10116, "Life Sciences"],
            [10117, "Physics"],
            [10118, "Reference"],
        ]],
        [9020, "Sci-Fi & Fantasy", [
            [10044, "Fantasy"],
            [10063, "Science Fiction"],
            [10064, "Science Fiction & Literature"],
        ]],
        [9024, "Lifestyle & Home", [
            [10001, "Antiques & Collectibles"],
            [10034, "Crafts & Hobbies"],
            [10068, "Gardening"],
            [10090, "Pets"],
        ]],
        [9025, "Health, Mind & Body", [
            [10004, "Spirituality"],
            [10069, "Health & Fitness"],
            [10094, "Psychology"],
            [10119, "Self-Improvement"],
        ]],
        [9026, "Comics & Graphic Novels", [
            [10015, "Graphic Novels"],
            [10016, "Manga"],
        ]],
        [9027, "Computers & Internet", [
            [10017, "Computers"],
            [10018, "Databases"],
            [10019, "Digital Media"],
            [10020, "Internet"],
            [10021, "Network"],
            [10022, "Operating Systems"],
            [10023, "Programming"],
            [10024, "Software"],
            [10025, "System Administration"],
        ]],
        [9028, "Cookbooks, Food & Wine", [
            [10026, "Beverages"],
            [10027, "Courses & Dishes"],
            [10028, "Special Diet"],
            [10029, "Special Occasions"],
            [10030, "Methods"],
            [10031, "Reference"],
            [10032, "Regional & Ethnic"],
            [10033, "Specific Ingredients"],
        ]],
        [9029, "Professional & Technical", [
            [10035, "Design"],
            [10037, "Education"],
            [10083, "Law"],
            [10086, "Medical"],
            [10137, "Engineering"],
        ]],
        [9030, "Parenting", [
        ]],
        [9031, "Fiction & Literature", [
            [10039, "Action & Adventure"],
            [10040, "African American"],
            [10041, "Religious"],
            [10042, "Classics"],
            [10043, "Erotica"],
            [10045, "Gay"],
            [10046, "Ghost"],
            [10047, "Historical"],
            [10048, "Horror"],
            [10049, "Literary"],
            [10065, "Short Stories"],
            [10084, "Literary Criticism"],
            [10093, "Poetry"],
        ]],
        [9032, "Mysteries & Thrillers", [
            [10050, "Hard-Boiled"],
            [10051, "Historical"],
            [10052, "Police Procedural"],
            [10053, "Short Stories"],
            [10054, "British Detectives"],
            [10055, "Women Sleuths"],
        ]],
        [9033, "Reference", [
            [10066, "Foreign Languages"],
            [10095, "Almanacs & Yearbooks"],
            [10096, "Atlases & Maps"],
            [10097, "Catalogs & Directories"],
            [10098, "Consumer Guides"],
            [10099, "Dictionaries & Thesauruses"],
            [10100, "Encyclopedias"],
            [10101, "Etiquette"],
            [10102, "Quotations"],
            [10103, "Words & Language"],
            [10104, "Writing"],
            [10136, "Study Aids"],
        ]],
        [9034, "Politics & Current Events", [
        ]],
        [9035, "Sports & Outdoors", [
            [10121, "Baseball"],
            [10122, "Basketball"],
            [10123, "Coaching"],
            [10124, "Extreme Sports"],
            [10125, "Football"],
            [10126, "Golf"],
            [10127, "Hockey"],
            [10128, "Mountaineering"],
            [10129, "Outdoors"],
            [10130, "Racket Sports"],
            [10131, "Reference"],
            [10132, "Soccer"],
            [10133, "Training"],
            [10134, "Water Sports"],
            [10135, "Winter Sports"],
        ]],
    ]],
    [39, "Mac App Store", [
        [12001, "Business", [
        ]],
        [12002, "Developer Tools", [
        ]],
        [12003, "Education", [
        ]],
        [12004, "Entertainment", [
        ]],
        [12005, "Finance", [
        ]],
        [12006, "Games", [
            [12201, "Action"],
            [12202, "Adventure"],
            [12203, "Arcade"],
            [12204, "Board"],
            [12205, "Card"],
            [12206, "Casino"],
            [12207, "Dice"],
            [12208, "Educational"],
            [12209, "Family"],
            [12210, "Kids"],
            [12211, "Music"],
            [12212, "Puzzle"],
            [12213, "Racing"],
            [12214, "Role Playing"],
            [12215, "Simulation"],
            [12216, "Sports"],
            [12217, "Strategy"],
            [12218, "Trivia"],
            [12219, "Word"],
        ]],
        [12007, "Health & Fitness", [
        ]],
        [12008, "Lifestyle", [
        ]],
        [12010, "Medical", [
        ]],
        [12011, "Music", [
        ]],
        [12012, "News", [
        ]],
        [12013, "Photography", [
        ]],
        [12014, "Productivity", [
        ]],
        [12015, "Reference", [
        ]],
        [12016, "Social Networking", [
        ]],
        [12017, "Sports", [
        ]],
        [12018, "Travel", [
        ]],
        [12019, "Utilities", [
        ]],
        [12020, "Video", [
        ]],
        [12021, "Weather", [
        ]],
        [12022, "Graphics & Design", [
        ]],
    ]],
    [40, "Textbooks", [
    ]],
    [40000000, "iTunes U", [
        [40000001, "Business", [
            [40000002, "Economics"],
            [40000003, "Finance"],
            [40000004, "Hospitality"],
            [40000005, "Management"],
            [40000006, "Marketing"],
            [40000007, "Personal Finance"],
            [40000008, "Real Estate"],
            [40000121, "Entrepreneurship"],
        ]],
        [40000009, "Engineering", [
            [40000010, "Chemical & Petroleum Engineering"],
            [40000011, "Civil Engineering"],
            [40000012, "Computer Science"],
            [40000013, "Electrical Engineering"],
            [40000014, "Environmental Engineering"],
            [40000015, "Mechanical Engineering"],
        ]],
        [40000016, "Art & Architecture", [
            [40000017, "Architecture"],
            [40000019, "Art History"],
            [40000020, "Dance"],
            [40000021, "Film"],
            [40000022, "Design"],
            [40000023, "Interior Design"],
            [40000024, "Music"],
            [40000025, "Theater"],
            [40000116, "Culinary Arts"],
            [40000117, "Fashion"],
            [40000118, "Media Arts"],
            [40000119, "Photography"],
            [40000120, "Visual Art"],
        ]],
        [40000026, "Health & Medicine", [
            [40000027, "Anatomy & Physiology"],
            [40000028, "Behavioral Science"],
            [40000029, "Dentistry"],
            [40000030, "Diet & Nutrition"],
            [40000031, "Emergency Medicine"],
            [40000032, "Genetics"],
            [40000033, "Gerontology"],
            [40000034, "Health & Exercise Science"],
            [40000035, "Immunology"],
            [40000036, "Neuroscience"],
            [40000037, "Pharmacology & Toxicology"],
            [40000038, "Psychiatry"],
            [40000039, "Global Health"],
            [40000040, "Radiology"],
            [40000129, "Nursing"],
        ]],
        [40000041, "History", [
            [40000042, "Ancient History"],
            [40000043, "Medieval History"],
            [40000044, "Military History"],
            [40000045, "Modern History"],
            [40000046, "African History"],
            [40000047, "Asia-Pacific History"],
            [40000048, "European History"],
            [40000049, "Middle Eastern History"],
            [40000050, "North American History"],
            [40000051, "South American History"],
        ]],
        [40000053, "Communications & Media", [
            [40000122, "Broadcasting"],
            [40000123, "Digital Media"],
            [40000124, "Journalism"],
            [40000125, "Photojournalism"],
            [40000126, "Print"],
            [40000127, "Speech"],
            [40000128, "Writing"],
        ]],
        [40000054, "Philosophy", [
            [40000146, "Aesthetics"],
            [40000147, "Epistemology"],
            [40000148, "Ethics"],
            [40000149, "Metaphysics"],
            [40000150, "Political Philosophy"],
            [40000151, "Logic"],
            [40000152, "Philosophy of Language"],
            [40000153, "Philosophy of Religion"],
        ]],
        [40000055, "Religion & Spirituality", [
            [40000156, "Buddhism"],
            [40000157, "Christianity"],
            [40000158, "Comparative Religion"],
            [40000159, "Hinduism"],
            [40000160, "Islam"],
            [40000161, "Judaism"],
            [40000162, "Other Religions"],
            [40000163, "Spirituality"],
        ]],
        [40000056, "Language", [
            [40000057, "African Languages"],
            [40000058, "Ancient Languages"],
            [40000061, "English"],
            [40000063, "French"],
            [40000064, "German"],
            [40000065, "Italian"],
            [40000066, "Linguistics"],
            [40000068, "Spanish"],
            [40000069, "Speech Pathology"],
            [40000130, "Arabic"],
            [40000131, "Chinese"],
            [40000132, "Hebrew"],
            [40000133, "Hindi"],
            [40000134, "Indigenous Languages"],
            [40000135, "Japanese"],
            [40000136, "Korean"],
            [40000137, "Other Languages"],
            [40000138, "Portuguese"],
            [40000139, "Russian"],
        ]],
        [40000070, "Literature", [
            [40000071, "Anthologies"],
            [40000072, "Biography"],
            [40000073, "Classics"],
            [40000074, "Literary Criticism"],
            [40000075, "Fiction"],
            [40000076, "Poetry"],
            [40000145, "Comparative Literature"],
        ]],
        [40000077, "Mathematics", [
            [40000078, "Advanced Mathematics"],
            [40000079, "Algebra"],
            [40000080, "Arithmetic"],
            [40000081, "Calculus"],
            [40000082, "Geometry"],
            [40000083, "Statistics"],
        ]],
        [40000084, "Science", [
            [40000085, "Agricultural"],
            [40000086, "Astronomy"],
            [40000087, "Atmosphere"],
            [40000088, "Biology"],
            [40000089, "Chemistry"],
            [40000090, "Ecology"],
            [40000091, "Geography"],
            [40000092, "Geology"],
            [40000093, "Physics"],
            [40000164, "Environment"],
        ]],
        [40000094, "Psychology & Social Science", [
            [40000098, "Psychology"],
            [40000099, "Social Welfare"],
            [40000100, "Sociology"],
            [40000154, "Archaeology"],
            [40000155, "Anthropology"],
        ]],
        [40000101, "Society", [
            [40000103, "Asia Pacific Studies"],
            [40000104, "European Studies"],
            [40000105, "Indigenous Studies"],
            [40000106, "Latin & Caribbean Studies"],
            [40000107, "Middle Eastern Studies"],
            [40000108, "Women's Studies"],
            [40000165, "African Studies"],
            [40000166, "American Studies"],
            [40000167, "Cross-cultural Studies"],
            [40000168, "Immigration & Emigration"],
            [40000169, "Race & Ethnicity Studies"],
            [40000170, "Sexuality Studies"],
        ]],
        [40000109, "Teaching & Learning", [
            [40000110, "Curriculum & Teaching"],
            [40000111, "Educational Leadership"],
            [40000112, "Family & Childcare"],
            [40000113, "Learning Resources"],
            [40000114, "Psychology & Research"],
            [40000115, "Special Education"],
            [40000171, "Educational Technology"],
            [40000172, "Information/Library Science"],
        ]],
        [40000140, "Law & Politics", [
            [40000095, "Law"],
            [40000096, "Political Science"],
            [40000097, "Public Administration"],
            [40000141, "Foreign Policy & International Relations"],
            [40000142, "Local Governments"],
            [40000143, "National Governments"],
            [40000144, "World Affairs"],
        ]],
    ]],
    [50000024, "Audiobooks", [
        [74, "News", [
        ]],
        [75, "Programs & Performances", [
        ]],
        [50000040, "Fiction", [
        ]],
        [50000041, "Arts & Entertainment", [
        ]],
        [50000042, "Biography & Memoir", [
        ]],
        [50000043, "Business", [
        ]],
        [50000044, "Kids & Young Adults", [
        ]],
        [50000045, "Classics", [
        ]],
        [50000046, "Comedy", [
        ]],
        [50000047, "Drama & Poetry", [
        ]],
        [50000048, "Speakers & Storytellers", [
        ]],
        [50000049, "History", [
        ]],
        [50000050, "Languages", [
        ]],
        [50000051, "Mystery", [
        ]],
        [50000052, "Nonfiction", [
        ]],
        [50000053, "Religion & Spirituality", [
        ]],
        [50000054, "Science", [
        ]],
        [50000055, "Sci-Fi & Fantasy", [
        ]],
        [50000056, "Self Development", [
        ]],
        [50000057, "Sports", [
        ]],
        [50000058, "Technology", [
        ]],
        [50000059, "Travel & Adventure", [
        ]],
        [50000069, "Romance", [
        ]],
        [50000070, "Audiobooks Latino", [
        ]],
    ]],
    ]:
    mp4v2_categories_id_map[cat_id] = cat_name
    mp4v2_categories.add(cat_name)
    for genre_id, genre_name, subgenres_info in genres_info:
        mp4v2_genres_id_map[genre_id] = genre_name
        mp4v2_genres.add(genre_name)
        mp4v2_genres_info[genre_id] = {
                'cat_id': cat_id,
                'genre_id': genre_id,
                'genre_name': genre_name,
                'sub_genres_info': {},
                }
        for subgenre_id, subgenre_name in subgenres_info:
            mp4v2_genres_id_map[subgenre_id] = subgenre_name
            mp4v2_genres.add(subgenre_name)
            mp4v2_genres_info[genre_id]['sub_genres_info'][subgenre_id] ={
                    'cat_id': cat_id,
                    'parent_genre_id': genre_id,
                    'genre_id': subgenre_id,
                    'genre_name': subgenre_name,
                    }

# }}}
# tag_stik_info (iTunes Media Type) {{{

tag_stik_info = {
        'stik': {},
        'map': {},
        }
# mp4v2 source
# AtomicParsley source
# https://code.google.com/p/mp4v2/wiki/iTunesMetadata
# TODO http://help.mp3tag.de/main_tags.html {{{
# ITUNESMEDIATYPE
#   Syntax: Enter the media type
#   Possible values: Movie, Normal, Audiobook, Music Video, Short Film, TV Show, Ringtone, iTunes U
# }}}
for element, stik, mp4v2_arg, atomicparsley_arg, aliases in [
    ["Movie (Old)",        0,      "oldmovie",   "Movie",            []],
    ["Normal (Music)",     1,      "normal",     "Normal",           ["music"]],
    ["Audio Book",         2,      "audiobook",  "Audiobook",        []],
    ["Whacked Bookmark",   5,      None,         "Whacked Bookmark", []],
    ["Music Video",        6,      "musicvideo", "Music Video",      []],
    ["Movie",              9,      "movie",      "Short Film",       []],
    ["TV Show",            10,     "tvshow",     "TV Show",          []],
    ["Booklet",            11,     "booklet",    "Bookley",          []],
    ["Ringtone",           14,     "ringtone",   None,               []],
    ["iTunes U",           'TODO', None,         None,               []],
    ["Voice Memo",         'TODO', None,         None,               []],
    ["Podcast",            'TODO', None,         None,               []],
    ]:
    if stik == 'TODO':
        continue
    for v in ['element', 'stik', 'mp4v2_arg', 'atomicparsley_arg', 'aliases']:
        t = locals()[v]
        if t is not None:
            tag_stik_info['stik'].setdefault(stik, {})
            tag_stik_info['stik'][stik][v] = t
    for t in [element, mp4v2_arg, atomicparsley_arg] + aliases:
        if t is not None:
            tag_stik_info['map'][re.sub(r'\s', '', t.lower())] = stik
            tag_stik_info['map'][t.lower()] = stik
            tag_stik_info['map'][t] = stik

# }}}
# tag_info {{{

# http://id3.org/id3v2-00 (ID3 tag version 2 - Informal Standard) {{{
#class ID3v2TagEnum(enum.Enum):
#    4.19  BUF Recommended buffer size
#
#    4.17  CNT Play counter
#    4.11  COM Comments
#    4.21  CRA Audio encryption
#    4.20  CRM Encrypted meta frame
#
#    4.6   ETC Event timing codes
#    4.13  EQU Equalization
#
#    4.16  GEO General encapsulated object
#
#    4.4   IPL Involved people list
#
#    4.22  LNK Linked information
#
#    4.5   MCI Music CD Identifier
#    4.7   MLL MPEG location lookup table
#
#    4.15  PIC Attached picture
#    4.18  POP Popularimeter
#
#    4.14  REV Reverb
#    4.12  RVA Relative volume adjustment
#
#    4.10  SLT Synchronized lyric/text
#    4.8   STC Synced tempo codes
#
#    4.2.1 TAL Album/Movie/Show title
#    4.2.1 TBP BPM (Beats Per Minute)
#    4.2.1 TCM Composer
#    4.2.1 TCO Content type
#    4.2.1 TCR Copyright message
#    4.2.1 TDA Date
#    4.2.1 TDY Playlist delay
#    4.2.1 TEN Encoded by
#    4.2.1 TFT File type
#    4.2.1 TIM Time
#    4.2.1 TKE Initial key
#    4.2.1 TLA Language(s)
#    4.2.1 TLE Length
#    4.2.1 TMT Media type
#    4.2.1 TOA Original artist(s)/performer(s)
#    4.2.1 TOF Original filename
#    4.2.1 TOL Original Lyricist(s)/text writer(s)
#    4.2.1 TOR Original release year
#    4.2.1 TOT Original album/Movie/Show title
#    4.2.1 TP1 Lead artist(s)/Lead performer(s)/Soloist(s)/Performing group
#    4.2.1 TP2 Band/Orchestra/Accompaniment
#    4.2.1 TP3 Conductor/Performer refinement
#    4.2.1 TP4 Interpreted, remixed, or otherwise modified by
#    4.2.1 TPA Part of a set
#    4.2.1 TPB Publisher
#    4.2.1 TRC ISRC (International Standard Recording Code)
#    4.2.1 TRD Recording dates
#    4.2.1 TRK Track number/Position in set
#    4.2.1 TSI Size
#    4.2.1 TSS Software/hardware and settings used for encoding
#    4.2.1 TT1 Content group description
#    4.2.1 TT2 Title/Songname/Content description
#    4.2.1 TT3 Subtitle/Description refinement
#    4.2.1 TXT Lyricist/text writer
#    4.2.2 TXX User defined text information frame
#    4.2.1 TYE Year
#
#    4.1   UFI Unique file identifier
#    4.9   ULT Unsychronized lyric/text transcription
#
#    4.3.1 WAF Official audio file webpage
#    4.3.1 WAR Official artist/performer webpage
#    4.3.1 WAS Official audio source webpage
#    4.3.1 WCM Commercial information
#    4.3.1 WCP Copyright/Legal information
#    4.3.1 WPB Publishers official webpage
#    4.3.2 WXX User defined URL link frame
# }}}

# http://id3.org/id3v2.3.0 {{{
#    4.20    AENC    [[#sec4.20|Audio encryption]]
#    4.15    APIC    [#sec4.15 Attached picture]
#    4.11    COMM    [#sec4.11 Comments]
#    4.25    COMR    [#sec4.25 Commercial frame]
#    4.26    ENCR    [#sec4.26 Encryption method registration]
#    4.13    EQUA    [#sec4.13 Equalization]
#    4.6     ETCO    [#sec4.6 Event timing codes]
#    4.16    GEOB    [#sec4.16 General encapsulated object]
#    4.27    GRID    [#sec4.27 Group identification registration]
#    4.4     IPLS    [#sec4.4 Involved people list]
#    4.21    LINK    [#sec4.21 Linked information]
#    4.5     MCDI    [#sec4.5 Music CD identifier]
#    4.7     MLLT    [#sec4.7 MPEG location lookup table]
#    4.24    OWNE    [#sec4.24 Ownership frame]
#    4.28    PRIV    [#sec4.28 Private frame]
#    4.17    PCNT    [#sec4.17 Play counter]
#    4.18    POPM    [#sec4.18 Popularimeter]
#    4.22    POSS    [#sec4.22 Position synchronisation frame]
#    4.19    RBUF    [#sec4.19 Recommended buffer size]
#    4.12    RVAD    [#sec4.12 Relative volume adjustment]
#    4.14    RVRB    [#sec4.14 Reverb]
#    4.10    SYLT    [#sec4.10 Synchronized lyric/text]
#    4.8     SYTC    [#sec4.8 Synchronized tempo codes]
#    4.2.1   TALB    [#TALB Album/Movie/Show title]
#    4.2.1   TBPM    [#TBPM BPM (beats per minute)]
#    4.2.1   TCOM    [#TCOM Composer]
#    4.2.1   TCON    [#TCON Content type]
#    4.2.1   TCOP    [#TCOP Copyright message]
#    4.2.1   TDAT    [#TDAT Date]
#    4.2.1   TDLY    [#TDLY Playlist delay]
#    4.2.1   TENC    [#TENC Encoded by]
#    4.2.1   TEXT    [#TEXT Lyricist/Text writer]
#    4.2.1   TFLT    [#TFLT File type]
#    4.2.1   TIME    [#TIME Time]
#    4.2.1   TIT1    [#TIT1 Content group description]
#    4.2.1   TIT2    [#TIT2 Title/songname/content description]
#    4.2.1   TIT3    [#TIT3 Subtitle/Description refinement]
#    4.2.1   TKEY    [#TKEY Initial key]
#    4.2.1   TLAN    [#TLAN Language(s)]
#    4.2.1   TLEN    [#TLEN Length]
#    4.2.1   TMED    [#TMED Media type]
#    4.2.1   TOAL    [#TOAL Original album/movie/show title]
#    4.2.1   TOFN    [#TOFN Original filename]
#    4.2.1   TOLY    [#TOLY Original lyricist(s)/text writer(s)]
#    4.2.1   TOPE    [#TOPE Original artist(s)/performer(s)]
#    4.2.1   TORY    [#TORY Original release year]
#    4.2.1   TOWN    [#TOWN File owner/licensee]
#    4.2.1   TPE1    [#TPE1 Lead performer(s)/Soloist(s)]
#    4.2.1   TPE2    [#TPE2 Band/orchestra/accompaniment]
#    4.2.1   TPE3    [#TPE3 Conductor/performer refinement]
#    4.2.1   TPE4    [#TPE4 Interpreted, remixed, or otherwise modified by]
#    4.2.1   TPOS    [#TPOS Part of a set]
#    4.2.1   TPUB    [#TPUB Publisher]
#    4.2.1   TRCK    [#TRCK Track number/Position in set]
#    4.2.1   TRDA    [#TRDA Recording dates]
#    4.2.1   TRSN    [#TRSN Internet radio station name]
#    4.2.1   TRSO    [#TRSO Internet radio station owner]
#    4.2.1   TSIZ    [#TSIZ Size]
#    4.2.1   TSRC    [#TSRC ISRC (international standard recording code)]
#    4.2.1   TSSE    [#TSEE Software/Hardware and settings used for encoding]
#    4.2.1   TYER    [#TYER Year]
#    4.2.2   TXXX    [#TXXX User defined text information frame]
#    4.1     UFID    [#sec4.1 Unique file identifier]
#    4.23    USER    [#sec4.23 Terms of use]
#    4.9     USLT    [#sec4.9 Unsychronized lyric/text transcription]
#    4.3.1   WCOM    [#WCOM Commercial information]
#    4.3.1   WCOP    [#WCOP Copyright/Legal information]
#    4.3.1   WOAF    [#WOAF Official audio file webpage]
#    4.3.1   WOAR    [#WOAR Official artist/performer webpage]
#    4.3.1   WOAS    [#WOAS Official audio source webpage]
#    4.3.1   WORS    [#WORS Official internet radio station homepage]
#    4.3.1   WPAY    [#WPAY Payment]
#    4.3.1   WPUB    [#WPUB Publishers official webpage]
#    4.3.2   WXXX    [#WXXX User defined URL link frame]
# }}}

# https://code.google.com/p/mp4v2/wiki/iTunesMetadata
tag_info = {
        'tags': {},
        'map': {},
        }
for element, mp4v2_tag, data_type, mp4v2_name, id3v2_20_tag, id3v2_30_tag, aliases in [
    # title = mp4v2 song
    ["Name",                   "©nam",                     "utf-8",                    "title",                    "TT2",                      "TIT2",           ["Song", 'song', "Title", "name"]],
    ["Artist",                 "©ART",                     "utf-8",                    "artist",                   "TP1",                      "TPE1",           []],
    ["Album Artist",           "aART",                     "utf-8",                    "albumArtist",              "TP2",                      "TPE2",           []],
    # albumtitle = mp4v2 album
    ["Album",                  "©alb",                     "utf-8",                    "albumtitle",               "TAL",                      "TALB",           ["album"]],
    ["Grouping",               "©grp",                     "utf-8",                    "grouping",                 "TT1",                      "TIT1",           []],
    # composer = mp4v2 writer
    ["Composer",               "©wrt",                     "utf-8",                    "composer",                 "TCM",                      "TCOM",           ["writer"]],
    ["Comment",                "©cmt",                     "utf-8",                    "comments",                 None,                       None,             []],
    ["Genre ID",               "gnre",                     "enum",                     "genreID",                  None,                       None,             []],
    ["Genre",                  "©gen",                     "utf-8",                    "genre",                    "TCO",                      "TCON",           ["GenreType"]],
    # date = mp4v2 year
    ["Release Date",           "©day",                     "utf-8",                    "date",                     "TDA",                      "TDAT",           ["releaseDate", "Date", "date"]],
    ["Track Number",           "trkn",                     "binary",                   "track",                    None,                       None,             []],
    ["Total Tracks",           None,                       "int32",                    "tracks",                   None,                       None,             []],
    ["track_slash_tracks",     None,                       "utf-8",                    None,                       "TPK",                      "TRCK",           []],
    ["Disc Number",            "disk",                     "binary",                   "disk",                     None,                       None,             ["disc"]],
    ["Total Discs",            None,                       "int32",                    "disks",                    None,                       None,             ["discs"]],
    ["disk_slash_disks",       None,                       "utf-8",                    None,                       "TPA",                      "TPOS",           []],
    ["Tempo (bpm)",            "tmpo",                     "int16",                    "tempo",                    None,                       None,             []],
    ["Compilation",            "cpil",                     "bool8",                    "compilation",              None,                       None,             []],
    ["TV Show Name",           "tvsh",                     "utf-8",                    "tvShow",                   None,                       None,             []],
    ["TV Episode ID",          "tven",                     "utf-8",                    "tvEpisodeID",              None,                       None,             []],
    ["TV Season",              "tvsn",                     "int32",                    "tvSeason",                 None,                       None,             []],
    ["TV Episode",             "tves",                     "int32",                    "tvEpisode",                None,                       None,             []],
    ["TV Network",             "tvnn",                     "utf-8",                    "tvNetwork",                None,                       None,             []],
    ["Description",            "desc",                     "utf-8",                    "description",              None,                       None,             []],
    ["Long Description",       "ldes",                     "utf-8",                    "longDescription",          None,                       None,             []],
    ["Lyrics",                 "©lyr",                     "utf-8",                    "lyrics",                   None,                       None,             []],
    # sortTitle = mp4v2 sortName
    ["Sort Name",              "sonm",                     "utf-8",                    "sortTitle",                None,                       None,             ["sortname"]],
    ["Sort Artist",            "soar",                     "utf-8",                    "sortArtist",               None,                       None,             []],
    ["Sort Album Artist",      "soaa",                     "utf-8",                    "sortAlbumArtist",          None,                       None,             []],
    # sortAlbumTitle = mp4v2 sortAlbum
    ["Sort Album",             "soal",                     "utf-8",                    "sortAlbumTitle",           None,                       None,             ["sortalbum"]],
    ["Sort Composer",          "soco",                     "utf-8",                    "sortComposer",             None,                       None,             ["sortwriter"]],
    ["Sort Show",              "sosn",                     "utf-8",                    "sortTVShow",               None,                       None,             []],
    ["Cover Art",              "covr",                     "picture",                  "picture",                  "PIC",                      "APIC",           []], # TODO artwork?
    ["Copyright",              "cprt",                     "utf-8",                    "copyright",                "TCR",                      "TCOP",           []],
    ["Encoding Tool",          "©too",                     "utf-8",                    "tool",                     None,                       None,             ["Encoded with", "encodingTool", "encoder"]],
    ["Encoded By",             "©enc",                     "utf-8",                    "encodedBy",                "TEN",                      "TENC",           []],
    ["Purchase Date",          "purd",                     "utf-8",                    "purchaseDate",             None,                       None,             []],
    ["Podcast",                "pcst",                     "bool8",                    "podcast",                  None,                       None,             []],
    ["Podcast URL",            "purl",                     "utf-8",                    "podcastUrl",               None,                       None,             []],
    ["Keywords",               "keyw",                     "utf-8",                    "keywords",                 None,                       None,             []],
    ["Category",               "catg",                     "utf-8",                    "category",                 None,                       None,             []],
    ["HD Video",               "hdvd",                     "bool8",                    "hdVideo",                  None,                       None,             []],
    ["Media Type",             "stik",                     "enum8",                    "type",                     "TMT",                      "TMED",           ["mediaType"]],
    ["Content Rating",         "rtng",                     "int8",                     "contentRating",            None,                       None,             []],
    ["Gapless Playback",       "pgap",                     "bool8",                    "gapless",                  None,                       None,             []],
    ["Purchase Account",       "apID",                     "utf-8",                    "iTunesAccount",            None,                       None,             []],
    ["Account Type",           "akID",                     "int8",                     "iTunesAccountType",        None,                       None,             []],
    ["Catalog ID",             "cnID",                     "int32",                    "iTunesCatalogID",          None,                       None,             []],
    ["Country Code",           "sfID",                     "int32",                    "iTunesCountry",            None,                       None,             []],
    ["Artist ID",              "atID",                     "int32",                    "artistID",                 None,                       None,             []],
    ["Alnum ID",               "plID",                     "int64",                    "plID",                     None,                       None,             []],
    ["Genre ID",               "geID",                     "int32",                    "geID",                     None,                       None,             []],
    ["Subtitle",               "©st3",                     "utf-8",                    "subtitle",                 "TT3",                      "TIT3",           []],
    ]:
    tag = (mp4v2_name or element).lower()
    for v in ["element", "mp4v2_tag", "data_type", "mp4v2_name", "id3v2_20_tag", "id3v2_30_tag", "aliases"]:
        t = locals()[v]
        if t is not None:
            tag_info['tags'].setdefault(tag, {})
            tag_info['tags'][tag][v] = t
    for t in [element, mp4v2_tag, mp4v2_name, id3v2_20_tag, id3v2_30_tag] + aliases:
        if t is not None:
            tag_info['map'][t.lower()] = tag
            tag_info['map'][t] = tag

# }}}

# class AudioAppSupport {{{

class AudioAppSupport(types.SimpleNamespace):

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
# class AudioFormatSupport {{{

class AudioFormatSupport(types.SimpleNamespace):

    def __init__(self, format, description=None, can_read=False, can_write=False, extensions=None):
        super().__init__(
                format=format,
                extensions=set(extensions) if extensions is not None else set(),
                can_read=can_read,
                can_write=can_write,
                description=description if description is not None else format,
                )

# }}}
# get_sox_app_support {{{

_sox_app_support = None
def get_sox_app_support():
    global _sox_app_support
    if _sox_app_support is None:
        _sox_app_support = AudioAppSupport('sox')
        if shutil.which('sox'):
            # sox --help-format all {{{
            try:
                out = dbg_exec_cmd(['sox', '--help-format', 'all'])
            except subprocess.CalledProcessError as e:
                if e.returncode == 1:
                    # NOTE: sox will exit with code 1
                    out = e.output
                else:
                    raise
            out = clean_cmd_output(out)
            parser = lines_parser(out.splitlines())
            while parser.advance():
                if parser.line == '':
                    pass
                elif parser.re_search(r'^Format: (\S+)$'):
                    # Format: wav
                    fmt = parser.match.group(1)
                    support = AudioFormatSupport(
                            format=fmt,
                            extensions=['.' + fmt],
                            )
                    _sox_app_support.formats[fmt] = support
                elif parser.re_search(r'^Description: (.+)$'):
                    # Description: Microsoft audio format
                    support.description = parser.match.group(1)
                elif parser.re_search(r'^Also handles: (.+)$'):
                    # Also handles: wavpcm amb
                    support.extensions |= set([
                        '.' + ext
                        for ext in parser.match.group(1).split()])
                elif parser.re_search(r'^Reads: yes$'):
                    # Reads: yes
                    support.can_read = True
                elif parser.re_search(r'^Writes: yes$'):
                    # theoritical... not seen
                    support.can_write = True
                elif parser.re_search(r'^Writes: no$'):
                    # Writes: no
                    support.can_write = False
                elif parser.re_search(r'^Writes:$'):
                    # Writes:
                    support.can_write = True
                    #   16-bit Signed Integer PCM (16-bit precision)
                    #   24-bit Signed Integer PCM (24-bit precision)
                    #   32-bit Signed Integer PCM (32-bit precision)
                    # ...
                else:
                    #log.debug('TODO: %s', parser.line)
                    # TODO
                    pass
            # }}}
            # sox --help {{{
            out = dbg_exec_cmd(['sox', '--help'])
            out = clean_cmd_output(out)
            parser = lines_parser(out.splitlines())
            while parser.advance():
                if parser.line == '':
                    pass
                elif parser.re_search(r'^AUDIO FILE FORMATS: (.+)$'):
                    # AUDIO FILE FORMATS: 8svx aif aifc ...
                    for fmt in parser.match.group(1).split():
                        if fmt not in _sox_app_support.formats:
                            # Assume can_read and can_write
                            _sox_app_support.formats[fmt] = AudioFormatSupport(
                                    format=fmt,
                                    extensions=['.' + fmt],
                                    can_read=True,
                                    can_write=True,
                                    )
                else:
                    #log.debug('TODO: %s', parser.line)
                    # TODO
                    pass
            # }}}
    return _sox_app_support

# }}}
# get_mp4v2_app_support {{{

_mp4v2_app_support = None
def get_mp4v2_app_support():
    global _mp4v2_app_support
    if _mp4v2_app_support is None:
        _mp4v2_app_support = AudioAppSupport('mp4v2')
        for fmt in ('mp4', 'm4a', 'm4p', 'm4b', 'm4r', 'm4v'):
            support = AudioFormatSupport(
                    format=fmt,
                    extensions=['.' + fmt],
                    can_read=True,
                    can_write=True,
                    )
            _mp4v2_app_support.formats[fmt] = support
    return _mp4v2_app_support

# }}}

def parse_disk_track(dt, default=None):
    if dt is None:
        return (default, default)
    if isinstance(dt, int):
        return (dt, default)
    m = re.match(r'^(?:(\d+)?(?:/(\d+)?)?)?$', dt)
    if not m:
        raise ValueError(dt)
    n, t = m.groups()
    n = int(n) if n is not None else default
    t = int(t) if t is not None else default
    return (n, t)

def soundfilecmp(f1, f2):
    v1 = parse_disk_track(f1.tags.get('disk', 0), default=0)[0]
    v2 = parse_disk_track(f2.tags.get('disk', 0), default=0)[0]
    c = genericcmp(v1, v2)
    if c:
        return c
    v1 = parse_disk_track(f1.tags.get('track', 0), default=0)[0]
    v2 = parse_disk_track(f2.tags.get('track', 0), default=0)[0]
    c = genericcmp(v1, v2)
    if c:
        return c
    return dictionarycmp(f1.file_name, f2.file_name)

# mp4chaps_format_time_offset {{{

def mp4chaps_format_time_offset(offset):
    s, ms = ('%.3f' % (offset,)).split('.')
    s = int(s)
    m = s / 60
    s = s % 60
    h = m / 60
    m = m % 60
    return '%02d:%02d:%02d.%s' % (h, m, s, ms)

# }}}

# AudioType {{{

@functools.total_ordering
class AudioType(enum.Enum):
    aac = 'aac'
    he_aac = 'he-aac'
    lc_aac = 'lc-aac'
    mp2 = 'mp2'
    mp3 = 'mp3'
    vorbis = 'vorbis'
    wav = 'wav'
    ac3 = 'ac3'

    def __eq__(self, other):
        try:
            other = AudioType(other)
        except ValueError:
            return NotImplemented
        return self.value == other.value

    def __lt__(self, other):
        other = AudioType(other)
        return self.value < other.value

    def __hash__(self):
        return hash(id(self))

    def __new(cls, value):
        if type(value) is str:
            value = value.strip()
            for pattern, new_value in (
                (r'^MPEG-4 AAC HE$', 'he-aac'),
                (r'^MPEG-4 AAC LC$', 'lc-aac'),
                (r'^MPEG1/layer III$', 'mp3'),
                (r'^MPEG audio \(layer I, II or III\)$', 'mp3'),
                (r'^Vorbis audio$', 'vorbis'),
                (r'^Vorbis$', 'vorbis'),
                (r'^WAVE audio$', 'wav'),
                (r'^m4a$', 'aac'),
                (r'^m4b$', 'aac'),
                (r'^ogg$', 'vorbis'),
                ):
                m = re.search(pattern, value)
                if m:
                    value = new_value
                    break
        return super().__new__(cls, value)

AudioType.__new__ = AudioType._AudioType__new

# }}}

# class SoundFile {{{

class SoundFile(BinaryFile):

    class Chapter(collections.namedtuple('Chapter', ['time', 'name'])):
        __slots__ = ()

    @property
    def audio_type(self):
        audio_type = getattr(self, '_audio_type', None)
        if audio_type is None:
            ext = os.path.splitext(self.file_name)[1]
            if ext:
                audio_type = AudioType(ext[1:])
        return audio_type

    @audio_type.setter
    def audio_type(self, value):
        if value is not None:
            value = AudioType(value)
        self._audio_type = value

    def __init__(self, file_name, cover_file=None, *args, **kwargs):
        super().__init__(file_name=file_name, *args, **kwargs)
        self.cover_file = cover_file
        self.tags = TrackTags()

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
        if not self.tags.set_tag(self.dest, values[0]):
            raise ValueError('Failed to set tag %r to %r' % (self.dest, values[0]))

# }}}
# class ArgparseTypeListAction {{{

class ArgparseTypeListAction(argparse.Action):

    def __init__(self,
                 option_strings,
                 dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS,
                 help="display valid audio book types and exit"):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        buf = 'Types:'
        for stik in sorted(tag_stik_info['stik'].keys()):
            buf += '\n  %-2d \'%s\'' % (stik, tag_stik_info['stik'][stik]['element'])
        parser._print_message(buf, _sys.stdout)
        parser.exit()

# }}}
# class ArgparseGenreListAction {{{

class ArgparseGenreListAction(argparse.Action):

    def __init__(self,
                 option_strings,
                 cat_id='Audiobooks',
                 dest=argparse.SUPPRESS,
                 default=argparse.SUPPRESS,
                 help="display valid audio book genres and exit"):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help)
        self.cat_id = cat_id

    def __call__(self, parser, namespace, values, option_string=None):
        cat_id = self.cat_id
        try:
            cat_name = mp4v2_categories_id_map[cat_id]
        except KeyError:
            for cat_id2, cat_name in mp4v2_categories_id_map.items():
                if cat_name == cat_id:
                    cat_id = cat_id2
                    break
            else:
                raise Exception('Unknown category \'%s\'' % (cat_id,))
        buf = 'Genres for category \'%s\'  (%s):' % (cat_name, cat_id)
        for genre_id in sorted(mp4v2_genres_info.keys()):
            if mp4v2_genres_info[genre_id]['cat_id'] != cat_id:
                continue
            buf += '\n  %-8d \'%s\'' % (genre_id, mp4v2_genres_info[genre_id]['genre_name'])
            for subgenre_id in sorted(mp4v2_genres_info[genre_id]['sub_genres_info'].keys()):
                buf += '\n    %-8i \'%s\'' % (subgenre_id, mp4v2_genres_info[genre_id]['sub_genres_info'][subgenre_id]['genre_name'])
        parser._print_message(buf, _sys.stdout)
        parser.exit()

# }}}

def date_to_year(date):
    m = re.match('^(\d{4})(?:\d\d?-\d\d?)?$', date)
    if m:
        return int(m.group(1))

class Mp4tags(Executable):

    name = 'mp4tags'

    STR = str
    NUM = int
    PTH = qip.file.cache_url

    class TagArgInfo(collections.namedtuple('TagArgInfo', 'short_arg long_arg tag_enum type description')):
        __slots__ = ()

    tag_args_info = (
        TagArgInfo('-A', '-album', SoundTagEnum.albumtitle, STR, 'Set the album title'),
        TagArgInfo('-a', '-artist', SoundTagEnum.artist, STR, 'Set the artist information'),
        TagArgInfo('-b', '-tempo', SoundTagEnum.tempo, NUM, 'Set the tempo (beats per minute)'),
        TagArgInfo('-c', '-comment', SoundTagEnum.comment, STR, 'Set a general comment'),
        TagArgInfo('-C', '-copyright', SoundTagEnum.copyright, STR, 'Set the copyright information'),
        TagArgInfo('-d', '-disk', SoundTagEnum.disk, NUM, 'Set the disk number'),
        TagArgInfo('-D', '-disks', SoundTagEnum.disks, NUM, 'Set the number of disks'),
        TagArgInfo('-e', '-encodedby', SoundTagEnum.encodedby, STR, 'Set the name of the person or company who encoded the file'),
        TagArgInfo('-E', '-tool', SoundTagEnum.tool, STR, 'Set the software used for encoding'),
        TagArgInfo('-g', '-genre', SoundTagEnum.genre, STR, 'Set the genre name'),
        TagArgInfo('-G', '-grouping', SoundTagEnum.grouping, STR, 'Set the grouping name'),
        TagArgInfo('-H', '-hdvideo', SoundTagEnum.hdvideo, NUM, 'Set the HD flag (1\\0)'),
        TagArgInfo('-i', '-type', SoundTagEnum.type, STR, 'Set the Media Type(tvshow, movie, music, ...)'),
        TagArgInfo('-I', '-contentid', SoundTagEnum.contentid, NUM, 'Set the content ID'),
        TagArgInfo('-j', '-genreid', SoundTagEnum.genreid, NUM, 'Set the genre ID'),
        TagArgInfo('-l', '-longdesc', SoundTagEnum.longdescription, STR, 'Set the long description'),
        TagArgInfo('-L', '-lyrics', SoundTagEnum.lyrics, NUM, 'Set the lyrics'),  # TODO NUM?
        TagArgInfo('-m', '-description', SoundTagEnum.description, STR, 'Set the short description'),
        TagArgInfo('-M', '-episode', SoundTagEnum.episode, NUM, 'Set the episode number'),
        TagArgInfo('-n', '-season', SoundTagEnum.season, NUM, 'Set the season number'),
        TagArgInfo('-N', '-network', SoundTagEnum.tvnetwork, STR, 'Set the TV network'),
        TagArgInfo('-o', '-episodeid', SoundTagEnum.episodeid, STR, 'Set the TV episode ID'),
        TagArgInfo('-O', '-category', SoundTagEnum.category, STR, 'Set the category'),
        TagArgInfo('-p', '-playlistid', SoundTagEnum.playlistid, NUM, 'Set the playlist ID'),
        TagArgInfo('-P', '-picture', SoundTagEnum.picture, PTH, 'Set the picture as a .png'),
        TagArgInfo('-B', '-podcast', SoundTagEnum.podcast, NUM, 'Set the podcast flag.'),
        TagArgInfo('-R', '-albumartist', SoundTagEnum.albumartist, STR, 'Set the album artist'),
        TagArgInfo('-s', '-song', SoundTagEnum.title, STR, 'Set the song title'),
        TagArgInfo('-S', '-show', SoundTagEnum.tvshow, STR, 'Set the TV show'),
        TagArgInfo('-t', '-track', SoundTagEnum.track, NUM, 'Set the track number'),
        TagArgInfo('-T', '-tracks', SoundTagEnum.tracks, NUM, 'Set the number of tracks'),
        TagArgInfo('-x', '-xid', SoundTagEnum.xid, STR, 'Set the globally-unique xid (vendor:scheme:id)'),
        TagArgInfo('-X', '-rating', SoundTagEnum.rating, STR, 'Set the Rating(none, clean, explicit)'),
        TagArgInfo('-w', '-writer', SoundTagEnum.composer, STR, 'Set the composer information'),
        TagArgInfo('-y', '-year', SoundTagEnum.year, NUM, 'Set the release date'),
        TagArgInfo('-z', '-artistid', SoundTagEnum.artistid, NUM, 'Set the artist ID'),
        TagArgInfo('-Z', '-composerid', SoundTagEnum.composerid, NUM, 'Set the composer ID'),
    )

    @classmethod
    def get_tag_args(cls, tags):
        tagargs = []
        for tag_info in cls.tag_args_info:
            value = tags.get(tag_info.tag_enum, None)
            if value is not None:
                value = str(tag_info.type(value))
                tagargs += [tag_info.long_arg or tag_info.short_arg, value]
        return tuple(tagargs)

    def write_tags(self, tags, file_name, **kwargs):
        tagargs = tuple(str(e) for e in self.get_tag_args(tags))
        self(*(tagargs + (file_name,)), **kwargs)

mp4tags = Mp4tags()

class Mp4info(Executable):

    name = 'mp4info'

    def query(self, file_name):
        track_tags = TrackTags(album_tags=None)
        d = {}
        # rund = self(file_name)
        rund = self(file_name, run_func=dbg_exec_cmd)
        out = clean_cmd_output(rund.out)
        parser = lines_parser(out.split('\n'))
        while parser.advance():
            if parser.line == '':
                pass
            elif parser.re_search(r'^Track +Type +Info$'):
                while parser.advance():
                    if parser.line == '':
                        pass
                    elif parser.re_search(r'^(?P<trackno>\d+) +(?P<tracktype>\S+) +(?P<infos>.+)$'):
                        # 1     audio   MPEG-4 AAC LC, 424.135 secs, 256 kbps, 44100 Hz
                        trackno = parser.match.group('trackno')
                        tracktype = parser.match.group('tracktype')
                        infos = parser.match.group('infos')
                        if tracktype == 'audio':
                            infos = infos.split(',')
                            d['audio_type'] = infos.pop(0)
                            for info in infos:
                                info = info.strip()
                                m = re.search(r'^(\d+\.\d+) secs', info)
                                if m:
                                    d['duration'] = float(m.group(1))
                                    continue
                                m = re.search(r'^(\d+(?:\.\d+)?) kbps', info)
                                if m:
                                    d['bitrate'] = times_1000(m.group(1))
                                    continue
                                m = re.search(r'^(\d+) Hz', info)
                                if m:
                                    d['frequency'] = int(m.group(1))
                                    continue
                    else:
                        parser.pushback(parser.line)
                        break
            elif parser.re_search(r'^ +Cover Art pieces: (\d+)$'):
                d['num_cover'] = int(parser.match.group(1))
            elif parser.re_search(r'^ +(?P<tag>\w+(?: \w+)*): (?P<value>.+)$'):
                track_tags.set_tag(parser.match.group('tag'), parser.match.group('value'))
            else:
                #app.log.debug('TODO: %s', parser.line)
                pass
        return d, track_tags

mp4info = Mp4info()

def genre_to_id3v2(genre):
    genre = genre.lower()
    for key, value in id3v1_genres_id_map.items():
        if value.lower() == genre:
            return key

class Id3v2(Executable):

    name = 'id3v2'

    STR = str
    NUM = int

    class TagArgInfo(collections.namedtuple('TagArgInfo', 'short_arg long_arg tag_enum type description')):
        __slots__ = ()

    tag_args_info_d = {}
    for key, info in tag_info['tags'].items():
        id3v2_30_tag = info.get('id3v2_30_tag', None)
        if id3v2_30_tag:
            long_arg = '--' + id3v2_30_tag
            short_arg = {
                '--artist': '-a',
                '--album': '-A',
                '--song': '-t',
                '--comment': '-c',  # TODO SoundTagEnum.comment: "DESCRIPTION":"COMMENT":"LANGUAGE"
                '--genre': '-g',
                '--year': '-y',
                '--track': '-T',
            }.get(long_arg, None)
            tag_args_info_d[id3v2_30_tag] = TagArgInfo(short_arg, '--' + id3v2_30_tag, SoundTagEnum(key), STR, 'Set the ' + info['element'])

    tag_args_info_d['TCON'] = tag_args_info_d['TCON']._replace(type=genre_to_id3v2)
    tag_args_info_d['TRCK'] = tag_args_info_d['TRCK']._replace(tag_enum=SoundTagEnum.track_slash_tracks)
    tag_args_info_d['TPOS'] = tag_args_info_d['TPOS']._replace(tag_enum=SoundTagEnum.disk_slash_disks)
    del tag_args_info_d['APIC']  # TODO

    def TYER(date):
        if type(date) is int:
            return date
    tag_args_info_d['TYER'] = TagArgInfo(None, '--TYER', SoundTagEnum.date, TYER, 'Set the year')
    def TDAT(date):
        if type(date) in (datetime.datetime, datetime.date):
            return date.strftime('%Y-%m-%d')
    tag_args_info_d['TDAT'] = tag_args_info_d['TDAT']._replace(type=TDAT)

    tag_args_info = tuple(tag_args_info_d.values())

    @classmethod
    def get_tag_args(cls, tags):
        tagargs = []
        for tag_info in cls.tag_args_info:
            value = tags.get(tag_info.tag_enum, None)
            if value is not None:
                value = tag_info.type(value)
                if value is not None:
                    arg = tag_info.long_arg or tag_info.short_arg
                    tagargs += [arg, value]
        return tuple(tagargs)

    def write_tags(self, tags, file_name, **kwargs):
        tagargs = tuple(str(e) for e in self.get_tag_args(tags))
        self(
                '-2',  # TODO
                *(tagargs + (file_name,)), **kwargs)

id3v2 = Id3v2()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
