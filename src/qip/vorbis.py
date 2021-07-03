# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
)

_vorbis_tag_map = {
    # https://xiph.org/vorbis/doc/v-comment.html
    'title': 'title',
    'version': 'subtitle',  # TODO CHECK!
    'album': 'albumtitle',
    'tracknumber': 'track',
    'artist': 'artist',
    'performer': 'performer',
    'copyright': 'copyright',
    'license': 'license',
    'organization': 'record_label',
    'description': 'description',
    'genre': 'genre',
    'date': 'date',  # TODO vs recording_date
    'location': 'recording_location',
    'contact': 'encodedby',  # TODO CHECK!
    'isrc': 'isrc',
    # More:
    'composer': 'composer',
    'albumartist': 'albumartist',
    'comment': 'comment',
    'discnumber': 'disk',
    'disctotal': 'disks',
    'totaldiscs': 'disks',  # HDtracks
    'tracktotal': 'tracks',
    'totaltracks': 'tracks',  # HDtracks
    'publisher': 'publisher',  # HDtracks
    'upc': 'barcode',  # HDtracks
    'encoder': 'tool',  # ffmpeg?
    # Opus (https://datatracker.ietf.org/doc/html/rfc7845#section-5.2.1)
    # 'R128_TRACK_GAIN': ,
    # 'R128_ALBUM_GAIN': ,
}

_vorbis_picture_extensions = (
    # https://wiki.xiph.org/index.php/VorbisComment#Cover_art
    '.png',
    '.jpg',
    '.jpeg',
)
