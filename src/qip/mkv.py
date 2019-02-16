
__all__ = (
    'MkvFile',
)

# https://matroska.org/technical/specs/tagging/index.html
# http://wiki.webmproject.org/webm-metadata/global-metadata

import logging
log = logging.getLogger(__name__)

import qip.snd as snd

mkv_tag_map = {
    (50, 'EPISODE', 'PART_NUMBER'): 'episode',
    (50, None, 'ARTIST'): 'artist',
    (50, None, 'ORIGNAL_MEDIA_TYPE'): 'mediatype',
    (50, None, 'CONTENT_TYPE'): 'contenttype',
    (50, None, 'DATE_RELEASED'): 'date',
    (50, None, 'ENCODER'): 'tool',
    (50, None, 'GENRE'): 'genre',
    (50, None, 'PART_NUMBER'): 'track',
    (50, None, 'TITLE'): 'title',
    (50, None, 'TOTAL_PARTS'): 'tracks',
    (60, 'SEASON', 'PART_NUMBER'): 'season',
    (70, 'COLLECTION', 'TITLE'): 'tvshow',
    }

class MkvFile(snd.SoundFile):

    @property
    def tag_writer(self):
        return snd.taged

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
