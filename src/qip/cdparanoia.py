# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'cdparanoia',
        ]

from .parser import *
from .exec import *
from .cdda import *

import re
import subprocess
import time

class Cdparanoia(Executable):

    name = 'cdparanoia'

    def run_wrapper(self,
            *args,
            retry_no_audio_cd=False,
            **kwargs):
        if retry_no_audio_cd is True:
            retry_no_audio_cd = 8
        while True:
            try:
                return self._run(*args, **kwargs)
            except subprocess.CalledProcessError as e:
                if retry_no_audio_cd and e.returncode in (1, 2) and e.output and re.search(
                        r'Unable to open disc\.  Is there an audio CD in the drive\?[\r\n]*$',
                        e.output):
                    time.sleep(2)
                    retry_no_audio_cd -= 1
                    continue
                raise

    def query(self,
            device=None,
            verbose=False,
            retry_no_audio_cd=False,
            **kwargs):
        args = ['--query']
        assert isinstance(verbose, bool)
        if verbose:
            args += ['--verbose']
        if device:
            args += ['--force-cdrom-device', device]
        d = self.run_wrapper(*args, retry_no_audio_cd=retry_no_audio_cd, **kwargs)
        parser = lines_parser(self.clean_cmd_output(d.out).splitlines())
        while parser.advance():
            if parser.line == '':
                pass
            elif parser.line == 'Table of contents (audio tracks only):':
                assert not hasattr(d, 'toc')
                d.toc = self._parse_toc(parser)
            else:
                # cdparanoia III release 10.2 (September 11, 2008)
                #
                # Using cdda library version: 10.2
                # Using paranoia library version: 10.2
                # Checking /dev/cdrom for cdrom...
                #     Testing /dev/cdrom for SCSI/MMC interface
                # 	SG_IO device: /dev/sr1
                #
                # CDROM model sensed sensed: ASUS BW-12B1ST   a 1.00
                #
                #
                # Checking for SCSI emulation...
                #     Drive is ATAPI (using SG_IO host adaptor emulation)
                #
                # Checking for MMC style command set...
                #     Drive is MMC style
                #     DMA scatter/gather table entries: 1
                #     table entry size: 122880 bytes
                #     maximum theoretical transfer: 52 sectors
                #     Setting default read size to 27 sectors (63504 bytes).
                #
                # Verifying CDDA command set...
                #     Expected command set reads OK.
                #
                # Attempting to set cdrom to full speed...
                #     drive returned OK.
                pass  # TODO

        return d

    def _parse_toc(self, parser):
        toc = CDToc()
        while parser.advance():
            if parser.re_search(r'^track +length +begin +copy +pre +ch$'):
                # track        length               begin        copy pre ch
                pass
            elif parser.re_search(r'^=+$'):
                # ===========================================================
                pass
            elif parser.re_search(r' *(?P<track_no>\d+)\. +(?P<length>\d+) +\[(?P<length_msf>\d\d:\d\d\.\d\d)\] +(?P<begin>\d+) +\[(?P<begin_msf>\d\d:\d\d\.\d\d)\] +(?P<copy>no|OK) +(?P<pre>no|yes) +(?P<ch>\d+)$'):
                #   1.    16503 [03:40.03]        0 [00:00.00]    no   no  2
                #   1.    16503 [03:40.03]        0 [00:00.00]    OK   no  2
                track_no = int(parser.match.group('track_no'))
                assert track_no == len(toc.tracks) + 1
                track = toc.add_track(
                        length=int(parser.match.group('length')),
                        begin=int(parser.match.group('begin')),
                        copy_permitted=parser.match.group('copy') == 'OK',
                        pre_emphasis=parser.match.group('pre') == 'yes',
                        audio_channels=int(parser.match.group('ch')),
                        )
            elif parser.re_search(r' *TOTAL +(?P<length>\d+) +\[(?P<length_msf>\d\d:\d\d\.\d\d)\] +\(audio only\)$'):
                # TOTAL  329039 [73:07.14]    (audio only)
                break
            else:
                raise ValueError('Unrecognized cdparanoia TOC line: %s' % (parser.line,))
        return toc

cdparanoia = Cdparanoia()
