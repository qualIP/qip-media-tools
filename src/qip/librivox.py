# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'LibrivoxBook',
        'LibrivoxIndexFile',
        ]

import functools
import types
import urllib.parse
import xml.etree.ElementTree as ET

from qip.file import *
from qip.cmp import *

class LibrivoxIndexFile(XmlFile):

    class FileInfo(types.SimpleNamespace):

        @staticmethod
        def cmp_original_sound_files_by_track(elem1, elem2):
            t1 = getattr(elem1, 'track', None)
            t2 = getattr(elem2, 'track', None)
            t1 = int(t1.split('/')[0]) if t1 else 0
            t2 = int(t2.split('/')[0]) if t2 else 0
            return genericcmp(t1, t2)

    def __init__(self, file_name, load=None, **kwargs):
        if load is None:
            load = file_name is not None
        super().__init__(file_name=file_name, **kwargs)
        if load:
            load()

    def load(self):
        tree = ET.parse(self.file_name)
        root = tree.getroot()
        self.originals = set()
        self.files = {}
        for file_elem in root:
            name = file_elem.attrib['name']
            source = file_elem.attrib['source']
            self.files[name] = file = LibrivoxIndexFile.FileInfo(
                    name=name,
                    source=source,
                    **{e.tag: e.text for e in file_elem})
            if file.source == 'original':
                self.originals.add(name)

    @property
    def original_files(self):
        return (file_info
                for file_info in self.files.values()
                if file_info.source == 'original')

    @property
    def derivative_files(self):
        return (file_info
                for file_info in self.files.values()
                if file_info.source == 'derivative')

    @property
    def metadata_files(self):
        return (file_info
                for file_info in self.files.values()
                if file_info.format == 'Metadata')

    def derivative_files_of(self, original):
        return (file_info
                for file_info in self.derivative_files
                if getattr(file_info, 'original', None) == original)

    @property
    def original_sound_files(self):
        return sorted((file_info
                for file_info in self.original_files
                if hasattr(file_info, 'title')),  # tried [track]
                key=functools.cmp_to_key(LibrivoxIndexFile.FileInfo.cmp_original_sound_files_by_track))

    @property
    def original_image_files(self):
        return (file_info
                for file_info in self.original_files
                if file_info.format in ('JPEG', 'PNG', 'GIF'))

class LibrivoxBook(object):

    @property
    def url_download_base(self):
        return 'https://archive.org/download/{b.book_id}/'.format(b=self)

    @property
    def url_download_index_xml(self):
        return urllib.parse.urljoin(self.url_download_base,
                '{b.book_id}_files.xml'.format(b=self))

    def __init__(self, book_id):
        self.book_id = book_id
