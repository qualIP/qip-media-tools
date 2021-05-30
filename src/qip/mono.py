# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'mono',
        ]

import logging
import os
from pathlib import Path
log = logging.getLogger(__name__)

from .exec import *
from qip.app import app
from qip.isolang import isolang

class Mono(Executable):

    name = 'mono'

    @property
    def config_dir(self):
        config_dir = Path.home() / '.mono'
        return config_dir

    @property
    def mwf_config_file_name(self):
        return self.config_dir / 'mwf_config'

    def read_mwf_config_xml(self):
        import xml.etree.ElementTree as ET
        try:
            mwf_config_xml = ET.parse(self.mwf_config_file_name)
        except FileNotFoundError:
            mwf_config_xml = ET.ElementTree(ET.fromstring('<MWFConfig />'))
        return mwf_config_xml

    def save_mwf_config_xml(self, mwf_config_xml):
        from qip.file import TempFile
        with TempFile(self.mwf_config_file_name.with_suffix(self.mwf_config_file_name.suffix + '.tmp')) as tmp_file:
            tmp_file.fp = tmp_file.open(mode='wt', encoding='utf-8')
            mwf_config_xml.write(tmp_file.fp,
                                 #xml_declaration=True,
                                 encoding='unicode')
            tmp_file.close()
            os.replace(
                src=tmp_file.file_name,
                dst=self.mwf_config_file_name)

mono = Mono()
