#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import qip  # Executable support

import collections
import enum
import io
import logging
import os
log = logging.getLogger(__name__)

from qip.propex import propex
from qip.file import toPath, File

from qip.libudfread_swig import *
import qip.libudfread_swig as libudfread_swig

class udf_reader(object):

    handle = None  # "udfread *"

    udf_image_path = propex(
        name='udf_image_path',
        type=(None,
              toPath,
              ),
        fdel=None)

    def __init__(self, /, udf_image_path, open: bool=True):
        self.udf_image_path = udf_image_path
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
        handle = libudfread_swig.udfread_init()
        if handle is None:
            raise Exception(f'Can\'t init UDF reader!')
        self.handle = handle
        libudfread_swig.udfread_open(self.handle, os.fspath(self.udf_image_path))
        return self

    def close(self):
        handle = self.handle
        assert handle is not None
        try:
            libudfread_swig.udfread_close(handle);
        finally:
            self.handle = None

    def __repr__(self):
        return f'{self.__class__.__name__}()'

    @property
    def closed(self, /):
        return self.handle is None

    def get_volume_id(self):
        return libudfread_swig.udfread_get_volume_id(self.handle)

    def opendir(self, path):
        path = os.path.join('/', path)
        dir_handle = libudfread_swig.udfread_opendir(self.handle, path)
        if not dir_handle:
            raise Exception(f'Error opening UDF directory: {path!r}')
        return udf_dir(udf=self, handle=dir_handle, path=path)

    def openfile(self, path, mode=None):
        path = os.fspath(path)
        file_handle = libudfread_swig.udfread_file_open(self.handle, path)
        if not file_handle:
            raise Exception(f'Error opening UDF file: {path!r}')
        return udf_file_io(udf=self, udf_file_handle=file_handle, name=path, mode=mode)

    @classmethod
    def closedir(cls, dir_handle):
        libudfread_swig.udfread_closedir(dir_handle)

    @classmethod
    def closefile(cls, file_handle):
        libudfread_swig.udfread_file_close(file_handle)

class udf_dir(object):

    handle = None  # UDFDIR *

    def __init__(self, udf, handle, path):
        self.udf = udf
        self.handle = handle
        self.path = os.fspath(path)
        super().__init__()

    def __del__(self):
        if self.handle is not None:
            self.close()

    def __enter__(self):
        if self.handle is None:
            pass  # self.open()
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            self.close()
        f = getattr(super(), '__exit__', None)
        return f(*exc) if f else None

    def close(self):
        handle = self.handle
        assert handle is not None
        try:
            self.udf.closedir(dir_handle=self.handle)
        finally:
            self.handle = None

    def open_at(self, path, mode=None):
        subpath = os.fspath(path)
        path = os.path.join(self.path, subpath)
        file_handle = libudfread_swig.udfread_file_openat(self.handle, subpath)
        if not file_handle:
            raise Exception(f'Error opening UDF file: {path!r}')
        return udf_file_io(udf=self.udf, udf_file_handle=file_handle, name=path, mode=mode)

    def opendir_at(self, path):
        subpath = os.fspath(path)
        path = os.path.join(self.path, subpath)
        dir_handle = libudfread_swig.udfread_opendir_at(self.handle, subpath)
        if not dir_handle:
            raise Exception(f'Error opening UDF directory: {path!r}')
        return udf_dir(udf=self.udf, handle=dir_handle, path=path)

    def readdir(self):
        while True:
            dirent = libudfread_swig.udfread_dirent()
            if libudfread_swig.udfread_readdir(self.handle, dirent):
                yield UdfDirEntry(dir=self, dirent=dirent)
            else:
                break

    def rewinddir(self):
        libudfread_swig.udfread_rewinddir(self.handle)

class udf_file_io(io.IOBase):

    udf = None  # udf_reader
    udf_file_handle = None  # UDFFILE *

    def __init__(self, *, udf, udf_file_handle, name=None, mode=None, encoding=None, errors='strict', **kwargs):
        self.udf = udf
        self.udf_file_handle = udf_file_handle
        self.name = os.fspath(name) if name else None
        self.open_mode = mode or 'b'
        self.encoding = encoding
        self.errors = errors
        self.open_kwargs = kwargs
        super().__init__(**kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if not self.closed:
            self.close()
        f = getattr(super(), '__exit__', None)
        return f(*exc) if f else None

    def __iter__(self, /):
        raise io.UnsupportedOperation('__iter__')

    def __next__(self, /):
        raise io.UnsupportedOperation('__next__')

    def __repr__(self, /):
        return f'<{self.__class__.__name__} name={self.name!r}>'

    def close(self, /):
        if not self.closed:
            try:
                self.udf.closefile(self.udf_file_handle)
            finally:
                self.udf_file_handle = None

    def fileno(self, /):
        raise io.UnsupportedOperation('fileno')

    def flush(self, /):
        pass

    def isatty(self, /):
        return False

    def readable(self, /):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return True

    def readline(self, size=-1, /):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        raise io.UnsupportedOperation('readline')

    def readlines(self, hint=-1, /):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        raise io.UnsupportedOperation('readlines')

    def seek(self, offset, whence):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return libudfread_swig.udfread_file_seek(self.udf_file_handle, offset, whence)

    def seekable(self, /):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return True

    def tell(self, /):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return libudfread_swig.udfread_file_tell(self.udf_file_handle)

    def truncate(self, /, size=None):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        raise io.UnsupportedOperation('truncate')

    def writable(self, /):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return False

    def writelines(self, lines, /):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        raise io.UnsupportedOperation('writelines')

    @property
    def closed(self):
        return self.udf_file_handle is None

    @property
    def is_text(self):
        return 't' in self.open_mode

    def read(self, size=-1, /):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        buf = '' if self.is_text else b''
        while True:
            buf2 = libudfread_swig.wrap_udfread_file_read(self.udf_file_handle,
                                          UDF_BLOCK_SIZE * 10 if size < 0 else size)
            if buf2:
                if self.is_text:
                    buf2 = buf2.decode(self.encoding,
                                       self.errors)
                buf += buf2
                if size >= 0:
                    size -= len(buf2)
                    if size <= 0:
                        break
            else:
                break
        return buf

    def read_blocks(self, file_block, num_blocks, flags):
        return libudfread_swig.wrap_udfread_read_blocks(self.udf_file_handle, file_block, num_blocks, flags)

    def block_to_lba(self, file_block):
        return libudfread_swig.udfread_file_lba(self.udf_file_handle, file_block)

    def getsize(self):
        return libudfread_swig.udfread_file_size(self.udf_file_handle)

class UdfDirEntry(object):

    def __init__(self, dir, dirent):
        self.dir = dir
        self.dirent = dirent
        super().__init__()

    def __fspath__(self, /):
        return self.path

    def __repr__(self, /):
        return f'<{self.__class__.__name__} {os.fspath(self)!r}>'

    def inode(self, /):
        return None

    def is_dir(self, /, *, follow_symlinks=True):
        return self.dirent.d_type == libudfread_swig.UDF_DT_DIR

    def is_file(self, /, *, follow_symlinks=True):
        return self.dirent.d_type == libudfread_swig.UDF_DT_REG

    def is_symlink(self, /, *, follow_symlinks=True):
        return False

    def stat(self, /, *, follow_symlinks=True):
        size = None
        if self.is_file(follow_symlinks=follow_symlinks):
            with self.dir.open_at(self.dirent.d_name) as fp:
                size = fp.getsize()
        return collections.namedtuple(
            st_mode=0o555 if self.is_dir(follow_symlinks=follow_symlinks) else 0o444,
            st_ino=None,
            st_dev=None,
            st_nlink=1,
            st_uid=0,
            st_gid=0,
            st_size=size,
            st_atime=None,
            st_mtime=None,
            st_ctime=None,
        )

    @property
    def name(self):
        return self.dirent.d_name

    @property
    def path(self):
        return os.path.join(self.dir.path, self.name)

if __name__ == "__main__":
    import logging
    import sys
    from qip.app import app

    @app.main_wrapper
    def main():

        app.init(logging_level=logging.DEBUG)
        subparsers = app.parser.add_subparsers(dest='action', required=True)
        subparser = subparsers.add_parser('ls')
        subparser.add_argument('udf_image')
        subparser = subparsers.add_parser('cat')
        subparser.add_argument('udf_image')
        subparser.add_argument('file')
        app.parse_args()

        if app.args.action == 'ls':
            # https://code.videolan.org/videolan/libudfread/-/blob/master/examples/udfls.c

            with udf_reader(app.args.udf_image) as udf:

                print(f'Volume ID: {udf.get_volume_id()}')

                def _lsdir_at(d, depth):
                    for dirent in d.readdir():
                        if dirent.name in ('.', '..'):
                            continue
                        if dirent.is_dir():
                            print(f'\t\t {dirent.path}')
                            with d.opendir_at(dirent.name) as child_d:
                                _lsdir_at(child_d, depth + 1)
                        else:
                            stat = dirent.stat()
                            print('{:16d} {}'.format(
                                stat.size,
                                dirent.name))

                with udf.opendir("/") as root:
                    _lsdir_at(root, 0)

        elif app.args.action == 'cat':
            # https://code.videolan.org/videolan/libudfread/-/blob/master/examples/udfcat.c

            with udf_reader(app.args.udf_image) as udf:
                with udf.openfile(app.args.file) as fp:
                    got = 0
                    try:
                        while True:
                            buf = fp.read(2048)
                            if not buf:
                                break
                            sys.stdout.buffer.write(buf)
                            got += len(buf)
                    finally:
                        sys.stdout.flush()
                    print(f'wrote {got} bytes of {fp.getsize()}', file=sys.stderr)

        else:
            raise NotImplementedError(app.args.action)

    main()
