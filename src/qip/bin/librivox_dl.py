#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

#if __name__ == "__main__":
#    import os, sys
#    sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), os.path.pardir, "lib", "python"))

from gettext import gettext as _
from pathlib import Path
import argparse
import functools
import io
import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

from qip.app import app
from qip.file import *
from qip.mm import *
from qip.img import *
from qip.cmp import *
from qip.librivox import *
from qip import json
from qip.mp4 import M4bFile

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='Librivox Downloader',
            contact='jst@qualipsoft.com',
            )

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    pgroup.add_argument('--continue', dest='_continue', action='store_true', help='continue previous download')
    pgroup.add_argument('--interactive', '-i', action='store_true', help='interactive mode')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')

    pgroup = app.parser.add_argument_group('Librivox Selection')
    app.parser.add_argument('--format', default=None, help='file format')
    app.parser.add_argument('--url', default=None, help='librivox or Internet Archive URL')

    app.parser.add_argument('--dir', default=None, type=Path, help='output directory')
    app.parser.add_argument('--m4b', action='store_true', help='create a M4B audiobook')

    pgroup = app.parser.add_argument_group('Audiobook Control')
    pgroup.add_argument('--m4b-reuse-chapters', action='store_true', help='M4B: reuse chapters.txt file')
    pgroup.add_argument('--m4b-single', action='store_true', help='M4B: singles')

    app.parse_args()

    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)

    audiobook = M4bFile(file_name=None)

    if app.args._continue:
        if app.args.dir is None:
            app.args.dir = '.'
    else:
        if app.args.url is None:
            app.parser.error(_('the following arguments is required: %s') % ('--url',))
        if app.args.dir is None:
            url = app.args.url
            p = urllib.parse.urlparse(url)
            if p.hostname in ('librivox.org', 'www.librivox.org'):
                # https://librivox.org/les-miserables-tome-4-by-victor-hugo/
                # <a href="http://archive.org/details/lesmiserables_t4_1208_librivox">Internet Archive Page</a>
                m = re.search(r'^/(?P<book_id>[\w-]+)/?$', p.path)
                if m:
                    app.args.dir = m.group('book_id')
            elif p.hostname in ('archive.org', 'www.archive.org'):
                # https://archive.org/details/les_miserables_tome_1_di_0910_librivox
                # https://archive.org/download/les_miserables_tome_1_di_0910_librivox
                # https://archive.org/download/les_miserables_tome_1_di_0910_librivox/les_miserables_tome_1_di_0910_librivox_files.xml
                m = re.search(r'^/(?:details|download)/(?P<book_id>[\w-]+)/?$', p.path)
                if m:
                    app.args.dir = m.group('book_id')
        if app.args.dir is None:
            app.parser.error(_('the following arguments is required: %s') % ('--dir',))

    args_file = json.JsonFile(file_name=app.args.dir / 'librivox-dl.args.json')
    if app.args._continue:
        with args_file.open(mode='r', encoding='utf-8') as fp:
            new_args = {k: v for k, v in vars(app.args).items() if v is not None}
            old_args = dict(json.load(fp))
            app.args = argparse.Namespace()
            app.args.__dict__ = old_args.copy()
            app.args.__dict__.update(new_args)
    else:
        os.makedirs(app.args.dir, exist_ok=True)
    with args_file.open(mode='w', encoding='utf-8') as fp:
        json.dump(
                {k: v for k, v in vars(app.args).items() if k not in ('logging_level',)},
                fp, indent=2, sort_keys=True)
        print('', file=fp)

    url = app.args.url
    p = urllib.parse.urlparse(url)
    if p.hostname in ('librivox.org', 'www.librivox.org'):
        # https://librivox.org/les-miserables-tome-4-by-victor-hugo/
        # <a href="http://archive.org/details/lesmiserables_t4_1208_librivox">Internet Archive Page</a>
        rel_librivox_html_file = 'librivox.html'
        librivox_html_file = HtmlFile(file_name=app.args.dir / rel_librivox_html_file)
        librivox_html_file.download(url=url)
        page = librivox_html_file.read()
        m = re.search(r'<a href="([^"]+)">Internet Archive Page</a>', page)
        url = m.group(1)
        p = urllib.parse.urlparse(url)
    if p.hostname in ('archive.org', 'www.archive.org'):
        # https://archive.org/details/les_miserables_tome_1_di_0910_librivox
        # https://archive.org/download/les_miserables_tome_1_di_0910_librivox
        # https://archive.org/download/les_miserables_tome_1_di_0910_librivox/les_miserables_tome_1_di_0910_librivox_files.xml
        m = re.search(r'^/(?:details|download)/(?P<book_id>[\w-]+)/?$', p.path)
        if not m:
            raise ValueError('Unrecognized archive.org URL: %s' % (url,))
    else:
        raise ValueError('Unrecognized URL: %s' % (url,))
    book_info = LibrivoxBook(**m.groupdict())
    rel_file_index_xml = Path(urllib.parse.urlparse(book_info.url_download_index_xml).path).name
    file_index_xml = LibrivoxIndexFile(file_name=app.args.dir / rel_file_index_xml, load=False)
    book_info.file_index_xml = rel_file_index_xml
    file_index_xml.download(url=book_info.url_download_index_xml)

    file_index_xml.load()

    book_info.snd_files = []
    orig_snd_file_infos = file_index_xml.original_sound_files
    if not orig_snd_file_infos:
        raise ValueError('No original sound files found')
    first_file = True
    for orig_snd_file_info in orig_snd_file_infos:
        orig_snd_file_format = orig_snd_file_info.format
        if app.args.format and orig_snd_file_format != app.args.format:
            snd_file_infos = [file_info for file_info in file_index_xml.derivative_files_of(orig_snd_file_info.name) if file_info.format==app.args.format]
            if not snd_file_infos:
                raise ValueError('No %s sound file matching %s' % (app.args.format, orig_snd_file_info.name))
            if len(snd_file_infos) > 1:
                raise ValueError('Multiple %s sound file matching %s' % (app.args.format, orig_snd_file_info.name))
            snd_file_info = snd_file_infos[0]
        else:
            snd_file_info = orig_snd_file_info
        url_file = urllib.parse.urljoin(book_info.url_download_base, snd_file_info.name)
        snd_file = SoundFile.new_by_file_name(
            app.args.dir / snd_file_info.format / Path(urllib.parse.urlparse(url_file).path).name)
        snd_file.parent.mkdir(parents=True, exist_ok=True)
        if snd_file.download(url=url_file, md5=snd_file_info.md5) and first_file:
            if not snd_file.test_integrity():
                app.log.info('Other formats:\n    ' + '\n    '.join(
                    [t
                        for t in [file_info.format
                            for file_info in file_index_xml.derivative_files_of(orig_snd_file_info.name)] + [
                                orig_snd_file_format,
                                ]
                        if t not in (snd_file_info.format, 'Spectrogram', 'PNG')]
                    ))
                exit(1)
        book_info.snd_files.append(snd_file.relative_to(app.args.dir))
        first_file = False

    cover_file_info = next(file_index_xml.original_image_files)
    url_file = urllib.parse.urljoin(book_info.url_download_base, cover_file_info.name)
    rel_cover_file = Path(urllib.parse.urlparse(url_file).path).name
    book_info.cover_file = rel_cover_file
    audiobook.cover_file = ImageFile.new_by_file_name(app.args.dir / rel_cover_file)
    audiobook.cover_file.download(url=url_file, md5=cover_file_info.md5)

    book_info_file = json.JsonFile(file_name=app.args.dir / 'librivox-dl.book_info.json')
    with book_info_file.open(mode='w', encoding='utf-8') as fp:
        json.dump(vars(book_info), fp, indent=2, sort_keys=True)
        print('', file=fp)

    if app.args.m4b:
        audiobook.create_mkm4b(
                snd_files=[app.args.dir / e for e in book_info.snd_files],
                out_dir=app.args.dir,
                interactive=app.args.interactive,
                **dict({k[4:]: v for k, v in vars(app.args).items() if k.startswith('m4b-')}))

    app.log.info('DONE!')

if __name__ == "__main__":
    main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
