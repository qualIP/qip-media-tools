__all__ = (
        'TypedKeyDict',
        'TypedValueDict',
        'byte_decode',
        'pairwise',
        )

import abc
import collections

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
