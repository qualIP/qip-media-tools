
__all__ = [
        'File',
        'TextFile',
        'BinaryFile',
        'HtmlFile',
        'XmlFile',
        'TempFile',
        'safe_write_file',
        'safe_write_file_eval',
        'safe_read_file',
        ]

import contextlib
import hashlib
import os
import urllib.parse
import urllib.request
import io
import tempfile
import shutil
import subprocess

import logging
log = logging.getLogger(__name__)

from qip.propex import propex
from qip.decorator import func_once

# http://stackoverflow.com/questions/3431825/generating-a-md5-checksum-of-a-file
def hashfile(afile, hasher, blocksize=65536):
    buf = afile.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = afile.read(blocksize)
    return hasher
# [(fname, hashfile(open(fname, 'rb'), hashlib.md5())) for fname in fnamelst]

class File(object):

    file_name = propex(
        name='file_name',
        type=(None, propex.test_istype(str)),
        fdel=None)

    open_mode = propex(
        name='open_mode',
        default='',
        type=propex.test_in(('', 't', 'b')))

    @classmethod
    def new_by_file_name(cls, file_name, *args, default_class=None, **kwargs):
        ext = os.path.splitext(file_name)[1]
        factory_cls = cls._extension_to_class_map.get(ext, default_class)
        if factory_cls is None:
            load_all_file_types()
            factory_cls = cls._extension_to_class_map.get(ext, default_class)
        if factory_cls is None:
            log.debug('%r._extension_to_class_map = %r', cls, cls._extension_to_class_map)
            raise ValueError('Unknown extension %r' % (ext,))
        return factory_cls(file_name, *args, **kwargs)

    def __init__(self, file_name, open_mode=None):
        self.file_name = file_name
        if open_mode is not None:
            self.open_mode = open_mode
        super().__init__()

    def __str__(self):
        return self.file_name

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.file_name)

    def exists(self):
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        return os.path.exists(self.file_name)

    def getsize(self):
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        return os.path.getsize(self.file_name)

    def unlink(self, force=False):
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        try:
            os.unlink(self.file_name)
        except FileNotFoundError:
            if not force:
                raise

    def truncate(self, length):
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        # TODO support os.truncate(self.fd, length)
        os.truncate(self.file_name, length)

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
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        if not overwrite and self.exists():
            return False
        log.info('Downloading %s...' % (url,))
        #log.info('Downloading %s to %s...' % (url, self))
        with TempFile(file_name=self.file_name + '.tmp', open_mode=self.open_mode) as tmp_file:
            urllib.request.urlretrieve(url, filename=tmp_file.file_name)
            if md5:
                file_md5 = tmp_file.md5.hexdigest()
                if file_md5 != md5:
                    raise ValueError('MD5 hash of %s is %s, expected %s' % (tmp_file, file_md5, md5))
            shutil.move(tmp_file.file_name, self.file_name)
            tmp_file.delete = False
        return True

    def move(self, dst, update_file_name=True):
        dst = str(dst)
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
        if fp:
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

    def open(self, mode='r', encoding=None):
        assert not self.fp
        if not self.file_name:
            raise ValueError('%r: file_name not defined' % (self,))
        if 't' not in mode and 'b' not in mode:
            mode += self.open_mode
        return open(self.file_name, mode=mode, encoding=encoding)

    def fdopen(self, fd, mode='r', encoding=None):
        assert not self.fp
        if 't' not in mode and 'b' not in mode:
            mode += self.open_mode
        return os.fdopen(fd, mode=mode, encoding=encoding)

    def read(self):
        fp = self.fp or self.open()
        return fp.read()

    def write(self, *args, **kwargs):
        fp = self.fp or self.open(mode='w')
        return fp.write(*args, **kwargs)

    def close(self):
        fp = self.fp
        if fp:
            fp.close()
            self.fp = None
        # No exception if no fp, like file objects

    @classmethod
    def _build_extension_to_class_map(cls):
        cls._extension_to_class_map = {}
        for subcls in cls.__subclasses__():
            subcls._build_extension_to_class_map()
            cls._extension_to_class_map.update(subcls._extension_to_class_map)
        for k in cls.__dict__.get('_common_extensions', ()):
            cls._extension_to_class_map[k] = cls

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

def cache_url(url, cache_dict={}):
    assert isinstance(url, str)
    purl = urllib.parse.urlparse(url)
    if purl.scheme == 'file':
        return os.path.normpath(purl.path)
    elif purl.scheme == '':
        # May not be true if url contains a #, in which case purl.path will be truncated
        #assert purl.path == url, (purl.path, url)
        #return os.path.normpath(purl.path)
        return os.path.normpath(url)

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

            suffix = os.path.splitext(purl.path)[1]
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

    return tfp.name

# safe_write_file {{{

def safe_write_file(file, content, **kwargs):
    def body(fp):
        fp.write(content)
    safe_write_file_eval(file, body, **kwargs)

# }}}
# safe_write_file_eval {{{

def safe_write_file_eval(file, body, *, text=False, encoding='utf-8'):
    file = str(file)
    if (
            not os.access(file, os.W_OK) and
            (os.path.exists(file) or
                not os.access(os.path.dirname(file), os.W_OK))):
        pass # XXXJST TODO: raise Exception('couldn\'t open "%s"' % (file,))
    with TempFile(file + '.tmp') as tmp_file:
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
    return open(str(file), mode='r', encoding=encoding).read()

# }}}

@func_once
def load_all_file_types():
    import qip.cdda
    #import qip.file
    import qip.json
    import qip.mm
    import qip.img
    import qip.snd
    import qip.mp4
    import qip.matroska
    import qip.mp3
    import qip.wav

File._build_extension_to_class_map()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
