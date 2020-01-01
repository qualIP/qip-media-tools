
__all__ = [
        'SubtitleEdit',
        ]

import logging
import os
from pathlib import Path
log = logging.getLogger(__name__)

from .exec import *
from .file import *
from qip.app import app
from qip.isolang import isolang

class CSubtitleEdit(Executable):

    name = 'SubtitleEdit'

    run_func = staticmethod(do_spawn_cmd)

    kwargs_to_cmdargs = Executable.kwargs_to_cmdargs_win_slash

    @property
    def config_dir(self):
        config_home = os.environ.get('XDG_CONFIG_HOME', None)
        config_home = Path(config_home) if config_home else Path.home() / '.config'
        return config_home / 'Subtitle Edit'

    @property
    def settings_file_name(self):
        return self.config_dir / 'Settings.xml'

    def read_settings_xml(self):
        import xml.etree.ElementTree as ET
        settings_xml = ET.parse(os.fspath(self.settings_file_name))
        return settings_xml

    def save_settings_xml(self, settings_xml):
        from qip.file import TempFile
        settings_file = File.new_by_file_name(self.settings_file_name)
        with settings_file.rename_temporarily(replace_ok=True):
            with settings_file.open(mode='w') as fp:
                settings_xml.write(fp,
                                   xml_declaration=True,
                                   encoding='unicode')

    def _run(self, *args,
             language=None, seed_file_name=None,
             dry_run=None,
             **kwargs):
        if dry_run is None:
             dry_run = getattr(app.args, 'dry_run', False)
        if language:
            import xml.etree.ElementTree as ET
            settings_xml = self.read_settings_xml()
            if not dry_run:
                bDidSomething = False
                settings_root = settings_xml.getroot()
                if language:
                    language = isolang(language).code3
                    eVobSubOcr = settings_root.find('VobSubOcr')
                    if eVobSubOcr is None:
                        eVobSubOcr = ET.SubElement(settings_root, 'VobSubOcr')
                    eTesseractLastLanguage = eVobSubOcr.find('TesseractLastLanguage')
                    if eTesseractLastLanguage is None:
                        eTesseractLastLanguage = ET.SubElement(eVobSubOcr, 'TesseractLastLanguage')
                    if eTesseractLastLanguage.text != language:
                        eTesseractLastLanguage.text = language
                        bDidSomething = True
                if bDidSomething:
                    self.save_settings_xml(settings_xml)
        if seed_file_name:
            seed_file_name = Path(seed_file_name)
            import xml.etree.ElementTree as ET
            from qip.mono import mono
            mwf_config_xml = mono.read_mwf_config_xml()
            if not dry_run:
                bDidSomething = False
                mwf_config_root = mwf_config_xml.getroot()
                if seed_file_name:
                    seed_file_name = seed_file_name.resolve()
                    seed_dir = seed_file_name.parent
                    eFileDialog = mwf_config_root.find('FileDialog')
                    if eFileDialog is None:
                        eFileDialog = ET.SubElement(mwf_config_root, 'FileDialog')
                    eFileNames = eFileDialog.find('value[@name="FileNames"]')
                    if eFileNames is None:
                        eFileNames = ET.SubElement(eFileDialog, 'value', attrib={
                            'name': 'FileNames',
                            'type': 'string-array',
                        })
                    l_FileNames = [e.text for e in eFileNames.findall('string')]
                    if l_FileNames != [os.fspath(seed_file_name)]:
                        for e in eFileNames:
                            eFileNames.remove(e)
                        eString = ET.SubElement(eFileNames, 'string')
                        eString.text = os.fspath(seed_file_name)
                        bDidSomething = True
                    eLastFolder = eFileDialog.find('value[@name="LastFolder"]')
                    if eLastFolder is None:
                        eLastFolder = ET.SubElement(eFileDialog, 'value', attrib={
                            'name': 'LastFolder',
                            'type': 'string',
                        })
                    if eLastFolder.text != seed_dir:
                        eLastFolder.text = os.fspath(seed_dir)
                        bDidSomething = True
                if bDidSomething:
                    mono.save_mwf_config_xml(mwf_config_xml)
        return super()._run(*args, dry_run=dry_run, **kwargs)

SubtitleEdit = CSubtitleEdit()
