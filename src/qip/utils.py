# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'beep',
    'humanbytes',
    'Constants',
    'KwVarsObject',
    'TypedKeyDict',
    'TypedValueDict',
    'byte_decode',
    'pairwise',
    'grouper',
    'Timestamp',
    'prettyxml',
    'round_up',
    'round_down',
    'round_half_up',
    'round_half_down',
    'round_half_away_from_zero',
    'compile_pattern_list',
    'indexable',
    'advenumerate',
    'adviter',
    'dict_from_swig_obj',
    'replace_html_entities',
    'StreamTransform',
    'is_term_dark',
)

from _collections_abc import _check_methods
from decimal import Decimal
from fractions import Fraction
import abc
import collections
import contextlib
import datetime
import enum
import functools
import html
import itertools
import logging
import math
import os
import re
import shutil
import stat
import sys
import termios
import textwrap
import time
log = logging.getLogger(__name__)

def beep():
    print('\a', end='')

try:
    # Python 3.9
    COPY_BUFSIZE = shutil.COPY_BUFSIZE
except:
    # https://eklitzke.org/efficient-file-copying-on-linux
    # http://git.savannah.gnu.org/cgit/coreutils.git/tree/src/ioblksize.h
    COPY_BUFSIZE = 128 * 1024

HAVE_PROGRESS_BAR = False
try:
    import progress.bar
    import progress.spinner
    HAVE_PROGRESS_BAR = True
except ImportError:
    pass

def progress_copy2(src, dst, *, follow_symlinks=True):
    """Copy data and metadata. Return the file's destination.

    Metadata is copied with copystat(). Please see the copystat function
    for more information.

    The destination may be a directory.

    If follow_symlinks is false, symlinks won't be followed. This
    resembles GNU's "cp -P src dst".

    NOTE: Same as Python 3.9's shutil.copy2 but with progress bar support
    """
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    progress_copyfile(src, dst, follow_symlinks=follow_symlinks)
    shutil.copystat(src, dst, follow_symlinks=follow_symlinks)
    return dst

def progress_copy2_link(src, dst, *, follow_symlinks=True):
    """Create a hard link pointing to src named dst. If a hard link is not possible, copy the file using progress_copy2.
    """
    try:
        os.link(src, dst, follow_symlinks=follow_symlinks)
    except OSError as e:
        if e.errno == errno.EXDEV:
            # [Errno 18] Invalid cross-device link: 'src' -> 'dst'
            progress_copy2(src, dst, follow_symlinks=follow_symlinks)
        else:
            raise
    return dst

def progress_copyfile(src, dst, *, follow_symlinks=True):
    """Copy data from src to dst.

    If follow_symlinks is not set and src is a symbolic link, a new
    symlink will be created instead of copying the file it points to.

    NOTE: Same as Python 3.9's shutil.copyfile but with progress bar support
    (No OS-Specific optimizations)
    """
    if shutil._samefile(src, dst):
        raise SameFileError("{!r} and {!r} are the same file".format(src, dst))

    for fn in [src, dst]:
        try:
            st = os.stat(fn)
        except OSError:
            # File most likely does not exist
            pass
        else:
            # XXX What about other special files? (sockets, devices...)
            if stat.S_ISFIFO(st.st_mode):
                fn = fn.path if isinstance(fn, os.DirEntry) else fn
                raise SpecialFileError("`%s` is a named pipe" % fn)

    if not follow_symlinks and os.path.islink(src):
        os.symlink(os.readlink(src), dst)
    else:
        with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
            progress_copyfileobj(fsrc, fdst)
    return dst

def progress_copyfileobj(fsrc, fdst, length=0):
    """copy data from file-like object fsrc to file-like object fdst

    NOTE: Same as Python 3.9's shutil.copyfileobj but with progress bar support
    """
    if not length:
        length = COPY_BUFSIZE
    fsrc_read = fsrc.read
    fdst_write = fdst.write
    if HAVE_PROGRESS_BAR and fsrc.seekable():
        # With progress bar
        flush = True
        fsrc_tell = fsrc.tell
        fsrc_seek = fsrc.seek
        pos = fsrc_tell()
        fsrc_seek(0, 2)
        siz = fsrc_tell()
        fsrc_seek(pos, 0)
        name = getattr(fsrc, 'name')
        bar = BytesBar(
            f'Copying {name}' if name else 'Copying',
            max=siz)
        bar_goto = bar.goto
        try:
            while 1:
                buf = fsrc_read(length)
                if not buf:
                    break
                fdst_write(buf)
                #if int(time.monotonic()) != int(bar._ts):
                bar_goto(fsrc_tell())
            if flush:
                fdst.flush()
                bar_goto(fsrc_tell())
        finally:
            bar.finish()
    else:
        # Without progress bar
        flush = False
        while 1:
            buf = fsrc_read(length)
            if not buf:
                break
            fdst_write(buf)
        if flush:
            fdst.flush()

def progress_move(src, dst, copy_function=progress_copy2):
    """Recursively move a file or directory (src) to another location (dst) and return the destination.

    NOTE: Same as shutil.move but with progress bar support
    """
    return shutil.move(src, dst,
                       copy_function=copy_function)

if HAVE_PROGRESS_BAR:

    __all__ += (
        'ProgressBar',
        'ProgressSpinner',
        'BytesBar',
    )

    from collections import deque
    try:
        from time import monotonic
    except ImportError:
        from time import time as monotonic


    class ProgressSpinner(progress.spinner.Spinner):

        def reset(self):
            self.index = 0
            self.update()

    class ProgressBar(progress.bar.Bar):

        def reset(self):
            # As in Infinite.__init__
            self.start_ts = monotonic()
            self.avg = 0
            self._avg_update_ts = self.start_ts
            self._ts = self.start_ts
            self._xput = deque(maxlen=self.sma_window)

        @property
        def end(self):
            return int(math.ceil(self.avg * self.max))

        @property
        def end_td(self):
            return datetime.timedelta(seconds=self.end)


    class BytesBar(ProgressBar):
        # 86.4% (16.3 GiB / 18.9 GiB) 26.2 MiB/s remaining 0:01:40
        suffix_start = '%(percent)d%% (%(humanindex)s / %(humanmax)s) %(humanrate)s/s remaining %(eta_td)s / %(end_td)s'
        suffix_finish = '%(percent)d%% (%(humanmax)s) %(humanrate)s/s %(elapsed_td)s'
        suffix = suffix_start

        @property
        def rate(self):
            return 1 / self.avg if self.avg else 0

        @property
        def humanindex(self):
            return humanbytes(self.index)

        @property
        def humanmax(self):
            return humanbytes(self.max)

        @property
        def humanrate(self):
            return humanbytes(self.rate)

        def start(self):
            self.suffix = self.suffix_start
            super().start()

        def finish(self):
            self.suffix = self.suffix_finish
            self.update()
            super().finish()

KB = float(1024)
MB = float(KB ** 2) # 1,048,576
GB = float(KB ** 3) # 1,073,741,824
TB = float(KB ** 4) # 1,099,511,627,776

def humanbytes(B):
   'Return the given bytes as a human friendly KB, MB, GB, or TB string'
   B = float(B)

   if B < KB:
      return '{0} {1}'.format(B,'Bytes' if 0 == B > 1 else 'Byte')
   elif KB <= B < MB:
      return '{0:.2f}KB'.format(B/KB)
   elif MB <= B < GB:
      return '{0:.2f}MB'.format(B/MB)
   elif GB <= B < TB:
      return '{0:.2f}GB'.format(B/GB)
   elif TB <= B:
      return '{0:.2f}TB'.format(B/TB)

class Constants(enum.Enum):
    # None = 'None'
    # False = 'False'
    # True = 'True'
    Auto = 'Auto'
    NotSet = 'NotSet'
    Ask = 'Ask'

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.name

Ask = Constants.Ask
Auto = Constants.Auto
NotSet = Constants.NotSet

Constants._value2member_map_.update({
    None: None,
    'None': None,
    'none': None,
    False: False,
    'False': False,
    'false': False,
    True: True,
    'True': True,
    'true': True,
    Auto: Auto,
    'Auto': Auto,
    'auto': Auto,
    Ask: Ask,
    'Ask': Ask,
    'ask': Ask,
    NotSet: NotSet,
    'NotSet': NotSet,
    'Notset': NotSet,
    'notset': NotSet,
    'not-set': NotSet,
})


class KwVarsObject(object):

    def __repr__(self):
        '''Generic namedtuple-like repr'''
        return '%s(%s)' % (
            self.__class__.__name__,
            ', '.join('%s=%r' % (k, v)
                      for k, v in self.__dict__.items()))

    def _replace(self, **kwargs):
        '''Generic namedtuple-like _replace'''
        kwargs = dict(
                tuple(vars(self).items())
                + tuple(kwargs.items()))
        return self.__class__(**kwargs)


@functools.total_ordering
class Timestamp(object):
    '''xxhxxmxx.xxxxxxxxxs format'''

    _SECONDS_COMPATIBLE_TYPES = (float, int, Fraction, Decimal)

    def __init__(self, value):
        if isinstance(value, Timestamp._SECONDS_COMPATIBLE_TYPES):
            seconds = float(value)
        elif isinstance(value, Timestamp):
            seconds = value.seconds
        elif isinstance(value, str):
            match = value and re.search(
                r'^'
                r'(?P<sign>-)?'
                r'(?:(?P<h>\d+)h)?'
                r'(?:(?P<m>\d+)m)?'
                r'(?:(?P<s>\d+(?:\.\d+)?)s?)?'
                r'$', value)
            if match:
                h = match.group('h') or 0
                m = match.group('m') or 0
                s = match.group('s') or 0
                sign = bool(match.group('sign'))
                seconds = int(h or 0) * 60 * 60 + int(m or 0) * 60 + float(s)
                if sign:
                    seconds = -seconds
            else:
                raise ValueError('Invalid xxhxxmxx.xxxxxxxxs format: %r' % (value,))
        else:
            raise ValueError(value)
        self.seconds = seconds

    def __bool__(self):
        return bool(self.seconds)

    def canonical_str(self, precision=9):
        s = self.seconds
        if s < 0.0:
            sign = '-'
            s = -s
        else:
            sign = ''
        m = s // 60
        s = s - m * 60
        h = m // 60
        m = m - h * 60
        s = '%.*f' % (9 if precision is None else precision, s)
        if h:
            if s[1] == '.':
                s = '0'+ s
            string = '%dh%02dm%s' % (h, m, s)
        elif m:
            if s[1] == '.':
                s = '0'+ s
            string = '%dm%s' % (m, s)
        else:
            string = s
        if precision is None:
            if string.endswith('000'):
                if string.endswith('000000'):
                    string = string[:-6]
                else:
                    string = string[:-3]
        return sign + string + 's'

    def friendly_str(self):
        s = self.seconds
        if s < 0.0:
            sign = '-'
            s = -s
        else:
            sign = ''
        m = s // 60
        s = s - m * 60
        h = m // 60
        m = m - h * 60
        string = ''
        if h:
            string += '%dh' % (h,)
        if m:
            string += '%dm' % (m,)
        if s:
            s = '%.9f' % (s,)
            if string and s[1] == '.':
                s = '0' + s
            if s.endswith('000'):
                if s.endswith('000000'):
                    if s.endswith('.000000000'):
                        s = s[:-10]
                    else:
                        s = s[:-6]
                else:
                    s = s[:-3]
            string += '%ss' % (s,)
        if not string:
            string = '0'
        return sign + string

    def hms_str(self):
        s = self.seconds
        if s < 0.0:
            sign = '-'
            s = -s
        else:
            sign = ''
        m = s // 60
        s = s - m * 60
        h = m // 60
        m = m - h * 60
        s = '%.0f' % (s,)
        string = '%dh%02dm%s' % (h, m, s)
        return string

    def __str__(self):
        return self.canonical_str()

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, str(self))

    def __float__(self):
        return self.seconds

    def __int__(self):
        return int(self.seconds)

    def __neg__(self):
        return self.__class__(-self.seconds)

    def __add__(self, other):
        if isinstance(other, Timestamp):
            return self.__class__(self.seconds + other.seconds)
        if isinstance(other, Timestamp._SECONDS_COMPATIBLE_TYPES):
            return self.__class__(self.seconds + other)
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Timestamp):
            return self.__class__(self.seconds - other.seconds)
        if isinstance(other, Timestamp._SECONDS_COMPATIBLE_TYPES):
            return self.__class__(self.seconds - other)
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, Timestamp):
            return self.__class__(self.seconds * other.seconds)
        if isinstance(other, Timestamp._SECONDS_COMPATIBLE_TYPES):
            return self.__class__(self.seconds * other)
        return NotImplemented

    def __truediv__(self, other):
        if isinstance(other, Timestamp):
            return self.__class__(self.seconds / other.seconds)
        if isinstance(other, Timestamp._SECONDS_COMPATIBLE_TYPES):
            return self.__class__(self.seconds / other)
        return NotImplemented

    def __floordiv__(self, other):
        return self.seconds // other

    def __abs__(self):
        return self.__class__(abs(self.seconds))

    def __eq__(self, other):
        if isinstance(other, Timestamp):
            return self.seconds == other.seconds
        if isinstance(other, Timestamp._SECONDS_COMPATIBLE_TYPES):
            return self.seconds == other
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, Timestamp):
            return self.seconds < other.seconds
        if isinstance(other, Timestamp._SECONDS_COMPATIBLE_TYPES):
            return self.seconds < other
        return NotImplemented

    def __format__(self, format_spec):
        if format_spec == '':
            return str(self)
        elif format_spec == 'canonical':
            return self.canonical_str()
        elif format_spec == 'friendly':
            return self.friendly_str()
        elif format_spec == 'ffmpeg':
            from qip.ffmpeg import ffmpeg
            return ffmpeg.Timestamp(self).canonical_str()
        elif format_spec == 'hms':
            return self.hms_str()
        else:
            raise NotImplementedError(f'Unsupported {self.__class__.__name__} format spec {format_spec!r}')

class TypedKeyDict(abc.ABC):

    @abc.abstractmethod
    def _sanitize_key(self, key):
        return key

    def __getitem__(self, key):
        key = self._sanitize_key(key)
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        key = self._sanitize_key(key)
        super().__setitem__(key, value)

    def __delitem__(self, key):
        key = self._sanitize_key(key)
        super().__delitem__(key)

    def __contains__(self, key):
        try:
            key = self._sanitize_key(key)
        except KeyError:
            return False
        return super().__contains__(key)

    update = collections.abc.MutableMapping.update

    @classmethod
    def __subclasshook__(cls, C):
        if cls is TypedKeyDict:
            if C is not TypedKeyDict and not issubclass(C, collections.abc.Mapping):
                return NotImplemented
            for B in C.__mro__:
                if "_sanitize_key" in B.__dict__:
                    if B.__dict__["_sanitize_key"]:
                        return True
                    break
        return NotImplemented


class TypedValueDict(abc.ABC):

    @abc.abstractmethod
    def _sanitize_value(self, value, key=None):
        return value

    def __setitem__(self, key, value):
        value = self._sanitize_value(value, key=key)
        super().__setitem__(key, value)

    @classmethod
    def __subclasshook__(cls, C):
        if cls is TypedValueDict:
            if C is not TypedValueDict and not issubclass(C, collections.abc.MutableMapping):
                return NotImplemented
            for B in C.__mro__:
                if "_sanitize_value" in B.__dict__:
                    if B.__dict__["_sanitize_value"]:
                        return True
                    break
        return NotImplemented


def byte_decode(b, encodings=('utf-8', 'iso-8859-1', 'us-ascii'), errors='strict'):
    if isinstance(b, str):
        return b
    if isinstance(encodings, str):
        encodings = [encodings]
    last_e = None
    for encoding in encodings:
        try:
            return b.decode(encoding, errors)
        except UnicodeDecodeError as e:
            #log.debug('%s output: %s', cmd[0], e)
            last_e = e
    raise ValueError('Unable to decode %r', (b,)) from last_e


def pairwise(iterable):
    # From https://docs.python.org/3/library/itertools.html
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return zip(a, b)


def grouper(iterable, n, fillvalue=None):
    # From https://docs.python.org/3/library/itertools.html
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


class Ratio(Fraction):
    '''num:den ratio format'''

    def __new__(cls, numerator=0, denominator=None, **kwargs):
        if denominator is None:
            if isinstance(numerator, str):
                numerator = numerator.replace(':', '/')
                m = re.match(r'^(?P<num>\d+(?:\.\d+)?)(?:/1)?$', numerator)
                if m:
                    numerator = Decimal(m.group('num'))
        elif type(numerator) is str is type(denominator):
            numerator = int(numerator)
            denominator = int(denominator)
        try:
            return super().__new__(cls, numerator, denominator, **kwargs)
        except Exception as e:
            log.debug('%s: %s(%r, %r)', e, cls.__name__, numerator, denominator)
            raise

    def to_str(self, *, separator=':', force_denominator=True):
        if not force_denominator and self._denominator == 1:
            return str(self._numerator)
        else:
            return '%s%s%s' % (self._numerator, separator, self._denominator)

    def __str__(self):
        """str(self)"""
        return self.to_str()

    def __add__(a, b):
        return a.__class__(super().__add__(b))

    def __radd__(a, b):
        return a.__class__(super().__radd__(b))

    def __sub__(a, b):
        return a.__class__(super().__sub__(b))

    def __rsub__(a, b):
        return a.__class__(super().__rsub__(b))

    def __mul__(a, b):
        return a.__class__(super().__mul__(b))

    def __rmul__(a, b):
        return a.__class__(super().__rmul__(b))

    def __truediv__(a, b):
        return a.__class__(super().__truediv__(b))

    def __rtruediv__(a, b):
        return a.__class__(super().__rtruediv__(b))

    def __pow__(a, b):
        v = a.__class__(super().__pow__(b))
        if isinstance(v, Fraction):
            v = a.__class__(v)
        return v

    def __rpow__(b, a):
        v = b.__class__(super().__rpow__(a))
        if isinstance(v, Fraction):
            v = b.__class__(v)
        return v

    def __pos__(a):
        return a.__class__(super().__pos__())

    def __neg__(a):
        return a.__class__(super().__neg__())

    def __abs__(a):
        return a.__class__(super().__abs__())

    def __round__(self, **kwargs):
        v = self.__class__(super().__round__(**kwargs))
        if isinstance(v, Fraction):
            v = self.__class__(v)
        return v

    def __copy__(self):
        if type(self) == Ratio:
            return self     # I'm immutable; therefore I am my own clone
        return super().__copy__()

    def __deepcopy__(self, memo):
        if type(self) == Ratio:
            return self     # My components are also immutable
        return super().__deepcopy__()


def prettyxml(sXml, *, indent="  ", preserve_whitespace_tags=None):
    try:
        return prettyxml_bs4(sXml, indent=indent, preserve_whitespace_tags=preserve_whitespace_tags)
    except ImportError:
        pass
    try:
        return prettyxml_minidom(sXml, indent=indent)
    except ImportError:
        pass
    raise NotImplementedError('No XML beautifier module detected')

def prettyxml_bs4(sXml, *, indent="  ", preserve_whitespace_tags=None):
    import bs4
    if not isinstance(sXml, (str, bytes)):
        try:
            import xml.etree.ElementTree
        except ImportError:
            pass
        else:
            if isinstance(sXml, xml.etree.ElementTree.ElementTree):
                sXml = xml.etree.ElementTree.tostring(sXml.getroot())
        if not isinstance(sXml, (str, bytes)):
            raise TypeError(sXml)
    builder = bs4.builder.builder_registry.lookup('xml')
    if preserve_whitespace_tags is None:
        preserve_whitespace_tags = builder.USE_DEFAULT
    builder = builder(
        preserve_whitespace_tags=preserve_whitespace_tags)
    bs = bs4.BeautifulSoup(sXml, builder=builder)
    return bs.prettify()

def prettyxml_minidom(sXml, *, indent="  "):
    import xml.dom.minidom
    if not isinstance(sXml, str):
        try:
            import xml.etree.ElementTree
        except ImportError:
            pass
        else:
            if isinstance(sXml, xml.etree.ElementTree.ElementTree):
                sXml = xml.etree.ElementTree.tostring(sXml.getroot())
        if not isinstance(sXml, str):
            raise TypeError(sXml)
    doc = xml.dom.minidom.parseString(sXml)
    return doc.toprettyxml(indent=indent)


def round_up(n, decimals=0):
    '''See: https://realpython.com/python-rounding/'''
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier


def round_down(n, decimals=0):
    '''See: https://realpython.com/python-rounding/'''
    multiplier = 10 ** decimals
    return math.floor(n * multiplier) / multiplier


def round_half_up(n, decimals=0):
    '''See: https://realpython.com/python-rounding/'''
    multiplier = 10 ** decimals
    return math.floor(n*multiplier + 0.5) / multiplier


def round_half_down(n, decimals=0):
    '''See: https://realpython.com/python-rounding/'''
    multiplier = 10 ** decimals
    return math.ceil(n*multiplier - 0.5) / multiplier


def round_half_away_from_zero(n, decimals=0):
    '''See: https://realpython.com/python-rounding/'''
    rounded_abs = round_half_up(abs(n), decimals)
    return math.copysign(rounded_abs, n)

def compile_pattern_list(pattern_list, *, compile_flags=re.DOTALL, ignorecase=False, filter_out_expect=False):
    import pexpect
    # Similar to pexpect's compile_pattern_list
    if ignorecase:
        compile_flags = compile_flags | re.IGNORECASE
    compiled_pattern_list = []
    compiled_re_type = type(re.compile(''))
    for p in pattern_list:
        if isinstance(p, (str, bytes)):
            p = byte_decode(p)
            compiled_pattern_list.append(re.compile(p, compile_flags))
        elif p is pexpect.EOF:
            if not filter_out_expect:
                compiled_pattern_list.append(pexpect.EOF)
        elif p is pexpect.TIMEOUT:
            if not filter_out_expect:
                compiled_pattern_list.append(pexpect.TIMEOUT)
        elif isinstance(p, compiled_re_type):
            compiled_pattern_list.append(p)
        else:
            raise TypeError(p)
    return compiled_pattern_list

class Indexable(collections.abc.Iterable):

    def __init__(self, iterable):
        self.iterable = iterable
        self.seen = []
        super().__init__()

    def __getitem__(self, index):
        seen = self.seen
        iterable = self.iterable
        #for i in range(len(seen) - index + 1):
        try:
            while index >= len(seen):
                seen.append(next(iterable))
        except StopIteration:
            raise IndexError(index)
        return seen[index]

    def __iter__(self):
        for i in itertools.count():
            try:
                v = self[i]
            except IndexError:
                raise StopIteration
            yield v

    @classmethod
    def __subclasshook__(cls, C):
        if cls is Indexable:
            return _check_methods(C, "__getitem__")
        return NotImplemented

def indexable(iterable):
    if isinstance(iterable, collections.abc.Collection):
        # Direct indexing supported
        return iterable
    return Indexable(iterable)

def advenumerate(iterable, start=0):
    iterable = indexable(iterable)
    i = start
    while True:
        try:
            v = iterable[i]
        except IndexError:
            break
        r = yield (i, v)
        i += 1
        while r is not None:
            i = r
            r = yield  # dummy so it.send(r) returns nothing and iterator is ready for next(it)

def adviter(iterable, start=0):
    iterable = advenumerate(iterable, start=start)
    for i, v in iterable:
        k = yield v
        while k is not None:
            k = yield iterable.send(k)

@contextlib.contextmanager
def save_and_restore_tcattr(*, fd=None, when=termios.TCSADRAIN):
    if fd is None:
        fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        yield
    finally:
        termios.tcsetattr(fd, when, old)

def dict_from_swig_obj(obj):
    return {
        name: getattr(obj, name)
        for name in dir(obj)
        if (
                not name.startswith('_')
                and name not in ('this', 'thisown')
                and not callable(getattr(obj, name))
        )
    }

def replace_html_entities(s):
    s = html.unescape(s)
    m = re.search(r'&\w+;', s)
    if m:
        raise ValueError('Unknown HTML entity: %s' % (m.group(0),))
    return s

class StreamTransform(object):

    file = None
    transform = None

    def __init__(self, file, *, transform=None):
        self.file = file
        self.transform = transform
        super().__init__()

    def __getattr__(self, name):
        # Attribute lookups are delegated to the underlying file
        # and cached for non-numeric results
        # (i.e. methods are cached, closed and friends are not)
        file = self.__dict__['file']
        a = getattr(file, name)
        #if hasattr(a, '__call__'):
        #    func = a
        #    @_functools.wraps(func)
        #    def func_wrapper(*args, **kwargs):
        #        return func(*args, **kwargs)
        #    # Avoid closing the file as long as the wrapper is alive,
        #    # see issue #18879.
        #    func_wrapper._closer = self._closer
        #    a = func_wrapper
        if not isinstance(a, int):
            setattr(self, name, a)
        return a

    # The underlying __enter__ method returns the wrong object
    # (self.file) so override it to return the wrapper
    def __enter__(self):
        self.file.__enter__()
        return self

    # Need to trap __exit__ as well to ensure the file gets
    # deleted when used in a with statement
    def __exit__(self, exc, value, tb):
        result = self.file.__exit__(exc, value, tb)
        return result

    # iter() doesn't use __getattr__ to find the __iter__ method
    def __iter__(self):
        # Don't return iter(self.file), but yield from it to avoid closing
        # file as long as it's being used as iterator (see issue #23700).  We
        # can't use 'yield from' here because iter(file) returns the file
        # object itself, which has a close method, and thus the file would get
        # closed when the generator is finalized, due to PEP380 semantics.
        for line in self.file:
            yield line

    #def writelines(self, lines):
    #    if self.closed:
    #        raise ValueError('I/O operation on closed file')
    #    return self.fp.writelines(lines)

    def write(self, s):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        if self.transform:
            s = self.transform(s)
        return self.file.write(s)

    @classmethod
    def indenter(cls, file, *, prefix=None, indent=4):
        if prefix is None:
            prefix = ' ' * indent
        return cls(file,
                   transform=functools.partial(textwrap.indent, prefix=prefix))

def is_term_dark(default=False):
    # TODO support other methods
    # Interesting thread: https://stackoverflow.com/questions/2507337/how-to-determine-a-terminals-background-color

    try:
        fg, bg = (int(e) for e in os.environ['COLORFGBG'].split(';'))
    except KeyError:
        # No COLORFGBG environment
        pass
    except ValueError:
        # Not two values or not integers
        pass
    else:
        # If background color is 0 to 6 or 8, it is dark.
        return 0 <= bg <= 6 or bg == 8

    return default
