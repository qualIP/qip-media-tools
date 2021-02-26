# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'VobFile',
)

from pathlib import Path
import errno
import io
import logging
import os
log = logging.getLogger(__name__)

from .mm import BinaryMediaFile
from .file import MultiFile
import qip.libdvdread as libdvdread

MAX_MULTIVOB_FILES = 10

class VobFile(MultiFile, BinaryMediaFile):

    _common_extensions = (
        '.vob',
    )

    dvd_reader = None
    vts = None

    @classmethod
    def get_vob_file_name_pattern(cls, title, menu):
        if title == 0:
            return 'VIDEO_TS.VOB'
        elif menu:
            return 'VTS_{title:02d}_0.VOB'.format(title=title)
        else:
            return 'VTS_{title:02d}_{{n}}.VOB'.format(title=title)

    def __init__(self, /, *, file_name=None, dvd_reader=None, vts=None, menu=None):
        if file_name is None and dvd_reader is not None and vts is not None:
            file_name = '{dvd_reader.device}:/VIDEO_TS/{pat}'.format(
                dvd_reader=dvd_reader,
                pat=self.get_vob_file_name_pattern(title=vtx, menu=menu))
        elif file_name is not None and dvd_reader is None and vts is None:
            pass
        else:
            raise TypeError
        self.dvd_reader = dvd_reader
        self.vts = vts
        super().__init__(file_name=file_name)

    @property
    def is_multifile(self):
        return self.dvd_reader is None \
            and '{n}' in os.fspath(self.file_name)

    @property
    def is_menu(self):
        return (
            '_0.VOB' in os.fspath(self.file_name)
            or 'VIDEO_TS.VOB' in os.fspath(self.file_name)
        )

    def open(self, mode='r', encoding=None, **kwargs):
        if not self.dvd_reader:
            return super().open(mode=mode, encoding=encoding, **kwargs)
        if 't' not in mode and 'b' not in mode:
            mode += self.open_mode
        assert 'r' in mode
        assert 't' not in mode
        assert encoding is None
        return True

    def open_index(self, /, file_index):
        if not self.dvd_reader:
            return super().open_index(file_index=file_index)
        if self.fp and self.file_index == file_index:
            return
        if self.is_menu:
            assert file_index == 0
            title = 0
        else:
            title = self.file_index + 1
        libdvdread.DVDOpenFile(
            self.dvd_reader,
            title,
            libdvdread.DVD_READ_MENU_VOBS if self.is_menu else libdvdread.DVD_READ_TITLE_VOBS,
        )
        try:
            file_name = self.file_names[file_index]
        except IndexError:
            raise FileNotFoundError(errno.ENOENT,
                                    os.strerror(errno.ENOENT),
                                    f'File w/ index {file_index}')
        new_fp = open(file_name,
                      mode=self.open_mode,
                      encoding=self.open_encoding)
        try:
            if self.fp:
                self.close()
        finally:
            self.file_index, self.fp = file_index, new_fp

    def get_multifile_file_name(self, n):
        self.assert_file_name_defined()
        assert self.is_multifile
        # assert n in range(MAX_MULTIVOB_FILES)
        return Path(os.fspath(self).format(n=n))

    def iter_multifile_file_names(self):
        self.assert_file_name_defined()
        if self.is_multifile:
            for n in range(MAX_MULTIVOB_FILES):
                multifile_file_name = self.get_multifile_file_name(n)
                if not multifile_file_name.exists():
                    if n == 0:
                        raise FileNotFoundError(errno.ENOENT,
                                                os.strerror(errno.ENOENT),
                                                os.fspath(multifile_file_name))
                    break
                yield multifile_file_name
        else:
            yield self.file_name

VobFile._build_extension_to_class_map()
