
__all__ = [
        'mediainfo',
        ]

import re
import logging
log = logging.getLogger(__name__)

from .exec import *
from .parser import lines_parser
from .utils import Timestamp, byte_decode, Ratio

class Mediainfo(Executable):

    name = 'mediainfo'

    run_func = staticmethod(dbg_exec_cmd)

    @classmethod
    def kwargs_to_cmdargs(cls, **kwargs):
        cmdargs = []
        for k, v in kwargs.items():
            if v in (None, False):
                # Dropped for ease of passing unused arguments
                continue
            k = {
                '_class': 'class',
                '_continue': 'continue',
            }.get(k, k)
            arg = '-' + k if len(k) == 1 else '--' + k
            if v is True:
                cmdargs.append(arg)
            else:
                cmdargs.append('%s=%s' % (arg, v))
        return cmdargs

    def parse(self, mediainfo_out):
        mediainfo_out = byte_decode(mediainfo_out)
        log.debug('mediainfo_out: \n%s', mediainfo_out)
        out_dict = {
            'media': {
                'track': []
            }
        }
        parser = lines_parser(mediainfo_out.split('\n'))
        while parser.advance():
            line = parser.line.strip()
            if line == '':
                continue
            track_type = line
            m = re.match(r'^(?P<track_type>\w+) #(\d+)$', track_type)
            if m:
                track_type = m.group('track_type')
            assert track_type in (
                'General',
                'Video',
                'Image',
                'Audio',
                'Text',
                'Menu',
            ), track_type
            track_dict = {
                '@type': track_type,
            }
            def scan_mediainfo_timestamp(v):
                v = re.sub(r' h *', 'h', v)
                v = re.sub(r' min *', 'm', v)
                v = re.sub(r' s *', 's', v)
                v = re.sub(r'(?P<s>\d+)s(?P<ms>\d{1,3}) ms', lambda m: '%d.%03d' % (int(m.group('s')), int(m.group('ms'))), v)
                v = re.sub(r'^(?P<sign>-?)(?P<ms>\d{1,3}) ms', lambda m: '%s0.%03d' % (m.group('sign'), int(m.group('ms'))), v)
                v = Timestamp(v)
                return v
            def scan_mediainfo_pixels(v):
                m = re.match(r'^(?P<v>\d+(?: \d\d\d)*) pixels$', v)
                assert m, (k, v)
                v = int(m.group('v').replace(' ', ''))
                return v
            while parser.advance():
                line = parser.line.strip()
                if line == '':
                    break
                m = (
                    re.match(r'^(?P<k>[^:]+):(?: |$)(?P<v>.*)$', line) or
                    re.match(r'^(?P<k>\d\d:\d\d:\d\d.\d\d\d) *:(?: |$)(?P<v>.*)$', line)  # (Menu) 00:00:00.000  : en:Chapter 01
                )
                assert m, line
                k, v = m.group('k').strip(), m.group('v').strip()
                if k in ('ID', 'ID in the original source medium'):
                    k = {
                        'ID': 'ID',
                        'ID in the original source medium': 'OriginalSourceMedium_ID',
                    }[k]
                    # 1
                    # 224 (0xE0)
                    # 189 (0xBD)-128 (0x80)
                    # 189 (0xBD)32 (0x20)
                    m = re.match(r'^((?P<int>-?\d{1,3}) \(0x(?P<hex>[0-9A-Fa-f]{2})\))*$', v)
                    if m:
                        v = int(
                            ''.join(tup[1] for tup in re.findall(r'(?P<int>-?\d{1,3}) \(0x(?P<hex>[0-9A-Fa-f]{2})\)', v)),
                            16)
                    else:
                        try:
                            v = int(v)
                        except ValueError:
                            pass
                elif k == 'Format':
                    k = 'Format'
                elif k == 'Format version':
                    k = 'FormatVersion'
                elif k == 'Duration':
                    # 2 h 13 min
                    k = 'Duration'
                    v = str(scan_mediainfo_timestamp(v).seconds)
                elif k == 'Delay relative to video':
                    # 7 m 7 s
                    k = 'Delay'
                    v = str(scan_mediainfo_timestamp(v).seconds)
                    assert 'Delay_Source' not in track_dict
                    track_dict['Delay_Source'] = 'Container'
                elif k in (
                    'Original frame rate',
                    'Frame rate',
                ):
                    k = ''.join(k.title().split())  # OriginalFrameRate, FrameRate
                    # 23.976 (24000/1001) FPS
                    m = re.match(r'^(?P<float>\d+\.\d+) \((?P<ratio>\d+/\d+)\) FPS$', v)
                    if m:
                        v = m.group('ratio')
                    else:
                        # 1 000.000 FPS
                        m = re.match(r'^(?P<float>\d+(?: \d\d\d)*\.\d+) FPS$', v)
                        if m:
                            v = m.group('float').replace(' ', '')
                        else:
                            # 31.250 FPS (1536 SPF)
                            m = re.match(r'^(?P<float>\d+(?: \d\d\d)*\.\d+) FPS \((?P<spf>\d+) SPF\)$', v)
                            if m:
                                v = m.group('float').replace(' ', '')
                            else:
                                raise ValueError((k, v))
                elif k == 'Scan type':
                    k = 'ScanType'
                elif k == 'Original source medium':
                    k = 'OriginalSourceMedium'
                elif k == 'Scan order':
                    k = 'ScanOrder'
                elif k == 'Display aspect ratio':
                    # 16:9
                    # 2.40:1
                    k = 'DisplayAspectRatio'
                elif k == 'Width':
                    # 780 pixels
                    # 1 920 pixels
                    k = 'Width'
                    v = str(scan_mediainfo_pixels(v))
                elif k == 'Height':
                    # 480 pixels
                    # 1 080 pixels
                    k = 'Height'
                    v = str(scan_mediainfo_pixels(v))
                elif k == 'Sampling rate':
                    k = 'SamplingRate'
                    # 48.0 kHz
                    m = re.match(r'^(?P<float>\d+\.\d{1,3}) kHz$', v)
                    if m:
                        v = int(float(m.group('float')) * 1000)
                    else:
                        raise ValueError((k, v))
                elif k == 'Writing application':
                    k = 'Encoded_Application'
                elif k == 'Format profile':
                    k = 'Format_Profile'
                elif k == 'MultiView_Count':
                    k = 'MultiView_Count'
                elif k == 'MultiView_Layout':
                    k = 'MultiView_Layout'
                else:
                    continue  # skip
                track_dict[k] = v
            try:
                Width = track_dict['Width']
                Height = track_dict['Height']
                DisplayAspectRatio = track_dict['DisplayAspectRatio']
            except KeyError:
                pass
            else:
                StorageAspectRatio = Ratio(Width, Height)
                DisplayAspectRatio = Ratio(DisplayAspectRatio)
                PixelAspectRatio = DisplayAspectRatio / StorageAspectRatio
                track_dict['PixelAspectRatio'] = str(PixelAspectRatio)
            out_dict['media']['track'].append(track_dict)
        return out_dict

mediainfo = Mediainfo()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
