# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
    'PgsFile',
)

# http://blog.thescorpius.com/index.php/2017/07/15/presentation-graphic-stream-sup-files-bluray-subtitle-format/

import enum
import itertools
import logging
import struct
import types
log = logging.getLogger(__name__)

from .mm import BinarySubtitleFile

pgs_segment_header_st = struct.Struct('!2sIIBH')
"""
PGS Segment Header
Name            Size in bytes   Description
Magic Number    2               "PG" (0x5047)
PTS             4               Presentation Timestamp (90kHz)
DTS             4               Decoding Timestamp (90kHz)
Segment Type    1               0x14: PDS
                                0x15: ODS
                                0x16: PCS
                                0x17: WDS
                                0x80: END
Segment Size    2               Size of the segment
"""

def test_pgs_segment_magic_number(magic_number):
    if magic_number != b'PG':
        raise ValueError(f'Invalid PGS segment magic: {magic_number!r}')
    return magic_number

class PgsSegmentTypeEnum(enum.IntEnum):
    PDS = 0x14
    ODS = 0x15
    PCS = 0x16
    WDS = 0x17
    END = 0x80

def pgs_read_segment_header(fp):
    buf = fp.read(pgs_segment_header_st.size)
    if buf == b'':
        return None
    try:
        magic_number, pts, dts, segment_type, segment_size = \
            pgs_segment_header_st.unpack(buf)
    except Exception as e:
        raise ValueError(f'Error reading PGS segment header from buffer of {len(buf)} bytes: {e}')
    return types.SimpleNamespace(
        magic_number=test_pgs_segment_magic_number(magic_number),
        pts=pts,
        dts=dts,
        segment_type=PgsSegmentTypeEnum(segment_type),
        segment_size=segment_size,
    )

def pgs_read_segment(fp):
    segment_header = pgs_read_segment_header(fp)
    if segment_header is None:
        return None
    next_st = {
        PgsSegmentTypeEnum.PDS: pgs_read_pds_segment,
        PgsSegmentTypeEnum.ODS: pgs_read_ods_segment,
        PgsSegmentTypeEnum.PCS: pgs_read_pcs_segment,
        PgsSegmentTypeEnum.WDS: pgs_read_wds_segment,
        PgsSegmentTypeEnum.END: pgs_read_end_segment,
    }[segment_header.segment_type]
    return next_st(segment_header=segment_header, fp=fp)


## Palette Definition Segment

YCbCr_white = (235, 128, 128)

pgs_pds_segment_header_st = struct.Struct('!BB')
"""
Name                        Size in bytes   Definition
Palette ID                  1               ID of the palette
Palette Version Number      1               Version of this palette within the Epoch
"""

pgs_pds_segment_entry_st = struct.Struct('!BBBBB')
"""
Palette Entry ID            1               Entry number of the palette
Luminance (Y)               1               Luminance (Y value)
Color Difference Red (Cr)   1               Color Difference Red (Cr value)
Color Difference Blue (Cb)  1               Color Difference Blue (Cb value)
Transparency (Alpha)        1               Transparency (Alpha value)
"""

def pgs_read_pds_segment(segment_header, fp):
    offset = 0
    buf = fp.read(segment_header.segment_size)
    try:
        palette_id, palette_version_number = \
            pgs_pds_segment_header_st.unpack_from(buf, offset=offset)
    except Exception as e:
        raise ValueError(f'Error reading PGS PDS segment header from buffer of {len(buf)} bytes: {e}')
    offset += pgs_pds_segment_header_st.size
    pds_segment = types.SimpleNamespace(
        palette_id=palette_id,
        palette_version_number=palette_version_number,
        palette_entries=[],
        **vars(segment_header),
    )
    while offset < len(buf):
        try:
            palette_entry_id, luminance, color_difference_red, color_difference_blue, transparency = \
                pgs_pds_segment_entry_st.unpack_from(buf, offset=offset)
        except Exception as e:
            raise ValueError(f'Error reading PGS PDS segment entry from offset {offset} of buffer of {len(buf)} bytes: {e}')
        offset += pgs_pds_segment_entry_st.size
        pds_segment.palette_entries.append(types.SimpleNamespace(
            palette_entry_id=palette_entry_id,
            luminance=luminance,
            color_difference_red=color_difference_red,
            color_difference_blue=color_difference_blue,
            transparency=transparency,
        ))
    return pds_segment

def pgs_segment_to_YCbCr_palette(pgs_segment):
    palette = list(itertools.repeat(bytes(YCbCr_white), 256))
    if pgs_segment is not None:
        for pgs_palette in pgs_segment.palette_entries:
            palette[pgs_palette.palette_entry_id] = \
                bytes([pgs_palette.luminance, pgs_palette.color_difference_blue, pgs_palette.color_difference_red])
    return palette

## Object Definition Segment

pgs_ods_segment_st = struct.Struct('!HBBBBBHH')
"""
Name                        Size in bytes   Definition
Object ID                   2               ID of this object
Object Version Number       1               Version of this object
Last in Sequence Flag       1               If the image is split into a series of consecutive fragments, the last fragment has this flag set. Possible values:
                                            0x40: Last in sequence
                                            0x80: First in sequence
                                            0xC0: First and last in sequence (0x40 | 0x80)
Object Data Length          3               The length of the Run-length Encoding (RLE) data buffer with the compressed image data.
Width                       2               Width of the image
Height                      2               Height of the image
Object Data                 variable        This is the image data compressed using Run-length Encoding (RLE). The size of the data is defined in the Object Data Length field.
"""

class PgsOdsSequenceFlags(enum.IntEnum):
    LastInSequence = 0x40
    FirstInSequence = 0x80
    FirstAndLastInSequence = FirstInSequence | LastInSequence

def pgs_read_ods_segment(segment_header, fp):
    offset = 0
    buf = fp.read(segment_header.segment_size)
    try:
        object_id, object_version_numner, sequence_flags, l1, l2, l3, width, height = \
            pgs_ods_segment_st.unpack_from(buf, offset=offset)
    except Exception as e:
        raise ValueError(f'Error reading PGS ODS segment from buffer of {len(buf)} bytes: {e}')
    object_data_length = (l1 << 16) | (l2 << 8) | l3
    offset += pgs_ods_segment_st.size
    if len(buf) - offset != (object_data_length - 4):  # -4 because Width and Height is part of the "object data"
        raise ValueError(f'Invalid object data length {object_data_length} for PGS ODS segment of size {segment_header.segment_sizer}')
    ods_segment = types.SimpleNamespace(
        object_id=object_id,
        object_version_numner=object_version_numner,
        sequence_flags=sequence_flags,
        object_data_length=object_data_length,
        width=width,
        height=height,
        object_data=buf[offset:],
        **vars(segment_header),
    )
    return ods_segment


## Presentation Composition Segment

pgs_pcs_segment_st = struct.Struct('!HHBHBBBB')
"""
Name                          Size in bytes   Description
Width                         2               Video width in pixels (ex. 0x780 = 1920)
Height                        2               Video height in pixels (ex. 0x438 = 1080)
Frame Rate                    1               Always 0x10. Can be ignored.
Composition Number            2               Number of this specific composition. It is incremented by one every time a graphics update occurs.
Composition State             1               Type of this composition. Allowed values are:
                                              0x00: Normal
                                              0x40: Acquisition Point
                                              0x80: Epoch Start
Palette Update Flag           1               Indicates if this PCS describes a Palette only Display Update. Allowed values are:
                                              0x00: False
                                              0x80: True
Palette ID                    1               ID of the palette to be used in the Palette only Display Update
Number of Composition Objects 1               Number of composition objects defined in this segment
"""

class PgsPcsCompositionStateEnum(enum.IntEnum):
    Normal = 0x00
    AcquisitionPoint = 0x40
    EpochStart = 0x80

class PaletteUpdateFlagEnum(enum.IntEnum):
    _False = 0x00
    _True = 0x80

def PaletteUpdateFlag(e):
    e = PaletteUpdateFlagEnum(e)
    return {
        PaletteUpdateFlagEnum._False: False,
        PaletteUpdateFlagEnum._True: True,
    }[e]

def pgs_read_pcs_segment(segment_header, fp):
    offset = 0
    buf = fp.read(segment_header.segment_size)
    try:
        width, height, frame_rate, composition_number, composition_state, palette_update_flag, palette_id, composition_objects_count = \
            pgs_pcs_segment_st.unpack_from(buf, offset=offset)
    except Exception as e:
        raise ValueError(f'Error reading PGS PCS segment header from buffer of {len(buf)} bytes: {e}')
    offset += pgs_pcs_segment_st.size
    pcs_segment = types.SimpleNamespace(
        width=width,
        height=height,
        frame_rate=frame_rate,
        composition_number=composition_number,
        composition_state=PgsPcsCompositionStateEnum(composition_state),
        palette_update_flag=PaletteUpdateFlag(palette_update_flag),
        palette_id=palette_id,
        composition_objects_count=composition_objects_count,
        composition_objects_data=buf[offset:],
        **vars(segment_header),
    )
    return pcs_segment


## Window Definition Segment

pgs_wds_segment_header_st = struct.Struct('!B')
"""
Name                        Size in bytes   Description
Number of Windows           1               Number of windows defined in this segment
"""

pgs_wds_segment_entry_st = struct.Struct('!BHHHH')
"""
Name                        Size in bytes   Description
Window ID                   1               ID of this window
Window Horizontal Position  2               X offset from the top left pixel of the window in the screen.
Window Vertical Position    2               Y offset from the top left pixel of the window in the screen.
Window Width                2               Width of the window
Window Height               2               Height of the window
"""

def pgs_read_wds_segment(segment_header, fp):
    offset = 0
    buf = fp.read(segment_header.segment_size)
    try:
        windows_count, = \
            pgs_wds_segment_header_st.unpack_from(buf, offset=offset)
    except Exception as e:
        raise ValueError(f'Error reading PGS WDS segment header from buffer of {len(buf)} bytes: {e}')
    offset += pgs_wds_segment_header_st.size
    wds_segment = types.SimpleNamespace(
        windows_count=windows_count,
        window_entries=[],
        **vars(segment_header),
    )
    for i in range(windows_count):
        try:
            window_id, horizontal_pos, vertical_pos, width, height = \
                pgs_wds_segment_entry_st.unpack_from(buf, offset=offset)
        except Exception as e:
            raise ValueError(f'Error reading PGS WDS segment entry from offset {offset} of buffer of {len(buf)} bytes: {e}')
        offset += pgs_wds_segment_entry_st.size
        wds_segment.window_entries.append(types.SimpleNamespace(
            window_id=window_id,
            horizontal_pos=horizontal_pos,
            vertical_pos=vertical_pos,
            width=width,
            height=height,
        ))
    if offset != segment_header.segment_size:
        raise ValueError(f'Invalid number of windows in segment: {windows_count} ({segment_header.segment_size - offset} bytes unused)')
    return wds_segment


## End Segment

def pgs_read_end_segment(segment_header, fp):
    if segment_header.segment_size != 0:
        raise ValueError(f'Invalid END segment size: {segment_header.segment_size}')
    return segment_header


def pgs_iter_segments(fp):
    while True:
        pgs_segment = pgs_read_segment(fp)
        if pgs_segment is None:
            break
        yield pgs_segment

class PgsFile(BinarySubtitleFile):
    # HDMV Presentation Graphic Stream subtitles

    _common_extensions = (
        '.sup',
    )

    ffmpeg_container_format = 'sup'

    SegmentType = PgsSegmentTypeEnum
    OdsSequenceFlags = PgsOdsSequenceFlags

    def iter_pgs_segments(self):
        if self.fp is not None:
            return pgs_iter_segments(self.fp)
        with self.open(mode='r') as fp:
            return iter(list(pgs_iter_segments(fp)))

def rle_decode(rle_data, width, height, palette=None):
    palettize = (lambda entry: entry) if palette is None else (lambda entry: palette[entry])

    # See https://github.com/Sec-ant/BDSupReader/blob/master/src/RunLength.c
    # offset = 0  # width and height passed in
    idata = iter(rle_data)
    i = 0
    while True:
        first = next(idata)
        if first > 0:
            # repeat = 1
            # entry = first
            yield palettize(first)
            # offset += 1
        else:
            second = next(idata)
            if second == 0:
                repeat = 0
                entry = 0
                i += 1
                if i == height:
                    break
                # offset += 2
            elif second < 64:
                repeat = second
                entry = 0
                # offset += 2
            elif second < 128:
                repeat = ((second - 64) << 8) + next(idata)
                entry = 0
                # offset += 3
            elif second < 192:
                repeat = second - 128
                entry = next(idata)
                # offset += 3
            else:
                repeat = ((second - 192) << 8) + next(idata)
                entry = next(idata)
                # offset += 4
            yield from itertools.repeat(palettize(entry), repeat)
    if i < height:
        log.warning('rle_decode: Hanging pixels without line ending (expected: %d, actual: %d)', height, i)

PgsFile._build_extension_to_class_map()
