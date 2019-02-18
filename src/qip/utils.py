__all__ = (
        'TypedKeyDict',
        'TypedValueDict',
        'byte_decode',
        'pairwise',
        'Timestamp',
        )

import abc
import collections
from fractions import Fraction
from decimal import Decimal
import functools
import re
import logging
log = logging.getLogger(__name__)

@functools.total_ordering
class Timestamp(object):
    '''xxhxxmxx.xxxxxxxxxs format'''

    def __init__(self, value):
        if isinstance(value, float):
            seconds = value
        elif isinstance(value, int):
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

    def __str__(self):
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
        if h:
            string = '%dh%02dm%s' % (h, m, ('%.9f' % (s + 100.0,))[1:])
        elif m:
            string = '%dm%s' % (m, ('%.9f' % (s + 100.0,))[1:])
        else:
            string = '%.9f' % (s,)
        if string.endswith('000'):
            if string.endswith('000000'):
                string = string[:-6]
            else:
                string = string[:-3]
        return sign + string + 's'

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
        if isinstance(other, (int, float)):
            return self.__class__(self.seconds + other)
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, Timestamp):
            return self.__class__(self.seconds - other.seconds)
        if isinstance(other, (int, float)):
            return self.__class__(self.seconds - other)
        return NotImplemented

    def __eq__(self, other):
        if isinstance(other, Timestamp):
            return self.seconds == other.seconds
        if isinstance(other, (int, float)):
            return self.seconds == other
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, Timestamp):
            return self.seconds < other.seconds
        if isinstance(other, (int, float)):
            return self.seconds < other
        return NotImplemented


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

    update = collections.MutableMapping.update

    @classmethod
    def __subclasshook__(cls, C):
        if cls is TypedKeyDict:
            if C is not TypedKeyDict and not issubclass(C, collections.Mapping):
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
            if C is not TypedValueDict and not issubclass(C, collections.MutableMapping):
                return NotImplemented
            for B in C.__mro__:
                if "_sanitize_value" in B.__dict__:
                    if B.__dict__["_sanitize_value"]:
                        return True
                    break
        return NotImplemented


def byte_decode(b, encodings=('utf-8', 'iso-8859-1', 'us-ascii')):
    if isinstance(b, str):
        return b
    last_e = None
    for encoding in encodings:
        try:
            return b.decode(encoding, 'strict')
        except UnicodeDecodeError as e:
            #log.debug('%s output: %s', cmd[0], e)
            last_e = e
    raise ValueError('Unable to decode %r', (b,)) from last_e


def pairwise(iterable):
    "s -> (s0, s1), (s2, s3), (s4, s5), ..."
    a = iter(iterable)
    return zip(a, a)


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
