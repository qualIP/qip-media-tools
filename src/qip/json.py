# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
        'JsonFile',
        'JSONEncodable',
        'JSONDecodable',
        'load',
        'loads',
        'dump',
        'dumps',
        'JSONEncoder',
        'JSONDecoder',
        )

import datetime
import importlib

from json import JSONEncoder as _JSONEncoder
from json import JSONDecoder as _JSONDecoder
from json import load as _load
from json import loads as _loads
from json import dump as _dump
from json import dumps as _dumps

from .file import TextFile

class JsonFile(TextFile):

    _common_extensions = (
        '.json',
    )

class JSONEncodable(object):

    def __json_encode_vars__(self):
        return {k: v for k, v in vars(self).items() if not k.startswith('_')}

    def __json_encode_class_name__(self):
        return JSONEncoder.encode_class_name(self.__class__)

    def __json_encode__(self):
        d = self.__json_encode_vars__()
        json_class_name = self.__json_encode_class_name__()
        if json_class_name:
            d['__class__'] = json_class_name
        return d

    def __json_prepare_dump__(self):
        return self

    def json_dump(self, fp):
        o = self.__json_prepare_dump__()
        return dump(o, fp, indent=2, sort_keys=True, ensure_ascii=False)

    def json_dumps(self):
        o = self.__json_prepare_dump__()
        return dumps(o, indent=2, sort_keys=True, ensure_ascii=False)

    @classmethod
    def __subclasshook__(cls, C):
        if cls is JSONEncodable:
            if any("__json_encode__" in B.__dict__ for B in C.__mro__):
                return True
        return NotImplemented

class JSONDecodable(object):

    @classmethod
    def __json_decode__(cls, obj):
        return cls(**obj)

    @classmethod
    def __subclasshook__(cls, C):
        if cls is JSONDecodable:
            if any("__json_decode__" in B.__dict__ for B in C.__mro__):
                return True
        return NotImplemented

    @classmethod
    def json_load(cls, fp):
        obj = load(fp)
        if type(obj) is dict:
            obj = cls.__json_decode__(obj)
        elif not isinstance(obj, cls):
            raise ValueError(obj)
        return obj

    @classmethod
    def json_loads(cls, s):
        obj = loads(s)
        if type(obj) is dict:
            obj = cls.__json_decode__(obj)
        elif not isinstance(obj, cls):
            raise ValueError(obj)
        return obj

def load(fp, cls=None, **kwargs):
    if cls is None:
        cls = JSONDecoder
    return _load(fp, cls=cls, **kwargs)

def loads(s, cls=None, **kwargs):
    if cls is None:
        cls = JSONDecoder
    return _loads(s, cls=cls, **kwargs)

def dump(obj, fp, cls=None, **kwargs):
    if cls is None:
        cls = JSONEncoder
    return _dump(obj, fp, cls=cls, **kwargs)

def dumps(obj, cls=None, **kwargs):
    if cls is None:
        cls = JSONEncoder
    return _dumps(obj, cls=cls, **kwargs)

class JSONEncoder(_JSONEncoder):

    _builtin_encoders = {}

    def _encode_datetime(obj):
        return {
            '__class__': JSONEncoder.encode_class_name(datetime.datetime),
            'year': obj.year,
            'month': obj.month,
            'day': obj.day,
            'hour': obj.hour,
            'minute': obj.minute,
            'second': obj.second,
            'microsecond': obj.microsecond,
            'tzinfo': obj.tzinfo,
        }

    _builtin_encoders[datetime.datetime] = _encode_datetime

    def _encode_date(obj):
        return {
            '__class__': JSONEncoder.encode_class_name(datetime.date),
            'year': obj.year,
            'month': obj.month,
            'day': obj.day,
        }

    _builtin_encoders[datetime.date] = _encode_date

    @classmethod
    def encode_class_name(self, cls):
        try:
            return CLASS_TO_ALIAS[cls]
        except KeyError:
            pass
        return '{}:{}'.format(cls.__module__, cls.__qualname__)

    def default(self, obj):
        if isinstance(obj, JSONEncodable):
            return obj.__json_encode__()
        else:
            f = self._builtin_encoders.get(obj.__class__, None)
            if f is not None:
                return f(obj)
            else:
                return super().default(obj)

class JSONDecoder(_JSONDecoder):

    _builtin_decoders = {}

    def _decode_datetime(obj):
        return datetime.datetime(**obj)

    _builtin_decoders[datetime.datetime] = _decode_datetime

    def _decode_date(obj):
        return datetime.date(**obj)

    _builtin_decoders[datetime.date] = _decode_date

    def __init__(self, object_hook=None, **kwargs):
        if object_hook is None:
            object_hook = self.default_object_hook
        super().__init__(object_hook=object_hook, **kwargs)

    def decode_class_name(self, cls_name):
        try:
            return ALIAS_TO_CLASS[cls_name]
        except KeyError:
            pass
        mod_name, cls_name = cls_name.split(':', maxsplit=1)
        mod = importlib.import_module(mod_name)
        cls = mod
        for sub_cls_name in cls_name.split(sep='.'):
            cls = getattr(cls, sub_cls_name)
        return cls

    def default_object_hook(self, obj):
        cls_name = obj.pop('__class__', None)
        if cls_name is not None:
            cls = self.decode_class_name(cls_name)
            if issubclass(cls, JSONDecodable):
                return cls.__json_decode__(obj)
            else:
                f = self._builtin_decoders.get(obj.__class__, None)
                if f is not None:
                    return f(obj)
                else:
                    return cls(**obj)
        else:
            return obj

ALIAS_TO_CLASS = {}
CLASS_TO_ALIAS = {}

def register_class_alias(cls, alias):
    ALIAS_TO_CLASS[alias] = cls
    CLASS_TO_ALIAS[cls] = alias

def register_class(cls, encoder, decoder, wrap=True):
    if wrap:
        def _json_encoder(obj):
            return {
                    '__class__': JSONEncoder.encode_class_name(obj.__class__),
                    'data': encoder(obj),
                    }
        cls.__json_encode__ = _json_encoder
        def _json_decoder(obj):
            return decoder(obj['data'])
        cls.__json_decode__ = _json_decoder
    else:
        cls.__json_encode__ = encoder
        cls.__json_decode__ = decoder

JSON_NATIVE_TYPES = (
    type(None),
    str,
    int,
    list,
    tuple,
    _collections.abc.Mapping,
    JSONEncodable,
)

JsonFile._build_extension_to_class_map()
