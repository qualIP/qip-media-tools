# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'toPath',
        'File',
        'TextFile',
        'BinaryFile',
        'HtmlFile',
        'XmlFile',
        'TempFile',
        ]

from contextlib import contextmanager
from gettext import gettext as _, ngettext
from pathlib import Path
import functools
import hashlib
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

import logging
log = logging.getLogger(__name__)

from qip.propex import propex
from qip.decorator import func_once
from qip.utils import Auto

_osPath = type(Path(''))


def toPath(value):
    if type(value) is _osPath:
        return value
    if isinstance(value, File):
        return value.file_name
    return Path(value)

# http://stackoverflow.com/questions/3431825/generating-a-md5-checksum-of-a-file
def hashfile(afile, hasher, blocksize=65536,
             show_progress_bar=None, progress_bar_max=None, progress_bar_title=None,
             ):
    pos = 0
    if show_progress_bar is None:
        show_progress_bar = progress_bar_max is not None
    if show_progress_bar:
        try:
            from qip.utils import BytesBar, ProgressSpinner
        except ImportError:
            show_progress_bar = False
    if show_progress_bar:
        start_pos = afile.tell()
        if progress_bar_max is None:
            if afile.seekable():
                afile.seek(0, io.SEEK_END)
                try:
                    size = afile.tell()
                finally:
                    afile.seek(start_pos)
                progress_bar_max = size - start_pos
        if progress_bar_max is not None:
            progress_bar = BytesBar(progress_bar_title or 'Calculating hash',
                                       max=progress_bar_max)
        else:
            progress_bar = ProgressSpinner(progress_bar_title or 'Calculating hash')
    try:
        buf = afile.read(blocksize)
        pos += len(buf)
        while len(buf) > 0:
            hasher.update(buf)
            if show_progress_bar:
                progress_bar.goto(pos - start_pos)
            buf = afile.read(blocksize)
            pos += len(buf)
    finally:
        if show_progress_bar:
            progress_bar.finish()
    return hasher
    # [(fname, hashfile(open(fname, 'rb'), hashlib.md5())) for fname in fnamelst]


class _argparse_type(object):

    def __init__(self, file_cls, mode='r', resolved=True, **kwargs):
        self._file_cls = file_cls
        self._resolved = resolved
        kwargs['mode'] = mode
        self._kwargs = kwargs

    def __call__(self, file_name):
        file_cls = self._file_cls
        kwargs = self._kwargs
        fp = None
        s_file_name = repr(file_name)

        # the special argument "-" means sys.std{in,out}
        if file_name == '-':
            file_name = None
            mode = kwargs['mode']
            if 'r' in mode:
                s_file_name = '<stdin>'
                fp = sys.stdin
            elif 'w' in mode:
                s_file_name = '<stdout>'
                fp = sys.stdout
            else:
                msg = 'argument "-" with mode %r' % mode
                raise ValueError(msg)
            file = file_cls(file_name=None)
        else:
            if self._resolved:
                file_name = toPath(file_name).resolve()
            file = file_cls.new_by_file_name(file_name)

        if fp is None:
            try:
                fp = file.open(**kwargs)
            except OSError as e:
                message = "can't open %s: %s"
                raise TypeError(message % (s_file_name, e))

        file.fp = fp
        return file

    def __repr__(self):
        file_cls = self._file_cls
        kwargs = self._kwargs
        args_str = ', '.join(['%s=%r' % (kw, arg) for kw, arg in kwargs.items()])
        return '%s.argparse_type(%s)' % (file_cls.__name__, args_str)


class File(object):
    # os.PathLike is not a parent since os.PathLike.__subclasses__ is not well formed in Python 3.7 as it doesn't check cls is PathLike

    file_name = propex(
        name='file_name',
        type=(None,
              toPath,
              ),
        fdel=None)

    open_mode = propex(
        name='open_mode',
        default='',
        type=propex.test_in(('', 't', 'b')))

    mime_type = propex(
        name='mime_type',
        type=str)

    @mime_type.initter
    def mime_type(self):
        from qip.exec import dbg_exec_cmd
        try:
            mime_type = dbg_exec_cmd(
                ['file', '--brief', '--mime-type', self],
                encoding='utf-8')
        except subprocess.CalledProcessError as e:
            raise AttributeError
        mime_type = mime_type.strip()
        if not mime_type:
            raise AttributeError
        return mime_type

    open_encoding = None

    @contextmanager
    def rename_temporarily(self, *, suffix='.tmp',
                           unlink_except=True,
                           replace_ok=False,
                           unlink_ok=False,
                           ):
        orig_name = self.file_name
        temp_name = orig_name.with_name(orig_name.name + suffix)
        try:
            self.file_name = temp_name
            yield
        except:
            if unlink_except:
                self.unlink(force=True)
            raise
        finally:
            self.file_name = orig_name
        if replace_ok:
            temp_name.replace(target=self)
        if unlink_ok:
            temp_name.unlink(force=True)

    @classmethod
    def argparse_type(cls, *args, **kwargs):
        return _argparse_type(file_cls=cls, *args, **kwargs)

    @classmethod
    def new_by_file_name(cls, file_name, *args, default_class=True, **kwargs):
        file_name = toPath(file_name)
        ext = file_name.suffix
        factory_cls = cls.cls_from_suffix(file_name.suffix,
                                          default_class=default_class)
        return factory_cls(file_name, *args, **kwargs)

    @classmethod
    def cls_from_suffix(cls, suffix, default_class=True):
        if default_class is True:
            default_class = cls
        if cls.__dict__.get('_extension_to_class_map', None) is None:
            cls._extension_to_class_map = {}
            cls._update_extension_to_class_map()
        factory_cls = cls._extension_to_class_map.get(suffix, None)
        if not factory_cls:
            load_all_file_types()
            factory_cls = cls._extension_to_class_map.get(suffix, default_class)
        if not factory_cls:
            log.debug('%r._extension_to_class_map = %r', cls, cls._extension_to_class_map)
            raise ValueError('Unknown extension %r' % (suffix,))
        return factory_cls

    @classmethod
    def NamedTemporaryFile(cls, mode=None, buffering=-1, encoding=None, newline=None, suffix=None, prefix=None, dir=None, delete=True, *, errors=None):
        '''NamedTemporaryFile(mode='w+b', buffering=-1, encoding=None, newline=None, suffix=None, prefix=None, dir=None, delete=True, *, errors=None)'''

        encoding = encoding or cls.open_encoding
        if mode is None:
            if encoding is None and errors is None:
                # Class default
                mode = 'w+' + (cls.open_mode or 't')
            else:
                mode = 'w+' + ('t' if (encoding or errors) else 'b')

        if suffix is None:
            for suffix in cls.get_default_extensions():
                break

        kwargs = {}
        if errors is not None:
            # Python 3.7 compat: tempfile.NamedTemporaryFile does not support `errors` argument
            kwargs['errors'] = errors

        tmp_fp = tempfile.NamedTemporaryFile(
            mode=mode, buffering=buffering, encoding=encoding, newline=newline,
            suffix=suffix, prefix=prefix, dir=dir, delete=delete,
            **kwargs)

        file = cls.new_by_file_name(file_name=tmp_fp.name)
        assert isinstance(file, cls)
        file.open_encoding = encoding
        file.open_mode = 'b' if 'b' in mode else 't'
        file.fp = tmp_fp
        return file

    def __init__(self, file_name, open_mode=None):
        self.file_name = file_name
        if open_mode is not None:
            self.open_mode = open_mode or ''
        super().__init__()

    def __copy__(self):
        other = self.__class__(file_name=self.file_name)
        other.open_mode = self.open_mode
        other.mime_type = self.mime_type
        # other.fp = self.fp
        return other

    def __fspath__(self):
        if self.file_name is None:
            raise ValueError('%r: file_name not defined' % (self,))
        return os.fspath(self.file_name)

    def __str__(self):
        if self.file_name is None:
            return '(unnamed)'
        else:
            return os.fspath(self)

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, str(self))

    def assert_file_name_defined(self):
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))

    def exists(self):
        self.assert_file_name_defined()
        return self.file_name.exists()

    def getsize(self):
        self.assert_file_name_defined()
        return self.file_name.stat().st_size

    def unlink(self, force=False):
        self.assert_file_name_defined()
        try:
            self.file_name.unlink()
        except FileNotFoundError:
            if not force:
                raise

    def send2trash(self):
        self.assert_file_name_defined()
        from send2trash import send2trash
        send2trash(os.fspath(self))

    def truncate(self, length):
        if self.fd is not None:
            os.truncate(self.fd, length)
        else:
            self.assert_file_name_defined()
            os.truncate(self.file_name, length)

    def touch(self):
        self.assert_file_name_defined()
        return self.file_name.touch()

    def test_integrity(self):
        raise NotImplementedError()

    def hash(self, hasher, **kwargs):
        return hashfile(self.open(mode='rb'), hasher, **kwargs)

    md5 = propex(
        name='md5')

    @md5.initter
    def md5(self):
        return self.md5_ex()

    def md5_ex(self, **kwargs):
        try:
            return getattr(self, '_md5')
        except AttributeError:
            md5 = self.hash(hashlib.md5(), **kwargs)
            self.md5 = md5
            return md5

    def download(self, url, md5=None, overwrite=False):
        assert self.fp is None, f'File is already opened: {self}'
        self.assert_file_name_defined()
        if not overwrite and self.exists():
            return False
        log.info('Downloading %s...' % (url,))
        #log.info('Downloading %s to %s...' % (url, self))
        with self.rename_temporarily(replace_ok=True):
            urllib.request.urlretrieve(url, filename=self.file_name)
            if md5:
                # write -> read
                self.flush()
                self.seek(0)
                file_md5 = tmp_file.md5.hexdigest()
                if file_md5 != md5:
                    raise ValueError('MD5 hash of %s is %s, expected %s' % (tmp_file, file_md5, md5))
        return True

    def replace(self, target, update_file_name=True):
        # Note: replace could fail if files are on different filesystems. Use move instead.
        target = toPath(target)
        self.assert_file_name_defined()
        self.file_name.replace(target=target)
        if update_file_name:
            self.file_name = target

    def move(self, dst, update_file_name=True):
        dst = toPath(dst)
        shutil.move(self.file_name, dst)
        if update_file_name:
            self.file_name = dst

    rename = move

    def combine_from(self, other_files):
        assert not self.fp
        with self.open(mode='w') as dstfp:
            for other_file in other_files:
                with other_file.open() as srcfp:
                    shutil.copyfileobj(srcfp, dstfp)

    fp = propex(
        name='fp',
        default=None,
        type=(None,
              propex.test_isinstance((
                  io.IOBase,
                  tempfile._TemporaryFileWrapper,
              ))))

    @property
    def fd(self):
        fp = self.fp
        return fp and fp.fileno()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        f = getattr(super(), '__exit__', None)
        return f(*exc) if f else None

    @property
    def closed(self):
        return not self.fp or self.fp.closed

    @property
    def is_text(self):
        return 'b' not in self.open_mode

    def fileno(self):
        fp = self.fp
        if fp is not None:
            return fp.fileno()
        raise ValueError('I/O operation on closed file')  # like file objects

    def pvopen(self, mode='r', encoding=None):
        """p1 = myfile.pvopen()
           p2 = myexe2.popen([...], stdin=p1)
        """
        assert 'r' in mode
        encoding = encoding or self.open_encoding
        if not shutil.which('pv'):
            return self.open(mode=mode, encoding=encoding)
        assert not self.fp
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        if 't' not in mode and 'b' not in mode and encoding is None:
            mode += self.open_mode
        if 'b' in mode:
            encoding = None
        p = subprocess.Popen(['pv', self.file_name],
                             stdout=subprocess.PIPE,
                             text=(
                                 True if 't' in mode else (
                                     False if 'b' in mode else
                                     None)),
                             encoding=encoding,
                  )
        return p.stdout

    def open(self, mode='r', encoding=None, **kwargs):
        assert self.fp is None, f'File is already opened: {self}'
        encoding = encoding or self.open_encoding
        self.assert_file_name_defined()
        if 't' not in mode and 'b' not in mode and encoding is None:
            mode += self.open_mode
        if 'b' in mode:
            encoding = None
        return self.file_name.open(mode=mode, encoding=encoding, **kwargs)

    def fdopen(self, fd, mode='r', encoding=None):
        assert self.fp is None, f'File is already opened: {self}'
        encoding = encoding or self.open_encoding
        if 't' not in mode and 'b' not in mode and encoding is None:
            mode += self.open_mode
        if 'b' in mode:
            encoding = None
        return os.fdopen(fd, mode=mode, encoding=encoding)

    def read(self):
        if self.fp is not None:
            return self.fp.read()
        # self.file_name.read_text/read_bytes
        with self.open(mode='r') as fp:
            return fp.read()

    def write(self, *args, **kwargs):
        if self.fp:
            return self.fp.write(*args, **kwargs)
        # self.file_name.write_text/write_bytes
        with self.open(mode='w') as fp:
            return fp.write(*args, **kwargs)

    def flush(self):
        if self.fp:
            self.fp.flush()

    def isatty(self):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.isatty()

    def readable(self):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.readable()

    def readline(self, size=-1):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.readline(size=size)

    def readlines(self, hint=-1):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.readlines(hint=hint)

    def seek(self, offset, whence=io.SEEK_SET):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.seek(offset, whence)

    def seekable(self):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.seekable()

    def tell(self):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.tell()

    def truncate(self, size=None):
        if self.closed:
            self.assert_file_name_defined()
            return os.truncate(self.file_name, size)
        else:
            return self.fp.truncate(size)

    def writable(self):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.writable()

    def writelines(self, lines):
        if self.closed:
            raise ValueError('I/O operation on closed file')
        return self.fp.writelines(lines)

    def close(self):
        fp = self.fp
        if fp is not None:
            self.fp = None
            fp.close()
        # No exception if no fp, like file objects

    def samefile(self, other):
        self.assert_file_name_defined()
        if not isinstance(other, Path):
            other = Path(other)
        return self.file_name.samefile(other)

    @classmethod
    def _build_extension_to_class_map(cls):
        cls._extension_to_class_map = {
            k: cls
            for k in cls.__dict__.get('_common_extensions', ())
        }
        for sub_cls in cls.__subclasses__():
            sub_cls._build_extension_to_class_map()
        cls._update_extension_to_class_map(force=True)

    @classmethod
    def _update_extension_to_class_map(cls, force=False):
        old_len = 0 if force else len(cls._extension_to_class_map)
        for sub_cls in cls.__subclasses__():
            cls._extension_to_class_map.update(sub_cls._extension_to_class_map)
        if old_len != len(cls._extension_to_class_map):
            for base_cls in cls.__bases__:
                try:
                    base_cls._update_extension_to_class_map()
                except AttributeError:
                    pass

    @classmethod
    def get_common_extensions(cls):
        common_extensions = set(cls.__dict__.get('_common_extensions', ()))
        for sub_cls in cls.__subclasses__():
            common_extensions |= sub_cls.get_common_extensions()
        return common_extensions

    @classmethod
    def get_default_extensions(cls):
        seen = set()
        for ext in cls.__dict__.get('_common_extensions', ()):
            if ext not in seen:
                yield ext
                seen.add(ext)
        for base_cls in cls.__bases__:
            if issubclass(base_cls, File):
                for ext in base_cls.get_default_extensions():
                    if ext not in seen:
                        yield ext
                        seen.add(ext)

    @classmethod
    def generate_file_name(cls, dirname=None, basename=None, ext=Auto):
        dirname = Path(dirname) if dirname else None
        if not basename:
            basename = cls.__class__.__name__
            basename = re.sub(r'File$', '', basename)
            basename = re.sub(r'(?=[A-Z][a-z])(?<!Mc)(?<!Mac)', r' ', basename)       # AbCDef ->  AbC Def (not Mc Donald)
            basename = re.sub(r'[a-z](?=[A-Z])(?<!Mc)(?<!Mac)', r'\g<0> ', basename)  # AbC Def -> Ab C Def (not Mc Donald)
            basename = re.sub(r'[A-Za-z](?=\d)', r'\g<0> ', basename)  # ABC123 -> ABC 123
            basename = re.sub(r'[^A-Za-z0-9]+', r'-', basename)      # AB$_12 -> AB-12
            basename = basename.strip('-')                           # -ABC-  -> ABC
        if not basename:
            basename = 'file'
        basename = Path(basename)
        file_name = dirname / basename if dirname else basename
        if ext is Auto:
            for ext in cls.get_default_extensions():
                break
            else:
                ext = None
        if ext:
            file_name = Path(os.fspath(file_name) + ext)
        return file_name

    def decode_ffmpeg_args(self, **kwargs):
        return kwargs


class TextFile(File):

    _common_extensions = (
        '.txt',
    )

    open_mode = 't'

    open_encoding = 'utf-8'


class BinaryFile(File):

    open_mode = 'b'


class HtmlFile(TextFile):

    _common_extensions = (
        '.html',
        '.htm',
    )


class XmlFile(TextFile):

    _common_extensions = (
        '.xml',
    )

    def write_xml(self, xml, file=None, encoding=None, xml_declaration=True):
        if file is None:
            file = self.fp
        if file is None:
            with self.open('w') as file:
                return self.write_xml(xml,
                                      file=file,
                                      encoding=encoding,
                                      xml_declaration=xml_declaration)
        if encoding is None:
            encoding=getattr(file, 'encoding', None) or 'utf-8'
        # ElementTree wants 'unicode' instead of 'utf-8'!
        xml_encoding = {
            'utf-8': 'unicode',
        }.get(encoding, encoding)
        xml.write(file,
                  xml_declaration=xml_declaration,
                  encoding=xml_encoding)


class TempFile(File):

    delete = True

    # TODO Allow base class override in __new__

    def __init__(self, file_name, *args, delete=True, **kwargs):
        self.delete = delete
        super().__init__(file_name=file_name, *args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.delete:
            self.unlink(force=True)
            self.delete = False
        f = getattr(super(), '__exit__', None)
        return f(*exc) if f else None

    def __del__(self):
        if self.delete:
            self.unlink(force=True)

    @classmethod
    def mkstemp(cls, *, open=False, text=False, **kwargs):
        '''mkstemp(suffix=, prefix=, dir=, text=, open=, ...)'''
        tmpfile = cls(file_name=None,
                      open_mode='t' if text else 'b')
        fd, tmpfile.file_name = tempfile.mkstemp(text=text, **kwargs)
        if open:
            tmpfile.fp = tmpfile.fdopen(fd, mode='w')
        else:
            os.close(fd)
        return tmpfile




class ConfigFile(File):

    _common_extensions = (
        '.conf',
    )


def cache_url(url, cache_dict={}):
    if isinstance(url, os.PathLike):
        return Path(url)
    assert isinstance(url, str)
    purl = urllib.parse.urlparse(url)
    if purl.scheme == 'file':
        return Path(purl.path).resolve()
    elif purl.scheme == '':
        # May not be true if url contains a #, in which case purl.path will be truncated
        #assert purl.path == url, (purl.path, url)
        #return Path(purl.path).resolve()
        return Path(url).resolve()
    temp_file = _lru_cache_url(url, Path(purl.path).suffix)
    return temp_file.file_name


@functools.lru_cache()
def _lru_cache_url(url, suffix):
    req = urllib.request.Request(url)
    from qip.app import app
    user_agent = app.user_agent
    if user_agent:
        req.add_header('User-Agent', user_agent)

    size = -1
    temp_file = BinaryFile.NamedTemporaryFile(suffix=suffix)

    opener = urllib.request.build_opener()
    with opener.open(req) as fp:

        headers = fp.info()
        if "content-length" in headers:
            size = int(headers["Content-Length"])

        shutil.copyfileobj(fsrc=fp, fdst=temp_file.fp)

    read = temp_file.tell()
    if size >= 0 and read < size:
        raise ContentTooShortError(f'retrieval incomplete: got only {read} out of {size} bytes')

    # write -> read
    temp_file.flush()
    temp_file.seek(0)

    return temp_file


@func_once
def load_all_file_types():
    import qip.avi
    import qip.cdda
    import qip.ffmpeg
    #import qip.file
    import qip.flac
    import qip.img
    import qip.json
    import qip.lodev
    import qip.matroska
    import qip.mm
    import qip.mp2
    import qip.mp3
    import qip.mp4
    import qip.ogg
    import qip.pgs
    #import qip.vob
    #import qip.vorbis
    import qip.wav

File._build_extension_to_class_map()
