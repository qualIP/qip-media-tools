# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import os

import logging
log = logging.getLogger(__name__)

from qip.propex import propex
from qip.file import toPath
from qip.mm import FrameRate
from qip.utils import Timestamp

from qip.libdvdread_swig import *
import qip.libdvdread_swig as libdvdread_swig

class dvd_reader(object):

    handle = None  # "dvd_reader_t *"

    device = propex(
        name='device',
        type=(None,
              toPath,
              ),
        fdel=None)

    def __init__(self, device, open: bool=True):
        self.device = device
        super().__init__()
        if open:
            self.open()

    def __del__(self):
        if self.handle is not None:
            self.close()

    def __enter__(self):
        if self.handle is None:
            self.open()
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            self.close()
        f = getattr(super(), '__exit__', None)
        return f(*exc) if f else None

    def open(self):
        assert self.handle is None
        device = self.device
        assert device is not None
        handle = libdvdread_swig.DVDOpen(os.fspath(device))
        if handle is None:
            raise Exception(f'Can\'t open disc {device}!')
        self.handle = handle
        return self

    def close(self):
        handle = self.handle
        assert handle is not None
        try:
            libdvdread_swig.DVDClose(handle)
        finally:
            self.handle = None

    def __repr__(self):
        return f'{self.__class__.__name__}({os.fspath(self.device)!r})'

    def open_ifo(self, ifo_idx: int):
        ifo = dvd_ifo(dvd=self, ifo_idx=ifo_idx, open=True)
        return ifo

    @property
    def closed(self):
        return self.handle is None

    def OpenFile(self, title, domain):
        return dvd_file(libdvdread_swig.DVDOpenFile(
            self.handle,
            title,
            domain))


class dvd_file(object):

    def __init__(self, handle):
        self.handle = handle
        super().__init__()

    def ReadBlocks(self, offset, count):
        return libdvdread_swig.wrapDVDReadBlocks(
            self.handle,
            offset,
            count,
        )

class dvd_ifo(object):

    dvd: dvd_reader = None
    ifo_idx: int = None
    handle = None  # "ifo_handle *"

    def __init__(self, dvd: dvd_reader, ifo_idx: int, open: bool=True):
        self.dvd = dvd
        self.ifo_idx = ifo_idx
        super().__init__()
        if open:
            self.open()

    def __del__(self):
        if self.handle is not None:
            self.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            self.close()
        f = getattr(super(), '__exit__', None)
        return f(*exc) if f else None

    def open(self):
        assert self.handle is None
        dvd = self.dvd
        assert dvd is not None
        assert dvd.handle is not None
        ifo_idx = self.ifo_idx
        assert ifo_idx is not None
        handle = libdvdread_swig.ifoOpen(dvd.handle, ifo_idx)
        if handle is None:
            raise Exception(f'Can\'t open {dvd.device} ifo {ifo_idx}!')
        self.handle = handle
        return self

    def close(self):
        handle = self.handle
        assert handle is not None
        try:
            libdvdread_swig.ifoClose(handle)
        finally:
            self.handle = None

    def __repr__(self):
        return f'{self.__class__.__name__}({self.dvd!r}, {self.ifo_idx!r})'

    def __getattr__(self, name):
        if not name.startswith('_'):
            handle = self.handle
            if handle is not None:
                try:
                    v = getattr(handle, name)
                    return v
                except AttributeError:
                    pass
        f = getattr(super(), '__getattr__', None)
        if f is not None:
            return f(name)
        else:
            raise AttributeError(name)

dvdFpss = {
    0: None,  # TODO
    1: FrameRate(25000, 1000),
    2: None,  # TODO
    3: FrameRate(30000, 1001),
}

def dvd_time_to_Timestamp(dt: 'dvd_time_t *') -> Timestamp:
    hour, minute, second, frame_u = dt.hour, dt.minute, dt.second, dt.frame_u
    ms = (((hour & 0xf0) >> 3) * 5 + (hour & 0x0f)) * 3600000
    ms += (((minute & 0xf0) >> 3) * 5 + (minute & 0x0f)) * 60000
    ms += (((second & 0xf0) >> 3) * 5 + (second & 0x0f)) * 1000

    fps = dvdFpss[(frame_u & 0xc0) >> 6]
    if fps is not None:
        ms += (((frame_u & 0x30) >> 3) * 5 + (frame_u & 0x0f)) * 1000.0 / fps

    ts = Timestamp(ms / 1000.0)
    return ts
