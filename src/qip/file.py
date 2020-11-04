
__all__ = [
        'toPath',
        'File',
        'TextFile',
        'BinaryFile',
        'HtmlFile',
        'XmlFile',
        'TempFile',
        'write_to_temp_context',
        'safe_write_file',
        'safe_write_file_eval',
        'safe_read_file',
        ]

from contextlib import contextmanager
from gettext import gettext as _, ngettext
from pathlib import Path
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

_osPath = type(Path(''))

def toPath(value):
    if type(value) is _osPath:
        return value
    if isinstance(value, File):
        return value.file_name
    return Path(value)

# http://stackoverflow.com/questions/3431825/generating-a-md5-checksum-of-a-file
def hashfile(afile, hasher, blocksize=65536):
    buf = afile.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = afile.read(blocksize)
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
                msg = _('argument "-" with mode %r') % mode
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
                message = _("can't open %s: %s")
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
        if default_class is True:
            default_class = cls
        file_name = toPath(file_name)
        ext = file_name.suffix
        if cls._extension_to_class_map is None:
            cls._update_extension_to_class_map()
        factory_cls = cls._extension_to_class_map.get(ext, None)
        if not factory_cls:
            load_all_file_types()
            factory_cls = cls._extension_to_class_map.get(ext, default_class)
        if not factory_cls:
            log.debug('%r._extension_to_class_map = %r', cls, cls._extension_to_class_map)
            raise ValueError('Unknown extension %r' % (ext,))
        return factory_cls(file_name, *args, **kwargs)

    def __init__(self, file_name, open_mode=None):
        self.file_name = file_name
        if open_mode is not None:
            self.open_mode = open_mode
        super().__init__()

    def __fspath__(self):
        if self.file_name is None:
            raise ValueError('%r: file_name not defined' % (self,))
        return os.fspath(self.file_name)

    def __str__(self):
        if self.file_name is None:
            return 'None'
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

    def hash(self, hasher):
        return hashfile(self.open(mode='rb'), hasher)

    md5 = propex(
        name='md5')

    @md5.initter
    def md5(self):
        return self.hash(hashlib.md5())

    def download(self, url, md5=None, overwrite=False):
        self.assert_file_name_defined()
        if not overwrite and self.exists():
            return False
        log.info('Downloading %s...' % (url,))
        #log.info('Downloading %s to %s...' % (url, self))
        with write_to_temp_context(self, open=False) as tmp_file:
            urllib.request.urlretrieve(url, filename=tmp_file.file_name)
            if md5:
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
                    dstfp.write(srcfp.read())

    fp = propex(
        name='fp',
        default=None,
        type=(None,
              propex.test_isinstance((
                  io.IOBase,
                  tempfile._TemporaryFileWrapper,
              ))))

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
        if not shutil.which('pv'):
            return self.open(mode=mode, encoding=encoding)
        assert not self.fp
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        if 't' not in mode and 'b' not in mode:
            mode += self.open_mode
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
        assert self.fp is None
        self.assert_file_name_defined()
        if 't' not in mode and 'b' not in mode:
            mode += self.open_mode
        return self.file_name.open(mode=mode, encoding=encoding, **kwargs)

    def fdopen(self, fd, mode='r', encoding=None):
        assert not self.fp
        if 't' not in mode and 'b' not in mode:
            mode += self.open_mode
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

    def close(self):
        fp = self.fp
        if fp:
            fp.close()
            self.fp = None
        # No exception if no fp, like file objects

    @classmethod
    def _build_extension_to_class_map(cls):
        cls._extension_to_class_map = {
            k: cls
            for k in cls.__dict__.get('_common_extensions', ())
        }
        for sub_cls in cls.__subclasses__():
            sub_cls._build_extension_to_class_map()
        if cls._extension_to_class_map:
            cls._update_extension_to_class_map()

    @classmethod
    def _update_extension_to_class_map(cls):
        old_len = len(cls._extension_to_class_map)
        for sub_cls in cls.__subclasses__():
            cls._extension_to_class_map.update(sub_cls._extension_to_class_map)
        if old_len != len(cls._extension_to_class_map):
            for base_cls in cls.__bases__:
                try:
                    base_cls._update_extension_to_class_map()
                except AttributeError:
                    pass

class TextFile(File):

    _common_extensions = (
        '.txt',
    )

    open_mode = 't'

    def read(self):
        return str(super().read())

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


@contextmanager
def write_to_temp_context(file, *, suffix='.tmp', open_mode=None, text=None, open=True):
    if isinstance(file, (str, os.PathLike)):
        file = TextFile(file) if text else BinaryFile(file)
    assert isinstance(file, File)
    assert not file.fp
    assert file.file_name
    assert suffix
    if open_mode is None:
        if text is not None:
            open_mode = 't' if text else 'b'
        else:
            open_mode = file.open_mode
    else:
        if text is not None:
            raise TypeError('Both open_mode and text provided')
    with TempFile(file_name=file.file_name.with_suffix(file.file_name.suffix + suffix), open_mode=open_mode) as tmp_file:
        if open:
            file.fp = tmp_file.fp = tmp_file.open('w')
        try:
            yield tmp_file
        finally:
            file.fp = None
        tmp_file.close()
        tmp_file.move(file.file_name)
        tmp_file.delete = False


class ConfigFile(File):

    _common_extensions = (
        '.conf',
    )


def cache_url(url, cache_dict={}):
    if isinstance(url, Path):
        return url
    assert isinstance(url, str)
    purl = urllib.parse.urlparse(url)
    if purl.scheme == 'file':
        return Path(purl.path).resolve()
    elif purl.scheme == '':
        # May not be true if url contains a #, in which case purl.path will be truncated
        #assert purl.path == url, (purl.path, url)
        #return Path(purl.path).resolve()
        return Path(url).resolve()

    try:
        tfp = cache_dict[url]
    except KeyError:
        req = urllib.request.Request(url)
        from qip.app import app
        user_agent = app.user_agent
        if user_agent:
            req.add_header('User-Agent', user_agent)
        opener = urllib.request.build_opener()
        with opener.open(req) as fp:
            headers = fp.info()

            suffix = Path(purl.path).suffix
            tfp = tempfile.NamedTemporaryFile(suffix=suffix)

            bs = 1024*8
            size = -1
            read = 0
            blocknum = 0
            if "content-length" in headers:
                size = int(headers["Content-Length"])

            #if reporthook:
            #    reporthook(blocknum, bs, size)

            while True:
                block = fp.read(bs)
                if not block:
                    break
                read += len(block)
                tfp.write(block)
                blocknum += 1
                #if reporthook:
                #    reporthook(blocknum, bs, size)

        if size >= 0 and read < size:
            raise ContentTooShortError(
                "retrieval incomplete: got only %i out of %i bytes"
                % (read, size))

        tfp.flush()
        cache_dict[url] = tfp

    return Path(tfp.name)

# safe_write_file {{{

def safe_write_file(file, content, **kwargs):
    def body(fp):
        fp.write(content)
    safe_write_file_eval(file, body, **kwargs)

# }}}
# safe_write_file_eval {{{

def safe_write_file_eval(file, body, *, text=False, encoding='utf-8'):
    file = toPath(file)
    if (
            not os.access(file, os.W_OK) and
            (file.exists() or
                not os.access(file.parent, os.W_OK))):
        pass # XXXJST TODO: raise Exception('couldn\'t open "%s"' % (file,))
    with TempFile(file.with_suffix(file.suffix + '.tmp')) as tmp_file:
        open_kwargs = {}
        if text:
            open_kwargs['encoding'] = encoding
        with tmp_file.open(mode='wt' if text else "wb",
                           **open_kwargs) as fp:
            ret = body(fp)
        shutil.move(tmp_file.file_name, file)
        tmp_file.delete = False
    return ret

# }}}
# safe_read_file {{{

def safe_read_file(file, *, encoding='utf-8'):
    return open(os.fspath(file), mode='r', encoding=encoding).read()

# }}}

@func_once
def load_all_file_types():
    import qip.cdda
    #import qip.file
    import qip.json
    import qip.mm
    import qip.img
    import qip.mp4
    import qip.matroska
    import qip.mp3
    import qip.wav

File._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
